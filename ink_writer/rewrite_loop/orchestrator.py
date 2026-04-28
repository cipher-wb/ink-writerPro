"""rewrite_loop orchestrator — write → check → block → polish (1 case/round) → ... (spec §5.2).

US-008 (M3 P1)：

* 主循环最多 ``cfg.rewrite_loop.max_rounds + 1`` 次 self_check（含初始 r0 + 最多 3 轮重写）。
* 每轮收集阻断 case：``compliance.cases_violated`` ∪ ``checker.cases_hit``，按 severity P0→P3
  排序，每轮仅修 ``blocking_cases[0]``（spec §5.2 Q3）。
* 全部清零 → outcome=``delivered`` 退出；超过 max_rounds 仍有阻断 → outcome=``needs_human_review``，
  把所有版本（r0..r3 共 4 版）保留在 ``history`` 供 US-010 写盘。
* 所有 LLM 依赖（self_check_fn / checkers_fn / polish_fn）通过 callable 注入便于单元测试 mock。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ink_writer.evidence_chain import EvidenceChain

_SEVERITY_ORDER = ["P0", "P1", "P2", "P3"]


@dataclass
class RewriteLoopResult:
    """run_rewrite_loop 返回值（spec §5.2 + Q4）。

    history 含初始 r0 与每轮重写产物，用于 US-010 needs_human_review 4 版保留。
    """

    final_text: str
    evidence: EvidenceChain
    outcome: str  # "delivered" | "needs_human_review"
    rounds: int = 0
    history: list[str] = field(default_factory=list)


def _case_in_scope(case: Any, scope_filter: dict | None) -> bool:
    """判断 case 是否落在 ``scope_filter`` 限定的 genre/chapter 范围内。

    规则（review §二 P1#4）：
      * scope_filter 为 None 或空 → 所有 case 通过（向后兼容）。
      * case.scope.genre 为空列表 → universal case，对任意 genre 都通过。
      * case.scope.genre 非空 → 必须包含 scope_filter['genre']。
      * chapter 同理：case.scope.chapter 空 → 通过；非空 → 必须包含或匹配 scope_filter['chapter']。
    """
    if not scope_filter:
        return True
    case_scope = getattr(case, "scope", None)
    if case_scope is None:
        return True

    genre_filter = scope_filter.get("genre")
    if genre_filter:
        case_genres = list(getattr(case_scope, "genre", []) or [])
        if case_genres and genre_filter not in case_genres:
            return False

    chapter_filter = scope_filter.get("chapter")
    if chapter_filter:
        case_chapters = list(getattr(case_scope, "chapter", []) or [])
        if case_chapters and chapter_filter not in case_chapters:
            return False

    return True


def collect_blocking_cases(
    compliance: Any,
    check_results: list[Any],
    case_store: Any,
    scope_filter: dict | None = None,
) -> list[Any]:
    """聚合 + 去重 + scope 过滤 + 按 severity 排序阻断 case（spec §5.4 + Q3 + review P1#4）。

    Args:
        compliance: writer_self_check.ComplianceReport-like，读 ``cases_violated``
            （仅当 ``overall_passed=False``）。
        check_results: list of CheckerOutcome-like，读 ``cases_hit``（仅当 ``blocked=True``）。
        case_store: CaseStore 风格对象，``load(case_id)`` 返回 case 实例。
        scope_filter: 可选 ``{"genre": str, "chapter": str}`` 限定召回范围；防止
            悬疑书被推荐言情 case，也降低 410 case 全量比对的噪声。None 时不过滤
            （向后兼容）。

    缺失/load 失败的 case 静默跳过；scope 不匹配的 case 也静默跳过。
    """

    all_ids: list[str] = []
    if not getattr(compliance, "overall_passed", True):
        all_ids.extend(getattr(compliance, "cases_violated", []) or [])
    for r in check_results:
        if getattr(r, "blocked", False):
            all_ids.extend(getattr(r, "cases_hit", []) or [])

    seen: set[str] = set()
    unique_cases: list[Any] = []
    for cid in all_ids:
        if cid in seen:
            continue
        seen.add(cid)
        try:
            case = case_store.load(cid)
        except Exception:  # noqa: BLE001 — 一个坏 case 不应阻断整个聚合
            continue
        if not _case_in_scope(case, scope_filter):
            continue
        unique_cases.append(case)

    def _severity_idx(case: Any) -> int:
        sev = getattr(getattr(case, "severity", None), "value", "P3")
        return _SEVERITY_ORDER.index(sev) if sev in _SEVERITY_ORDER else 99

    unique_cases.sort(key=_severity_idx)
    return unique_cases


def run_rewrite_loop(
    *,
    book: str,
    chapter: str,
    chapter_text: str,
    cfg: dict,
    case_store: Any,
    self_check_fn: Callable[..., Any],
    checkers_fn: Callable[..., list[Any]],
    polish_fn: Callable[..., str],
    is_dry_run: bool,
    base_dir: Path | None = None,  # noqa: ARG001 — US-010 写 history 时启用
    scope_filter: dict | None = None,
) -> RewriteLoopResult:
    """主循环（spec §5.2）。

    流程：r0 self_check + checkers → 若无阻断 case → ``delivered``；否则 polish 第一个 case
    （severity 排序）→ rN+1。最多 ``max_rounds`` 轮重写后仍阻断 → ``needs_human_review``。
    """

    max_rounds = int(cfg["rewrite_loop"]["max_rounds"])
    evidence = EvidenceChain(book=book, chapter=chapter, dry_run=is_dry_run)
    current_text = chapter_text
    history: list[str] = [current_text]

    # Compute debug run_id once for this rewrite_loop invocation (used by all T17/T18/T19 blocks).
    try:
        import time as _time
        _debug_run_id = f"rewrite-{book}-ch{chapter}-{int(_time.time())}"
    except Exception:
        _debug_run_id = "rewrite-unknown"

    # --- debug invariant: writer_word_count (T17) ---
    try:
        from pathlib import Path as _Path
        from ink_writer.debug.collector import Collector as _DebugCollector
        from ink_writer.debug.config import load_config as _load_debug_cfg
        from ink_writer.debug.invariants.writer_word_count import check as _check_word_count

        _project_root = _Path.cwd()
        _dbg_cfg = _load_debug_cfg(
            global_yaml_path=_Path("config/debug.yaml"),
            project_root=_project_root,
        )
        if _dbg_cfg.master_enabled and _dbg_cfg.layers.layer_c_invariants \
                and _dbg_cfg.invariants.get("writer_word_count", {}).get("enabled", True):
            try:
                _chapter_num = int(chapter)
            except (ValueError, TypeError):
                _chapter_num = None
            try:
                from ink_writer.core.preferences import load_word_limits as _load_word_limits
                _min_words, _ = _load_word_limits(_project_root)
            except Exception:
                _min_words = 2200  # qidian default fallback
            _inc = _check_word_count(
                text=current_text,
                run_id=_debug_run_id,
                chapter=_chapter_num,
                min_words=_min_words,
                skill="ink-write",
            )
            if _inc is not None:
                _DebugCollector(_dbg_cfg).record(_inc)
    except Exception:
        pass  # Debug must never break the writing loop.

    last_check_results: list[Any] = []

    for round_idx in range(max_rounds + 1):
        compliance = self_check_fn(
            chapter_text=current_text, book=book, chapter=chapter
        )
        evidence.record_self_check(
            round_idx=round_idx,
            compliance_report={
                "rule_compliance": getattr(compliance, "rule_compliance", 0.0),
                "chunk_borrowing": getattr(compliance, "chunk_borrowing", None),
                "cases_addressed": list(
                    getattr(compliance, "cases_addressed", []) or []
                ),
                "cases_violated": list(
                    getattr(compliance, "cases_violated", []) or []
                ),
                "overall_passed": bool(
                    getattr(compliance, "overall_passed", False)
                ),
                "notes": getattr(compliance, "notes", "") or "",
            },
        )

        check_results = checkers_fn(
            chapter_text=current_text, book=book, chapter=chapter
        ) or []
        last_check_results = check_results

        # --- debug invariant: review_dimensions (T19) ---
        try:
            from pathlib import Path as _Path
            from ink_writer.debug.collector import Collector as _DebugCollector
            from ink_writer.debug.config import load_config as _load_debug_cfg
            from ink_writer.debug.invariants.review_dimensions import check as _check_review_dims

            _project_root = _Path.cwd()
            _dbg_cfg = _load_debug_cfg(
                global_yaml_path=_Path("config/debug.yaml"),
                project_root=_project_root,
            )
            if _dbg_cfg.master_enabled and _dbg_cfg.layers.layer_c_invariants \
                    and _dbg_cfg.invariants.get("review_dimensions", {}).get("enabled", True):
                _min_dims = (
                    _dbg_cfg.invariants.get("review_dimensions", {})
                    .get("min_dimensions_per_skill", {}).get("ink-review", 7)
                )
                try:
                    _chapter_num = int(chapter)
                except (ValueError, TypeError):
                    _chapter_num = None
                # Synthesize report from check_results: each checker_id is a "dimension".
                _synth_report = {
                    "dimensions": {
                        getattr(r, "checker_id", f"unknown_{i}"): getattr(r, "score", 0)
                        for i, r in enumerate(check_results)
                    },
                }
                _inc = _check_review_dims(
                    report=_synth_report,
                    skill="ink-review",
                    run_id=_debug_run_id,
                    chapter=_chapter_num,
                    min_dimensions=_min_dims,
                )
                if _inc is not None:
                    _DebugCollector(_dbg_cfg).record(_inc)
        except Exception:
            pass

        # TODO(spec §13 Q2): wire checker_router (Layer B) once orchestrator's check_results
        # carry per-violation detail (severity/kind/message). Currently they only carry
        # checker_id + score + cases_hit, which doesn't match checker_router's input shape.

        evidence.record_checkers(
            [
                {
                    "id": getattr(r, "checker_id", "?"),
                    "score": getattr(r, "score", 0),
                    "blocked": getattr(r, "blocked", False),
                    "would_have_blocked": getattr(r, "would_have_blocked", False),
                    "cases_hit": list(getattr(r, "cases_hit", []) or []),
                }
                for r in check_results
            ]
        )

        blocking_cases = collect_blocking_cases(
            compliance, check_results, case_store, scope_filter=scope_filter
        )
        if not blocking_cases:
            evidence.outcome = "delivered"
            return RewriteLoopResult(
                final_text=current_text,
                evidence=evidence,
                outcome="delivered",
                rounds=round_idx + 1,
                history=history,
            )

        if round_idx >= max_rounds:
            evidence.outcome = "needs_human_review"
            return RewriteLoopResult(
                final_text=current_text,
                evidence=evidence,
                outcome="needs_human_review",
                rounds=round_idx + 1,
                history=history,
            )

        target = blocking_cases[0]
        case_id = getattr(target, "case_id", "")
        failure_pattern = getattr(target, "failure_pattern", None)
        failure_description = getattr(failure_pattern, "description", "") or ""
        observable = list(getattr(failure_pattern, "observable", []) or [])

        _pre_polish_text = current_text
        current_text = polish_fn(
            chapter_text=current_text,
            case_id=case_id,
            case_failure_description=failure_description,
            case_observable=observable,
            related_chunks=None,  # M3 期 chunk_borrowing deferred（spec §3.5 风险 8）
        )
        # --- debug invariant: polish_diff (T18) ---
        try:
            from pathlib import Path as _Path
            from ink_writer.debug.collector import Collector as _DebugCollector
            from ink_writer.debug.config import load_config as _load_debug_cfg
            from ink_writer.debug.invariants.polish_diff import check as _check_polish_diff

            _project_root = _Path.cwd()
            _dbg_cfg = _load_debug_cfg(
                global_yaml_path=_Path("config/debug.yaml"),
                project_root=_project_root,
            )
            _inv_cfg = _dbg_cfg.invariants.get("polish_diff", {})
            if _dbg_cfg.master_enabled and _dbg_cfg.layers.layer_c_invariants \
                    and _inv_cfg.get("enabled", True):
                try:
                    _chapter_num = int(chapter)
                except (ValueError, TypeError):
                    _chapter_num = None
                _inc = _check_polish_diff(
                    before=_pre_polish_text,
                    after=current_text,
                    run_id=_debug_run_id,
                    chapter=_chapter_num,
                    min_diff_chars=_inv_cfg.get("min_diff_chars", 50),
                )
                if _inc is not None:
                    _DebugCollector(_dbg_cfg).record(_inc)
        except Exception:
            pass
        evidence.record_polish(
            round_idx=round_idx + 1,
            case_id=case_id,
            result="rewrite_for_single_case",
        )
        history.append(current_text)

    # 兜底：理论上不会走到这里，max_rounds 内的 round_idx >= max_rounds 分支已 return
    evidence.outcome = "needs_human_review"
    _ = last_check_results  # 保留以便未来扩展观测
    return RewriteLoopResult(
        final_text=current_text,
        evidence=evidence,
        outcome="needs_human_review",
        rounds=max_rounds + 1,
        history=history,
    )
