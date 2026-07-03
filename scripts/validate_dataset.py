"""Validate a configured PaperBananaBench reference dataset."""

from __future__ import annotations

import argparse
import json

from paperbanana_common import resolve_dataset_root, validate_dataset


def main() -> int:
    """
    输出数据集校验报告。
    Args:
        input: 命令行中的可选数据集路径和任务类型。

    Returns:
        Output：无错误时返回 0，否则返回 1。
    """
    parser = argparse.ArgumentParser(description="Validate PaperBananaBench")
    parser.add_argument("--dataset-root", default="")
    parser.add_argument(
        "--task", choices=["all", "diagram", "plot"], default="all"
    )
    args = parser.parse_args()
    root = resolve_dataset_root(args.dataset_root or None)
    tasks = ("diagram", "plot") if args.task == "all" else (args.task,)
    report = validate_dataset(root, tasks)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

