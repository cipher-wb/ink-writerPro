"""conflict-skeleton-checker — M3 章节级冲突骨架检查（spec §4.1 + Q6+Q7）。"""

from ink_writer.checkers.conflict_skeleton.checker import check_conflict_skeleton
from ink_writer.checkers.conflict_skeleton.models import ConflictReport

__all__ = ["ConflictReport", "check_conflict_skeleton"]
