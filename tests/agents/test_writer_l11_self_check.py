"""US-009: writer-agent L12 对话+动作驱动律 self-check 测试。

验证 writer-agent.md 中 L12a-L12d 四子律的规范存在性 +
基本的违例/合规文本自检逻辑。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

_WRITER_AGENT_SPEC = (
    Path(__file__).resolve().parents[2]
    / "ink-writer" / "agents" / "writer-agent.md"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spec_text() -> str:
    return _WRITER_AGENT_SPEC.read_text(encoding="utf-8")


_L11_DIALOGUE_ACTION_PROSE = textwrap.dedent("""
"你确定要走？"老陈把烟袋往桌上一磕，烟灰弹了半桌。
他点了点头，走到门口，弯腰系紧鞋带。手上动作不快，但每个结都拉得死紧。
"东西都收拾好了？"老陈又问。
他没回头，只从肩上把包袱往上耸了耸。"三天前就收好了。"
老陈没再说话。屋里只剩炉子上水壶咕嘟咕嘟的声音。他推开门，冷风灌进来。
门槛外面一片漆黑。
""").strip()

_L12_VIOLATION_STATIC_TEXT = textwrap.dedent("""
时光荏苒，转眼已是三年。他站在院子里，看着那棵槐树发呆。叶子还是那样绿，影子还是那样斜。
他想起很多事。那些事像是别人的故事，又像是自己的。说不清道不明，只是觉得胸口闷闷的。
如果没有那场雨，如果没有那个人，一切会不会不一样？他不知道。也许这个问题永远没有答案。
又过了一盏茶的工夫，天色暗了下来。远处有炊烟升起，细细的，淡淡的。
""").strip()


# ---------------------------------------------------------------------------
# Section 1: L12 spec presence (AC 1-4)
# ---------------------------------------------------------------------------

class TestL12SpecPresence:
    """Verify L12 dialogue+action driving iron law exists in writer-agent.md."""

    def test_l12_heading_exists(self, spec_text: str) -> None:
        assert "铁律 L12: 对话+动作驱动律" in spec_text or "L12: 对话+动作驱动律" in spec_text

    def test_l12a_dialogue_action_density(self, spec_text: str) -> None:
        assert "L12a" in spec_text
        assert "200 字" in spec_text

    def test_l12b_paragraph_opening_ban(self, spec_text: str) -> None:
        assert "L12b" in spec_text
        assert "段首" in spec_text

    def test_l12c_paragraph_priority(self, spec_text: str) -> None:
        assert "L12c" in spec_text
        assert "优先级" in spec_text or "对话 > 动作" in spec_text

    def test_l12d_scene_conflict(self, spec_text: str) -> None:
        assert "L12d" in spec_text
        assert "冲突" in spec_text

    def test_l12_completeness_list_includes_l12(self, spec_text: str) -> None:
        """The completeness list at bottom must reference L12."""
        assert "L12" in spec_text


# ---------------------------------------------------------------------------
# Section 2: Self-check heuristic logic
# ---------------------------------------------------------------------------

class TestL12SelfCheck:
    """Verify basic text-level heuristics for L12 rules."""

    def test_l12a_dialogue_action_coverage_pass(self) -> None:
        """Dialogue-driven prose has good dialogue+action coverage."""
        # Count dialogue lines (lines with 「 or " or ')
        dialogue_lines = sum(
            1 for line in _L11_DIALOGUE_ACTION_PROSE.split("\n")
            if '"' in line or "「" in line or "」" in line
        )
        assert dialogue_lines >= 2, "dialogue-driven fixture should have ≥2 dialogue lines"

    def test_l12b_no_abstract_opening_in_dialogue_prose(self) -> None:
        """Dialogue prose should not start paragraphs with abstract nouns."""
        abstract_openers = {"时光", "岁月", "宿命", "命运", "寂寞", "孤独", "虚无", "永恒"}
        for para in _L11_DIALOGUE_ACTION_PROSE.split("\n"):
            para = para.strip()
            if not para or para.startswith('"') or para.startswith("「"):
                continue
            first_word = para[:2] if len(para) >= 2 else para
            assert first_word not in abstract_openers, (
                f"Paragraph should not open with abstract word: {para[:30]}..."
            )

    def test_l12b_violation_fixture_opens_with_abstract(self) -> None:
        """The violation fixture should demonstrate L12b violation."""
        first_para = _L12_VIOLATION_STATIC_TEXT.strip().split("\n")[0]
        # "时光荏苒" is a classic abstract opening
        assert "时光" in first_para or "荏苒" in first_para, (
            "Violation fixture should open with abstract phrasing"
        )

    def test_l12a_violation_fixture_lacks_dialogue(self) -> None:
        """The violation fixture should have minimal/no dialogue."""
        has_dialogue = any(
            '"' in line or "「" in line
            for line in _L12_VIOLATION_STATIC_TEXT.split("\n")
        )
        assert not has_dialogue, (
            "Violation fixture should demonstrate lack of dialogue/action"
        )


# ---------------------------------------------------------------------------
# Section 3: anti-detection-writing.md cleanup (AC 4-5)
# ---------------------------------------------------------------------------

class TestAntiDetectionWritingCleanup:

    @pytest.fixture(scope="class")
    def adw_text(self) -> str:
        adw_path = (
            Path(__file__).resolve().parents[2]
            / "ink-writer" / "skills" / "ink-write"
            / "references" / "anti-detection-writing.md"
        )
        return adw_path.read_text(encoding="utf-8")

    def test_no_promotion_of_em_dash(self, adw_text: str) -> None:
        """The file should not encourage em-dash usage."""
        # It should warn against, not encourage
        if "破折号" in adw_text:
            # If mentions em-dash, it should be in a warning context
            idx = adw_text.find("破折号")
            context = adw_text[max(0, idx - 50):idx + 100]
            assert "禁止" in context or "监控" in context or "零容忍" in context or "避免" in context, (
                "破折号 mention should be in warning/prohibition context"
            )

    def test_anti_detection_references_exist(self, adw_text: str) -> None:
        """Basic integrity: file has expected sections."""
        assert "情感" in adw_text or "节奏" in adw_text
        assert len(adw_text) > 500, "anti-detection-writing.md should be substantial"


# ---------------------------------------------------------------------------
# Section 4: writer-agent.md must NOT promote em-dash (regression guard)
# ---------------------------------------------------------------------------

class TestWriterAgentNoEmDashPromotion:

    def test_writer_agent_does_not_promote_em_dash(self, spec_text: str) -> None:
        """writer-agent.md must not encourage em-dash usage — ZT_EM_DASH blocks it."""
        if "破折号" in spec_text:
            idx = spec_text.find("破折号")
            context = spec_text[max(0, idx - 50):idx + 120]
            assert "禁止" in context or "零容忍" in context or "阻断" in context, (
                "writer-agent.md must not promote em-dash; "
                "any mention of 破折号 must be in prohibition context"
            )
