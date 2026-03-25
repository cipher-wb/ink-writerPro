#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_chapter_context.py - extract chapter writing context

Features:
- chapter outline snippet
- previous chapter summaries (prefers .ink/summaries)
- compact state summary
- ContextManager contract sections (reader_signal / genre_profile / writing_guidance)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from chapter_outline_loader import load_chapter_outline

from runtime_compat import enable_windows_utf8_stdio

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file


def _ensure_scripts_path():
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def find_project_root(start_path: Path | None = None) -> Path:
    """解析真实书项目根（包含 `.ink/state.json` 的目录）。"""
    from project_locator import resolve_project_root

    if start_path is None:
        return resolve_project_root()
    return resolve_project_root(str(start_path))


def extract_chapter_outline(project_root: Path, chapter_num: int) -> str:
    """Extract chapter outline segment from volume outline file."""
    return load_chapter_outline(project_root, chapter_num, max_chars=1500)


def _load_summary_file(project_root: Path, chapter_num: int) -> str:
    """Load summary section from `.ink/summaries/chNNNN.md`."""
    summary_path = project_root / ".ink" / "summaries" / f"ch{chapter_num:04d}.md"
    if not summary_path.exists():
        return ""

    text = summary_path.read_text(encoding="utf-8")
    summary_match = re.search(r"##\s*剧情摘要\s*\r?\n(.+?)(?=\r?\n##|$)", text, re.DOTALL)
    if summary_match:
        return summary_match.group(1).strip()
    return ""


def extract_chapter_summary(project_root: Path, chapter_num: int) -> str:
    """Extract chapter summary, fallback to chapter body head."""
    summary = _load_summary_file(project_root, chapter_num)
    if summary:
        return summary

    chapter_file = find_chapter_file(project_root, chapter_num)
    if not chapter_file or not chapter_file.exists():
        return f"⚠️ 第{chapter_num}章文件不存在"

    content = chapter_file.read_text(encoding="utf-8")

    summary_match = re.search(r"##\s*本章摘要\s*\r?\n(.+?)(?=\r?\n##|$)", content, re.DOTALL)
    if summary_match:
        return summary_match.group(1).strip()

    stats_match = re.search(r"##\s*本章统计\s*\r?\n(.+?)(?=\r?\n##|$)", content, re.DOTALL)
    if stats_match:
        return f"[无摘要，仅统计]\n{stats_match.group(1).strip()}"

    lines = content.split("\n")
    text_lines = [line for line in lines if not line.startswith("#") and line.strip()]
    text = "\n".join(text_lines)[:500]
    return f"[自动截取前500字]\n{text}..."


def extract_state_summary(project_root: Path) -> str:
    """Extract key fields from `.ink/state.json`."""
    state_file = project_root / ".ink" / "state.json"
    if not state_file.exists():
        return "⚠️ state.json 不存在"

    state = json.loads(state_file.read_text(encoding="utf-8"))
    summary_parts: List[str] = []

    if "progress" in state:
        progress = state["progress"]
        summary_parts.append(
            f"**进度**: 第{progress.get('current_chapter', '?')}章 / {progress.get('total_words', '?')}字"
        )

    if "protagonist_state" in state:
        ps = state["protagonist_state"]
        power = ps.get("power", {})
        summary_parts.append(f"**主角实力**: {power.get('realm', '?')} {power.get('layer', '?')}层")
        summary_parts.append(f"**当前位置**: {ps.get('location', '?')}")
        golden_finger = ps.get("golden_finger", {})
        summary_parts.append(
            f"**金手指**: {golden_finger.get('name', '?')} Lv.{golden_finger.get('level', '?')}"
        )

    if "strand_tracker" in state:
        tracker = state["strand_tracker"]
        history = tracker.get("history", [])[-5:]
        if history:
            items: List[str] = []
            for row in history:
                if not isinstance(row, dict):
                    continue
                chapter = row.get("chapter", "?")
                strand = row.get("strand") or row.get("dominant") or "unknown"
                items.append(f"Ch{chapter}:{strand}")
            if items:
                summary_parts.append(f"**近5章Strand**: {', '.join(items)}")

    plot_threads = state.get("plot_threads", {}) if isinstance(state.get("plot_threads"), dict) else {}
    foreshadowing = plot_threads.get("foreshadowing", [])
    if isinstance(foreshadowing, list) and foreshadowing:
        active = [row for row in foreshadowing if row.get("status") in {"active", "未回收"}]
        urgent = [row for row in active if row.get("urgency", 0) > 50]
        if urgent:
            urgent_list = [
                f"{row.get('content', '?')[:30]}... (紧急度:{row.get('urgency')})"
                for row in urgent[:3]
            ]
            summary_parts.append(f"**紧急伏笔**: {'; '.join(urgent_list)}")

    return "\n".join(summary_parts)


def _normalize_outline_text(outline: str) -> str:
    text = str(outline or "")
    if not text or text.startswith("⚠️"):
        return ""
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize_query_text(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return []

    tokens: List[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]+", normalized):
        tokens.append(chunk)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", chunk):
            for idx in range(0, max(0, len(chunk) - 1)):
                tokens.append(chunk[idx : idx + 2])
    return tokens


def _build_rag_query(
    outline: str,
    chapter_num: int,
    memory_context: Dict[str, Any],
    min_chars: int,
    max_chars: int,
) -> str:
    plain = _normalize_outline_text(outline)
    previous_card = memory_context.get("previous_chapter_memory_card", {}) if isinstance(memory_context, dict) else {}
    active_threads = memory_context.get("active_plot_threads", []) if isinstance(memory_context, dict) else []

    fragments: List[str] = []
    if plain:
        fragments.append(f"章纲:{plain}")

    if isinstance(previous_card, dict):
        prev_summary = str(previous_card.get("summary", "") or "").strip()
        bridge = str(previous_card.get("next_chapter_bridge", "") or "").strip()
        prev_entities = previous_card.get("involved_entities", []) or []
        if prev_summary:
            fragments.append(f"上章交接:{prev_summary}")
        if bridge:
            fragments.append(f"必须承接:{bridge}")
        if prev_entities:
            fragments.append("相关实体:" + " ".join(str(item) for item in prev_entities[:6]))

    thread_labels: List[str] = []
    for row in active_threads[:4]:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or row.get("title") or "").strip()
        if content:
            thread_labels.append(content[:30])
    if thread_labels:
        fragments.append("活跃线程:" + "；".join(thread_labels))

    joined = " ".join(fragment for fragment in fragments if fragment).strip()
    if len(joined) < min_chars:
        return ""

    clean_max = max(40, int(max_chars))
    return f"第{chapter_num}章 连续性检索：{joined[:clean_max]}"


def _score_lexical_match(query: str, text: str) -> float:
    query_tokens = set(_tokenize_query_text(query))
    text_tokens = set(_tokenize_query_text(text))
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = query_tokens & text_tokens
    if not overlap:
        return 0.0
    return round(len(overlap) / max(1, len(query_tokens)), 6)


def _search_memory_cards_and_summaries(
    project_root: Path,
    chapter_num: int,
    query: str,
    top_k: int,
) -> Dict[str, Any]:
    _ensure_scripts_path()
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import IndexManager

    config = DataModulesConfig.from_project_root(project_root)
    index_manager = IndexManager(config)

    candidates: List[Dict[str, Any]] = []

    for row in index_manager.get_recent_chapter_memory_cards(limit=max(top_k * 4, 10), before_chapter=chapter_num):
        content = " ".join(
            str(part or "")
            for part in [
                row.get("summary"),
                row.get("goal"),
                row.get("conflict"),
                row.get("result"),
                row.get("next_chapter_bridge"),
                "；".join(row.get("unresolved_questions", []) or []),
                "；".join(row.get("key_facts", []) or []),
            ]
        ).strip()
        score = _score_lexical_match(query, content)
        if score <= 0:
            continue
        candidates.append(
            {
                "chapter": int(row.get("chapter") or 0),
                "scene_index": 0,
                "score": score,
                "source": "chapter_memory_card",
                "source_file": "",
                "content": re.sub(r"\s+", " ", content)[:180],
            }
        )

    summaries_dir = project_root / ".ink" / "summaries"
    if summaries_dir.exists():
        for path in sorted(summaries_dir.glob("ch*.md")):
            match = re.search(r"ch(\d+)\.md$", path.name)
            if not match:
                continue
            row_chapter = int(match.group(1))
            if row_chapter >= chapter_num:
                continue
            text = _load_summary_file(project_root, row_chapter)
            score = _score_lexical_match(query, text)
            if score <= 0:
                continue
            candidates.append(
                {
                    "chapter": row_chapter,
                    "scene_index": 0,
                    "score": score,
                    "source": "summary_bm25",
                    "source_file": str(path),
                    "content": re.sub(r"\s+", " ", text)[:180],
                }
            )

    candidates.sort(key=lambda row: (float(row.get("score", 0.0)), int(row.get("chapter", 0))), reverse=True)
    hits = candidates[:top_k]
    return {
        "invoked": True,
        "query": query,
        "mode": "summary_memory_bm25",
        "reason": "ok" if hits else "no_hit",
        "intent": "continuity_memory",
        "needs_graph": False,
        "center_entities": [],
        "hits": hits,
    }


def _search_with_rag(
    project_root: Path,
    chapter_num: int,
    query: str,
    top_k: int,
) -> Dict[str, Any]:
    _ensure_scripts_path()
    from data_modules.config import DataModulesConfig
    from data_modules.rag_adapter import RAGAdapter

    config = DataModulesConfig.from_project_root(project_root)
    adapter = RAGAdapter(config)
    intent_payload = adapter.query_router.route_intent(query)
    center_entities = list(intent_payload.get("entities") or [])

    results = []
    mode = "auto"
    fallback_reason = ""
    has_embed_key = bool(str(getattr(config, "embed_api_key", "") or "").strip())
    if has_embed_key:
        try:
            results = asyncio.run(
                adapter.search(
                    query=query,
                    top_k=top_k,
                    strategy="auto",
                    chapter=chapter_num,
                    center_entities=center_entities,
                )
            )
        except Exception as exc:
            fallback_reason = f"auto_failed:{exc.__class__.__name__}"
            mode = "bm25_fallback"
            results = adapter.bm25_search(query=query, top_k=top_k, chapter=chapter_num)
    else:
        mode = "bm25_fallback"
        fallback_reason = "missing_embed_api_key"
        results = adapter.bm25_search(query=query, top_k=top_k, chapter=chapter_num)

    hits: List[Dict[str, Any]] = []
    for row in results:
        content = re.sub(r"\s+", " ", str(getattr(row, "content", "") or "")).strip()
        hits.append(
            {
                "chunk_id": str(getattr(row, "chunk_id", "") or ""),
                "chapter": int(getattr(row, "chapter", 0) or 0),
                "scene_index": int(getattr(row, "scene_index", 0) or 0),
                "score": round(float(getattr(row, "score", 0.0) or 0.0), 6),
                "source": str(getattr(row, "source", "") or mode),
                "source_file": str(getattr(row, "source_file", "") or ""),
                "content": content[:180],
            }
        )

    return {
        "invoked": True,
        "query": query,
        "mode": mode,
        "reason": fallback_reason or ("ok" if hits else "no_hit"),
        "intent": intent_payload.get("intent"),
        "needs_graph": bool(intent_payload.get("needs_graph")),
        "center_entities": center_entities,
        "hits": hits,
    }


def _load_rag_assist(
    project_root: Path,
    chapter_num: int,
    outline: str,
    memory_context: Dict[str, Any],
) -> Dict[str, Any]:
    _ensure_scripts_path()
    from data_modules.config import DataModulesConfig

    config = DataModulesConfig.from_project_root(project_root)
    enabled = bool(getattr(config, "context_rag_assist_enabled", True))
    top_k = max(1, int(getattr(config, "context_rag_assist_top_k", 4)))
    min_chars = max(20, int(getattr(config, "context_rag_assist_min_outline_chars", 40)))
    max_chars = max(40, int(getattr(config, "context_rag_assist_max_query_chars", 120)))
    base_payload = {"enabled": enabled, "invoked": False, "reason": "", "query": "", "hits": []}

    if not enabled:
        base_payload["reason"] = "disabled_by_config"
        return base_payload

    query = _build_rag_query(
        outline,
        chapter_num=chapter_num,
        memory_context=memory_context,
        min_chars=min_chars,
        max_chars=max_chars,
    )
    if not query:
        base_payload["reason"] = "context_not_actionable"
        return base_payload

    vector_db = config.vector_db
    has_embed_key = bool(str(getattr(config, "embed_api_key", "") or "").strip())

    try:
        if has_embed_key and vector_db.exists() and vector_db.stat().st_size > 0:
            rag_payload = _search_with_rag(project_root=project_root, chapter_num=chapter_num, query=query, top_k=top_k)
            rag_payload["enabled"] = True
            if rag_payload.get("hits"):
                return rag_payload
        local_payload = _search_memory_cards_and_summaries(
            project_root=project_root,
            chapter_num=chapter_num,
            query=query,
            top_k=top_k,
        )
        local_payload["enabled"] = True
        if not has_embed_key:
            local_payload["reason"] = "missing_embed_api_key"
        elif not vector_db.exists() or vector_db.stat().st_size <= 0:
            local_payload["reason"] = "vector_db_missing_or_empty"
        return local_payload
    except Exception as exc:
        try:
            local_payload = _search_memory_cards_and_summaries(
                project_root=project_root,
                chapter_num=chapter_num,
                query=query,
                top_k=top_k,
            )
            local_payload["enabled"] = True
            local_payload["reason"] = f"rag_error:{exc.__class__.__name__}"
            return local_payload
        except Exception:
            base_payload["reason"] = f"rag_error:{exc.__class__.__name__}"
            return base_payload


def _load_contract_context(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    """Build context via ContextManager and return selected sections."""
    _ensure_scripts_path()
    from data_modules.config import DataModulesConfig
    from data_modules.context_manager import ContextManager

    config = DataModulesConfig.from_project_root(project_root)
    manager = ContextManager(config)
    payload = manager.build_context(
        chapter=chapter_num,
        template="plot",
        use_snapshot=True,
        save_snapshot=True,
        max_chars=8000,
    )

    sections = payload.get("sections", {})
    return {
        "context_contract_version": (payload.get("meta") or {}).get("context_contract_version"),
        "context_weight_stage": (payload.get("meta") or {}).get("context_weight_stage"),
        "reader_signal": (sections.get("reader_signal") or {}).get("content", {}),
        "genre_profile": (sections.get("genre_profile") or {}).get("content", {}),
        "writing_guidance": (sections.get("writing_guidance") or {}).get("content", {}),
        "memory": (sections.get("memory") or {}).get("content", {}),
    }


def build_chapter_context_payload(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    """Assemble full chapter context payload for text/json output."""
    outline = extract_chapter_outline(project_root, chapter_num)

    prev_summaries = []
    for prev_ch in range(max(1, chapter_num - 2), chapter_num):
        summary = extract_chapter_summary(project_root, prev_ch)
        prev_summaries.append(f"### 第{prev_ch}章摘要\n{summary}")

    state_summary = extract_state_summary(project_root)
    contract_context = _load_contract_context(project_root, chapter_num)
    memory_context = contract_context.get("memory", {})
    rag_assist = _load_rag_assist(project_root, chapter_num, outline, memory_context)

    return {
        "chapter": chapter_num,
        "outline": outline,
        "previous_summaries": prev_summaries,
        "state_summary": state_summary,
        "context_contract_version": contract_context.get("context_contract_version"),
        "context_weight_stage": contract_context.get("context_weight_stage"),
        "memory_context": memory_context,
        "reader_signal": contract_context.get("reader_signal", {}),
        "genre_profile": contract_context.get("genre_profile", {}),
        "writing_guidance": contract_context.get("writing_guidance", {}),
        "rag_assist": rag_assist,
    }


def _render_text(payload: Dict[str, Any]) -> str:
    chapter_num = payload.get("chapter")
    lines: List[str] = []

    lines.append(f"# 第 {chapter_num} 章创作上下文")
    lines.append("")

    lines.append("## 本章大纲")
    lines.append("")
    lines.append(str(payload.get("outline", "")))
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 前文摘要")
    lines.append("")
    for item in payload.get("previous_summaries", []):
        lines.append(item)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 当前状态")
    lines.append("")
    lines.append(str(payload.get("state_summary", "")))
    lines.append("")

    memory_context = payload.get("memory_context") or {}
    previous_card = memory_context.get("previous_chapter_memory_card") or {}
    active_threads = memory_context.get("active_plot_threads") or []
    timeline_anchors = memory_context.get("recent_timeline_anchors") or []
    state_changes = memory_context.get("related_entity_state_changes") or []
    if previous_card or active_threads or timeline_anchors or state_changes:
        lines.append("## 连续性记忆")
        lines.append("")
        if previous_card:
            chapter = previous_card.get("chapter", "?")
            lines.append(f"- 上章交接卡: 第{chapter}章")
            summary = str(previous_card.get("summary", "") or "").strip()
            if summary:
                lines.append(f"- 上章摘要: {summary}")
            bridge = str(previous_card.get("next_chapter_bridge", "") or "").strip()
            if bridge:
                lines.append(f"- 本章必须接住: {bridge}")
        for row in active_threads[:3]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- 活跃线程: "
                f"{row.get('title') or row.get('content') or '未命名'} "
                f"(status={row.get('status')}, priority={row.get('priority', row.get('urgency', ''))})"
            )
        for row in timeline_anchors[:2]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- 时间锚点: "
                f"Ch{row.get('chapter', '?')} "
                f"{row.get('anchor_time') or row.get('relative_to_previous') or row.get('notes') or ''}"
            )
        for row in state_changes[:3]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- 状态变化: "
                f"{row.get('entity_id')} {row.get('field')} "
                f"{row.get('old_value')}→{row.get('new_value')} (Ch{row.get('chapter')})"
            )
        lines.append("")

    contract_version = payload.get("context_contract_version")
    if contract_version:
        lines.append(f"## Contract ({contract_version})")
        lines.append("")
        stage = payload.get("context_weight_stage")
        if stage:
            lines.append(f"- 上下文阶段权重: {stage}")
            lines.append("")

    writing_guidance = payload.get("writing_guidance") or {}
    guidance_items = writing_guidance.get("guidance_items") or []
    checklist = writing_guidance.get("checklist") or []
    checklist_score = writing_guidance.get("checklist_score") or {}
    methodology = writing_guidance.get("methodology") or {}
    if guidance_items or checklist:
        lines.append("## 写作执行建议")
        lines.append("")
        for idx, item in enumerate(guidance_items, start=1):
            lines.append(f"{idx}. {item}")

        if checklist:
            total_weight = 0.0
            required_count = 0
            for row in checklist:
                if isinstance(row, dict):
                    try:
                        total_weight += float(row.get("weight") or 0)
                    except (TypeError, ValueError):
                        pass
                    if row.get("required"):
                        required_count += 1

            lines.append("")
            lines.append("### 执行检查清单（可评分）")
            lines.append("")
            lines.append(f"- 项目数: {len(checklist)}")
            lines.append(f"- 总权重: {total_weight:.2f}")
            lines.append(f"- 必做项: {required_count}")
            lines.append("")

            for idx, row in enumerate(checklist, start=1):
                if not isinstance(row, dict):
                    lines.append(f"{idx}. {row}")
                    continue
                label = str(row.get("label") or "").strip() or "未命名项"
                weight = row.get("weight")
                required_tag = "必做" if row.get("required") else "可选"
                verify_hint = str(row.get("verify_hint") or "").strip()
                lines.append(f"{idx}. [{required_tag}][w={weight}] {label}")
                if verify_hint:
                    lines.append(f"   - 验收: {verify_hint}")

        if checklist_score:
            lines.append("")
            lines.append("### 执行评分")
            lines.append("")
            lines.append(f"- 评分: {checklist_score.get('score')}")
            lines.append(f"- 完成率: {checklist_score.get('completion_rate')}")
            lines.append(f"- 必做完成率: {checklist_score.get('required_completion_rate')}")

        lines.append("")

    if isinstance(methodology, dict) and methodology.get("enabled"):
        lines.append("## 长篇方法论策略")
        lines.append("")
        lines.append(f"- 框架: {methodology.get('framework')}")
        methodology_scope = methodology.get("genre_profile_key") or methodology.get("pilot") or "general"
        lines.append(f"- 适用题材: {methodology_scope}")
        lines.append(f"- 章节阶段: {methodology.get('chapter_stage')}")
        observability = methodology.get("observability") or {}
        if observability:
            lines.append(
                "- 指标: "
                f"next_reason={observability.get('next_reason_clarity')}, "
                f"anchor={observability.get('anchor_effectiveness')}, "
                f"rhythm={observability.get('rhythm_naturalness')}"
            )
        signals = methodology.get("signals") or {}
        risk_flags = list(signals.get("risk_flags") or [])
        if risk_flags:
            lines.append(f"- 风险标记: {', '.join(str(flag) for flag in risk_flags)}")
        lines.append("")

    reader_signal = payload.get("reader_signal") or {}
    review_trend = reader_signal.get("review_trend") or {}
    if review_trend:
        overall_avg = review_trend.get("overall_avg")
        lines.append("## 追读信号")
        lines.append("")
        lines.append(f"- 最近审查均分: {overall_avg}")
        low_ranges = reader_signal.get("low_score_ranges") or []
        if low_ranges:
            lines.append(f"- 低分区间数: {len(low_ranges)}")
        lines.append("")

    genre_profile = payload.get("genre_profile") or {}
    if genre_profile.get("genre"):
        lines.append("## 题材锚定")
        lines.append("")
        lines.append(f"- 题材: {genre_profile.get('genre')}")
        genres = genre_profile.get("genres") or []
        if len(genres) > 1:
            lines.append(f"- 复合题材: {' + '.join(str(token) for token in genres)}")
            composite_hints = genre_profile.get("composite_hints") or []
            for row in composite_hints[:2]:
                lines.append(f"- {row}")
        refs = genre_profile.get("reference_hints") or []
        for row in refs[:3]:
            lines.append(f"- {row}")
        lines.append("")

    rag_assist = payload.get("rag_assist") or {}
    hits = rag_assist.get("hits") or []
    if rag_assist.get("invoked") and hits:
        lines.append("## RAG 检索线索")
        lines.append("")
        lines.append(f"- 模式: {rag_assist.get('mode')}")
        lines.append(f"- 意图: {rag_assist.get('intent')}")
        lines.append(f"- 查询: {rag_assist.get('query')}")
        lines.append("")
        for idx, row in enumerate(hits[:5], start=1):
            chapter = row.get("chapter", "?")
            scene_index = row.get("scene_index", "?")
            score = row.get("score", 0)
            source = row.get("source", "unknown")
            content = row.get("content", "")
            lines.append(f"{idx}. [Ch{chapter}-S{scene_index}][{source}][score={score}] {content}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="提取章节创作所需的精简上下文")
    parser.add_argument("--chapter", type=int, required=True, help="目标章节号")
    parser.add_argument("--project-root", type=str, help="项目根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    args = parser.parse_args()

    try:
        project_root = (
            find_project_root(Path(args.project_root))
            if args.project_root
            else find_project_root()
        )
        payload = build_chapter_context_payload(project_root, args.chapter)

        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_text(payload), end="")

    except Exception as exc:
        print(f"❌ 错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
