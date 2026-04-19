"""Editor-wisdom coverage metrics: record per-chapter rule-category coverage.

v18 US-002：每次 writer-agent prompt 装配后，把实际注入的规则类别/数量快照写入
`.ink/editor-wisdom-coverage.json`。用于：
- 审计"黄金三章 opening/taboo/hook 各 ≥3"是否真的落地；
- 长期跟踪 SM-7 指标：平均覆盖率 %/章 ≥20（当前 3.9%/章）。

文件 schema（单文件滚动，append-only）：
{
  "total_rules": 364,          # data/editor-wisdom/vector_index 总规则数
  "target_categories": ["opening", "taboo", "hook", ...],
  "chapters": {
    "1": {
      "chapter_no": 1,
      "injected_total": 21,
      "coverage_pct": 5.77,     # injected_total / total_rules * 100
      "by_category": {"opening": 5, "taboo": 4, ...},
      "golden_three_floor_met": true  # 仅 ch1-3 意义；ch4+ 恒 true
    },
    ...
  }
}
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import json
from pathlib import Path
from typing import Any

from ink_writer.editor_wisdom.golden_three import (
    GOLDEN_THREE_FLOOR_CATEGORIES,
    GOLDEN_THREE_FLOOR_PER_CATEGORY,
)
from ink_writer.editor_wisdom.retriever import Rule

DEFAULT_TOTAL_RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "editor-wisdom"
    / "vector_index"
    / "metadata.json"
)


def _load_total_rules(total_rules_path: Path | None = None) -> int:
    path = total_rules_path or DEFAULT_TOTAL_RULES_PATH
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(meta, list):
            return len(meta)
    except Exception:
        pass
    return 0


def _coverage_path(project_root: Path) -> Path:
    return Path(project_root) / ".ink" / "editor-wisdom-coverage.json"


def _load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def compute_coverage(
    rules: list[Rule],
    chapter_no: int,
    *,
    total_rules: int,
    target_categories: tuple[str, ...] = GOLDEN_THREE_FLOOR_CATEGORIES,
    floor: int = GOLDEN_THREE_FLOOR_PER_CATEGORY,
) -> dict[str, Any]:
    """Pure function: compute coverage snapshot for a single chapter injection."""
    by_category: dict[str, int] = {}
    for r in rules:
        by_category[r.category] = by_category.get(r.category, 0) + 1

    injected_total = len(rules)
    coverage_pct = (
        (injected_total / total_rules * 100.0) if total_rules > 0 else 0.0
    )

    if chapter_no <= 3:
        floor_met = all(
            by_category.get(cat, 0) >= floor for cat in target_categories
        )
    else:
        floor_met = True

    return {
        "chapter_no": chapter_no,
        "injected_total": injected_total,
        "coverage_pct": round(coverage_pct, 2),
        "by_category": dict(sorted(by_category.items())),
        "golden_three_floor_met": floor_met,
    }


def record_chapter_coverage(
    *,
    project_root: Path | str,
    chapter_no: int,
    rules: list[Rule],
    total_rules: int | None = None,
    total_rules_path: Path | None = None,
) -> Path:
    """Append/overwrite coverage for `chapter_no` in `.ink/editor-wisdom-coverage.json`.

    Returns the path of the coverage file for callers that want to inspect/log it.
    """
    project_root = Path(project_root)
    path = _coverage_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _load_existing(path)

    if total_rules is None:
        total_rules = _load_total_rules(total_rules_path)

    snapshot = compute_coverage(
        rules,
        chapter_no,
        total_rules=total_rules,
        target_categories=GOLDEN_THREE_FLOOR_CATEGORIES,
        floor=GOLDEN_THREE_FLOOR_PER_CATEGORY,
    )

    data.setdefault("total_rules", total_rules)
    # 总规则数可能随知识库更新变化；以最新为准
    data["total_rules"] = total_rules
    data["target_categories"] = list(GOLDEN_THREE_FLOOR_CATEGORIES)

    chapters = data.setdefault("chapters", {})
    if not isinstance(chapters, dict):
        chapters = {}
        data["chapters"] = chapters
    chapters[str(chapter_no)] = snapshot

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def read_coverage(project_root: Path | str) -> dict[str, Any]:
    """Read the coverage file; returns {} if absent."""
    return _load_existing(_coverage_path(Path(project_root)))


def summarize(project_root: Path | str) -> dict[str, Any]:
    """Aggregate coverage across all recorded chapters. Used by audits / CLI."""
    data = read_coverage(project_root)
    chapters = data.get("chapters", {}) if isinstance(data, dict) else {}
    if not isinstance(chapters, dict) or not chapters:
        return {
            "chapter_count": 0,
            "avg_coverage_pct": 0.0,
            "golden_three_violations": [],
        }

    pcts: list[float] = []
    violations: list[int] = []
    for key, snap in chapters.items():
        if not isinstance(snap, dict):
            continue
        pct = snap.get("coverage_pct", 0.0)
        if isinstance(pct, (int, float)):
            pcts.append(float(pct))
        try:
            ch_no = int(snap.get("chapter_no", key))
        except (TypeError, ValueError):
            continue
        if ch_no <= 3 and not snap.get("golden_three_floor_met", True):
            violations.append(ch_no)

    avg = sum(pcts) / len(pcts) if pcts else 0.0
    return {
        "chapter_count": len(pcts),
        "avg_coverage_pct": round(avg, 2),
        "golden_three_violations": sorted(violations),
    }


def _cli(argv: list[str] | None = None) -> int:
    """`python -m ink_writer.editor_wisdom.coverage_metrics [project_root]` prints summary."""
    import sys

    argv = list(argv) if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.cwd()
    summary = summarize(root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(_cli())
