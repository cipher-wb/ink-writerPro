"""naming-style-checker — M4 ink-init 策划期角色起名风格检查（spec §3.3）。"""

from ink_writer.checkers.naming_style.checker import check_naming_style
from ink_writer.checkers.naming_style.models import NamingStyleReport

__all__ = ["NamingStyleReport", "check_naming_style"]
