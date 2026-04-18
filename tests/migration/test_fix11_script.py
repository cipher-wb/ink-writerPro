"""Tests for scripts/migration/fix11_merge_packages.py (US-025)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure repo root on sys.path for ``scripts`` package import
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.migration import fix11_merge_packages as fix11  # noqa: E402


# --- rewrite_python --------------------------------------------------------


def test_rewrites_from_data_modules_dotted():
    src = "from data_modules.state_manager import StateManager\n"
    assert fix11.rewrite_python(src) == "from ink_writer.core.state.state_manager import StateManager\n"


def test_rewrites_from_scripts_data_modules_prefix():
    src = "from scripts.data_modules.index_manager import IndexManager\n"
    assert fix11.rewrite_python(src) == "from ink_writer.core.index.index_manager import IndexManager\n"


def test_rewrites_import_data_modules_dotted_with_alias():
    src = "import data_modules.api_client as api\n"
    assert fix11.rewrite_python(src) == "import ink_writer.core.infra.api_client as api\n"


def test_rewrites_from_data_modules_flat_known_names():
    src = "from data_modules import state_manager, index_manager\n"
    out = fix11.rewrite_python(src)
    assert "from ink_writer.core.state import state_manager" in out
    assert "from ink_writer.core.index import index_manager" in out


def test_preserves_unknown_module_names():
    # `unknown_mod` is not in BUCKET_MAP — line should stay untouched.
    src = "from data_modules.unknown_mod import Something\n"
    assert fix11.rewrite_python(src) == src


def test_comments_out_sys_path_insert_to_scripts():
    src = "sys.path.insert(0, 'ink-writer/scripts/data_modules')\n"
    out = fix11.rewrite_python(src)
    assert out.startswith("# [FIX-11] removed: ")
    assert "sys.path.insert" in out  # original body kept after the marker


def test_preserves_unrelated_imports():
    src = "from pathlib import Path\nimport sys\nfrom ink_writer.state import StateManager\n"
    assert fix11.rewrite_python(src) == src


def test_rewrite_is_idempotent():
    src = "from data_modules.context_manager import ContextManager\n"
    once = fix11.rewrite_python(src)
    twice = fix11.rewrite_python(once)
    assert once == twice


# --- rewrite_pytest_ini ----------------------------------------------------


def test_pytest_ini_substitutes_testpaths_and_drops_pythonpath_token():
    src = (
        "[pytest]\n"
        "testpaths = ink-writer/scripts/data_modules/tests tests/baseline\n"
        "pythonpath = . ink-writer/scripts scripts\n"
    )
    out = fix11.rewrite_pytest_ini(src)
    assert "ink-writer/scripts/data_modules/tests" not in out
    assert "ink_writer/core/tests" in out
    # pythonpath token dropped
    assert "ink-writer/scripts" not in out.split("pythonpath", 1)[1]


# --- rewrite_markdown ------------------------------------------------------


def test_markdown_rewrites_import_example():
    src = "Example: `from data_modules.state_manager import StateManager`\n"
    out = fix11.rewrite_markdown(src)
    assert "from ink_writer.core.state.state_manager import StateManager" in out


def test_markdown_rewrites_sys_path_example():
    src = "sys.path.insert(0, '${SCRIPTS_DIR}/data_modules')\n"
    out = fix11.rewrite_markdown(src)
    assert "[FIX-11]" in out
    assert "SCRIPTS_DIR" not in out
    assert "data_modules" not in out


# --- file-walk & diff ------------------------------------------------------


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "app.py").write_text(
        "from data_modules.state_manager import StateManager\n"
        "print('ok')\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "See `from data_modules.index_manager import IndexManager`.\n",
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\n"
        "testpaths = ink-writer/scripts/data_modules/tests\n"
        "pythonpath = . ink-writer/scripts\n",
        encoding="utf-8",
    )
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text(
        "from data_modules.state_manager import X\n",
        encoding="utf-8",
    )
    return tmp_path


def test_iter_target_files_skips_excluded_dirs(fake_repo: Path):
    found = {p.name for p in fix11.iter_target_files(fake_repo)}
    assert "app.py" in found
    assert "README.md" in found
    assert "pytest.ini" in found
    # ignored by EXCLUDED_DIR_NAMES
    assert "ignored.py" not in found


def test_compute_diff_finds_changes(fake_repo: Path):
    diff_lines, changes = fix11.compute_diff(fake_repo)
    changed_names = {p.name for p, *_ in changes}
    assert {"app.py", "README.md", "pytest.ini"}.issubset(changed_names)
    joined = "".join(diff_lines)
    assert "ink_writer.core.state.state_manager" in joined


def test_apply_writes_changes(tmp_path: Path, fake_repo: Path):
    diff_out = tmp_path / "diff.txt"
    rc = fix11.main(["--root", str(fake_repo), "--apply", "--diff-out", str(diff_out)])
    assert rc == 0
    assert diff_out.exists()
    after = (fake_repo / "pkg" / "app.py").read_text(encoding="utf-8")
    assert "ink_writer.core.state.state_manager" in after
    assert "data_modules" not in after


def test_dry_run_does_not_modify_files(tmp_path: Path, fake_repo: Path):
    diff_out = tmp_path / "diff.txt"
    original = (fake_repo / "pkg" / "app.py").read_text(encoding="utf-8")
    rc = fix11.main(["--root", str(fake_repo), "--diff-out", str(diff_out)])
    assert rc == 0
    assert (fake_repo / "pkg" / "app.py").read_text(encoding="utf-8") == original
    assert diff_out.read_text(encoding="utf-8")  # non-empty diff captured
