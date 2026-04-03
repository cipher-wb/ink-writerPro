#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Index Types - 索引相关数据类型定义

从 index_manager.py 提取，供 index_manager、各 mixin、sql_state_manager 等模块共享，
消除 mixin ↔ index_manager 之间的循环导入。
"""

from typing import Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class ChapterMeta:
    """章节元数据"""

    chapter: int
    title: str
    location: str
    word_count: int
    characters: List[str]
    summary: str = ""


@dataclass
class SceneMeta:
    """场景元数据"""

    chapter: int
    scene_index: int
    start_line: int
    end_line: int
    location: str
    summary: str
    characters: List[str]


@dataclass
class EntityMeta:
    """实体元数据 (v5.1 引入)"""

    id: str
    type: str  # 角色/地点/物品/势力/招式
    canonical_name: str
    tier: str = "装饰"  # 核心/重要/次要/装饰
    desc: str = ""
    current: Dict = field(default_factory=dict)  # 当前状态 (realm/location/items等)
    first_appearance: int = 0
    last_appearance: int = 0
    is_protagonist: bool = False
    is_archived: bool = False


@dataclass
class StateChangeMeta:
    """状态变化记录 (v5.1 引入)"""

    entity_id: str
    field: str
    old_value: str
    new_value: str
    reason: str
    chapter: int


@dataclass
class RelationshipMeta:
    """关系记录 (v5.1 引入)"""

    from_entity: str
    to_entity: str
    type: str
    description: str
    chapter: int


@dataclass
class RelationshipEventMeta:
    """关系事件记录 (v5.5 引入)"""

    from_entity: str
    to_entity: str
    type: str
    chapter: int
    action: str = "update"  # create/update/decay/remove
    polarity: int = 0  # -1/0/1
    strength: float = 0.5  # 0~1
    description: str = ""
    scene_index: int = 0
    evidence: str = ""
    confidence: float = 1.0


@dataclass
class OverrideContractMeta:
    """Override Contract (v5.3 引入)"""

    chapter: int
    constraint_type: str  # SOFT_HOOK_STRENGTH / SOFT_MICROPAYOFF / etc.
    constraint_id: str  # 具体约束标识
    rationale_type: str  # TRANSITIONAL_SETUP / LOGIC_INTEGRITY / etc.
    rationale_text: str  # 具体理由说明
    payback_plan: str  # 偿还计划描述
    due_chapter: int  # 偿还截止章节
    status: str = "pending"  # pending / fulfilled / overdue / cancelled


@dataclass
class ChaseDebtMeta:
    """追读力债务 (v5.3 引入)"""

    id: int = 0
    debt_type: str = ""  # hook_strength / micropayoff / coolpoint / etc.
    original_amount: float = 1.0  # 初始债务量
    current_amount: float = 1.0  # 当前债务量（含利息）
    interest_rate: float = 0.1  # 利息率（每章）
    source_chapter: int = 0  # 产生债务的章节
    due_chapter: int = 0  # 截止章节
    override_contract_id: int = 0  # 关联的Override Contract
    status: str = "active"  # active / paid / overdue / written_off


@dataclass
class DebtEventMeta:
    """债务事件日志 (v5.3 引入)"""

    debt_id: int
    event_type: (
        str  # created / interest_accrued / partial_payment / full_payment / overdue
    )
    amount: float
    chapter: int
    note: str = ""


@dataclass
class ChapterReadingPowerMeta:
    """章节追读力元数据 (v5.3 引入)"""

    chapter: int
    hook_type: str = ""  # 章末钩子类型
    hook_strength: str = "medium"  # strong / medium / weak
    coolpoint_patterns: List[str] = field(default_factory=list)  # 使用的爽点模式
    micropayoffs: List[str] = field(default_factory=list)  # 微兑现列表
    hard_violations: List[str] = field(default_factory=list)  # 硬约束违规
    soft_suggestions: List[str] = field(default_factory=list)  # 软建议
    is_transition: bool = False  # 是否为过渡章
    override_count: int = 0  # Override Contract数量
    debt_balance: float = 0.0  # 当前债务余额
    notes: str = ""
    payload_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterMemoryCardMeta:
    """章节记忆卡（质量优先重构）"""

    chapter: int
    summary: str = ""
    goal: str = ""
    conflict: str = ""
    result: str = ""
    next_chapter_bridge: str = ""
    unresolved_questions: List[str] = field(default_factory=list)
    key_facts: List[str] = field(default_factory=list)
    involved_entities: List[str] = field(default_factory=list)
    plot_progress: List[str] = field(default_factory=list)
    payload_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlotThreadRegistryMeta:
    """剧情线程注册表（伏笔/支线/悬念）"""

    thread_id: str
    title: str = ""
    content: str = ""
    thread_type: str = "foreshadowing"
    status: str = "active"
    priority: int = 50
    planted_chapter: int = 0
    last_touched_chapter: int = 0
    target_payoff_chapter: int = 0
    resolved_chapter: int = 0
    related_entities: List[str] = field(default_factory=list)
    notes: str = ""
    confidence: float = 1.0
    payload_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimelineAnchorMeta:
    """章节时间锚点"""

    chapter: int
    anchor_time: str = ""
    relative_to_previous: str = ""
    previous_time_delta: str = ""
    countdown: str = ""
    from_location: str = ""
    to_location: str = ""
    movement: str = ""
    notes: str = ""
    involved_entities: List[str] = field(default_factory=list)
    payload_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateFactMeta:
    """低置信度候选事实"""

    chapter: int
    fact: str
    fact_key: str = ""
    entity_id: str = ""
    confidence: float = 0.5
    status: str = "candidate"
    source: str = "data_agent"
    evidence: str = ""
    related_entities: List[str] = field(default_factory=list)
    payload_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewMetrics:
    """审查指标记录 (v5.4 引入)"""

    start_chapter: int
    end_chapter: int
    overall_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    severity_counts: Dict[str, int] = field(default_factory=dict)
    critical_issues: List[str] = field(default_factory=list)
    report_file: str = ""
    notes: str = ""
    review_payload_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WritingChecklistScoreMeta:
    """写作清单评分记录（Context Contract v2 Phase F）"""

    chapter: int
    template: str = "plot"
    total_items: int = 0
    required_items: int = 0
    completed_items: int = 0
    completed_required: int = 0
    total_weight: float = 0.0
    completed_weight: float = 0.0
    completion_rate: float = 0.0
    score: float = 0.0
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    pending_items: List[str] = field(default_factory=list)
    source: str = "context_manager"
    notes: str = ""
