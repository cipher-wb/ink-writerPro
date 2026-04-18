#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL State Manager - SQLite 状态管理模块 (v5.4)

基于 IndexManager 扩展，提供与 StateManager 兼容的高级接口，
将大数据（实体、别名、状态变化、关系）存储到 SQLite 而非 JSON。

目标（v5.1 引入，v5.4 沿用）：
- 替代 state.json 中的大数据字段
- 保持与 Data Agent / Context Agent 的接口兼容
- 支持增量写入和按需查询
"""

import json
import hashlib
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ink_writer.core.index.index_manager import IndexManager
from ink_writer.core.index.index_types import (
    ChapterMeta,
    EntityMeta,
    SceneMeta,
    StateChangeMeta,
    RelationshipMeta,
    RelationshipEventMeta,
    ChapterMemoryCardMeta,
    PlotThreadRegistryMeta,
    TimelineAnchorMeta,
    CandidateFactMeta,
    ChapterReadingPowerMeta,
)
from ink_writer.core.infra.config import get_config
from ink_writer.core.infra.observability import safe_log_tool_call


@dataclass
class EntityData:
    """实体数据（用于 Data Agent 输入）"""
    id: str
    type: str  # 角色/地点/物品/势力/招式
    name: str
    tier: str = "装饰"
    desc: str = ""
    current: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    first_appearance: int = 0
    last_appearance: int = 0
    is_protagonist: bool = False


class SQLStateManager:
    """
    SQLite 状态管理器（v5.1 引入，v5.4 沿用）

    提供与 StateManager 兼容的接口，但数据存储在 SQLite (index.db) 中。
    用于替代 state.json 中膨胀的数据结构。

    用法:
    ```python
    manager = SQLStateManager(config)

    # 写入实体
    manager.upsert_entity(EntityData(
        id="xiaoyan",
        type="角色",
        name="萧炎",
        tier="核心",
        current={"realm": "斗师", "location": "天云宗"},
        aliases=["小炎子", "废柴"],
        is_protagonist=True
    ))

    # 写入状态变化
    manager.record_state_change(
        entity_id="xiaoyan",
        field="realm",
        old_value="斗者",
        new_value="斗师",
        reason="闭关突破",
        chapter=100
    )

    # 写入关系
    manager.upsert_relationship(
        from_entity="xiaoyan",
        to_entity="yaolao",
        type="师徒",
        description="药老收萧炎为徒",
        chapter=5
    )

    # 读取
    protagonist = manager.get_protagonist()
    core_entities = manager.get_core_entities()
    changes = manager.get_recent_state_changes(limit=50)
    ```
    """

    # v5.0 引入的实体类型
    ENTITY_TYPES = ["角色", "地点", "物品", "势力", "招式"]

    def __init__(self, config=None):
        self.config = config or get_config()
        self._index_manager = IndexManager(config)

    def _make_plot_thread_id(self, row: Dict[str, Any], chapter: int) -> str:
        raw_id = str(row.get("thread_id") or "").strip()
        if raw_id:
            return raw_id

        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or title or "").strip()
        basis = title or content or f"chapter-{chapter}-thread"
        slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", basis).strip("-").lower()
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:10]
        slug = slug[:32] or "thread"
        return f"{slug}-{digest}"

    def _normalize_plot_thread_status(self, raw_status: Any) -> str:
        text = str(raw_status or "").strip().lower()
        if text in {"resolved", "done", "closed", "已回收", "已兑现", "finish"}:
            return "resolved"
        if text in {"paused", "snoozed", "搁置"}:
            return "paused"
        return "active"

    # ==================== 实体操作 ====================

    def upsert_entity(self, entity: EntityData) -> bool:
        """
        插入或更新实体

        自动处理：
        - 实体基本信息写入 entities 表
        - 别名写入 aliases 表
        - canonical_name 自动添加为别名

        返回: 是否为新实体
        """
        # 构建 EntityMeta
        meta = EntityMeta(
            id=entity.id,
            type=entity.type,
            canonical_name=entity.name,
            tier=entity.tier,
            desc=entity.desc,
            current=entity.current,
            first_appearance=entity.first_appearance,
            last_appearance=entity.last_appearance,
            is_protagonist=entity.is_protagonist,
            is_archived=False
        )

        is_new = self._index_manager.upsert_entity(meta)

        # 注册别名
        # 1. canonical_name 本身作为别名
        self._index_manager.register_alias(entity.name, entity.id, entity.type)

        # 2. 其他别名
        for alias in entity.aliases:
            if alias and alias != entity.name:
                self._index_manager.register_alias(alias, entity.id, entity.type)

        return is_new

    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """获取实体详情"""
        entity = self._index_manager.get_entity(entity_id)
        if entity:
            # 添加别名
            entity["aliases"] = self._index_manager.get_entity_aliases(entity_id)
        return entity

    def get_entities_by_type(self, entity_type: str, include_archived: bool = False) -> List[Dict]:
        """按类型获取实体"""
        entities = self._index_manager.get_entities_by_type(entity_type, include_archived)
        for e in entities:
            e["aliases"] = self._index_manager.get_entity_aliases(e["id"])
        return entities

    def get_core_entities(self) -> List[Dict]:
        """
        获取核心实体（用于 Context Agent 全量加载）

        返回所有 tier=核心/重要 或 is_protagonist=1 的实体
        （次要/装饰实体按需查询，不全量加载）
        """
        entities = self._index_manager.get_core_entities()
        for e in entities:
            e["aliases"] = self._index_manager.get_entity_aliases(e["id"])
        return entities

    def get_protagonist(self) -> Optional[Dict]:
        """获取主角实体"""
        protagonist = self._index_manager.get_protagonist()
        if protagonist:
            protagonist["aliases"] = self._index_manager.get_entity_aliases(protagonist["id"])
        return protagonist

    def update_entity_current(self, entity_id: str, updates: Dict) -> bool:
        """增量更新实体的 current 字段"""
        return self._index_manager.update_entity_current(entity_id, updates)

    def resolve_alias(self, alias: str) -> List[Dict]:
        """
        根据别名解析实体（一对多）

        返回所有匹配的实体
        """
        return self._index_manager.get_entities_by_alias(alias)

    def register_alias(self, alias: str, entity_id: str, entity_type: str) -> bool:
        """注册别名"""
        return self._index_manager.register_alias(alias, entity_id, entity_type)

    # ==================== 状态变化操作 ====================

    def record_state_change(
        self,
        entity_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
        reason: str,
        chapter: int
    ) -> int:
        """
        记录状态变化

        返回: 记录 ID
        """
        change = StateChangeMeta(
            entity_id=entity_id,
            field=field,
            old_value=str(old_value) if old_value is not None else "",
            new_value=str(new_value),
            reason=reason,
            chapter=chapter
        )
        return self._index_manager.record_state_change(change)

    def get_entity_state_changes(self, entity_id: str, limit: int = 20) -> List[Dict]:
        """获取实体的状态变化历史"""
        return self._index_manager.get_entity_state_changes(entity_id, limit)

    def get_recent_state_changes(self, limit: int = 50) -> List[Dict]:
        """获取最近的状态变化"""
        return self._index_manager.get_recent_state_changes(limit)

    def get_chapter_state_changes(self, chapter: int) -> List[Dict]:
        """获取某章的所有状态变化"""
        return self._index_manager.get_chapter_state_changes(chapter)

    # ==================== 关系操作 ====================

    def upsert_relationship(
        self,
        from_entity: str,
        to_entity: str,
        type: str,
        description: str,
        chapter: int
    ) -> bool:
        """
        插入或更新关系

        返回: 是否为新关系
        """
        rel = RelationshipMeta(
            from_entity=from_entity,
            to_entity=to_entity,
            type=type,
            description=description,
            chapter=chapter
        )
        return self._index_manager.upsert_relationship(rel)

    def get_entity_relationships(self, entity_id: str, direction: str = "both") -> List[Dict]:
        """获取实体的关系"""
        return self._index_manager.get_entity_relationships(entity_id, direction)

    def get_relationship_between(self, entity1: str, entity2: str) -> List[Dict]:
        """获取两个实体之间的所有关系"""
        return self._index_manager.get_relationship_between(entity1, entity2)

    def get_recent_relationships(self, limit: int = 30) -> List[Dict]:
        """获取最近建立的关系"""
        return self._index_manager.get_recent_relationships(limit)

    # ==================== 批量写入（供 Data Agent 使用） ====================

    def process_chapter_entities(
        self,
        chapter: int,
        entities_appeared: List[Dict],
        entities_new: List[Dict],
        state_changes: List[Dict],
        relationships_new: List[Dict],
        scenes: Optional[List[Dict]] = None,
        chapter_meta: Optional[Dict[str, Any]] = None,
        chapter_memory_card: Optional[Dict[str, Any]] = None,
        timeline_anchor: Optional[Dict[str, Any]] = None,
        plot_thread_updates: Optional[List[Dict[str, Any]]] = None,
        reading_power: Optional[Dict[str, Any]] = None,
        candidate_facts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """
        处理章节的实体数据（Data Agent 主入口）

        参数:
        - chapter: 章节号
        - entities_appeared: 出场的已有实体
          [{"id": "xiaoyan", "type": "角色", "mentions": ["萧炎", "他"], "confidence": 0.95}]
        - entities_new: 新发现的实体
          [{"suggested_id": "hongyi_girl", "name": "红衣女子", "type": "角色", "tier": "装饰"}]
        - state_changes: 状态变化
          [{"entity_id": "xiaoyan", "field": "realm", "old": "斗者", "new": "斗师", "reason": "突破"}]
        - relationships_new: 新关系
          [{"from": "xiaoyan", "to": "hongyi_girl", "type": "相识", "description": "初次见面"}]

        返回: 写入统计
        """
        stats = {
            "chapters": 0,
            "scenes": 0,
            "entities_updated": 0,
            "entities_created": 0,
            "state_changes": 0,
            "relationships": 0,
            "aliases": 0,
            "memory_cards": 0,
            "timeline_anchors": 0,
            "plot_threads": 0,
            "reading_power": 0,
            "candidate_facts": 0,
        }

        scenes = scenes or []
        chapter_meta = chapter_meta or {}
        chapter_memory_card = chapter_memory_card or {}
        timeline_anchor = timeline_anchor or {}
        plot_thread_updates = plot_thread_updates or []
        reading_power = reading_power or {}
        candidate_facts = candidate_facts or []

        # 1. 处理出场实体（更新 last_appearance）
        for entity in entities_appeared:
            entity_id = entity.get("id")
            if not entity_id:
                continue

            self._index_manager.update_entity_current(entity_id, {})  # 触发 updated_at
            # 更新 last_appearance
            existing = self._index_manager.get_entity(entity_id)
            if existing:
                # 使用 SQL 直接更新 last_appearance
                self._update_last_appearance(entity_id, chapter)
                stats["entities_updated"] += 1

            # 记录出场（保留原有逻辑）
            self._index_manager.record_appearance(
                entity_id=entity_id,
                chapter=chapter,
                mentions=entity.get("mentions", []),
                confidence=entity.get("confidence", 1.0)
            )

        # 2. 处理新实体
        for entity in entities_new:
            suggested_id = entity.get("suggested_id") or entity.get("id")
            if not suggested_id:
                continue

            entity_data = EntityData(
                id=suggested_id,
                type=entity.get("type", "角色"),
                name=entity.get("name", suggested_id),
                tier=entity.get("tier", "装饰"),
                desc=entity.get("desc", ""),
                current=entity.get("current", {}),
                aliases=entity.get("aliases", []),
                first_appearance=chapter,
                last_appearance=chapter,
                is_protagonist=entity.get("is_protagonist", False)
            )
            is_new = self.upsert_entity(entity_data)
            if is_new:
                stats["entities_created"] += 1
            else:
                stats["entities_updated"] += 1

            # 统计别名
            stats["aliases"] += 1 + len(entity_data.aliases)

            # 记录新实体的首次出场（解决 appearances 缺失问题）
            mentions = entity.get("mentions", [])
            if not mentions:
                mentions = [entity_data.name]  # 至少包含实体名
            self._index_manager.record_appearance(
                entity_id=suggested_id,
                chapter=chapter,
                mentions=mentions,
                confidence=entity.get("confidence", 1.0)
            )

        # 3. 处理状态变化
        for change in state_changes:
            entity_id = change.get("entity_id")
            if not entity_id:
                continue

            self.record_state_change(
                entity_id=entity_id,
                field=change.get("field", ""),
                old_value=change.get("old", change.get("old_value", "")),
                new_value=change.get("new", change.get("new_value", "")),
                reason=change.get("reason", ""),
                chapter=chapter
            )
            stats["state_changes"] += 1

            # 同步更新实体的 current
            field_name = change.get("field")
            new_value = change.get("new", change.get("new_value"))
            # 注意：new_value 可能是 0/""/False 等 falsy 值，需要用 is not None 判断
            if field_name and new_value is not None:
                self._index_manager.update_entity_current(entity_id, {field_name: new_value})

        # 4. 处理新关系
        for rel in relationships_new:
            from_entity = rel.get("from", rel.get("from_entity"))
            to_entity = rel.get("to", rel.get("to_entity"))
            if not from_entity or not to_entity:
                continue
            rel_type = rel.get("type", "相识")
            description = rel.get("description", "")

            # v5.5: 先记录关系事件，再更新关系快照
            self._index_manager.record_relationship_event(
                RelationshipEventMeta(
                    from_entity=from_entity,
                    to_entity=to_entity,
                    type=rel_type,
                    chapter=chapter,
                    action=rel.get("action", "update"),
                    polarity=rel.get("polarity", 0),
                    strength=rel.get("strength", 0.5),
                    description=description,
                    scene_index=rel.get("scene_index", 0),
                    evidence=rel.get("evidence", ""),
                    confidence=rel.get("confidence", 1.0),
                )
            )

            self.upsert_relationship(
                from_entity=from_entity,
                to_entity=to_entity,
                type=rel_type,
                description=description,
                chapter=chapter
            )
            stats["relationships"] += 1

        related_entities: List[str] = []
        for row in entities_appeared:
            entity_id = row.get("id")
            if entity_id and entity_id not in related_entities:
                related_entities.append(entity_id)
        for row in entities_new:
            entity_id = row.get("suggested_id") or row.get("id")
            if entity_id and entity_id not in related_entities:
                related_entities.append(entity_id)

        chapter_characters: List[str] = []
        for row in [*entities_appeared, *entities_new]:
            entity_id = row.get("id") or row.get("suggested_id")
            entity_type = str(row.get("type", "") or "")
            if entity_id and entity_type == "角色" and entity_id not in chapter_characters:
                chapter_characters.append(entity_id)

        chapter_summary = str(
            chapter_memory_card.get("summary")
            or chapter_meta.get("summary")
            or ""
        )
        chapter_location = str(
            timeline_anchor.get("to_location")
            or timeline_anchor.get("location")
            or (scenes[0].get("location") if scenes else "")
            or ""
        )
        chapter_title = str(chapter_meta.get("title", "") or "")
        chapter_word_count = int(chapter_meta.get("word_count", 0) or 0)

        self._index_manager.add_chapter(
            ChapterMeta(
                chapter=chapter,
                title=chapter_title,
                location=chapter_location,
                word_count=chapter_word_count,
                characters=chapter_characters,
                summary=chapter_summary,
            )
        )
        stats["chapters"] += 1

        if scenes:
            scene_metas: List[SceneMeta] = []
            for idx, scene in enumerate(scenes, start=1):
                if not isinstance(scene, dict):
                    continue
                scene_metas.append(
                    SceneMeta(
                        chapter=chapter,
                        scene_index=int(scene.get("scene_index") or scene.get("index") or idx),
                        start_line=int(scene.get("start_line", 0) or 0),
                        end_line=int(scene.get("end_line", 0) or 0),
                        location=str(scene.get("location", "") or ""),
                        summary=str(scene.get("summary", "") or ""),
                        characters=list(scene.get("characters", []) or []),
                    )
                )
            if scene_metas:
                self._index_manager.add_scenes(chapter, scene_metas)
                stats["scenes"] += len(scene_metas)

        if chapter_memory_card:
            self._index_manager.save_chapter_memory_card(
                ChapterMemoryCardMeta(
                    chapter=chapter,
                    summary=str(chapter_memory_card.get("summary", "")),
                    goal=str(chapter_memory_card.get("goal", "")),
                    conflict=str(chapter_memory_card.get("conflict", "")),
                    result=str(chapter_memory_card.get("result", "")),
                    next_chapter_bridge=str(chapter_memory_card.get("next_chapter_bridge", "")),
                    unresolved_questions=list(chapter_memory_card.get("unresolved_questions", []) or []),
                    key_facts=list(chapter_memory_card.get("key_facts", []) or []),
                    involved_entities=list(chapter_memory_card.get("involved_entities", []) or related_entities),
                    plot_progress=list(chapter_memory_card.get("plot_progress", []) or []),
                    scene_exit_snapshot=list(chapter_memory_card.get("scene_exit_snapshot", []) or []),
                    payload_json=dict(chapter_memory_card),
                )
            )
            stats["memory_cards"] += 1

        if timeline_anchor:
            self._index_manager.save_timeline_anchor(
                TimelineAnchorMeta(
                    chapter=chapter,
                    anchor_time=str(timeline_anchor.get("anchor_time", "")),
                    relative_to_previous=str(timeline_anchor.get("relative_to_previous", "")),
                    previous_time_delta=str(timeline_anchor.get("previous_time_delta", "")),
                    countdown=str(timeline_anchor.get("countdown", "")),
                    from_location=str(timeline_anchor.get("from_location", "")),
                    to_location=str(timeline_anchor.get("to_location", "")),
                    movement=str(timeline_anchor.get("movement", "")),
                    notes=str(timeline_anchor.get("notes", "")),
                    involved_entities=list(timeline_anchor.get("involved_entities", []) or related_entities),
                    payload_json=dict(timeline_anchor),
                )
            )
            stats["timeline_anchors"] += 1

        for item in plot_thread_updates:
            if not isinstance(item, dict):
                continue
            thread_id = self._make_plot_thread_id(item, chapter)
            self._index_manager.upsert_plot_thread(
                PlotThreadRegistryMeta(
                    thread_id=thread_id,
                    title=str(item.get("title", "")),
                    content=str(item.get("content", item.get("title", ""))),
                    thread_type=str(item.get("thread_type", item.get("type", "foreshadowing"))),
                    status=self._normalize_plot_thread_status(item.get("status", "active")),
                    priority=int(item.get("priority", 50) or 50),
                    planted_chapter=int(item.get("planted_chapter") or item.get("chapter") or chapter),
                    last_touched_chapter=int(item.get("last_touched_chapter") or chapter),
                    # v9.x+: 把 `or 0` 兜底改为 None，避免 audit 查询把未设目标的伏笔误判为"已逾期"
                    target_payoff_chapter=(lambda v: int(v) if v else None)(item.get("target_payoff_chapter") or item.get("target_chapter")),
                    resolved_chapter=(lambda v: int(v) if v else None)(item.get("resolved_chapter")),
                    related_entities=list(item.get("related_entities", []) or related_entities),
                    notes=str(item.get("notes", "")),
                    confidence=float(item.get("confidence", 1.0) or 1.0),
                    payload_json={**item, "thread_id": thread_id},
                )
            )
            stats["plot_threads"] += 1

        reading_payload = dict(reading_power)
        if isinstance(chapter_meta, dict):
            hook = chapter_meta.get("hook", {}) if isinstance(chapter_meta.get("hook"), dict) else {}
            pattern = chapter_meta.get("pattern", {}) if isinstance(chapter_meta.get("pattern"), dict) else {}
            if not reading_payload.get("hook_type"):
                reading_payload["hook_type"] = hook.get("type") or pattern.get("hook") or ""
            if not reading_payload.get("hook_strength"):
                reading_payload["hook_strength"] = hook.get("strength") or "medium"
            if not reading_payload.get("coolpoint_patterns"):
                reading_payload["coolpoint_patterns"] = (
                    chapter_meta.get("coolpoint_patterns")
                    or pattern.get("coolpoint_patterns")
                    or []
                )

        if reading_payload:
            self._index_manager.save_chapter_reading_power(
                ChapterReadingPowerMeta(
                    chapter=chapter,
                    hook_type=str(reading_payload.get("hook_type", "")),
                    hook_strength=str(reading_payload.get("hook_strength", "medium")),
                    coolpoint_patterns=list(reading_payload.get("coolpoint_patterns", []) or []),
                    micropayoffs=list(reading_payload.get("micropayoffs", []) or []),
                    hard_violations=list(reading_payload.get("hard_violations", []) or []),
                    soft_suggestions=list(reading_payload.get("soft_suggestions", []) or []),
                    is_transition=bool(reading_payload.get("is_transition", False)),
                    override_count=int(reading_payload.get("override_count", 0) or 0),
                    debt_balance=float(reading_payload.get("debt_balance", 0.0) or 0.0),
                    notes=str(reading_payload.get("notes", "")),
                    payload_json={**reading_payload, "chapter_meta": chapter_meta},
                )
            )
            stats["reading_power"] += 1

        for item in candidate_facts:
            if not isinstance(item, dict):
                continue
            fact = str(item.get("fact", "") or "").strip()
            if not fact:
                continue
            self._index_manager.save_candidate_fact(
                CandidateFactMeta(
                    chapter=chapter,
                    fact=fact,
                    fact_key=str(item.get("fact_key", "")),
                    entity_id=str(item.get("entity_id", "")),
                    confidence=float(item.get("confidence", 0.5) or 0.5),
                    status=str(item.get("status", "candidate")),
                    source=str(item.get("source", "data_agent")),
                    evidence=str(item.get("evidence", "")),
                    related_entities=list(item.get("related_entities", []) or related_entities),
                    payload_json=dict(item),
                )
            )
            stats["candidate_facts"] += 1

        return stats

    def _update_last_appearance(self, entity_id: str, chapter: int):
        """更新实体的 last_appearance"""
        with self._index_manager._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE entities SET
                    last_appearance = MAX(last_appearance, ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (chapter, entity_id))
            conn.commit()

    # ==================== 统计 ====================

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._index_manager.get_stats()

    # ==================== 格式转换（兼容性） ====================

    def export_to_entities_v3_format(self) -> Dict[str, Dict[str, Dict]]:
        """
        导出为 entities_v3 格式（用于兼容性）

        返回: {"角色": {"xiaoyan": {...}}, "地点": {...}, ...}
        """
        result = {t: {} for t in self.ENTITY_TYPES}

        for entity_type in self.ENTITY_TYPES:
            entities = self.get_entities_by_type(entity_type, include_archived=True)
            for e in entities:
                entity_dict = {
                    "canonical_name": e.get("canonical_name"),
                    "name": e.get("canonical_name"),  # 兼容性别名
                    "tier": e.get("tier", "装饰"),
                    "aliases": e.get("aliases", []),
                    "desc": e.get("desc", ""),
                    "current": e.get("current_json", {}),
                    "history": [],  # 历史记录需要从 state_changes 表查询
                    "first_appearance": e.get("first_appearance", 0),
                    "last_appearance": e.get("last_appearance", 0)
                }
                if e.get("is_protagonist"):
                    entity_dict["is_protagonist"] = True
                result[entity_type][e["id"]] = entity_dict

        return result

    def export_to_alias_index_format(self) -> Dict[str, List[Dict[str, str]]]:
        """
        导出为 alias_index 格式（用于兼容性）

        返回: {"萧炎": [{"type": "角色", "id": "xiaoyan"}], ...}
        """
        result = {}

        with self._index_manager._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT alias, entity_id, entity_type FROM aliases")
            for row in cursor.fetchall():
                alias = row["alias"]
                if alias not in result:
                    result[alias] = []
                result[alias].append({
                    "type": row["entity_type"],
                    "id": row["entity_id"]
                })

        return result

    # ==================== v13 单一事实源: state_kv 操作 ====================

    def set_state_kv(self, key: str, value: Any) -> None:
        """写入 state_kv 键值对（value 自动 JSON 序列化）"""
        value_json = json.dumps(value, ensure_ascii=False)
        with self._index_manager._get_conn(immediate=True) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO state_kv (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value_json),
            )

    def get_state_kv(self, key: str, default: Any = None) -> Any:
        """读取 state_kv 键值对（自动 JSON 反序列化）"""
        with self._index_manager._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM state_kv WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return default
            return json.loads(row["value"])

    def get_all_state_kv(self) -> Dict[str, Any]:
        """读取全部 state_kv 键值对"""
        with self._index_manager._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM state_kv").fetchall()
            return {row["key"]: json.loads(row["value"]) for row in rows}

    def delete_state_kv(self, key: str) -> bool:
        """删除 state_kv 键值对"""
        with self._index_manager._get_conn(immediate=True) as conn:
            cursor = conn.execute("DELETE FROM state_kv WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def bulk_set_state_kv(self, entries: Dict[str, Any]) -> int:
        """批量写入 state_kv 键值对"""
        with self._index_manager._get_conn(immediate=True) as conn:
            count = 0
            for key, value in entries.items():
                value_json = json.dumps(value, ensure_ascii=False)
                conn.execute(
                    "INSERT OR REPLACE INTO state_kv (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (key, value_json),
                )
                count += 1
            return count

    # ==================== v13 单一事实源: 消歧记录操作 ====================

    def add_disambiguation_entry(self, category: str, payload: Any, chapter: int = 0) -> int:
        """添加消歧记录 (category: 'warning' | 'pending')"""
        payload_json = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
        with self._index_manager._get_conn(immediate=True) as conn:
            cursor = conn.execute(
                "INSERT INTO disambiguation_log (category, payload, chapter, status) VALUES (?, ?, ?, 'active')",
                (category, payload_json, chapter),
            )
            return cursor.lastrowid or 0

    def get_disambiguation_entries(self, category: str, status: str = "active") -> List[Any]:
        """获取消歧记录"""
        with self._index_manager._get_conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM disambiguation_log WHERE category = ? AND status = ? ORDER BY created_at",
                (category, status),
            ).fetchall()
            result = []
            for row in rows:
                try:
                    result.append(json.loads(row["payload"]))
                except (json.JSONDecodeError, TypeError):
                    result.append(row["payload"])
            return result

    def resolve_disambiguation_entry(self, entry_id: int) -> bool:
        """标记消歧记录为已解决"""
        with self._index_manager._get_conn(immediate=True) as conn:
            cursor = conn.execute(
                "UPDATE disambiguation_log SET status = 'resolved', resolved_at = datetime('now') WHERE id = ?",
                (entry_id,),
            )
            return cursor.rowcount > 0

    def bulk_add_disambiguation_entries(self, category: str, payloads: List[Any], chapter: int = 0) -> int:
        """批量添加消歧记录"""
        with self._index_manager._get_conn(immediate=True) as conn:
            count = 0
            for payload in payloads:
                payload_json = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
                conn.execute(
                    "INSERT INTO disambiguation_log (category, payload, chapter, status) VALUES (?, ?, ?, 'active')",
                    (category, payload_json, chapter),
                )
                count += 1
            return count

    # ==================== v13 单一事实源: 审查检查点操作 ====================

    def add_review_checkpoint(self, payload: Any) -> int:
        """添加审查检查点"""
        payload_json = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
        with self._index_manager._get_conn(immediate=True) as conn:
            cursor = conn.execute(
                "INSERT INTO review_checkpoint_entries (payload) VALUES (?)",
                (payload_json,),
            )
            return cursor.lastrowid or 0

    def get_review_checkpoints(self, limit: int = 100) -> List[Any]:
        """获取审查检查点（按插入顺序返回）"""
        with self._index_manager._get_conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM review_checkpoint_entries ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                try:
                    result.append(json.loads(row["payload"]))
                except (json.JSONDecodeError, TypeError):
                    result.append(row["payload"])
            return result

    def bulk_add_review_checkpoints(self, payloads: List[Any]) -> int:
        """批量添加审查检查点"""
        with self._index_manager._get_conn(immediate=True) as conn:
            count = 0
            for payload in payloads:
                payload_json = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
                conn.execute(
                    "INSERT INTO review_checkpoint_entries (payload) VALUES (?)",
                    (payload_json,),
                )
                count += 1
            return count

    # ==================== v13 单一事实源: state.json 视图重建 ====================

    def rebuild_state_dict(self) -> Dict[str, Any]:
        """
        从 SQLite 重建完整的 state.json 字典。

        SQLite 是唯一事实源，此方法从各表汇总数据，
        输出与现有 state.json schema 完全兼容的 dict。
        """
        kv = self.get_all_state_kv()

        state: Dict[str, Any] = {
            "schema_version": int(kv.get("schema_version", 9)),
            "project_info": kv.get("project_info", {}),
            "progress": kv.get("progress", {}),
            "protagonist_state": kv.get("protagonist_state", {}),
            "relationships": kv.get("relationships", {}),
            "world_settings": kv.get("world_settings", {
                "power_system": [], "factions": [], "locations": []
            }),
            "strand_tracker": kv.get("strand_tracker", {
                "last_quest_chapter": 0,
                "last_fire_chapter": 0,
                "last_constellation_chapter": 0,
                "current_dominant": "quest",
                "chapters_since_switch": 0,
                "history": [],
            }),
        }

        # 消歧数据
        state["disambiguation_warnings"] = self.get_disambiguation_entries("warning")
        state["disambiguation_pending"] = self.get_disambiguation_entries("pending")

        # 审查检查点
        state["review_checkpoints"] = self.get_review_checkpoints()

        # 剧情线程 → plot_threads 格式
        state["plot_threads"] = self._rebuild_plot_threads()

        # chapter_meta: 最近 20 章
        state["chapter_meta"] = self._rebuild_recent_chapter_meta(limit=20)

        # 附加 config 字段
        for cfg_key in ("harness_config", "hook_contract_config"):
            if cfg_key in kv:
                state[cfg_key] = kv[cfg_key]

        return state

    def rebuild_state_json(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """重建 state.json 文件并写入磁盘"""
        state = self.rebuild_state_dict()
        target = output_path or self.config.state_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return state

    def _rebuild_plot_threads(self) -> Dict[str, Any]:
        """从 plot_thread_registry 表重建 plot_threads"""
        with self._index_manager._get_conn() as conn:
            active_rows = conn.execute(
                "SELECT * FROM plot_thread_registry WHERE status = 'active' ORDER BY priority DESC"
            ).fetchall()
            foreshadow_rows = conn.execute(
                "SELECT * FROM plot_thread_registry WHERE thread_type = 'foreshadowing' ORDER BY planted_chapter"
            ).fetchall()

        active_threads = []
        for row in active_rows:
            active_threads.append({
                "thread_id": row["thread_id"],
                "title": row["title"],
                "content": row["content"],
                "type": row["thread_type"],
                "status": row["status"],
                "priority": row["priority"],
                "planted_chapter": row["planted_chapter"],
                "last_touched_chapter": row["last_touched_chapter"],
            })

        foreshadowing = []
        for row in foreshadow_rows:
            foreshadowing.append({
                "thread_id": row["thread_id"],
                "title": row["title"],
                "content": row["content"],
                "status": row["status"],
                "planted_chapter": row["planted_chapter"],
                "target_payoff_chapter": row["target_payoff_chapter"],
                "resolved_chapter": row["resolved_chapter"],
            })

        return {"active_threads": active_threads, "foreshadowing": foreshadowing}

    def _rebuild_recent_chapter_meta(self, limit: int = 20) -> Dict[str, Any]:
        """从 chapters + chapter_reading_power 表重建最近 chapter_meta"""
        with self._index_manager._get_conn() as conn:
            rows = conn.execute(
                "SELECT chapter, title, location, word_count FROM chapters ORDER BY chapter DESC LIMIT ?",
                (limit,),
            ).fetchall()

        result = {}
        for row in rows:
            ch_key = str(row["chapter"])
            meta: Dict[str, Any] = {"version": 1}

            with self._index_manager._get_conn() as conn:
                rp = conn.execute(
                    "SELECT hook_type, hook_strength FROM chapter_reading_power WHERE chapter = ?",
                    (row["chapter"],),
                ).fetchone()

            hook_type = rp["hook_type"] if rp else ""
            hook_strength = rp["hook_strength"] if rp else ""

            meta["hook"] = {"type": hook_type, "content": "", "strength": hook_strength}
            meta["pattern"] = {"opening": "", "hook": hook_type, "emotion_rhythm": ""}
            meta["ending"] = {"time": "", "location": row["location"] or "", "emotion": ""}

            result[ch_key] = meta

        return result

    def migrate_state_to_kv(self, state: Dict[str, Any]) -> int:
        """
        将 state.json 全量数据迁移到 state_kv + disambiguation_log + review_checkpoint_entries。

        用于 v8→v9 迁移。
        返回写入的 kv 条目数。
        """
        kv_keys = [
            "schema_version", "project_info", "progress", "protagonist_state",
            "relationships", "world_settings", "strand_tracker",
            "harness_config", "hook_contract_config",
        ]

        kv_entries = {}
        for key in kv_keys:
            if key in state:
                kv_entries[key] = state[key]

        count = self.bulk_set_state_kv(kv_entries)

        # 迁移消歧数据
        warnings = state.get("disambiguation_warnings", [])
        if warnings:
            count += self.bulk_add_disambiguation_entries("warning", warnings)

        pending = state.get("disambiguation_pending", [])
        if pending:
            count += self.bulk_add_disambiguation_entries("pending", pending)

        # 迁移审查检查点
        checkpoints = state.get("review_checkpoints", [])
        if checkpoints:
            count += self.bulk_add_review_checkpoints(checkpoints)

        return count


# ==================== CLI 接口 ====================

def main():
    import argparse
    import sys
    from ink_writer.core.cli.cli_output import print_success, print_error
    from ink_writer.core.cli.cli_args import normalize_global_project_root, load_json_arg
    from ink_writer.core.index.index_manager import IndexManager

    parser = argparse.ArgumentParser(description="SQL State Manager CLI (v5.4)")
    parser.add_argument("--project-root", type=str, help="项目根目录")

    subparsers = parser.add_subparsers(dest="command")

    # 获取统计
    subparsers.add_parser("stats")

    # 获取主角
    subparsers.add_parser("get-protagonist")

    # 获取核心实体
    subparsers.add_parser("get-core-entities")

    # 导出 entities_v3 格式
    subparsers.add_parser("export-entities-v3")

    # 导出 alias_index 格式
    subparsers.add_parser("export-alias-index")

    # 处理章节数据
    process_parser = subparsers.add_parser("process-chapter")
    process_parser.add_argument("--chapter", type=int, required=True)
    process_parser.add_argument("--data", required=True, help="JSON 格式的章节数据")

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)

    # 初始化
    config = None
    if args.project_root:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .ink/state.json）
        from project_locator import resolve_project_root
        from ink_writer.core.infra.config import DataModulesConfig

        try:
            resolved_root = resolve_project_root(args.project_root)
        except FileNotFoundError:
            resolved_root = Path(args.project_root).expanduser().resolve()
        config = DataModulesConfig.from_project_root(resolved_root)

    manager = SQLStateManager(config)
    logger = IndexManager(config)
    tool_name = f"sql_state_manager:{args.command or 'unknown'}"

    def emit_success(data=None, message: str = "ok"):
        print_success(data, message=message)
        safe_log_tool_call(logger, tool_name=tool_name, success=True)

    def emit_error(code: str, message: str, suggestion: str | None = None):
        print_error(code, message, suggestion=suggestion)
        safe_log_tool_call(
            logger,
            tool_name=tool_name,
            success=False,
            error_code=code,
            error_message=message,
        )

    if args.command == "stats":
        stats = manager.get_stats()
        emit_success(stats, message="stats")

    elif args.command == "get-protagonist":
        protagonist = manager.get_protagonist()
        if protagonist:
            emit_success(protagonist, message="protagonist")
        else:
            emit_error("NOT_FOUND", "未设置主角")

    elif args.command == "get-core-entities":
        entities = manager.get_core_entities()
        emit_success(entities, message="core_entities")

    elif args.command == "export-entities-v3":
        data = manager.export_to_entities_v3_format()
        emit_success(data, message="entities_v3")

    elif args.command == "export-alias-index":
        data = manager.export_to_alias_index_format()
        emit_success(data, message="alias_index")

    elif args.command == "process-chapter":
        data = load_json_arg(args.data)
        stats = manager.process_chapter_entities(
            chapter=args.chapter,
            entities_appeared=data.get("entities_appeared", []),
            entities_new=data.get("entities_new", []),
            state_changes=data.get("state_changes", []),
            relationships_new=data.get("relationships_new", []),
        )
        emit_success(stats, message="chapter_processed")

    else:
        emit_error("UNKNOWN_COMMAND", "未指定有效命令", suggestion="请查看 --help")


if __name__ == "__main__":
    main()
