"""US-009: scene_mode 场景识别器。

从章节号 + 章节大纲文本（markdown）推断 scene_mode，作为 writer-agent /
directness-checker / sensory-immersion-checker / polish-agent 共享的激活依据。

取值固定 7 种之一（PRD FR-1）：

    golden_three | combat | climax | high_point | slow_build | emotional | other

优先级（PRD US-009，高优先级覆盖低优先级）::

    golden_three > climax > high_point > combat > emotional > slow_build > other

判定规则：

- ``chapter_no ∈ [1, 2, 3]`` → 强制 ``golden_three``（与 directness_checker
  ``is_activated`` 同源语义）。
- 其他章节基于大纲文本关键词命中：

  * ``climax``  命中 → 大结局 / 高潮 / 终局 / 决战 / 最终战
  * ``high_point`` 命中 → 爽点 / 反转 / 打脸 / 掉马 / 震撼 / 装逼
  * ``combat``   命中 → 战斗 / 对战 / 交手 / 厮杀 / 激战 / 对决 / 出手 / 剑 / 拳
  * ``emotional`` 命中 → 告别 / 离别 / 悲痛 / 痛哭 / 情感 / 心碎 / 思念 / 缅怀
  * ``slow_build`` 命中 → 日常 / 铺垫 / 闲聊 / 修炼 / 闲暇 / 家常 / 平静
  * 其余 → ``other``

大纲文本允许 ``None`` / 空串；空输入在非 golden_three 章段直接回落 ``other``。
分类器保持确定性（不依赖 LLM），方便 context pack 静态装填与单测覆盖。
"""

from __future__ import annotations

from collections.abc import Iterable

GOLDEN_THREE: str = "golden_three"
CLIMAX: str = "climax"
HIGH_POINT: str = "high_point"
COMBAT: str = "combat"
EMOTIONAL: str = "emotional"
SLOW_BUILD: str = "slow_build"
OTHER: str = "other"

SCENE_MODES: tuple[str, ...] = (
    GOLDEN_THREE,
    CLIMAX,
    HIGH_POINT,
    COMBAT,
    EMOTIONAL,
    SLOW_BUILD,
    OTHER,
)

# 优先级从高到低：多命中时取最高优先级的那类。
_PRIORITY_ORDER: tuple[str, ...] = (
    GOLDEN_THREE,
    CLIMAX,
    HIGH_POINT,
    COMBAT,
    EMOTIONAL,
    SLOW_BUILD,
    OTHER,
)

# 关键词命中表。每类至少 5 条，覆盖章节大纲常见措辞。
# 选词原则：避免歧义（如"激情"不列入 emotional，易误伤设定段落）。
_SCENE_KEYWORDS: dict[str, tuple[str, ...]] = {
    CLIMAX: (
        "大结局",
        "终局",
        "最终战",
        "最终决战",
        "决战",
        "高潮",
        "本卷终章",
        "全书高潮",
    ),
    HIGH_POINT: (
        "爽点",
        "反转",
        "打脸",
        "掉马",
        "震撼全场",
        "震撼四座",
        "装逼",
        "装比",
        "碾压",
    ),
    COMBAT: (
        "战斗",
        "对战",
        "交手",
        "厮杀",
        "激战",
        "对决",
        "出手",
        "动手",
        "搏杀",
        "斗法",
        "剑指",
        "拳下",
        "出剑",
        "交锋",
    ),
    EMOTIONAL: (
        "告别",
        "离别",
        "诀别",
        "悲痛",
        "痛哭",
        "心碎",
        "思念",
        "缅怀",
        "忏悔",
        "哀伤",
    ),
    SLOW_BUILD: (
        "日常",
        "铺垫",
        "闲聊",
        "修炼",
        "闲暇",
        "家常",
        "平静",
        "过渡",
        "休整",
        "调息",
    ),
}


def _iter_category_keywords() -> Iterable[tuple[str, tuple[str, ...]]]:
    """按固定顺序迭代 (category, keywords)，方便测试锁定顺序。"""
    for category in _PRIORITY_ORDER:
        if category in (GOLDEN_THREE, OTHER):
            continue
        yield category, _SCENE_KEYWORDS[category]


def _is_golden_three(chapter_no: int) -> bool:
    return 1 <= int(chapter_no or 0) <= 3


def classify_scene(
    chapter_no: int,
    outline_text: str | None = None,
) -> str:
    """返回 scene_mode（固定 7 值之一）。

    参数:
        chapter_no: 章节号；``1/2/3`` 强制返回 ``golden_three``。
        outline_text: 章节大纲（markdown 或纯文本）；``None`` / 空串时仅依赖章节号。

    规则:
        1. ``chapter_no ∈ [1, 2, 3]`` → ``golden_three``
        2. 按 ``_PRIORITY_ORDER`` 顺序扫描关键词，第一个命中的 category 即返回
        3. 全部未命中 → ``other``
    """
    if _is_golden_three(chapter_no):
        return GOLDEN_THREE

    if not outline_text:
        return OTHER

    text = str(outline_text)
    for category, keywords in _iter_category_keywords():
        for kw in keywords:
            if kw and kw in text:
                return category
    return OTHER


def resolve_scene_mode(
    chapter_no: int,
    outline_text: str | None = None,
    explicit_scene_mode: str | None = None,
) -> str:
    """解析最终 scene_mode。

    优先级：

    1. ``explicit_scene_mode`` 显式传入且合法 → 直接使用（支持大纲元数据外部覆盖）
    2. ``chapter_no ∈ [1,3]`` → ``golden_three``（硬覆盖外部输入的非 golden_three 值）
    3. ``classify_scene`` 结果

    显式 ``explicit_scene_mode`` 为未知值时静默回落到 ``classify_scene``，避免拼写
    错误导致 writer / checker 被错误激活。
    """
    chapter_int = int(chapter_no or 0)

    # Golden three 硬覆盖：PRD 明确"chapter ∈ [1,3] 强制激活"。
    if _is_golden_three(chapter_int):
        return GOLDEN_THREE

    if explicit_scene_mode and explicit_scene_mode in SCENE_MODES:
        return explicit_scene_mode

    return classify_scene(chapter_int, outline_text)


__all__ = [
    "GOLDEN_THREE",
    "CLIMAX",
    "HIGH_POINT",
    "COMBAT",
    "EMOTIONAL",
    "SLOW_BUILD",
    "OTHER",
    "SCENE_MODES",
    "classify_scene",
    "resolve_scene_mode",
]
