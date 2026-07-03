"""Configure the local PaperBananaBench path for paperbanana-codex."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from paperbanana_common import (
    default_model_config_path,
    save_user_config,
    validate_dataset,
)


def ensure_model_config_template() -> Path:
    """
    在用户目录创建空的 API 配置模板。
    Args:
        input: 无。

    Returns:
        Output：用户 API 配置文件路径。
    """
    destination = default_model_config_path()
    if destination.exists():
        return destination
    source = Path(__file__).resolve().parents[1] / "configs" / "model_config.template.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def main() -> int:
    """
    校验并保存数据集路径。
    Args:
        input: 命令行中的 dataset-root、task 和 config 参数。

    Returns:
        Output：进程退出码，成功为 0。
    """
    parser = argparse.ArgumentParser(description="Configure PaperBananaBench path")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument(
        "--task",
        choices=["all", "diagram", "plot"],
        default="all",
        help="Validate all data or only one task",
    )
    parser.add_argument("--config", default="")
    args = parser.parse_args()

    tasks = ("diagram", "plot") if args.task == "all" else (args.task,)
    report = validate_dataset(args.dataset_root, tasks)
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    if report["errors"]:
        for error in report["errors"]:
            print(f"ERROR: {error}")
        return 1

    config_path = save_user_config(args.dataset_root, args.config or None)
    model_config = ensure_model_config_template()
    print(f"Dataset configured: {report['dataset_root']}")
    print(f"Config saved: {config_path}")
    print(f"Optional API config: {model_config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

