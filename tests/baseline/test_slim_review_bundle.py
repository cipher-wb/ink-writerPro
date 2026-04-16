"""Tests for ink-writer/scripts/slim_review_bundle.py"""

import json
import sys
from pathlib import Path

import pytest

# Ensure the script is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"))

from slim_review_bundle import (
    CHECKER_PROFILES,
    META_FIELDS,
    generate_slim_bundles,
    resolve_profile,
    slim_bundle,
)


def _make_full_bundle() -> dict:
    """Build a realistic full review bundle."""
    return {
        # meta fields
        "chapter": 5,
        "project_root": "/tmp/test_project",
        "chapter_file": "/tmp/test_project/正文/第0005章.md",
        "chapter_file_name": "第0005章.md",
        "chapter_char_count": 3000,
        "absolute_paths": {"project_root": "/tmp/test_project"},
        "allowed_read_files": ["/tmp/test_project/正文/第0005章.md"],
        "review_policy": {"primary_source": "review_bundle_file"},
        # content fields
        "chapter_text": "这是正文内容" * 100,
        "outline": "第五章大纲摘要",
        "previous_chapters": [{"chapter": 4, "summary": "前章摘要"}],
        "state_summary": "当前状态",
        "core_context": {"mcc": {"板块14": "数据"}},
        "scene_context": {"appearing_characters": [{"id": "c1", "name": "主角"}]},
        "memory_context": {"recent_events": ["event1"]},
        "reader_signal": {"hook_strength": 8},
        "genre_profile": {"genre": "玄幻"},
        "golden_three_contract": {"promise": "开篇承诺"},
        "writing_guidance": {"guidance": "风格指导"},
        "setting_snapshots": [{"name": "城市", "data": "描述"}],
        "narrative_commitments": [{"id": "nc1", "content": "承诺"}],
        "plot_structure_fingerprints": [{"pattern": "反转", "count": 3}],
    }


class TestResolveProfile:
    def test_core_checker(self):
        profile = resolve_profile("anti-detection-checker")
        assert profile == ["chapter_text"]

    def test_conditional_checker_maps_to_core(self):
        profile = resolve_profile("golden-three-checker")
        expected = CHECKER_PROFILES["reader-pull-checker"]
        assert profile == expected

    def test_unknown_checker_returns_none(self):
        assert resolve_profile("nonexistent-checker") is None


class TestSlimBundle:
    def test_anti_detection_minimal(self):
        full = _make_full_bundle()
        slimmed = slim_bundle(full, "anti-detection-checker")
        # Should have meta + chapter_text only
        assert "chapter_text" in slimmed
        assert "chapter" in slimmed
        assert "review_policy" in slimmed
        # Should NOT have heavy fields
        assert "previous_chapters" not in slimmed
        assert "scene_context" not in slimmed
        assert "outline" not in slimmed

    def test_consistency_heaviest(self):
        full = _make_full_bundle()
        slimmed = slim_bundle(full, "consistency-checker")
        assert "chapter_text" in slimmed
        assert "setting_snapshots" in slimmed
        assert "scene_context" in slimmed
        assert "previous_chapters" in slimmed
        assert "memory_context" in slimmed
        assert "narrative_commitments" in slimmed
        # Should NOT have unrelated fields
        assert "golden_three_contract" not in slimmed
        assert "reader_signal" not in slimmed

    def test_reader_pull_fields(self):
        full = _make_full_bundle()
        slimmed = slim_bundle(full, "reader-pull-checker")
        assert "chapter_text" in slimmed
        assert "reader_signal" in slimmed
        assert "golden_three_contract" in slimmed
        assert "memory_context" in slimmed
        assert "outline" in slimmed
        # Should NOT have
        assert "setting_snapshots" not in slimmed
        assert "previous_chapters" not in slimmed

    def test_unknown_checker_raises(self):
        full = _make_full_bundle()
        with pytest.raises(ValueError, match="Unknown checker"):
            slim_bundle(full, "nonexistent-checker")

    def test_conditional_checker_uses_mapped_profile(self):
        full = _make_full_bundle()
        pacing = slim_bundle(full, "pacing-checker")
        continuity = slim_bundle(full, "continuity-checker")
        assert set(pacing.keys()) == set(continuity.keys())

    def test_meta_fields_always_present(self):
        full = _make_full_bundle()
        for checker in CHECKER_PROFILES:
            slimmed = slim_bundle(full, checker)
            for mf in META_FIELDS:
                assert mf in slimmed, f"meta field {mf} missing in {checker} slim bundle"

    def test_slim_is_smaller_than_full(self):
        full = _make_full_bundle()
        full_size = len(json.dumps(full))
        slimmed = slim_bundle(full, "anti-detection-checker")
        slim_size = len(json.dumps(slimmed))
        assert slim_size < full_size


class TestGenerateSlimBundles:
    def test_generates_files(self, tmp_path):
        bundle_path = tmp_path / "full_bundle.json"
        bundle_path.write_text(json.dumps(_make_full_bundle()), encoding="utf-8")

        checkers = ["anti-detection-checker", "logic-checker"]
        result = generate_slim_bundles(bundle_path, checkers, tmp_path)

        assert len(result) == 2
        for checker in checkers:
            assert checker in result
            path = result[checker]
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["chapter"] == 5

    def test_fallback_on_unknown_checker(self, tmp_path):
        bundle_path = tmp_path / "full_bundle.json"
        bundle_path.write_text(json.dumps(_make_full_bundle()), encoding="utf-8")

        result = generate_slim_bundles(bundle_path, ["nonexistent-checker"], tmp_path)
        # Should fall back to original bundle path
        assert result["nonexistent-checker"] == bundle_path

    def test_mixed_known_and_unknown(self, tmp_path):
        bundle_path = tmp_path / "full_bundle.json"
        bundle_path.write_text(json.dumps(_make_full_bundle()), encoding="utf-8")

        checkers = ["anti-detection-checker", "nonexistent-checker"]
        result = generate_slim_bundles(bundle_path, checkers, tmp_path)
        # Known checker gets slim bundle
        assert result["anti-detection-checker"] != bundle_path
        assert result["anti-detection-checker"].exists()
        # Unknown checker falls back
        assert result["nonexistent-checker"] == bundle_path
