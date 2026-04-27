import json
import tempfile
from pathlib import Path
from ink_writer.platforms.resolver import (
    get_platform,
    resolve_platform_config,
    PLATFORM_QIDIAN,
    PLATFORM_FANQIE,
)


def test_get_platform_returns_qidian_when_state_has_platform():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "qidian"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN


def test_get_platform_returns_fanqie_when_state_has_platform():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "fanqie"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_FANQIE


def test_get_platform_defaults_to_qidian_when_platform_missing():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN


def test_get_platform_defaults_to_qidian_when_state_missing():
    root = Path(tempfile.mkdtemp())
    assert get_platform(root) == PLATFORM_QIDIAN


def test_resolve_platform_config_extracts_platform_block():
    raw = {
        "platforms": {
            "qidian": {"block_threshold": 60},
            "fanqie": {"block_threshold": 85},
        },
        "warn_threshold": 75,
    }
    qidian = resolve_platform_config(raw, PLATFORM_QIDIAN)
    fanqie = resolve_platform_config(raw, PLATFORM_FANQIE)
    assert qidian["block_threshold"] == 60
    assert qidian["warn_threshold"] == 75
    assert fanqie["block_threshold"] == 85
    assert fanqie["warn_threshold"] == 75


def test_resolve_platform_config_no_platforms_block_returns_original():
    raw = {"block_threshold": 60, "warn_threshold": 75}
    result = resolve_platform_config(raw, PLATFORM_FANQIE)
    assert result["block_threshold"] == 60
    assert result["warn_threshold"] == 75


def test_resolve_platform_config_platform_key_missing_falls_back_to_top():
    raw = {
        "platforms": {"qidian": {"block_threshold": 60}},
        "block_threshold": 70,
    }
    result = resolve_platform_config(raw, PLATFORM_FANQIE)
    assert result["block_threshold"] == 70


def test_get_platform_handles_corrupt_state_json():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    (ink_dir / "state.json").write_text("not valid json {{{", encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN


def test_get_platform_migrates_legacy_chinese_label():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "起点"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN


def test_get_platform_migrates_legacy_chinese_label_qidian():
    root = Path(tempfile.mkdtemp())
    ink_dir = root / ".ink"
    ink_dir.mkdir()
    state = {"project_info": {"platform": "起点中文网"}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert get_platform(root) == PLATFORM_QIDIAN
