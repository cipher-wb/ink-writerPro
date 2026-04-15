"""Inject editor-wisdom violations into polish-agent and generate patches."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config


@dataclass
class Violation:
    rule_id: str
    quote: str
    severity: str
    fix_suggestion: str


@dataclass
class PolishViolationsSection:
    violations: list[Violation] = field(default_factory=list)
    chapter_no: int = 1

    @property
    def empty(self) -> bool:
        return len(self.violations) == 0

    def to_markdown(self) -> str:
        if self.empty:
            return ""
        hard = [v for v in self.violations if v.severity == "hard"]
        soft = [v for v in self.violations if v.severity == "soft"]
        if not hard and not soft:
            return ""
        lines: list[str] = ["### 编辑智慧违规修复清单（Editor Wisdom Violations）", ""]
        if hard:
            lines.append("**【必须修复 — hard 级违规】**：")
            lines.append("")
            for v in hard:
                lines.append(f"- **[{v.rule_id}]** 引用段落：「{v.quote}」")
                lines.append(f"  - 修复建议：{v.fix_suggestion}")
            lines.append("")
        if soft:
            lines.append("**【建议修复 — soft 级违规】**：")
            lines.append("")
            for v in soft:
                lines.append(f"- **[{v.rule_id}]** 引用段落：「{v.quote}」")
                lines.append(f"  - 修复建议：{v.fix_suggestion}")
            lines.append("")
        return "\n".join(lines)


def build_polish_violations(
    violations_data: list[dict],
    chapter_no: int = 1,
    *,
    config: EditorWisdomConfig | None = None,
) -> PolishViolationsSection:
    """Build the violations section for polish-agent from checker output."""
    if config is None:
        config = load_config()

    if not config.enabled or not config.inject_into.polish:
        return PolishViolationsSection(chapter_no=chapter_no)

    if not violations_data:
        return PolishViolationsSection(chapter_no=chapter_no)

    violations = [
        Violation(
            rule_id=v.get("rule_id", ""),
            quote=v.get("quote", ""),
            severity=v.get("severity", "info"),
            fix_suggestion=v.get("fix_suggestion", ""),
        )
        for v in violations_data
        if v.get("severity") in ("hard", "soft")
    ]

    return PolishViolationsSection(violations=violations, chapter_no=chapter_no)


def generate_patches(
    original_text: str,
    polished_text: str,
    chapter_no: int,
    project_root: str,
) -> str:
    """Generate unified diff and write to chapters/{n}/_patches.md."""
    chapter_dir = os.path.join(project_root, "chapters", str(chapter_no))
    os.makedirs(chapter_dir, exist_ok=True)
    patches_path = os.path.join(chapter_dir, "_patches.md")

    original_lines = original_text.splitlines(keepends=True)
    polished_lines = polished_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        polished_lines,
        fromfile=f"chapters/{chapter_no}/original.md",
        tofile=f"chapters/{chapter_no}/polished.md",
    )
    diff_text = "".join(diff)

    content = f"# 润色变更记录 — 第{chapter_no}章\n\n```diff\n{diff_text}```\n"

    with open(patches_path, "w", encoding="utf-8") as f:
        f.write(content)

    return patches_path
