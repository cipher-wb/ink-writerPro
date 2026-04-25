"""protagonist-agency-skeleton-checker — M4 ink-plan 策划期主角能动性骨架检查（spec §3.6）。"""

from ink_writer.checkers.protagonist_agency_skeleton.checker import (
    check_protagonist_agency_skeleton,
)
from ink_writer.checkers.protagonist_agency_skeleton.models import (
    ProtagonistAgencySkeletonReport,
)

__all__ = [
    "ProtagonistAgencySkeletonReport",
    "check_protagonist_agency_skeleton",
]
