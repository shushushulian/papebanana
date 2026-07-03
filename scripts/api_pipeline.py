"""Explicit, optional Gemini/OpenRouter fallback for paperbanana-codex."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from paperbanana_common import default_model_config_path, resolve_dataset_root
from retrieve_references import retrieve
from run_artifacts import create_run_directory, write_manifest
from safe_plot import PlotSecurityError, render_plot


class ApiModeNotConfirmedError(PermissionError):
    """Raised when API execution was not explicitly confirmed."""


class ApiConfigurationError(ValueError):
    """Raised when the optional API configuration is unusable."""


@dataclass(frozen=True)
class ApiSettings:
    """Resolved API provider settings with a redacted public representation."""

    provider: str
    api_key: str = field(repr=False)
    main_model_name: str = "gemini-3.1-pro-preview"
    image_gen_model_name: str = "gemini-3.1-flash-image-preview"

    def public_summary(self) -> dict[str, str]:
        """
        返回不含凭据的 API 配置摘要。
        Args:
            input: 当前 ApiSettings 实例。

        Returns:
            Output：provider 和模型名称字典。
        """
        return {
            "provider": self.provider,
            "main_model_name": self.main_model_name,
            "image_gen_model_name": self.image_gen_model_name,
        }


def require_api_confirmation(confirmed: bool) -> None:
    """
    强制要求用户当次显式确认外部 API。
    Args:
        input: confirmed 表示是否传入 --confirm-api。

    Returns:
        Output：无，未确认时抛出异常。
    """
    if not confirmed:
        raise ApiModeNotConfirmedError(
            "外部 API 未启用。只有用户明确要求使用自己的 API 时才能传入 --confirm-api。"
        )


def load_api_settings(config_path: str | Path | None = None) -> ApiSettings:
    """
    从 YAML 读取 Gemini 或 OpenRouter 配置。
    Args:
        input: 可选 model_config.yaml 路径。

    Returns:
        Output：解析后的 ApiSettings。
    """
    path = (
        Path(config_path).expanduser().resolve()
        if config_path
        else default_model_config_path()
    )
    if not path.is_file():
        raise ApiConfigurationError(f"API 配置文件不存在：{path}")
    try:
        import yaml
    except ImportError as error:
        raise ApiConfigurationError(
            "API 模式需要 PyYAML，请安装 requirements-api.txt。"
        ) from error
    with path.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle) or {}
    defaults = data.get("defaults") or {}
    keys = data.get("api_keys") or {}
    openrouter_key = str(keys.get("openrouter_api_key") or "").strip()
    google_key = str(keys.get("google_api_key") or "").strip()
    if openrouter_key:
        provider, api_key = "openrouter", openrouter_key
    elif google_key:
        provider, api_key = "google", google_key
    else:
        raise ApiConfigurationError(
            "model_config.yaml 中必须配置 openrouter_api_key 或 google_api_key。"
        )
    return ApiSettings(
        provider=provider,
        api_key=api_key,
        main_model_name=str(
            defaults.get("main_model_name") or "gemini-3.1-pro-preview"
        ),
        image_gen_model_name=str(
            defaults.get("image_gen_model_name")
            or "gemini-3.1-flash-image-preview"
        ),
    )


def _qualified_openrouter_model(model_name: str) -> str:
    """
    将 Gemini 短模型名转换为 OpenRouter 模型标识。
    Args:
        input: 配置中的模型名称。

    Returns:
        Output：OpenRouter 可接受的模型标识。
    """
    if "/" in model_name:
        return model_name
    return f"google/{model_name}" if model_name.startswith("gemini") else model_name


def _image_data_url(image_path: Path) -> str:
    """
    将本地图片转换为多模态请求 data URL。
    Args:
        input: 本地图片路径。

    Returns:
        Output：包含 MIME 和 Base64 的 data URL。
    """
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _openrouter_text(
    settings: ApiSettings,
    system_prompt: str,
    prompt: str,
    image_paths: list[Path] | None = None,
) -> str:
    """
    调用 OpenRouter 多模态文本模型。
    Args:
        input: settings、系统提示、用户提示和可选图片路径。

    Returns:
        Output：模型文本响应。
    """
    try:
        import httpx
    except ImportError as error:
        raise ApiConfigurationError(
            "OpenRouter 模式需要 httpx，请安装 requirements-api.txt。"
        ) from error
    content: list[dict] = [{"type": "text", "text": prompt}]
    for image_path in image_paths or []:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _image_data_url(image_path)},
            }
        )
    payload = {
        "model": _qualified_openrouter_model(settings.main_model_name),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "temperature": 1.0,
        "max_completion_tokens": 50000,
    }
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"].get("content") or ""
    if not str(text).strip():
        raise RuntimeError("OpenRouter 返回了空文本")
    return str(text).strip()


def _gemini_parts(prompt: str, image_paths: list[Path] | None = None) -> list:
    """
    构造 Google GenAI 多模态 Part 列表。
    Args:
        input: 文本提示和可选图片路径。

    Returns:
        Output：Google GenAI Part 列表。
    """
    try:
        from google.genai import types
    except ImportError as error:
        raise ApiConfigurationError(
            "Gemini 模式需要 google-genai，请安装 requirements-api.txt。"
        ) from error
    parts = [types.Part.from_text(text=prompt)]
    for image_path in image_paths or []:
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        parts.append(
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)
        )
    return parts


def _gemini_text(
    settings: ApiSettings,
    system_prompt: str,
    prompt: str,
    image_paths: list[Path] | None = None,
) -> str:
    """
    调用 Gemini 多模态文本模型。
    Args:
        input: settings、系统提示、用户提示和可选图片路径。

    Returns:
        Output：模型文本响应。
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise ApiConfigurationError(
            "Gemini 模式需要 google-genai，请安装 requirements-api.txt。"
        ) from error
    client = genai.Client(api_key=settings.api_key)
    response = client.models.generate_content(
        model=settings.main_model_name,
        contents=_gemini_parts(prompt, image_paths),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=1.0,
            candidate_count=1,
            max_output_tokens=50000,
        ),
    )
    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise RuntimeError("Gemini 返回了空文本")
    return text.strip()


def call_text_model(
    settings: ApiSettings,
    system_prompt: str,
    prompt: str,
    image_paths: list[Path] | None = None,
) -> str:
    """
    根据配置路由多模态文本请求。
    Args:
        input: settings、系统提示、用户提示和可选图片路径。

    Returns:
        Output：模型文本响应。
    """
    if settings.provider == "openrouter":
        return _openrouter_text(settings, system_prompt, prompt, image_paths)
    return _gemini_text(settings, system_prompt, prompt, image_paths)


def _extract_openrouter_image(message: dict) -> bytes:
    """
    从 OpenRouter 响应消息提取首张图片。
    Args:
        input: choices[0].message 字典。

    Returns:
        Output：图片二进制数据。
    """
    images = message.get("images") or []
    if images:
        image = images[0]
        data_url = (
            image.get("image_url", {}).get("url", "")
            if isinstance(image, dict)
            else str(image)
        )
        if "," in data_url:
            return base64.b64decode(data_url.split(",", 1)[1])
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            inline = part.get("inline_data") if isinstance(part, dict) else None
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    if isinstance(content, str) and content.startswith("data:image") and "," in content:
        return base64.b64decode(content.split(",", 1)[1])
    raise RuntimeError("OpenRouter 响应中没有图片")


def _openrouter_image(
    settings: ApiSettings,
    prompt: str,
    aspect_ratio: str,
    image_size: str,
) -> bytes:
    """
    调用 OpenRouter 图片生成模型。
    Args:
        input: settings、绘图提示、长宽比和图片尺寸。

    Returns:
        Output：生成图片的二进制数据。
    """
    try:
        import httpx
    except ImportError as error:
        raise ApiConfigurationError(
            "OpenRouter 模式需要 httpx，请安装 requirements-api.txt。"
        ) from error
    payload = {
        "model": _qualified_openrouter_model(settings.image_gen_model_name),
        "messages": [
            {
                "role": "system",
                "content": "You are an expert scientific diagram illustrator.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 1.0,
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        },
    }
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    return _extract_openrouter_image(response.json()["choices"][0]["message"])


def _gemini_image(
    settings: ApiSettings,
    prompt: str,
    aspect_ratio: str,
    image_size: str,
) -> bytes:
    """
    调用 Gemini 图片生成模型。
    Args:
        input: settings、绘图提示、长宽比和图片尺寸。

    Returns:
        Output：生成图片的二进制数据。
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise ApiConfigurationError(
            "Gemini 模式需要 google-genai，请安装 requirements-api.txt。"
        ) from error
    client = genai.Client(api_key=settings.api_key)
    response = client.models.generate_content(
        model=settings.image_gen_model_name,
        contents=[types.Part.from_text(text=prompt)],
        config=types.GenerateContentConfig(
            system_instruction="You are an expert scientific diagram illustrator.",
            temperature=1.0,
            candidate_count=1,
            max_output_tokens=50000,
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            ),
        ),
    )
    for part in response.candidates[0].content.parts:
        inline_data = getattr(part, "inline_data", None)
        if inline_data and inline_data.data:
            data = inline_data.data
            return data if isinstance(data, bytes) else base64.b64decode(data)
    raise RuntimeError("Gemini 响应中没有图片")


def call_image_model(
    settings: ApiSettings,
    prompt: str,
    aspect_ratio: str,
    image_size: str,
) -> bytes:
    """
    根据配置路由图片生成请求。
    Args:
        input: settings、绘图提示、长宽比和图片尺寸。

    Returns:
        Output：生成图片的二进制数据。
    """
    if settings.provider == "openrouter":
        return _openrouter_image(settings, prompt, aspect_ratio, image_size)
    return _gemini_image(settings, prompt, aspect_ratio, image_size)


def _save_png(image_data: bytes, output_path: Path) -> None:
    """
    将任意常见图片字节规范化保存为 PNG。
    Args:
        input: 图片二进制和目标路径。

    Returns:
        Output：无。
    """
    try:
        from PIL import Image
    except ImportError as error:
        raise ApiConfigurationError(
            "API 图片模式需要 Pillow，请安装 requirements-api.txt。"
        ) from error
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(image_data)) as image:
        image.convert("RGB").save(output_path, format="PNG")


def _load_guidance(task: str) -> tuple[str, str]:
    """
    读取任务工作流提示和风格指南。
    Args:
        input: diagram 或 plot。

    Returns:
        Output：工作流提示与风格指南文本。
    """
    reference_root = Path(__file__).resolve().parents[1] / "references"
    workflow = (reference_root / f"{task}-workflow.md").read_text(encoding="utf-8")
    style = (reference_root / f"{task}-style.md").read_text(encoding="utf-8")
    return workflow, style


def _reference_prompt(references: list[dict]) -> tuple[str, list[Path]]:
    """
    将检索结果整理为 Planner 示例上下文。
    Args:
        input: 本地检索结果。

    Returns:
        Output：参考文本和对应图片路径。
    """
    blocks = []
    images = []
    for index, item in enumerate(references, start=1):
        blocks.append(
            f"Example {index} ({item['id']}):\n"
            f"Intent: {item['visual_intent']}\n"
            f"Context: {item['content_excerpt']}"
        )
        images.append(Path(item["image_path"]))
    return "\n\n".join(blocks), images


def _extract_json_object(text: str) -> dict:
    """
    从模型响应中提取 JSON 对象。
    Args:
        input: 可能包含 Markdown 围栏的模型文本。

    Returns:
        Output：解析后的字典，无法解析时返回空字典。
    """
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}


def _extract_python(text: str) -> str:
    """
    从模型响应中提取 Python 代码。
    Args:
        input: 原始文本或 Markdown Python 代码块。

    Returns:
        Output：纯 Python 源代码。
    """
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() + "\n" if match else text.strip() + "\n"


def _infer_caption(
    settings: ApiSettings,
    task: str,
    source_text: str,
    caption: str,
    guidance: str,
) -> str:
    """
    在图注缺失时使用文本模型生成绘图意图。
    Args:
        input: API 设置、任务、源文本、现有图注和工作流指南。

    Returns:
        Output：用户图注或自动生成的简洁图注。
    """
    if caption.strip():
        return caption.strip()
    prompt = (
        f"Task: {task}\nSource:\n{source_text}\n\n"
        "Write one concise figure caption that defines the intended visual."
    )
    return call_text_model(settings, guidance, prompt)


def _plan_and_style(
    settings: ApiSettings,
    task: str,
    source_text: str,
    caption: str,
    references: list[dict],
    guidance: str,
    style_guide: str,
) -> str:
    """
    执行 API 模式的 Planner 和 Stylist 阶段。
    Args:
        input: 任务输入、参考样本、工作流指南和风格指南。

    Returns:
        Output：可直接用于渲染的最终详细描述。
    """
    reference_text, images = _reference_prompt(references)
    planner_prompt = (
        f"Reference examples:\n{reference_text}\n\n"
        f"Target source:\n{source_text}\n\nTarget caption:\n{caption}\n\n"
        "Produce a complete detailed visual description. Preserve every critical "
        "semantic relationship and do not add unsupported content."
    )
    planned = call_text_model(settings, guidance, planner_prompt, images)
    stylist_prompt = (
        f"Detailed description:\n{planned}\n\nStyle guide:\n{style_guide}\n\n"
        f"Original source:\n{source_text}\n\nCaption:\n{caption}\n\n"
        "Return only a publication-ready refined description. Preserve semantics."
    )
    return call_text_model(settings, guidance, stylist_prompt)


def _critic_revision(
    settings: ApiSettings,
    guidance: str,
    source_text: str,
    caption: str,
    description: str,
    image_path: Path,
) -> tuple[str, str]:
    """
    让 Critic 检查当前图片并返回建议和修订描述。
    Args:
        input: 原始输入、当前描述和生成图片。

    Returns:
        Output：critic 建议和修订后的描述。
    """
    prompt = (
        f"Source:\n{source_text}\n\nCaption:\n{caption}\n\n"
        f"Current description:\n{description}\n\n"
        "Inspect the image for fidelity, labels, connections, readability, and "
        "aesthetics. Return strict JSON with keys critic_suggestions and "
        "revised_description. Use 'No changes needed.' when it is already correct."
    )
    response = call_text_model(settings, guidance, prompt, [image_path])
    parsed = _extract_json_object(response)
    suggestions = str(parsed.get("critic_suggestions") or "No changes needed.")
    revised = str(parsed.get("revised_description") or description)
    return suggestions, revised


def _run_diagram_candidate(
    settings: ApiSettings,
    run_dir: Path,
    source_text: str,
    caption: str,
    description: str,
    guidance: str,
    aspect_ratio: str,
    image_size: str,
    critic_rounds: int,
) -> tuple[Path, str, list[str]]:
    """
    生成并迭代一个 API Diagram 候选。
    Args:
        input: API 设置、输入描述、尺寸和 Critic 轮数。

    Returns:
        Output：最终图片、最终描述和警告列表。
    """
    output = run_dir / "final.png"
    prompt = (
        f"Render a scientific diagram from this detailed description:\n{description}\n"
        "Do not include a figure title."
    )
    _save_png(call_image_model(settings, prompt, aspect_ratio, image_size), output)
    warnings = []
    current_description = description
    for round_index in range(critic_rounds):
        suggestions, revised = _critic_revision(
            settings,
            guidance,
            source_text,
            caption,
            current_description,
            output,
        )
        if suggestions.strip().rstrip(".") == "No changes needed":
            break
        try:
            next_prompt = (
                "Render a corrected scientific diagram from this revised detailed "
                f"description:\n{revised}\nDo not include a figure title."
            )
            image_data = call_image_model(
                settings, next_prompt, aspect_ratio, image_size
            )
            _save_png(image_data, output)
            current_description = revised
        except Exception as error:
            warnings.append(f"Critic round {round_index + 1} failed: {error}")
            break
    return output, current_description, warnings


def _run_plot_candidate(
    settings: ApiSettings,
    run_dir: Path,
    source_text: str,
    caption: str,
    description: str,
    guidance: str,
    critic_rounds: int,
) -> tuple[Path, str, list[str]]:
    """
    生成并迭代一个 API Plot 候选。
    Args:
        input: API 设置、原始数据、绘图描述和 Critic 轮数。

    Returns:
        Output：最终图片、最终描述和警告列表。
    """
    output = run_dir / "final.png"
    code_output = run_dir / "plot.py"
    prompt = (
        f"Write safe Python Matplotlib code for this plot:\n{description}\n\n"
        f"Exact source data:\n{source_text}\n\n"
        "Use inline data only. Do not read/write files, call show(), or call savefig(). "
        "Return code only."
    )
    code = _extract_python(call_text_model(settings, guidance, prompt))
    render_plot(code, output, code_output)
    warnings = []
    current_description = description
    for round_index in range(critic_rounds):
        suggestions, revised = _critic_revision(
            settings,
            guidance,
            source_text,
            caption,
            current_description,
            output,
        )
        if suggestions.strip().rstrip(".") == "No changes needed":
            break
        code_prompt = (
            f"Write corrected safe Matplotlib code for:\n{revised}\n\n"
            f"Exact source data:\n{source_text}\n\n"
            "Use inline data only. Do not read/write files, call show(), or call savefig(). "
            "Return code only."
        )
        try:
            next_code = _extract_python(
                call_text_model(settings, guidance, code_prompt)
            )
            render_plot(next_code, output, code_output)
            code, current_description = next_code, revised
        except (PlotSecurityError, RuntimeError) as error:
            warnings.append(f"Critic round {round_index + 1} failed: {error}")
            break
    return output, current_description, warnings


def run_pipeline(args: argparse.Namespace) -> list[Path]:
    """
    执行显式确认后的最小 PaperBanana API 管线。
    Args:
        input: 已解析的命令行参数。

    Returns:
        Output：生成的最终图片路径列表。
    """
    require_api_confirmation(args.confirm_api)
    settings = load_api_settings(args.model_config or None)
    dataset_root = resolve_dataset_root(args.dataset_root or None)
    source_text = Path(args.source_file).read_text(encoding="utf-8")
    guidance, style_guide = _load_guidance(args.task)
    caption = _infer_caption(
        settings, args.task, source_text, args.caption, guidance
    )
    query = f"{caption}\n{source_text[:4000]}"
    references = retrieve(dataset_root, args.task, query, limit=5)
    if not references:
        raise RuntimeError("ref.json 中没有可用且图片存在的参考记录")
    description = _plan_and_style(
        settings,
        args.task,
        source_text,
        caption,
        references,
        guidance,
        style_guide,
    )
    candidates = max(1, min(int(args.candidates), 3))
    critic_rounds = max(0, min(int(args.critic_rounds), 3))
    root_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else create_run_directory()
    )
    root_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index in range(candidates):
        run_dir = root_dir if candidates == 1 else root_dir / f"candidate-{index + 1:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        if args.task == "diagram":
            output, final_description, warnings = _run_diagram_candidate(
                settings,
                run_dir,
                source_text,
                caption,
                description,
                guidance,
                args.aspect_ratio,
                args.image_size,
                critic_rounds,
            )
            output_files = ["final.png"]
        else:
            output, final_description, warnings = _run_plot_candidate(
                settings,
                run_dir,
                source_text,
                caption,
                description,
                guidance,
                critic_rounds,
            )
            output_files = ["final.png", "plot.py"]
        write_manifest(
            run_dir,
            task=args.task,
            backend="api",
            source_text=source_text,
            caption=caption,
            selected_references=[item["id"] for item in references],
            final_description=final_description,
            parameters={
                "provider": settings.provider,
                "main_model_name": settings.main_model_name,
                "image_gen_model_name": settings.image_gen_model_name,
                "aspect_ratio": args.aspect_ratio,
                "image_size": args.image_size,
                "critic_rounds": critic_rounds,
                "candidate_index": index,
            },
            output_files=output_files,
            warnings=warnings,
        )
        outputs.append(output)
    return outputs


def build_parser() -> argparse.ArgumentParser:
    """
    构建 API 回退命令行解析器。
    Args:
        input: 无。

    Returns:
        Output：ArgumentParser 实例。
    """
    parser = argparse.ArgumentParser(description="Explicit PaperBanana API fallback")
    parser.add_argument("--confirm-api", action="store_true")
    parser.add_argument("--model-config", default="")
    parser.add_argument("--dataset-root", default="")
    parser.add_argument("--task", choices=["diagram", "plot"], required=True)
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--caption", default="")
    parser.add_argument("--aspect-ratio", default="21:9")
    parser.add_argument("--image-size", choices=["1k", "2k", "4k"], default="2k")
    parser.add_argument("--candidates", type=int, default=1)
    parser.add_argument("--critic-rounds", type=int, default=3)
    parser.add_argument("--output-dir", default="")
    return parser


def main() -> int:
    """
    运行显式 API 回退 CLI。
    Args:
        input: 命令行参数。

    Returns:
        Output：进程退出码，成功为 0。
    """
    outputs = run_pipeline(build_parser().parse_args())
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

