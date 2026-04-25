"""golden-finger-spec-checker — M4 ink-init 策划期金手指规格检查（spec §3.2）。"""

from ink_writer.checkers.golden_finger_spec.checker import check_golden_finger_spec
from ink_writer.checkers.golden_finger_spec.models import GoldenFingerSpecReport

__all__ = ["GoldenFingerSpecReport", "check_golden_finger_spec"]
