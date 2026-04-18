"""Unified thread-lifecycle tracker (US-025, F-004).

Historically the project shipped two independent trackers:

    - ``ink_writer.foreshadow.tracker`` —伏笔 (foreshadow) overdue / silent scan
    - ``ink_writer.plotline.tracker``   — 主/支/暗线 inactivity scan

Both walk the same ``plot_thread_registry`` SQLite table and serve the same
consumer (Context Agent Board 7, ink-plan injection). US-025 consolidates them
behind a single entry point: ``scan_all(db_path, current_chapter)``.

This module is the **authoritative** surface. The two original tracker modules
are kept as transitional shims (they still export the dataclasses and
helper functions used by existing tests / callers). They will be removed in a
future iteration — do not add new call sites to them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ink_writer.foreshadow.config import ForeshadowLifecycleConfig
from ink_writer.foreshadow.tracker import (
    ForeshadowScanResult,
    scan_foreshadows,
)
from ink_writer.plotline.config import PlotlineLifecycleConfig
from ink_writer.plotline.tracker import (
    PlotlineScanResult,
    scan_plotlines,
)


@dataclass
class UnifiedScanResult:
    """Aggregated result from a single ``scan_all`` invocation."""

    current_chapter: int
    foreshadow: ForeshadowScanResult
    plotline: PlotlineScanResult
    alerts: list[str] = field(default_factory=list)

    @property
    def total_active(self) -> int:
        """Sum of active foreshadows + active plotlines."""
        return self.foreshadow.total_active + self.plotline.total_active

    @property
    def has_forced_actions(self) -> bool:
        """True iff at least one forced payoff / advance was scheduled."""
        return bool(self.foreshadow.forced_payoffs) or bool(
            self.plotline.forced_advances
        )


def scan_all(
    db_path: str | Path,
    current_chapter: int,
    *,
    foreshadow_config: Optional[ForeshadowLifecycleConfig] = None,
    plotline_config: Optional[PlotlineLifecycleConfig] = None,
) -> UnifiedScanResult:
    """Run both foreshadow + plotline lifecycle scans and merge the results.

    Parameters
    ----------
    db_path:
        Path to the project's ``index.db``. Both underlying scanners read
        the ``plot_thread_registry`` table from it.
    current_chapter:
        Chapter number being planned / drafted. Used to compute overdue /
        inactive gaps for both scanners.
    foreshadow_config / plotline_config:
        Optional pre-built configs. When ``None`` the underlying scanners
        load their respective defaults via ``load_config()``.

    Returns
    -------
    UnifiedScanResult
        Aggregate containing both sub-results plus a merged ``alerts`` list
        (foreshadow alerts first, then plotline alerts). The underlying
        ``ForeshadowScanResult`` / ``PlotlineScanResult`` objects are exposed
        unchanged so existing consumers can keep using their richer APIs.
    """
    foreshadow_result = scan_foreshadows(
        db_path, current_chapter, config=foreshadow_config
    )
    plotline_result = scan_plotlines(
        db_path, current_chapter, config=plotline_config
    )

    merged_alerts: list[str] = []
    merged_alerts.extend(foreshadow_result.alerts)
    merged_alerts.extend(plotline_result.alerts)

    return UnifiedScanResult(
        current_chapter=current_chapter,
        foreshadow=foreshadow_result,
        plotline=plotline_result,
        alerts=merged_alerts,
    )


__all__ = ["UnifiedScanResult", "scan_all"]
