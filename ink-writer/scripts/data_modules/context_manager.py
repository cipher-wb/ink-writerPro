#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ContextManager - assemble context packs with weighted priorities.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import logging
from contextlib import contextmanager
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Any, Dict, List, Optional

try:
    from chapter_outline_loader import load_chapter_outline
except ImportError:  # pragma: no cover
    from scripts.chapter_outline_loader import load_chapter_outline

from .config import get_config
from .index_manager import IndexManager, WritingChecklistScoreMeta
from .context_ranker import ContextRanker
from .snapshot_manager import SnapshotManager, SnapshotVersionMismatch
from .context_weights import (
    DEFAULT_TEMPLATE as CONTEXT_DEFAULT_TEMPLATE,
    TEMPLATE_WEIGHTS as CONTEXT_TEMPLATE_WEIGHTS,
    TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT as CONTEXT_TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT,
)
from .genre_aliases import normalize_genre_token, to_profile_key
from .genre_profile_builder import (
    build_composite_genre_hints,
    extract_genre_section,
    extract_markdown_refs,
    parse_genre_tokens,
)
from .golden_three import (
    build_default_preferences,
    build_golden_three_guidance,
    resolve_golden_three_contract,
)
from .writing_guidance_builder import (
    build_methodology_guidance_items,
    build_methodology_strategy_card,
    build_guidance_items,
    build_writing_checklist,
    is_checklist_item_completed,
)


logger = logging.getLogger(__name__)


class ContextManager:
    DEFAULT_TEMPLATE = CONTEXT_DEFAULT_TEMPLATE
    TEMPLATE_WEIGHTS = CONTEXT_TEMPLATE_WEIGHTS
    TEMPLATE_WEIGHTS_DYNAMIC = CONTEXT_TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT
    EXTRA_SECTIONS = {
        "story_skeleton",
        "memory",
        "preferences",
        "alerts",
        "reader_signal",
        "genre_profile",
        "writing_guidance",
        "golden_three_contract",
    }
    SECTION_ORDER = [
        "core",
        "scene",
        "global",
        "reader_signal",
        "genre_profile",
        "golden_three_contract",
        "writing_guidance",
        "story_skeleton",
        "memory",
        "preferences",
        "alerts",
    ]
    SUMMARY_SECTION_RE = re.compile(r"##\s*剧情摘要\s*\r?\n(.*?)(?=\r?\n##|\Z)", re.DOTALL)

    def __init__(self, config=None, snapshot_manager: Optional[SnapshotManager] = None):
        self.config = config or get_config()
        self.snapshot_manager = snapshot_manager or SnapshotManager(self.config)
        self.index_manager = IndexManager(self.config)
        self.context_ranker = ContextRanker(self.config)

    @contextmanager
    def _get_index_conn(self):
        """获取 index.db 连接（确保关闭，避免资源泄漏）"""
        conn = sqlite3.connect(str(self.config.index_db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    def _is_snapshot_compatible(self, cached: Dict[str, Any], template: str) -> bool:
        """判断快照是否可用于当前模板。"""
        if not isinstance(cached, dict):
            return False

        meta = cached.get("meta")
        if not isinstance(meta, dict):
            # 兼容旧快照：未记录 template 时仅允许默认模板复用
            return template == self.DEFAULT_TEMPLATE

        cached_template = meta.get("template")
        if not isinstance(cached_template, str):
            return template == self.DEFAULT_TEMPLATE

        return cached_template == template

    def build_context(
        self,
        chapter: int,
        template: str | None = None,
        use_snapshot: bool = True,
        save_snapshot: bool = True,
        max_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        template = template or self.DEFAULT_TEMPLATE
        self._active_template = template
        if template not in self.TEMPLATE_WEIGHTS:
            template = self.DEFAULT_TEMPLATE
            self._active_template = template

        if use_snapshot:
            try:
                cached = self.snapshot_manager.load_snapshot(chapter)
                if cached and self._is_snapshot_compatible(cached, template):
                    return cached.get("payload", cached)
            except SnapshotVersionMismatch:
                # Snapshot incompatible; rebuild below.
                pass

        pack = self._build_pack(chapter)
        if getattr(self.config, "context_ranker_enabled", True):
            pack = self.context_ranker.rank_pack(pack, chapter)
        assembled = self.assemble_context(pack, template=template, max_chars=max_chars)

        if save_snapshot:
            meta = {"template": template}
            self.snapshot_manager.save_snapshot(chapter, assembled, meta=meta)

        return assembled

    def assemble_context(
        self,
        pack: Dict[str, Any],
        template: str = DEFAULT_TEMPLATE,
        max_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        chapter = int((pack.get("meta") or {}).get("chapter") or 0)
        weights = self._resolve_template_weights(template=template, chapter=chapter)
        # v7.0.4: 动态分层预算，对齐 context-agent.md 规范
        # 基础预算按章节阶段分层，但保底不低于 8000（兼容性保证）
        if max_chars is None:
            if chapter <= 3:
                base_budget = 8000   # 黄金三章：密集加载世界观/角色
            elif chapter <= 30:
                base_budget = 8000   # 开篇期：规范为7000，保底取8000
            elif chapter <= 100:
                base_budget = 9000   # 展开期
            else:
                base_budget = 11000  # 长线期
            max_chars = max(base_budget, 8000)
        else:
            max_chars = max_chars
        extra_budget = int(self.config.context_extra_section_budget or 0)

        sections = {}
        for section_name in self.SECTION_ORDER:
            if section_name in pack:
                sections[section_name] = pack[section_name]

        assembled: Dict[str, Any] = {"meta": pack.get("meta", {}), "sections": {}}
        for name, content in sections.items():
            weight = weights.get(name, 0.0)
            if weight > 0:
                budget = int(max_chars * weight)
            elif name in self.EXTRA_SECTIONS and extra_budget > 0:
                budget = extra_budget
            else:
                budget = None
            text = self._compact_json_text(content, budget)
            assembled["sections"][name] = {"content": content, "text": text, "budget": budget}

        assembled["template"] = template
        assembled["weights"] = weights
        if chapter > 0:
            assembled.setdefault("meta", {})["context_weight_stage"] = self._resolve_context_stage(chapter)

        # Token 预算硬上限：估算总 token 数，超出时按优先级裁剪
        hard_token_limit = int(getattr(self.config, "context_hard_token_limit", 16000))
        total_chars = sum(
            len(s.get("text", ""))
            for s in assembled.get("sections", {}).values()
        )
        # 中文约 1.5 chars/token
        estimated_tokens = int(total_chars / 1.5)
        assembled.setdefault("meta", {})["estimated_tokens"] = estimated_tokens
        assembled["meta"]["hard_token_limit"] = hard_token_limit

        if estimated_tokens > hard_token_limit:
            # 按优先级从低到高裁剪：alerts → preferences → memory → story_skeleton → global
            trim_order = ["alerts", "preferences", "memory", "story_skeleton", "global"]
            sections = assembled.get("sections", {})
            for section_name in trim_order:
                if section_name not in sections:
                    continue
                section = sections[section_name]
                text = section.get("text", "")
                if len(text) > 200:
                    trimmed = text[:200] + "…[BUDGET_TRIMMED]"
                    section["text"] = trimmed
                    section["budget_trimmed"] = True
                    total_chars = sum(len(s.get("text", "")) for s in sections.values())
                    estimated_tokens = int(total_chars / 1.5)
                    assembled["meta"]["estimated_tokens"] = estimated_tokens
                    if estimated_tokens <= hard_token_limit:
                        break
            assembled["meta"]["budget_trimmed"] = estimated_tokens > hard_token_limit
            if estimated_tokens > hard_token_limit:
                logger.warning(
                    "Context pack exceeds hard token limit: %d > %d (after trimming)",
                    estimated_tokens, hard_token_limit,
                )

        return assembled

    def filter_invalid_items(self, items: List[Dict[str, Any]], source_type: str, id_key: str) -> List[Dict[str, Any]]:
        confirmed = self.index_manager.get_invalid_ids(source_type, status="confirmed")
        pending = self.index_manager.get_invalid_ids(source_type, status="pending")
        result = []
        for item in items:
            item_id = str(item.get(id_key, ""))
            if item_id in confirmed:
                continue
            if item_id in pending:
                item = dict(item)
                item["warning"] = "pending_invalid"
            result.append(item)
        return result

    def apply_confidence_filter(self, items: List[Dict[str, Any]], min_confidence: float) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for item in items:
            conf = item.get("confidence")
            if conf is None or conf >= min_confidence:
                filtered.append(item)
        return filtered

    def _build_pack(self, chapter: int) -> Dict[str, Any]:
        state = self._load_state()
        core = {
            "chapter_outline": self._load_outline(chapter),
            "protagonist_snapshot": state.get("protagonist_state", {}),
            "recent_summaries": self._load_recent_summaries(
                chapter,
                window=self.config.context_recent_summaries_window,
            ),
            "recent_meta": self._load_recent_meta(
                state,
                chapter,
                window=self.config.context_recent_meta_window,
            ),
            "volume_summaries": self._load_volume_summaries(
                chapter,
                window=self.config.context_recent_summaries_window,
            ),
        }

        scene = {
            "location_context": state.get("protagonist_state", {}).get("location", {}),
            "appearing_characters": self._load_recent_appearances(
                limit=self.config.context_max_appearing_characters,
            ),
        }
        scene["appearing_characters"] = self.filter_invalid_items(
            scene["appearing_characters"], source_type="entity", id_key="entity_id"
        )
        # 注入角色演变轨迹（如果有）
        scene["appearing_characters"] = self._enrich_with_evolution(scene["appearing_characters"])
        # 注入关系演变轨迹（从relationship_events表读取）
        scene["appearing_characters"] = self._enrich_with_relationship_trajectories(scene["appearing_characters"])

        global_ctx = {
            "worldview_skeleton": self._load_setting("世界观"),
            "power_system_skeleton": self._load_setting("力量体系"),
            "style_contract_ref": self._load_setting("风格契约"),
        }
        # 加载总纲核心段落（全局故事走向感知）
        if getattr(self.config, "context_master_outline_enabled", True):
            global_ctx["master_outline_core"] = self._load_master_outline_core()

        genre_profile = self._load_genre_profile(state)
        preferences = build_default_preferences(self._load_json_optional(self.config.preferences_file))
        golden_three_plan = self._load_json_optional(self.config.golden_three_plan_file)
        golden_three_contract = resolve_golden_three_contract(
            chapter=chapter,
            preferences=preferences,
            golden_three_plan=golden_three_plan,
            genre_profile=genre_profile,
        )
        memory = self._load_json_optional(self.config.project_memory_file)
        memory.update(self._load_structured_memory(chapter, state))
        story_skeleton = self._load_story_skeleton(chapter)
        alert_slice = max(0, int(self.config.context_alerts_slice))
        reader_signal = self._load_reader_signal(chapter)
        writing_guidance = self._build_writing_guidance(
            chapter,
            reader_signal,
            genre_profile,
            golden_three_contract=golden_three_contract,
        )

        return {
            "meta": {"chapter": chapter},
            "core": core,
            "scene": scene,
            "global": global_ctx,
            "reader_signal": reader_signal,
            "genre_profile": genre_profile,
            "golden_three_contract": golden_three_contract,
            "writing_guidance": writing_guidance,
            "story_skeleton": story_skeleton,
            "preferences": preferences,
            "memory": memory,
            "alerts": {
                "disambiguation_warnings": (
                    state.get("disambiguation_warnings", [])[-alert_slice:] if alert_slice else []
                ),
                "disambiguation_pending": (
                    state.get("disambiguation_pending", [])[-alert_slice:] if alert_slice else []
                ),
                **self._build_canary_alerts(chapter),
            },
        }

    def _build_canary_alerts(self, chapter: int) -> Dict[str, Any]:
        """构建金丝雀健康提醒数据，集成到 alerts 字段中。

        所有查询包裹 try/except，表不存在或数据为空时返回空列表（检查通过）。
        """
        result: Dict[str, Any] = {
            "canary_stagnant_characters": [],
            "canary_conflict_repetitions": [],
            "canary_forgotten_threads": [],
            "canary_timeline_issues": [],
        }
        db_path = self.config.index_db
        if not db_path or not db_path.exists():
            return result

        try:
            with self._get_index_conn() as conn:
                # A.2 角色发展停滞检测（40+章无演变记录）
                try:
                    rows = conn.execute(
                        """
                        SELECT e.canonical_name, e.tier,
                               (SELECT MAX(chapter) FROM chapters) - COALESCE(MAX(cel.chapter), 0) as stagnant_chapters
                        FROM entities e
                        LEFT JOIN character_evolution_ledger cel ON e.id = cel.entity_id
                        WHERE e.type = '角色' AND e.tier IN ('核心', '重要') AND e.is_archived = 0
                        GROUP BY e.id
                        HAVING stagnant_chapters > 40
                        ORDER BY stagnant_chapters DESC LIMIT 5
                        """
                    ).fetchall()
                    result["canary_stagnant_characters"] = [
                        {"name": r["canonical_name"], "tier": r["tier"], "chapters_stagnant": r["stagnant_chapters"]}
                        for r in rows
                    ]
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
                    logger.warning("canary: stagnant characters query failed: %s", exc)

                # A.3 冲突模式重复检测（最近30章内重复3+次）
                try:
                    rows = conn.execute(
                        """
                        SELECT conflict_type, resolution_mechanism, COUNT(*) as count,
                               GROUP_CONCAT(chapter) as chapters
                        FROM plot_structure_fingerprints
                        WHERE chapter >= (SELECT MAX(chapter) FROM chapters) - 30
                        GROUP BY conflict_type, resolution_mechanism
                        HAVING COUNT(*) >= 3
                        ORDER BY count DESC
                        """
                    ).fetchall()
                    result["canary_conflict_repetitions"] = [
                        {
                            "pattern": f"{r['conflict_type']}+{r['resolution_mechanism']}",
                            "count": r["count"],
                            "chapters": r["chapters"],
                        }
                        for r in rows
                    ]
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
                    logger.warning("canary: conflict repetition query failed: %s", exc)

                # A.6 遗忘伏笔补充检测（活跃但已沉默30+章）
                try:
                    rows = conn.execute(
                        """
                        SELECT thread_id, title, content, last_touched_chapter,
                               (SELECT MAX(chapter) FROM chapters) - last_touched_chapter as silent_chapters
                        FROM plot_thread_registry
                        WHERE status = 'active'
                          AND last_touched_chapter < (SELECT MAX(chapter) FROM chapters) - 30
                        ORDER BY silent_chapters DESC LIMIT 5
                        """
                    ).fetchall()
                    result["canary_forgotten_threads"] = [
                        {
                            "id": r["thread_id"],
                            "title": r["title"],
                            "last_touched": r["last_touched_chapter"],
                            "silent_chapters": r["silent_chapters"],
                        }
                        for r in rows
                    ]
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
                    logger.warning("canary: forgotten threads query failed: %s", exc)

                # A.5 时间线链条验证（最近10章锚点）
                try:
                    rows = conn.execute(
                        """
                        SELECT chapter, anchor_time, countdown, relative_to_previous
                        FROM timeline_anchors
                        WHERE chapter >= (SELECT MAX(chapter) FROM chapters) - 10
                        ORDER BY chapter ASC
                        """
                    ).fetchall()
                    issues = []
                    prev_time = None
                    prev_chapter = None
                    for r in rows:
                        if prev_time and r["anchor_time"] and r["relative_to_previous"]:
                            rel = str(r["relative_to_previous"])
                            if "倒退" in rel or "之前" in rel:
                                issues.append(
                                    f"ch{prev_chapter}→ch{r['chapter']}: 时间倒退（{rel}）"
                                )
                        prev_time = r["anchor_time"]
                        prev_chapter = r["chapter"]
                    result["canary_timeline_issues"] = issues
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
                    logger.warning("canary: timeline anchor query failed: %s", exc)
        except sqlite3.Error as exc:
            logger.warning("canary: index.db connection failed: %s", exc)

        return result

    def _load_reader_signal(self, chapter: int) -> Dict[str, Any]:
        if not getattr(self.config, "context_reader_signal_enabled", True):
            return {}

        recent_limit = max(1, int(getattr(self.config, "context_reader_signal_recent_limit", 5)))
        pattern_window = max(1, int(getattr(self.config, "context_reader_signal_window_chapters", 20)))
        review_window = max(1, int(getattr(self.config, "context_reader_signal_review_window", 5)))
        include_debt = bool(getattr(self.config, "context_reader_signal_include_debt", False))

        recent_power = self.index_manager.get_recent_reading_power(limit=recent_limit)
        pattern_stats = self.index_manager.get_pattern_usage_stats(last_n_chapters=pattern_window)
        hook_stats = self.index_manager.get_hook_type_stats(last_n_chapters=pattern_window)
        review_trend = self.index_manager.get_review_trend_stats(last_n=review_window)

        low_score_ranges: List[Dict[str, Any]] = []
        for row in review_trend.get("recent_ranges", []):
            score = row.get("overall_score")
            if isinstance(score, (int, float)) and float(score) < 75:
                low_score_ranges.append(
                    {
                        "start_chapter": row.get("start_chapter"),
                        "end_chapter": row.get("end_chapter"),
                        "overall_score": score,
                    }
                )

        signal: Dict[str, Any] = {
            "recent_reading_power": recent_power,
            "pattern_usage": pattern_stats,
            "hook_type_usage": hook_stats,
            "review_trend": review_trend,
            "low_score_ranges": low_score_ranges,
            "next_chapter": chapter,
        }

        if include_debt:
            signal["debt_summary"] = self.index_manager.get_debt_summary()

        return signal

    def _load_genre_profile(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not getattr(self.config, "context_genre_profile_enabled", True):
            return {}

        fallback = str(getattr(self.config, "context_genre_profile_fallback", "shuangwen") or "shuangwen")
        project = state.get("project") or {}
        project_info = state.get("project_info") or {}
        genre_raw = str(project.get("genre") or project_info.get("genre") or fallback)
        genres = self._parse_genre_tokens(genre_raw)
        if not genres:
            genres = [fallback]
        max_genres = max(1, int(getattr(self.config, "context_genre_profile_max_genres", 2)))
        genres = genres[:max_genres]

        primary_genre = genres[0]
        secondary_genres = genres[1:]
        composite = len(genres) > 1
        profile_texts = self._load_reference_texts("genre-profiles.md")
        taxonomy_texts = self._load_reference_texts("reading-power-taxonomy.md")

        profile_excerpt = self._extract_reference_section(profile_texts, primary_genre)
        taxonomy_excerpt = self._extract_reference_section(taxonomy_texts, primary_genre)

        secondary_profiles: List[str] = []
        secondary_taxonomies: List[str] = []
        for extra in secondary_genres:
            secondary_profiles.append(self._extract_reference_section(profile_texts, extra))
            secondary_taxonomies.append(self._extract_reference_section(taxonomy_texts, extra))

        refs = self._extract_markdown_refs(
            "\n".join([profile_excerpt] + secondary_profiles),
            max_items=int(getattr(self.config, "context_genre_profile_max_refs", 8)),
        )

        composite_hints = self._build_composite_genre_hints(genres, refs)

        return {
            "genre": primary_genre,
            "genre_raw": genre_raw,
            "genres": genres,
            "composite": composite,
            "secondary_genres": secondary_genres,
            "profile_excerpt": profile_excerpt,
            "taxonomy_excerpt": taxonomy_excerpt,
            "secondary_profile_excerpts": secondary_profiles,
            "secondary_taxonomy_excerpts": secondary_taxonomies,
            "reference_hints": refs,
            "composite_hints": composite_hints,
        }

    def _load_structured_memory(self, chapter: int, state: Dict[str, Any]) -> Dict[str, Any]:
        previous_card = self._load_previous_memory_card(chapter, state)
        active_threads = self._load_active_plot_threads(chapter, state)
        timeline_anchors = self._load_recent_timeline_anchors(chapter, state)
        state_changes = self._load_related_entity_state_changes(
            chapter,
            previous_card=previous_card,
            active_threads=active_threads,
        )
        candidate_facts = self._load_candidate_facts(previous_card, active_threads)

        return {
            "previous_chapter_memory_card": previous_card,
            "active_plot_threads": active_threads,
            "recent_timeline_anchors": timeline_anchors,
            "related_entity_state_changes": state_changes,
            "candidate_facts": candidate_facts,
        }

    def _load_previous_memory_card(self, chapter: int, state: Dict[str, Any]) -> Dict[str, Any]:
        card = self.index_manager.get_previous_chapter_memory_card(chapter)
        if card:
            return card

        previous_chapter = chapter - 1
        if previous_chapter < 1:
            return {}

        summary_entry = self._load_summary_text(
            previous_chapter,
            snippet_chars=int(getattr(self.config, "context_story_skeleton_snippet_chars", 400)),
        )
        recent_meta = self._load_recent_meta(state, chapter, window=1)
        prev_meta = recent_meta[-1] if recent_meta else {}
        appearances = self.index_manager.get_chapter_appearances(previous_chapter)
        involved_entities = [row.get("entity_id") for row in appearances if row.get("entity_id")]

        hook = prev_meta.get("hook", {}) if isinstance(prev_meta.get("hook"), dict) else {}
        ending = prev_meta.get("ending", {}) if isinstance(prev_meta.get("ending"), dict) else {}

        fallback = {
            "chapter": previous_chapter,
            "summary": (summary_entry or {}).get("summary", ""),
            "goal": "",
            "conflict": "",
            "result": "",
            "next_chapter_bridge": str(hook.get("content") or ending.get("emotion") or ""),
            "unresolved_questions": [],
            "key_facts": [],
            "involved_entities": involved_entities,
            "plot_progress": [],
            "payload_json": {
                "source": "legacy_backfill",
                "chapter_meta": prev_meta,
            },
        }

        if fallback["summary"] or fallback["next_chapter_bridge"] or involved_entities:
            try:
                from .index_manager import ChapterMemoryCardMeta

                self.index_manager.save_chapter_memory_card(
                    ChapterMemoryCardMeta(
                        chapter=previous_chapter,
                        summary=fallback["summary"],
                        next_chapter_bridge=fallback["next_chapter_bridge"],
                        involved_entities=involved_entities,
                        payload_json=fallback["payload_json"],
                    )
                )
            except (sqlite3.Error, OSError) as e:
                logger.warning("failed to persist memory card for chapter %s: %s", previous_chapter, e)
        return fallback

    def _load_active_plot_threads(self, chapter: int, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        limit = max(1, int(getattr(self.config, "context_max_urgent_foreshadowing", 10)))
        rows = self.index_manager.get_active_plot_threads(
            limit=limit,
            before_chapter=chapter,
            min_priority=0,
        )
        if rows:
            # 对临近解决的伏笔（remaining <= 5），加载种植章摘要以增强共鸣性
            enriched = []
            for row in rows:
                row = dict(row)  # 浅拷贝避免污染原数据
                target = row.get("target_payoff_chapter")
                planted = row.get("planted_chapter")
                if target and planted:
                    remaining = int(target) - chapter
                    row["remaining_chapters"] = remaining
                    if remaining <= 5 and planted:
                        # 加载种植章摘要（如果没有atmospheric_snapshot）
                        if not row.get("atmospheric_snapshot"):
                            planted_summary = self._load_summary_text(int(planted), snippet_chars=300)
                            if planted_summary and planted_summary.get("summary"):
                                row["planted_chapter_summary"] = planted_summary["summary"]
                enriched.append(row)
            return enriched

        plot_threads = state.get("plot_threads", {}) if isinstance(state.get("plot_threads"), dict) else {}
        foreshadowing = plot_threads.get("foreshadowing", [])
        if not isinstance(foreshadowing, list):
            return []

        ranked = sorted(
            [row for row in foreshadowing if isinstance(row, dict)],
            key=lambda row: (
                int(row.get("priority") or row.get("urgency") or 0),
                int(row.get("last_touched_chapter") or row.get("planted_chapter") or row.get("chapter") or 0),
            ),
            reverse=True,
        )
        return ranked[:limit]

    def _load_recent_timeline_anchors(self, chapter: int, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = self.index_manager.get_recent_timeline_anchors(limit=3, before_chapter=chapter)
        if rows:
            return rows

        recent_meta = self._load_recent_meta(state, chapter, window=3)
        anchors: List[Dict[str, Any]] = []
        for row in recent_meta:
            if not isinstance(row, dict):
                continue
            timeline_anchor = row.get("timeline_anchor")
            if isinstance(timeline_anchor, dict) and timeline_anchor:
                anchors.append({"chapter": row.get("chapter"), **timeline_anchor})
                continue
            ending = row.get("ending")
            if isinstance(ending, dict) and any(ending.get(key) for key in ("time", "location", "emotion")):
                anchors.append(
                    {
                        "chapter": row.get("chapter"),
                        "anchor_time": ending.get("time", ""),
                        "to_location": ending.get("location", ""),
                        "notes": ending.get("emotion", ""),
                    }
                )
        return anchors[-3:]

    def _load_related_entity_state_changes(
        self,
        chapter: int,
        previous_card: Dict[str, Any],
        active_threads: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        entity_ids: List[str] = []
        for entity_id in previous_card.get("involved_entities", []) if isinstance(previous_card, dict) else []:
            if entity_id and entity_id not in entity_ids:
                entity_ids.append(entity_id)
        for row in active_threads:
            if not isinstance(row, dict):
                continue
            for entity_id in row.get("related_entities", []) or []:
                if entity_id and entity_id not in entity_ids:
                    entity_ids.append(entity_id)

        if not entity_ids:
            recent = self._load_recent_appearances(limit=5)
            for row in recent:
                entity_id = row.get("entity_id")
                if entity_id and entity_id not in entity_ids:
                    entity_ids.append(entity_id)

        changes: List[Dict[str, Any]] = []
        for entity_id in entity_ids[:6]:
            for row in self.index_manager.get_entity_state_changes(entity_id, limit=3):
                try:
                    row_chapter = int(row.get("chapter") or 0)
                except (TypeError, ValueError):
                    row_chapter = 0
                if row_chapter >= chapter:
                    continue
                changes.append(row)

        changes.sort(key=lambda row: int(row.get("chapter") or 0), reverse=True)
        return changes[:12]

    def _load_candidate_facts(
        self,
        previous_card: Dict[str, Any],
        active_threads: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        entity_ids: List[str] = []
        for entity_id in previous_card.get("involved_entities", []) if isinstance(previous_card, dict) else []:
            if entity_id and entity_id not in entity_ids:
                entity_ids.append(entity_id)
        for row in active_threads:
            if not isinstance(row, dict):
                continue
            for entity_id in row.get("related_entities", []) or []:
                if entity_id and entity_id not in entity_ids:
                    entity_ids.append(entity_id)

        candidates: List[Dict[str, Any]] = []
        if entity_ids:
            for entity_id in entity_ids[:4]:
                candidates.extend(self.index_manager.get_candidate_facts(limit=3, entity_id=entity_id))
        if not candidates:
            candidates = self.index_manager.get_candidate_facts(limit=6)
        return candidates[:8]

    def _load_genre_baseline(self, genre: str) -> Dict[str, Any]:
        """从 style_benchmark.json 读取题材的统计基线数据。"""
        _repo_root = Path(__file__).resolve().parents[3]
        benchmark_path = _repo_root / "benchmark" / "style_benchmark.json"
        if not benchmark_path.exists():
            return {}
        try:
            import json as _json
            data = _json.loads(benchmark_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        by_genre = data.get("by_genre", {})
        # 尝试精确匹配
        if genre in by_genre:
            return {"source": "exact", "genre": genre, **by_genre[genre]}
        # 尝试模糊匹配（题材名包含关系）
        for key, val in by_genre.items():
            if genre and (genre in key or key in genre):
                return {"source": "fuzzy", "genre": key, **val}
        # 回退到 overall
        overall = data.get("overall", {})
        if overall:
            return {"source": "overall_fallback", "genre": "总体", **overall}
        return {}

    def _build_writing_guidance(
        self,
        chapter: int,
        reader_signal: Dict[str, Any],
        genre_profile: Dict[str, Any],
        *,
        golden_three_contract: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if not getattr(self.config, "context_writing_guidance_enabled", True):
            return {}

        limit = max(1, int(getattr(self.config, "context_writing_guidance_max_items", 6)))
        low_score_threshold = float(
            getattr(self.config, "context_writing_guidance_low_score_threshold", 75.0)
        )

        # 解析 craft_lessons 目录：ink-writer repo 根目录下的 benchmark/craft_lessons/
        _repo_root = Path(__file__).resolve().parents[3]
        _craft_dir = _repo_root / "benchmark" / "craft_lessons"
        guidance_bundle = build_guidance_items(
            chapter=chapter,
            reader_signal=reader_signal,
            genre_profile=genre_profile,
            low_score_threshold=low_score_threshold,
            hook_diversify_enabled=bool(
                getattr(self.config, "context_writing_guidance_hook_diversify", True)
            ),
            craft_lessons_dir=str(_craft_dir) if _craft_dir.is_dir() else "",
        )

        guidance = list(guidance_bundle.get("guidance") or [])
        golden_three_guidance = build_golden_three_guidance(golden_three_contract or {})
        if golden_three_guidance:
            guidance = golden_three_guidance + guidance

        # v10.5: 注入题材风格基线（来自 benchmark 114本小说统计）
        genre_baseline = self._load_genre_baseline(
            str(genre_profile.get("genre") or "")
        )
        if genre_baseline:
            baseline_hints = []
            sl = genre_baseline.get("sentence_length_mean")
            dr = genre_baseline.get("dialogue_ratio")
            ed = genre_baseline.get("exclamation_density")
            if sl:
                baseline_hints.append(f"句长目标≈{sl:.0f}字")
            if dr:
                baseline_hints.append(f"对话占比≈{dr * 100:.0f}%")
            if ed:
                baseline_hints.append(f"感叹号密度≈{ed:.1f}/千字")
            if baseline_hints:
                guidance.append(
                    f"题材风格基线（{genre_baseline.get('genre', '总体')}，114本统计）："
                    + "、".join(baseline_hints)
                )

        methodology_strategy: Dict[str, Any] = {}

        if self._is_methodology_enabled_for_genre(genre_profile):
            methodology_strategy = build_methodology_strategy_card(
                chapter=chapter,
                reader_signal=reader_signal,
                genre_profile=genre_profile,
                label=str(getattr(self.config, "context_methodology_label", "digital-serial-v1")),
            )
            guidance.extend(build_methodology_guidance_items(methodology_strategy))

        checklist = self._build_writing_checklist(
            chapter=chapter,
            guidance_items=guidance,
            reader_signal=reader_signal,
            genre_profile=genre_profile,
            golden_three_contract=golden_three_contract,
            strategy_card=methodology_strategy,
        )

        checklist_score = self._compute_writing_checklist_score(
            chapter=chapter,
            checklist=checklist,
            reader_signal=reader_signal,
        )

        if getattr(self.config, "context_writing_score_persist_enabled", True):
            self._persist_writing_checklist_score(checklist_score)

        low_ranges = guidance_bundle.get("low_ranges") or []
        hook_usage = guidance_bundle.get("hook_usage") or {}
        pattern_usage = guidance_bundle.get("pattern_usage") or {}
        genre = str(guidance_bundle.get("genre") or genre_profile.get("genre") or "").strip()

        hook_types = list(hook_usage.keys())[:3] if isinstance(hook_usage, dict) else []
        top_patterns = (
            sorted(pattern_usage, key=pattern_usage.get, reverse=True)[:3]
            if isinstance(pattern_usage, dict)
            else []
        )

        return {
            "chapter": chapter,
            "guidance_items": guidance[:limit],
            "checklist": checklist,
            "checklist_score": checklist_score,
            "methodology": methodology_strategy,
            "golden_three_mode": bool((golden_three_contract or {}).get("enabled")),
            "golden_three_contract": golden_three_contract or {},
            "signals_used": {
                "has_low_score_ranges": bool(low_ranges),
                "hook_types": hook_types,
                "top_patterns": top_patterns,
                "genre": genre,
                "methodology_enabled": bool(methodology_strategy.get("enabled")),
                "golden_three_enabled": bool((golden_three_contract or {}).get("enabled")),
            },
        }

    def _compute_writing_checklist_score(
        self,
        chapter: int,
        checklist: List[Dict[str, Any]],
        reader_signal: Dict[str, Any],
    ) -> Dict[str, Any]:
        total_items = len(checklist)
        required_items = 0
        completed_items = 0
        completed_required = 0
        total_weight = 0.0
        completed_weight = 0.0
        pending_labels: List[str] = []

        for item in checklist:
            if not isinstance(item, dict):
                continue
            required = bool(item.get("required"))
            weight = float(item.get("weight") or 1.0)
            total_weight += weight
            if required:
                required_items += 1

            completed = self._is_checklist_item_completed(item, reader_signal)
            if completed:
                completed_items += 1
                completed_weight += weight
                if required:
                    completed_required += 1
            else:
                pending_labels.append(str(item.get("label") or item.get("id") or "未命名项"))

        completion_rate = (completed_items / total_items) if total_items > 0 else 1.0
        weighted_rate = (completed_weight / total_weight) if total_weight > 0 else completion_rate
        required_rate = (completed_required / required_items) if required_items > 0 else 1.0

        score = 100.0 * (0.5 * weighted_rate + 0.3 * required_rate + 0.2 * completion_rate)

        if getattr(self.config, "context_writing_score_include_reader_trend", True):
            trend_window = max(1, int(getattr(self.config, "context_writing_score_trend_window", 10)))
            trend = self.index_manager.get_writing_checklist_score_trend(last_n=trend_window)
            baseline = float(trend.get("score_avg") or 0.0)
            if baseline > 0:
                score += max(-10.0, min(10.0, (score - baseline) * 0.1))

        score = round(max(0.0, min(100.0, score)), 2)

        return {
            "chapter": chapter,
            "score": score,
            "completion_rate": round(completion_rate, 4),
            "weighted_completion_rate": round(weighted_rate, 4),
            "required_completion_rate": round(required_rate, 4),
            "total_items": total_items,
            "required_items": required_items,
            "completed_items": completed_items,
            "completed_required": completed_required,
            "total_weight": round(total_weight, 2),
            "completed_weight": round(completed_weight, 2),
            "pending_items": pending_labels,
            "trend_window": int(getattr(self.config, "context_writing_score_trend_window", 10)),
        }

    def _is_checklist_item_completed(self, item: Dict[str, Any], reader_signal: Dict[str, Any]) -> bool:
        return is_checklist_item_completed(item, reader_signal)

    def _persist_writing_checklist_score(self, checklist_score: Dict[str, Any]) -> None:
        if not checklist_score:
            return
        try:
            self.index_manager.save_writing_checklist_score(
                WritingChecklistScoreMeta(
                    chapter=int(checklist_score.get("chapter") or 0),
                    template=str(getattr(self, "_active_template", self.DEFAULT_TEMPLATE) or self.DEFAULT_TEMPLATE),
                    total_items=int(checklist_score.get("total_items") or 0),
                    required_items=int(checklist_score.get("required_items") or 0),
                    completed_items=int(checklist_score.get("completed_items") or 0),
                    completed_required=int(checklist_score.get("completed_required") or 0),
                    total_weight=float(checklist_score.get("total_weight") or 0.0),
                    completed_weight=float(checklist_score.get("completed_weight") or 0.0),
                    completion_rate=float(checklist_score.get("completion_rate") or 0.0),
                    score=float(checklist_score.get("score") or 0.0),
                    score_breakdown={
                        "weighted_completion_rate": checklist_score.get("weighted_completion_rate"),
                        "required_completion_rate": checklist_score.get("required_completion_rate"),
                        "trend_window": checklist_score.get("trend_window"),
                    },
                    pending_items=list(checklist_score.get("pending_items") or []),
                    source="context_manager",
                )
            )
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            logger.warning("failed to persist writing checklist score: %s", exc)

    def _resolve_context_stage(self, chapter: int) -> str:
        early = max(1, int(getattr(self.config, "context_dynamic_budget_early_chapter", 30)))
        late = max(early + 1, int(getattr(self.config, "context_dynamic_budget_late_chapter", 120)))
        if chapter <= early:
            return "early"
        if chapter >= late:
            return "late"
        return "mid"

    def _resolve_template_weights(self, template: str, chapter: int) -> Dict[str, float]:
        template_key = template if template in self.TEMPLATE_WEIGHTS else self.DEFAULT_TEMPLATE
        base = dict(self.TEMPLATE_WEIGHTS.get(template_key, self.TEMPLATE_WEIGHTS[self.DEFAULT_TEMPLATE]))
        if not getattr(self.config, "context_dynamic_budget_enabled", True):
            return base

        stage = self._resolve_context_stage(chapter)
        dynamic_weights = getattr(self.config, "context_template_weights_dynamic", None)
        if not isinstance(dynamic_weights, dict):
            dynamic_weights = self.TEMPLATE_WEIGHTS_DYNAMIC

        stage_weights = dynamic_weights.get(stage, {}) if isinstance(dynamic_weights.get(stage, {}), dict) else {}
        staged = stage_weights.get(template_key)
        if isinstance(staged, dict):
            return dict(staged)

        return base

    def _parse_genre_tokens(self, genre_raw: str) -> List[str]:
        support_composite = bool(getattr(self.config, "context_genre_profile_support_composite", True))
        separators_raw = getattr(self.config, "context_genre_profile_separators", ("+", "/", "|", ","))
        separators = tuple(str(token) for token in separators_raw if str(token))
        return parse_genre_tokens(
            genre_raw,
            support_composite=support_composite,
            separators=separators,
        )

    def _normalize_genre_token(self, token: str) -> str:
        return normalize_genre_token(token)

    def _build_composite_genre_hints(self, genres: List[str], refs: List[str]) -> List[str]:
        return build_composite_genre_hints(genres, refs)

    def _plugin_reference_root(self) -> Path:
        return Path(__file__).resolve().parents[2] / "references"

    def _project_reference_root(self) -> Path:
        return self.config.project_root / ".claude" / "references"

    def _load_reference_texts(self, filename: str) -> Dict[str, str]:
        texts = {"base": "", "override": ""}
        base_path = self._plugin_reference_root() / filename
        override_path = self._project_reference_root() / filename
        if base_path.exists():
            texts["base"] = base_path.read_text(encoding="utf-8")
        if override_path.exists():
            texts["override"] = override_path.read_text(encoding="utf-8")
        return texts

    def _extract_reference_section(self, texts: Dict[str, str], genre: str) -> str:
        override_text = str((texts or {}).get("override") or "")
        base_text = str((texts or {}).get("base") or "")
        override_excerpt = self._extract_genre_section(override_text, genre) if override_text else ""
        if override_excerpt:
            return override_excerpt
        return self._extract_genre_section(base_text, genre) if base_text else ""

    def _build_writing_checklist(
        self,
        chapter: int,
        guidance_items: List[str],
        reader_signal: Dict[str, Any],
        genre_profile: Dict[str, Any],
        golden_three_contract: Dict[str, Any] | None = None,
        strategy_card: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        _ = chapter
        if not getattr(self.config, "context_writing_checklist_enabled", True):
            return []

        min_items = max(1, int(getattr(self.config, "context_writing_checklist_min_items", 3)))
        max_items = max(min_items, int(getattr(self.config, "context_writing_checklist_max_items", 6)))
        default_weight = float(getattr(self.config, "context_writing_checklist_default_weight", 1.0))
        if default_weight <= 0:
            default_weight = 1.0

        return build_writing_checklist(
            guidance_items=guidance_items,
            reader_signal=reader_signal,
            genre_profile=genre_profile,
            golden_three_contract=golden_three_contract,
            strategy_card=strategy_card,
            min_items=min_items,
            max_items=max_items,
            default_weight=default_weight,
        )

    def _is_methodology_enabled_for_genre(self, genre_profile: Dict[str, Any]) -> bool:
        if not bool(getattr(self.config, "context_methodology_enabled", False)):
            return False

        whitelist_raw = getattr(self.config, "context_methodology_genre_whitelist", ("*",))
        if isinstance(whitelist_raw, str):
            whitelist_iter = [whitelist_raw]
        else:
            whitelist_iter = list(whitelist_raw or [])

        whitelist = {str(token).strip().lower() for token in whitelist_iter if str(token).strip()}
        if not whitelist:
            return True
        if "*" in whitelist or "all" in whitelist:
            return True

        genre = str((genre_profile or {}).get("genre") or "").strip()
        if not genre:
            return False

        profile_key = to_profile_key(genre)
        return profile_key in whitelist

    def _compact_json_text(self, content: Any, budget: Optional[int]) -> str:
        raw = json.dumps(content, ensure_ascii=False)
        if budget is None or len(raw) <= budget:
            return raw
        if not getattr(self.config, "context_compact_text_enabled", True):
            return raw[:budget]

        min_budget = max(1, int(getattr(self.config, "context_compact_min_budget", 120)))
        if budget <= min_budget:
            return raw[:budget]

        head_ratio = float(getattr(self.config, "context_compact_head_ratio", 0.65))
        head_budget = int(budget * max(0.2, min(0.9, head_ratio)))
        tail_budget = max(0, budget - head_budget - 10)
        compact = f"{raw[:head_budget]}…[TRUNCATED]{raw[-tail_budget:] if tail_budget else ''}"
        return compact[:budget]

    def _extract_genre_section(self, text: str, genre: str) -> str:
        return extract_genre_section(text, genre)

    def _extract_markdown_refs(self, text: str, max_items: int = 8) -> List[str]:
        return extract_markdown_refs(text, max_items=max_items)

    def _load_state(self) -> Dict[str, Any]:
        path = self.config.state_file
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_outline(self, chapter: int) -> str:
        return load_chapter_outline(self.config.project_root, chapter, max_chars=1500)

    def _load_volume_summaries(
        self, chapter: int, window: int = 3, chapters_per_volume: int = 50
    ) -> List[Dict[str, Any]]:
        """加载当前章节之前所有已完成卷的 mega-summary。

        只返回在 recent_summaries 窗口之前的卷，避免重复加载。
        """
        if chapter <= chapters_per_volume:
            return []

        summaries_dir = self.config.ink_dir / "summaries"
        if not summaries_dir.exists():
            return []

        # recent window 覆盖的最小章节号
        recent_start = max(1, chapter - window)

        results: List[Dict[str, Any]] = []
        vol = 1
        while True:
            vol_end = vol * chapters_per_volume
            # 该卷结束章必须在 recent window 之前，否则跳过（避免重叠）
            if vol_end >= recent_start:
                break
            mega_file = summaries_dir / f"vol{vol}_mega.md"
            if mega_file.exists():
                try:
                    content = mega_file.read_text(encoding="utf-8")
                    results.append({
                        "volume": vol,
                        "summary": content,
                        "type": "mega_summary",
                    })
                except OSError:
                    logger.warning("failed to read mega-summary: %s", mega_file)
            vol += 1

        return results

    def _load_recent_summaries(self, chapter: int, window: int = 3) -> List[Dict[str, Any]]:
        summaries = []
        for ch in range(max(1, chapter - window), chapter):
            summary = self._load_summary_text(ch)
            if summary:
                summaries.append(summary)
        return summaries

    def _load_recent_meta(self, state: Dict[str, Any], chapter: int, window: int = 3) -> List[Dict[str, Any]]:
        meta = state.get("chapter_meta", {}) or {}
        results = []
        for ch in range(max(1, chapter - window), chapter):
            for key in (f"{ch:04d}", str(ch)):
                if key in meta:
                    results.append({"chapter": ch, **meta.get(key, {})})
                    break
        return results

    def _load_recent_appearances(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        appearances = self.index_manager.get_recent_appearances(limit=limit)
        return appearances or []

    def _enrich_with_evolution(self, characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为出场角色注入演变轨迹摘要（仅核心/重要角色）"""
        if not characters:
            return characters
        entity_ids = [
            c.get("entity_id") or c.get("id")
            for c in characters
            if (c.get("entity_id") or c.get("id"))
            and c.get("tier") in ("核心", "重要", None)  # None = 未标注，也尝试查询
        ]
        if not entity_ids:
            return characters
        try:
            evolution_map = self.index_manager.get_characters_evolution_summary(
                entity_ids, max_entries_per_char=8
            )
        except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
            logger.warning("failed to load character evolution summary: %s", e)
            return characters
        if not evolution_map:
            return characters
        enriched = []
        for c in characters:
            c = dict(c)  # 浅拷贝避免污染原数据
            eid = c.get("entity_id") or c.get("id")
            if eid and eid in evolution_map:
                entries = evolution_map[eid]
                # 压缩为弧线概述
                arc_summary = " → ".join(
                    f"ch{e['chapter']} {e.get('arc_phase', '?')}"
                    for e in entries
                    if e.get("arc_phase")
                )
                c["evolution_arc"] = arc_summary or None
                # 附最近一条台词样本
                for e in reversed(entries):
                    if e.get("voice_sample"):
                        c["recent_voice_sample"] = e["voice_sample"]
                        break
            enriched.append(c)
        return enriched

    def _enrich_with_relationship_trajectories(self, characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为出场角色注入关系演变轨迹（批量SQL查询，从relationship_events表读取）"""
        if not characters:
            return characters
        entity_ids = [c.get("entity_id") or c.get("id") for c in characters if c.get("entity_id") or c.get("id")]
        if not entity_ids:
            return characters
        try:
            # 单次批量查询所有角色的关系事件
            all_events = self.index_manager.get_relationship_events_batch(entity_ids, limit_per_entity=20)
            if not all_events:
                return characters
            # 为每个角色构建轨迹摘要
            trajectories: Dict[str, list] = {}
            for eid, events in all_events.items():
                pairs: Dict[str, list] = {}
                for evt in events:
                    pair_key = f"{evt.get('from_entity', '')}↔{evt.get('to_entity', '')}"
                    pairs.setdefault(pair_key, []).append(evt)
                summaries = []
                for pair_key, evts in pairs.items():
                    trajectory = " → ".join(
                        f"ch{e.get('chapter', '?')} {e.get('type', '?')}({e.get('polarity', 0):+.1f})"
                        for e in sorted(evts, key=lambda x: x.get("chapter", 0))
                    )
                    summaries.append(f"{pair_key}: {trajectory}")
                if summaries:
                    trajectories[eid] = summaries
        except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
            logger.warning("failed to load relationship trajectories: %s", e)
            return characters
        if not trajectories:
            return characters
        enriched = []
        for c in characters:
            c = dict(c)
            eid = c.get("entity_id") or c.get("id")
            if eid and eid in trajectories:
                c["relationship_trajectory"] = "; ".join(trajectories[eid][:5])
            enriched.append(c)
        return enriched

    def _load_setting(self, keyword: str) -> str:
        settings_dir = self.config.settings_dir
        candidates = [
            settings_dir / f"{keyword}.md",
        ]
        for path in candidates:
            if path.exists():
                return path.read_text(encoding="utf-8")
        # fallback: any file containing keyword
        matches = list(settings_dir.glob(f"*{keyword}*.md"))
        if matches:
            return matches[0].read_text(encoding="utf-8")
        return f"[{keyword}设定未找到]"

    def _extract_summary_excerpt(self, text: str, max_chars: int) -> str:
        if not text:
            return ""
        match = self.SUMMARY_SECTION_RE.search(text)
        excerpt = match.group(1).strip() if match else text.strip()
        if max_chars > 0 and len(excerpt) > max_chars:
            return excerpt[:max_chars].rstrip()
        return excerpt

    def _load_summary_text(self, chapter: int, snippet_chars: Optional[int] = None) -> Optional[Dict[str, Any]]:
        summary_path = self.config.ink_dir / "summaries" / f"ch{chapter:04d}.md"
        if not summary_path.exists():
            return None
        text = summary_path.read_text(encoding="utf-8")
        if snippet_chars:
            summary_text = self._extract_summary_excerpt(text, snippet_chars)
        else:
            summary_text = text
        return {"chapter": chapter, "summary": summary_text}

    def _load_master_outline_core(self) -> str:
        """加载总纲核心段落（故事内核/主线脉络）"""
        max_chars = int(getattr(self.config, "context_master_outline_max_chars", 500))
        outline_dir = self.config.outline_dir
        candidates = [
            outline_dir / "总纲.md",
            outline_dir / "总大纲.md",
            outline_dir / "master_outline.md",
        ]
        for path in candidates:
            try:
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                    if len(text) > max_chars:
                        return text[:max_chars].rstrip() + "…"
                    return text
            except OSError:
                logger.warning("failed to read outline file %s", path, exc_info=True)
                continue
        return ""

    def _load_story_skeleton(self, chapter: int) -> List[Dict[str, Any]]:
        max_samples = max(0, int(self.config.context_story_skeleton_max_samples))
        snippet_chars = int(self.config.context_story_skeleton_snippet_chars)

        if max_samples <= 0 or chapter <= 3:
            return []

        samples: List[Dict[str, Any]] = []
        used_chapters: set = set()

        # Slot 1: 第1章摘要（故事起点，始终包含）
        s1 = self._load_summary_text(1, snippet_chars=snippet_chars)
        if s1 and s1.get("summary"):
            samples.append(s1)
            used_chapters.add(1)

        # Slot 2: 尝试按chapter_reading_power加载高分关键章（转折点）
        try:
            top_chapters = self.index_manager.get_top_reading_power_chapters(
                limit=max_samples - 2,  # 留2个slot给起点和最近
                before_chapter=chapter,
            )
            for tc in top_chapters:
                ch_num = tc.get("chapter")
                if ch_num and ch_num not in used_chapters and len(samples) < max_samples - 1:
                    s = self._load_summary_text(int(ch_num), snippet_chars=snippet_chars)
                    if s and s.get("summary"):
                        samples.append(s)
                        used_chapters.add(int(ch_num))
        except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
            logger.warning("failed to load top reading power chapters, falling back to interval sampling: %s", e)
            # 回退到固定间隔采样
            interval = max(1, int(self.config.context_story_skeleton_interval))
            cursor = chapter - interval
            while cursor >= 1 and len(samples) < max_samples - 1:
                if cursor not in used_chapters:
                    s = self._load_summary_text(cursor, snippet_chars=snippet_chars)
                    if s and s.get("summary"):
                        samples.append(s)
                        used_chapters.add(cursor)
                cursor -= interval

        # Slot N: 最近1章摘要（紧邻上下文）
        recent = chapter - 1
        if recent >= 1 and recent not in used_chapters and len(samples) < max_samples:
            s = self._load_summary_text(recent, snippet_chars=snippet_chars)
            if s and s.get("summary"):
                samples.append(s)

        # 按章节号排序
        samples.sort(key=lambda x: x.get("chapter", 0))
        return samples

    def _load_json_optional(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}


def main():
    import argparse
    from .cli_output import print_success, print_error

    parser = argparse.ArgumentParser(description="Context Manager CLI")
    parser.add_argument("--project-root", type=str, help="项目根目录")
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--template", type=str, default=ContextManager.DEFAULT_TEMPLATE)
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--max-chars", type=int, default=8000)

    args = parser.parse_args()

    config = None
    if args.project_root:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .ink/state.json）
        from project_locator import resolve_project_root
        from .config import DataModulesConfig

        resolved_root = resolve_project_root(args.project_root)
        config = DataModulesConfig.from_project_root(resolved_root)

    manager = ContextManager(config)
    try:
        payload = manager.build_context(
            chapter=args.chapter,
            template=args.template,
            use_snapshot=not args.no_snapshot,
            save_snapshot=True,
            max_chars=args.max_chars,
        )
        print_success(payload, message="context_built")
        try:
            manager.index_manager.log_tool_call("context_manager:build", True, chapter=args.chapter)
        except (sqlite3.Error, OSError) as exc:
            logger.warning("failed to log successful tool call: %s", exc)
    except Exception as exc:
        print_error("CONTEXT_BUILD_FAILED", str(exc), suggestion="请检查项目结构与依赖文件")
        try:
            manager.index_manager.log_tool_call(
                "context_manager:build", False, error_code="CONTEXT_BUILD_FAILED", error_message=str(exc), chapter=args.chapter
            )
        except (sqlite3.Error, OSError) as log_exc:
            logger.warning("failed to log failed tool call: %s", log_exc)


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
