"""Tests for ``ink_writer.case_library.cli`` (US-008)."""
from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.case_library.cli import main


def _create_args(library_root: Path, raw_text: str, title: str = "t") -> list[str]:
    """Build a valid ``create`` argv for the CLI."""
    return [
        "--library-root",
        str(library_root),
        "create",
        "--title",
        title,
        "--raw-text",
        raw_text,
        "--domain",
        "writing_quality",
        "--layer",
        "downstream",
        "--severity",
        "P1",
        "--tags",
        "reader_immersion",
        "--source-type",
        "editor_review",
        "--ingested-at",
        "2026-04-24",
        "--failure-description",
        "情绪缓冲缺失",
        "--observable",
        "突发事件到理性反应字符数 < 200",
    ]


def test_cli_create_then_list_then_show(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_root = tmp_path / "lib"

    rc = main(_create_args(library_root, raw_text="主角反应太快", title="冷静过头"))
    assert rc == 0
    created_out = capsys.readouterr().out.strip()
    # CLI prints exactly one case_id on create (new path).
    assert created_out.startswith("CASE-"), created_out
    case_id = created_out

    rc = main(["--library-root", str(library_root), "list"])
    assert rc == 0
    list_out = capsys.readouterr().out.strip().splitlines()
    assert list_out == [case_id]

    rc = main(["--library-root", str(library_root), "show", case_id])
    assert rc == 0
    show_out = capsys.readouterr().out
    # YAML dump preserves Chinese and starts with case_id (sort_keys=False).
    assert show_out.startswith("case_id:"), show_out
    assert case_id in show_out
    assert "冷静过头" in show_out
    assert "主角反应太快" in show_out


def test_cli_status_filters_by_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_root = tmp_path / "lib"

    # Case A: default initial_status=active.
    rc = main(_create_args(library_root, raw_text="文本甲"))
    assert rc == 0
    active_id = capsys.readouterr().out.strip()

    # Case B: explicit --initial-status pending.
    argv = _create_args(library_root, raw_text="文本乙")
    argv += ["--initial-status", "pending"]
    rc = main(argv)
    assert rc == 0
    pending_id = capsys.readouterr().out.strip()

    assert active_id != pending_id

    # Filter active -> only Case A.
    rc = main(["--library-root", str(library_root), "status", "active"])
    assert rc == 0
    active_out = capsys.readouterr().out.strip().splitlines()
    assert active_out == [active_id]

    # Filter pending -> only Case B.
    rc = main(["--library-root", str(library_root), "status", "pending"])
    assert rc == 0
    pending_out = capsys.readouterr().out.strip().splitlines()
    assert pending_out == [pending_id]

    # Filter resolved -> empty.
    rc = main(["--library-root", str(library_root), "status", "resolved"])
    assert rc == 0
    resolved_out = capsys.readouterr().out.strip()
    assert resolved_out == ""


def test_cli_rebuild_index_creates_sqlite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library_root = tmp_path / "lib"

    rc = main(_create_args(library_root, raw_text="索引用例"))
    assert rc == 0
    capsys.readouterr()

    rc = main(["--library-root", str(library_root), "rebuild-index"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "indexed=1"
    assert (library_root / "index.sqlite").exists()
