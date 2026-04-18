"""US-010: init_project.py 消费 Quick 输出写入 5 字段测试。

验证：
  1. 无创意参数时创建 state.json 含空 creative_fingerprint
  2. JSON 字符串传入时正确解析为列表
  3. 逗号分隔字符串 fallback 解析
  4. style_voice=V3 字面值
  5. CLI subprocess 能接收 --meta-rules-hit 等参数
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
INIT_SCRIPT = ROOT / "ink-writer" / "scripts" / "init_project.py"


def _read_state(project_dir: Path) -> dict:
    state_file = project_dir / ".ink" / "state.json"
    return json.loads(state_file.read_text(encoding="utf-8"))


def test_no_creative_params_empty_fingerprint(tmp_path):
    """直接调用 init_project()，无创意参数 → 空字段。"""
    # [FIX-11] removed: sys.path.insert(0, str(ROOT / "ink-writer" / "scripts"))
    import init_project  # noqa: E402

    project_dir = tmp_path / "book1"
    init_project.init_project(
        str(project_dir), title="测试1", genre="仙侠",
    )
    state = _read_state(project_dir)
    cf = state["project_info"]["creative_fingerprint"]
    assert cf["meta_rules_hit"] == []
    assert cf["perturbation_pairs"] == []
    assert cf["gf_checks"] == []
    assert cf["style_voice"] is None
    assert cf["market_avoid"] == []


def test_json_string_params_parsed(tmp_path):
    # [FIX-11] removed: sys.path.insert(0, str(ROOT / "ink-writer" / "scripts"))
    import init_project  # noqa: E402

    project_dir = tmp_path / "book2"
    init_project.init_project(
        str(project_dir), title="测试2", genre="都市",
        meta_rules_hit='["M01","M03","M11"]',
        perturbation_pairs='[{"pair_id":"P1","pattern":"A","seed_a":"x","seed_b":"y"}]',
        gf_checks="[1,1,0]",
        style_voice="V3",
        market_avoid='["重生复仇","系统签到"]',
    )
    state = _read_state(project_dir)
    cf = state["project_info"]["creative_fingerprint"]
    assert cf["meta_rules_hit"] == ["M01", "M03", "M11"]
    assert cf["gf_checks"] == [1, 1, 0]
    assert cf["style_voice"] == "V3"
    assert cf["market_avoid"] == ["重生复仇", "系统签到"]
    assert len(cf["perturbation_pairs"]) == 1
    assert cf["perturbation_pairs"][0]["pair_id"] == "P1"


def test_comma_separated_fallback(tmp_path):
    # [FIX-11] removed: sys.path.insert(0, str(ROOT / "ink-writer" / "scripts"))
    import init_project  # noqa: E402

    project_dir = tmp_path / "book3"
    init_project.init_project(
        str(project_dir), title="测试3", genre="末世",
        meta_rules_hit="M02,M05,M08",
        market_avoid="套路A, 套路B, 套路C",
    )
    state = _read_state(project_dir)
    cf = state["project_info"]["creative_fingerprint"]
    assert cf["meta_rules_hit"] == ["M02", "M05", "M08"]
    assert cf["market_avoid"] == ["套路A", "套路B", "套路C"]


def test_list_params_direct(tmp_path):
    # [FIX-11] removed: sys.path.insert(0, str(ROOT / "ink-writer" / "scripts"))
    import init_project  # noqa: E402

    project_dir = tmp_path / "book4"
    init_project.init_project(
        str(project_dir), title="测试4", genre="科幻",
        meta_rules_hit=["M04", "M07"],
        gf_checks=[1, 0, 1],
    )
    state = _read_state(project_dir)
    cf = state["project_info"]["creative_fingerprint"]
    assert cf["meta_rules_hit"] == ["M04", "M07"]
    assert cf["gf_checks"] == [1, 0, 1]


def test_cli_accepts_creative_args(tmp_path):
    """subprocess 调用 CLI 参数能正常被接收（避免 argparse 漏配）。"""
    project_dir = tmp_path / "book5"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'ink-writer' / 'scripts'}:{ROOT}"
    env["INK_SKIP_STYLE_RAG_INIT"] = "1"  # 跳过 CI 冷启动时 ~3min 的 FAISS 索引构建
    result = subprocess.run(
        [sys.executable, str(INIT_SCRIPT), str(project_dir), "CLI测试", "玄幻",
         "--meta-rules-hit", '["M06"]', "--style-voice", "V2"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    state = _read_state(project_dir)
    assert state["project_info"]["creative_fingerprint"]["meta_rules_hit"] == ["M06"]
    assert state["project_info"]["creative_fingerprint"]["style_voice"] == "V2"
