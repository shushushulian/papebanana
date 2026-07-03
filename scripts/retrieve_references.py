"""Retrieve PaperBananaBench references with a dependency-free BM25 scorer."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from paperbanana_common import (
    _safe_image_path,
    load_reference_records,
    resolve_dataset_root,
)


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(value: object) -> list[str]:
    """
    将英文单词、数字和中文字符转换为检索词元。
    Args:
        input: 任意可转为字符串的字段值。

    Returns:
        Output：小写词元列表。
    """
    return [token.lower() for token in TOKEN_PATTERN.findall(str(value))]


def _field_scores(documents: list[list[str]], query_tokens: list[str]) -> list[float]:
    """
    计算一个字段语料的 BM25 分数。
    Args:
        input: documents 为词元文档列表，query_tokens 为查询词元。

    Returns:
        Output：与文档顺序一致的分数列表。
    """
    if not documents or not query_tokens:
        return [0.0] * len(documents)
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document))
    average_length = sum(len(document) for document in documents) / len(documents)
    average_length = max(average_length, 1.0)
    query_frequency = Counter(query_tokens)
    scores: list[float] = []
    for document in documents:
        frequencies = Counter(document)
        length = len(document)
        score = 0.0
        for token, query_count in query_frequency.items():
            frequency = frequencies.get(token, 0)
            if not frequency:
                continue
            occurrences = document_frequency[token]
            inverse_frequency = math.log(
                1 + (len(documents) - occurrences + 0.5) / (occurrences + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * length / average_length
            )
            score += inverse_frequency * frequency * 2.5 / denominator * query_count
        scores.append(score)
    return scores


def retrieve(
    dataset_root: str | Path,
    task: str,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """
    从完整 ref.json 中召回存在图片的相关参考记录。
    Args:
        input: dataset_root 为数据集，task 为任务，query 为查询，limit 为数量。

    Returns:
        Output：按分数降序排列的参考记录摘要。
    """
    task_root, records = load_reference_records(dataset_root, task)
    candidates: list[tuple[dict, Path]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        image_path = _safe_image_path(task_root, item.get("path_to_gt_image"))
        if image_path is None or not image_path.is_file():
            continue
        candidates.append((item, image_path))

    query_tokens = tokenize(query)
    intent_documents = [tokenize(item.get("visual_intent", "")) for item, _ in candidates]
    content_documents = [tokenize(item.get("content", "")) for item, _ in candidates]
    category_documents = [tokenize(item.get("category", "")) for item, _ in candidates]
    intent_scores = _field_scores(intent_documents, query_tokens)
    content_scores = _field_scores(content_documents, query_tokens)
    category_scores = _field_scores(category_documents, query_tokens)

    ranked: list[dict] = []
    for index, (item, image_path) in enumerate(candidates):
        score = (
            4.0 * intent_scores[index]
            + content_scores[index]
            + 1.5 * category_scores[index]
        )
        content = item.get("content", "")
        if isinstance(content, (dict, list)):
            content_text = json.dumps(content, ensure_ascii=False)
        else:
            content_text = str(content)
        ranked.append(
            {
                "id": str(item.get("id", "")),
                "score": round(score, 6),
                "visual_intent": str(item.get("visual_intent", "")),
                "content_excerpt": content_text[:2000],
                "category": item.get("category"),
                "image_path": image_path,
                "path_to_gt_image": str(item.get("path_to_gt_image", "")),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["id"]))
    return ranked[: max(1, min(limit, 100))]


def _json_ready(records: list[dict]) -> list[dict]:
    """
    将检索结果转换为可序列化结构。
    Args:
        input: 含 Path 对象的检索结果。

    Returns:
        Output：仅含 JSON 基础类型的记录列表。
    """
    return [
        {
            **item,
            "image_path": str(item["image_path"]),
        }
        for item in records
    ]


def main() -> int:
    """
    执行命令行参考检索。
    Args:
        input: 数据集、任务、查询、数量和可选输出文件。

    Returns:
        Output：成功时返回 0。
    """
    parser = argparse.ArgumentParser(description="Retrieve PaperBanana references")
    parser.add_argument("--dataset-root", default="")
    parser.add_argument("--task", choices=["diagram", "plot"], required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = resolve_dataset_root(args.dataset_root or None)
    payload = _json_ready(retrieve(root, args.task, args.query, args.limit))
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
