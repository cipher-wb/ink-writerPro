"""US-009: state_schema.py 扩展创意指纹字段测试。

验证：
  1. CreativeFingerprint 模型 5 字段默认值为空
  2. StateModel 默认含 project_info.creative_fingerprint
  3. 从旧 state.json（schema_version 9）加载能升级且不丢字段
  4. schema_version 从 10 起
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))

from state_schema import CreativeFingerprint, StateModel  # noqa: E402


def test_creative_fingerprint_defaults_empty():
    cf = CreativeFingerprint()
    assert cf.meta_rules_hit == []
    assert cf.perturbation_pairs == []
    assert cf.gf_checks == []
    assert cf.style_voice is None
    assert cf.market_avoid == []


def test_state_model_includes_creative_fingerprint():
    state = StateModel()
    assert state.schema_version == 10
    assert hasattr(state.project_info, "creative_fingerprint")
    assert isinstance(state.project_info.creative_fingerprint, CreativeFingerprint)


def test_creative_fingerprint_populated():
    cf = CreativeFingerprint(
        meta_rules_hit=["M01", "M03", "M11"],
        perturbation_pairs=[{"pair_id": "P1", "pattern": "A", "seed_a": "x", "seed_b": "y"}],
        gf_checks=[1, 1, 0],
        style_voice="V3",
        market_avoid=["重生复仇", "系统签到"],
    )
    assert cf.meta_rules_hit == ["M01", "M03", "M11"]
    assert cf.style_voice == "V3"
    assert len(cf.perturbation_pairs) == 1


def test_legacy_state_json_loadable():
    """旧 schema_version 9 的 state.json 应能无损加载（extra=allow + 默认字段填充）。"""
    legacy = {
        "schema_version": 9,
        "project_info": {
            "title": "测试小说",
            "genre": "仙侠",
        },
        "progress": {},
    }
    state = StateModel.model_validate(legacy)
    # Pydantic 不会自动升级 schema_version，但新字段应有 default
    assert state.project_info.title == "测试小说"
    assert state.project_info.creative_fingerprint.meta_rules_hit == []


def test_state_json_roundtrip(tmp_path):
    """构造 → dump → load 往返无损。"""
    original = StateModel()
    original.project_info.title = "往返测试"
    original.project_info.creative_fingerprint.meta_rules_hit = ["M02", "M05"]
    original.project_info.creative_fingerprint.style_voice = "V2"

    state_file = tmp_path / "state.json"
    state_file.write_text(original.model_dump_json(), encoding="utf-8")
    loaded = StateModel.model_validate(json.loads(state_file.read_text(encoding="utf-8")))

    assert loaded.project_info.creative_fingerprint.meta_rules_hit == ["M02", "M05"]
    assert loaded.project_info.creative_fingerprint.style_voice == "V2"
