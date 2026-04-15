"""Tests for polish-agent editor-wisdom violation injection and patch generation."""

from __future__ import annotations

import os
import tempfile

from ink_writer.editor_wisdom.config import EditorWisdomConfig, InjectInto
from ink_writer.editor_wisdom.polish_injection import (
    PolishViolationsSection,
    Violation,
    build_polish_violations,
    generate_patches,
)


def _make_violation(
    rule_id: str = "EW-0001",
    quote: str = "测试引用段落",
    severity: str = "hard",
    fix_suggestion: str = "修复建议",
) -> dict:
    return {
        "rule_id": rule_id,
        "quote": quote,
        "severity": severity,
        "fix_suggestion": fix_suggestion,
    }


class TestPolishViolationsSection:
    def test_empty_section(self):
        section = PolishViolationsSection()
        assert section.empty
        assert section.to_markdown() == ""

    def test_hard_violations_in_markdown(self):
        violations = [Violation("EW-0001", "问题段落", "hard", "修改方案")]
        section = PolishViolationsSection(violations=violations)
        md = section.to_markdown()
        assert "必须修复" in md
        assert "EW-0001" in md
        assert "问题段落" in md
        assert "修改方案" in md

    def test_soft_violations_in_markdown(self):
        violations = [Violation("EW-0002", "建议段落", "soft", "优化方案")]
        section = PolishViolationsSection(violations=violations)
        md = section.to_markdown()
        assert "建议修复" in md
        assert "建议段落" in md

    def test_info_violations_omitted(self):
        violations = [Violation("EW-0003", "信息段落", "info", "仅供参考")]
        section = PolishViolationsSection(violations=violations)
        assert not section.empty
        md = section.to_markdown()
        assert md == ""

    def test_hard_before_soft(self):
        violations = [
            Violation("EW-0002", "软问题", "soft", "软修复"),
            Violation("EW-0001", "硬问题", "hard", "硬修复"),
        ]
        section = PolishViolationsSection(violations=violations)
        md = section.to_markdown()
        hard_pos = md.index("硬问题")
        soft_pos = md.index("软问题")
        assert hard_pos < soft_pos

    def test_mixed_severities(self):
        violations = [
            Violation("EW-0001", "硬A", "hard", "修A"),
            Violation("EW-0002", "软B", "soft", "修B"),
            Violation("EW-0003", "信息C", "info", "修C"),
        ]
        section = PolishViolationsSection(violations=violations)
        md = section.to_markdown()
        assert "硬A" in md
        assert "软B" in md
        assert "信息C" not in md

    def test_quote_and_fix_suggestion_in_output(self):
        violations = [
            Violation("EW-0010", "他猛然抬头望向天空", "hard", "改为通过角色感知描写天空变化"),
        ]
        section = PolishViolationsSection(violations=violations)
        md = section.to_markdown()
        assert "他猛然抬头望向天空" in md
        assert "改为通过角色感知描写天空变化" in md


class TestBuildPolishViolations:
    def test_disabled_config(self):
        config = EditorWisdomConfig(enabled=False)
        result = build_polish_violations(
            [_make_violation()], config=config
        )
        assert result.empty

    def test_polish_inject_disabled(self):
        config = EditorWisdomConfig(inject_into=InjectInto(polish=False))
        result = build_polish_violations(
            [_make_violation()], config=config
        )
        assert result.empty

    def test_empty_violations(self):
        config = EditorWisdomConfig()
        result = build_polish_violations([], config=config)
        assert result.empty

    def test_basic_build(self):
        violations = [
            _make_violation(rule_id="EW-0001", severity="hard"),
            _make_violation(rule_id="EW-0002", severity="soft"),
        ]
        config = EditorWisdomConfig()
        result = build_polish_violations(violations, chapter_no=5, config=config)
        assert not result.empty
        assert len(result.violations) == 2
        assert result.chapter_no == 5

    def test_info_filtered_out(self):
        violations = [
            _make_violation(severity="hard"),
            _make_violation(rule_id="EW-0002", severity="info"),
        ]
        config = EditorWisdomConfig()
        result = build_polish_violations(violations, config=config)
        assert len(result.violations) == 1
        assert result.violations[0].severity == "hard"

    def test_all_info_returns_empty_markdown(self):
        violations = [_make_violation(severity="info")]
        config = EditorWisdomConfig()
        result = build_polish_violations(violations, config=config)
        assert result.empty

    def test_chapter_no_preserved(self):
        config = EditorWisdomConfig()
        result = build_polish_violations(
            [_make_violation()], chapter_no=42, config=config
        )
        assert result.chapter_no == 42


class TestGeneratePatches:
    def test_creates_patches_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original = "第一段原文。\n第二段原文。\n第三段原文。\n"
            polished = "第一段原文。\n第二段修改后。\n第三段原文。\n"
            path = generate_patches(original, polished, chapter_no=1, project_root=tmpdir)
            assert os.path.exists(path)
            assert path.endswith("_patches.md")

    def test_diff_contains_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original = "不变行。\n原始内容要改。\n不变行结尾。\n"
            polished = "不变行。\n修改后的内容。\n不变行结尾。\n"
            path = generate_patches(original, polished, chapter_no=3, project_root=tmpdir)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "原始内容要改" in content
            assert "修改后的内容" in content

    def test_no_changes_produces_empty_diff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            text = "完全相同的文本。\n"
            path = generate_patches(text, text, chapter_no=1, project_root=tmpdir)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "```diff\n```" in content

    def test_chapter_dir_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_patches("a\n", "b\n", chapter_no=99, project_root=tmpdir)
            assert os.path.isdir(os.path.join(tmpdir, "chapters", "99"))

    def test_integration_three_violations_diff(self):
        """Integration test: given 3 synthetic violations, assert the diff touches
        paragraphs containing at least 2 of the 3 quoted passages."""
        quote_1 = "萧尘猛然站起身来，双目之中精光闪烁"
        quote_2 = "那柄长剑在月光下泛着幽幽寒光"
        quote_3 = "他的内心深处涌起一股莫名的悲伤"

        original = (
            f"风起云涌之际，{quote_1}，仿佛要将一切看穿。\n\n"
            f"远处山巅之上，{quote_2}，似乎在等待主人的召唤。\n\n"
            f"夜深人静之时，{quote_3}，那是对往昔岁月的追忆。\n\n"
            "第四段无关内容，保持不变。\n"
        )

        polished = (
            "风起云涌之际，萧尘的肩膀微微一震，瞳孔骤然收缩，仿佛要将一切看穿。\n\n"
            f"远处山巅之上，{quote_2}，似乎在等待主人的召唤。\n\n"
            "夜深人静之时，胸口那团说不清的东西又翻搅起来，像被人攥住了心脏。\n\n"
            "第四段无关内容，保持不变。\n"
        )

        violations_data = [
            _make_violation(rule_id="EW-0010", quote=quote_1, severity="hard",
                           fix_suggestion="避免'猛然'等AI味词汇，用具体身体反应替代"),
            _make_violation(rule_id="EW-0011", quote=quote_2, severity="soft",
                           fix_suggestion="月光寒光属于陈词滥调，换用更独特的意象"),
            _make_violation(rule_id="EW-0012", quote=quote_3, severity="hard",
                           fix_suggestion="禁止'内心深处涌起'等心理直述，改用身体化情感"),
        ]

        config = EditorWisdomConfig()
        section = build_polish_violations(violations_data, chapter_no=1, config=config)
        assert not section.empty
        md = section.to_markdown()
        quotes_in_md = 0
        for v in violations_data:
            if v["severity"] in ("hard", "soft"):
                assert v["quote"] in md
                assert v["fix_suggestion"] in md
                quotes_in_md += 1
        assert quotes_in_md >= 2, (
            f"Expected at least 2 violation quotes in markdown, got {quotes_in_md}"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_patches(original, polished, chapter_no=1, project_root=tmpdir)
            with open(path, encoding="utf-8") as f:
                diff_content = f.read()

            touched_quotes = 0
            for q in [quote_1, quote_2, quote_3]:
                if q in diff_content:
                    touched_quotes += 1
            assert touched_quotes >= 2, (
                f"Expected diff to touch at least 2 of 3 quoted passages, "
                f"but only touched {touched_quotes}"
            )
