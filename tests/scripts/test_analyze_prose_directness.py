"""analyze_prose_directness.py 单测（US-001）。

覆盖点：
  * D1~D5 指标计算正确
  * 场景分类（golden_three / combat / other）
  * run_analysis 生成 JSONL + 记录条数
  * 抽象词黑名单覆盖（种子 → YAML）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.analyze_prose_directness import (
    _ABSTRACT_SEED,
    classify_scene,
    compute_metrics,
    has_parallelism,
    has_simile,
    is_empty_description,
    run_analysis,
    split_paragraphs,
    split_sentences,
)

# ----- 构造样本 -----

SAMPLE_PLAIN = """
楚山拔刀砍向对手。
对手低头避开，反手一刀回击。
楚山格挡，步法飞快地移动，再砍一刀。
血溅三尺，对手倒地。
""".strip()


SAMPLE_RHETORIC = """
夜空仿佛一块巨大的黑幕。
风声恍若低语，月光犹如银水流淌，云影宛如轻纱拂过。
他的心如同死水，毫无波澜。
她是风，她是雨，她是夜里的梦。
""".strip()


SAMPLE_EMPTY_DESC = """
夜雨飘摇，风中带着凉意。山路蜿蜒，泥土的气息在空气中弥漫开来。

远方的灯火若隐若现，仿佛一场梦境。整片山林都被雾气包裹，寂静到极致。

他站在雨中，目光沉重地望向远方。
""".strip()


# ----- 单元测试 -----


def test_split_sentences_strip_empty() -> None:
    out = split_sentences("第一句。第二句！第三句？  ")
    assert out == ["第一句", "第二句", "第三句"]


def test_split_paragraphs_strip_indent() -> None:
    text = "　　段落一首行缩进。\n\n　　段落二。\n\n  \n第三段。"
    assert split_paragraphs(text) == ["段落一首行缩进。", "段落二。", "第三段。"]


def test_has_simile_positive_and_negative() -> None:
    assert has_simile("他的心如同死水") is True
    assert has_simile("月光犹如银水") is True
    assert has_simile("他拔刀砍向对手") is False


def test_has_parallelism_three_segments_same_first_char() -> None:
    assert has_parallelism("她是风，她是雨，她是夜里的梦") is True
    # 少于 3 段：False
    assert has_parallelism("她是风，她是雨") is False
    # 首字不同：False
    assert has_parallelism("她是风，他是雨，你是梦") is False


def test_is_empty_description_detects_pure_env() -> None:
    pure_env = "夜色笼罩山川，风声低低。远处灯火微弱。"
    assert is_empty_description(pure_env) is True


def test_is_empty_description_false_when_pronoun_present() -> None:
    with_pronoun = "他站在山顶，望着远方。"
    assert is_empty_description(with_pronoun) is False


def test_is_empty_description_false_when_dialogue_markers() -> None:
    with_dialogue = "山风阵阵，远处传来声音：\"有人吗？\""
    assert is_empty_description(with_dialogue) is False


def test_compute_metrics_plain_action_text_has_low_rhetoric() -> None:
    m = compute_metrics(SAMPLE_PLAIN)
    assert m["sentence_count"] >= 4
    assert m["D1_rhetoric_density"] <= 0.25, m  # 最多一两句有"飞快"类比喻意味
    assert m["D2_adj_verb_ratio"] < 1.0, m  # 动作文本，动词应多于形容词
    assert m["D3_abstract_per_100_chars"] == 0, m
    assert m["D4_sent_len_median"] > 0


def test_compute_metrics_rhetoric_text_has_high_density() -> None:
    m = compute_metrics(SAMPLE_RHETORIC)
    # 4 句中至少 3 句含比喻或排比
    assert m["D1_rhetoric_density"] >= 0.5, m
    assert m["D3_abstract_per_100_chars"] > 0, m  # 含"仿佛/恍若/宛如/犹如"


def test_compute_metrics_empty_desc_text_has_empty_paragraphs() -> None:
    m = compute_metrics(SAMPLE_EMPTY_DESC)
    assert m["D5_empty_paragraphs"] >= 2, m  # 前两段纯环境，第三段有 "他"


def test_classify_scene_golden_three() -> None:
    assert classify_scene(1, "ch001", SAMPLE_PLAIN) == "golden_three"
    assert classify_scene(3, "ch003", SAMPLE_PLAIN) == "golden_three"


def test_classify_scene_combat_by_title_keyword() -> None:
    # 需要非黄金三章，确保命中 combat 分支
    assert classify_scene(20, "ch020_决战", SAMPLE_PLAIN) == "combat"


def test_classify_scene_other_for_non_keyword_non_combat() -> None:
    calm_text = "他坐在院子里喝茶，思考人生，回忆往事。阳光温和。" * 20
    assert classify_scene(15, "ch015", calm_text) == "other"


def test_run_analysis_emits_jsonl(tmp_path: Path) -> None:
    # 构造 2 本 × 3 章的迷你语料
    corpus = tmp_path / "corpus"
    book1 = corpus / "book_a" / "chapters"
    book2 = corpus / "book_b" / "chapters"
    book1.mkdir(parents=True)
    book2.mkdir(parents=True)
    for idx in (1, 2, 3):
        (book1 / f"ch{idx:03d}.txt").write_text(SAMPLE_PLAIN, encoding="utf-8")
        (book2 / f"ch{idx:03d}.txt").write_text(SAMPLE_RHETORIC, encoding="utf-8")

    output = tmp_path / "reports" / "stats.json"
    records = run_analysis(corpus, output, max_chapters=3)
    assert len(records) == 6
    assert output.exists()

    lines = output.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6
    decoded = [json.loads(line) for line in lines]
    books = sorted({rec["book"] for rec in decoded})
    assert books == ["book_a", "book_b"]
    # 所有章 chapter ∈ [1, 3] → golden_three
    assert {rec["scene"] for rec in decoded} == {"golden_three"}


def test_run_analysis_max_books_limits_scan(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    for b in ("b1", "b2", "b3"):
        (corpus / b / "chapters").mkdir(parents=True)
        (corpus / b / "chapters" / "ch001.txt").write_text(SAMPLE_PLAIN, encoding="utf-8")
    output = tmp_path / "out.json"
    records = run_analysis(corpus, output, max_chapters=1, max_books=2)
    assert len(records) == 2
    assert {rec["book"] for rec in records} == {"b1", "b2"}


def test_abstract_seed_coverage_sanity() -> None:
    # 种子黑名单覆盖常见网文抽象词（US-003 会扩展到 ≥50）
    assert "莫名" in _ABSTRACT_SEED
    assert "仿佛" in _ABSTRACT_SEED
    assert "宛如" in _ABSTRACT_SEED


def test_load_blacklist_yaml(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    from scripts.analyze_prose_directness import _load_blacklist

    blk = tmp_path / "blk.yaml"
    blk.write_text(
        "abstract_adjectives:\n  - 诡异\n  - 神秘\n  - word: 朦胧\n",
        encoding="utf-8",
    )
    words = _load_blacklist(blk)
    assert "诡异" in words
    assert "神秘" in words
    assert "朦胧" in words
