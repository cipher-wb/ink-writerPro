# state.json → SQLite 迁移指南

> **目标**：将 state.json 从"全局单文件"演进为"SQLite 主存储 + JSON 精简缓存"，消除并发写入风险，提升长篇项目的数据可靠性。
>
> **现状**：v5.4 已完成大数据字段迁移（entities/aliases/state_changes/relationships → index.db），state.json 仍保留 progress/protagonist_state/strand_tracker/chapter_meta/plot_threads 等运行时数据。

## 一、迁移策略：渐进式双写

不做一次性迁移，而是分3个阶段渐进推进，每阶段保持向后兼容。

### Phase 1：高频写入字段迁移（推荐先行）

将最容易产生并发冲突的字段迁移到 index.db 新表。

| 字段 | 当前位置 | 目标表 | 迁移理由 |
|------|---------|--------|---------|
| `progress.current_chapter` | state.json | `project_progress` | 每章都写，最高频 |
| `progress.current_volume` | state.json | `project_progress` | 同上 |
| `strand_tracker` | state.json | `strand_tracker_entries` | 每章追加，查询频繁 |
| `chapter_meta` | state.json | `chapter_meta`（已有） | 已部分迁移，完成剩余 |
| `review_checkpoints` | state.json | `review_checkpoints` | 独立审查流程写入 |

**新表 DDL**：

```sql
-- 项目进度（单行表）
CREATE TABLE IF NOT EXISTS project_progress (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_chapter INTEGER NOT NULL DEFAULT 0,
    current_volume INTEGER NOT NULL DEFAULT 1,
    total_chapters INTEGER NOT NULL DEFAULT 0,
    total_words INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Strand 追踪（每章一行）
CREATE TABLE IF NOT EXISTS strand_tracker_entries (
    chapter INTEGER PRIMARY KEY,
    dominant_strand TEXT NOT NULL CHECK (dominant_strand IN ('quest', 'fire', 'constellation')),
    quest_ratio REAL,
    fire_ratio REAL,
    constellation_ratio REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 审查检查点
CREATE TABLE IF NOT EXISTS review_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_range TEXT NOT NULL,
    report_file TEXT NOT NULL,
    overall_score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**双写策略**：
1. `state process-chapter` 同时写 index.db 新表和 state.json 对应字段
2. 读取时优先从 index.db 读，state.json 作为 fallback
3. 当所有调用方切换到 index.db 读取后，state.json 中的对应字段降级为"缓存"

### Phase 2：中频字段迁移

| 字段 | 目标表 | 说明 |
|------|--------|------|
| `protagonist_state` | `protagonist_snapshots` | 按章快照，支持任意章回溯 |
| `plot_threads.foreshadowing` | `foreshadowing`（已有？检查 index_manager） | 完成补全 |
| `disambiguation_warnings` | `disambiguation_log` | 消歧日志 |

### Phase 3：state.json 降级为配置文件

最终状态：
- **state.json** 仅保留不变或极少变的字段：`project_info`、`world_settings`、`preferences`
- **index.db** 存储所有运行时数据
- state.json 文件大小 < 2KB，消除并发写入问题

## 二、CLI 接口变更

### 新增命令

```bash
# 读取进度（从 index.db）
ink.py progress get

# 读取 strand 历史（从 index.db）
ink.py strand history --last-n 20

# 迁移命令（Phase 1）
ink.py migrate phase1 --dry-run
ink.py migrate phase1 --execute --backup
```

### 现有命令兼容

| 命令 | Phase 1 行为 | Phase 3 行为 |
|------|-------------|-------------|
| `state process-chapter` | 双写（index.db + state.json） | 仅写 index.db |
| `update-state` | 双写 | 仅写 index.db |
| `workflow *` | 不变（workflow_state.json 独立） | 不变 |
| `extract-context --format pack-json` | 优先读 index.db | 仅读 index.db |

## 三、Agent 和 Skill 适配

### 影响范围

| 模块 | 需要适配 | 说明 |
|------|---------|------|
| context-agent | Step 1/3 读取 state | 改为通过 CLI 读取，不直接解析 JSON |
| data-agent | Step D 写入 state | 已通过 `state process-chapter`，无需改 |
| ink-write | Step 0 预检 | 增加 index.db 新表存在性检查 |
| ink-query | 多处读取 state | CLI 命令已封装，改返回源即可 |
| ink-resume | 读取 workflow_state | 不受影响（独立文件） |

### 兼容性检测

```bash
# 预检命令：检测当前项目是否已完成 Phase 1 迁移
ink.py migrate check --phase 1
# 输出：MIGRATED / PENDING / PARTIAL
```

## 四、回滚方案

每个 Phase 迁移前自动备份：
```bash
cp .ink/state.json .ink/state.json.pre-phase{N}.bak
cp .ink/index.db .ink/index.db.pre-phase{N}.bak
```

回滚命令：
```bash
ink.py migrate rollback --phase 1
```

## 五、实施建议

1. **Phase 1 可立即实施**：`project_progress` 和 `strand_tracker_entries` 表简单，影响面小
2. **Phase 2 需要验证 foreshadowing 表结构**：确认 index_manager 是否已有对应表
3. **Phase 3 是长期目标**：需所有 CLI 命令切换到 index.db 读取后才能执行
4. **每个 Phase 之间至少间隔 1 个版本发布**：确保用户有时间适配
