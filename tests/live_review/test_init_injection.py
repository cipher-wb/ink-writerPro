"""US-LR-011 Tests for init_injection.check_genre — D+B 组合 UI 输出。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_30_CASES = FIXTURES_DIR / "sample_30_cases"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def vector_index_dir(tmp_path_factory) -> Path:
    """Build vector index from sample_30_cases once for the whole module."""
    from ink_writer.live_review._vector_index import build_index

    out_dir = tmp_path_factory.mktemp("init_inject_index")
    build_index(SAMPLE_30_CASES, out_dir)
    return out_dir


@pytest.fixture(scope="module")
def genre_stats_path(tmp_path_factory) -> Path:
    """Run aggregate_genre.py once to produce genre_acceptance.json from 30 cases."""
    out = tmp_path_factory.mktemp("genre_stats") / "genre_acceptance.json"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "live-review" / "aggregate_genre.py"),
            "--cases-dir",
            str(SAMPLE_30_CASES),
            "--out",
            str(out),
            "--min-cases",
            "3",
        ],
        check=True,
    )
    return out


def test_check_genre_high_score_returns_ok(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """仙侠 score_mean=70 > 60 (default threshold) → warning_level=ok."""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "仙侠",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert out["warning_level"] == "ok"
    assert out["genre_stats"] is not None
    assert out["genre_stats"]["score_mean"] >= 60
    assert "星河直播相似案例" in out["render_text"]
    assert "该题材统计" in out["render_text"]


def test_check_genre_low_score_returns_warn(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """玄幻 score_mean=44 < 60 (default threshold) → warning_level=warn."""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "玄幻",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert out["warning_level"] == "warn"
    assert out["genre_stats"]["score_mean"] < 60
    assert len(out["suggested_actions"]) >= 1
    assert "写作建议" in out["render_text"]


def test_check_genre_unmatched_returns_no_data(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """Unrecognized genre → warning_level=no_data."""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "蒸汽朋克生物机械",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert out["warning_level"] == "no_data"
    assert out["genre_stats"] is None


def test_check_genre_mid_score_returns_ok(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """都市 score_mean=65 > 60 → ok."""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "都市",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert out["warning_level"] == "ok"
    assert "都市" in (out["genre_stats"] or {}).get("genre", "都市")


def test_check_genre_extreme_high_returns_ok(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """职业流 score_mean=65 > 60 → ok."""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "职业流",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert out["warning_level"] == "ok"
    assert out["genre_stats"]["score_mean"] >= 60


def test_check_genre_render_text_top_k_cases(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "都市重生律师",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert len(out["similar_cases"]) == 3
    for c in out["similar_cases"]:
        assert c["case_id"].startswith("CASE-LR-2026-")


def test_check_genre_returns_json_serializable(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """Return value must be json-serializable for CLI consumption."""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "玄幻",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    json.dumps(out, ensure_ascii=False)  # should not raise
