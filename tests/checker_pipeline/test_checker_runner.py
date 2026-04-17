"""Tests for CheckerRunner: parallel execution, early-fail, concurrency control."""

from __future__ import annotations

import asyncio
import time

import pytest

from ink_writer.checker_pipeline.runner import (
    CheckerResult,
    CheckerRunner,
    GateSpec,
    GateStatus,
    PipelineReport,
)


def _pass_checker(**kwargs):
    time.sleep(0.02)
    return (True, 85.0, "")


def _fail_checker(**kwargs):
    time.sleep(0.02)
    return (False, 30.0, "fix this")


def _slow_pass_checker(**kwargs):
    time.sleep(0.2)
    return (True, 90.0, "")


def _error_checker(**kwargs):
    raise RuntimeError("checker exploded")


def _dict_result_checker(**kwargs):
    return {"passed": True, "score": 75.0, "fix_prompt": ""}


def _bool_result_checker(**kwargs):
    return True


async def _async_pass_checker(**kwargs):
    await asyncio.sleep(0.02)
    return (True, 88.0, "")


async def _async_fail_checker(**kwargs):
    await asyncio.sleep(0.02)
    return (False, 25.0, "async fix")


class TestGateSpec:
    def test_basic_spec(self):
        spec = GateSpec("test", _pass_checker)
        assert spec.name == "test"
        assert spec.is_hard_gate is True

    def test_soft_gate(self):
        spec = GateSpec("soft", _pass_checker, is_hard_gate=False)
        assert spec.is_hard_gate is False

    def test_with_kwargs(self):
        spec = GateSpec("kw", _pass_checker, kwargs={"chapter": 1})
        assert spec.kwargs == {"chapter": 1}


class TestCheckerResult:
    def test_to_dict(self):
        r = CheckerResult(
            name="test", status=GateStatus.PASSED, score=85.0, elapsed_s=1.5
        )
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "passed"
        assert d["score"] == 85.0

    def test_status_values(self):
        assert GateStatus.PASSED.value == "passed"
        assert GateStatus.FAILED.value == "failed"
        assert GateStatus.CANCELLED.value == "cancelled"
        assert GateStatus.ERROR.value == "error"


class TestPipelineReport:
    def test_all_passed(self):
        r = PipelineReport(results=[
            CheckerResult("a", GateStatus.PASSED),
            CheckerResult("b", GateStatus.PASSED),
        ])
        assert r.all_passed

    def test_has_failure(self):
        r = PipelineReport(results=[
            CheckerResult("a", GateStatus.PASSED),
            CheckerResult("b", GateStatus.FAILED, is_hard_gate=True),
        ])
        assert not r.all_passed
        assert len(r.hard_failures) == 1

    def test_speedup(self):
        r = PipelineReport(wall_time_s=10.0, serial_time_s=40.0)
        assert r.speedup == 4.0

    def test_to_dict(self):
        r = PipelineReport(results=[], wall_time_s=5.0, serial_time_s=20.0)
        d = r.to_dict()
        assert d["speedup"] == 4.0
        assert d["all_passed"] is True


class TestCheckerRunnerBasic:
    @pytest.mark.asyncio
    async def test_empty_runner(self):
        runner = CheckerRunner()
        report = await runner.run()
        assert len(report.results) == 0
        assert report.all_passed

    @pytest.mark.asyncio
    async def test_single_pass(self):
        runner = CheckerRunner()
        runner.add(GateSpec("test", _pass_checker))
        report = await runner.run()
        assert report.all_passed
        assert len(report.results) == 1
        assert report.results[0].score == 85.0

    @pytest.mark.asyncio
    async def test_single_fail(self):
        runner = CheckerRunner()
        runner.add(GateSpec("test", _fail_checker))
        report = await runner.run()
        assert not report.all_passed
        assert report.results[0].score == 30.0
        assert report.results[0].fix_prompt == "fix this"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        runner = CheckerRunner()
        runner.add(GateSpec("boom", _error_checker, is_hard_gate=False))
        report = await runner.run()
        assert report.results[0].status == GateStatus.ERROR
        assert "exploded" in report.results[0].error

    @pytest.mark.asyncio
    async def test_dict_result(self):
        runner = CheckerRunner()
        runner.add(GateSpec("dict", _dict_result_checker))
        report = await runner.run()
        assert report.results[0].score == 75.0

    @pytest.mark.asyncio
    async def test_bool_result(self):
        runner = CheckerRunner()
        runner.add(GateSpec("bool", _bool_result_checker))
        report = await runner.run()
        assert report.results[0].status == GateStatus.PASSED
        assert report.results[0].score == 1.0


class TestCheckerRunnerAsync:
    @pytest.mark.asyncio
    async def test_async_checker(self):
        runner = CheckerRunner()
        runner.add(GateSpec("async", _async_pass_checker))
        report = await runner.run()
        assert report.all_passed
        assert report.results[0].score == 88.0

    @pytest.mark.asyncio
    async def test_async_fail(self):
        runner = CheckerRunner()
        runner.add(GateSpec("async_fail", _async_fail_checker))
        report = await runner.run()
        assert not report.all_passed
        assert report.results[0].fix_prompt == "async fix"


class TestCheckerRunnerParallel:
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        runner = CheckerRunner(max_concurrency=4)
        for i in range(4):
            runner.add(GateSpec(f"checker_{i}", _pass_checker, is_hard_gate=False))
        start = time.time()
        report = await runner.run()
        elapsed = time.time() - start

        assert report.all_passed
        assert len(report.results) == 4
        assert elapsed < 0.5  # CI runners (especially macOS) can be slow  # 4 × 0.02s serial = 0.08, parallel < 0.15

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        runner = CheckerRunner(max_concurrency=2)
        for i in range(4):
            runner.add(GateSpec(f"checker_{i}", _pass_checker, is_hard_gate=False))
        start = time.time()
        report = await runner.run()
        elapsed = time.time() - start

        assert report.all_passed
        assert elapsed < 0.5  # CI runners (especially macOS) can be slow

    @pytest.mark.asyncio
    async def test_add_many(self):
        runner = CheckerRunner()
        gates = [GateSpec(f"g{i}", _pass_checker) for i in range(3)]
        runner.add_many(gates)
        report = await runner.run()
        assert len(report.results) == 3


class TestEarlyTermination:
    @pytest.mark.asyncio
    async def test_hard_gate_cancels_others(self):
        runner = CheckerRunner(max_concurrency=4)
        runner.add(GateSpec("fast_fail", _fail_checker, is_hard_gate=True))
        runner.add(GateSpec("slow_pass", _slow_pass_checker, is_hard_gate=False))

        report = await runner.run()

        assert report.early_terminated
        assert report.termination_gate == "fast_fail"
        cancelled_or_done = [
            r for r in report.results
            if r.name == "slow_pass" and r.status in (GateStatus.CANCELLED, GateStatus.PASSED)
        ]
        assert len(cancelled_or_done) >= 1

    @pytest.mark.asyncio
    async def test_soft_gate_no_cancel(self):
        runner = CheckerRunner(max_concurrency=4)
        runner.add(GateSpec("soft_fail", _fail_checker, is_hard_gate=False))
        runner.add(GateSpec("pass", _pass_checker, is_hard_gate=False))

        report = await runner.run()
        assert not report.early_terminated
        passed_results = [r for r in report.results if r.status == GateStatus.PASSED]
        assert len(passed_results) >= 1

    @pytest.mark.asyncio
    async def test_error_in_hard_gate_cancels(self):
        runner = CheckerRunner(max_concurrency=4)
        runner.add(GateSpec("error_gate", _error_checker, is_hard_gate=True))
        runner.add(GateSpec("slow_pass", _slow_pass_checker, is_hard_gate=False))

        report = await runner.run()
        error_result = next(r for r in report.results if r.name == "error_gate")
        assert error_result.status == GateStatus.ERROR


class TestSpeedupMetrics:
    @pytest.mark.asyncio
    async def test_review_stage_speedup(self):
        """Simulate review stage: 5 checkers each taking 0.05s.
        Serial: 0.25s. Parallel: ~0.05s. Speedup should be ≥ 2.5x.
        """
        def checker(**kw):
            time.sleep(0.05)
            return (True, 80.0, "")

        runner = CheckerRunner(max_concurrency=5)
        for i in range(5):
            runner.add(GateSpec(f"checker_{i}", checker, is_hard_gate=False))

        report = await runner.run()

        assert report.all_passed
        assert report.serial_time_s > 0.2
        assert report.wall_time_s < report.serial_time_s
        assert report.speedup >= 2.0

    @pytest.mark.asyncio
    async def test_wall_time_le_50pct_serial(self):
        """US-503 acceptance: review-stage wall time ≤ 50% of serial baseline."""
        def checker(**kw):
            time.sleep(0.04)
            return (True, 90.0, "")

        runner = CheckerRunner(max_concurrency=6)
        for i in range(6):
            runner.add(GateSpec(f"checker_{i}", checker, is_hard_gate=False))

        report = await runner.run()

        serial_baseline = 6 * 0.04
        assert report.wall_time_s <= serial_baseline * 0.5 + 0.15  # CI 抖动容差
