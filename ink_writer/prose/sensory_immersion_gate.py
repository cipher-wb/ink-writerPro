"""US-007: sensory-immersion-checker 直白模式激活门控。

单源语义：复用 :func:`ink_writer.prose.directness_checker.is_activated` 的判定结果，
让 writer / sensory-immersion-checker / arbitration 三端的"是否直白模式"判定保持
一致——修改激活条件时只需改 directness_checker 一处。

规则（与 writer-agent 顶部 ## Directness Mode 同源）：

1. ``scene_mode ∈ {golden_three, combat, climax, high_point}`` → skip
2. ``scene_mode`` 缺省（``None``）且 ``chapter_no ∈ [1, 2, 3]`` → skip（黄金三章兜底）
3. 其他 → 不 skip，sensory-immersion-checker 正常审查

本模块只暴露判定函数；skipped 时的 JSON 输出形态由 agent spec 约定（见
``ink-writer/agents/sensory-immersion-checker.md`` 顶部"## 直白模式激活门控"）。
"""

from __future__ import annotations

from ink_writer.prose.directness_checker import is_activated as _directness_is_activated

SENSORY_IMMERSION_CHECKER_NAME: str = "sensory-immersion-checker"


def should_skip_sensory_immersion(
    scene_mode: str | None,
    chapter_no: int = 0,
) -> bool:
    """sensory-immersion-checker 是否应在本场景下 skipped。

    返回 ``True`` 时 checker 应短路返回 ``{status: "skipped", pass: true, issues: []}``；
    返回 ``False`` 时执行完整五维审查流程（维度 1-5）。

    与 directness_checker 同源：``chapter_no=0`` + ``scene_mode=None`` 不激活。
    """
    return _directness_is_activated(scene_mode, int(chapter_no or 0))


__all__ = [
    "SENSORY_IMMERSION_CHECKER_NAME",
    "should_skip_sensory_immersion",
]
