"""并行检查器管线：asyncio.gather + 首个硬门禁失败立即取消其余。

设计要点：
- 所有 gate 模块封装为 GateSpec（name, fn, is_hard_gate）
- 硬门禁失败立即 cancel 其余任务，触发 polish
- 结果按完成时间排序
- 支持最大并发度控制
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional


class GateStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class CheckerResult:
    name: str
    status: GateStatus
    score: float = 0.0
    elapsed_s: float = 0.0
    is_hard_gate: bool = False
    error: str = ""
    fix_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "score": round(self.score, 2),
            "elapsed_s": round(self.elapsed_s, 2),
            "is_hard_gate": self.is_hard_gate,
            "error": self.error,
        }


@dataclass
class GateSpec:
    """单个检查器规格。

    fn: 同步或异步检查函数，返回 (passed: bool, score: float, fix_prompt: str)
    is_hard_gate: True 时失败立即取消其余检查器
    """
    name: str
    fn: Callable[..., Any]
    is_hard_gate: bool = True
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineReport:
    results: list[CheckerResult] = field(default_factory=list)
    wall_time_s: float = 0.0
    serial_time_s: float = 0.0
    early_terminated: bool = False
    termination_gate: str = ""

    @property
    def all_passed(self) -> bool:
        return all(r.status == GateStatus.PASSED for r in self.results)

    @property
    def hard_failures(self) -> list[CheckerResult]:
        return [
            r for r in self.results
            if r.status == GateStatus.FAILED and r.is_hard_gate
        ]

    @property
    def speedup(self) -> float:
        if self.wall_time_s <= 0:
            return 0.0
        return self.serial_time_s / self.wall_time_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "wall_time_s": round(self.wall_time_s, 2),
            "serial_time_s": round(self.serial_time_s, 2),
            "speedup": round(self.speedup, 2),
            "early_terminated": self.early_terminated,
            "termination_gate": self.termination_gate,
            "results": [r.to_dict() for r in self.results],
        }


class CheckerRunner:
    """并发检查器执行引擎。

    用法:
        runner = CheckerRunner(max_concurrency=4)
        runner.add(GateSpec("hook", hook_check_fn, is_hard_gate=True))
        runner.add(GateSpec("emotion", emotion_check_fn, is_hard_gate=True))
        runner.add(GateSpec("ooc", ooc_check_fn, is_hard_gate=False))
        report = await runner.run()
    """

    def __init__(self, max_concurrency: int = 4):
        self.max_concurrency = max_concurrency
        self._gates: list[GateSpec] = []

    def add(self, gate: GateSpec) -> None:
        self._gates.append(gate)

    def add_many(self, gates: list[GateSpec]) -> None:
        self._gates.extend(gates)

    async def run(self) -> PipelineReport:
        if not self._gates:
            return PipelineReport()

        report = PipelineReport()
        start = time.time()
        cancel_event = asyncio.Event()
        sem = asyncio.Semaphore(self.max_concurrency)

        tasks = [
            asyncio.create_task(
                self._run_gate(gate, cancel_event, sem),
                name=gate.name,
            )
            for gate in self._gates
        ]

        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_EXCEPTION
        )

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        for task in list(done) + list(pending):
            try:
                result = task.result()
            except asyncio.CancelledError:
                gate_name = task.get_name()
                gate_spec = next(
                    (g for g in self._gates if g.name == gate_name), None
                )
                result = CheckerResult(
                    name=gate_name,
                    status=GateStatus.CANCELLED,
                    is_hard_gate=gate_spec.is_hard_gate if gate_spec else False,
                )
            except Exception as e:
                gate_name = task.get_name()
                gate_spec = next(
                    (g for g in self._gates if g.name == gate_name), None
                )
                result = CheckerResult(
                    name=gate_name,
                    status=GateStatus.ERROR,
                    error=str(e),
                    is_hard_gate=gate_spec.is_hard_gate if gate_spec else False,
                )
            report.results.append(result)

        report.wall_time_s = time.time() - start
        report.serial_time_s = sum(r.elapsed_s for r in report.results)

        hard_fails = report.hard_failures
        if hard_fails:
            report.early_terminated = True
            report.termination_gate = hard_fails[0].name

        return report

    async def _run_gate(
        self,
        gate: GateSpec,
        cancel_event: asyncio.Event,
        sem: asyncio.Semaphore,
    ) -> CheckerResult:
        async with sem:
            if cancel_event.is_set():
                return CheckerResult(
                    name=gate.name,
                    status=GateStatus.CANCELLED,
                    is_hard_gate=gate.is_hard_gate,
                )

            start = time.time()
            try:
                if inspect.iscoroutinefunction(gate.fn):
                    fn_result = await gate.fn(**gate.kwargs)
                else:
                    fn_result = await asyncio.to_thread(
                        gate.fn, **gate.kwargs
                    )

                if isinstance(fn_result, tuple) and len(fn_result) >= 2:
                    passed, score = fn_result[0], fn_result[1]
                    fix_prompt = fn_result[2] if len(fn_result) > 2 else ""
                elif isinstance(fn_result, dict):
                    passed = fn_result.get("passed", False)
                    score = fn_result.get("score", 0.0)
                    fix_prompt = fn_result.get("fix_prompt", "")
                elif isinstance(fn_result, bool):
                    passed = fn_result
                    score = 1.0 if passed else 0.0
                    fix_prompt = ""
                else:
                    passed = bool(fn_result)
                    score = 1.0 if passed else 0.0
                    fix_prompt = ""

                elapsed = time.time() - start
                status = GateStatus.PASSED if passed else GateStatus.FAILED

                result = CheckerResult(
                    name=gate.name,
                    status=status,
                    score=score,
                    elapsed_s=elapsed,
                    is_hard_gate=gate.is_hard_gate,
                    fix_prompt=fix_prompt,
                )

                if status == GateStatus.FAILED and gate.is_hard_gate:
                    cancel_event.set()

                return result

            except Exception as e:
                elapsed = time.time() - start
                result = CheckerResult(
                    name=gate.name,
                    status=GateStatus.ERROR,
                    elapsed_s=elapsed,
                    is_hard_gate=gate.is_hard_gate,
                    error=str(e),
                )
                if gate.is_hard_gate:
                    cancel_event.set()
                return result
