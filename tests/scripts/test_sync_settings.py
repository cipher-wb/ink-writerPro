"""Tests for sync_settings.py (US-004)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts dir + project root are on sys.path for imports
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"
_PROJECT_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sync_settings import (
    _entity_to_markdown,
    _find_entity_in_settings,
    _read_existing_settings,
    _target_file,
    sync,
)


def _make_entity(**overrides):
    """Build a dict matching the structure returned by IndexManager.get_entities_by_type()."""
    base = {
        "id": "test_entity",
        "type": "角色",
        "canonical_name": "测试角色",
        "tier": "装饰",
        "desc": "",
        "first_appearance": 0,
        "last_appearance": 0,
        "is_protagonist": False,
        "is_archived": False,
        "current_json": {},
    }
    base.update(overrides)
    return base


# ── _entity_to_markdown ───────────────────────────────────────────────


def test_entity_to_markdown_basic():
    entity = _make_entity(canonical_name="裴砚", type="角色", tier="核心")
    md = _entity_to_markdown(entity)
    assert "## 裴砚" in md
    assert "- **类型**: 角色" in md
    assert "- **重要度**: 核心" in md


def test_entity_to_markdown_protagonist():
    entity = _make_entity(canonical_name="主角", is_protagonist=True, tier="核心")
    md = _entity_to_markdown(entity)
    assert "- **身份**: 主角" in md


def test_entity_to_markdown_with_description():
    entity = _make_entity(canonical_name="张三", desc="一个神秘人物")
    md = _entity_to_markdown(entity)
    assert "- **描述**: 一个神秘人物" in md


def test_entity_to_markdown_with_appearance():
    entity = _make_entity(canonical_name="李四", first_appearance=3, last_appearance=5)
    md = _entity_to_markdown(entity)
    assert "- **首次出场**: 第3章" in md
    assert "- **最后出场**: 第5章" in md


def test_entity_to_markdown_with_current_state():
    entity = _make_entity(
        canonical_name="王五", current_json={"realm": "元婴期", "faction": "天剑宗"}
    )
    md = _entity_to_markdown(entity)
    assert "元婴期" in md
    assert "天剑宗" in md


# ── _target_file ──────────────────────────────────────────────────────


def test_target_file_core_character():
    entity = _make_entity(type="角色", is_protagonist=True, tier="核心")
    assert _target_file("角色", entity) == "主角组.md"


def test_target_file_normal_character():
    entity = _make_entity(type="角色", tier="次要")
    assert _target_file("角色", entity) == "角色卡.md"


def test_target_file_faction():
    entity = _make_entity(type="势力", tier="重要")
    assert _target_file("势力", entity) == "世界观.md"


def test_target_file_location():
    entity = _make_entity(type="地点")
    assert _target_file("地点", entity) == "世界观.md"


# ── _read_existing_settings / _find_entity_in_settings ─────────────────


def test_read_existing_settings_parses_headers(tmp_path: Path):
    settings_dir = tmp_path / "設定集"
    settings_dir.mkdir()
    (settings_dir / "角色卡.md").write_text("## 裴砚\n- 类型: 角色\n\n## 折玥\n- 类型: 角色\n", encoding="utf-8")

    existing = _read_existing_settings(settings_dir)
    all_names = set().union(*existing.values())
    assert "裴砚" in all_names
    assert "折玥" in all_names


def test_find_entity_in_settings_found():
    existing = {"/fake/角色卡.md": {"裴砚", "折玥"}}
    assert _find_entity_in_settings("裴砚", existing) == "/fake/角色卡.md"


def test_find_entity_in_settings_not_found():
    existing = {"/fake/角色卡.md": {"裴砚"}}
    assert _find_entity_in_settings("张三", existing) is None


def test_read_existing_settings_empty_dir(tmp_path: Path):
    settings_dir = tmp_path / "empty"
    settings_dir.mkdir()
    existing = _read_existing_settings(settings_dir)
    assert existing == {}


# ── sync (integration) ────────────────────────────────────────────────


def _setup_project_with_entities(tmp_path: Path):
    """Create a minimal book project with index.db + settings dir."""
    pr = tmp_path / "book"
    pr.mkdir(parents=True)
    (pr / ".ink").mkdir()
    (pr / "設定集").mkdir()

    from ink_writer.core.index.index_manager import IndexManager
    from ink_writer.core.infra.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(str(pr))
    mgr = IndexManager(cfg)
    return pr, mgr


def test_sync_writes_new_entities_to_settings(tmp_path: Path):
    pr, mgr = _setup_project_with_entities(tmp_path)

    from ink_writer.core.index.index_types import EntityMeta

    mgr.upsert_entity(EntityMeta(
        id="char1", type="角色", canonical_name="主角A", tier="核心",
        desc="主角描述", first_appearance=1, is_protagonist=True,
    ))
    mgr.upsert_entity(EntityMeta(
        id="char2", type="角色", canonical_name="配角B", tier="次要",
        desc="配角", first_appearance=3,
    ))
    mgr.upsert_entity(EntityMeta(
        id="fac1", type="势力", canonical_name="天剑宗", tier="重要",
    ))

    result = sync(str(pr))
    assert result == 0

    protagonists = (pr / "設定集" / "主角组.md").read_text(encoding="utf-8")
    characters = (pr / "設定集" / "角色卡.md").read_text(encoding="utf-8")
    worldview = (pr / "設定集" / "世界观.md").read_text(encoding="utf-8")

    assert "主角A" in protagonists
    assert "配角B" in characters
    assert "天剑宗" in worldview


def test_sync_dry_run_does_not_write(tmp_path: Path):
    pr, mgr = _setup_project_with_entities(tmp_path)

    from ink_writer.core.index.index_types import EntityMeta

    mgr.upsert_entity(EntityMeta(
        id="char1", type="角色", canonical_name="主角A", tier="核心",
    ))

    result = sync(str(pr), dry_run=True)
    assert result == 0

    # 不应创建任何文件
    md_files = list((pr / "設定集").glob("**/*.md"))
    assert len(md_files) == 0


def test_sync_idempotent(tmp_path: Path):
    pr, mgr = _setup_project_with_entities(tmp_path)

    from ink_writer.core.index.index_types import EntityMeta

    mgr.upsert_entity(EntityMeta(
        id="char1", type="角色", canonical_name="主角A", tier="核心",
    ))

    # 第一次运行
    sync(str(pr))
    first_content = (pr / "設定集" / "主角组.md").read_text(encoding="utf-8")

    # 第二次运行
    sync(str(pr))
    second_content = (pr / "設定集" / "主角组.md").read_text(encoding="utf-8")

    assert first_content == second_content


def test_sync_no_db_skips_gracefully(tmp_path: Path):
    pr = tmp_path / "book"
    pr.mkdir(parents=True)
    (pr / "設定集").mkdir(parents=True, exist_ok=True)
    # No .ink/index.db

    result = sync(str(pr))
    assert result == 0


def test_sync_empty_db_no_entities(tmp_path: Path):
    pr, mgr = _setup_project_with_entities(tmp_path)
    # No entities inserted

    result = sync(str(pr))
    assert result == 0


def test_sync_respects_existing_entity(tmp_path: Path):
    """已存在于設定集中的实体不会被重复添加。"""
    pr, mgr = _setup_project_with_entities(tmp_path)

    # 预设设定集中已有"主角A"
    (pr / "設定集" / "主角组.md").write_text("## 主角A\n- 类型: 角色\n", encoding="utf-8")

    from ink_writer.core.index.index_types import EntityMeta

    mgr.upsert_entity(EntityMeta(
        id="char1", type="角色", canonical_name="主角A", tier="核心",
    ))
    mgr.upsert_entity(EntityMeta(
        id="char2", type="角色", canonical_name="配角B", tier="次要",
    ))

    result = sync(str(pr))
    assert result == 0

    protagonists = (pr / "設定集" / "主角组.md").read_text(encoding="utf-8")
    # 主角A 不应出现两次
    assert protagonists.count("## 主角A") == 1
    # 配角B 应该被追加
    characters = (pr / "設定集" / "角色卡.md").read_text(encoding="utf-8")
    assert "配角B" in characters


def test_sync_multiple_entity_types(tmp_path: Path):
    """多种实体类型各自路由到正确文件。"""
    pr, mgr = _setup_project_with_entities(tmp_path)

    from ink_writer.core.index.index_types import EntityMeta

    mgr.upsert_entity(EntityMeta(
        id="c1", type="角色", canonical_name="核心主角", tier="核心", is_protagonist=True,
    ))
    mgr.upsert_entity(EntityMeta(
        id="c2", type="角色", canonical_name="普通角色", tier="装饰",
    ))
    mgr.upsert_entity(EntityMeta(
        id="f1", type="势力", canonical_name="某宗门", tier="重要",
    ))
    mgr.upsert_entity(EntityMeta(
        id="l1", type="地点", canonical_name="某城池", tier="次要",
    ))
    mgr.upsert_entity(EntityMeta(
        id="i1", type="物品", canonical_name="神剑", tier="核心",
    ))

    result = sync(str(pr))
    assert result == 0

    assert "核心主角" in (pr / "設定集" / "主角组.md").read_text(encoding="utf-8")
    assert "普通角色" in (pr / "設定集" / "角色卡.md").read_text(encoding="utf-8")
    worldview = (pr / "設定集" / "世界观.md").read_text(encoding="utf-8")
    assert "某宗门" in worldview
    assert "某城池" in worldview
    assert "神剑" in worldview
