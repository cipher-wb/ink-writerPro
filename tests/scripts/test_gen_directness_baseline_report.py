"""gen_directness_baseline_report.py 单测（US-002）。

覆盖点：
  * percentiles() 对单值 / 多值 / 空序列的鲁棒性
  * bucket_by_scene 按 scene 正确分桶，跳过缺失 metric
  * recommend_thresholds 区分 lower_is_better / mid_is_better 两类
  * generate_reports 产出 markdown + yaml 双文件，关键字段齐全
  * Combat 0 样本 → YAML 写入 inherits_from，Markdown 显式提示继承
  * 跨书对比 Top 5 排序正确
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.gen_directness_baseline_report import (
    _COMBAT_FALLBACK_SCENE,
    _METRIC_NAMES,
    bucket_by_scene,
    compute_book_means,
    compute_scene_percentiles,
    generate_reports,
    percentiles,
    recommend_thresholds,
    render_markdown,
    render_yaml,
)


def _make_record(
    book: str,
    chapter: int,
    scene: str,
    *,
    d1: float = 0.02,
    d2: float = 0.15,
    d3: float = 0.08,
    d4: float = 15.0,
    d5: int = 30,
) -> dict:
    return {
        "book": book,
        "chapter": chapter,
        "file": f"corpus/{book}/ch{chapter:03d}.txt",
        "scene": scene,
        "metrics": {
            "char_count": 3000,
            "sentence_count": 100,
            "paragraph_count": 80,
            "D1_rhetoric_density": d1,
            "D2_adj_verb_ratio": d2,
            "D3_abstract_per_100_chars": d3,
            "D4_sent_len_median": d4,
            "D5_empty_paragraphs": d5,
        },
    }


# ----- percentiles / bucket / threshold 单元测试 -----


def test_percentiles_empty_returns_zeros() -> None:
    out = percentiles([])
    assert out == {"n": 0, "min": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "max": 0.0}


def test_percentiles_single_value_degenerate() -> None:
    out = percentiles([7.5])
    assert out["n"] == 1
    assert out["min"] == out["p25"] == out["p50"] == out["p75"] == out["max"] == 7.5


def test_percentiles_sorted_distribution() -> None:
    out = percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert out["n"] == 10
    assert out["min"] == 1.0
    assert out["max"] == 10.0
    assert out["p50"] == 5.5
    assert 2 <= out["p25"] <= 3.5
    assert 7 <= out["p75"] <= 9


def test_bucket_by_scene_groups_and_drops_missing() -> None:
    records = [
        _make_record("bk1", 1, "golden_three", d1=0.05),
        _make_record("bk1", 2, "golden_three", d1=0.10),
        _make_record("bk2", 20, "other", d1=0.03),
        {"book": "bk3", "scene": "golden_three", "metrics": {"D1_rhetoric_density": "not-a-num"}},
    ]
    buckets = bucket_by_scene(records)
    assert sorted(buckets.keys()) == ["golden_three", "other"]
    # 两条合法 golden_three + 第 4 条 D1 非数值跳过
    assert buckets["golden_three"]["D1_rhetoric_density"] == [0.05, 0.10]
    assert buckets["other"]["D1_rhetoric_density"] == [0.03]


def test_recommend_thresholds_lower_is_better_maps_to_p50_p75() -> None:
    pcts = {name: {"p25": 1.0, "p50": 2.0, "p75": 3.0} for name in _METRIC_NAMES}
    th = recommend_thresholds(pcts)
    # D1 属 lower_is_better
    assert th["D1_rhetoric_density"]["direction"] == "lower_is_better"
    assert th["D1_rhetoric_density"]["green_max"] == 2.0
    assert th["D1_rhetoric_density"]["yellow_max"] == 3.0
    assert th["D1_rhetoric_density"]["red_min"] == 3.0


def test_recommend_thresholds_mid_is_better_builds_iqr_band() -> None:
    pcts = {name: {"p25": 10.0, "p50": 15.0, "p75": 20.0} for name in _METRIC_NAMES}
    th = recommend_thresholds(pcts)
    # D4 属 mid_is_better：P25/P75 给 green band，外扩 1 IQR (=10) 给 yellow band
    t = th["D4_sent_len_median"]
    assert t["direction"] == "mid_is_better"
    assert t["green_low"] == 10.0
    assert t["green_high"] == 20.0
    assert t["yellow_low"] == 0.0  # max(10 - 10, 0)
    assert t["yellow_high"] == 30.0  # 20 + 10


def test_compute_book_means_sorted_ascending() -> None:
    records = [
        _make_record("plain", 1, "other", d1=0.01, d3=0.02),
        _make_record("plain", 2, "other", d1=0.01, d3=0.02),
        _make_record("ornate", 1, "other", d1=0.20, d3=0.30),
        _make_record("ornate", 2, "other", d1=0.18, d3=0.25),
    ]
    means = compute_book_means(records)
    # 最直白在前
    assert means[0][0] == "plain"
    assert means[-1][0] == "ornate"
    # plain mean = 0.03；ornate mean = (0.50 + 0.43) / 2 = 0.465
    assert means[0][1] < means[-1][1]


# ----- markdown / yaml 渲染测试 -----


def test_render_markdown_contains_key_sections() -> None:
    records = [
        _make_record("bk1", 1, "golden_three", d1=0.01),
        _make_record("bk2", 10, "other", d1=0.05),
    ]
    buckets = bucket_by_scene(records)
    stats = {sc: compute_scene_percentiles(inner) for sc, inner in buckets.items()}
    th = {sc: recommend_thresholds(s) for sc, s in stats.items()}
    counts = {"golden_three": 1, "combat": 0, "other": 1}

    md = render_markdown(
        records,
        counts,
        stats,
        th,
        generated="2026-04-20",
        source=Path("reports/stats.json"),
    )
    assert "Prose Directness Baseline Report" in md
    assert "场景样本分布" in md
    assert "每场景 5 维度百分位" in md
    assert "推荐阈值" in md
    assert "跨书对比" in md
    assert "seed_thresholds.yaml" in md
    # combat 0 样本时必须有继承提示
    assert _COMBAT_FALLBACK_SCENE in md


def test_render_yaml_emits_stable_structure() -> None:
    records = [
        _make_record("bk1", 1, "golden_three", d1=0.02, d2=0.10, d3=0.05, d4=14.0, d5=20),
        _make_record("bk1", 20, "other", d1=0.03),
    ]
    buckets = bucket_by_scene(records)
    stats = {sc: compute_scene_percentiles(inner) for sc, inner in buckets.items()}
    th = {sc: recommend_thresholds(s) for sc, s in stats.items()}
    counts = {"golden_three": 1, "combat": 0, "other": 1}

    yml = render_yaml(
        stats,
        th,
        counts,
        generated="2026-04-20",
        source="reports/stats.json",
    )
    # 关键字段：version / scenes / combat_fallback_scene / inherits_from
    assert "version: 1" in yml
    assert "scenes:" in yml
    assert "golden_three:" in yml
    assert "combat:" in yml
    assert "inherits_from: golden_three" in yml
    assert "other:" in yml
    # 5 metric 都出现在 golden_three percentiles 下
    for name in _METRIC_NAMES:
        assert f"{name}:" in yml


def test_render_yaml_is_parseable_by_pyyaml() -> None:
    import pytest

    yaml = pytest.importorskip("yaml")
    records = [
        _make_record("bk", 1, "golden_three", d1=0.02),
        _make_record("bk", 10, "other", d1=0.03),
    ]
    buckets = bucket_by_scene(records)
    stats = {sc: compute_scene_percentiles(inner) for sc, inner in buckets.items()}
    th = {sc: recommend_thresholds(s) for sc, s in stats.items()}
    counts = {"golden_three": 1, "combat": 0, "other": 1}
    yml_text = render_yaml(
        stats,
        th,
        counts,
        generated="2026-04-20",
        source="reports/stats.json",
    )
    parsed = yaml.safe_load(yml_text)
    assert parsed["version"] == 1
    assert parsed["scenes"]["combat"]["inherits_from"] == "golden_three"
    assert parsed["scenes"]["golden_three"]["n"] == 1
    # Lower-is-better 阈值键齐全
    gt_d1 = parsed["scenes"]["golden_three"]["thresholds"]["D1_rhetoric_density"]
    assert gt_d1["direction"] == "lower_is_better"
    assert "green_max" in gt_d1 and "yellow_max" in gt_d1 and "red_min" in gt_d1
    # Mid-is-better 阈值键齐全
    gt_d4 = parsed["scenes"]["golden_three"]["thresholds"]["D4_sent_len_median"]
    assert gt_d4["direction"] == "mid_is_better"
    assert {"green_low", "green_high", "yellow_low", "yellow_high"} <= gt_d4.keys()


# ----- generate_reports end-to-end 测试 -----


def test_generate_reports_writes_both_files(tmp_path: Path) -> None:
    stats_path = tmp_path / "stats.json"
    md_path = tmp_path / "out" / "baseline.md"
    yml_path = tmp_path / "out" / "seed_thresholds.yaml"
    # 构造 8 条记录：5 golden_three + 3 other，combat 留空
    lines = []
    for i in range(5):
        lines.append(
            json.dumps(
                _make_record(f"bk{i}", i + 1, "golden_three", d1=0.01 + i * 0.01),
                ensure_ascii=False,
            )
        )
    for i in range(3):
        lines.append(
            json.dumps(
                _make_record(f"bk{i}", 10 + i, "other", d1=0.05 + i * 0.01),
                ensure_ascii=False,
            )
        )
    stats_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_md, out_yaml = generate_reports(stats_path, md_path, yml_path, generated="2026-04-20")
    assert out_md == md_path and out_yaml == yml_path
    assert md_path.exists() and yml_path.exists()

    md_text = md_path.read_text(encoding="utf-8")
    yml_text = yml_path.read_text(encoding="utf-8")
    # markdown 必含关键段
    assert "Prose Directness Baseline Report" in md_text
    assert "golden_three" in md_text
    # 5 维度都展开
    for name in _METRIC_NAMES:
        assert name in yml_text or _metric_label_fragment(name) in md_text


def _metric_label_fragment(name: str) -> str:
    from scripts.gen_directness_baseline_report import _METRIC_LABELS

    return _METRIC_LABELS[name]


def test_generate_reports_empty_stats_still_writes_shell(tmp_path: Path) -> None:
    stats_path = tmp_path / "stats.json"
    stats_path.write_text("", encoding="utf-8")
    md = tmp_path / "b.md"
    yml = tmp_path / "b.yaml"
    generate_reports(stats_path, md, yml, generated="2026-04-20")
    # 全空语料也应产出壳文件，不崩
    assert md.exists() and yml.exists()
    yml_text = yml.read_text(encoding="utf-8")
    assert "version: 1" in yml_text
    # 所有 scene 都 0 样本 → 全部 inherits_from（除 golden_three 自身也是 0）
    assert "inherits_from: golden_three" in yml_text
