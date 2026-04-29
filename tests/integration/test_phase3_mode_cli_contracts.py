from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "phase3"
INK = REPO_ROOT / "ink-writer" / "scripts" / "ink.py"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    paths = [
        str(REPO_ROOT),
        str(REPO_ROOT / "ink-writer"),
        str(REPO_ROOT / "ink-writer" / "scripts"),
        str(REPO_ROOT / "ink-writer" / "dashboard"),
        str(REPO_ROOT / "scripts"),
    ]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONIOENCODING"] = "utf-8"
    env["INK_SKIP_STYLE_RAG_INIT"] = "1"
    return env


def _run(args: list[str], *, cwd: Path = REPO_ROOT, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=_env(),
        timeout=30,
    )


def _make_project(root: Path) -> Path:
    project = root / "雾港 问心录"
    (project / ".ink").mkdir(parents=True)
    (project / ".ink" / "state.json").write_text(
        json.dumps({"progress": {"current_chapter": 0, "is_completed": False}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return project


def test_quick_mode_blueprint_cli_writes_draft_json(tmp_path: Path) -> None:
    output = tmp_path / "quick-draft.json"
    result = _run([
        sys.executable,
        str(REPO_ROOT / "ink-writer" / "scripts" / "blueprint_to_quick_draft.py"),
        "--input",
        str(FIXTURES / "quick_blueprint.md"),
        "--output",
        str(output),
    ])

    assert result.returncode == 0, result.stderr
    assert "BLUEPRINT_OK" in result.stdout
    assert result.stderr == ""
    assert output.exists()
    draft = json.loads(output.read_text(encoding="utf-8"))
    assert draft["题材方向"] == "都市悬疑+轻异能"
    assert draft["platform"] == "fanqie"


def test_deep_mode_init_cli_creates_project_skeleton(tmp_path: Path) -> None:
    project = tmp_path / "深潮秘档"
    result = _run([
        sys.executable,
        str(INK),
        "init",
        str(project),
        "深潮秘档",
        "都市悬疑",
        "--protagonist-name",
        "闻照",
        "--protagonist-desire",
        "查清父亲失踪前留下的潮汐档案",
        "--protagonist-flaw",
        "过度相信证据而忽略人的动机",
        "--golden-finger-name",
        "潮汐档案",
        "--golden-finger-type",
        "信息",
        "--golden-finger-style",
        "冷静旁白型",
        "--core-selling-points",
        "事故倒计时,旧城档案,记忆代价",
        "--platform",
        "qidian",
        "--target-chapters",
        "60",
        "--target-words",
        "180000",
    ])

    assert result.returncode == 0, result.stderr
    assert "Project initialized at:" in result.stdout
    assert (project / ".ink" / "state.json").exists()
    assert (project / "设定集" / "主角卡.md").exists()
    assert "闻照" in (project / "设定集" / "主角卡.md").read_text(encoding="utf-8")


def test_daily_workflow_clear_cli_writes_workflow_state_and_trace(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    workflow_state = project / ".ink" / "workflow_state.json"
    workflow_state.write_text(
        json.dumps({
            "current_task": {
                "command": "ink-write",
                "status": "running",
                "args": {"chapter_num": 12},
                "failed_steps": [],
                "retry_count": 0,
            },
            "last_stable_state": None,
            "history": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run([sys.executable, str(INK), "--project-root", str(project), "workflow", "clear"])

    assert result.returncode == 0, result.stderr
    assert "中断任务已清除" in result.stdout
    saved = json.loads(workflow_state.read_text(encoding="utf-8"))
    assert saved["current_task"] is None
    assert (project / ".ink" / "observability" / "call_trace.jsonl").exists()


def test_auto_checkpoint_cli_reports_level_json(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    result = _run([sys.executable, str(INK), "--project-root", str(project), "checkpoint-level", "--chapter", "20"])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "chapter": 20,
        "review": True,
        "review_range": [16, 20],
        "audit": "standard",
        "macro": "Tier2",
        "disambig": True,
    }
    assert (project / ".ink" / "state.json").exists()


def test_debug_mode_toggle_cli_writes_local_config(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    result = _run([
        sys.executable,
        "-m",
        "ink_writer.debug.cli",
        "--project-root",
        str(project),
        "--global-yaml",
        str(FIXTURES / "debug.yaml"),
        "toggle",
        "layer_c",
        "off",
    ])

    local_cfg = project / ".ink-debug" / "config.local.yaml"
    assert result.returncode == 0, result.stderr
    assert "已写入" in result.stdout
    assert local_cfg.exists()
    assert "layer_c_invariants: false" in local_cfg.read_text(encoding="utf-8")


def test_debug_mode_report_cli_indexes_jsonl_and_writes_report(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "run_id": "phase3-run",
        "source": "layer_c_invariant",
        "skill": "ink-write",
        "kind": "writer.short_word_count",
        "severity": "warn",
        "message": "第12章正文低于平台下限",
        "chapter": 12,
        "step": "Step 2B",
    }
    debug_dir = project / ".ink-debug"
    debug_dir.mkdir()
    (debug_dir / "events.jsonl").write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")

    result = _run([
        sys.executable,
        "-m",
        "ink_writer.debug.cli",
        "--project-root",
        str(project),
        "--global-yaml",
        str(FIXTURES / "debug.yaml"),
        "report",
        "--since",
        "1d",
        "--run-id",
        "phase3-run",
        "--severity",
        "warn",
    ])

    assert result.returncode == 0, result.stderr
    assert "报告已生成" in result.stdout
    reports = list((debug_dir / "reports").glob("manual-*.md"))
    assert len(reports) == 1
    assert "writer.short_word_count" in reports[0].read_text(encoding="utf-8")


def test_cross_platform_where_cli_accepts_chinese_and_space_path(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    result = _run([sys.executable, str(INK), "--project-root", str(project), "where"])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(project.resolve())
    assert (project / ".ink" / "state.json").exists()


def test_external_environment_manifest_cli_passes_version_consistency() -> None:
    result = _run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "maintenance" / "check_plugin_version_consistency.py"),
        "--plugin-json",
        str(FIXTURES / "plugin.json"),
        "--marketplace-json",
        str(FIXTURES / "marketplace.json"),
    ])

    assert result.returncode == 0, result.stderr
    assert "PASS  ink-writer version aligned" in result.stdout
    assert (FIXTURES / "plugin.json").exists()


def test_v27_bootstrap_scanner_and_interactive_bootstrap_cli(tmp_path: Path) -> None:
    scan_dir = tmp_path / "empty-start"
    scan_dir.mkdir()
    (scan_dir / "README.md").write_text("说明", encoding="utf-8")
    (scan_dir / "notes.draft.md").write_text("草稿", encoding="utf-8")
    small = scan_dir / "短蓝本.md"
    large = scan_dir / "旧城雨夜蓝本.md"
    small.write_text("### 题材方向\n都市\n", encoding="utf-8")
    large.write_text((FIXTURES / "quick_blueprint.md").read_text(encoding="utf-8"), encoding="utf-8")

    scan = _run([
        sys.executable,
        str(REPO_ROOT / "ink-writer" / "scripts" / "blueprint_scanner.py"),
        "--cwd",
        str(scan_dir),
    ])
    assert scan.returncode == 0, scan.stderr
    assert scan.stdout.strip() == str(large)
    assert large.exists()

    out = tmp_path / ".ink-auto-blueprint.md"
    answers = "\n".join([
        "都市悬疑",
        "退职事故调查员，想救人却害怕相信自己",
        "信息",
        "听见明日事故的回响",
        "旧城事故记录会提前变成现实",
        "fanqie",
        "2",
    ]) + "\n"
    bootstrap = _run([
        "bash",
        str(REPO_ROOT / "ink-writer" / "scripts" / "interactive_bootstrap.sh"),
        str(out),
    ], input_text=answers)

    assert bootstrap.returncode == 0, bootstrap.stderr
    assert "蓝本已落盘" in bootstrap.stderr
    assert out.exists()
    assert "### 核心冲突" in out.read_text(encoding="utf-8")
