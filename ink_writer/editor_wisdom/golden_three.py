"""Golden-three enhancement: stricter editor-wisdom checks for chapters 1-3."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config
from ink_writer.editor_wisdom.retriever import Rule

GOLDEN_THREE_CATEGORIES = frozenset({"opening", "hook", "golden_finger", "character"})

# v18 US-002：黄金三章（ch1-3）分类别召回下限。
# opening/taboo/hook 三类编辑智慧为过审核心因子，无论向量检索排序如何，
# 必须保证每类 ≥GOLDEN_THREE_FLOOR_PER_CATEGORY 条进入 writer prompt。
# 定义在此模块（而非 writer_injection）以避免 coverage_metrics ↔ writer_injection 循环引用。
GOLDEN_THREE_FLOOR_CATEGORIES: tuple[str, ...] = ("opening", "taboo", "hook")
GOLDEN_THREE_FLOOR_PER_CATEGORY: int = 3


@dataclass
class GoldenThreeCheckResult:
    chapter_no: int
    score: float
    threshold: float
    passed: bool
    violations: list[dict] = field(default_factory=list)
    summary: str = ""


@dataclass
class GoldenThreeReport:
    chapters: list[GoldenThreeCheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(ch.passed for ch in self.chapters)

    def to_markdown(self) -> str:
        lines = [
            "# 黄金三章编辑智慧审查报告",
            "",
            "## 总览",
            "",
            "| 章节 | 得分 | 阈值 | 结果 |",
            "|------|------|------|------|",
        ]
        for ch in self.chapters:
            status = "✅ PASS" if ch.passed else "❌ FAIL"
            lines.append(f"| 第{ch.chapter_no}章 | {ch.score:.2f} | {ch.threshold:.2f} | {status} |")

        lines.append("")
        overall = "全部通过" if self.all_passed else "存在未通过章节"
        lines.append(f"**综合结果**: {overall}")
        lines.append("")

        for ch in self.chapters:
            lines.append(f"## 第{ch.chapter_no}章")
            lines.append("")
            if ch.passed:
                lines.append(f"得分 {ch.score:.2f} >= 阈值 {ch.threshold:.2f}，通过。")
            else:
                lines.append(f"得分 {ch.score:.2f} < 阈值 {ch.threshold:.2f}，未通过。")
            lines.append("")
            if ch.violations:
                lines.append("### 违规项")
                lines.append("")
                for v in ch.violations:
                    lines.append(f"- **[{v.get('rule_id', '?')}]** ({v.get('severity', '?')})")
                    lines.append(f"  - 引用：「{v.get('quote', '')}」")
                    lines.append(f"  - 建议：{v.get('fix_suggestion', '')}")
                lines.append("")
            if ch.summary:
                lines.append(f"**评语**: {ch.summary}")
                lines.append("")

        return "\n".join(lines)


def retrieve_golden_three_rules(
    query: str,
    retriever: object,
    k: int = 5,
) -> list[Rule]:
    """Retrieve rules restricted to golden-three categories."""
    all_rules: list[Rule] = []
    seen_ids: set[str] = set()

    for category in sorted(GOLDEN_THREE_CATEGORIES):
        rules = retriever.retrieve(query, k=k, category=category)
        for r in rules:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                all_rules.append(r)

    all_rules.sort(key=lambda r: -r.score)
    return all_rules[:k]


def check_golden_three_chapter(
    chapter_text: str,
    chapter_no: int,
    checker_result: dict,
    config: EditorWisdomConfig | None = None,
) -> GoldenThreeCheckResult:
    """Evaluate a single chapter's checker result against the golden-three threshold."""
    if config is None:
        config = load_config()

    threshold = config.golden_three_threshold if chapter_no <= 3 else config.hard_gate_threshold
    score = checker_result.get("score", 0.0)

    return GoldenThreeCheckResult(
        chapter_no=chapter_no,
        score=score,
        threshold=threshold,
        passed=score >= threshold,
        violations=checker_result.get("violations", []),
        summary=checker_result.get("summary", ""),
    )


def generate_report(
    results: list[GoldenThreeCheckResult],
    project_root: str,
) -> str:
    """Generate reports/golden-three-editor-wisdom.md and return the path."""
    report = GoldenThreeReport(chapters=results)
    report_dir = os.path.join(project_root, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "golden-three-editor-wisdom.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report.to_markdown())

    return report_path
