"""PRD US-009: L12 对话+动作驱动律 self-check 验证。

验证:
  1. L12 rules 存在於 writer-agent.md spec 中
  2. L12a 违规 fixture（含装逼词+四字格排比）→ colloquial-checker 检测
  3. L12b 违规 fixture（含 abstract_adjectives 词汇）→ directness-checker D3 检测
  4. 合规 fixture → 两个 checker 均通过
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITER_AGENT_SPEC = REPO_ROOT / "ink-writer" / "agents" / "writer-agent.md"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_text() -> str:
    assert WRITER_AGENT_SPEC.exists(), f"writer-agent spec missing: {WRITER_AGENT_SPEC}"
    return WRITER_AGENT_SPEC.read_text(encoding="utf-8")


# Fixture 1: 违 L12a/L10c -- 含四字格排比 + 抽象名词链（触发 colloquial C2+C3）
_L12A_VIOLATION = textwrap.dedent(
    """
    他目光如电，身形似风，出手如龙，回鞘似凤。这一刹那的虚无的缥缈的深邃的感觉，
    像是宿命的孤寂的沧桑在心头萦绕。他缓缓地抬起头，望着远处的苍茫暮色。
    这一切都是那么莫名，那么难以言喻。他淡淡地笑了笑，悄然转身离去。
    那种难以名状的情绪，那种不可思议的力量，在他的胸中汹涌澎湃。
    """
).strip()

# Fixture 2: 违 L12b -- 含 abstract_adjectives 词汇（触发 directness D3）
_L12B_VIOLATION = textwrap.dedent(
    """
    莫名的不安笼罩着他。

    他推开半掩的木门，屋子里积了厚厚的灰。桌上还摆着三封信，封口完好。
    他拉开椅子坐下，把最上面那封信拿起来翻了个面。邮戳的日期是三个月前的。

    虚无的感觉从心底升起，像是一种难以言喻的悲伤。

    "有人来过。"他看见地上的脚印，跟自己的重叠在一起。
    他站起来，把剑扛上肩。脚印通向里屋，门虚掩着。
    """
).strip()

# Fixture 3: 合规 -- 对话+动作驱动，无装逼词，无抽象段首
_L12_COMPLIANT = textwrap.dedent(
    """
    他推开门，走进屋子，看见桌上摆着三封信。
    "你来了。"老人抬起头，把茶杯推到他面前。
    他拉开椅子，坐下，伸手摸了一下最上面那封信的封口。
    "这封是林老板寄的。"老人慢慢开口，"他说账目对不上。"
    他没有立刻回答。他把信封翻了个面，看了看邮戳的日期。
    "我去一趟苏州。"他站起来，把剑扛上肩，"三天内回来。"
    老人点了点头，从抽屉里取出一袋银子，递过去：
    "路上小心，别惹钱帮的人。"
    """
).strip()


def _ratings_from_colloquial(report: dict) -> set[str]:
    """从 colloquial report 的 dimensions list 提取 rating 集合。"""
    dims = report.get("dimensions", [])
    if isinstance(dims, list):
        return {d.get("rating", "") for d in dims if isinstance(d, dict)}
    return set()


# ---------------------------------------------------------------------------
# Spec-level gates
# ---------------------------------------------------------------------------


class TestL12SpecPresence:
    """AC: writer-agent.md 应包含完整的 L12 铁律及其 4 条子律。"""

    def test_l12_section_exists(self, spec_text: str) -> None:
        assert "铁律 L12: 对话+动作驱动律" in spec_text, (
            "writer-agent.md 缺少 L12 铁律"
        )

    @pytest.mark.parametrize("sub_law", [
        "L12a 对话/动作密度",
        "L12b 段首禁抽象",
        "L12c 段首优先级",
        "L12d 每场景必有冲突",
    ])
    def test_l12_sub_laws_present(self, spec_text: str, sub_law: str) -> None:
        assert sub_law in spec_text, (
            f"writer-agent.md 缺少子律: {sub_law}"
        )

    def test_l10c_quad_phrase_ban(self, spec_text: str) -> None:
        assert "禁止四字格排比" in spec_text, (
            "L10c 缺少禁止四字格排比"
        )

    def test_l10c_abstract_chain_ban(self, spec_text: str) -> None:
        assert "禁止抽象名词链" in spec_text, (
            "L10c 缺少禁止抽象名词链"
        )


# ---------------------------------------------------------------------------
# Colloquial-checker: L12a/L10c detection
# ---------------------------------------------------------------------------


class TestL12aViaColloquialChecker:
    """L12a/L10c 违规通过 colloquial-checker 检测。

    L12A_VIOLATION fixture 含四字格排比 + 抽象名词链 + 装逼副词，
    应触发 C2（四字格密度）或 C3（抽象名词链）的 yellow/red。
    """

    def test_l12a_violation_detected(self) -> None:
        """违 L12a fixture → colloquial-checker 不应为全绿。"""
        from ink_writer.prose.colloquial_checker import run_colloquial_check

        report = run_colloquial_check(_L12A_VIOLATION)
        ratings = _ratings_from_colloquial(report)
        non_green = ratings - {"green"}
        assert non_green, (
            f"L12a 违规 fixture 应触发 yellow/red，实际全部 {ratings}"
        )

    def test_l12_compliant_passes_colloquial(self) -> None:
        """合规 fixture → colloquial-checker 应为全绿。"""
        from ink_writer.prose.colloquial_checker import run_colloquial_check

        report = run_colloquial_check(_L12_COMPLIANT)
        ratings = _ratings_from_colloquial(report)
        non_green = ratings - {"green"}
        assert not non_green, (
            f"合规 fixture 不应有非 green 维度，got {non_green}"
        )


# ---------------------------------------------------------------------------
# Directness-checker: L12b detection
# ---------------------------------------------------------------------------


class TestL12bViaDirectnessChecker:
    """L12b = 段首禁止 abstract_adjectives 开篇。

    directness-checker D3 使用 abstract_adjectives 词表检测抽象词密度。
    L12B_VIOLATION fixture 含"莫名"、"虚无"、"难以言喻"等词。
    """

    def test_l12b_violation_detected(self) -> None:
        """违 L12b fixture → directness-checker D3 抽象词密度不应为满分。"""
        from ink_writer.prose.directness_checker import run_directness_check

        report = run_directness_check(
            _L12B_VIOLATION, chapter_no=1, scene_mode="golden_three"
        )
        assert not report.skipped
        d3 = next(
            d for d in report.dimensions if d.key == "D3_abstract_per_100_chars"
        )
        # "莫名" + "虚无" + "难以言喻" 出现在 fixture 中，应触发非满分
        assert d3.score < 10.0, (
            f"L12b 违规 fixture 含 abstract_adjectives 词，D3 score={d3.score} 应 < 10.0"
        )

    def test_l12b_compliant_passes_directness(self) -> None:
        """合规 fixture → directness-checker 应通过。"""
        from ink_writer.prose.directness_checker import run_directness_check

        report = run_directness_check(
            _L12_COMPLIANT, chapter_no=1, scene_mode="golden_three"
        )
        assert not report.skipped
        assert report.severity in {"green", "yellow"}, (
            f"合规 fixture severity={report.severity} 应在 green/yellow"
        )


# ---------------------------------------------------------------------------
# End-to-end: 合规 fixture 应被两个 checker 同时认作通过
# ---------------------------------------------------------------------------


class TestL12E2E:
    """E2E: 合规 fixture 通过 colloquial + directness 双 checker。"""

    def test_compliant_passes_both(self) -> None:
        from ink_writer.prose.colloquial_checker import run_colloquial_check
        from ink_writer.prose.directness_checker import run_directness_check

        # colloquial
        c_report = run_colloquial_check(_L12_COMPLIANT)
        c_ratings = _ratings_from_colloquial(c_report)
        assert not (c_ratings - {"green"}), (
            f"colloquial 合规 fixture 应全 green: {c_ratings}"
        )

        # directness
        d_report = run_directness_check(
            _L12_COMPLIANT, chapter_no=1, scene_mode="golden_three"
        )
        assert not d_report.skipped
        assert d_report.severity in {"green", "yellow"}
        assert d_report.passed is True
