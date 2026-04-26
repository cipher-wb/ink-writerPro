"""US-LR-013 end-to-end smoke test for scripts/live-review/smoke_test.py.

Covers default (mock) mode: subprocess invocation, exit-code, report generation.

bge-small-zh-v1.5 模型加载 ~30s — 用 module-scoped fixture 共享预构建的 vector
index，避免每个 test 重复 build。`smoke_test.py` 通过 `--index-dir` 复用既有索引时，
init 路径仅 query encoding ~1s；review 路径以 mock_response 短路检索 + LLM。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "smoke_test.py"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_30_CASES = FIXTURES_DIR / "sample_30_cases"


@pytest.fixture(scope="module")
def prebuilt_index(tmp_path_factory) -> Path:
    """Build vector index once for all smoke tests in this module (~30s).

    Reused across tests via subprocess `--index-dir` to avoid per-test rebuild.
    """
    from ink_writer.live_review._vector_index import build_index

    out_dir = tmp_path_factory.mktemp("smoke_vector_index")
    build_index(SAMPLE_30_CASES, out_dir)
    return out_dir


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Invoke smoke_test.py as subprocess from repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        **kwargs,
    )


def test_smoke_default_mock_mode_passes(tmp_path: Path, prebuilt_index: Path) -> None:
    """Default mode (no --with-api) → exit 0 + report exists + contains 'PASS'."""
    report = tmp_path / "smoke-report.md"
    proc = _run(
        [
            "--index-dir",
            str(prebuilt_index),
            "--report-out",
            str(report),
            "--cases-dir",
            str(SAMPLE_30_CASES),
        ]
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert report.exists(), f"report not written: {report}"
    content = report.read_text(encoding="utf-8")
    assert "PASS" in content, f"report missing 'PASS' keyword:\n{content}"


def test_smoke_report_enumerates_init_and_review_steps(
    tmp_path: Path, prebuilt_index: Path
) -> None:
    """Report markdown must enumerate init / review / index step names so users can
    audit the smoke flow. Pinned to step ids that smoke_test.py emits.
    """
    report = tmp_path / "smoke-report.md"
    proc = _run(
        [
            "--index-dir",
            str(prebuilt_index),
            "--report-out",
            str(report),
            "--cases-dir",
            str(SAMPLE_30_CASES),
        ]
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    content = report.read_text(encoding="utf-8")
    assert "init_check_genre" in content, "report should mention init step id"
    assert "review_checker" in content, "report should mention review step id"
    assert "ensure_index" in content, "report should mention ensure_index step id"


def test_smoke_no_api_key_does_not_import_anthropic(
    tmp_path: Path, prebuilt_index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ANTHROPIC_API_KEY in env → mock mode must still succeed.

    Run subprocess with ANTHROPIC_API_KEY explicitly removed; mock path should
    short-circuit before any network/SDK access.
    """
    import os

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    report = tmp_path / "smoke-report.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--index-dir",
            str(prebuilt_index),
            "--report-out",
            str(report),
            "--cases-dir",
            str(SAMPLE_30_CASES),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    # Mode line must reflect mock (not with-api).
    assert "mock" in content.lower(), f"report should declare mock mode:\n{content}"


def test_smoke_builds_index_when_missing(tmp_path: Path) -> None:
    """If --index-dir is empty + --cases-dir is given, smoke_test rebuilds index."""
    fresh_index = tmp_path / "fresh_index"
    report = tmp_path / "smoke-report.md"
    proc = _run(
        [
            "--index-dir",
            str(fresh_index),
            "--report-out",
            str(report),
            "--cases-dir",
            str(SAMPLE_30_CASES),
        ]
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert (fresh_index / "index.faiss").exists(), "index.faiss should be built"
    assert (fresh_index / "meta.jsonl").exists(), "meta.jsonl should be built"
