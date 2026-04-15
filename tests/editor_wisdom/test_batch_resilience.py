"""Tests for batch resilience: per-file error handling + periodic cache flushing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))

from importlib import import_module

classify_mod = import_module("03_classify")
classify = classify_mod.classify

extract_mod = import_module("05_extract_rules")
extract_rules = extract_mod.extract_rules


def _make_clean_index(data_dir: Path, source_dir: Path, count: int) -> list[dict]:
    data_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for i in range(count):
        name = f"file_{i}.md"
        path = source_dir / name
        path.write_text(f"# File {i}\n" + "内容" * 50, encoding="utf-8")
        entries.append({
            "path": str(path),
            "filename": name,
            "title": f"File {i}",
            "platform": "xhs",
            "word_count": 100,
            "file_hash": f"hash_{i}",
        })

    (data_dir / "clean_index.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return entries


def _make_classified_index(data_dir: Path, source_dir: Path, count: int) -> list[dict]:
    entries = _make_clean_index(data_dir, source_dir, count)
    for e in entries:
        e["categories"] = ["opening"]
        e["summary"] = "test"
    (data_dir / "classified.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return entries


def _classify_response(categories: list[str], summary: str) -> str:
    return json.dumps({"categories": categories, "summary": summary})


def _extract_response(rules: list[dict]) -> str:
    return json.dumps(rules)


class TestClassifyBatchResilience:
    """03_classify.py survives per-file LLM failures."""

    def test_failures_on_3rd_5th_7th_still_exits_zero(self, tmp_path: Path) -> None:
        fail_indices = {2, 4, 6}  # 0-indexed: 3rd, 5th, 7th
        call_counter = {"n": 0}

        def side_effect(model, system, user, max_tokens=0):
            idx = call_counter["n"]
            call_counter["n"] += 1
            if idx in fail_indices:
                raise RuntimeError(f"LLM failure on call {idx}")
            return _classify_response(["opening"], f"summary_{idx}")

        with patch.object(classify_mod, "call_llm", side_effect):
            data_dir = tmp_path / "data"
            _make_clean_index(data_dir, tmp_path / "src", 10)

            stats = classify(data_dir)

            assert stats["total"] == 7
            assert stats["api_calls"] == 7

            error_path = data_dir / "errors.log"
            assert error_path.exists()
            error_lines = [
                json.loads(line) for line in error_path.read_text(encoding="utf-8").strip().split("\n")
            ]
            assert len(error_lines) == 3

            for err in error_lines:
                assert "file_hash" in err
                assert "filename" in err
                assert err["error_type"] == "RuntimeError"
                assert "timestamp" in err

            cache_path = data_dir / "classify_cache.json"
            assert cache_path.exists()
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            assert len(cache) >= 4

    def test_cache_flushed_periodically(self, tmp_path: Path) -> None:
        """Cache is flushed at least once before the loop ends (every 10 items)."""

        def fake_call(model, system, user, max_tokens=0):
            return _classify_response(["misc"], "ok")

        with patch.object(classify_mod, "call_llm", fake_call):
            data_dir = tmp_path / "data"
            _make_clean_index(data_dir, tmp_path / "src", 15)

            with patch.object(classify_mod, "_save_cache", wraps=classify_mod._save_cache) as spy:
                classify(data_dir)
                assert spy.call_count >= 2


class TestExtractRulesBatchResilience:
    """05_extract_rules.py survives per-file LLM failures."""

    def test_failures_on_3rd_5th_7th_still_exits_zero(self, tmp_path: Path) -> None:
        fail_indices = {2, 4, 6}
        call_counter = {"n": 0}

        def side_effect(model, system, user, max_tokens=0):
            idx = call_counter["n"]
            call_counter["n"] += 1
            if idx in fail_indices:
                raise RuntimeError(f"LLM failure on call {idx}")
            return _extract_response([{
                "rule": f"规则{idx}",
                "why": "原因",
                "severity": "hard",
                "applies_to": ["all_chapters"],
            }])

        with patch.object(extract_mod, "call_llm", side_effect):
            data_dir = tmp_path / "data"
            _make_classified_index(data_dir, tmp_path / "src", 10)

            stats = extract_rules(data_dir)

            assert stats["api_calls"] == 7

            error_path = data_dir / "errors.log"
            assert error_path.exists()
            error_lines = [
                json.loads(line) for line in error_path.read_text(encoding="utf-8").strip().split("\n")
            ]
            assert len(error_lines) == 3

            for err in error_lines:
                assert err["error_type"] == "RuntimeError"

            cache_path = data_dir / "rules_cache.json"
            assert cache_path.exists()
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            assert len(cache) >= 4

    def test_cache_flushed_periodically(self, tmp_path: Path) -> None:
        def fake_call(model, system, user, max_tokens=0):
            return _extract_response([{
                "rule": "测试规则",
                "why": "原因",
                "severity": "soft",
                "applies_to": ["all_chapters"],
            }])

        with patch.object(extract_mod, "call_llm", fake_call):
            data_dir = tmp_path / "data"
            _make_classified_index(data_dir, tmp_path / "src", 15)

            with patch.object(extract_mod, "_save_cache", wraps=extract_mod._save_cache) as spy:
                extract_rules(data_dir)
                assert spy.call_count >= 2
