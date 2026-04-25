"""tests for orchestrator.collect_blocking_cases scope 过滤（review §二 P1#4）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ink_writer.rewrite_loop.orchestrator import collect_blocking_cases


@dataclass
class _StubScope:
    genre: list[str] = field(default_factory=list)
    chapter: list[str] = field(default_factory=list)


@dataclass
class _StubSeverity:
    value: str = "P2"


@dataclass
class _StubCase:
    case_id: str
    severity: _StubSeverity = field(default_factory=lambda: _StubSeverity("P2"))
    scope: _StubScope = field(default_factory=_StubScope)


@dataclass
class _StubCompliance:
    overall_passed: bool = False
    cases_violated: list[str] = field(default_factory=list)


@dataclass
class _StubChecker:
    blocked: bool = True
    cases_hit: list[str] = field(default_factory=list)


class _StubStore:
    def __init__(self, cases: dict[str, _StubCase]) -> None:
        self._cases = cases

    def load(self, cid: str) -> Any:
        return self._cases[cid]


def test_no_scope_filter_returns_all_cases() -> None:
    """向后兼容：scope_filter=None 时不过滤。"""
    store = _StubStore({
        "C1": _StubCase("C1", scope=_StubScope(genre=["xianxia"])),
        "C2": _StubCase("C2", scope=_StubScope(genre=["history"])),
    })
    compliance = _StubCompliance(cases_violated=["C1", "C2"])
    out = collect_blocking_cases(compliance, [], store, scope_filter=None)
    assert {c.case_id for c in out} == {"C1", "C2"}


def test_scope_filter_drops_off_genre_cases() -> None:
    """scope.genre=['xianxia'] 时，history-only case 被过滤。"""
    store = _StubStore({
        "C1": _StubCase("C1", scope=_StubScope(genre=["xianxia"])),
        "C2": _StubCase("C2", scope=_StubScope(genre=["history"])),
        "C3": _StubCase("C3", scope=_StubScope(genre=[])),  # universal
    })
    compliance = _StubCompliance(cases_violated=["C1", "C2", "C3"])
    out = collect_blocking_cases(
        compliance, [], store, scope_filter={"genre": "xianxia"}
    )
    assert {c.case_id for c in out} == {"C1", "C3"}


def test_scope_filter_universal_case_always_included() -> None:
    """scope.genre 空 → 视作 universal，对任意 genre 都通过。"""
    store = _StubStore({
        "U": _StubCase("U", scope=_StubScope(genre=[], chapter=[])),
    })
    compliance = _StubCompliance(cases_violated=["U"])
    out = collect_blocking_cases(
        compliance, [], store, scope_filter={"genre": "any_unknown_genre"}
    )
    assert [c.case_id for c in out] == ["U"]


def test_scope_filter_chapter_dimension() -> None:
    """同时按 chapter 维度过滤。"""
    store = _StubStore({
        "EARLY": _StubCase("EARLY", scope=_StubScope(chapter=["1-3"])),
        "LATE": _StubCase("LATE", scope=_StubScope(chapter=["100+"])),
    })
    compliance = _StubCompliance(cases_violated=["EARLY", "LATE"])
    out = collect_blocking_cases(
        compliance, [], store, scope_filter={"chapter": "1-3"}
    )
    assert [c.case_id for c in out] == ["EARLY"]


def test_scope_filter_skips_load_failures_silently() -> None:
    """坏 case load 抛错 → 跳过；好 case 仍走 scope 过滤。"""
    class _BadStore:
        def load(self, cid: str) -> Any:
            if cid == "BAD":
                raise RuntimeError("schema invalid")
            return _StubCase(cid, scope=_StubScope(genre=["xianxia"]))

    compliance = _StubCompliance(cases_violated=["BAD", "GOOD"])
    out = collect_blocking_cases(
        compliance, [], _BadStore(), scope_filter={"genre": "xianxia"}
    )
    assert [c.case_id for c in out] == ["GOOD"]
