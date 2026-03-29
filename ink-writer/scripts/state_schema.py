#!/usr/bin/env python3
"""
State Schema — state.json 的 Pydantic v2 模型定义

用途：
1. 类型安全的 state.json 读写
2. 自动验证字段完整性
3. 为 IDE 提供自动补全支持
4. 为 migrate.py 提供 schema 定义

使用方式：
    from state_schema import StateModel, load_state, save_state

    state = load_state(project_root)
    state.progress.current_chapter = 42
    save_state(project_root, state)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field
except ImportError:
    import sys

    print(
        "\u26a0\ufe0f pydantic \u672a\u5b89\u88c5\uff0cstate_schema \u5c06\u4e0d\u53ef\u7528\u3002\u8fd0\u884c: pip install pydantic",
        file=sys.stderr,
    )
    raise


# ---------------------------------------------------------------------------
# Sub-models: Protagonist
# ---------------------------------------------------------------------------


class PowerState(BaseModel):
    model_config = ConfigDict(extra="allow")

    realm: str = Field(default="")
    layer: int = Field(default=1)
    bottleneck: str = Field(default="")


class LocationState(BaseModel):
    model_config = ConfigDict(extra="allow")

    current: str = Field(default="")
    last_chapter: int = Field(default=0)


class GoldenFingerState(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="")
    level: int = Field(default=1)
    cooldown: int = Field(default=0)
    skills: List[str] = Field(default_factory=list)


class ProtagonistState(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="")
    power: PowerState = Field(default_factory=PowerState)
    location: LocationState = Field(default_factory=LocationState)
    golden_finger: GoldenFingerState = Field(default_factory=GoldenFingerState)
    attributes: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sub-models: Progress
# ---------------------------------------------------------------------------


class ProgressState(BaseModel):
    model_config = ConfigDict(extra="allow")

    current_chapter: int = Field(default=0)
    total_words: int = Field(default=0)
    last_updated: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    volumes_completed: List[Any] = Field(default_factory=list)
    current_volume: int = Field(default=1)
    volumes_planned: List[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-models: World / Plot
# ---------------------------------------------------------------------------


class WorldSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    power_system: List[Any] = Field(default_factory=list)
    factions: List[Any] = Field(default_factory=list)
    locations: List[Any] = Field(default_factory=list)


class PlotThreads(BaseModel):
    model_config = ConfigDict(extra="allow")

    active_threads: List[Any] = Field(default_factory=list)
    foreshadowing: List[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-models: Strand Tracker
# ---------------------------------------------------------------------------


class StrandTracker(BaseModel):
    model_config = ConfigDict(extra="allow")

    last_quest_chapter: int = Field(default=0)
    last_fire_chapter: int = Field(default=0)
    last_constellation_chapter: int = Field(default=0)
    current_dominant: str = Field(default="quest")
    chapters_since_switch: int = Field(default=0)
    history: List[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-models: Chapter Meta
# ---------------------------------------------------------------------------


class HookMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = Field(default="")
    content: str = Field(default="")
    strength: str = Field(default="")


class PatternMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    opening: str = Field(default="")
    hook: str = Field(default="")
    emotion_rhythm: str = Field(default="")


class EndingMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    time: str = Field(default="")
    location: str = Field(default="")
    emotion: str = Field(default="")


class ChapterMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = Field(default=1)
    updated_at: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    hook: HookMeta = Field(default_factory=HookMeta)
    pattern: PatternMeta = Field(default_factory=PatternMeta)
    ending: EndingMeta = Field(default_factory=EndingMeta)


# ---------------------------------------------------------------------------
# Sub-models: Project Info
# ---------------------------------------------------------------------------


class GoldenFingerInfo(BaseModel):
    """金手指相关信息"""
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = Field(default=None)
    type: Optional[str] = Field(default=None)
    style: Optional[str] = Field(default=None)
    visibility: Optional[str] = Field(default=None)
    irreversible_cost: Optional[str] = Field(default=None)


class HeroineCharacterInfo(BaseModel):
    """女主/情感线相关信息"""
    model_config = ConfigDict(extra="allow")
    config: Optional[str] = Field(default=None)
    names: Optional[str] = Field(default=None)
    role: Optional[str] = Field(default=None)


class WorldBuildingInfo(BaseModel):
    """世界观设定相关信息"""
    model_config = ConfigDict(extra="allow")
    scale: Optional[str] = Field(default=None)
    factions: Optional[str] = Field(default=None)
    power_system_type: Optional[str] = Field(default=None)
    social_class: Optional[str] = Field(default=None)
    resource_distribution: Optional[str] = Field(default=None)
    currency_system: Optional[str] = Field(default=None)
    currency_exchange: Optional[str] = Field(default=None)
    sect_hierarchy: Optional[str] = Field(default=None)
    cultivation_chain: Optional[str] = Field(default=None)
    cultivation_subtiers: Optional[str] = Field(default=None)


class ProjectInfo(BaseModel):
    """项目信息（v2: 子模型分组，保持向后兼容）"""
    model_config = ConfigDict(extra="allow")

    # 基础信息
    title: Optional[str] = Field(default=None)
    genre: Optional[str] = Field(default=None)
    created_at: Optional[str] = Field(default=None)
    target_words: Optional[int] = Field(default=None)
    target_chapters: Optional[int] = Field(default=None)
    core_selling_points: Optional[str] = Field(default=None)
    target_reader: Optional[str] = Field(default=None)
    platform: Optional[str] = Field(default=None)
    opening_hook: Optional[str] = Field(default=None)

    # 角色信息
    protagonist_structure: Optional[str] = Field(default=None)
    co_protagonists: Optional[str] = Field(default=None)
    co_protagonist_roles: Optional[str] = Field(default=None)
    antagonist_tiers: Optional[str] = Field(default=None)

    # 核心主题（v6.4 引入）
    themes: List[str] = Field(default_factory=list)

    # 子模型（新增，向后兼容：extra="allow" 确保旧字段不报错）
    golden_finger: GoldenFingerInfo = Field(default_factory=GoldenFingerInfo)
    heroine: HeroineCharacterInfo = Field(default_factory=HeroineCharacterInfo)
    world_building: WorldBuildingInfo = Field(default_factory=WorldBuildingInfo)

    # 保留旧字段以向后兼容（已迁移到子模型，但旧数据可能仍有这些平铺字段）
    golden_finger_name: Optional[str] = Field(default=None)
    golden_finger_type: Optional[str] = Field(default=None)
    golden_finger_style: Optional[str] = Field(default=None)
    heroine_config: Optional[str] = Field(default=None)
    heroine_names: Optional[str] = Field(default=None)
    heroine_role: Optional[str] = Field(default=None)
    world_scale: Optional[str] = Field(default=None)
    factions: Optional[str] = Field(default=None)
    power_system_type: Optional[str] = Field(default=None)
    social_class: Optional[str] = Field(default=None)
    resource_distribution: Optional[str] = Field(default=None)
    gf_visibility: Optional[str] = Field(default=None)
    gf_irreversible_cost: Optional[str] = Field(default=None)
    currency_system: Optional[str] = Field(default=None)
    currency_exchange: Optional[str] = Field(default=None)
    sect_hierarchy: Optional[str] = Field(default=None)
    cultivation_chain: Optional[str] = Field(default=None)
    cultivation_subtiers: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Top-level State Model
# ---------------------------------------------------------------------------


class StateModel(BaseModel):
    """state.json 顶层模型 (schema_version 6)"""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=6)
    project_info: ProjectInfo = Field(default_factory=ProjectInfo)
    progress: ProgressState = Field(default_factory=ProgressState)
    protagonist_state: ProtagonistState = Field(default_factory=ProtagonistState)
    relationships: Dict[str, Any] = Field(default_factory=dict)
    disambiguation_warnings: List[Any] = Field(default_factory=list)
    disambiguation_pending: List[Any] = Field(default_factory=list)
    world_settings: WorldSettings = Field(default_factory=WorldSettings)
    plot_threads: PlotThreads = Field(default_factory=PlotThreads)
    review_checkpoints: List[Any] = Field(default_factory=list)
    chapter_meta: Dict[str, ChapterMeta] = Field(default_factory=dict)
    strand_tracker: StrandTracker = Field(default_factory=StrandTracker)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def load_state(project_root: Path | str) -> StateModel:
    """从 .ink/state.json 加载并验证 state"""
    state_file = Path(project_root) / ".ink" / "state.json"
    if not state_file.exists():
        return StateModel()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    return StateModel.model_validate(data)


def save_state(project_root: Path | str, state: StateModel) -> None:
    """将 state 保存到 .ink/state.json"""
    state_file = Path(project_root) / ".ink" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        state.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
