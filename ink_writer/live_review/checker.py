"""US-LR-012: live-review-checker — 章节评分 + violations + cases_hit。

依赖现有 live-review FAISS 索引（由 build_vector_index.py 构建）+ LLM 输出评分。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ink_writer.live_review.config import LiveReviewConfig, load_config
from ink_writer.live_review.genre_retrieval import (
    DEFAULT_INDEX_DIR,
    retrieve_similar_cases,
)

DEFAULT_TOP_K = 5
_RETRIEVE_QUERY_HEAD = 500


def _disabled_response() -> dict:
    return {
        "score": 1.0,
        "dimensions": {},
        "violations": [],
        "cases_hit": [],
        "disabled": True,
    }


def _build_query(chapter_text: str, genre_tags: list[str]) -> str:
    """合并 genre_tags + 章节正文头部用于 FAISS 检索。"""
    head = (chapter_text or "")[:_RETRIEVE_QUERY_HEAD]
    return " ".join(filter(None, [" ".join(genre_tags or []), head]))


def _validate_result_shape(result: dict) -> None:
    """fail-loud：result 必须包含 score/dimensions/violations/cases_hit 四字段。"""
    required = ("score", "dimensions", "violations", "cases_hit")
    missing = [k for k in required if k not in result]
    if missing:
        raise ValueError(f"checker response missing fields: {missing}")
    if not isinstance(result["score"], (int, float)):
        raise ValueError(f"score must be number, got {type(result['score']).__name__}")
    if not isinstance(result["dimensions"], dict):
        raise ValueError("dimensions must be a dict")
    if not isinstance(result["violations"], list):
        raise ValueError("violations must be a list")
    if not isinstance(result["cases_hit"], list):
        raise ValueError("cases_hit must be a list")


def _normalize_result(result: dict) -> dict:
    """剥除 disabled 标志，统一 score 为 float。"""
    return {
        "score": float(result["score"]),
        "dimensions": dict(result["dimensions"]),
        "violations": list(result["violations"]),
        "cases_hit": list(result["cases_hit"]),
        "disabled": False,
    }


def run_live_review_checker(
    chapter_text: str,
    chapter_no: int,
    genre_tags: list[str],
    *,
    mock_response: dict | None = None,
    llm_call: Callable[[str], str] | None = None,
    config_path: Path | None = None,
    index_dir: Path | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """对章节运行 live-review checker 并返回 {score, dimensions, violations, cases_hit}。

    优先级：``mock_response`` > ``llm_call`` > 真实 anthropic SDK。
    主分支：master switch（``enabled`` / ``inject_into.review``）短路时返回早退响应。

    Args:
        chapter_text: 章节正文。
        chapter_no: 章节号。
        genre_tags: 题材标签列表（如 ['都市', '重生']）。
        mock_response: 测试用 — 直接返回的响应字典；提供则跳过检索 + LLM。
        llm_call: 测试用 — 注入的 LLM callable，签名为 (prompt) -> str。
        config_path: live-review.yaml 路径；None 走默认。
        index_dir: vector_index 目录；None 走默认。
        top_k: 检索 Top-K 案例数。

    Returns:
        dict：``score`` (0-1) / ``dimensions`` (dict[str, float]) / ``violations``
        (list[{case_id, dimension, evidence_quote, severity}]) / ``cases_hit``
        (list[str case_id]) / ``disabled`` (bool)。
    """
    cfg: LiveReviewConfig = load_config(config_path)
    if not cfg.enabled or not cfg.inject_into.review:
        return _disabled_response()

    if mock_response is not None:
        _validate_result_shape(mock_response)
        return _normalize_result(mock_response)

    idx_dir = Path(index_dir) if index_dir is not None else DEFAULT_INDEX_DIR
    query = _build_query(chapter_text, genre_tags)
    similar_cases = retrieve_similar_cases(query, top_k=top_k, index_dir=idx_dir)
    cases_hit_default = [c["case_id"] for c in similar_cases]

    prompt = _build_llm_prompt(chapter_text, chapter_no, genre_tags, similar_cases)

    if llm_call is not None:
        output = llm_call(prompt)
    else:
        output = _call_anthropic(prompt, model=cfg.model)

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

    if "cases_hit" not in parsed:
        parsed["cases_hit"] = cases_hit_default
    _validate_result_shape(parsed)
    return _normalize_result(parsed)


def _build_llm_prompt(
    chapter_text: str,
    chapter_no: int,
    genre_tags: list[str],
    similar_cases: list[dict],
) -> str:
    """构造 LLM prompt（真实路径使用；mock/test 路径不调用此函数）。"""
    cases_block = "\n".join(
        f"- {c['case_id']} ({c.get('verdict', '?')} / "
        f"{c.get('score', '?')}分): {c.get('overall_comment', '')[:200]}"
        for c in similar_cases
    )
    return (
        "你是 174 份起点编辑星河直播稿训练出来的网文审稿助手。基于检索到的相似病例对章节做命中评分。\n\n"
        f"## 章节号: {chapter_no}\n"
        f"## 题材: {', '.join(genre_tags)}\n"
        "## 相似病例 (Top-K):\n"
        f"{cases_block}\n\n"
        "## 章节正文:\n"
        f"{chapter_text}\n\n"
        "## 输出要求 (严格 JSON，无 markdown):\n"
        "{\n"
        '  "score": <float 0-1，综合 = (1 - violation_density) × verdict_pass_rate_of_top5>,\n'
        '  "dimensions": {<dimension>: <float 0-1>, ...},\n'
        '  "violations": [{"case_id": "...", "dimension": "...", "evidence_quote": "...", "severity": "negative|neutral|positive"}, ...],\n'
        '  "cases_hit": [<相关案例 case_id>, ...]\n'
        "}\n"
    )


def _call_anthropic(prompt: str, *, model: str) -> str:
    """真实 LLM 调用 — 仅在 mock_response/llm_call 都不传时走此路径。

    走统一 provider：env-driven 自动选 GLM / anthropic（保留函数名兼容历史调用点）。
    """
    from ink_writer.live_review._llm_provider import make_client

    client, effective_model = make_client(default_model=model)
    msg = client.messages.create(
        model=effective_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    parts: list[str] = []
    for block in msg.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


__all__ = ["DEFAULT_TOP_K", "run_live_review_checker"]
