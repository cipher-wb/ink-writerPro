#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Index Manager - 索引管理模块 (v5.4)

管理 index.db (SQLite) 的读写操作：
- 章节元数据索引
- 实体出场记录
- 场景索引
- 实体存储 (从 state.json 迁移)
- 别名索引 (一对多)
- 状态变化记录
- 关系存储
- 快速查询接口
- 追读力债务管理 (v5.3 引入，v5.4 沿用)

v5.4 变更:
- 新增 invalid_facts 表：追踪无效事实 (pending/confirmed)
- 新增 tool_call_stats 表：记录工具调用成功率与错误信息
- 新增 review_metrics 表：记录审查指标与趋势数据

v5.3 变更:
- 新增 override_contracts 表：记录违背软建议时的Override Contract
- 新增 chase_debt 表：追读力债务追踪
- 新增 debt_events 表：债务事件日志（产生/偿还/利息）
- 新增 chapter_reading_power 表：章节追读力元数据

v5.1 变更:
- 新增 entities 表替代 state.json 中的 entities_v3
- 新增 aliases 表替代 state.json 中的 alias_index (支持一对多)
- 新增 state_changes 表替代 state.json 中的 state_changes
- 新增 relationships 表替代 state.json 中的 structured_relationships
"""

import sqlite3
import json
import time
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime

from .config import get_config
from .index_chapter_mixin import IndexChapterMixin
from .index_entity_mixin import IndexEntityMixin
from .index_debt_mixin import IndexDebtMixin
from .index_reading_mixin import IndexReadingMixin
from .index_observability_mixin import IndexObservabilityMixin
from .observability import safe_append_perf_timing, safe_log_tool_call

# 数据类型定义已提取至 index_types.py，此处保留 re-export 以兼容现有导入
from .index_types import (  # noqa: F401
    ChapterMeta,
    SceneMeta,
    EntityMeta,
    StateChangeMeta,
    RelationshipMeta,
    RelationshipEventMeta,
    OverrideContractMeta,
    ChaseDebtMeta,
    DebtEventMeta,
    ChapterReadingPowerMeta,
    ChapterMemoryCardMeta,
    PlotThreadRegistryMeta,
    TimelineAnchorMeta,
    CandidateFactMeta,
    ReviewMetrics,
    WritingChecklistScoreMeta,
)


class IndexManager(IndexChapterMixin, IndexEntityMixin, IndexDebtMixin, IndexReadingMixin, IndexObservabilityMixin):
    """索引管理器"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self._init_db()

    # ==================== 数据库完整性与备份 ====================

    def check_integrity(self) -> dict:
        """
        检查 index.db 完整性。

        返回:
            {"ok": bool, "detail": str, "table_count": int}
        """
        db_path = self.config.index_db
        if not db_path.exists():
            return {"ok": False, "detail": "index.db not found", "table_count": 0}

        try:
            conn = sqlite3.connect(str(db_path))
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                integrity_ok = result is not None and str(result[0]).lower() == "ok"

                tables = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()
                table_count = int(tables[0]) if tables else 0

                detail = str(result[0]) if result else "no result"
                return {
                    "ok": integrity_ok,
                    "detail": detail,
                    "table_count": table_count,
                }
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            return {"ok": False, "detail": str(exc), "table_count": 0}

    def backup_db(self, reason: str = "manual") -> Optional[Path]:
        """
        备份 index.db 到 .ink/ 目录。

        返回备份文件路径，失败返回 None。
        """
        db_path = self.config.index_db
        if not db_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"index.db.{reason}.{timestamp}.bak"
        backup_path = self.config.ink_dir / backup_name

        try:
            # 使用 SQLite 的 backup API 确保一致性
            src = sqlite3.connect(str(db_path))
            dst = sqlite3.connect(str(backup_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            return backup_path
        except (sqlite3.Error, OSError):
            # 降级到文件复制
            try:
                import shutil
                shutil.copy2(str(db_path), str(backup_path))
                return backup_path
            except OSError:
                return None

    def rebuild_db(self) -> dict:
        """
        从章节文件和 state.json 重建 index.db（灾难恢复）。

        仅重建 chapters 表和基础元数据。实体/关系/审查等需要后续
        通过 Data Agent 重新提取来恢复。

        返回: {"ok": bool, "chapters_recovered": int, "detail": str}
        """
        db_path = self.config.index_db
        chapters_dir = self.config.chapters_dir
        summaries_dir = self.config.ink_dir / "summaries"

        # 如果旧库存在，先备份
        if db_path.exists():
            self.backup_db(reason="pre_rebuild")
            db_path.unlink()

        # 重新初始化空库
        self._init_db()

        recovered = 0
        errors = []

        if not chapters_dir.exists():
            return {
                "ok": True,
                "chapters_recovered": 0,
                "detail": "chapters dir not found, empty db created",
            }

        # 扫描章节文件，重建 chapters 表
        import re
        chapter_pattern = re.compile(r"第(\d+)章")

        for md_file in sorted(chapters_dir.glob("第*章*.md")):
            try:
                match = chapter_pattern.search(md_file.name)
                if not match:
                    continue
                chapter_num = int(match.group(1))

                content = md_file.read_text(encoding="utf-8")
                word_count = len(content)

                # 提取标题（文件名中 "章" 后面的部分）
                title = ""
                title_match = re.search(r"第\d+章[-.—]?(.*?)\.md$", md_file.name)
                if title_match:
                    title = title_match.group(1).strip()

                # 尝试加载对应摘要
                summary = ""
                summary_file = summaries_dir / f"ch{chapter_num:04d}.md"
                if summary_file.exists():
                    try:
                        summary = summary_file.read_text(encoding="utf-8")[:2000]
                    except OSError:
                        pass

                meta = ChapterMeta(
                    chapter=chapter_num,
                    title=title,
                    location="",
                    word_count=word_count,
                    characters=[],
                    summary=summary,
                )
                self.add_chapter(meta)
                recovered += 1

            except Exception as exc:
                errors.append(f"ch{md_file.name}: {exc}")

        detail = f"recovered {recovered} chapters"
        if errors:
            detail += f", {len(errors)} errors: {'; '.join(errors[:5])}"

        return {
            "ok": recovered > 0 or not list(chapters_dir.glob("第*章*.md")),
            "chapters_recovered": recovered,
            "detail": detail,
        }

    @staticmethod
    def list_backups(ink_dir: Path) -> list:
        """列出所有 index.db 备份文件。"""
        if not ink_dir.exists():
            return []
        backups = sorted(ink_dir.glob("index.db.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"path": str(p), "size": p.stat().st_size, "name": p.name} for p in backups]

    def restore_from_backup(self, backup_path: Path) -> bool:
        """
        从备份文件恢复 index.db。

        先备份当前损坏的库（如果存在），再用备份替换。
        """
        if not backup_path.exists():
            return False

        db_path = self.config.index_db

        # 备份当前损坏的文件
        if db_path.exists():
            corrupted_path = self.config.ink_dir / f"index.db.corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                import shutil
                shutil.move(str(db_path), str(corrupted_path))
            except OSError:
                pass

        # 复制备份到 index.db
        try:
            import shutil
            shutil.copy2(str(backup_path), str(db_path))
            # 验证恢复后的完整性
            check = self.check_integrity()
            return check["ok"]
        except (OSError, sqlite3.Error):
            return False

    # index.db schema 版本号，每次变更表结构时递增
    SCHEMA_VERSION = 1

    def _init_db(self):
        """初始化数据库表"""
        self.config.ensure_dirs()

        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Schema 元信息表（追踪 index.db 结构版本）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
                (str(self.SCHEMA_VERSION),),
            )

            # 章节表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
                    chapter INTEGER PRIMARY KEY,
                    title TEXT,
                    location TEXT,
                    word_count INTEGER,
                    characters TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 场景表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER,
                    scene_index INTEGER,
                    start_line INTEGER,
                    end_line INTEGER,
                    location TEXT,
                    summary TEXT,
                    characters TEXT,
                    UNIQUE(chapter, scene_index)
                )
            """)

            # 实体出场表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appearances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT,
                    chapter INTEGER,
                    mentions TEXT,
                    confidence REAL,
                    UNIQUE(entity_id, chapter)
                )
            """)

            # 创建索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_scenes_chapter ON scenes(chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_appearances_entity ON appearances(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_appearances_chapter ON appearances(chapter)"
            )

            # ==================== v5.1 引入表 ====================

            # 实体表 (替代 state.json 中的 entities_v3)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    tier TEXT DEFAULT '装饰',
                    desc TEXT,
                    current_json TEXT,
                    first_appearance INTEGER DEFAULT 0,
                    last_appearance INTEGER DEFAULT 0,
                    is_protagonist INTEGER DEFAULT 0,
                    is_archived INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 别名表 (替代 state.json 中的 alias_index，支持一对多)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    alias TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (alias, entity_id, entity_type)
                )
            """)

            # 状态变化表 (替代 state.json 中的 state_changes)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    field TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    reason TEXT,
                    chapter INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 关系表 (替代 state.json 中的 structured_relationships)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_entity TEXT NOT NULL,
                    to_entity TEXT NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    chapter INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(from_entity, to_entity, type),
                    FOREIGN KEY (from_entity) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (to_entity) REFERENCES entities(id) ON DELETE CASCADE
                )
            """)

            # v5.1 引入索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_tier ON entities(tier)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_protagonist ON entities(is_protagonist)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_aliases_entity ON aliases(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_changes_entity ON state_changes(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_changes_chapter ON state_changes(chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_entity)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_entity)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationships_chapter ON relationships(chapter)"
            )

            # 关系事件表 (v5.5 引入，用于时序回放/图谱分析)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationship_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_entity TEXT NOT NULL,
                    to_entity TEXT NOT NULL,
                    type TEXT NOT NULL,
                    action TEXT NOT NULL DEFAULT 'update',
                    polarity INTEGER DEFAULT 0,
                    strength REAL DEFAULT 0.5,
                    description TEXT,
                    chapter INTEGER NOT NULL,
                    scene_index INTEGER DEFAULT 0,
                    evidence TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationship_events_from_chapter ON relationship_events(from_entity, chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationship_events_to_chapter ON relationship_events(to_entity, chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationship_events_chapter ON relationship_events(chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationship_events_type_chapter ON relationship_events(type, chapter)"
            )

            # ==================== v5.3 引入表：追读力债务管理 ====================

            # Override Contract 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS override_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    constraint_type TEXT NOT NULL,
                    constraint_id TEXT NOT NULL,
                    rationale_type TEXT NOT NULL,
                    rationale_text TEXT,
                    payback_plan TEXT,
                    due_chapter INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fulfilled_at TIMESTAMP,
                    UNIQUE(chapter, constraint_type, constraint_id)
                )
            """)

            # 追读力债务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chase_debt (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    debt_type TEXT NOT NULL,
                    original_amount REAL DEFAULT 1.0,
                    current_amount REAL DEFAULT 1.0,
                    interest_rate REAL DEFAULT 0.1,
                    source_chapter INTEGER NOT NULL,
                    due_chapter INTEGER NOT NULL,
                    override_contract_id INTEGER,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (override_contract_id) REFERENCES override_contracts(id)
                )
            """)

            # 债务事件日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS debt_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    debt_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    chapter INTEGER NOT NULL,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (debt_id) REFERENCES chase_debt(id)
                )
            """)

            # 章节追读力元数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_reading_power (
                    chapter INTEGER PRIMARY KEY,
                    hook_type TEXT,
                    hook_strength TEXT DEFAULT 'medium',
                    coolpoint_patterns TEXT,
                    micropayoffs TEXT,
                    hard_violations TEXT,
                    soft_suggestions TEXT,
                    is_transition INTEGER DEFAULT 0,
                    override_count INTEGER DEFAULT 0,
                    debt_balance REAL DEFAULT 0.0,
                    notes TEXT,
                    payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # v5.3 引入索引
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_override_contracts_chapter ON override_contracts(chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_override_contracts_status ON override_contracts(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_override_contracts_due ON override_contracts(due_chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chase_debt_status ON chase_debt(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chase_debt_source ON chase_debt(source_chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chase_debt_due ON chase_debt(due_chapter)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_debt_events_debt ON debt_events(debt_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_debt_events_chapter ON debt_events(chapter)"
            )

            # ==================== v5.4 新增表：无效事实与日志 ====================

            # 无效事实表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invalid_facts (
                    id INTEGER PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    marked_by TEXT NOT NULL,
                    marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    chapter_discovered INTEGER
                )
            """)

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_invalid_status ON invalid_facts(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_invalid_source ON invalid_facts(source_type, source_id)"
            )

            # 审查指标表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_metrics (
                    start_chapter INTEGER NOT NULL,
                    end_chapter INTEGER NOT NULL,
                    overall_score REAL DEFAULT 0,
                    dimension_scores TEXT,
                    severity_counts TEXT,
                    critical_issues TEXT,
                    report_file TEXT,
                    notes TEXT,
                    review_payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (start_chapter, end_chapter)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_review_metrics_end ON review_metrics(end_chapter)"
            )

            # 章节记忆卡
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_memory_cards (
                    chapter INTEGER PRIMARY KEY,
                    summary TEXT,
                    goal TEXT,
                    conflict TEXT,
                    result TEXT,
                    next_chapter_bridge TEXT,
                    unresolved_questions TEXT,
                    key_facts TEXT,
                    involved_entities TEXT,
                    plot_progress TEXT,
                    payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_cards_updated ON chapter_memory_cards(updated_at)"
            )

            # 剧情线程注册表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plot_thread_registry (
                    thread_id TEXT PRIMARY KEY,
                    title TEXT,
                    content TEXT,
                    thread_type TEXT DEFAULT 'foreshadowing',
                    status TEXT DEFAULT 'active',
                    priority INTEGER DEFAULT 50,
                    planted_chapter INTEGER DEFAULT 0,
                    last_touched_chapter INTEGER DEFAULT 0,
                    target_payoff_chapter INTEGER DEFAULT 0,
                    resolved_chapter INTEGER DEFAULT 0,
                    related_entities TEXT,
                    notes TEXT,
                    confidence REAL DEFAULT 1.0,
                    payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_plot_thread_status_priority ON plot_thread_registry(status, priority DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_plot_thread_last_touched ON plot_thread_registry(last_touched_chapter DESC)"
            )

            # 时间锚点
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timeline_anchors (
                    chapter INTEGER PRIMARY KEY,
                    anchor_time TEXT,
                    relative_to_previous TEXT,
                    previous_time_delta TEXT,
                    countdown TEXT,
                    from_location TEXT,
                    to_location TEXT,
                    movement TEXT,
                    notes TEXT,
                    involved_entities TEXT,
                    payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timeline_anchor_updated ON timeline_anchors(updated_at)"
            )

            # 候选事实（低置信度，弱证据层）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS candidate_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    fact TEXT NOT NULL,
                    fact_key TEXT,
                    entity_id TEXT,
                    confidence REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'candidate',
                    source TEXT DEFAULT 'data_agent',
                    evidence TEXT,
                    related_entities TEXT,
                    payload_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter, fact, entity_id, source)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_candidate_facts_chapter ON candidate_facts(chapter DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_candidate_facts_entity ON candidate_facts(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_candidate_facts_status ON candidate_facts(status)"
            )

            # RAG 查询日志
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rag_query_log (
                    id INTEGER PRIMARY KEY,
                    query TEXT,
                    query_type TEXT,
                    results_count INTEGER,
                    hit_sources TEXT,
                    latency_ms INTEGER,
                    chapter INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_query_type ON rag_query_log(query_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_query_chapter ON rag_query_log(chapter)"
            )

            # 工具调用统计
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_call_stats (
                    id INTEGER PRIMARY KEY,
                    tool_name TEXT,
                    success BOOLEAN,
                    retry_count INTEGER DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    chapter INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_stats_name ON tool_call_stats(tool_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_stats_chapter ON tool_call_stats(chapter)"
            )

            # 写作清单评分记录（Phase F）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS writing_checklist_scores (
                    chapter INTEGER PRIMARY KEY,
                    template TEXT DEFAULT 'plot',
                    total_items INTEGER DEFAULT 0,
                    required_items INTEGER DEFAULT 0,
                    completed_items INTEGER DEFAULT 0,
                    completed_required INTEGER DEFAULT 0,
                    total_weight REAL DEFAULT 0,
                    completed_weight REAL DEFAULT 0,
                    completion_rate REAL DEFAULT 0,
                    score REAL DEFAULT 0,
                    score_breakdown TEXT,
                    pending_items TEXT,
                    source TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_checklist_score_value ON writing_checklist_scores(score)"
            )

            # 叙事承诺表（P0-3 引入）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS narrative_commitments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    commitment_type TEXT NOT NULL,
                    entity_id TEXT,
                    content TEXT NOT NULL,
                    context_snippet TEXT,
                    scope TEXT DEFAULT 'permanent',
                    condition TEXT,
                    resolved_chapter INTEGER,
                    resolution_type TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_nc_entity ON narrative_commitments(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_nc_active ON narrative_commitments(resolved_chapter) WHERE resolved_chapter IS NULL"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_nc_chapter ON narrative_commitments(chapter)"
            )

            # v6.4 引入: 角色演变账本
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS character_evolution_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    chapter INTEGER NOT NULL,
                    arc_phase TEXT,
                    personality_delta TEXT,
                    voice_sample TEXT,
                    motivation_shift TEXT,
                    relationship_shifts TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(entity_id, chapter)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cel_entity ON character_evolution_ledger(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cel_chapter ON character_evolution_ledger(chapter)"
            )

            self._ensure_column(cursor, "chapter_reading_power", "notes", "TEXT")
            self._ensure_column(cursor, "chapter_reading_power", "payload_json", "TEXT")
            self._ensure_column(cursor, "review_metrics", "review_payload_json", "TEXT")
            # v6.4 引入: 伏笔氛围快照
            self._ensure_column(cursor, "plot_thread_registry", "atmospheric_snapshot", "TEXT")
            # v6.4 引入: 主题呈现追踪
            self._ensure_column(cursor, "chapter_memory_cards", "theme_presence", "TEXT DEFAULT '[]'")

            # v6.4 引入: 冲突结构指纹
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plot_structure_fingerprints (
                    chapter INTEGER PRIMARY KEY,
                    conflict_type TEXT,
                    resolution_mechanism TEXT,
                    twist_type TEXT,
                    emotional_arc TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # v6.4 引入: 卷元数据
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS volume_metadata (
                    volume_id INTEGER PRIMARY KEY,
                    title TEXT,
                    start_chapter INTEGER NOT NULL,
                    end_chapter INTEGER,
                    arc_summary TEXT,
                    themes TEXT DEFAULT '[]',
                    resolution_status TEXT DEFAULT 'in_progress',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # v8.2 引入: 主角视角知识管理（Knowledge Gate）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS protagonist_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    knowledge_type TEXT NOT NULL,
                    knowledge_value TEXT NOT NULL,
                    chapter_learned INTEGER,
                    how_learned TEXT,
                    known_descriptor TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
                    UNIQUE (entity_id, knowledge_type)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_protagonist_knowledge_entity ON protagonist_knowledge(entity_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_protagonist_knowledge_learned ON protagonist_knowledge(chapter_learned)"
            )

            # ==================== v9.0 引入表：Harness Engineering ====================

            # Reader Verdict 评分历史
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS harness_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    hook_strength REAL,
                    curiosity_continuation REAL,
                    emotional_reward REAL,
                    protagonist_pull REAL,
                    cliffhanger_drive REAL,
                    filler_risk REAL,
                    repetition_risk REAL,
                    total REAL,
                    verdict TEXT,
                    review_depth TEXT DEFAULT 'core',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_harness_eval_chapter ON harness_evaluations(chapter)"
            )

            # 计算型闸门日志
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS computational_gate_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter INTEGER NOT NULL,
                    gate_pass INTEGER NOT NULL DEFAULT 1,
                    checks_run INTEGER,
                    checks_passed INTEGER,
                    hard_failures TEXT,
                    soft_warnings TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_comp_gate_chapter ON computational_gate_log(chapter)"
            )

            conn.commit()

    @contextmanager
    def _get_conn(self, immediate: bool = False):
        """获取数据库连接。immediate=True 时使用 BEGIN IMMEDIATE 事务。"""
        conn = sqlite3.connect(str(self.config.index_db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            if immediate:
                conn.commit()
        except Exception:
            if immediate:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            conn.close()

    @contextmanager
    def _write_transaction(self):
        """Wrap write operations in BEGIN IMMEDIATE transaction with retry-on-busy.

        Usage::

            with self._write_transaction() as conn:
                conn.execute("INSERT ...")
                # commit is called automatically on success
        """
        with self._get_conn() as conn:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    yield conn
                    conn.commit()
                    return
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        time.sleep(0.1 * (attempt + 1))
                    else:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        raise

    def _ensure_column(self, cursor, table_name: str, column_name: str, column_def: str) -> None:
        """为旧库追加缺失列。"""
        try:
            rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.OperationalError:
            return

        existing = {str(row[1]) for row in rows if len(row) > 1}
        if column_name in existing:
            return

        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    # ==================== 章节操作 ====================

    # ==================== 叙事承诺操作 ====================

    def save_narrative_commitment(self, data: Dict[str, Any]) -> int:
        """Save a narrative commitment record."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO narrative_commitments
                   (chapter, commitment_type, entity_id, content, context_snippet, scope, condition)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("chapter"),
                    data.get("commitment_type", "promise"),
                    data.get("entity_id"),
                    data.get("content", ""),
                    data.get("context_snippet"),
                    data.get("scope", "permanent"),
                    data.get("condition"),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)

    def resolve_narrative_commitment(self, commitment_id: int, chapter: int, resolution_type: str = "fulfilled"):
        """Mark a narrative commitment as resolved."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE narrative_commitments
                   SET resolved_chapter = ?, resolution_type = ?
                   WHERE id = ?""",
                (chapter, resolution_type, commitment_id),
            )
            conn.commit()

    def get_active_commitments(self, entity_ids: list = None) -> list:
        """Get all active (unresolved) narrative commitments, optionally filtered by entity."""
        with self._get_conn() as conn:
            if entity_ids:
                placeholders = ",".join("?" for _ in entity_ids)
                rows = conn.execute(
                    f"""SELECT id, chapter, commitment_type, entity_id, content,
                               context_snippet, scope, condition
                        FROM narrative_commitments
                        WHERE resolved_chapter IS NULL
                          AND (entity_id IN ({placeholders}) OR entity_id IS NULL)
                        ORDER BY chapter ASC""",
                    entity_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, chapter, commitment_type, entity_id, content,
                              context_snippet, scope, condition
                       FROM narrative_commitments
                       WHERE resolved_chapter IS NULL
                       ORDER BY chapter ASC""",
                ).fetchall()
            columns = ["id", "chapter", "commitment_type", "entity_id", "content",
                        "context_snippet", "scope", "condition"]
            return [dict(zip(columns, row)) for row in rows]

    def get_all_commitments(self, include_resolved: bool = True) -> list:
        """Get all narrative commitments."""
        with self._get_conn() as conn:
            if include_resolved:
                rows = conn.execute("SELECT * FROM narrative_commitments ORDER BY chapter ASC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM narrative_commitments WHERE resolved_chapter IS NULL ORDER BY chapter ASC").fetchall()
            return [dict(row) for row in rows]

    # ==================== 角色演变账本 ====================

    def save_character_evolution(self, data: Dict[str, Any]) -> int:
        """保存角色演变记录（UPSERT: 同entity同chapter覆盖）"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO character_evolution_ledger
                   (entity_id, chapter, arc_phase, personality_delta,
                    voice_sample, motivation_shift, relationship_shifts)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(entity_id, chapter) DO UPDATE SET
                    arc_phase = excluded.arc_phase,
                    personality_delta = excluded.personality_delta,
                    voice_sample = excluded.voice_sample,
                    motivation_shift = excluded.motivation_shift,
                    relationship_shifts = excluded.relationship_shifts""",
                (
                    data.get("entity_id"),
                    data.get("chapter"),
                    data.get("arc_phase"),
                    data.get("personality_delta"),
                    data.get("voice_sample"),
                    data.get("motivation_shift"),
                    data.get("relationship_shifts"),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_character_evolution(self, entity_id: str, limit: int = 50) -> list:
        """获取角色的演变轨迹，按章节升序"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT chapter, arc_phase, personality_delta,
                          voice_sample, motivation_shift, relationship_shifts
                   FROM character_evolution_ledger
                   WHERE entity_id = ?
                   ORDER BY chapter ASC
                   LIMIT ?""",
                (entity_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_characters_evolution_summary(self, entity_ids: list, max_entries_per_char: int = 10) -> Dict[str, list]:
        """批量获取多个角色的演变摘要（单次SQL查询，避免N+1）"""
        if not entity_ids:
            return {}
        result: Dict[str, list] = {}
        try:
            with self._get_conn() as conn:
                placeholders = ",".join("?" for _ in entity_ids)
                rows = conn.execute(
                    f"""SELECT entity_id, chapter, arc_phase, personality_delta,
                               voice_sample, motivation_shift, relationship_shifts
                        FROM character_evolution_ledger
                        WHERE entity_id IN ({placeholders})
                        ORDER BY entity_id, chapter ASC""",
                    entity_ids,
                ).fetchall()
                for row in rows:
                    row_dict = dict(row)
                    eid = row_dict.get("entity_id")
                    if eid:
                        result.setdefault(eid, [])
                        if len(result[eid]) < max_entries_per_char:
                            result[eid].append(row_dict)
        except Exception:
            # 回退到逐个查询
            for eid in entity_ids:
                entries = self.get_character_evolution(eid, limit=max_entries_per_char)
                if entries:
                    result[eid] = entries
        return result

    def get_relationship_events_batch(self, entity_ids: list, limit_per_entity: int = 20) -> Dict[str, list]:
        """批量获取多个角色的关系事件（单次SQL查询，避免N+1）"""
        if not entity_ids:
            return {}
        result: Dict[str, list] = {}
        try:
            with self._get_conn() as conn:
                placeholders = ",".join("?" for _ in entity_ids)
                params = entity_ids + entity_ids  # for from_entity IN + to_entity IN
                rows = conn.execute(
                    f"""SELECT from_entity, to_entity, type, polarity, chapter
                        FROM relationship_events
                        WHERE from_entity IN ({placeholders}) OR to_entity IN ({placeholders})
                        ORDER BY chapter DESC
                        LIMIT ?""",
                    params + [limit_per_entity * len(entity_ids)],
                ).fetchall()
                for row in rows:
                    row_dict = dict(row)
                    from_e = row_dict.get("from_entity", "")
                    to_e = row_dict.get("to_entity", "")
                    for eid in entity_ids:
                        if eid == from_e or eid == to_e:
                            result.setdefault(eid, []).append(row_dict)
        except Exception:
            pass
        return result

    # ==================== 冲突结构指纹 ====================

    def save_plot_structure_fingerprint(self, data: Dict[str, Any]):
        """保存章节冲突结构指纹（UPSERT）"""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO plot_structure_fingerprints
                   (chapter, conflict_type, resolution_mechanism, twist_type, emotional_arc)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(chapter) DO UPDATE SET
                    conflict_type = excluded.conflict_type,
                    resolution_mechanism = excluded.resolution_mechanism,
                    twist_type = excluded.twist_type,
                    emotional_arc = excluded.emotional_arc""",
                (
                    data.get("chapter"),
                    data.get("conflict_type"),
                    data.get("resolution_mechanism"),
                    data.get("twist_type"),
                    data.get("emotional_arc"),
                ),
            )
            conn.commit()

    def get_recent_fingerprints(self, limit: int = 50, before_chapter: int = 9999) -> list:
        """获取最近的结构指纹用于去重检测"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT chapter, conflict_type, resolution_mechanism, twist_type, emotional_arc
                   FROM plot_structure_fingerprints
                   WHERE chapter < ?
                   ORDER BY chapter DESC
                   LIMIT ?""",
                (before_chapter, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_fingerprint_pattern_counts(self, limit: int = 50, before_chapter: int = 9999) -> list:
        """统计最近N章中各冲突模式组合的出现次数"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT conflict_type, resolution_mechanism, COUNT(*) as count
                   FROM plot_structure_fingerprints
                   WHERE chapter < ? AND chapter >= ? - ?
                   GROUP BY conflict_type, resolution_mechanism
                   HAVING COUNT(*) >= 3
                   ORDER BY count DESC""",
                (before_chapter, before_chapter, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    # ==================== 卷元数据 ====================

    def save_volume_metadata(self, data: Dict[str, Any]):
        """保存卷元数据（UPSERT）"""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO volume_metadata
                   (volume_id, title, start_chapter, end_chapter, arc_summary, themes, resolution_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(volume_id) DO UPDATE SET
                    title = excluded.title,
                    end_chapter = excluded.end_chapter,
                    arc_summary = excluded.arc_summary,
                    themes = excluded.themes,
                    resolution_status = excluded.resolution_status,
                    updated_at = datetime('now')""",
                (
                    data.get("volume_id"),
                    data.get("title"),
                    data.get("start_chapter"),
                    data.get("end_chapter"),
                    data.get("arc_summary"),
                    data.get("themes", "[]"),
                    data.get("resolution_status", "in_progress"),
                ),
            )
            conn.commit()

    def get_volume_metadata(self, volume_id: int = None) -> list:
        """获取卷元数据"""
        with self._get_conn() as conn:
            if volume_id is not None:
                rows = conn.execute(
                    "SELECT * FROM volume_metadata WHERE volume_id = ?", (volume_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM volume_metadata ORDER BY volume_id ASC"
                ).fetchall()
            return [dict(row) for row in rows]

    def get_volume_for_chapter(self, chapter: int) -> Optional[Dict[str, Any]]:
        """获取某章节所属的卷"""
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT * FROM volume_metadata
                   WHERE start_chapter <= ? AND (end_chapter IS NULL OR end_chapter >= ?)
                   ORDER BY volume_id DESC LIMIT 1""",
                (chapter, chapter),
            ).fetchone()
            return dict(row) if row else None

    # ==================== 故事骨架采样 ====================

    def get_top_reading_power_chapters(self, limit: int = 5, before_chapter: int = 9999) -> list:
        """获取reading_power评分最高的章节（用于故事骨架智能采样）"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT chapter, hook_type, hook_strength
                   FROM chapter_reading_power
                   WHERE chapter < ?
                     AND hook_strength = 'strong'
                   ORDER BY chapter DESC
                   LIMIT ?""",
                (before_chapter, limit),
            ).fetchall()
            if rows:
                return [dict(row) for row in rows]
            # 回退: 如果没有strong hook的章，取最近的
            rows = conn.execute(
                """SELECT chapter, hook_type, hook_strength
                   FROM chapter_reading_power
                   WHERE chapter < ?
                   ORDER BY chapter DESC
                   LIMIT ?""",
                (before_chapter, limit),
            ).fetchall()
            return [dict(row) for row in rows]

# ==================== CLI 命令处理函数 ====================


def _handle_stats(manager, args, emit_success, emit_error):
    emit_success(manager.get_stats(), message="stats")


def _handle_get_chapter(manager, args, emit_success, emit_error):
    chapter = manager.get_chapter(args.chapter)
    if chapter:
        emit_success(chapter, message="chapter")
    else:
        emit_error("NOT_FOUND", f"未找到章节: {args.chapter}")


def _handle_recent_appearances(manager, args, emit_success, emit_error):
    emit_success(manager.get_recent_appearances(args.limit), message="recent_appearances")


def _handle_entity_appearances(manager, args, emit_success, emit_error):
    appearances = manager.get_entity_appearances(args.entity, args.limit)
    emit_success({"entity": args.entity, "appearances": appearances}, message="entity_appearances")


def _handle_search_scenes(manager, args, emit_success, emit_error):
    scenes = manager.search_scenes_by_location(args.location, args.limit)
    emit_success(scenes, message="scenes")


def _handle_process_chapter(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    entities = load_json_arg(args.entities)
    scenes = load_json_arg(args.scenes)
    stats = manager.process_chapter_data(
        chapter=args.chapter, title=args.title, location=args.location,
        word_count=args.word_count, entities=entities, scenes=scenes,
    )
    emit_success(stats, message="chapter_processed", chapter=args.chapter)


def _handle_get_entity(manager, args, emit_success, emit_error):
    entity = manager.get_entity(args.id)
    if entity:
        emit_success(entity, message="entity")
    else:
        emit_error("NOT_FOUND", f"未找到实体: {args.id}")


def _handle_get_core_entities(manager, args, emit_success, emit_error):
    emit_success(manager.get_core_entities(), message="core_entities")


def _handle_get_protagonist(manager, args, emit_success, emit_error):
    protagonist = manager.get_protagonist()
    if protagonist:
        emit_success(protagonist, message="protagonist")
    else:
        emit_error("NOT_FOUND", "未设置主角")


def _handle_get_entities_by_type(manager, args, emit_success, emit_error):
    emit_success(manager.get_entities_by_type(args.type, args.include_archived), message="entities_by_type")


def _handle_get_by_alias(manager, args, emit_success, emit_error):
    entities = manager.get_entities_by_alias(args.alias)
    if entities:
        emit_success(entities, message="entities_by_alias")
    else:
        emit_error("NOT_FOUND", f"未找到别名: {args.alias}")


def _handle_get_aliases(manager, args, emit_success, emit_error):
    aliases = manager.get_entity_aliases(args.entity)
    if aliases:
        emit_success({"entity": args.entity, "aliases": aliases}, message="aliases")
    else:
        emit_error("NOT_FOUND", f"{args.entity} 没有别名")


def _handle_register_alias(manager, args, emit_success, emit_error):
    success = manager.register_alias(args.alias, args.entity, args.type)
    if success:
        emit_success({"alias": args.alias, "entity": args.entity, "type": args.type}, message="alias_registered")
    else:
        emit_error("ALIAS_EXISTS", f"别名已存在或注册失败: {args.alias}")


def _handle_get_relationships(manager, args, emit_success, emit_error):
    rels = manager.get_entity_relationships(args.entity, args.direction)
    emit_success(rels, message="relationships")


def _handle_get_relationship_events(manager, args, emit_success, emit_error):
    events = manager.get_relationship_events(
        entity_id=args.entity, direction=args.direction,
        from_chapter=args.from_chapter, to_chapter=args.to_chapter, limit=args.limit,
    )
    emit_success(events, message="relationship_events")


def _handle_get_relationship_graph(manager, args, emit_success, emit_error):
    graph = manager.build_relationship_subgraph(
        center_entity=args.center, depth=args.depth,
        chapter=args.chapter, top_edges=args.top_edges,
    )
    if args.format == "mermaid":
        emit_success({"mermaid": manager.render_relationship_subgraph_mermaid(graph)}, message="relationship_graph")
    else:
        emit_success(graph, message="relationship_graph")


def _handle_get_relationship_timeline(manager, args, emit_success, emit_error):
    timeline = manager.get_relationship_timeline(
        entity1=args.a, entity2=args.b,
        from_chapter=args.from_chapter, to_chapter=args.to_chapter, limit=args.limit,
    )
    emit_success(timeline, message="relationship_timeline")


def _handle_get_state_changes(manager, args, emit_success, emit_error):
    emit_success(manager.get_entity_state_changes(args.entity, args.limit), message="state_changes")


def _handle_record_relationship_event(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    try:
        data = load_json_arg(args.data)
    except (TypeError, ValueError, json.JSONDecodeError):
        emit_error("INVALID_RELATIONSHIP_EVENT", "关系事件 JSON 无效")
        return
    event = RelationshipEventMeta(
        from_entity=data.get("from_entity", ""), to_entity=data.get("to_entity", ""),
        type=data.get("type", ""), chapter=data.get("chapter", 0),
        action=data.get("action", "update"), polarity=data.get("polarity", 0),
        strength=data.get("strength", 0.5), description=data.get("description", ""),
        scene_index=data.get("scene_index", 0), evidence=data.get("evidence", ""),
        confidence=data.get("confidence", 1.0),
    )
    event_id = manager.record_relationship_event(event)
    if event_id > 0:
        emit_success({"id": event_id}, message="relationship_event_recorded")
    else:
        emit_error("INVALID_RELATIONSHIP_EVENT", "关系事件参数无效，未写入")


def _handle_upsert_entity(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    entity = EntityMeta(
        id=data["id"], type=data["type"], canonical_name=data["canonical_name"],
        tier=data.get("tier", "装饰"), desc=data.get("desc", ""),
        current=data.get("current", {}),
        first_appearance=data.get("first_appearance", 0),
        last_appearance=data.get("last_appearance", 0),
        is_protagonist=data.get("is_protagonist", False),
        is_archived=data.get("is_archived", False),
    )
    is_new = manager.upsert_entity(entity)
    emit_success({"id": entity.id, "created": is_new}, message="entity_upserted")


def _handle_upsert_relationship(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    rel = RelationshipMeta(
        from_entity=data["from_entity"], to_entity=data["to_entity"],
        type=data["type"], description=data.get("description", ""), chapter=data["chapter"],
    )
    is_new = manager.upsert_relationship(rel)
    emit_success(
        {"from": rel.from_entity, "to": rel.to_entity, "type": rel.type, "created": is_new},
        message="relationship_upserted",
    )


def _handle_record_state_change(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    change = StateChangeMeta(
        entity_id=data["entity_id"], field=data["field"],
        old_value=data.get("old_value", ""), new_value=data["new_value"],
        reason=data.get("reason", ""), chapter=data["chapter"],
    )
    record_id = manager.record_state_change(change)
    emit_success({"id": record_id, "entity": change.entity_id, "field": change.field}, message="state_change_recorded")


def _handle_mark_invalid(manager, args, emit_success, emit_error):
    invalid_id = manager.mark_invalid_fact(
        args.source_type, args.source_id, args.reason,
        marked_by=args.marked_by, chapter_discovered=args.chapter,
    )
    emit_success({"id": invalid_id}, message="invalid_marked")


def _handle_resolve_invalid(manager, args, emit_success, emit_error):
    ok = manager.resolve_invalid_fact(args.id, args.action)
    if ok:
        emit_success({"id": args.id, "action": args.action}, message="invalid_resolved")
    else:
        emit_error("INVALID_ACTION", f"无法处理 action: {args.action}")


def _handle_list_invalid(manager, args, emit_success, emit_error):
    emit_success(manager.list_invalid_facts(args.status), message="invalid_list")


def _handle_save_review_metrics(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    metrics = ReviewMetrics(
        start_chapter=data["start_chapter"], end_chapter=data["end_chapter"],
        overall_score=data.get("overall_score", 0.0),
        dimension_scores=data.get("dimension_scores", {}),
        severity_counts=data.get("severity_counts", {}),
        critical_issues=data.get("critical_issues", []),
        report_file=data.get("report_file", ""),
        notes=data.get("notes", ""),
        review_payload_json=data.get("review_payload_json", {}),
    )
    manager.save_review_metrics(metrics)
    emit_success(
        {"start_chapter": metrics.start_chapter, "end_chapter": metrics.end_chapter},
        message="review_metrics_saved",
    )


def _handle_get_recent_review_metrics(manager, args, emit_success, emit_error):
    emit_success(manager.get_recent_review_metrics(args.limit), message="recent_review_metrics")


def _handle_get_review_trend_stats(manager, args, emit_success, emit_error):
    emit_success(manager.get_review_trend_stats(args.last_n), message="review_trend_stats")


def _handle_save_harness_evaluation(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    chapter = data.get("chapter", 0)
    verdict = data.get("reader_verdict", data)
    review_depth = data.get("review_depth", "core")
    try:
        with manager._get_conn() as conn:
            conn.execute(
                """INSERT INTO harness_evaluations
                   (chapter, hook_strength, curiosity_continuation, emotional_reward,
                    protagonist_pull, cliffhanger_drive, filler_risk, repetition_risk,
                    total, verdict, review_depth)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chapter, verdict.get("hook_strength"), verdict.get("curiosity_continuation"),
                    verdict.get("emotional_reward"), verdict.get("protagonist_pull"),
                    verdict.get("cliffhanger_drive"), verdict.get("filler_risk"),
                    verdict.get("repetition_risk"), verdict.get("total"),
                    verdict.get("verdict"), review_depth,
                ),
            )
            conn.commit()
        emit_success({"chapter": chapter, "verdict": verdict.get("verdict")}, message="harness_evaluation_saved")
    except sqlite3.Error as e:
        emit_error("SAVE_FAILED", f"保存 harness evaluation 失败: {e}")


def _handle_get_review_trends(manager, args, emit_success, emit_error):
    start_ch, end_ch, fmt = args.start, args.end, args.format
    records = manager.get_recent_review_metrics(end_ch - start_ch + 1)
    in_range = [r for r in records if start_ch <= r.get("end_chapter", 0) <= end_ch]

    try:
        active_threads = manager.get_active_plot_threads(limit=100)
        overdue = [t for t in active_threads if t.get("status") == "overdue"]
    except (sqlite3.Error, KeyError, TypeError):
        active_threads = []
        overdue = []

    if fmt == "json":
        result = {
            "review_scores": [{"chapter": r.get("end_chapter"), "score": r.get("overall_score")} for r in in_range],
            "avg_score": sum(r.get("overall_score", 0) for r in in_range) / max(len(in_range), 1),
            "active_threads": len(active_threads),
            "overdue_threads": len(overdue),
        }
        emit_success(result, message="review_trends")
    elif fmt == "markdown":
        lines = []
        if in_range:
            scores = [r.get("overall_score", 0) for r in in_range]
            avg = sum(scores) / len(scores)
            trend = "↑" if len(scores) > 1 and scores[-1] > scores[0] else ("↓" if len(scores) > 1 and scores[-1] < scores[0] else "→")
            lines.append(f"- 平均审查分：{avg:.1f}/100 {trend}")
        if active_threads:
            lines.append(f"- 活跃伏笔：{len(active_threads)} 条")
        if overdue:
            lines.append(f"- 逾期伏笔：{len(overdue)} 条")
        print("\n".join(lines) if lines else "暂无趋势数据")
    else:
        if in_range:
            scores = [r.get("overall_score", 0) for r in in_range]
            avg = sum(scores) / len(scores)
            trend = "↑" if len(scores) > 1 and scores[-1] > scores[0] else ("↓" if len(scores) > 1 and scores[-1] < scores[0] else "→")
            print(f"  追读力信号：")
            print(f"  ├─ 平均审查分：{avg:.1f}/100 {trend}")
        if active_threads:
            print(f"  ├─ 活跃伏笔：{len(active_threads)} 条")
        if overdue:
            print(f"  └─ 逾期伏笔：{len(overdue)} 条 ⚠️")


def _handle_save_writing_checklist_score(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    metrics = WritingChecklistScoreMeta(
        chapter=data["chapter"], template=data.get("template", "plot"),
        total_items=data.get("total_items", 0), required_items=data.get("required_items", 0),
        completed_items=data.get("completed_items", 0),
        completed_required=data.get("completed_required", 0),
        total_weight=data.get("total_weight", 0.0),
        completed_weight=data.get("completed_weight", 0.0),
        completion_rate=data.get("completion_rate", 0.0),
        score=data.get("score", 0.0),
        score_breakdown=data.get("score_breakdown", {}),
        pending_items=data.get("pending_items", []),
        source=data.get("source", "context_manager"),
        notes=data.get("notes", ""),
    )
    manager.save_writing_checklist_score(metrics)
    emit_success({"chapter": metrics.chapter, "score": metrics.score}, message="writing_checklist_score_saved")


def _handle_get_writing_checklist_score(manager, args, emit_success, emit_error):
    score = manager.get_writing_checklist_score(args.chapter)
    if score:
        emit_success(score, message="writing_checklist_score")
    else:
        emit_error("NOT_FOUND", f"未找到第 {args.chapter} 章的写作清单评分")


def _handle_get_recent_writing_checklist_scores(manager, args, emit_success, emit_error):
    emit_success(manager.get_recent_writing_checklist_scores(args.limit), message="recent_writing_checklist_scores")


def _handle_get_writing_checklist_score_trend(manager, args, emit_success, emit_error):
    emit_success(manager.get_writing_checklist_score_trend(args.last_n), message="writing_checklist_score_trend")


def _handle_get_debt_summary(manager, args, emit_success, emit_error):
    emit_success(manager.get_debt_summary(), message="debt_summary")


def _handle_get_recent_reading_power(manager, args, emit_success, emit_error):
    emit_success(manager.get_recent_reading_power(args.limit), message="recent_reading_power")


def _handle_get_chapter_reading_power(manager, args, emit_success, emit_error):
    record = manager.get_chapter_reading_power(args.chapter)
    if record:
        emit_success(record, message="chapter_reading_power")
    else:
        emit_error("NOT_FOUND", f"未找到第 {args.chapter} 章的追读力元数据")


def _handle_get_pattern_usage_stats(manager, args, emit_success, emit_error):
    emit_success(manager.get_pattern_usage_stats(args.last_n), message="pattern_usage_stats")


def _handle_get_hook_type_stats(manager, args, emit_success, emit_error):
    emit_success(manager.get_hook_type_stats(args.last_n), message="hook_type_stats")


def _handle_get_pending_overrides(manager, args, emit_success, emit_error):
    emit_success(manager.get_pending_overrides(args.before_chapter), message="pending_overrides")


def _handle_get_overdue_overrides(manager, args, emit_success, emit_error):
    emit_success(manager.get_overdue_overrides(args.current_chapter), message="overdue_overrides")


def _handle_get_active_debts(manager, args, emit_success, emit_error):
    emit_success(manager.get_active_debts(), message="active_debts")


def _handle_get_overdue_debts(manager, args, emit_success, emit_error):
    emit_success(manager.get_overdue_debts(args.current_chapter), message="overdue_debts")


def _handle_accrue_interest(manager, args, emit_success, emit_error):
    result = manager.accrue_interest(args.current_chapter)
    emit_success(result, message="interest_accrued", chapter=args.current_chapter)


def _handle_pay_debt(manager, args, emit_success, emit_error):
    result = manager.pay_debt(args.debt_id, args.amount, args.chapter)
    if "error" in result:
        emit_error("PAY_DEBT_FAILED", result["error"], chapter=args.chapter)
    else:
        emit_success(result, message="debt_payment", chapter=args.chapter)


def _handle_create_override_contract(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    contract = OverrideContractMeta(
        chapter=data["chapter"], constraint_type=data["constraint_type"],
        constraint_id=data["constraint_id"], rationale_type=data["rationale_type"],
        rationale_text=data.get("rationale_text", ""),
        payback_plan=data.get("payback_plan", ""),
        due_chapter=data["due_chapter"], status=data.get("status", "pending"),
    )
    emit_success({"id": manager.create_override_contract(contract)}, message="override_contract_created")


def _handle_create_debt(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    debt = ChaseDebtMeta(
        debt_type=data["debt_type"],
        original_amount=data.get("original_amount", 1.0),
        current_amount=data.get("current_amount", data.get("original_amount", 1.0)),
        interest_rate=data.get("interest_rate", 0.1),
        source_chapter=data["source_chapter"], due_chapter=data["due_chapter"],
        override_contract_id=data.get("override_contract_id", 0),
        status=data.get("status", "active"),
    )
    emit_success({"id": manager.create_debt(debt), "debt_type": debt.debt_type}, message="debt_created")


def _handle_fulfill_override(manager, args, emit_success, emit_error):
    success = manager.fulfill_override(args.contract_id)
    if success:
        emit_success({"id": args.contract_id}, message="override_fulfilled")
    else:
        emit_error("NOT_FOUND", f"未找到 Override Contract #{args.contract_id}")


def _handle_save_chapter_reading_power(manager, args, emit_success, emit_error):
    from .cli_args import load_json_arg
    data = load_json_arg(args.data)
    meta = ChapterReadingPowerMeta(
        chapter=data["chapter"], hook_type=data.get("hook_type", ""),
        hook_strength=data.get("hook_strength", "medium"),
        coolpoint_patterns=data.get("coolpoint_patterns", []),
        micropayoffs=data.get("micropayoffs", []),
        hard_violations=data.get("hard_violations", []),
        soft_suggestions=data.get("soft_suggestions", []),
        is_transition=data.get("is_transition", False),
        override_count=data.get("override_count", 0),
        debt_balance=data.get("debt_balance", 0.0),
        notes=data.get("notes", ""), payload_json=data.get("payload_json", {}),
    )
    manager.save_chapter_reading_power(meta)
    emit_success({"chapter": meta.chapter}, message="reading_power_saved")


# ==================== CLI 接口 ====================


def main():
    import argparse
    import sys
    from .cli_output import print_success, print_error
    from .cli_args import normalize_global_project_root

    parser = argparse.ArgumentParser(description="Index Manager CLI (v5.4)")
    parser.add_argument("--project-root", type=str, help="项目根目录")

    subparsers = parser.add_subparsers(dest="command")

    # 获取统计
    subparsers.add_parser("stats")

    # 查询章节
    chapter_parser = subparsers.add_parser("get-chapter")
    chapter_parser.add_argument("--chapter", type=int, required=True)

    # 查询最近出场
    recent_parser = subparsers.add_parser("recent-appearances")
    recent_parser.add_argument("--limit", type=int, default=None)

    # 查询实体出场
    entity_parser = subparsers.add_parser("entity-appearances")
    entity_parser.add_argument("--entity", required=True)
    entity_parser.add_argument("--limit", type=int, default=None)

    # 搜索场景
    search_parser = subparsers.add_parser("search-scenes")
    search_parser.add_argument("--location", required=True)
    search_parser.add_argument("--limit", type=int, default=None)

    # 处理章节数据 (写入)
    process_parser = subparsers.add_parser("process-chapter")
    process_parser.add_argument("--chapter", type=int, required=True)
    process_parser.add_argument("--title", required=True)
    process_parser.add_argument("--location", required=True)
    process_parser.add_argument("--word-count", type=int, required=True)
    process_parser.add_argument("--entities", required=True, help="JSON 格式的实体列表")
    process_parser.add_argument("--scenes", required=True, help="JSON 格式的场景列表")

    # ==================== v5.1 引入命令 ====================

    # 获取实体
    get_entity_parser = subparsers.add_parser("get-entity")
    get_entity_parser.add_argument("--id", required=True, help="实体 ID")

    # 获取核心实体
    subparsers.add_parser("get-core-entities")

    # 获取主角
    subparsers.add_parser("get-protagonist")

    # 按类型获取实体
    type_parser = subparsers.add_parser("get-entities-by-type")
    type_parser.add_argument(
        "--type", required=True, help="实体类型 (角色/地点/物品/势力/招式)"
    )
    type_parser.add_argument("--include-archived", action="store_true")

    # 按别名查找实体
    alias_parser = subparsers.add_parser("get-by-alias")
    alias_parser.add_argument("--alias", required=True, help="别名")

    # 获取实体别名
    aliases_parser = subparsers.add_parser("get-aliases")
    aliases_parser.add_argument("--entity", required=True, help="实体 ID")

    # 注册别名
    reg_alias_parser = subparsers.add_parser("register-alias")
    reg_alias_parser.add_argument("--alias", required=True)
    reg_alias_parser.add_argument("--entity", required=True)
    reg_alias_parser.add_argument("--type", required=True, help="实体类型")

    # 获取实体关系
    rel_parser = subparsers.add_parser("get-relationships")
    rel_parser.add_argument("--entity", required=True)
    rel_parser.add_argument(
        "--direction", choices=["from", "to", "both"], default="both"
    )

    # 获取关系事件
    rel_events_parser = subparsers.add_parser("get-relationship-events")
    rel_events_parser.add_argument("--entity", required=True)
    rel_events_parser.add_argument("--direction", choices=["from", "to", "both"], default="both")
    rel_events_parser.add_argument("--from-chapter", type=int, default=None)
    rel_events_parser.add_argument("--to-chapter", type=int, default=None)
    rel_events_parser.add_argument("--limit", type=int, default=100)

    # 获取关系图谱
    rel_graph_parser = subparsers.add_parser("get-relationship-graph")
    rel_graph_parser.add_argument("--center", required=True, help="中心实体 ID")
    rel_graph_parser.add_argument("--depth", type=int, default=2)
    rel_graph_parser.add_argument("--chapter", type=int, default=None)
    rel_graph_parser.add_argument("--top-edges", type=int, default=50)
    rel_graph_parser.add_argument("--format", choices=["json", "mermaid"], default="json")

    # 获取关系时间线
    rel_timeline_parser = subparsers.add_parser("get-relationship-timeline")
    rel_timeline_parser.add_argument("--a", required=True, help="实体 A")
    rel_timeline_parser.add_argument("--b", required=True, help="实体 B")
    rel_timeline_parser.add_argument("--from-chapter", type=int, default=None)
    rel_timeline_parser.add_argument("--to-chapter", type=int, default=None)
    rel_timeline_parser.add_argument("--limit", type=int, default=100)

    # 写入关系事件
    rel_event_record_parser = subparsers.add_parser("record-relationship-event")
    rel_event_record_parser.add_argument("--data", required=True, help="JSON 格式的关系事件数据")

    # 获取状态变化
    changes_parser = subparsers.add_parser("get-state-changes")
    changes_parser.add_argument("--entity", required=True)
    changes_parser.add_argument("--limit", type=int, default=20)

    # 写入实体
    upsert_entity_parser = subparsers.add_parser("upsert-entity")
    upsert_entity_parser.add_argument(
        "--data", required=True, help="JSON 格式的实体数据"
    )

    # 写入关系
    upsert_rel_parser = subparsers.add_parser("upsert-relationship")
    upsert_rel_parser.add_argument("--data", required=True, help="JSON 格式的关系数据")

    # 写入状态变化
    state_change_parser = subparsers.add_parser("record-state-change")
    state_change_parser.add_argument(
        "--data", required=True, help="JSON 格式的状态变化数据"
    )

    # ==================== v5.4 新增命令 ====================
    invalid_parser = subparsers.add_parser("mark-invalid")
    invalid_parser.add_argument("--source-type", required=True)
    invalid_parser.add_argument("--source-id", required=True)
    invalid_parser.add_argument("--reason", required=True)
    invalid_parser.add_argument("--marked-by", default="user")
    invalid_parser.add_argument("--chapter", type=int, default=None)

    resolve_parser = subparsers.add_parser("resolve-invalid")
    resolve_parser.add_argument("--id", type=int, required=True)
    resolve_parser.add_argument("--action", choices=["confirm", "dismiss"], required=True)

    list_invalid_parser = subparsers.add_parser("list-invalid")
    list_invalid_parser.add_argument("--status", choices=["pending", "confirmed"], default=None)

    review_save_parser = subparsers.add_parser("save-review-metrics")
    review_save_parser.add_argument("--data", required=True, help="JSON 格式的审查指标数据")

    review_recent_parser = subparsers.add_parser("get-recent-review-metrics")
    review_recent_parser.add_argument("--limit", type=int, default=5)

    review_trend_parser = subparsers.add_parser("get-review-trend-stats")
    review_trend_parser.add_argument("--last-n", type=int, default=5)

    # v9.0: harness evaluation (reader_verdict) 写入
    harness_eval_parser = subparsers.add_parser("save-harness-evaluation")
    harness_eval_parser.add_argument("--data", required=True, help="JSON: reader_verdict + chapter + review_depth")

    # v9.0: ink-auto 增强输出用
    review_trends_parser = subparsers.add_parser("get-review-trends")
    review_trends_parser.add_argument("--start", type=int, required=True, help="起始章节号")
    review_trends_parser.add_argument("--end", type=int, required=True, help="结束章节号")
    review_trends_parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")

    checklist_score_save_parser = subparsers.add_parser("save-writing-checklist-score")
    checklist_score_save_parser.add_argument("--data", required=True, help="JSON 格式的写作清单评分数据")

    checklist_score_get_parser = subparsers.add_parser("get-writing-checklist-score")
    checklist_score_get_parser.add_argument("--chapter", type=int, required=True)

    checklist_score_recent_parser = subparsers.add_parser("get-recent-writing-checklist-scores")
    checklist_score_recent_parser.add_argument("--limit", type=int, default=10)

    checklist_score_trend_parser = subparsers.add_parser("get-writing-checklist-score-trend")
    checklist_score_trend_parser.add_argument("--last-n", type=int, default=10)

    # ==================== v5.3 引入命令 ====================

    # 获取债务汇总
    subparsers.add_parser("get-debt-summary")

    # 获取最近章节追读力元数据
    reading_power_parser = subparsers.add_parser("get-recent-reading-power")
    reading_power_parser.add_argument("--limit", type=int, default=10)

    # 获取章节追读力元数据
    chapter_rp_parser = subparsers.add_parser("get-chapter-reading-power")
    chapter_rp_parser.add_argument("--chapter", type=int, required=True)

    # 获取爽点模式使用统计
    pattern_stats_parser = subparsers.add_parser("get-pattern-usage-stats")
    pattern_stats_parser.add_argument("--last-n", type=int, default=20)

    # 获取钩子类型使用统计
    hook_stats_parser = subparsers.add_parser("get-hook-type-stats")
    hook_stats_parser.add_argument("--last-n", type=int, default=20)

    # 获取待偿还Override
    pending_override_parser = subparsers.add_parser("get-pending-overrides")
    pending_override_parser.add_argument("--before-chapter", type=int, default=None)

    # 获取逾期Override
    overdue_override_parser = subparsers.add_parser("get-overdue-overrides")
    overdue_override_parser.add_argument("--current-chapter", type=int, required=True)

    # 获取活跃债务
    subparsers.add_parser("get-active-debts")

    # 获取逾期债务
    overdue_debt_parser = subparsers.add_parser("get-overdue-debts")
    overdue_debt_parser.add_argument("--current-chapter", type=int, required=True)

    # 计算利息
    accrue_parser = subparsers.add_parser("accrue-interest")
    accrue_parser.add_argument("--current-chapter", type=int, required=True)

    # 偿还债务
    pay_debt_parser = subparsers.add_parser("pay-debt")
    pay_debt_parser.add_argument("--debt-id", type=int, required=True)
    pay_debt_parser.add_argument("--amount", type=float, required=True)
    pay_debt_parser.add_argument("--chapter", type=int, required=True)

    # 创建Override Contract
    create_override_parser = subparsers.add_parser("create-override-contract")
    create_override_parser.add_argument(
        "--data", required=True, help="JSON 格式的Override Contract数据"
    )

    # 创建债务
    create_debt_parser = subparsers.add_parser("create-debt")
    create_debt_parser.add_argument("--data", required=True, help="JSON 格式的债务数据")

    # 标记Override已偿还
    fulfill_override_parser = subparsers.add_parser("fulfill-override")
    fulfill_override_parser.add_argument("--contract-id", type=int, required=True)

    # 保存章节追读力元数据
    save_rp_parser = subparsers.add_parser("save-chapter-reading-power")
    save_rp_parser.add_argument(
        "--data", required=True, help="JSON 格式的章节追读力元数据"
    )

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)
    command_started_at = time.perf_counter()

    # 初始化
    config = None
    if args.project_root:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .ink/state.json）
        from project_locator import resolve_project_root
        from .config import DataModulesConfig

        resolved_root = resolve_project_root(args.project_root)
        config = DataModulesConfig.from_project_root(resolved_root)

    manager = IndexManager(config)
    tool_name = f"index_manager:{args.command or 'unknown'}"

    def _append_timing(
        success: bool,
        *,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        chapter: Optional[int] = None,
    ):
        elapsed_ms = int((time.perf_counter() - command_started_at) * 1000)
        safe_append_perf_timing(
            manager.config.project_root,
            tool_name=tool_name,
            success=success,
            elapsed_ms=elapsed_ms,
            chapter=chapter,
            error_code=error_code,
            error_message=error_message,
        )

    def emit_success(data=None, message: str = "ok", chapter: Optional[int] = None):
        print_success(data, message=message)
        safe_log_tool_call(manager, tool_name=tool_name, success=True, chapter=chapter)
        _append_timing(True, chapter=chapter)

    def emit_error(code: str, message: str, suggestion: Optional[str] = None, chapter: Optional[int] = None):
        print_error(code, message, suggestion=suggestion)
        safe_log_tool_call(
            manager,
            tool_name=tool_name,
            success=False,
            error_code=code,
            error_message=message,
            chapter=chapter,
        )
        _append_timing(False, error_code=code, error_message=message, chapter=chapter)

    # 命令分发表：将 if/elif 链拆分为独立处理函数
    _COMMAND_HANDLERS = {
        "stats": _handle_stats,
        "get-chapter": _handle_get_chapter,
        "recent-appearances": _handle_recent_appearances,
        "entity-appearances": _handle_entity_appearances,
        "search-scenes": _handle_search_scenes,
        "process-chapter": _handle_process_chapter,
        "get-entity": _handle_get_entity,
        "get-core-entities": _handle_get_core_entities,
        "get-protagonist": _handle_get_protagonist,
        "get-entities-by-type": _handle_get_entities_by_type,
        "get-by-alias": _handle_get_by_alias,
        "get-aliases": _handle_get_aliases,
        "register-alias": _handle_register_alias,
        "get-relationships": _handle_get_relationships,
        "get-relationship-events": _handle_get_relationship_events,
        "get-relationship-graph": _handle_get_relationship_graph,
        "get-relationship-timeline": _handle_get_relationship_timeline,
        "get-state-changes": _handle_get_state_changes,
        "record-relationship-event": _handle_record_relationship_event,
        "upsert-entity": _handle_upsert_entity,
        "upsert-relationship": _handle_upsert_relationship,
        "record-state-change": _handle_record_state_change,
        "mark-invalid": _handle_mark_invalid,
        "resolve-invalid": _handle_resolve_invalid,
        "list-invalid": _handle_list_invalid,
        "save-review-metrics": _handle_save_review_metrics,
        "get-recent-review-metrics": _handle_get_recent_review_metrics,
        "get-review-trend-stats": _handle_get_review_trend_stats,
        "save-harness-evaluation": _handle_save_harness_evaluation,
        "get-review-trends": _handle_get_review_trends,
        "save-writing-checklist-score": _handle_save_writing_checklist_score,
        "get-writing-checklist-score": _handle_get_writing_checklist_score,
        "get-recent-writing-checklist-scores": _handle_get_recent_writing_checklist_scores,
        "get-writing-checklist-score-trend": _handle_get_writing_checklist_score_trend,
        "get-debt-summary": _handle_get_debt_summary,
        "get-recent-reading-power": _handle_get_recent_reading_power,
        "get-chapter-reading-power": _handle_get_chapter_reading_power,
        "get-pattern-usage-stats": _handle_get_pattern_usage_stats,
        "get-hook-type-stats": _handle_get_hook_type_stats,
        "get-pending-overrides": _handle_get_pending_overrides,
        "get-overdue-overrides": _handle_get_overdue_overrides,
        "get-active-debts": _handle_get_active_debts,
        "get-overdue-debts": _handle_get_overdue_debts,
        "accrue-interest": _handle_accrue_interest,
        "pay-debt": _handle_pay_debt,
        "create-override-contract": _handle_create_override_contract,
        "create-debt": _handle_create_debt,
        "fulfill-override": _handle_fulfill_override,
        "save-chapter-reading-power": _handle_save_chapter_reading_power,
    }

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler:
        handler(manager, args, emit_success, emit_error)
    else:
        emit_error("UNKNOWN_COMMAND", "未指定有效命令", suggestion="请查看 --help")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
