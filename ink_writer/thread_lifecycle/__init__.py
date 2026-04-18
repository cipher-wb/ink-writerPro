"""Unified thread lifecycle tracker (US-025, F-004).

Single entry point that delegates to the existing foreshadow + plotline
trackers. The old ``ink_writer.foreshadow.tracker`` and
``ink_writer.plotline.tracker`` modules are kept as transitional shims;
they will be removed in a future iteration.
"""

from ink_writer.thread_lifecycle.tracker import (
    UnifiedScanResult,
    scan_all,
)

__all__ = ["UnifiedScanResult", "scan_all"]
