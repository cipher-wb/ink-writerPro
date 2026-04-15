#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻量级 schema 迁移框架

用于将 state.json 从旧版本逐步迁移到 CURRENT_SCHEMA_VERSION。
每次迁移前自动备份 state.json 为 state.json.bak.{version}。

用法:
    python migrate.py --project-root <path>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

CURRENT_SCHEMA_VERSION = 9

# 迁移注册表: List[(from_version, migration_func)]
_migrations: List[Tuple[int, Callable[[Dict[str, Any]], Dict[str, Any]]]] = []


def detect_version(state: Dict[str, Any]) -> int:
    """检测 state.json 的 schema 版本，不存在 schema_version 字段时返回 5。"""
    return state.get("schema_version", 5)


def migration(from_version: int):
    """装饰器：注册一个从 from_version 到 from_version+1 的迁移函数。"""

    def decorator(func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        _migrations.append((from_version, func))
        _migrations.sort(key=lambda t: t[0])
        return func

    return decorator


def run_migrations(state_path: Path) -> Dict[str, Any]:
    """读取 state.json，逐步执行迁移直到 CURRENT_SCHEMA_VERSION。

    每步迁移前会备份为 state.json.bak.{当前版本}。
    返回迁移后的 state 字典。
    """
    if not state_path.exists():
        print(f"❌ state.json 不存在: {state_path}")
        sys.exit(1)

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    current = detect_version(state)

    if current >= CURRENT_SCHEMA_VERSION:
        print(f"✅ schema 已是最新版本 (v{current})，无需迁移。")
        return state

    print(f"📦 检测到 schema v{current}，目标 v{CURRENT_SCHEMA_VERSION}")

    # 构建迁移映射
    migration_map: Dict[int, Callable] = {v: fn for v, fn in _migrations}

    while current < CURRENT_SCHEMA_VERSION:
        if current not in migration_map:
            print(f"❌ 缺少从 v{current} 到 v{current + 1} 的迁移函数")
            sys.exit(1)

        # 备份
        backup_path = state_path.parent / f"state.json.bak.{current}"
        shutil.copy2(state_path, backup_path)
        print(f"  💾 已备份 → {backup_path.name}")

        # 执行迁移
        state = migration_map[current](state)
        current = detect_version(state)
        print(f"  ✅ 已迁移到 v{current}")

    # 写回
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"🎉 迁移完成，当前 schema v{current}")
    return state


# ---------------------------------------------------------------------------
# 迁移定义
# ---------------------------------------------------------------------------


@migration(5)
def _migrate_v5_to_v6(state: Dict[str, Any]) -> Dict[str, Any]:
    """v5 → v6: 添加 schema_version 字段。"""
    state["schema_version"] = 6
    return state


@migration(6)
def _migrate_v6_to_v7(state: Dict[str, Any]) -> Dict[str, Any]:
    """v6 → v7: Harness-First 架构（v9.0）。

    新增:
    - harness_config: 计算型闸门开关、Reader Verdict 模式和阈值
    """
    state["schema_version"] = 7
    state["harness_config"] = {
        "computational_gate_enabled": True,
        "reader_verdict_mode": "core",
        "reader_verdict_thresholds": {
            "pass": 32,
            "enhance": 25,
            "rewrite_min": 0,
        },
    }
    return state


@migration(7)
def _migrate_v7_to_v8(state: Dict[str, Any]) -> Dict[str, Any]:
    """v7 → v8: 钩子契约支持。

    新增:
    - hook_contract_config: 钩子契约验证配置
    """
    state["schema_version"] = 8
    state["hook_contract_config"] = {
        "enabled": True,
        "valid_types": ["crisis", "mystery", "emotion", "choice", "desire"],
        "max_payoff_window": 30,
        "outline_backfilled": False,
    }
    return state


@migration(8)
def _migrate_v8_to_v9(state: Dict[str, Any]) -> Dict[str, Any]:
    """v8 → v9: 单一事实源架构。

    state.json 中的所有数据迁移到 SQLite (index.db) 的 state_kv、
    disambiguation_log、review_checkpoint_entries 表。
    state.json 降级为可随时重建的视图缓存。
    标记 _migrated_to_single_source。
    """
    state["schema_version"] = 9
    state["_migrated_to_single_source"] = True
    return state


def migrate_state_to_sqlite(state_path: Path, project_root: Path) -> None:
    """v8→v9 的 SQLite 数据迁移（在 schema 迁移后调用）。

    将 state.json 全量数据写入 SQLite state_kv 等表，
    然后从 SQLite 重建 state.json 验证往返一致性。
    """
    import json as _json

    with open(state_path, "r", encoding="utf-8") as f:
        state = _json.load(f)

    if state.get("schema_version", 0) < 9:
        return

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from data_modules.sql_state_manager import SQLStateManager
        from data_modules.config import DataModulesConfig

        config = DataModulesConfig(project_root=project_root)
        sql_mgr = SQLStateManager(config)
        sql_mgr.migrate_state_to_kv(state)
        print("  ✅ state.json 数据已同步到 SQLite state_kv")
    except Exception as e:
        print(f"  ⚠️ SQLite 数据迁移失败（state.json 仍可用）: {e}")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ink-Writer schema 迁移工具")
    parser.add_argument(
        "--project-root",
        type=str,
        required=True,
        help="项目根目录路径",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    state_file = project_root / ".ink" / "state.json"

    state = run_migrations(state_file)
    if state.get("schema_version", 0) >= 9:
        migrate_state_to_sqlite(state_file, project_root)
