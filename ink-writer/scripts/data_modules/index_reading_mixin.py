#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexReadingMixin extracted from IndexManager.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class IndexReadingMixin:
    def _review_span_label(self, metrics: ReviewMetrics) -> str:
        if metrics.start_chapter == metrics.end_chapter:
            return f"第{metrics.start_chapter}章"
        return f"第{metrics.start_chapter}-{metrics.end_chapter}章"

    def _review_grade_label(self, score: float) -> str:
        if score >= 90:
            return "S"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 60:
            return "C"
        return "D"

    def _render_review_report(self, metrics: ReviewMetrics) -> str:
        span_label = self._review_span_label(metrics)
        severity_counts = metrics.severity_counts or {}
        payload = metrics.review_payload_json or {}
        lines = [f"# {span_label}审查报告", ""]
        lines.extend(
            [
                "## 综合评分",
                f"- 总分：{metrics.overall_score}",
                f"- 等级：{self._review_grade_label(metrics.overall_score)}",
                "",
            ]
        )

        if metrics.dimension_scores:
            lines.append("## 维度评分")
            for key, value in metrics.dimension_scores.items():
                lines.append(f"- {key}：{value}")
            lines.append("")

        lines.extend(
            [
                "## 修改优先级",
                f"- critical：{severity_counts.get('critical', 0)}",
                f"- high：{severity_counts.get('high', 0)}",
                f"- medium：{severity_counts.get('medium', 0)}",
                f"- low：{severity_counts.get('low', 0)}",
                "",
            ]
        )

        lines.append("## 关键问题")
        if metrics.critical_issues:
            for issue in metrics.critical_issues:
                lines.append(f"- {issue}")
        else:
            lines.append("- 无 critical 问题")
        lines.append("")

        golden_three = payload.get("golden_three_metrics")
        if isinstance(golden_three, dict) and golden_three:
            lines.append("## 黄金三章指标")
            for key, value in golden_three.items():
                lines.append(f"- {key}：{value}")
            lines.append("")

        selected_checkers = payload.get("selected_checkers")
        if isinstance(selected_checkers, list) and selected_checkers:
            lines.append("## 审查器")
            for checker in selected_checkers:
                lines.append(f"- {checker}")
            lines.append("")

        anti_ai_force_check = payload.get("anti_ai_force_check")
        timeline_gate = payload.get("timeline_gate")
        if anti_ai_force_check or timeline_gate is not None:
            lines.append("## 审查门槛")
            if anti_ai_force_check:
                lines.append(f"- anti_ai_force_check：{anti_ai_force_check}")
            if timeline_gate is not None:
                lines.append(f"- timeline_gate：{timeline_gate}")
            lines.append("")

        lines.append("## 备注")
        lines.append(metrics.notes.strip() or "- 无")
        lines.append("")
        lines.append(f"_自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")
        lines.append("")
        return "\n".join(lines)

    def _ensure_review_report_file(self, metrics: ReviewMetrics) -> None:
        if not metrics.report_file:
            return
        report_path = Path(metrics.report_file)
        if not report_path.is_absolute():
            report_path = Path(self.config.project_root) / report_path
        if report_path.exists():
            return
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(self._render_review_report(metrics), encoding="utf-8")

    def save_chapter_reading_power(self, meta: ChapterReadingPowerMeta):
        """保存章节追读力元数据"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO chapter_reading_power
                (chapter, hook_type, hook_strength, coolpoint_patterns,
                 micropayoffs, hard_violations, soft_suggestions,
                 is_transition, override_count, debt_balance, notes, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    meta.chapter,
                    meta.hook_type,
                    meta.hook_strength,
                    json.dumps(meta.coolpoint_patterns, ensure_ascii=False),
                    json.dumps(meta.micropayoffs, ensure_ascii=False),
                    json.dumps(meta.hard_violations, ensure_ascii=False),
                    json.dumps(meta.soft_suggestions, ensure_ascii=False),
                    1 if meta.is_transition else 0,
                    meta.override_count,
                    meta.debt_balance,
                    meta.notes,
                    json.dumps(meta.payload_json, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_chapter_reading_power(self, chapter: int) -> Optional[Dict]:
        """获取章节追读力元数据"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM chapter_reading_power WHERE chapter = ?", (chapter,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(
                    row,
                    parse_json=[
                        "coolpoint_patterns",
                        "micropayoffs",
                        "hard_violations",
                        "soft_suggestions",
                        "payload_json",
                    ],
                )
            return None

    def get_recent_reading_power(self, limit: int = 10) -> List[Dict]:
        """获取最近章节的追读力元数据"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM chapter_reading_power
                ORDER BY chapter DESC
                LIMIT ?
            """,
                (limit,),
            )
            return [
                self._row_to_dict(
                    row,
                    parse_json=[
                        "coolpoint_patterns",
                        "micropayoffs",
                        "hard_violations",
                        "soft_suggestions",
                        "payload_json",
                    ],
                )
                for row in cursor.fetchall()
            ]

    def get_pattern_usage_stats(self, last_n_chapters: int = 20) -> Dict[str, int]:
        """获取最近N章的爽点模式使用统计"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT coolpoint_patterns FROM chapter_reading_power
                ORDER BY chapter DESC
                LIMIT ?
            """,
                (last_n_chapters,),
            )

            stats = {}
            for row in cursor.fetchall():
                if row["coolpoint_patterns"]:
                    try:
                        patterns = json.loads(row["coolpoint_patterns"])
                        for p in patterns:
                            stats[p] = stats.get(p, 0) + 1
                    except json.JSONDecodeError as exc:
                        print(
                            f"[index_manager] failed to parse JSON in chapter_reading_power.coolpoint_patterns: {exc}",
                            file=sys.stderr,
                        )
            return stats

    def get_hook_type_stats(self, last_n_chapters: int = 20) -> Dict[str, int]:
        """获取最近N章的钩子类型使用统计"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT hook_type FROM chapter_reading_power
                WHERE hook_type IS NOT NULL AND hook_type != ''
                ORDER BY chapter DESC
                LIMIT ?
            """,
                (last_n_chapters,),
            )

            stats = {}
            for row in cursor.fetchall():
                hook = row["hook_type"]
                stats[hook] = stats.get(hook, 0) + 1
            return stats

    # ==================== 章节记忆 / 线程 / 时间锚点 ====================

    def save_chapter_memory_card(self, meta: ChapterMemoryCardMeta) -> None:
        """保存章节记忆卡。"""
        payload = meta.payload_json or {
            "summary": meta.summary,
            "goal": meta.goal,
            "conflict": meta.conflict,
            "result": meta.result,
            "next_chapter_bridge": meta.next_chapter_bridge,
            "unresolved_questions": meta.unresolved_questions,
            "key_facts": meta.key_facts,
            "involved_entities": meta.involved_entities,
            "plot_progress": meta.plot_progress,
        }
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chapter_memory_cards (
                    chapter, summary, goal, conflict, result, next_chapter_bridge,
                    unresolved_questions, key_facts, involved_entities, plot_progress, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter) DO UPDATE SET
                    summary=excluded.summary,
                    goal=excluded.goal,
                    conflict=excluded.conflict,
                    result=excluded.result,
                    next_chapter_bridge=excluded.next_chapter_bridge,
                    unresolved_questions=excluded.unresolved_questions,
                    key_facts=excluded.key_facts,
                    involved_entities=excluded.involved_entities,
                    plot_progress=excluded.plot_progress,
                    payload_json=excluded.payload_json,
                    updated_at=CURRENT_TIMESTAMP
            """,
                (
                    meta.chapter,
                    meta.summary,
                    meta.goal,
                    meta.conflict,
                    meta.result,
                    meta.next_chapter_bridge,
                    json.dumps(meta.unresolved_questions, ensure_ascii=False),
                    json.dumps(meta.key_facts, ensure_ascii=False),
                    json.dumps(meta.involved_entities, ensure_ascii=False),
                    json.dumps(meta.plot_progress, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_chapter_memory_card(self, chapter: int) -> Optional[Dict[str, Any]]:
        """获取某章记忆卡。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM chapter_memory_cards WHERE chapter = ?",
                (chapter,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(
                row,
                parse_json=[
                    "unresolved_questions",
                    "key_facts",
                    "involved_entities",
                    "plot_progress",
                    "payload_json",
                ],
            )

    def get_recent_chapter_memory_cards(self, limit: int = 5, before_chapter: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取最近章节记忆卡。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if before_chapter is None:
                cursor.execute(
                    "SELECT * FROM chapter_memory_cards ORDER BY chapter DESC LIMIT ?",
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM chapter_memory_cards
                    WHERE chapter < ?
                    ORDER BY chapter DESC
                    LIMIT ?
                """,
                    (before_chapter, limit),
                )
            return [
                self._row_to_dict(
                    row,
                    parse_json=[
                        "unresolved_questions",
                        "key_facts",
                        "involved_entities",
                        "plot_progress",
                        "payload_json",
                    ],
                )
                for row in cursor.fetchall()
            ]

    def get_previous_chapter_memory_card(self, chapter: int) -> Optional[Dict[str, Any]]:
        """获取上一章记忆卡。"""
        cards = self.get_recent_chapter_memory_cards(limit=1, before_chapter=chapter)
        return cards[0] if cards else None

    def upsert_plot_thread(self, meta: PlotThreadRegistryMeta) -> None:
        """写入或更新剧情线程。"""
        payload = meta.payload_json or {
            "thread_id": meta.thread_id,
            "title": meta.title,
            "content": meta.content,
            "thread_type": meta.thread_type,
            "status": meta.status,
            "priority": meta.priority,
            "planted_chapter": meta.planted_chapter,
            "last_touched_chapter": meta.last_touched_chapter,
            "target_payoff_chapter": meta.target_payoff_chapter,
            "resolved_chapter": meta.resolved_chapter,
            "related_entities": meta.related_entities,
            "notes": meta.notes,
            "confidence": meta.confidence,
        }
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO plot_thread_registry (
                    thread_id, title, content, thread_type, status, priority,
                    planted_chapter, last_touched_chapter, target_payoff_chapter,
                    resolved_chapter, related_entities, notes, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    thread_type=excluded.thread_type,
                    status=excluded.status,
                    priority=excluded.priority,
                    planted_chapter=CASE
                        WHEN plot_thread_registry.planted_chapter <= 0 THEN excluded.planted_chapter
                        WHEN excluded.planted_chapter <= 0 THEN plot_thread_registry.planted_chapter
                        ELSE MIN(plot_thread_registry.planted_chapter, excluded.planted_chapter)
                    END,
                    last_touched_chapter=MAX(plot_thread_registry.last_touched_chapter, excluded.last_touched_chapter),
                    target_payoff_chapter=CASE
                        WHEN excluded.target_payoff_chapter > 0 THEN excluded.target_payoff_chapter
                        ELSE plot_thread_registry.target_payoff_chapter
                    END,
                    resolved_chapter=CASE
                        WHEN excluded.resolved_chapter > 0 THEN excluded.resolved_chapter
                        ELSE plot_thread_registry.resolved_chapter
                    END,
                    related_entities=excluded.related_entities,
                    notes=excluded.notes,
                    confidence=excluded.confidence,
                    payload_json=excluded.payload_json,
                    updated_at=CURRENT_TIMESTAMP
            """,
                (
                    meta.thread_id,
                    meta.title,
                    meta.content,
                    meta.thread_type,
                    meta.status,
                    meta.priority,
                    meta.planted_chapter,
                    meta.last_touched_chapter,
                    meta.target_payoff_chapter,
                    meta.resolved_chapter,
                    json.dumps(meta.related_entities, ensure_ascii=False),
                    meta.notes,
                    meta.confidence,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_plot_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """获取单条剧情线程。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM plot_thread_registry WHERE thread_id = ?",
                (thread_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, parse_json=["related_entities", "payload_json"])

    def get_active_plot_threads(
        self,
        limit: int = 10,
        before_chapter: Optional[int] = None,
        min_priority: int = 0,
    ) -> List[Dict[str, Any]]:
        """获取高优先级活跃线程。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            params: List[Any] = [min_priority]
            query = """
                SELECT * FROM plot_thread_registry
                WHERE status NOT IN ('resolved', '已回收', 'closed', 'done')
                  AND priority >= ?
            """
            if before_chapter is not None:
                query += " AND planted_chapter <= ?"
                params.append(before_chapter)
            query += " ORDER BY priority DESC, last_touched_chapter DESC, planted_chapter DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, tuple(params))
            return [
                self._row_to_dict(row, parse_json=["related_entities", "payload_json"])
                for row in cursor.fetchall()
            ]

    def save_timeline_anchor(self, meta: TimelineAnchorMeta) -> None:
        """保存章节时间锚点。"""
        payload = meta.payload_json or {
            "anchor_time": meta.anchor_time,
            "relative_to_previous": meta.relative_to_previous,
            "previous_time_delta": meta.previous_time_delta,
            "countdown": meta.countdown,
            "from_location": meta.from_location,
            "to_location": meta.to_location,
            "movement": meta.movement,
            "notes": meta.notes,
            "involved_entities": meta.involved_entities,
        }
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO timeline_anchors (
                    chapter, anchor_time, relative_to_previous, previous_time_delta,
                    countdown, from_location, to_location, movement, notes,
                    involved_entities, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter) DO UPDATE SET
                    anchor_time=excluded.anchor_time,
                    relative_to_previous=excluded.relative_to_previous,
                    previous_time_delta=excluded.previous_time_delta,
                    countdown=excluded.countdown,
                    from_location=excluded.from_location,
                    to_location=excluded.to_location,
                    movement=excluded.movement,
                    notes=excluded.notes,
                    involved_entities=excluded.involved_entities,
                    payload_json=excluded.payload_json,
                    updated_at=CURRENT_TIMESTAMP
            """,
                (
                    meta.chapter,
                    meta.anchor_time,
                    meta.relative_to_previous,
                    meta.previous_time_delta,
                    meta.countdown,
                    meta.from_location,
                    meta.to_location,
                    meta.movement,
                    meta.notes,
                    json.dumps(meta.involved_entities, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_timeline_anchor(self, chapter: int) -> Optional[Dict[str, Any]]:
        """获取单章时间锚点。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM timeline_anchors WHERE chapter = ?", (chapter,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, parse_json=["involved_entities", "payload_json"])

    def get_recent_timeline_anchors(self, limit: int = 5, before_chapter: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取最近时间锚点。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if before_chapter is None:
                cursor.execute(
                    "SELECT * FROM timeline_anchors ORDER BY chapter DESC LIMIT ?",
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM timeline_anchors
                    WHERE chapter < ?
                    ORDER BY chapter DESC
                    LIMIT ?
                """,
                    (before_chapter, limit),
                )
            return [
                self._row_to_dict(row, parse_json=["involved_entities", "payload_json"])
                for row in cursor.fetchall()
            ]

    def save_candidate_fact(self, meta: CandidateFactMeta) -> int:
        """保存单条候选事实。"""
        payload = meta.payload_json or {
            "fact": meta.fact,
            "fact_key": meta.fact_key,
            "entity_id": meta.entity_id,
            "confidence": meta.confidence,
            "status": meta.status,
            "source": meta.source,
            "evidence": meta.evidence,
            "related_entities": meta.related_entities,
        }
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO candidate_facts (
                    chapter, fact, fact_key, entity_id, confidence, status,
                    source, evidence, related_entities, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter, fact, entity_id, source) DO UPDATE SET
                    fact_key=excluded.fact_key,
                    confidence=excluded.confidence,
                    status=excluded.status,
                    evidence=excluded.evidence,
                    related_entities=excluded.related_entities,
                    payload_json=excluded.payload_json
            """,
                (
                    meta.chapter,
                    meta.fact,
                    meta.fact_key,
                    meta.entity_id,
                    meta.confidence,
                    meta.status,
                    meta.source,
                    meta.evidence,
                    json.dumps(meta.related_entities, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)

    def get_candidate_facts(
        self,
        limit: int = 20,
        entity_id: Optional[str] = None,
        chapter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """查询候选事实。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            clauses: List[str] = []
            params: List[Any] = []
            if entity_id:
                clauses.append("entity_id = ?")
                params.append(entity_id)
            if chapter is not None:
                clauses.append("chapter = ?")
                params.append(chapter)
            query = "SELECT * FROM candidate_facts"
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY chapter DESC, confidence DESC, id DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, tuple(params))
            return [
                self._row_to_dict(row, parse_json=["related_entities", "payload_json"])
                for row in cursor.fetchall()
            ]

    # ==================== v5.4 审查指标 ====================

    def save_review_metrics(self, metrics: ReviewMetrics) -> None:
        """保存审查指标记录"""
        self._ensure_review_report_file(metrics)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO review_metrics
                (start_chapter, end_chapter, overall_score, dimension_scores,
                 severity_counts, critical_issues, report_file, notes, review_payload_json,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(start_chapter, end_chapter)
                DO UPDATE SET
                    overall_score = excluded.overall_score,
                    dimension_scores = excluded.dimension_scores,
                    severity_counts = excluded.severity_counts,
                    critical_issues = excluded.critical_issues,
                    report_file = excluded.report_file,
                    notes = excluded.notes,
                    review_payload_json = excluded.review_payload_json,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    metrics.start_chapter,
                    metrics.end_chapter,
                    metrics.overall_score,
                    json.dumps(metrics.dimension_scores, ensure_ascii=False),
                    json.dumps(metrics.severity_counts, ensure_ascii=False),
                    json.dumps(metrics.critical_issues, ensure_ascii=False),
                    metrics.report_file,
                    metrics.notes,
                    json.dumps(metrics.review_payload_json, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_recent_review_metrics(self, limit: int = 5) -> List[Dict]:
        """获取最近审查记录"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM review_metrics
                ORDER BY end_chapter DESC, start_chapter DESC
                LIMIT ?
            """,
                (limit,),
            )
            return [
                self._row_to_dict(
                    row,
                    parse_json=[
                        "dimension_scores",
                        "severity_counts",
                        "critical_issues",
                        "review_payload_json",
                    ],
                )
                for row in cursor.fetchall()
            ]

    def get_review_trend_stats(self, last_n: int = 5) -> Dict[str, Any]:
        """获取审查趋势统计"""
        records = self.get_recent_review_metrics(last_n)
        if not records:
            return {
                "count": 0,
                "overall_avg": 0.0,
                "dimension_avg": {},
                "severity_totals": {},
                "recent_ranges": [],
            }

        overall_scores: List[float] = []
        dimension_totals: Dict[str, float] = {}
        dimension_counts: Dict[str, int] = {}
        severity_totals: Dict[str, int] = {}

        for record in records:
            score = record.get("overall_score")
            if score is not None:
                try:
                    overall_scores.append(float(score))
                except (TypeError, ValueError):
                    pass

            dimensions = record.get("dimension_scores") or {}
            if isinstance(dimensions, dict):
                for key, value in dimensions.items():
                    try:
                        val = float(value)
                    except (TypeError, ValueError):
                        continue
                    dimension_totals[key] = dimension_totals.get(key, 0.0) + val
                    dimension_counts[key] = dimension_counts.get(key, 0) + 1

            severities = record.get("severity_counts") or {}
            if isinstance(severities, dict):
                for key, value in severities.items():
                    try:
                        count = int(value)
                    except (TypeError, ValueError):
                        continue
                    severity_totals[key] = severity_totals.get(key, 0) + count

        overall_avg = round(sum(overall_scores) / len(overall_scores), 2) if overall_scores else 0.0
        dimension_avg = {
            key: round(dimension_totals[key] / dimension_counts[key], 2)
            for key in dimension_totals
            if dimension_counts.get(key, 0) > 0
        }
        recent_ranges = [
            {
                "start_chapter": record.get("start_chapter"),
                "end_chapter": record.get("end_chapter"),
                "overall_score": record.get("overall_score", 0),
            }
            for record in records
        ]

        return {
            "count": len(records),
            "overall_avg": overall_avg,
            "dimension_avg": dimension_avg,
            "severity_totals": severity_totals,
            "recent_ranges": recent_ranges,
        }

    # ==================== 写作清单评分（Phase F） ====================

    def save_writing_checklist_score(self, meta: WritingChecklistScoreMeta) -> None:
        """保存章节写作清单评分。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO writing_checklist_scores (
                    chapter, template, total_items, required_items,
                    completed_items, completed_required,
                    total_weight, completed_weight, completion_rate, score,
                    score_breakdown, pending_items, source, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter) DO UPDATE SET
                    template=excluded.template,
                    total_items=excluded.total_items,
                    required_items=excluded.required_items,
                    completed_items=excluded.completed_items,
                    completed_required=excluded.completed_required,
                    total_weight=excluded.total_weight,
                    completed_weight=excluded.completed_weight,
                    completion_rate=excluded.completion_rate,
                    score=excluded.score,
                    score_breakdown=excluded.score_breakdown,
                    pending_items=excluded.pending_items,
                    source=excluded.source,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
            """,
                (
                    meta.chapter,
                    meta.template,
                    meta.total_items,
                    meta.required_items,
                    meta.completed_items,
                    meta.completed_required,
                    meta.total_weight,
                    meta.completed_weight,
                    meta.completion_rate,
                    meta.score,
                    json.dumps(meta.score_breakdown, ensure_ascii=False),
                    json.dumps(meta.pending_items, ensure_ascii=False),
                    meta.source,
                    meta.notes,
                ),
            )
            conn.commit()

    def get_writing_checklist_score(self, chapter: int) -> Optional[Dict[str, Any]]:
        """获取指定章节的写作清单评分。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM writing_checklist_scores WHERE chapter = ?",
                (chapter,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, parse_json=["score_breakdown", "pending_items"])

    def get_recent_writing_checklist_scores(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近章节写作清单评分。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM writing_checklist_scores
                ORDER BY chapter DESC
                LIMIT ?
            """,
                (limit,),
            )
            return [
                self._row_to_dict(row, parse_json=["score_breakdown", "pending_items"])
                for row in cursor.fetchall()
            ]

    def get_writing_checklist_score_trend(self, last_n: int = 10) -> Dict[str, Any]:
        """获取写作清单评分趋势统计。"""
        records = self.get_recent_writing_checklist_scores(limit=max(1, int(last_n)))
        if not records:
            return {
                "count": 0,
                "score_avg": 0.0,
                "completion_avg": 0.0,
                "required_completion_avg": 0.0,
                "recent": [],
            }

        scores: List[float] = []
        completion_rates: List[float] = []
        required_rates: List[float] = []
        for row in records:
            try:
                scores.append(float(row.get("score", 0.0)))
            except (TypeError, ValueError):
                pass
            try:
                completion_rates.append(float(row.get("completion_rate", 0.0)))
            except (TypeError, ValueError):
                pass

            required_items = int(row.get("required_items") or 0)
            completed_required = int(row.get("completed_required") or 0)
            if required_items > 0:
                required_rates.append(completed_required / required_items)
            else:
                required_rates.append(1.0)

        return {
            "count": len(records),
            "score_avg": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "completion_avg": round(sum(completion_rates) / len(completion_rates), 4) if completion_rates else 0.0,
            "required_completion_avg": round(sum(required_rates) / len(required_rates), 4) if required_rates else 0.0,
            "recent": [
                {
                    "chapter": row.get("chapter"),
                    "score": row.get("score"),
                    "completion_rate": row.get("completion_rate"),
                }
                for row in records
            ],
        }
