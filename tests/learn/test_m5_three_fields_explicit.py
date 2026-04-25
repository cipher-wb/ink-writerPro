"""tests for auto_case / promote 显式赋 M5 三字段（review §二 P1#5）。"""

from __future__ import annotations

from datetime import UTC, datetime

from ink_writer.learn.auto_case import _make_learn_case
from ink_writer.learn.promote import _make_promote_case


def test_make_learn_case_sets_three_m5_fields_explicitly() -> None:
    case = _make_learn_case(
        case_id="CASE-LEARN-0001",
        pattern=("CASE-2026-0010", "CASE-2026-0011"),
        occurrences=2,
        sample_chapters=["Ch001", "Ch002"],
        now=datetime.now(UTC),
    )
    # 三字段必须显式赋默认值，而不是依赖 dataclass 缺省（避免 dashboard 聚合
    # 误判"无复发数据" vs "已复发但记录丢失"）。
    assert case.recurrence_history == []
    assert case.meta_rule_id is None
    assert case.sovereign is False


def test_make_promote_case_sets_three_m5_fields_explicitly() -> None:
    case = _make_promote_case(
        case_id="CASE-PROMOTE-0001",
        text="主角行动力不足",
        kind="failure",
        count=5,
        now=datetime.now(UTC),
    )
    assert case.recurrence_history == []
    assert case.meta_rule_id is None
    assert case.sovereign is False
