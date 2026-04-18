"""v16 US-013：creativity CLI 入口烟囱测试。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(args: list[str], env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "ink_writer.creativity"] + args,
        env=env, capture_output=True, text=True, timeout=30,
    )


class TestCliValidate:
    def test_all_pass_scheme(self, tmp_path: Path):
        draft = {
            "schemes": [
                {
                    "id": "s1",
                    "book_title": "山风穿门",
                    "character_names": [{"name": "卫砚之", "role": "main"}],
                    "golden_finger": {
                        "dimension": "信息",
                        "cost": "每次使用扣减 1 年寿命，触发即被对手同步定位。",
                        "one_liner": "我能听见死人的谎话，但每次少一年。",
                    },
                }
            ]
        }
        input_f = tmp_path / "draft.json"
        output_f = tmp_path / "val.json"
        input_f.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        result = _run_cli(
            ["validate", "--input", str(input_f), "--output", str(output_f)]
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(output_f.read_text(encoding="utf-8"))
        assert data["all_passed"] is True

    def test_book_title_banned_triggers_failure(self, tmp_path: Path):
        draft = {
            "schemes": [{
                "id": "s1",
                "book_title": "我的斗罗大陆",
                "character_names": [],
            }]
        }
        input_f = tmp_path / "draft.json"
        input_f.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        result = _run_cli(["validate", "--input", str(input_f)])
        assert result.returncode == 0  # CLI 不用 exit code 表示业务失败
        out = json.loads(result.stdout)
        assert out["all_passed"] is False
        assert "斗罗" in out["results"][0]["checks"]["book_title"]["violations"][0]["description"] or \
               out["results"][0]["checks"]["book_title"]["violations"][0]["id"].startswith("BOOK_TITLE")

    def test_missing_input_file_exit_2(self, tmp_path: Path):
        result = _run_cli(["validate", "--input", str(tmp_path / "nope.json")])
        assert result.returncode == 2

    def test_invalid_json_exit_2(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        result = _run_cli(["validate", "--input", str(bad)])
        assert result.returncode == 2

    def test_stdout_output_when_no_output_flag(self, tmp_path: Path):
        draft = {"schemes": [{"id": "s1", "book_title": "清风徐来"}]}
        input_f = tmp_path / "draft.json"
        input_f.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        result = _run_cli(["validate", "--input", str(input_f)])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["all_passed"] is True
