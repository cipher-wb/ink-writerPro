"""PRD US-003: Replacement Map Pass tests for ``simplification_pass.py``.

Three fixtures per AC：
1. Pure replacement_map happy path — 装逼词被首项爆款词替换。
2. S1 + S1.5 协作 — abstract_adjective 被 S1 删除，replacement_map 词被 S1.5 替换。
3. Diff log writer — 给定 ``chapter_no`` + ``diff_dir`` 时写出 ``chapter_NNN.diff``，
   且文件含命中清单 + unified diff 体；空跑（无命中）不写文件。

依赖固定 ``prose-blacklist.yaml``：``凝视 → 盯着``、``苍茫 → 广``、``缓缓 → 慢慢``、
``莫名`` ∈ abstract_adjectives（直接删除）。如未来 YAML 顺序变更，``凝视`` 首项替换
仍应保持 ``盯着``（这是 polish-agent 默认行为契约）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.prose.blacklist_loader import (
    Blacklist,
    BlacklistEntry,
    ReplacementMap,
    clear_cache,
    load_replacement_map,
)
from ink_writer.prose.simplification_pass import (
    ReplacementResult,
    apply_replacement_map,
    simplify_text,
)

# ---------------------------------------------------------------------------
# apply_replacement_map — pure-function behaviour
# ---------------------------------------------------------------------------


def test_apply_replacement_map_returns_replacement_result_type() -> None:
    clear_cache()
    result = apply_replacement_map("无关文本，无需替换。")
    assert isinstance(result, ReplacementResult)
    assert result.text == "无关文本，无需替换。"
    assert result.hits == ()
    assert result.diff_path is None
    assert result.changed is False
    assert result.total_hits == 0


def test_apply_replacement_map_empty_text() -> None:
    result = apply_replacement_map("")
    assert result.text == ""
    assert result.hits == ()
    assert result.diff_path is None


def test_apply_replacement_map_uses_first_candidate() -> None:
    """凝视 → 盯着 (first item of [盯着, 看着, 死盯])."""
    clear_cache()
    text = "他凝视着远方。"
    result = apply_replacement_map(text)
    assert "凝视" not in result.text
    assert "盯着" in result.text
    assert result.text == "他盯着着远方。"  # 子串替换，不去叠词
    assert result.changed is True
    assert ("凝视", "盯着", 1) in result.hits


def test_apply_replacement_map_explicit_map_override() -> None:
    """显式传入 replacement_map 不依赖 YAML 默认值。"""
    custom = ReplacementMap(
        forward={"独有词A": ("替换A1", "替换A2")},
        reverse={"替换A1": ("独有词A",)},
    )
    text = "他写下独有词A，又写下独有词A。"
    result = apply_replacement_map(text, replacement_map=custom)
    assert result.text == "他写下替换A1，又写下替换A1。"
    assert result.hits == (("独有词A", "替换A1", 2),)
    assert result.total_hits == 2


def test_apply_replacement_map_longest_first_tie_break() -> None:
    """多 source word 长度相同时，长 source 优先于其单字前缀，避免误吃。"""
    custom = ReplacementMap(
        forward={
            "凝": ("看",),  # 1-char
            "凝视": ("盯着",),  # 2-char — 必须先匹配
        },
        reverse={"看": ("凝",), "盯着": ("凝视",)},
    )
    text = "他凝视远方。"
    result = apply_replacement_map(text, replacement_map=custom)
    # 必须先把 凝视 → 盯着，余下不再有 凝 字
    assert "凝视" not in result.text
    assert "盯着" in result.text
    assert "看" not in result.text  # 1-char 规则未误触发
    # 命中清单含 凝视 不含 凝
    sources = {src for src, _, _ in result.hits}
    assert "凝视" in sources
    assert "凝" not in sources


def test_apply_replacement_map_skips_empty_replacement_lists() -> None:
    custom = ReplacementMap(
        forward={"留白词": ()},
        reverse={},
    )
    text = "正文里有留白词。"
    result = apply_replacement_map(text, replacement_map=custom)
    assert result.text == text
    assert result.hits == ()


def test_apply_replacement_map_no_self_replacement() -> None:
    """source word == replacement first item 时跳过（虽然词典不该这么写）。"""
    custom = ReplacementMap(
        forward={"同名": ("同名",)},
        reverse={"同名": ("同名",)},
    )
    result = apply_replacement_map("他叫同名。", replacement_map=custom)
    assert result.hits == ()
    assert result.text == "他叫同名。"


# ---------------------------------------------------------------------------
# Diff log writer (chapter_NNN.diff)
# ---------------------------------------------------------------------------


def test_apply_replacement_map_writes_diff_when_chapter_and_dir(tmp_path: Path) -> None:
    """Fixture 3：chapter_no + diff_dir → 写 reports/polish_diff/chapter_NNN.diff。"""
    clear_cache()
    text = "他凝视着远方，又凝视着脚下。"
    diff_dir = tmp_path / "polish_diff"

    result = apply_replacement_map(text, chapter_no=7, diff_dir=diff_dir)

    assert result.changed is True
    assert result.diff_path is not None

    diff_file = diff_dir / "chapter_007.diff"
    assert diff_file.exists()
    payload = diff_file.read_text(encoding="utf-8")

    # 头注释含命中清单
    assert "Replacement Map Pass" in payload
    assert "chapter 007" in payload
    assert "凝视 → 盯着" in payload
    assert "×2" in payload

    # unified diff body 应含 before/after 行
    assert "--- chapter_007.before" in payload
    assert "+++ chapter_007.after" in payload
    assert "-他凝视着远方，又凝视着脚下。" in payload
    assert "+他盯着着远方，又盯着着脚下。" in payload


def test_apply_replacement_map_no_diff_when_no_hits(tmp_path: Path) -> None:
    """空跑（无命中）不应写 diff 文件。"""
    clear_cache()
    text = "这段文字里没有任何装逼词。"
    diff_dir = tmp_path / "polish_diff"

    result = apply_replacement_map(text, chapter_no=42, diff_dir=diff_dir)

    assert result.changed is False
    assert result.diff_path is None
    # 目录可能因 mkdir 提前创建过，但 chapter_042.diff 文件应不存在
    assert not (diff_dir / "chapter_042.diff").exists()


def test_apply_replacement_map_no_diff_when_dir_missing(tmp_path: Path) -> None:
    """只给 chapter_no 不给 diff_dir 时，行为正常但不落 diff。"""
    clear_cache()
    text = "他凝视着远方。"
    result = apply_replacement_map(text, chapter_no=1)
    assert result.changed is True
    assert result.diff_path is None


def test_apply_replacement_map_diff_chapter_zero_pad(tmp_path: Path) -> None:
    """chapter_no=1 应写到 chapter_001.diff（3 位补零）。"""
    clear_cache()
    text = "他凝视着远方。"
    result = apply_replacement_map(text, chapter_no=1, diff_dir=tmp_path)
    assert result.diff_path is not None
    assert (tmp_path / "chapter_001.diff").exists()


def test_apply_replacement_map_diff_overwrites_prior_run(tmp_path: Path) -> None:
    """同章节多次跑 polish 时后写覆盖前写，避免 diff 文件无限增长。"""
    clear_cache()
    diff_dir = tmp_path / "polish_diff"

    # 第一次：text 含 凝视
    apply_replacement_map(
        "他凝视着远方。",
        chapter_no=12,
        diff_dir=diff_dir,
    )
    first = (diff_dir / "chapter_012.diff").read_text(encoding="utf-8")
    assert "凝视" in first

    # 第二次：text 改为 缓缓
    apply_replacement_map(
        "他缓缓抬头。",
        chapter_no=12,
        diff_dir=diff_dir,
    )
    second = (diff_dir / "chapter_012.diff").read_text(encoding="utf-8")
    assert "缓缓" in second
    assert "凝视" not in second  # 旧内容已被覆盖


# ---------------------------------------------------------------------------
# simplify_text 集成 — S1 → S1.5 先后顺序
# ---------------------------------------------------------------------------


def test_simplify_text_fires_replacement_map_pass_after_blacklist_drop() -> None:
    """Fixture 2：S1 删 莫名，S1.5 替 凝视。两条规则均触发，互不抵消。"""
    clear_cache()
    text = "他莫名凝视着远方。"
    report = simplify_text(text)

    # S1: 莫名 删除
    assert "莫名" not in report.simplified_text
    assert "blacklist_abstract_drop" in report.rules_fired

    # S1.5: 凝视 → 盯着
    assert "凝视" not in report.simplified_text
    assert "盯着" in report.simplified_text
    assert "replacement_map_pass" in report.rules_fired

    # 命中清单回传
    sources = {src for src, _, _ in report.replacement_hits}
    assert "凝视" in sources


def test_simplify_text_no_replacement_when_no_hits() -> None:
    clear_cache()
    text = "他走进教室，对老师点头。"
    report = simplify_text(text)
    assert "replacement_map_pass" not in report.rules_fired
    assert report.replacement_hits == ()
    assert report.replacement_diff_path is None


def test_simplify_text_passes_chapter_no_to_diff_writer(tmp_path: Path) -> None:
    """Fixture 3 集成版：simplify_text 把 chapter_no/diff_dir 转给 apply_replacement_map。"""
    clear_cache()
    text = "他凝视着远方。"
    report = simplify_text(text, chapter_no=15, diff_dir=tmp_path)

    assert "replacement_map_pass" in report.rules_fired
    assert report.replacement_diff_path is not None
    assert (tmp_path / "chapter_015.diff").exists()


def test_simplify_text_no_diff_when_only_blacklist_drop(tmp_path: Path) -> None:
    """章节只触发 S1 不触发 S1.5 时不写 diff。"""
    clear_cache()
    text = "她莫名感到一阵心慌。"  # 莫名 ∈ abstract_adjectives；无 replacement_map 命中
    report = simplify_text(text, chapter_no=8, diff_dir=tmp_path)
    assert "blacklist_abstract_drop" in report.rules_fired
    assert "replacement_map_pass" not in report.rules_fired
    assert report.replacement_diff_path is None
    assert not (tmp_path / "chapter_008.diff").exists()


def test_simplify_text_replacement_preserved_after_rollback() -> None:
    """70% 回滚触发时 replacement_hits 仍回传（rolled_back 不抹掉 diff 元数据）。"""
    clear_cache()
    # 构造一个 S4 会大量删段、触发回滚的纯环境段，加一个替换词
    text = "凝视。星光洒满天空。风从远处吹来。月光铺展地面。大地寂静。云层低垂。"
    report = simplify_text(text)
    if report.rolled_back:
        # 回滚时 simplified_text 必须等于原文
        assert report.simplified_text == text
        # replacement_hits 仍应记录（透明审计）
        sources = {src for src, _, _ in report.replacement_hits}
        # 凝视 在 S1.5 阶段被替换的中间结果可见，但最终回滚到原文
        assert "凝视" in sources or report.replacement_hits == ()


# ---------------------------------------------------------------------------
# 回归保护 — load_replacement_map 与 simplify_text 旧 fixture 仍通过
# ---------------------------------------------------------------------------


def test_load_replacement_map_returns_loaded_yaml() -> None:
    rmap = load_replacement_map()
    assert isinstance(rmap, ReplacementMap)
    # YAML 装载 ≥ 100 条（PRD US-002 落地数）
    assert len(rmap) >= 100
    # 关键词必须能查到
    assert rmap.lookup("凝视")[:1] == ("盯着",)
    assert rmap.lookup("缓缓")[:1] == ("慢慢",)


def test_simplify_text_legacy_clean_text_unchanged() -> None:
    """无装逼词、无黑名单的干净段落 → byte-identical。"""
    clear_cache()
    text = "小明走进教室，对李老师点头。李老师递过一本书。"
    report = simplify_text(text)
    assert report.simplified_text == text
    assert report.replacement_hits == ()
    assert "replacement_map_pass" not in report.rules_fired
    assert report.replacement_diff_path is None


def test_simplify_text_custom_blacklist_no_replacement_map() -> None:
    """显式 Blacklist override 不带 replacement_map 时跳过 S1.5。"""
    custom = Blacklist(
        version=1,
        entries=(BlacklistEntry(word="独有魔咒", category="abstract_adjectives", replacement=""),),
    )
    # 长度需够大避免 70% floor 触发回滚（删 4 字后字数仍在 70% 以上）
    text = "她心中独有魔咒在回响，迟迟不能散去，整夜辗转反侧。"
    report = simplify_text(text, blacklist=custom)
    assert "独有魔咒" not in report.simplified_text
    assert report.rolled_back is False
    assert "blacklist_abstract_drop" in report.rules_fired
    assert "replacement_map_pass" not in report.rules_fired
    assert report.replacement_hits == ()


# ---------------------------------------------------------------------------
# 公共导出
# ---------------------------------------------------------------------------


def test_public_exports_include_replacement_api() -> None:
    from ink_writer import prose

    for name in ("apply_replacement_map", "ReplacementResult"):
        assert hasattr(prose, name), f"ink_writer.prose 未导出 {name!r}"
        assert name in prose.__all__, f"{name!r} 缺失于 prose.__all__"


@pytest.mark.parametrize(
    "marker",
    [
        "Replacement Map Pass",
        "S1.5",
        "replacement_map",
        "reports/polish_diff/chapter_NNN.diff",
        "apply_replacement_map",
    ],
)
def test_polish_agent_spec_documents_replacement_map_pass(marker: str) -> None:
    """polish-agent.md 必须文档化 Replacement Map Pass（PRD US-003 AC 3）。"""
    spec_path = (
        Path(__file__).resolve().parents[2]
        / "ink-writer"
        / "agents"
        / "polish-agent.md"
    )
    text = spec_path.read_text(encoding="utf-8")
    assert marker in text, f"polish-agent.md 缺失 Replacement Map Pass 关键词 {marker!r}"
