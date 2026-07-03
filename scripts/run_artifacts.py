"""Create PaperBanana run directories and privacy-safe manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SENSITIVE_PARAMETER_FRAGMENTS = {
    "api",
    "credential",
    "key",
    "password",
    "secret",
    "token",
}


def create_run_directory(
    base_dir: str | Path = "paperbanana_outputs",
    timestamp: str | None = None,
) -> Path:
    """
    创建不覆盖已有结果的运行目录。
    Args:
        input: base_dir 为输出根目录，timestamp 为可选时间戳。

    Returns:
        Output：新建运行目录的绝对路径。
    """
    base = Path(base_dir).expanduser().resolve()
    label = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base / label
    suffix = 1
    while candidate.exists():
        candidate = base / f"{label}-{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _sanitize_parameters(value: object) -> object:
    """
    递归移除参数中的密钥和凭据字段。
    Args:
        input: 任意 JSON 兼容参数值。

    Returns:
        Output：不含敏感键的参数值。
    """
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SENSITIVE_PARAMETER_FRAGMENTS):
                continue
            sanitized[str(key)] = _sanitize_parameters(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_parameters(item) for item in value]
    return value


def write_manifest(
    output_dir: str | Path,
    *,
    task: str,
    backend: str,
    source_text: str,
    caption: str,
    selected_references: list[str],
    final_description: str,
    parameters: dict,
    output_files: list[str],
    warnings: list[str],
) -> Path:
    """
    写入不包含原始正文和密钥的运行清单。
    Args:
        input: 输出目录、任务参数、输入正文、参考 ID 和产物列表。

    Returns:
        Output：run.json 的绝对路径。
    """
    if task not in {"diagram", "plot"}:
        raise ValueError("task 必须是 diagram 或 plot")
    if backend not in {"native", "api"}:
        raise ValueError("backend 必须是 native 或 api")
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    unique_references = list(dict.fromkeys(str(item) for item in selected_references))
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "backend": backend,
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "caption": caption,
        "selected_references": unique_references,
        "final_description": final_description,
        "parameters": _sanitize_parameters(parameters),
        "output_files": [str(item) for item in output_files],
        "warnings": [str(item) for item in warnings],
    }
    manifest_path = directory / "run.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _read_json_list(path_value: str) -> list:
    """
    从可选 JSON 文件读取列表。
    Args:
        input: JSON 文件路径，空值代表空列表。

    Returns:
        Output：解析后的列表。
    """
    if not path_value:
        return []
    value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"JSON 文件必须包含数组：{path_value}")
    return value


def _read_json_dict(path_value: str) -> dict:
    """
    从可选 JSON 文件读取对象。
    Args:
        input: JSON 文件路径，空值代表空对象。

    Returns:
        Output：解析后的字典。
    """
    if not path_value:
        return {}
    value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 文件必须包含对象：{path_value}")
    return value


def main() -> int:
    """
    创建运行目录或写入运行清单。
    Args:
        input: prepare 或 manifest 子命令参数。

    Returns:
        Output：进程退出码，成功为 0。
    """
    parser = argparse.ArgumentParser(description="Manage PaperBanana run artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--base-dir", default="paperbanana_outputs")

    manifest_parser = subparsers.add_parser("manifest")
    manifest_parser.add_argument("--output-dir", required=True)
    manifest_parser.add_argument("--task", choices=["diagram", "plot"], required=True)
    manifest_parser.add_argument("--backend", choices=["native", "api"], required=True)
    manifest_parser.add_argument("--source-file", required=True)
    manifest_parser.add_argument("--caption", default="")
    manifest_parser.add_argument("--description-file", required=True)
    manifest_parser.add_argument("--references-file", default="")
    manifest_parser.add_argument("--parameters-file", default="")
    manifest_parser.add_argument("--output-file", action="append", default=[])
    manifest_parser.add_argument("--warning", action="append", default=[])
    args = parser.parse_args()

    if args.command == "prepare":
        print(create_run_directory(args.base_dir))
        return 0

    manifest = write_manifest(
        args.output_dir,
        task=args.task,
        backend=args.backend,
        source_text=Path(args.source_file).read_text(encoding="utf-8"),
        caption=args.caption,
        selected_references=_read_json_list(args.references_file),
        final_description=Path(args.description_file).read_text(encoding="utf-8"),
        parameters=_read_json_dict(args.parameters_file),
        output_files=args.output_file,
        warnings=args.warning,
    )
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
