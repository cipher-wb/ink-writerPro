---
name: ink-resolve
description: Resolve accumulated disambiguation entries and candidate facts. Presents uncertain entities to user for confirmation/rejection. Activates when user asks to resolve ambiguities or /ink-resolve.
allowed-tools: Read Grep Bash AskUserQuestion
---

# Disambiguation Resolution Skill（消歧处理）

## 用途

长篇创作中，Data Agent 对低置信度实体（<0.5）会写入 `disambiguation_log` 表（v13 US-011 前为 state.json.disambiguation_pending；现已迁移到 SQL 单源）。本工具将积压的消歧项呈现给用户，让用户决定合并、拆分或忽略。

## v13 US-011 数据源更新

**SQLite 是单一事实源**：所有消歧读写都通过 `ink-writer/scripts/data_modules/sql_state_manager.py` 的 API，不再直写 `state.json`。`state.json.disambiguation_pending` 仅为视图（`rebuild_state_dict()` 从 SQL 重生），本 skill 读写**必须**走 SQL。

## Project Root Guard

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```

## 执行流程

### Step 1: 收集待处理项（SQL 单源）

```bash
# v13 US-011：从 disambiguation_log 表读（替代 state.json 直读）
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT id, chapter, payload, created_at
  FROM disambiguation_log
  WHERE category = 'pending' AND status = 'active'
  ORDER BY chapter ASC, id ASC
  LIMIT 20;
"
```

```bash
# 候选事实（另一个数据源，不变）
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT id, chapter, fact, entity_id, confidence, status
  FROM candidate_facts
  WHERE status = 'pending'
  ORDER BY chapter ASC
  LIMIT 20;
"
```

### Step 2: 逐项处理

对每个待消歧项，使用 AskUserQuestion 询问用户（`payload` JSON 中含 mention/suggested_id/confidence 字段）：

```
🔍 消歧项 [{N}/{total}]:

章节: 第{chapter}章
提及: "{mention}"
建议实体ID: {suggested_id}
置信度: {confidence}

选项:
A) 确认合并到 {suggested_id}
B) 创建新实体（这是不同的角色/物品）
C) 跳过（暂不处理）
D) 删除（误提取，忽略）
```

### Step 3: 执行操作

- **A (合并)**: `ink.py index register-alias --alias "{mention}" --entity "{suggested_id}" --type "角色"`，然后调用 Step 4 的 SQL 路径标记 resolved
- **B (新建)**: 提示用户输入新实体信息，创建新实体；同样走 Step 4 标记 resolved
- **C (跳过)**: 不做任何操作（entry 保持 status='active'）
- **D (删除)**: 同样走 Step 4 标记 resolved（或改为 status='rejected' 如需区分）

### Step 4: 标记处理完成（SQL 单接口）

**v13 US-011 替代原"更新 state.json 移除已处理的 disambiguation_pending 条目"**。
使用 `sql_state_manager.resolve_disambiguation_entry(entry_id)`：

```bash
python3 -c "
import sys
from pathlib import Path
# [FIX-11] sys.path.insert no longer required — ink_writer is importable
sys.path.insert(0, str(Path('${CLAUDE_PLUGIN_ROOT}/..')))
from ink_writer.core.index.index_manager import IndexManager
from ink_writer.core.state.sql_state_manager import SQLStateManager

idx = IndexManager(db_path=Path('${PROJECT_ROOT}/.ink/index.db'))
sql = SQLStateManager(idx)

# 对每个 entry_id 调用 resolve_disambiguation_entry
entry_ids = ${ENTRY_IDS_JSON}  # 由 Step 2/3 收集的 id 列表
for eid in entry_ids:
    ok = sql.resolve_disambiguation_entry(eid)
    print(f'Resolved entry {eid}: {ok}')

# 触发视图重建（state.json 从 SQL 重生）
idx.rebuild_state_dict()
"
```

**禁止**：直接读写 `state.json` 的 `disambiguation_pending` 字段。所有状态变更必须通过 `SQLStateManager`；`state.json` 仅作为重建视图用。

## 自动提醒

在 ink-auto 完成后，若 `current_chapter % 100 == 0` 且 SQL 里 `disambiguation_log` 的 `active` 条目超过20条，输出：
```
📋 消歧积压提醒：{count}条待处理消歧项，建议运行 /ink-resolve
```

## 迁移说明

此文件于 v13 US-011 重写。原直读 `state.json.disambiguation_pending` 的 Python 代码片段已移除（风险：多进程并发时被 `rebuild_state_json()` 覆盖）。若在用户项目里见到 state.json 中的 `disambiguation_pending` 字段，那是 SQL 视图重生的结果，**不要**直写。
