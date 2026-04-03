---
name: ink-resolve
description: Resolve accumulated disambiguation entries and candidate facts. Presents uncertain entities to user for confirmation/rejection. Activates when user asks to resolve ambiguities or /ink-resolve.
allowed-tools: Read Grep Bash AskUserQuestion
---

# Disambiguation Resolution Skill（消歧处理）

## 用途

长篇创作中，Data Agent 对低置信度实体（<0.5）会写入 `disambiguation_pending`，但这些条目永远不会被自动解决。本工具将积压的消歧项呈现给用户，让用户决定合并、拆分或忽略。

## Project Root Guard

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```

## 执行流程

### Step 1: 收集待处理项

```bash
# 读取 disambiguation_pending
python3 -c "
import json
from pathlib import Path
state = json.loads(Path('${PROJECT_ROOT}/.ink/state.json').read_text())
pending = state.get('disambiguation_pending', [])
print(f'待消歧项: {len(pending)}条')
for i, item in enumerate(pending[:20]):
    print(f'  [{i+1}] ch{item.get(\"chapter\",\"?\")} | {item.get(\"mention\",\"?\")} | 建议ID: {item.get(\"suggested_id\",\"?\")} | 置信度: {item.get(\"confidence\",\"?\")}')
"
```

```bash
# 读取 candidate_facts
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT id, chapter, fact, entity_id, confidence, status
  FROM candidate_facts
  WHERE status = 'pending'
  ORDER BY chapter ASC
  LIMIT 20;
"
```

### Step 2: 逐项处理

对每个待消歧项，使用 AskUserQuestion 询问用户：

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

- **A (合并)**: `ink.py index register-alias --alias "{mention}" --entity "{suggested_id}" --type "角色"`
- **B (新建)**: 提示用户输入新实体信息，创建新实体
- **C (跳过)**: 保留在 pending 中
- **D (删除)**: 从 pending 列表中移除

### Step 4: 清理

处理完成后，更新 `state.json` 移除已处理的 disambiguation_pending 条目。

## 自动提醒

在 ink-auto 完成后，若 `current_chapter % 100 == 0` 且 `disambiguation_pending` 积压超过20条，输出：
```
📋 消歧积压提醒：{count}条待处理消歧项，建议运行 /ink-resolve
```
