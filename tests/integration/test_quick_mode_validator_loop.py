"""v16 US-013：Quick Mode 三套方案集成校验测试。

模拟 Quick Mode 生成 3 套方案后交由 creativity CLI 校验，验证能拦下已知俗套样本。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "ink_writer.creativity"] + args,
        env=env, capture_output=True, text=True, timeout=30, encoding="utf-8",
    )


def test_quick_mode_3_schemes_mixed_pass_and_fail(tmp_path: Path):
    """3 套方案：1 合规 + 2 踩俗套，CLI 应汇报 all_passed=False 且精确定位。"""
    draft = {
        "schemes": [
            # S1：合规方案
            {
                "id": "S1_clean",
                "book_title": "锈铁观音",
                "character_names": [
                    {"name": "池冷灰", "role": "main"},
                    {"name": "崔蚀", "role": "side"},
                ],
                "golden_finger": {
                    "dimension": "时间",
                    "cost": "每次回溯扣 30 秒，触发即被对手同步定位。",
                    "one_liner": "我能倒流三十秒，但每次忘一人。",
                },
            },
            # S2：书名踩陈词前缀
            {
                "id": "S2_bad_title",
                "book_title": "我的斗罗大陆",
                "character_names": [{"name": "叶辰", "role": "main"}],
                "golden_finger": {
                    "dimension": "规则",
                    "cost": "每次签约立即暴露血脉印记给神级存在。",
                    "one_liner": "凡签我名的人，都会梦见自己死法。",
                },
            },
            # S3：金手指踩禁用词 + 维度非白名单
            {
                "id": "S3_bad_gf",
                "book_title": "黄铜钟声",
                "character_names": [{"name": "裴断雪", "role": "main"}],
                "golden_finger": {
                    "dimension": "纯战斗力",
                    "cost": "修为暴涨，无上限。",
                    "one_liner": "系统签到，万倍返还。",
                },
            },
        ]
    }
    input_f = tmp_path / "draft.json"
    output_f = tmp_path / "val.json"
    input_f.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(
        ["validate", "--input", str(input_f), "--output", str(output_f)]
    )
    assert result.returncode == 0, result.stderr

    out = json.loads(output_f.read_text(encoding="utf-8"))
    assert out["all_passed"] is False

    results = {r["scheme_id"]: r for r in out["results"]}

    # S1 通过
    assert results["S1_clean"]["passed"] is True, (
        f"S1 期望通过，违规={results['S1_clean']['checks']}"
    )

    # S2 失败（book_title 前缀黑名单 + 人名 male 黑名单）
    assert results["S2_bad_title"]["passed"] is False
    assert "book_title" in results["S2_bad_title"]["checks"]
    assert not results["S2_bad_title"]["checks"]["book_title"]["passed"]

    # S3 失败（gf dimension 非白名单 + banned words）
    assert results["S3_bad_gf"]["passed"] is False
    gf_violations = results["S3_bad_gf"]["checks"]["golden_finger"]["violations"]
    violation_ids = {v["id"] for v in gf_violations}
    assert "GF1_DIMENSION_NOT_IN_WHITELIST" in violation_ids
    assert "GF1_BANNED_WORD" in violation_ids
