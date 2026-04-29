"""US-007: sensory-immersion-checker 直白模式激活门控。

单源语义：复用 :func:`ink_writer.prose.directness_checker.is_activated` 的判定结果，
让 writer / sensory-immersion-checker / arbitration 三端的"是否直白模式"判定保持
一致——修改激活条件时只需改 directness_checker 一处。

规则（与 writer-agent 顶部 ## Directness Mode 同源）：

US-006 起直白模式全场景激活，因此自动流水线中本 checker 全场景
``skip``，由 directness-checker 接管直白度与感官相关冲突。历史
``scene_mode`` / ``chapter_no`` 参数保留用于日志、阈值桶选择和兼容旧调用方。

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

    与 directness_checker 同源：US-006 起默认全场景激活。
    """
    return _directness_is_activated(scene_mode, int(chapter_no or 0))


__all__ = [
    "SENSORY_IMMERSION_CHECKER_NAME",
    "should_skip_sensory_immersion",
]
