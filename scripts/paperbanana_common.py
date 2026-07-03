"""Shared configuration and PaperBananaBench validation helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


REQUIRED_REFERENCE_FIELDS = {
    "id",
    "content",
    "visual_intent",
    "path_to_gt_image",
}


def get_codex_home() -> Path:
    """
    获取 Codex 用户目录。
    Args:
        input: 无，优先读取 CODEX_HOME 环境变量。

    Returns:
        Output：Codex 用户目录的绝对路径。
    """
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".codex"


def default_user_config_path() -> Path:
    """
    获取 PaperBanana 用户配置文件路径。
    Args:
        input: 无。

    Returns:
        Output：config.json 的绝对路径。
    """
    return get_codex_home() / "paperbanana" / "config.json"


def default_model_config_path() -> Path:
    """
    获取外部 API 模型配置文件路径。
    Args:
        input: 无。

    Returns:
        Output：model_config.yaml 的绝对路径。
    """
    override = os.environ.get("PAPERBANANA_MODEL_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return get_codex_home() / "paperbanana" / "configs" / "model_config.yaml"


def normalize_dataset_root(path_value: str | Path) -> Path:
    """
    将数据集路径规范化为 PaperBananaBench 根目录。
    Args:
        input: PaperBananaBench 目录或包含它的父目录。

    Returns:
        Output：规范化后的绝对路径。
    """
    candidate = Path(path_value).expanduser().resolve()
    nested = candidate / "PaperBananaBench"
    if candidate.name.lower() != "paperbananabench" and nested.is_dir():
        return nested.resolve()
    return candidate


def load_user_config(config_path: str | Path | None = None) -> dict:
    """
    读取 PaperBanana 用户配置。
    Args:
        input: 可选配置文件路径。

    Returns:
        Output：配置字典，文件不存在时返回空字典。
    """
    path = Path(config_path).expanduser() if config_path else default_user_config_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 JSON 对象：{path}")
    return data


def resolve_dataset_root(
    explicit_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> Path:
    """
    按优先级解析 PaperBananaBench 数据集路径。
    Args:
        input: explicit_path 为当次路径，config_path 为可选配置路径。

    Returns:
        Output：解析后的数据集绝对路径。
    """
    if explicit_path:
        return normalize_dataset_root(explicit_path)
    environment_path = os.environ.get("PAPERBANANA_BENCH_ROOT")
    if environment_path:
        return normalize_dataset_root(environment_path)
    configured = load_user_config(config_path).get("dataset_root")
    if configured:
        return normalize_dataset_root(configured)
    raise FileNotFoundError(
        "未配置 PaperBananaBench。请提供数据集路径、设置 "
        "PAPERBANANA_BENCH_ROOT，或运行 scripts/configure.py。"
    )


def save_user_config(dataset_root: str | Path, config_path: str | Path | None = None) -> Path:
    """
    原子保存默认数据集路径。
    Args:
        input: dataset_root 为数据集目录，config_path 为可选配置路径。

    Returns:
        Output：写入的配置文件绝对路径。
    """
    path = (
        Path(config_path).expanduser().resolve()
        if config_path
        else default_user_config_path()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"dataset_root": str(normalize_dataset_root(dataset_root))}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def load_reference_records(dataset_root: str | Path, task: str) -> tuple[Path, list[dict]]:
    """
    读取指定任务的参考记录。
    Args:
        input: dataset_root 为数据集目录，task 为 diagram 或 plot。

    Returns:
        Output：任务目录和参考记录列表。
    """
    if task not in {"diagram", "plot"}:
        raise ValueError("task 必须是 diagram 或 plot")
    task_root = normalize_dataset_root(dataset_root) / task
    ref_path = task_root / "ref.json"
    if not ref_path.is_file():
        raise FileNotFoundError(f"缺少参考文件：{ref_path}")
    with ref_path.open("r", encoding="utf-8-sig") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError(f"ref.json 必须是 JSON 数组：{ref_path}")
    return task_root, records


def _safe_image_path(task_root: Path, relative_path: object) -> Path | None:
    """
    安全解析参考图片路径。
    Args:
        input: task_root 为任务目录，relative_path 为 JSON 中的相对路径。

    Returns:
        Output：目录内的绝对路径，非法路径返回 None。
    """
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    image_path = (task_root / relative_path).resolve()
    try:
        image_path.relative_to(task_root.resolve())
    except ValueError:
        return None
    return image_path


def validate_dataset(
    dataset_root: str | Path,
    tasks: Iterable[str] = ("diagram", "plot"),
) -> dict:
    """
    校验 PaperBananaBench 参考数据结构和图片路径。
    Args:
        input: dataset_root 为数据集目录，tasks 为待校验任务集合。

    Returns:
        Output：包含 errors、warnings 和 counts 的校验报告。
    """
    root = normalize_dataset_root(dataset_root)
    report = {"dataset_root": str(root), "errors": [], "warnings": [], "counts": {}}
    if not root.is_dir():
        report["errors"].append(f"数据集目录不存在：{root}")
        return report

    for task in tasks:
        if task not in {"diagram", "plot"}:
            report["errors"].append(f"未知任务类型：{task}")
            continue
        try:
            task_root, records = load_reference_records(root, task)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
            report["errors"].append(str(error))
            continue

        seen_ids: set[str] = set()
        valid_count = 0
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                report["errors"].append(f"{task}/ref.json 第 {index} 条不是对象")
                continue
            missing = sorted(REQUIRED_REFERENCE_FIELDS - item.keys())
            if missing:
                report["errors"].append(
                    f"{task}/ref.json 第 {index} 条缺少字段：{', '.join(missing)}"
                )
                continue
            item_id = str(item["id"])
            if item_id in seen_ids:
                report["errors"].append(f"{task}/ref.json 存在重复 ID：{item_id}")
            seen_ids.add(item_id)
            image_path = _safe_image_path(task_root, item["path_to_gt_image"])
            if image_path is None:
                report["errors"].append(f"{task}/{item_id} 的图片路径不安全")
            elif not image_path.is_file():
                report["warnings"].append(f"{task}/{item_id} 缺少图片：{image_path}")
            else:
                valid_count += 1
        report["counts"][task] = {
            "records": len(records),
            "valid_images": valid_count,
        }
    return report

