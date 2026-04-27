"""Spec-level gates for writer-agent Directness Mode (US-006).

These tests assert that the writer-agent.md prompt has the Directness Mode
section wired correctly — activation conditions, the five hard principles,
the L10b/L10e 暂挂 protocol, and the top-20 blacklist exemplars embedded
as 反例. The real behavioural coupling (scene_mode → checker activation)
lives elsewhere (US-005 directness-checker, US-007 sensory coupling);
this file keeps the spec honest so the prompt doesn't silently drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.prose.blacklist_loader import clear_cache, load_blacklist

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITER_AGENT_SPEC = REPO_ROOT / "ink-writer" / "agents" / "writer-agent.md"


@pytest.fixture(scope="module")
def spec_text() -> str:
    assert WRITER_AGENT_SPEC.exists(), f"writer-agent spec missing: {WRITER_AGENT_SPEC}"
    return WRITER_AGENT_SPEC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Section presence + activation contract
# ---------------------------------------------------------------------------


def test_directness_mode_section_present(spec_text: str) -> None:
    assert "## Directness Mode" in spec_text, (
        "writer-agent.md must declare a top-level ## Directness Mode section (US-006)"
    )
    # Section must sit before ## 写作核心思维 — prompt-top prominence per PRD.
    dm_idx = spec_text.index("## Directness Mode")
    core_idx = spec_text.index("## 写作核心思维")
    assert dm_idx < core_idx, (
        "Directness Mode must appear before '写作核心思维' to satisfy PRD 'prompt 顶部高优先级标注'"
    )


def test_activation_conditions_declared(spec_text: str) -> None:
    """Activation must mention chapter ∈ [1,3] OR scene_mode ∈ {combat, climax, high_point}."""
    assert "chapter_no ∈ [1, 2, 3]" in spec_text or "chapter_no ∈ [1,2,3]" in spec_text, (
        "Directness Mode must declare chapter ∈ [1,3] activation explicitly"
    )
    for mode in ("combat", "climax", "high_point"):
        assert mode in spec_text, f"Activation must name scene_mode = {mode!r}"


# ---------------------------------------------------------------------------
# Five hard principles + L10 coupling
# ---------------------------------------------------------------------------


_REQUIRED_PRINCIPLE_MARKERS = (
    "剧情推进",       # 原则 1：每句服务三选一
    "角色心理",
    "冲突升级",
    "抽象形容词堆叠",  # 原则 2
    "空境描写段",     # 原则 3（PRD 用词）
    "高级比喻",       # 原则 4
    "强动词",         # 原则 5
    "具体名词",
)


@pytest.mark.parametrize("marker", _REQUIRED_PRINCIPLE_MARKERS)
def test_five_hard_principles_enumerated(spec_text: str, marker: str) -> None:
    assert marker in spec_text, (
        f"Directness Mode 五条硬原则缺少关键词 {marker!r}；检查 writer-agent.md 是否漏条"
    )


def test_l10b_l10e_scene_aware_marked(spec_text: str) -> None:
    """L10b/L10e bullets must note they are scene-aware and yield to colloquial-checker (US-009)."""
    for anchor in ("L10b 感官锚点法则", "L10e 感官主导模态法则"):
        idx = spec_text.find(anchor)
        assert idx >= 0, f"writer-agent.md must still declare bullet `{anchor}`"
        line_end = spec_text.find("\n", idx)
        heading_line = spec_text[idx:line_end]
        assert "colloquial-checker" in heading_line, (
            f"`{anchor}` 段落首行必须交叉引用 colloquial-checker（US-009 要求）"
        )


def test_l10b_l10e_decoupling_declared(spec_text: str) -> None:
    """The top-level Directness Mode must have an L10b/L10e 暂挂 subsection (US-006 AC 6)."""
    assert "L10b/L10e 暂挂" in spec_text or "L10b / L10e 暂挂" in spec_text, (
        "Directness Mode 必须包含 L10b/L10e 暂挂协议小节（US-006 AC 6）"
    )
    assert "sensory-immersion-checker" in spec_text, (
        "Directness Mode 暂挂协议需指向 sensory-immersion-checker 的 skipped 行为（US-007 协同）"
    )


# ---------------------------------------------------------------------------
# Top-20 blacklist exemplars embedded
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def top_twenty_blacklist_words() -> tuple[str, ...]:
    """Return first 20 entries from abstract_adjectives (YAML-definition order)."""
    clear_cache()
    bundle = load_blacklist()
    words = tuple(entry.word for entry in bundle.abstract_adjectives[:20])
    assert len(words) == 20, "abstract_adjectives must ship with ≥20 entries"
    return words


def test_top_twenty_blacklist_words_present(
    spec_text: str, top_twenty_blacklist_words: tuple[str, ...]
) -> None:
    """Every one of the top-20 高危词 must appear verbatim in writer-agent.md."""
    missing = [w for w in top_twenty_blacklist_words if w not in spec_text]
    assert not missing, (
        f"Directness Mode 反例清单遗漏 top-20 禁区词: {missing}; "
        "prompt 必须显式列出 US-003 黑名单前 20 条（PRD AC 5）"
    )


def test_blacklist_asset_path_referenced(spec_text: str) -> None:
    """Spec must point readers to the canonical YAML for the full 107-entry list."""
    assert "ink-writer/assets/prose-blacklist.yaml" in spec_text, (
        "Directness Mode 需指向 `ink-writer/assets/prose-blacklist.yaml` 作为完整黑名单来源"
    )


# ---------------------------------------------------------------------------
# Negative guards
# ---------------------------------------------------------------------------


def test_directness_mode_does_not_remove_existing_iron_laws(spec_text: str) -> None:
    """US-006 only adds; existing L10 family must remain intact (零回归)."""
    for tag in ("L10a", "L10b", "L10c", "L10d", "L10e", "L10f", "L10g"):
        assert tag in spec_text, f"L10 family regression: {tag} missing"
    # Iron Law L11 must stay too.
    assert "L11" in spec_text, "L11 (信息密度铁律) must not be removed"
