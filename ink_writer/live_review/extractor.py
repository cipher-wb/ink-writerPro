"""LLM 切分核心 — 抽取直播稿为结构化小说点评（US-LR-003）。"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_PATH = _REPO_ROOT / "scripts" / "live-review" / "prompts" / "extract_v1.txt"
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "live_review_extracted.schema.json"

_logger = logging.getLogger(__name__)


def _clamp_numeric_fields(novel: dict, novel_idx: int) -> None:
    """LLM 软容错：把数值字段 clamp 到 schema 允许范围（in-place）。

    只处理两个最易混淆的字段：
    - ``title_confidence`` 应在 [0.0, 1.0]；超界（如 LLM 误填分数 45）→ clamp + warn
    - ``score`` 应在 [0, 100]；超界 → clamp + warn

    Schema 验证在本函数后进行；clamp 后仍超界（如类型错误 'abc'）会被 schema fail-loud。
    """
    tc = novel.get("title_confidence")
    if isinstance(tc, (int, float)) and (tc > 1.0 or tc < 0.0):
        clamped = max(0.0, min(1.0, float(tc)))
        _logger.warning(
            "novel #%d title_confidence=%r out of [0,1] range, clamped to %f",
            novel_idx, tc, clamped,
        )
        novel["title_confidence"] = clamped

    s = novel.get("score")
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        if s > 100 or s < 0:
            clamped_s = max(0, min(100, int(s)))
            _logger.warning(
                "novel #%d score=%r out of [0,100] range, clamped to %d",
                novel_idx, s, clamped_s,
            )
            novel["score"] = clamped_s


class ExtractionError(Exception):
    """LLM 输出不合法 / 解析失败 / schema 校验失败。"""


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _build_record(
    bvid: str,
    source_path: str,
    source_line_total: int,
    model: str,
    extractor_version: str,
    novel: dict,
) -> dict:
    """合并 LLM 返回的 novel 对象与调用方上下文为完整 jsonl 记录。"""
    return {
        "schema_version": "1.0",
        "bvid": bvid,
        "source_path": source_path,
        "source_line_total": source_line_total,
        "extracted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "extractor_version": extractor_version,
        **novel,
    }


def extract_from_text(
    raw_text: str,
    bvid: str,
    source_path: str,
    *,
    model: str = "claude-sonnet-4-6",
    extractor_version: str = "1.0.0",
    mock_response: list[dict] | None = None,
    llm_call: Callable[[str, str, str], str] | None = None,
) -> list[dict]:
    """从直播稿文本抽取结构化小说点评列表。

    优先级：``mock_response`` > ``llm_call`` > 真实 anthropic SDK。

    Raises:
        ExtractionError: LLM 输出非 JSON / 非 Array / 单条 record 校验失败。
    """
    source_line_total = raw_text.count("\n") + 1
    record_model = model  # 实际写入 jsonl 的 model 字段；真实 SDK 路径会覆盖为 effective_model

    if mock_response is not None:
        novels = mock_response
    elif llm_call is not None:
        prompt = _load_prompt()
        try:
            output = llm_call(prompt, raw_text, model)
        except Exception as exc:
            raise ExtractionError(f"LLM call failed: {exc}") from exc
        try:
            novels = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"LLM output is not valid JSON: {exc}") from exc
    else:
        from ink_writer.live_review._llm_provider import make_client

        prompt = _load_prompt()
        try:
            client, effective_model = make_client(default_model=model)
        except RuntimeError as exc:
            raise ExtractionError(str(exc)) from exc
        record_model = effective_model
        resp = client.messages.create(
            model=effective_model,
            max_tokens=64000,
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}\n\n=== 直播稿全文 ===\n{raw_text}",
                }
            ],
        )
        text = resp.content[0].text  # type: ignore[attr-defined]
        try:
            novels = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"LLM output is not valid JSON: {exc}\nText preview: {text[:200]}"
            ) from exc

    if not isinstance(novels, list):
        raise ExtractionError(
            f"Expected JSON array, got {type(novels).__name__}"
        )

    schema = _load_schema()
    validator = Draft202012Validator(schema)
    records: list[dict] = []
    for i, novel in enumerate(novels):
        if not isinstance(novel, dict):
            raise ExtractionError(
                f"novel #{i} is not an object (got {type(novel).__name__})"
            )
        _clamp_numeric_fields(novel, i)
        record = _build_record(
            bvid, source_path, source_line_total, record_model, extractor_version, novel
        )
        errors = list(validator.iter_errors(record))
        if errors:
            raise ExtractionError(
                f"novel #{i} (title={novel.get('title_guess', '?')!r}) "
                f"failed schema: {[e.message for e in errors[:3]]}"
            )
        records.append(record)
    return records


__all__ = ["ExtractionError", "extract_from_text"]
