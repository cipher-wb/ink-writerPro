"""v16 US-008：5/10/20/50/200 分层检查点的三文档源 + 代码源一致性校验。

受审对象：
1. ``ink_writer/core/cli/checkpoint_utils.determine_checkpoint`` — 代码源。
2. ``ink-writer/skills/ink-auto/SKILL.md`` — 用户可见规格。
3. ``ink-writer/scripts/ink-auto.sh`` 顶部注释 + echo 打印。
4. ``README.md`` FAQ — 对外宣传口径。

规则：**5 个层级（5/10/20/50/200）的数字必须在所有 4 份来源出现**。
本测试不强制解析具体结构化表格（避免脆弱），仅做"数字锚点 + 关键字"的弱
一致性断言，既能防回退又不卡死正常排版调整。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

INK_AUTO_SH = ROOT / "ink-writer" / "scripts" / "ink-auto.sh"
INK_AUTO_SKILL = ROOT / "ink-writer" / "skills" / "ink-auto" / "SKILL.md"
README = ROOT / "README.md"
MACRO_SKILL = ROOT / "ink-writer" / "skills" / "ink-macro-review" / "SKILL.md"

TIERS = (5, 10, 20, 50, 200)


def _read(p: Path) -> str:
    assert p.exists(), f"{p} 不存在"
    return p.read_text(encoding="utf-8")


class TestCodeSourceOfTruth:
    def test_checkpoint_utils_returns_expected_tier_for_each_mark(self) -> None:
        """checkpoint_utils.determine_checkpoint 在 5/10/20/50/200 各档返回正确级别。"""
        from ink_writer.core.cli.checkpoint_utils import determine_checkpoint

        # 5 章：仅 review
        lvl = determine_checkpoint(5)
        assert lvl.review is True
        assert lvl.audit is None and lvl.macro is None

        # 10 章：+ audit quick
        lvl = determine_checkpoint(10)
        assert lvl.review is True and lvl.audit == "quick" and lvl.macro is None

        # 20 章：+ audit standard + Tier2
        lvl = determine_checkpoint(20)
        assert lvl.audit == "standard" and lvl.macro == "Tier2"

        # 50 章：+ Tier2 完整
        lvl = determine_checkpoint(50)
        assert lvl.audit == "standard" and lvl.macro == "Tier2" and lvl.disambig is True

        # 200 章：+ Tier3
        lvl = determine_checkpoint(200)
        assert lvl.macro == "Tier3"

    def test_non_multiple_of_5_returns_empty_level(self) -> None:
        from ink_writer.core.cli.checkpoint_utils import determine_checkpoint

        for ch in (1, 3, 7, 11, 13, 17, 19, 23, 47, 49):
            lvl = determine_checkpoint(ch)
            assert lvl.review is False, f"章 {ch} 不该触发任何检查点"


class TestDocSourcesMentionAllTiers:
    @pytest.mark.parametrize("path", [INK_AUTO_SH, INK_AUTO_SKILL, README])
    def test_every_tier_number_present(self, path: Path) -> None:
        """ink-auto.sh / ink-auto SKILL.md / README 必须提到 5/10/20/50/200 全部 5 档。"""
        content = _read(path)
        missing = []
        for t in TIERS:
            # 匹配"每 N 章"/"N 章"/"(N,...)"/数字单独出现，放宽以兼容各种文风
            if not re.search(rf"\b{t}\b", content):
                missing.append(t)
        assert not missing, f"{path.name} 缺少 tier 数字: {missing}"

    def test_macro_review_skill_mentions_20_50_200(self) -> None:
        """ink-macro-review SKILL.md 的"与 ink-auto 集成"段必须提到 20/50/200。"""
        content = _read(MACRO_SKILL)
        # 定位"与 ink-auto 的集成"段
        idx = content.find("与 ink-auto 的集成")
        assert idx >= 0, "ink-macro-review SKILL.md 未找到 '与 ink-auto 的集成' 段"
        section = content[idx: idx + 1500]
        for t in (20, 50, 200):
            assert str(t) in section, (
                f"ink-macro-review SKILL.md '与 ink-auto' 段未提及 tier {t}"
            )


class TestNoContradictionBetweenSkillAndImpl:
    def test_macro_review_skill_no_shadow_default_language(self) -> None:
        """'Tier2 默认每 50 章外部触发 + ink-auto 每 20 章内部触发浅版' 必须一致。

        US-008 显式修复此矛盾；如果 SKILL.md 再次把 20/50 说成互斥语义，测试会 fail。
        """
        content = _read(MACRO_SKILL)
        # 关键词：'浅版' 与 '完整版' 必须同时存在（解释差异）
        assert "浅版" in content and "完整版" in content, (
            "ink-macro-review SKILL.md 必须解释 Tier2 '浅版 vs 完整版' 的 20/50 章差异"
        )
