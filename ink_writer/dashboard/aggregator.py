"""M5 治理指标聚合 — 4 大指标 + dry-run 通过率 + 切换推荐。

Pure helpers — no I/O side effects. Designed for the dashboard ``/api/m5-overview``
route and the ``ink dashboard report --week N`` weekly markdown generator
(see :mod:`ink_writer.dashboard.weekly_report`, US-006).

Schema contracts (spec §13.1)::

    compute_recurrence_rate(case_store_iter)        -> float
    compute_repair_speed(case_store_iter)            -> float (M5 placeholder 7.0)
    compute_editor_score_trend(base_dir=...)         -> list[{date, score, book}]
    compute_checker_accuracy(sample_dir=...)         -> float (M5 placeholder 0.0)
    compute_m3_dry_run_pass_rate(base_dir=...)       -> tuple[int, float]
    compute_m4_dry_run_pass_rate(base_dir=...)       -> tuple[int, float]
    recommend_dry_run_switch(counter, pass_rate, ...) -> Literal["continue","investigate","switch"]
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import yaml

from ink_writer.case_library.models import Case, CaseStatus

_DEFAULT_EDITOR_REVIEWS_DIR = Path("data/editor_reviews")
_DEFAULT_CHECKER_SAMPLES_DIR = Path("data/checker_accuracy_samples")
_M3_COUNTER_FILENAME = ".dry_run_counter"
_M4_COUNTER_FILENAME = ".planning_dry_run_counter"


def compute_recurrence_rate(*, case_store_iter: Iterable[Case]) -> float:
    """Recurrence rate = regressed / (resolved + regressed).

    Returns ``0.0`` when there are no resolved/regressed cases (avoids the
    spurious ``100% recurrence`` reading on a fresh library).
    """
    total = 0
    recurrent = 0
    for case in case_store_iter:
        if case.status not in (CaseStatus.RESOLVED, CaseStatus.REGRESSED):
            continue
        total += 1
        if case.recurrence_history:
            recurrent += 1
    if total == 0:
        return 0.0
    return recurrent / total


def compute_repair_speed(*, case_store_iter: Iterable[Case]) -> float:
    """Average days from case ingestion to resolution.

    M5 placeholder returning ``7.0``. The ``Case`` schema does not yet carry
    ``resolved_at`` (only ``ingested_at``); a real implementation needs that
    field — slated for the post-M5 quality-validation milestone.
    """
    # Touch the iterable to keep the contract symmetric with the other
    # case_store_iter consumers (drains generators just like
    # compute_recurrence_rate). The value itself is a constant placeholder.
    for _ in case_store_iter:
        pass
    return 7.0


def compute_editor_score_trend(
    *, base_dir: Path = _DEFAULT_EDITOR_REVIEWS_DIR
) -> list[dict[str, Any]]:
    """Scan ``base_dir/*.yaml`` for editor scores; return chronological list.

    Each yaml file is expected to contain ``{book, date, score}`` (or a
    ``reviews:`` list of such). Missing dir → empty list. Malformed files
    are skipped silently (dashboard must never crash on bad input).
    """
    base = Path(base_dir)
    if not base.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.yaml")):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            continue
        if doc is None:
            continue
        if isinstance(doc, dict) and "reviews" in doc:
            book = doc.get("book") or path.stem
            for item in doc.get("reviews") or []:
                if not isinstance(item, dict):
                    continue
                entries.append(
                    {
                        "date": item.get("date"),
                        "score": item.get("score"),
                        "book": item.get("book") or book,
                    }
                )
        elif isinstance(doc, dict):
            entries.append(
                {
                    "date": doc.get("date"),
                    "score": doc.get("score"),
                    "book": doc.get("book") or path.stem,
                }
            )
    entries.sort(key=lambda e: (str(e.get("date") or ""), str(e.get("book") or "")))
    return entries


def compute_checker_accuracy(
    *, sample_dir: Path = _DEFAULT_CHECKER_SAMPLES_DIR
) -> float:
    """Checker accuracy placeholder — returns 0.0 until samples land.

    Real implementation will compare checker verdicts against editor
    annotations under ``data/checker_accuracy_samples/<book>/...``. Until
    those land we surface a deterministic 0.0 so the dashboard renders.
    """
    base = Path(sample_dir)
    if not base.is_dir():
        return 0.0
    return 0.0


def recommend_dry_run_switch(
    *,
    counter: int,
    pass_rate: float,
    threshold_runs: int = 5,
    threshold_pass_rate: float = 0.60,
) -> Literal["continue", "investigate", "switch"]:
    """Suggest the next dry-run posture.

    - ``continue``: fewer than ``threshold_runs`` observation runs so far.
    - ``investigate``: enough runs but pass rate below ``threshold_pass_rate``.
    - ``switch``: ready to flip to real blocking.
    """
    if counter < threshold_runs:
        return "continue"
    if pass_rate < threshold_pass_rate:
        return "investigate"
    return "switch"


def _read_counter(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError:
        return 0
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def compute_m3_dry_run_pass_rate(*, base_dir: Path) -> tuple[int, float]:
    """Return ``(counter, pass_rate)`` for chapter-level dry-run.

    Reads ``<base_dir>/.dry_run_counter`` and walks every
    ``<base_dir>/<book>/chapters/*.evidence.json`` treating
    ``outcome == 'delivered'`` as a pass.
    """
    base = Path(base_dir)
    counter = _read_counter(base / _M3_COUNTER_FILENAME)
    total = 0
    passed = 0
    if base.is_dir():
        for book_dir in base.iterdir():
            if not book_dir.is_dir():
                continue
            chapters_dir = book_dir / "chapters"
            if not chapters_dir.is_dir():
                continue
            for evidence_path in chapters_dir.glob("*.evidence.json"):
                try:
                    with open(evidence_path, encoding="utf-8") as fh:
                        doc = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                total += 1
                if doc.get("outcome") == "delivered":
                    passed += 1
    pass_rate = (passed / total) if total else 0.0
    return counter, pass_rate


def compute_m4_dry_run_pass_rate(*, base_dir: Path) -> tuple[int, float]:
    """Return ``(counter, pass_rate)`` for planning-stage dry-run.

    Reads ``<base_dir>/.planning_dry_run_counter`` and walks every
    ``<base_dir>/<book>/planning_evidence_chain.json``; each ``stages`` entry
    counts as one observation; ``outcome != 'blocked'`` is a pass.
    """
    base = Path(base_dir)
    counter = _read_counter(base / _M4_COUNTER_FILENAME)
    total = 0
    passed = 0
    if base.is_dir():
        for book_dir in base.iterdir():
            if not book_dir.is_dir():
                continue
            planning_path = book_dir / "planning_evidence_chain.json"
            if not planning_path.exists():
                continue
            try:
                with open(planning_path, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            for stage in doc.get("stages") or []:
                total += 1
                if stage.get("outcome") != "blocked":
                    passed += 1
    pass_rate = (passed / total) if total else 0.0
    return counter, pass_rate
