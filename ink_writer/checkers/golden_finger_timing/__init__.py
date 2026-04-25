"""golden-finger-timing-checker — M4 ink-plan 策划期金手指出场时机检查（spec §3.5）。

regex 主 + LLM 回退判断金手指是否在前 3 章 summary 出现：
  - regex 命中即通过（不调 LLM）；
  - regex miss 时调 LLM 二次判断（语义匹配）。
硬阻断 block_threshold=1.0（passed→1.0 / failed→0.0）。
"""

from ink_writer.checkers.golden_finger_timing.checker import check_golden_finger_timing
from ink_writer.checkers.golden_finger_timing.models import GoldenFingerTimingReport

__all__ = ["GoldenFingerTimingReport", "check_golden_finger_timing"]
