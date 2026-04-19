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
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from chapter_outline_loader import load_chapter_outline

from runtime_compat import enable_windows_utf8_stdio

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file


OUTLINE_FIELD_ALIASES: Dict[str, List[str]] = {
    "goal": ["本章目标", "目标", "本章职责", "章节职责", "核心任务"],
    "conflict": ["核心冲突", "冲突", "阻力", "对抗点"],
    "cost": ["代价", "风险", "压力", "代偿"],
    "change": ["本章变化", "变化", "结果", "阶段变化"],
    "hook": ["章末钩子", "钩子", "尾钩", "章末问题"],
    "transition": ["是否过渡章", "过渡章判定", "过渡章"],
}

REVIEW_SETTINGS_FILE_LIMIT = 8
REVIEW_SETTINGS_SNIPPET_CHARS = 700
REVIEW_CHAPTER_SNIPPET_CHARS = 900


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
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager

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
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.context.rag_adapter import RAGAdapter

    config = DataModulesConfig.from_project_root(project_root)
    adapter = RAGAdapter(config)
    intent_payload = adapter.query_router.route_intent(query)
    center_entities = list(intent_payload.get("entities") or [])

    results = []
    mode = "auto"
    fallback_reason = ""

    # v10.6.1: RAG 必填，不再静默降级到 BM25
    results = asyncio.run(
        adapter.search(
            query=query,
            top_k=top_k,
            strategy="auto",
            chapter=chapter_num,
            center_entities=center_entities,
        )
    )

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


def _search_semantic_recall(
    project_root: Path,
    chapter_num: int,
    query: str,
    top_k: int,
    scene_entities: List[str] | None = None,
) -> Dict[str, Any] | None:
    """Semantic chapter recall via local FAISS index (US-302).

    Returns payload dict on success, None if index not available.
    """
    from ink_writer.semantic_recall.config import SemanticRecallConfig
    from ink_writer.semantic_recall.chapter_index import ChapterVectorIndex
    from ink_writer.semantic_recall.retriever import SemanticChapterRetriever

    sr_config = SemanticRecallConfig.from_project_root(project_root)
    if not sr_config.enabled:
        return None

    index_dir = project_root / ".ink" / "chapter_index"
    if not (index_dir / "chapters.faiss").exists():
        return None

    try:
        index = ChapterVectorIndex(index_dir=index_dir, model_name=sr_config.model_name)
        if index.card_count == 0:
            return None
        sr_config.final_top_k = top_k
        retriever = SemanticChapterRetriever(index=index, config=sr_config)
        payload = retriever.recall_to_payload(
            query=query,
            chapter_num=chapter_num,
            scene_entities=scene_entities,
        )
        payload["enabled"] = True
        return payload
    except Exception as exc:
        logger.warning("Semantic recall failed: %s, falling back", exc)
        return None


def _extract_scene_entities(memory_context: Dict[str, Any]) -> List[str]:
    """Extract entity names from memory context for entity-forced recall."""
    entities: List[str] = []
    prev_card = memory_context.get("previous_chapter_memory_card", {})
    if isinstance(prev_card, dict):
        entities.extend(prev_card.get("involved_entities", []) or [])
    return [str(e) for e in entities if e][:20]


def _load_rag_assist(
    project_root: Path,
    chapter_num: int,
    outline: str,
    memory_context: Dict[str, Any],
) -> Dict[str, Any]:
    _ensure_scripts_path()
    from ink_writer.core.infra.config import DataModulesConfig

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

    # v13.0 (US-302): 优先使用本地语义召回（FAISS），无需 API Key
    scene_entities = _extract_scene_entities(memory_context)
    semantic_payload = _search_semantic_recall(
        project_root=project_root,
        chapter_num=chapter_num,
        query=query,
        top_k=top_k,
        scene_entities=scene_entities,
    )
    if semantic_payload and semantic_payload.get("hits"):
        return semantic_payload

    vector_db = config.vector_db
    has_embed_key = bool(str(getattr(config, "embed_api_key", "") or "").strip())

    if not has_embed_key:
        logger.warning("RAG: EMBED_API_KEY 未配置，跳过向量检索，使用本地内存卡")
        try:
            local_payload = _search_memory_cards_and_summaries(
                project_root=project_root,
                chapter_num=chapter_num,
                query=query,
                top_k=top_k,
            )
            local_payload["enabled"] = True
            local_payload["reason"] = "missing_embed_api_key"
            return local_payload
        except Exception:
            base_payload["reason"] = "missing_embed_api_key"
            return base_payload

    if not vector_db.exists() or vector_db.stat().st_size <= 0:
        local_payload = _search_memory_cards_and_summaries(
            project_root=project_root,
            chapter_num=chapter_num,
            query=query,
            top_k=top_k,
        )
        local_payload["enabled"] = True
        local_payload["reason"] = "vector_db_empty_first_chapters"
        return local_payload

    try:
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
        local_payload["reason"] = "vector_no_hits_supplemented_local"
        return local_payload
    except Exception as exc:
        logger.warning("RAG API 调用失败: %s，回退到本地内存卡检索", exc)
        try:
            local_payload = _search_memory_cards_and_summaries(
                project_root=project_root,
                chapter_num=chapter_num,
                query=query,
                top_k=top_k,
            )
            local_payload["enabled"] = True
            local_payload["reason"] = f"rag_api_error:{exc.__class__.__name__}"
            return local_payload
        except Exception:
            base_payload["reason"] = f"rag_api_error:{exc.__class__.__name__}"
            return base_payload


def _load_contract_context(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    """Build context via ContextManager and return selected sections."""
    _ensure_scripts_path()
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.context.context_manager import ContextManager

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
        "core": (sections.get("core") or {}).get("content", {}),
        "scene": (sections.get("scene") or {}).get("content", {}),
        "story_skeleton": (sections.get("story_skeleton") or {}).get("content", {}),
        "reader_signal": (sections.get("reader_signal") or {}).get("content", {}),
        "genre_profile": (sections.get("genre_profile") or {}).get("content", {}),
        "golden_three_contract": (sections.get("golden_three_contract") or {}).get("content", {}),
        "writing_guidance": (sections.get("writing_guidance") or {}).get("content", {}),
        "memory": (sections.get("memory") or {}).get("content", {}),
        "alerts": (sections.get("alerts") or {}).get("content", {}),
    }


def build_chapter_context_payload(project_root: Path, chapter_num: int) -> Dict[str, Any]:
    """Assemble full chapter context payload for text/json output."""
    outline = extract_chapter_outline(project_root, chapter_num)

    prev_summaries = []
    # v9.x+: 窗口从 2 章扩大到 10 章，让 core_context.recent_summaries 承载更长的跨章记忆
    for prev_ch in range(max(1, chapter_num - 10), chapter_num):
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
        "core_context": contract_context.get("core", {}),
        "scene_context": contract_context.get("scene", {}),
        "story_skeleton": contract_context.get("story_skeleton", []),
        "memory_context": memory_context,
        "reader_signal": contract_context.get("reader_signal", {}),
        "genre_profile": contract_context.get("genre_profile", {}),
        "golden_three_contract": contract_context.get("golden_three_contract", {}),
        "writing_guidance": contract_context.get("writing_guidance", {}),
        "rag_assist": rag_assist,
        "alerts": contract_context.get("alerts", {}),
    }


def _setting_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    priority = 50
    if "角色" in path.as_posix() or "character" in name:
        priority = 10
    elif "规则" in path.as_posix() or "world" in name or "设定" in name:
        priority = 20
    elif "修炼" in path.as_posix() or "力量" in path.as_posix() or "realm" in name:
        priority = 30
    elif "势力" in path.as_posix() or "地图" in path.as_posix():
        priority = 40
    return (priority, path.as_posix())


def _collect_setting_snapshots(project_root: Path) -> List[Dict[str, Any]]:
    settings_dir = project_root / "设定集"
    if not settings_dir.exists():
        return []

    candidates: List[Path] = []
    for pattern in ("**/*.md", "**/*.txt", "**/*.json"):
        candidates.extend(path for path in settings_dir.glob(pattern) if path.is_file())

    snapshots: List[Dict[str, Any]] = []
    for path in sorted(set(candidates), key=_setting_priority):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            logger.debug("failed to read setting file %s", path, exc_info=True)
            continue
        snippet = _compact_text(text, REVIEW_SETTINGS_SNIPPET_CHARS)
        if not snippet:
            continue
        snapshots.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(project_root)),
                "snippet": snippet,
            }
        )
        if len(snapshots) >= REVIEW_SETTINGS_FILE_LIMIT:
            break
    return snapshots


def build_review_pack_payload(project_root: Path, chapter_num: int, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload or build_chapter_context_payload(project_root, chapter_num)

    chapter_file = find_chapter_file(project_root, chapter_num)
    chapter_path = chapter_file.resolve() if chapter_file and chapter_file.exists() else None
    chapter_text = chapter_path.read_text(encoding="utf-8") if chapter_path else ""

    previous_chapters: List[Dict[str, Any]] = []
    # v9.x+: 窗口从 2 章扩大到 10 章，缓解跨章遗忘 bug（作者写新章时能看到前 10 章而非 2 章）
    for prev_ch in range(max(1, chapter_num - 10), chapter_num):
        prev_file = find_chapter_file(project_root, prev_ch)
        prev_path = prev_file.resolve() if prev_file and prev_file.exists() else None
        previous_chapters.append(
            {
                "chapter": prev_ch,
                "chapter_file": str(prev_path) if prev_path else "",
                "summary": extract_chapter_summary(project_root, prev_ch),
                "text_snippet": _compact_text(
                    prev_path.read_text(encoding="utf-8") if prev_path else "",
                    REVIEW_CHAPTER_SNIPPET_CHARS,
                ),
            }
        )

    settings_snapshots = _collect_setting_snapshots(project_root)

    absolute_paths = {
        "project_root": str(project_root.resolve()),
        "chapter_file": str(chapter_path) if chapter_path else "",
        "state_file": str((project_root / ".ink" / "state.json").resolve()),
        "preferences_file": str((project_root / ".ink" / "preferences.json").resolve()),
        "golden_three_plan_file": str((project_root / ".ink" / "golden_three_plan.json").resolve()),
        "setting_files": [row["path"] for row in settings_snapshots],
        "previous_chapter_files": [row["chapter_file"] for row in previous_chapters if row.get("chapter_file")],
    }
    allowed_read_files = _dedupe_preserve(
        [
            path
            for path in [
                absolute_paths["chapter_file"],
                absolute_paths["state_file"],
                absolute_paths["preferences_file"],
                absolute_paths["golden_three_plan_file"],
                *absolute_paths["setting_files"],
                *absolute_paths["previous_chapter_files"],
            ]
            if path and Path(path).exists()
        ]
    )

    bundle = {
        "chapter": chapter_num,
        "project_root": absolute_paths["project_root"],
        "chapter_file": absolute_paths["chapter_file"],
        "chapter_file_name": chapter_path.name if chapter_path else "",
        "chapter_char_count": len(chapter_text),
        "chapter_text": chapter_text,
        "outline": payload.get("outline", ""),
        "previous_chapters": previous_chapters,
        "state_summary": payload.get("state_summary", ""),
        "core_context": payload.get("core_context", {}),
        "scene_context": payload.get("scene_context", {}),
        "memory_context": payload.get("memory_context", {}),
        "reader_signal": payload.get("reader_signal", {}),
        "genre_profile": payload.get("genre_profile", {}),
        "golden_three_contract": payload.get("golden_three_contract", {}),
        "writing_guidance": payload.get("writing_guidance", {}),
        "setting_snapshots": settings_snapshots,
        "absolute_paths": absolute_paths,
        "allowed_read_files": allowed_read_files,
        "review_policy": {
            "primary_source": "review_bundle_file",
            "forbid_binary_db": True,
            "forbid_directory_read": True,
            "forbid_non_whitelisted_relative_paths": True,
            "note": "优先使用 bundle 内嵌内容；仅当 bundle 缺字段时，允许读取 allowed_read_files 中的绝对路径文件。",
        },
    }

    # Inject narrative commitments + plot structure fingerprints from index.db
    try:
        from ink_writer.core.index.index_manager import IndexManager
        from ink_writer.core.infra.config import get_config
        idx_config = get_config(str(project_root))
        idx = IndexManager(idx_config)

        # Active narrative commitments for appearing characters
        entity_ids = []
        if payload and isinstance(payload.get("scene_context"), dict):
            chars = payload["scene_context"].get("appearing_characters", [])
            entity_ids = [c.get("id") for c in chars if isinstance(c, dict) and c.get("id")]
        active_commitments = idx.get_active_commitments(entity_ids=entity_ids if entity_ids else None)
        bundle["narrative_commitments"] = active_commitments[:20]

        # Plot structure fingerprint stats for repetition detection
        pattern_counts = idx.get_fingerprint_pattern_counts(limit=50, before_chapter=chapter_num)
        bundle["plot_structure_fingerprints"] = pattern_counts
    except Exception:
        logger.debug("failed to load narrative commitments or fingerprints", exc_info=True)
        bundle.setdefault("narrative_commitments", [])
        bundle.setdefault("plot_structure_fingerprints", [])

    return bundle


def _compact_text(text: Any, limit: int = 80) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _to_text_list(values: Any, *, limit: int = 4, item_limit: int = 80) -> List[str]:
    rows = values if isinstance(values, list) else [values]
    items: List[str] = []
    for row in rows:
        value = _compact_text(row, item_limit)
        if value:
            items.append(value)
        if len(items) >= limit:
            break
    return _dedupe_preserve(items)


def _extract_outline_title(outline: str) -> str:
    for line in str(outline or "").splitlines():
        raw = line.strip()
        if not raw.startswith("#"):
            continue
        title = re.sub(r"^#+\s*", "", raw)
        title = re.sub(r"^第\s*\d+\s*章[：:\-\s]*", "", title).strip()
        if title:
            return title
    return ""


def _extract_outline_field(outline: str, aliases: List[str], *, max_chars: int = 90) -> str:
    lines = [line.strip() for line in str(outline or "").splitlines() if line.strip()]
    for line in lines:
        normalized = re.sub(r"^[>\-\*\d\.\)\s]+", "", line)
        normalized = normalized.replace("**", "").replace("__", "")
        for alias in aliases:
            for sep in ("：", ":"):
                prefix = f"{alias}{sep}"
                if normalized.startswith(prefix):
                    return _compact_text(normalized[len(prefix) :].strip(), max_chars)
    return ""


def _extract_outline_points(outline: str, *, limit: int = 5, item_limit: int = 80) -> List[str]:
    points: List[str] = []
    for line in str(outline or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned = re.sub(r"^[>\-\*\d\.\)\s]+", "", stripped).strip()
        if not cleaned:
            continue
        points.append(_compact_text(cleaned, item_limit))
        if len(points) >= limit:
            return _dedupe_preserve(points)

    normalized = _normalize_outline_text(outline)
    if not normalized:
        return []
    for chunk in re.split(r"[。！？；]", normalized):
        value = _compact_text(chunk, item_limit)
        if value:
            points.append(value)
        if len(points) >= limit:
            break
    return _dedupe_preserve(points[:limit])


def _display_name(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("display_name", "name", "title", "entity_name", "entity_id"):
        value = _compact_text(row.get(key), 36)
        if value:
            return value
    return ""


def _extract_location_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("current", "name", "location", "to_location", "from_location"):
            text = _compact_text(value.get(key), 24)
            if text:
                return text
        return ""
    return _compact_text(value, 24)


def _clean_reference_hint(value: Any) -> str:
    text = _compact_text(value, 60).strip("`")
    if not text:
        return ""
    lowered = text.lower()
    if text.startswith("```"):
        return ""
    if re.fullmatch(r"[a-z0-9_\-\[\],: ]+", lowered):
        return ""
    if text.endswith(":"):
        return ""
    return text


def _should_skip_character_row(row: Dict[str, Any]) -> bool:
    entity_id = str((row or {}).get("entity_id") or "").strip().lower()
    return entity_id.startswith(("item_", "loc_", "gf_"))


def _build_character_lines(scene_context: Dict[str, Any], core_context: Dict[str, Any], limit: int = 4) -> List[str]:
    protagonist = core_context.get("protagonist_snapshot", {}) if isinstance(core_context, dict) else {}
    appearances = scene_context.get("appearing_characters", []) if isinstance(scene_context, dict) else []
    lines: List[str] = []

    if isinstance(protagonist, dict):
        name = _compact_text(
            protagonist.get("name")
            or protagonist.get("id")
            or protagonist.get("identity")
            or "主角",
            24,
        )
        power = protagonist.get("power", {}) if isinstance(protagonist.get("power"), dict) else {}
        location = _extract_location_name(protagonist.get("location"))
        motive = _compact_text(protagonist.get("goal") or protagonist.get("current_goal"), 36)
        attributes = protagonist.get("attributes", {}) if isinstance(protagonist.get("attributes"), dict) else {}
        parts = []
        realm = _compact_text(f"{power.get('realm', '')} {power.get('layer', '')}".strip(), 20)
        if realm:
            parts.append(realm)
        if location:
            parts.append(f"位置={location}")
        identity = _compact_text(attributes.get("identity"), 24)
        if identity:
            parts.append(identity)
        if motive:
            parts.append(f"动机={motive}")
        lines.append(f"{name}：{'；'.join(parts) if parts else '承接上章主线行动'}")

    for row in appearances[:limit]:
        if not isinstance(row, dict):
            continue
        if _should_skip_character_row(row):
            continue
        name = _display_name(row)
        if not name or name == "主角":
            continue
        hints = []
        if row.get("last_seen_chapter") or row.get("last_chapter"):
            hints.append(f"最近出场 Ch{row.get('last_seen_chapter') or row.get('last_chapter')}")
        if row.get("entity_type"):
            hints.append(str(row.get("entity_type")))
        if row.get("summary"):
            hints.append(_compact_text(row.get("summary"), 36))
        lines.append(f"{name}：{'；'.join(hints) if hints else '需带着既有关系入场'}")
        if len(lines) >= limit + 1:
            break

    return _dedupe_preserve(lines[: max(1, limit)])


def _format_thread_line(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    title = _compact_text(row.get("title") or row.get("content"), 40)
    if not title:
        return ""
    parts = [title]
    status = _compact_text(row.get("status"), 16)
    if status:
        parts.append(f"状态={status}")
    priority = row.get("priority", row.get("urgency"))
    if priority not in (None, ""):
        parts.append(f"优先级={priority}")
    target = row.get("target_payoff_chapter") or row.get("target_chapter")
    if target:
        parts.append(f"目标回收 Ch{target}")
    return "；".join(parts)


def _format_timeline_line(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    parts: List[str] = []
    chapter = row.get("chapter")
    if chapter:
        parts.append(f"Ch{chapter}")
    for key in ("anchor_time", "relative_to_previous", "previous_time_delta", "countdown"):
        value = _compact_text(row.get(key), 24)
        if value:
            parts.append(value)
    movement = _compact_text(
        "→".join(
            part
            for part in [
                str(row.get("from_location") or "").strip(),
                str(row.get("to_location") or "").strip(),
            ]
            if part
        ),
        24,
    )
    if movement:
        parts.append(f"地点={movement}")
    notes = _compact_text(row.get("notes"), 28)
    if notes:
        parts.append(f"备注={notes}")
    return "；".join(parts)


def _format_state_change_line(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    entity = _compact_text(row.get("entity_id"), 24)
    field = _compact_text(row.get("field"), 18)
    old_value = _compact_text(row.get("old_value"), 18)
    new_value = _compact_text(row.get("new_value"), 18)
    chapter = row.get("chapter")
    if not entity or not field:
        return ""
    change = f"{old_value}→{new_value}" if old_value or new_value else "状态变化"
    if chapter:
        change = f"{change} (Ch{chapter})"
    return f"{entity}.{field} = {change}"


def _format_candidate_fact_line(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    fact = _compact_text(row.get("fact"), 48)
    if not fact:
        return ""
    entity = _compact_text(row.get("entity_id"), 20)
    confidence = row.get("confidence")
    parts = [fact]
    if entity:
        parts.append(f"实体={entity}")
    if confidence not in (None, ""):
        parts.append(f"置信度={confidence}")
    return "；".join(parts)


def _resolve_opening_type(golden_three_contract: Dict[str, Any], outline: str, genre_profile: Dict[str, Any]) -> str:
    opening_trigger = _compact_text((golden_three_contract or {}).get("opening_trigger"), 40)
    if opening_trigger:
        return f"强触发开场：{opening_trigger}"
    genre = _compact_text((genre_profile or {}).get("genre"), 20)
    if genre:
        return f"{genre}题材直入冲突"
    title = _extract_outline_title(outline)
    if title:
        return f"围绕“{title}”直入主冲突"
    return "直入当前主冲突"


def _resolve_emotional_rhythm(
    golden_three_contract: Dict[str, Any],
    writing_guidance: Dict[str, Any],
) -> str:
    role = _compact_text((golden_three_contract or {}).get("golden_three_role"), 30)
    if role:
        return f"{role}，前段施压，中后段兑现并留尾钩"
    methodology = (writing_guidance or {}).get("methodology", {})
    stage = _compact_text(methodology.get("chapter_stage"), 20) if isinstance(methodology, dict) else ""
    if stage:
        return f"{stage}节奏，保持压力-破局-余波链路"
    return "前段设压，中段受阻，后段兑现并留下下一章驱动力"


def _resolve_information_density(golden_three_contract: Dict[str, Any], genre_profile: Dict[str, Any]) -> str:
    opening_window = (golden_three_contract or {}).get("opening_window_chars")
    if opening_window:
        return f"前{opening_window}字优先冲突、承诺与主角压力，设定解释后置"
    genre = _compact_text((genre_profile or {}).get("genre"), 18)
    if genre:
        return f"{genre}题材密度：优先动作/结果/代价，避免说明书化"
    return "高信息密度：优先动作、结果、代价，不平铺背景"


def _resolve_transition_flag(outline: str, golden_three_contract: Dict[str, Any]) -> bool:
    if isinstance(golden_three_contract, dict) and golden_three_contract.get("enabled"):
        return False
    raw = " ".join(
        value
        for value in [
            _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["transition"]),
            _normalize_outline_text(outline),
        ]
        if value
    ).lower()
    return any(token in raw for token in ("过渡", "铺垫", "承上启下"))


def _build_contract_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    outline = str(payload.get("outline") or "")
    memory = payload.get("memory_context") or {}
    previous_card = memory.get("previous_chapter_memory_card") or {}
    golden_three = payload.get("golden_three_contract") or {}
    writing_guidance = payload.get("writing_guidance") or {}
    genre_profile = payload.get("genre_profile") or {}

    unresolved = _to_text_list(previous_card.get("unresolved_questions"), limit=3, item_limit=36)
    micro_payoffs = _to_text_list(golden_three.get("micro_payoffs"), limit=3, item_limit=36)
    hook_requirement = _compact_text(
        _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["hook"])
        or golden_three.get("end_hook_requirement"),
        60,
    )
    dominant_patterns = _to_text_list(
        ((writing_guidance.get("signals_used") or {}).get("top_patterns") or []),
        limit=2,
        item_limit=24,
    )

    goal = _compact_text(
        _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["goal"])
        or previous_card.get("next_chapter_bridge")
        or _extract_outline_title(outline),
        64,
    )
    conflict = _compact_text(
        _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["conflict"])
        or previous_card.get("conflict")
        or golden_three.get("opening_trigger"),
        64,
    )
    cost = _compact_text(
        _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["cost"])
        or previous_card.get("result")
        or "本章必须付出代价或暴露更高层问题",
        64,
    )
    chapter_change = _compact_text(
        _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["change"])
        or (golden_three.get("must_deliver_this_chapter") or golden_three.get("must_deliver") or ["本章必须出现可见变化"])[0],
        64,
    )

    hook_type = ""
    recent_power = (payload.get("reader_signal") or {}).get("recent_reading_power") or []
    if recent_power and isinstance(recent_power[0], dict):
        hook_type = _compact_text(recent_power[0].get("hook_type"), 20)

    track_design_parts = []
    if hook_type:
        track_design_parts.append(f"钩子类型={hook_type}")
    if hook_requirement:
        track_design_parts.append(f"章末要求={hook_requirement}")
    if micro_payoffs:
        track_design_parts.append("微兑现=" + "；".join(micro_payoffs))
    if dominant_patterns:
        track_design_parts.append("爽点模式=" + " / ".join(dominant_patterns))

    return {
        "目标": goal,
        "阻力": conflict,
        "代价": cost,
        "本章变化": chapter_change,
        "未闭合问题": "；".join(unresolved) if unresolved else (hook_requirement or "章末必须留下新的未闭合问题"),
        "核心冲突一句话": conflict or goal or "围绕本章核心目标推进冲突",
        "开头类型": _resolve_opening_type(golden_three, outline, genre_profile),
        "情绪节奏": _resolve_emotional_rhythm(golden_three, writing_guidance),
        "信息密度": _resolve_information_density(golden_three, genre_profile),
        "是否过渡章": _resolve_transition_flag(outline, golden_three),
        "追读力设计": "；".join(track_design_parts) if track_design_parts else "章末必须留下下一章驱动力",
    }


def build_execution_pack_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    chapter_num = int(payload.get("chapter") or 0)
    outline = str(payload.get("outline") or "")
    title = _extract_outline_title(outline) or f"第{chapter_num}章"
    memory = payload.get("memory_context") or {}
    previous_card = memory.get("previous_chapter_memory_card") or {}
    active_threads = memory.get("active_plot_threads") or []
    timeline_anchors = memory.get("recent_timeline_anchors") or []
    state_changes = memory.get("related_entity_state_changes") or []
    candidate_facts = memory.get("candidate_facts") or []
    writing_guidance = payload.get("writing_guidance") or {}
    golden_three = payload.get("golden_three_contract") or {}
    genre_profile = payload.get("genre_profile") or {}
    core_context = payload.get("core_context") or {}
    scene_context = payload.get("scene_context") or {}
    rag_assist = payload.get("rag_assist") or {}
    checklist = writing_guidance.get("checklist") or []

    outline_points = _extract_outline_points(outline, limit=5, item_limit=72)
    must_deliver = _to_text_list(
        golden_three.get("must_deliver_this_chapter") or golden_three.get("must_deliver"),
        limit=4,
        item_limit=40,
    )
    forbidden = _to_text_list(golden_three.get("forbidden_slow_zones"), limit=4, item_limit=28)
    micro_payoffs = _to_text_list(golden_three.get("micro_payoffs"), limit=3, item_limit=36)
    timeline_lines = _dedupe_preserve(
        [value for value in [_format_timeline_line(row) for row in timeline_anchors[:3]] if value]
    )
    thread_lines = _dedupe_preserve(
        [value for value in [_format_thread_line(row) for row in active_threads[:4]] if value]
    )
    state_change_lines = _dedupe_preserve(
        [value for value in [_format_state_change_line(row) for row in state_changes[:4]] if value]
    )
    candidate_fact_lines = _dedupe_preserve(
        [value for value in [_format_candidate_fact_line(row) for row in candidate_facts[:3]] if value]
    )
    rag_lines = _dedupe_preserve(
        [
            _compact_text(
                f"Ch{row.get('chapter', '?')} {row.get('content', '')}",
                72,
            )
            for row in (rag_assist.get("hits") or [])[:3]
            if isinstance(row, dict)
        ]
    )
    character_lines = _build_character_lines(scene_context, core_context, limit=4)
    protagonist = core_context.get("protagonist_snapshot", {}) if isinstance(core_context, dict) else {}
    power = protagonist.get("power", {}) if isinstance(protagonist.get("power"), dict) else {}
    golden_finger = protagonist.get("golden_finger", {}) if isinstance(protagonist.get("golden_finger"), dict) else {}
    location_value = scene_context.get("location_context") if isinstance(scene_context, dict) else ""
    location = ""
    location = _extract_location_name(location_value)
    if not location:
        location = _extract_location_name(protagonist.get("location"))

    guidance_items = _to_text_list(writing_guidance.get("guidance_items"), limit=4, item_limit=72)
    reference_hints = _dedupe_preserve(
        [
            value
            for value in [_clean_reference_hint(item) for item in (genre_profile.get("reference_hints") or [])]
            if value
        ][:2]
    )
    unresolved_questions = _to_text_list(previous_card.get("unresolved_questions"), limit=3, item_limit=36)
    key_facts = _to_text_list(previous_card.get("key_facts"), limit=4, item_limit=36)
    hook_requirement = _compact_text(
        _extract_outline_field(outline, OUTLINE_FIELD_ALIASES["hook"])
        or golden_three.get("end_hook_requirement"),
        72,
    )
    contract_payload = _build_contract_payload(payload)

    taskbook = {
        "本章核心任务": _dedupe_preserve(
            [
                f"标题/定位：{title}",
                *[f"大纲要点：{item}" for item in outline_points[:3]],
                *(f"必须交付：{item}" for item in must_deliver[:3]),
                *(f"绝对不能：{item}" for item in forbidden[:2]),
            ]
        ),
        "接住上章": _dedupe_preserve(
            [
                f"上章摘要：{_compact_text(previous_card.get('summary'), 72)}" if previous_card.get("summary") else "",
                f"本章必须接住：{_compact_text(previous_card.get('next_chapter_bridge'), 72)}"
                if previous_card.get("next_chapter_bridge")
                else "",
                *(f"未闭合：{item}" for item in unresolved_questions[:2]),
                *(f"关键事实：{item}" for item in key_facts[:3]),
            ]
        ),
        "出场角色": character_lines or ["主角与核心关系必须带着上章结果入场"],
        "场景与力量约束": _dedupe_preserve(
            [
                f"地点：{location}" if location else "",
                f"主角实力：{_compact_text('{} {}'.format(power.get('realm', ''), power.get('layer', '')).strip(), 24)}"
                if isinstance(power, dict) and (power.get("realm") or power.get("layer"))
                else "",
                f"金手指：{_compact_text('{} Lv.{}'.format(golden_finger.get('name', ''), golden_finger.get('level', '')).strip(), 24)}"
                if isinstance(golden_finger, dict) and (golden_finger.get("name") or golden_finger.get("level"))
                else "",
                *(f"状态变化：{item}" for item in state_change_lines[:2]),
            ]
        )
        or ["沿用既有地点、能力与资源约束，禁止无因果升级"],
        "时间约束": timeline_lines or ["默认承接上章时间线，若跨日/跨场需显式补过渡"],
        "风格指导": _dedupe_preserve(
            [
                f"黄金三章模式：{golden_three.get('golden_three_role')}" if golden_three.get("enabled") else "常规连载模式",
                *guidance_items,
                *(f"题材提示：{item}" for item in reference_hints),
            ]
        ),
        "连续性与伏笔": _dedupe_preserve(
            [
                *(f"活跃线程：{item}" for item in thread_lines[:3]),
                *(f"低置信度候选事实：{item}" for item in candidate_fact_lines[:2]),
                *(f"检索命中：{item}" for item in rag_lines[:2]),
            ]
        )
        or ["本章至少推进一个活跃线程，禁止重置上一章承诺"],
        "追读力策略": _dedupe_preserve(
            [
                f"读者承诺：{_compact_text(golden_three.get('reader_promise'), 72)}" if golden_three.get("reader_promise") else "",
                f"开头窗口：前{golden_three.get('opening_window_chars')}字"
                if golden_three.get("opening_window_chars")
                else "",
                *(f"微兑现：{item}" for item in micro_payoffs[:2]),
                f"章末要求：{hook_requirement}" if hook_requirement else "",
            ]
        )
        or ["章末必须留下高价值承诺与下章驱动力"],
    }

    immutable_facts = _dedupe_preserve(
        [
            f"大纲标题：{title}",
            *(f"大纲要点：{item}" for item in outline_points[:4]),
            f"上章结果：{_compact_text(previous_card.get('summary'), 72)}" if previous_card.get("summary") else "",
            f"本章承接：{_compact_text(previous_card.get('next_chapter_bridge'), 72)}"
            if previous_card.get("next_chapter_bridge")
            else "",
            *(f"活跃线程：{item}" for item in thread_lines[:2]),
            *(f"时间线：{item}" for item in timeline_lines[:2]),
            *(f"状态变化：{item}" for item in state_change_lines[:2]),
        ]
    )

    required_check_items = []
    optional_check_items = []
    for row in checklist:
        if not isinstance(row, dict):
            continue
        label = _compact_text(row.get("label") or row.get("id"), 40)
        if not label:
            continue
        if row.get("required"):
            required_check_items.append(label)
        else:
            optional_check_items.append(label)

    final_checklist = _dedupe_preserve(
        [*required_check_items[:4], *must_deliver[:3], "章末必须留下未闭合问题或更大驱动力"]
    )
    fail_conditions = _dedupe_preserve(
        [
            "与大纲关键事件或设定规则冲突",
            "未接住上章钩子/承诺",
            "时间线回跳或跨场无过渡",
            "主角能力、信息或资源无因果来源",
            *(f"出现慢区：{item}" for item in forbidden[:2]),
        ]
    )

    step_2a_prompt = {
        "章节节拍": _dedupe_preserve(
            [
                f"开场触发：{contract_payload['开头类型']}",
                f"推进/受阻：{contract_payload['阻力'] or '围绕本章目标持续加压'}",
                f"反转/兑现：{'；'.join(micro_payoffs) if micro_payoffs else contract_payload['本章变化']}",
                f"章末钩子：{hook_requirement or contract_payload['未闭合问题']}",
            ]
        ),
        "不可变事实清单": immutable_facts,
        "禁止事项": fail_conditions,
        "终检清单": final_checklist,
        "fail_conditions": fail_conditions,
    }

    # 提取金丝雀健康提醒数据
    alerts = payload.get("alerts") or {}
    canary_alerts = {
        "stagnant_characters": alerts.get("canary_stagnant_characters") or [],
        "conflict_repetitions": alerts.get("canary_conflict_repetitions") or [],
        "forgotten_threads": alerts.get("canary_forgotten_threads") or [],
        "timeline_issues": alerts.get("canary_timeline_issues") or [],
    }

    return {
        "chapter": chapter_num,
        "title": title,
        "mode": "golden_three" if golden_three.get("enabled") else "standard",
        "taskbook": taskbook,
        "context_contract": contract_payload,
        "step_2a_prompt": step_2a_prompt,
        "canary_alerts": canary_alerts,
    }


def _render_execution_pack_text(pack: Dict[str, Any]) -> str:
    lines: List[str] = []
    chapter_num = pack.get("chapter", "?")
    title = _compact_text(pack.get("title"), 40)
    mode = "黄金三章" if pack.get("mode") == "golden_three" else "常规模式"

    lines.append(f"# 第 {chapter_num} 章创作执行包")
    lines.append("")
    lines.append(f"- 标题: {title}")
    lines.append(f"- 模式: {mode}")
    lines.append("")

    lines.append("## 任务书（8板块）")
    lines.append("")
    taskbook = pack.get("taskbook") or {}
    ordered_sections = [
        "本章核心任务",
        "接住上章",
        "出场角色",
        "场景与力量约束",
        "时间约束",
        "风格指导",
        "连续性与伏笔",
        "追读力策略",
    ]
    for section in ordered_sections:
        rows = taskbook.get(section) or []
        if not rows:
            continue
        lines.append(f"### {section}")
        lines.append("")
        for row in rows:
            lines.append(f"- {row}")
        lines.append("")

    contract = pack.get("context_contract") or {}
    lines.append("## Context Contract")
    lines.append("")
    for key in [
        "目标",
        "阻力",
        "代价",
        "本章变化",
        "未闭合问题",
        "核心冲突一句话",
        "开头类型",
        "情绪节奏",
        "信息密度",
        "是否过渡章",
        "追读力设计",
    ]:
        value = contract.get(key)
        if value in (None, ""):
            continue
        lines.append(f"- {key}: {value}")
    lines.append("")

    prompt = pack.get("step_2a_prompt") or {}
    lines.append("## Step 2A 直写提示")
    lines.append("")
    for key in ["章节节拍", "不可变事实清单", "禁止事项", "终检清单", "fail_conditions"]:
        rows = prompt.get(key) or []
        if not rows:
            continue
        lines.append(f"### {key}")
        lines.append("")
        for row in rows:
            lines.append(f"- {row}")
        lines.append("")

    # 金丝雀写作约束板块（仅在有 WARNING 级结果时渲染）
    canary = pack.get("canary_alerts") or {}
    canary_lines: List[str] = []

    stagnant = canary.get("stagnant_characters") or []
    if stagnant:
        canary_lines.append("### 角色发展要求")
        canary_lines.append("")
        for c in stagnant:
            canary_lines.append(
                f"- 角色 \"{c.get('name', '?')}\"（{c.get('tier', '?')}）"
                f"已 {c.get('chapters_stagnant', '?')} 章无演变，"
                f"本章若出场**必须**展现变化（行为/态度/能力/关系至少一项）"
            )
        canary_lines.append("")

    conflicts = canary.get("conflict_repetitions") or []
    if conflicts:
        canary_lines.append("### 禁用冲突模式")
        canary_lines.append("")
        for c in conflicts:
            canary_lines.append(
                f"- 本章**禁止**使用 \"{c.get('pattern', '?')}\" 冲突模式"
                f"（最近30章已用{c.get('count', '?')}次，出现于ch{c.get('chapters', '?')}）"
            )
        canary_lines.append("")

    forgotten = canary.get("forgotten_threads") or []
    if forgotten:
        canary_lines.append("### 伏笔推进建议")
        canary_lines.append("")
        for t in forgotten:
            canary_lines.append(
                f"- 伏笔 [{t.get('id', '?')}] \"{t.get('title', '?')}\" "
                f"已沉默 {t.get('silent_chapters', '?')} 章，本章**建议**推进或提及"
            )
        canary_lines.append("")

    timeline = canary.get("timeline_issues") or []
    if timeline:
        canary_lines.append("### 时间线约束")
        canary_lines.append("")
        for issue in timeline:
            canary_lines.append(f"- {issue}")
        canary_lines.append("")

    if canary_lines:
        lines.append("## 金丝雀写作约束（自动注入，优先级等同不可变事实）")
        lines.append("")
        lines.extend(canary_lines)

    return "\n".join(lines).rstrip() + "\n"


def _render_review_pack_text(pack: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# 第 {pack.get('chapter', '?')} 章审查包")
    lines.append("")
    lines.append(f"- project_root: {pack.get('project_root', '')}")
    lines.append(f"- chapter_file: {pack.get('chapter_file', '')}")
    lines.append(f"- 正文字数: {pack.get('chapter_char_count', 0)}")
    lines.append("")

    policy = pack.get("review_policy") or {}
    lines.append("## 审查策略")
    lines.append("")
    for key in ["primary_source", "forbid_binary_db", "forbid_directory_read", "forbid_non_whitelisted_relative_paths", "note"]:
        value = policy.get(key)
        if value in ("", None):
            continue
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## 章节正文")
    lines.append("")
    lines.append(str(pack.get("chapter_text", "")))
    lines.append("")

    previous = pack.get("previous_chapters") or []
    if previous:
        lines.append("## 前序章节")
        lines.append("")
        for row in previous:
            lines.append(f"### 第{row.get('chapter')}章")
            if row.get("chapter_file"):
                lines.append(f"- 文件: {row.get('chapter_file')}")
            if row.get("summary"):
                lines.append(f"- 摘要: {row.get('summary')}")
            if row.get("text_snippet"):
                lines.append(f"- 片段: {row.get('text_snippet')}")
            lines.append("")

    snapshots = pack.get("setting_snapshots") or []
    if snapshots:
        lines.append("## 设定快照")
        lines.append("")
        for row in snapshots:
            lines.append(f"- {row.get('relative_path')}: {row.get('snippet')}")
        lines.append("")

    lines.append("## 允许补充读取的绝对路径")
    lines.append("")
    for path in pack.get("allowed_read_files") or []:
        lines.append(f"- {path}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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

    golden_three_contract = payload.get("golden_three_contract") or {}
    if isinstance(golden_three_contract, dict) and golden_three_contract.get("enabled"):
        lines.append("## 黄金三章契约")
        lines.append("")
        lines.append(f"- 本章职责: {golden_three_contract.get('golden_three_role')}")
        lines.append(f"- 开头窗口: 前{golden_three_contract.get('opening_window_chars')}字")
        if golden_three_contract.get("reader_promise"):
            lines.append(f"- 读者承诺: {golden_three_contract.get('reader_promise')}")
        if golden_three_contract.get("opening_trigger"):
            lines.append(f"- 开头触发: {golden_three_contract.get('opening_trigger')}")
        must_deliver = golden_three_contract.get("must_deliver_this_chapter") or []
        if must_deliver:
            lines.append("- 本章必须兑现: " + "；".join(str(item) for item in must_deliver[:3]))
        if golden_three_contract.get("end_hook_requirement"):
            lines.append(f"- 章末要求: {golden_three_contract.get('end_hook_requirement')}")
        forbidden = golden_three_contract.get("forbidden_slow_zones") or []
        if forbidden:
            lines.append("- 硬禁区: " + "；".join(str(item) for item in forbidden[:4]))
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
    import sys as _sys_for_policy
    if _sys_for_policy.platform == "win32":  # pragma: no cover
        import asyncio as _asyncio_for_policy
        _policy_cls = getattr(_asyncio_for_policy, "WindowsProactorEventLoopPolicy", None)
        if _policy_cls is not None:
            _asyncio_for_policy.set_event_loop_policy(_policy_cls())
    parser = argparse.ArgumentParser(description="提取章节创作所需的精简上下文")
    parser.add_argument("--chapter", type=int, required=True, help="目标章节号")
    parser.add_argument("--project-root", type=str, help="项目根目录")
    parser.add_argument(
        "--format",
        choices=["text", "json", "pack", "pack-json", "review-pack", "review-pack-json"],
        default="text",
        help="输出格式",
    )

    args = parser.parse_args()

    try:
        project_root = (
            find_project_root(Path(args.project_root))
            if args.project_root
            else find_project_root()
        )
        payload = build_chapter_context_payload(project_root, args.chapter)
        execution_pack = build_execution_pack_payload(payload)
        review_pack = build_review_pack_payload(project_root, args.chapter, payload)

        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.format == "pack-json":
            print(json.dumps(execution_pack, ensure_ascii=False, indent=2))
        elif args.format == "pack":
            print(_render_execution_pack_text(execution_pack), end="")
        elif args.format == "review-pack-json":
            print(json.dumps(review_pack, ensure_ascii=False, indent=2))
        elif args.format == "review-pack":
            print(_render_review_pack_text(review_pack), end="")
        else:
            print(_render_text(payload), end="")

    except Exception as exc:
        print(f"❌ 错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
