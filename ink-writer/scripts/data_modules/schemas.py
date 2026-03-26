#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pydantic schemas for data_modules outputs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, ConfigDict


class EntityAppeared(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    mentions: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class EntityNew(BaseModel):
    model_config = ConfigDict(extra="allow")

    suggested_id: str
    name: str
    type: str
    tier: str = "装饰"


class StateChange(BaseModel):
    model_config = ConfigDict(extra="allow")

    entity_id: str
    field: str
    old: Optional[str] = None
    new: str
    reason: Optional[str] = None


class RelationshipNew(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_entity: str = Field(alias="from")
    to_entity: str = Field(alias="to")
    type: str
    description: Optional[str] = None
    chapter: Optional[int] = None


class UncertainCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    id: str


class UncertainMention(BaseModel):
    model_config = ConfigDict(extra="allow")

    mention: str
    candidates: List[UncertainCandidate] = Field(default_factory=list)
    confidence: float = 0.0
    adopted: Optional[str] = None


class SceneChunk(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int = 0
    start_line: int = 0
    end_line: int = 0
    location: str = ""
    summary: str = ""
    characters: List[str] = Field(default_factory=list)
    content: str = ""


class ChapterMemoryCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    summary: str = ""
    goal: str = ""
    conflict: str = ""
    result: str = ""
    next_chapter_bridge: str = ""
    unresolved_questions: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    involved_entities: List[str] = Field(default_factory=list)
    plot_progress: List[str] = Field(default_factory=list)


class TimelineAnchor(BaseModel):
    model_config = ConfigDict(extra="allow")

    anchor_time: str = ""
    relative_to_previous: str = ""
    previous_time_delta: str = ""
    countdown: str = ""
    from_location: str = ""
    to_location: str = ""
    movement: str = ""
    notes: str = ""
    involved_entities: List[str] = Field(default_factory=list)


class PlotThreadUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    thread_id: str = ""
    title: str = ""
    content: str = ""
    thread_type: str = "foreshadowing"
    status: str = "active"
    priority: int = 50
    planted_chapter: Optional[int] = None
    last_touched_chapter: Optional[int] = None
    target_payoff_chapter: Optional[int] = None
    resolved_chapter: Optional[int] = None
    related_entities: List[str] = Field(default_factory=list)
    notes: str = ""
    confidence: float = 1.0


class ReadingPowerPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    hook_type: str = ""
    hook_strength: str = "medium"
    coolpoint_patterns: List[str] = Field(default_factory=list)
    micropayoffs: List[str] = Field(default_factory=list)
    hard_violations: List[str] = Field(default_factory=list)
    soft_suggestions: List[str] = Field(default_factory=list)
    is_transition: bool = False
    override_count: int = 0
    debt_balance: float = 0.0
    golden_three_role: str = ""
    opening_trigger_type: str = ""
    opening_trigger_position: int = 0
    reader_promise: str = ""
    visible_change: str = ""
    next_chapter_drive: str = ""
    golden_three_metrics: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="allow")

    fact: str
    fact_key: str = ""
    entity_id: str = ""
    confidence: float = 0.5
    evidence: str = ""
    status: str = "candidate"
    source: str = "data_agent"
    related_entities: List[str] = Field(default_factory=list)


class ChapterMetaPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    hook: Dict[str, Any] = Field(default_factory=dict)
    pattern: Dict[str, Any] = Field(default_factory=dict)
    ending: Dict[str, Any] = Field(default_factory=dict)
    golden_three: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class DataAgentOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    entities_appeared: List[EntityAppeared] = Field(default_factory=list)
    entities_new: List[EntityNew] = Field(default_factory=list)
    state_changes: List[StateChange] = Field(default_factory=list)
    relationships_new: List[RelationshipNew] = Field(default_factory=list)
    scenes: List[SceneChunk] = Field(default_factory=list)
    scenes_chunked: int = 0
    chapter_meta: ChapterMetaPayload = Field(default_factory=ChapterMetaPayload)
    chapter_memory_card: ChapterMemoryCard = Field(default_factory=ChapterMemoryCard)
    timeline_anchor: TimelineAnchor = Field(default_factory=TimelineAnchor)
    plot_thread_updates: List[PlotThreadUpdate] = Field(default_factory=list)
    reading_power: ReadingPowerPayload = Field(default_factory=ReadingPowerPayload)
    candidate_facts: List[CandidateFact] = Field(default_factory=list)
    uncertain: List[UncertainMention] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ErrorSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    suggestion: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def validate_data_agent_output(payload: Dict[str, Any]) -> DataAgentOutput:
    return DataAgentOutput.model_validate(payload)


def format_validation_error(exc: ValidationError) -> Dict[str, Any]:
    return {
        "code": "SCHEMA_VALIDATION_FAILED",
        "message": "数据结构校验失败",
        "details": {"errors": exc.errors()},
        "suggestion": "请检查 data-agent 输出字段是否完整且类型正确",
    }


def normalize_data_agent_output(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    def _ensure_list(key: str):
        value = payload.get(key)
        if value is None:
            payload[key] = []
        elif isinstance(value, list):
            return
        else:
            payload[key] = [value]

    for key in [
        "entities_appeared",
        "entities_new",
        "state_changes",
        "relationships_new",
        "scenes",
        "plot_thread_updates",
        "candidate_facts",
        "uncertain",
        "warnings",
    ]:
        _ensure_list(key)

    for key, default in {
        "chapter_meta": {},
        "chapter_memory_card": {},
        "timeline_anchor": {},
        "reading_power": {},
    }.items():
        value = payload.get(key)
        if not isinstance(value, dict):
            payload[key] = dict(default)

    payload.setdefault("scenes_chunked", 0)
    if not payload.get("scenes_chunked"):
        payload["scenes_chunked"] = len(payload.get("scenes", []))
    return payload
