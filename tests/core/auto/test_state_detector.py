# tests/core/auto/test_state_detector.py
import json
from pathlib import Path
import pytest
from ink_writer.core.auto.state_detector import detect_project_state, ProjectState


def _write_state(root: Path, *, current_chapter: int = 0, is_completed: bool = False, volumes: list | None = None) -> None:
    (root / ".ink").mkdir(parents=True, exist_ok=True)
    state = {
        "project_info": {"volumes": volumes or []},
        "progress": {"current_chapter": current_chapter, "is_completed": is_completed},
    }
    (root / ".ink" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def test_s0_uninit_when_no_state_json(tmp_path: Path) -> None:
    assert detect_project_state(tmp_path) == ProjectState.S0_UNINIT


def test_s1_no_outline_when_state_exists_but_outline_dir_missing(tmp_path: Path) -> None:
    _write_state(tmp_path, volumes=[{"volume_id": "1", "chapter_range": "1-50"}])
    assert detect_project_state(tmp_path) == ProjectState.S1_NO_OUTLINE


def test_s1_no_outline_when_outline_dir_empty(tmp_path: Path) -> None:
    _write_state(tmp_path, volumes=[{"volume_id": "1", "chapter_range": "1-50"}])
    (tmp_path / "大纲").mkdir()
    assert detect_project_state(tmp_path) == ProjectState.S1_NO_OUTLINE


def test_s2_writing_when_state_and_outline_present(tmp_path: Path) -> None:
    _write_state(tmp_path, current_chapter=5, volumes=[{"volume_id": "1", "chapter_range": "1-50"}])
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("# 总纲", encoding="utf-8")
    assert detect_project_state(tmp_path) == ProjectState.S2_WRITING


def test_s3_completed_when_is_completed_true(tmp_path: Path) -> None:
    _write_state(tmp_path, current_chapter=600, is_completed=True, volumes=[{"volume_id": "1", "chapter_range": "1-600"}])
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "总纲.md").write_text("# 总纲", encoding="utf-8")
    assert detect_project_state(tmp_path) == ProjectState.S3_COMPLETED
