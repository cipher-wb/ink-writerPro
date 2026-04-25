"""protagonist-agency-checker — M3 章节级主角能动性检查（spec §4.2 + Q8）。"""

from ink_writer.checkers.protagonist_agency.checker import check_protagonist_agency
from ink_writer.checkers.protagonist_agency.models import AgencyReport

__all__ = ["AgencyReport", "check_protagonist_agency"]
