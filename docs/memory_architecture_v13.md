# Memory Architecture v13 — 单一事实源设计文档

## 1. 动机

v12 架构中 `state.json` 和 `index.db` 双存储并存，存在以下问题：

| 问题 | 影响 |
|------|------|
| 数据漂移 | state.json 与 index.db 同一实体字段不一致（如 protagonist_state.power vs entities.current_json） |
| 恢复困难 | state.json 损坏后无法从 index.db 重建完整状态 |
| 写入竞争 | JSON 文件级锁 vs SQLite 行级锁，并发时 state.json 成瓶颈 |
| 审计复杂 | ink-audit 需同时校验两个存储，逻辑分散 |

## 2. 设计目标

1. **SQLite 为唯一事实源**（Single Source of Truth）
2. **state.json 降级为可重建视图缓存**（随时可删除重建）
3. **零数据丢失迁移**（半写项目无损升级）
4. **向后兼容**（读 state.json 的旧代码无需修改，只是数据来源变了）

## 3. 架构总览

```
┌─────────────────────────────────────────────────┐
│                   SQLite (index.db)              │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ entities     │  │ relationships│  │ chapters│ │
│  │ aliases      │  │ rel_events   │  │ scenes  │ │
│  │ state_changes│  │ plot_thread  │  │ ...     │ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ NEW: state_kv (key-value 单例状态存储)       │ │
│  │  project_info, progress, protagonist_state,  │ │
│  │  world_settings, strand_tracker,             │ │
│  │  harness_config, hook_contract_config         │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌──────────────────┐  ┌────────────────────┐    │
│  │ NEW: disambig_log│  │ NEW: review_ckpts  │    │
│  └──────────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────┘
                      │
                      │ rebuild_state_json()
                      ▼
              ┌───────────────┐
              │  state.json   │  ← 视图缓存，可随时重建
              │  (derived)    │
              └───────────────┘
```

## 4. 新增表设计

### 4.1 `state_kv` — 单例状态键值存储

存储 state.json 中的"单例"字段（项目信息、进度、主角状态等）。

```sql
CREATE TABLE IF NOT EXISTS state_kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,       -- JSON 序列化值
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**存储的 key**：

| key | 对应 state.json 字段 | 值类型 |
|-----|---------------------|--------|
| `project_info` | `.project_info` | ProjectInfo JSON |
| `progress` | `.progress` | ProgressState JSON |
| `protagonist_state` | `.protagonist_state` | ProtagonistState JSON |
| `world_settings` | `.world_settings` | WorldSettings JSON |
| `strand_tracker` | `.strand_tracker` | StrandTracker JSON |
| `harness_config` | `.harness_config` | dict JSON |
| `hook_contract_config` | `.hook_contract_config` | dict JSON |
| `schema_version` | `.schema_version` | int (as string) |

### 4.2 `disambiguation_log` — 消歧记录

```sql
CREATE TABLE IF NOT EXISTS disambiguation_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL,   -- 'warning' | 'pending'
    payload    TEXT NOT NULL,   -- JSON 序列化的单条记录
    chapter    INTEGER,
    status     TEXT DEFAULT 'active',  -- 'active' | 'resolved'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_disambig_category_status
    ON disambiguation_log(category, status);
```

### 4.3 `review_checkpoint_entries` — 审查检查点

```sql
CREATE TABLE IF NOT EXISTS review_checkpoint_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    payload    TEXT NOT NULL,   -- JSON 序列化的检查点数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 5. `rebuild_state_json()` — 视图重建

核心函数，从 SQLite 读取所有数据，组装为与现有 state.json 兼容的 dict，写入文件。

```python
def rebuild_state_json(config) -> dict:
    """从 SQLite 重建 state.json（视图缓存）"""
    kv = read_all_state_kv(config)  # {key: parsed_json}

    state = {
        "schema_version": int(kv.get("schema_version", 9)),
        "project_info": kv.get("project_info", {}),
        "progress": kv.get("progress", {}),
        "protagonist_state": kv.get("protagonist_state", {}),
        "relationships": {},  # 从 relationships 表汇总
        "disambiguation_warnings": load_disambig("warning"),
        "disambiguation_pending": load_disambig("pending"),
        "world_settings": kv.get("world_settings", {...}),
        "plot_threads": rebuild_plot_threads(),  # 从 plot_thread_registry
        "review_checkpoints": load_review_checkpoints(),
        "chapter_meta": rebuild_recent_chapter_meta(limit=20),
        "strand_tracker": kv.get("strand_tracker", {...}),
    }

    # 附加 config 字段
    for cfg_key in ("harness_config", "hook_contract_config"):
        if cfg_key in kv:
            state[cfg_key] = kv[cfg_key]

    return state
```

## 6. 迁移策略 (v8 → v9)

### 6.1 迁移步骤

1. **备份** state.json → state.json.bak.8
2. **读取** state.json 全量数据
3. **写入 state_kv**：逐字段 INSERT OR REPLACE
4. **写入 disambiguation_log**：遍历 warnings + pending
5. **写入 review_checkpoint_entries**：遍历 review_checkpoints
6. **更新 schema_version** = 9
7. **重建 state.json**（验证往返一致性）
8. **标记** `_migrated_to_single_source: true`

### 6.2 回滚

- 恢复 state.json.bak.8
- DROP 新表（state_kv, disambiguation_log, review_checkpoint_entries）
- schema_version 回退到 8

### 6.3 半写项目兼容

- 迁移前检测 schema_version ≥ 9 → 跳过
- state.json 缺少字段 → 使用默认值填充
- index.db 不存在 → 先创建（IndexManager.__init__ 自动建表）

## 7. 读写流程变更

### 7.1 写入流程（StateManager.flush()）

```
Before (v12):
  state.json ← 直接写入
  index.db   ← 同步写入（可能失败）

After (v13):
  index.db   ← 先写入（事实源）
  state.json ← rebuild_state_json()（视图缓存）
```

### 7.2 读取流程（StateManager._load_state()）

```
Before (v12):
  读取 state.json → 内存

After (v13):
  读取 state.json → 内存 （不变，因为 state.json 是最新缓存）
  如果 state.json 缺失/损坏 → rebuild_state_json()
```

## 8. 对现有组件的影响

| 组件 | 影响 | 变更 |
|------|------|------|
| StateManager | 中 | flush() 先写 SQLite，再 rebuild state.json |
| SQLStateManager | 中 | 新增 state_kv/disambig/checkpoint 读写方法 |
| IndexManager | 小 | __init__ 新增 3 张表的 CREATE |
| ink-audit | 小 | 新增 state_kv 一致性检查（可选） |
| ink-migrate | 小 | 注册 v8→v9 迁移 |
| data-agent | 无 | 不直接读写 state.json |
| context-agent | 无 | 通过 StateManager 接口 |
| 其他 agent | 无 | 通过 StateManager 接口 |

## 9. 测试计划

1. **单元测试**：state_kv CRUD、rebuild_state_json 往返一致性
2. **迁移测试**：v8 fixture → v9、半写项目迁移、回滚验证
3. **集成测试**：StateManager 写入后 state.json 与 SQLite 一致
4. **回归测试**：现有全量 pytest 通过
