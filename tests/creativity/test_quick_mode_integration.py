"""v18 US-010：ink-init Quick Mode → creativity CLI 集成测试。

场景：Quick Mode 每次重抽书名后调用 ``python -m ink_writer.creativity.cli validate
--book-title '<候选>' --strict``。本测试覆盖：

1. 合法书名 → exit 0、all_passed=true。
2. 黑名单命中 → --strict 下 exit 1、all_passed=false、validator 真 fail。
3. --strict off 回退默认 → 即便命中也 exit 0（Quick Mode 可依旧用 JSON 字段判）。
4. --book-title 与 --input 互斥。
5. 空书名 → exit 1（--strict）。
6. 黑名单 JSON 必须含相应 token，防止数据源漂移绕过校验。
7. 零回归：`python -m ink_writer.creativity validate --input ...` 原路径不变。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "ink_writer.creativity"] + args,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout, encoding="utf-8",
    )


class TestBookTitleQuickCheck:
    def test_pass_returns_exit_0(self):
        """合法书名（非黑名单命中）→ exit 0。"""
        result = _run_cli(
            ["validate", "--book-title", "山风穿门", "--strict"]
        )
        assert result.returncode == 0, f"stderr={result.stderr} stdout={result.stdout}"
        data = json.loads(result.stdout)
        assert data["all_passed"] is True
        assert data["results"][0]["scheme_id"] == "(book_title_only)"
        assert data["results"][0]["checks"]["book_title"]["passed"] is True

    def test_blacklist_hit_strict_exit_1(self):
        """黑名单 prefix 命中 + --strict → exit 1（v18 US-010 核心需求）。"""
        # 先从 blacklist.json 读一个实际存在的 prefix token，确保测试不因数据漂移绕过。
        blacklist = json.loads(
            (ROOT / "data" / "naming" / "blacklist.json").read_text(encoding="utf-8")
        )
        prefix_tokens = (blacklist.get("book_title_prefix_ban") or {}).get("tokens") or []
        assert prefix_tokens, "blacklist.json.book_title_prefix_ban.tokens 必须非空"
        bad_title = prefix_tokens[0] + "某某书"  # 保证以 banned prefix 开头
        result = _run_cli(
            ["validate", "--book-title", bad_title, "--strict"]
        )
        assert result.returncode == 1, (
            f"期望 exit 1（Quick Mode 降档重抽）, 实际 {result.returncode}; "
            f"stdout={result.stdout}"
        )
        data = json.loads(result.stdout)
        assert data["all_passed"] is False
        violations = data["results"][0]["checks"]["book_title"]["violations"]
        assert any(
            v["id"].startswith("BOOK_TITLE") for v in violations
        ), f"应抛 BOOK_TITLE_* 违规，实际 {violations}"

    def test_blacklist_hit_without_strict_exit_0_but_fail_field(self):
        """无 --strict → 回退 US-013 行为：exit 0 + all_passed=false。"""
        blacklist = json.loads(
            (ROOT / "data" / "naming" / "blacklist.json").read_text(encoding="utf-8")
        )
        suffix_tokens = (blacklist.get("book_title_suffix_ban") or {}).get("tokens") or []
        prefix_tokens = (blacklist.get("book_title_prefix_ban") or {}).get("tokens") or []
        assert suffix_tokens or prefix_tokens
        bad_title = (
            "某某" + suffix_tokens[0] if suffix_tokens else prefix_tokens[0] + "某某"
        )
        result = _run_cli(["validate", "--book-title", bad_title])
        assert result.returncode == 0  # 缺省行为不变
        data = json.loads(result.stdout)
        assert data["all_passed"] is False

    def test_book_title_and_input_mutually_exclusive(self, tmp_path: Path):
        """--book-title 与 --input 互斥（防用户误用）。"""
        draft = tmp_path / "draft.json"
        draft.write_text(json.dumps({"schemes": []}), encoding="utf-8")
        result = _run_cli(
            [
                "validate",
                "--book-title",
                "山风穿门",
                "--input",
                str(draft),
                "--strict",
            ]
        )
        assert result.returncode == 2
        assert "互斥" in result.stderr

    def test_empty_book_title_strict_exit_1(self):
        """空书名 → HARD 违规 → --strict 下 exit 1。"""
        result = _run_cli(["validate", "--book-title", "", "--strict"])
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["all_passed"] is False
        violations = data["results"][0]["checks"]["book_title"]["violations"]
        assert any(v["id"] == "BOOK_TITLE_EMPTY" for v in violations)

    def test_missing_both_inputs_exit_2(self):
        """--input 与 --book-title 都没提供 → exit 2（参数错误）。"""
        result = _run_cli(["validate", "--strict"])
        assert result.returncode == 2
        assert "必须提供" in result.stderr

    def test_file_output_with_book_title(self, tmp_path: Path):
        """--book-title 也支持 --output 写文件，便于 Quick Mode 归档审计。"""
        out_f = tmp_path / "val.json"
        result = _run_cli(
            [
                "validate",
                "--book-title",
                "山风穿门",
                "--output",
                str(out_f),
                "--strict",
            ]
        )
        assert result.returncode == 0
        assert result.stdout == "" or result.stdout.strip() == ""
        data = json.loads(out_f.read_text(encoding="utf-8"))
        assert data["all_passed"] is True


class TestBackwardCompatibility:
    """v18 US-010 不得回退 v16 US-013 行为。"""

    def test_input_json_path_unchanged(self, tmp_path: Path):
        """--input 原路径 exit 0 + all_passed 字段，无 --strict 时即便失败也不报错。"""
        draft = {
            "schemes": [
                {"id": "s1", "book_title": "我的斗罗大陆", "character_names": []}
            ]
        }
        input_f = tmp_path / "draft.json"
        input_f.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        result = _run_cli(["validate", "--input", str(input_f)])
        assert result.returncode == 0  # US-013 契约保持
        data = json.loads(result.stdout)
        assert data["all_passed"] is False

    def test_input_json_strict_mode(self, tmp_path: Path):
        """已有 --input 路径叠加 --strict：失败方案 → exit 1（新增能力）。"""
        draft = {
            "schemes": [
                {"id": "s1", "book_title": "我的斗罗大陆", "character_names": []}
            ]
        }
        input_f = tmp_path / "draft.json"
        input_f.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        result = _run_cli(["validate", "--input", str(input_f), "--strict"])
        assert result.returncode == 1


class TestValidatorModulesPreserved:
    """v18 US-010 要求保留 NG-4/G-004 三模块：name_validator / gf_validator / sensitive_lexicon_validator。"""

    def test_three_validators_importable(self):
        """确保三文件保留、符号导入无漂移（零回归）。"""
        from ink_writer.creativity import (  # noqa: F401
            gf_validator,
            name_validator,
            sensitive_lexicon_validator,
        )

        assert hasattr(name_validator, "validate_book_title")
        assert hasattr(name_validator, "validate_character_name")
        assert hasattr(gf_validator, "validate_golden_finger")
        assert hasattr(sensitive_lexicon_validator, "validate_density")
