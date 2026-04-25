"""protagonist-motive-checker — M4 ink-init 策划期主角动机检查（spec §3.4）。"""

from ink_writer.checkers.protagonist_motive.checker import check_protagonist_motive
from ink_writer.checkers.protagonist_motive.models import ProtagonistMotiveReport

__all__ = ["ProtagonistMotiveReport", "check_protagonist_motive"]
