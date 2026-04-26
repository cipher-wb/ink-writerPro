"""US-LR-011 Tests for ink-init Step 99.5 接入点 + SKILL.md 含示例代码块。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_30_CASES = FIXTURES_DIR / "sample_30_cases"
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MD_PATH = REPO_ROOT / "ink-writer" / "skills" / "ink-init" / "SKILL.md"


@pytest.fixture(scope="module")
def vector_index_dir(tmp_path_factory) -> Path:
    from ink_writer.live_review._vector_index import build_index

    out_dir = tmp_path_factory.mktemp("step995_index")
    build_index(SAMPLE_30_CASES, out_dir)
    return out_dir


@pytest.fixture(scope="module")
def genre_stats_path(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("step995_stats") / "genre_acceptance.json"
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


def test_step_99_5_render_text_contains_required_sections(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """模拟 ink-init 调 check_genre 后 render_text 含三段必出标记。"""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text("enabled: true\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8")
    out = check_genre(
        "都市重生",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    text = out["render_text"]
    assert "星河直播相似案例" in text
    assert "该题材统计" in text
    assert "写作建议" in text


def test_step_99_5_inject_into_init_false_short_circuits(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """inject_into.init=false 时 check_genre 早退：warning_level=ok + render_text 简短/空。"""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: true\ninject_into:\n  init: false\n  review: true\n", encoding="utf-8"
    )
    out = check_genre(
        "玄幻",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    # warning_level should be 'ok' (or a disabled marker), and render_text should be empty/short
    assert out["warning_level"] == "ok"
    assert out["similar_cases"] == [] or out["render_text"] == ""


def test_step_99_5_disabled_globally_short_circuits(
    vector_index_dir: Path, genre_stats_path: Path, tmp_path: Path
) -> None:
    """enabled=false master switch 同样短路。"""
    from ink_writer.live_review.init_injection import check_genre

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: false\ninject_into:\n  init: true\n  review: true\n", encoding="utf-8"
    )
    out = check_genre(
        "玄幻",
        top_k=3,
        config_path=cfg,
        genre_stats_path=genre_stats_path,
        index_dir=vector_index_dir,
    )
    assert out["warning_level"] == "ok"


def test_skill_md_contains_step_99_5_section() -> None:
    """ink-init/SKILL.md 必须含 'Step 99.5' 段 + check_genre 引用 + inject_into 提示。"""
    text = SKILL_MD_PATH.read_text(encoding="utf-8")
    assert "Step 99.5" in text, "SKILL.md should declare Step 99.5"
    assert "live-review" in text or "live_review" in text
    assert "check_genre" in text, "SKILL.md should reference check_genre"
    assert "inject_into" in text, "SKILL.md should mention inject_into.init switch"
