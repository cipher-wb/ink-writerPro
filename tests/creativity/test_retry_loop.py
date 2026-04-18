"""v16 US-012：retry_loop 单元测试。"""

from __future__ import annotations

import pytest

from ink_writer.creativity.name_validator import (
    Severity,
    ValidationResult,
    Violation,
)
from ink_writer.creativity.retry_loop import (
    CreativityExhaustedError,
    MAX_RETRIES_PER_LEVEL,
    run_quick_mode_with_retry,
)


def _pass_result() -> ValidationResult:
    return ValidationResult(passed=True)


def _fail_result() -> ValidationResult:
    return ValidationResult(
        passed=False,
        violations=[Violation(id="FAKE", severity=Severity.HARD, description="fail")],
    )


class TestFirstTryPass:
    def test_first_try_success(self):
        gen_calls: list[int] = []

        def gen(agg: int):
            gen_calls.append(agg)
            return {"agg": agg}

        report = run_quick_mode_with_retry(
            generate_fn=gen,
            validate_fn=lambda s: _pass_result(),
        )
        assert report.final_aggression == 4
        assert not report.downgraded
        assert len(report.attempts) == 1
        assert gen_calls == [4]


class TestRetryWithinLevel:
    def test_retry_3rd_attempt_passes(self):
        counter = {"n": 0}

        def validate(scheme):
            counter["n"] += 1
            return _pass_result() if counter["n"] == 3 else _fail_result()

        report = run_quick_mode_with_retry(
            generate_fn=lambda agg: {"agg": agg},
            validate_fn=validate,
        )
        assert report.final_aggression == 4
        assert not report.downgraded
        assert len(report.attempts) == 3


class TestDowngrade:
    def test_downgrade_triggers_after_5_fails(self):
        """第 1-5 次（档位 4）全 fail，第 6 次（档位 3）pass → downgraded=True。"""
        counter = {"n": 0}

        def validate(scheme):
            counter["n"] += 1
            # 档位 4 内全 fail；档位 3 首次 pass
            return _pass_result() if counter["n"] > MAX_RETRIES_PER_LEVEL else _fail_result()

        report = run_quick_mode_with_retry(
            generate_fn=lambda agg: {"agg": agg},
            validate_fn=validate,
        )
        assert report.downgraded
        assert report.final_aggression == 3
        # 前 5 attempts 都是 aggression=4
        assert all(a.aggression == 4 for a in report.attempts[:5])
        assert report.attempts[5].aggression == 3

    def test_multi_level_downgrade(self):
        """档位 4/3/2 全 fail，档位 1 首次 pass → final_aggression=1。"""
        counter = {"n": 0}

        def validate(scheme):
            counter["n"] += 1
            # 档位 4/3/2 全 fail = 15 fails；档位 1 第 1 次 pass（第 16 次）
            return _pass_result() if counter["n"] > 15 else _fail_result()

        report = run_quick_mode_with_retry(
            generate_fn=lambda agg: {"agg": agg},
            validate_fn=validate,
        )
        assert report.downgraded
        assert report.final_aggression == 1
        levels = {a.aggression for a in report.attempts}
        assert levels == {4, 3, 2, 1}


class TestExhaustion:
    def test_exhaustion_raises(self):
        def always_fail(scheme):
            return _fail_result()

        with pytest.raises(CreativityExhaustedError):
            run_quick_mode_with_retry(
                generate_fn=lambda agg: {"agg": agg},
                validate_fn=always_fail,
            )


class TestStartAggression:
    def test_start_from_level_2(self):
        report = run_quick_mode_with_retry(
            generate_fn=lambda agg: {"agg": agg},
            validate_fn=lambda s: _pass_result(),
            start_aggression=2,
        )
        assert report.final_aggression == 2
        assert report.attempts[0].aggression == 2

    def test_start_from_level_1_exhaust(self):
        def always_fail(scheme):
            return _fail_result()

        with pytest.raises(CreativityExhaustedError):
            run_quick_mode_with_retry(
                generate_fn=lambda agg: {"agg": agg},
                validate_fn=always_fail,
                start_aggression=1,
            )


class TestReport:
    def test_report_to_dict(self):
        report = run_quick_mode_with_retry(
            generate_fn=lambda agg: {"agg": agg},
            validate_fn=lambda s: _pass_result(),
        )
        d = report.to_dict()
        assert d["final_aggression"] == 4
        assert d["downgraded"] is False
        assert len(d["attempts"]) == 1
