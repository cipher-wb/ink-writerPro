# tests/core/auto/test_integration_s0a.py
"""Integration test: blueprint .md found → state detected → quick draft generated.

Stops short of actual ink-init CLI subprocess invocation (which would need API key).
"""
import json
from pathlib import Path
import subprocess
import sys
from ink_writer.core.auto.state_detector import detect_project_state, ProjectState
from ink_writer.core.auto.blueprint_scanner import find_blueprint
from tests.core.auto._blueprint_fixtures import write_full_blueprint


def test_s0a_pipeline_produces_valid_quick_draft(tmp_path: Path) -> None:
    write_full_blueprint(tmp_path / "我的修真.md")
    (tmp_path / "README.md").write_text("# readme", encoding="utf-8")

    assert detect_project_state(tmp_path) == ProjectState.S0_UNINIT

    bp = find_blueprint(tmp_path)
    assert bp is not None and bp.name == "我的修真.md"

    out = tmp_path / "draft.json"
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.core.auto.blueprint_to_quick_draft",
         "--input", str(bp), "--output", str(out)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr

    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["platform"] == "qidian"
    assert draft["aggression_level"] == 2
    assert draft["target_chapters"] == 600
    assert draft["题材方向"] == "仙侠"
    assert draft["主角人设"].startswith("寒门弟子")
    assert draft["金手指类型"] == "信息"
    assert "__missing__" in draft
