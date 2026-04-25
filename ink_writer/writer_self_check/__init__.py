"""M3 writer-self-check：写完比对 rule_compliance + cases_addressed/violated。

spec §3 + Q1+Q2+Q15。chunk_borrowing 在 M3 期始终为 None
（M2 chunks deferred 兼容；spec §3.5 风险 8）。
"""

from __future__ import annotations

from ink_writer.writer_self_check.checker import writer_self_check
from ink_writer.writer_self_check.models import ComplianceReport

__all__ = ["ComplianceReport", "writer_self_check"]
