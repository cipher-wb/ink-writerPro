---
name: ink-audit
description: Data consistency audit for ink-writer projects. Validates state.json vs index.db, detects ghost entities, orphan foreshadowing, protagonist state drift, and timeline contradictions. Supports Quick/Standard/Deep modes. Activates when user asks for data audit or /ink-audit.
allowed-tools: Read Grep Bash AskUserQuestion
---

# Data Audit Skill（数据对账）

## 用途

长篇连续创作中，AI 提取的数据（实体、状态、伏笔等）会产生累积误差。本工具定期扫描并报告数据不一致问题，防止错误复利增长。

## Project Root Guard（必须先确认）

```bash
export WORKSPACE_ROOT="${INK_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  if [ -d "$PWD/scripts" ] && [ -d "$PWD/skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$PWD"
  elif [ -d "$PWD/../scripts" ] && [ -d "$PWD/../skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$(cd "$PWD/.." && pwd)"
  fi
fi

export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"
export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## 审计深度（3级）

用户可指定深度：`/ink-audit [quick|standard|deep]`，默认 `quick`。

### Quick（~2分钟）

快速健康检查，不读章节原文：

1. **state.json ↔ index.db 主角状态比对**：
   ```bash
   # 读取 state.json 中的 protagonist_state
   python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" state export-context 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('progress',{}), ensure_ascii=False))"
   ```
   ```bash
   # 读取 index.db 中的主角实体
   python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index get-protagonist 2>/dev/null
   ```
   比对两者的 realm/location 是否一致。

2. **chapter_meta 条数 vs current_chapter**：
   ```bash
   python3 -c "
   import json
   from pathlib import Path
   state = json.loads(Path('${PROJECT_ROOT}/.ink/state.json').read_text())
   meta_count = len(state.get('chapter_meta', {}))
   current = state.get('progress', {}).get('current_chapter', 0)
   print(f'chapter_meta条数: {meta_count}, current_chapter: {current}')
   if meta_count > 20:
       print(f'⚠️ chapter_meta未flush: {meta_count}条（阈值20）')
   "
   ```

3. **伏笔逾期计数**：
   ```bash
   sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
     SELECT COUNT(*) as overdue_count
     FROM plot_thread_registry
     WHERE status = 'active'
       AND target_payoff_chapter IS NOT NULL
       AND target_payoff_chapter < (SELECT COALESCE(MAX(chapter), 0) FROM chapters) - 10;
   "
   ```

4. **disambiguation_pending 积压**：
   ```bash
   python3 -c "
   import json
   from pathlib import Path
   state = json.loads(Path('${PROJECT_ROOT}/.ink/state.json').read_text())
   pending = state.get('disambiguation_pending', [])
   print(f'disambiguation_pending积压: {len(pending)}条')
   if len(pending) > 50:
       print(f'⚠️ 建议运行 /ink-resolve 处理积压消歧项')
   "
   ```

5. **输出 Quick 报告**

### Standard（~10分钟）

Quick 全部 + 重读最近20章原文校验：

6. **实体出场校验**：
   - 读取最近20章的正文文件
   - 对每章中提到的角色名，查询 index.db appearances 表
   - 报告：原文中出现但 DB 无记录的实体（漏提取）、DB 中记录但原文未提及的实体（幽灵记录）

7. **时间线算术一致性**：
   ```bash
   sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
     SELECT chapter, anchor_time, relative_to_previous, countdown
     FROM timeline_anchors
     ORDER BY chapter DESC
     LIMIT 20;
   "
   ```
   检查倒计时是否逐章递减、时间是否有不合理倒退。

8. **strand_tracker 一致性**：
   - 比对 state.json.strand_tracker 与 index.db 中最近20章的实际 strand 分类

### Deep（~30分钟）

Standard 全部 + 全量校验：

9. **全量实体校验**：扫描所有章节原文，交叉比对全部实体
10. **state_changes 链条逻辑**：检查同一实体的 state_changes 是否有逻辑矛盾（如 realm 从高级回退到低级，但非闪回章节）
11. **伏笔孤儿检测**：检查 plot_thread_registry 中标记 active 但在最近50章原文中已有明确解决描写的线程
12. **关系图一致性**：检查 relationships 表与 relationship_events 表的最终状态是否一致

## 输出格式

```markdown
# 数据对账报告

**审计时间**: {timestamp}
**审计深度**: {quick|standard|deep}
**项目**: {title}
**当前章节**: {current_chapter}

## 📊 概览

| 维度 | 状态 | 详情 |
|------|------|------|
| 主角状态同步 | ✅/⚠️ | state.json ↔ index.db 一致/不一致 |
| chapter_meta膨胀 | ✅/⚠️ | {count}条（阈值20） |
| 伏笔逾期 | ✅/⚠️ | {overdue_count}条逾期 |
| 消歧积压 | ✅/⚠️ | {pending_count}条待处理 |
| 实体幽灵 | ✅/⚠️ | {ghost_count}个幽灵实体（仅Standard+） |
| 时间线一致 | ✅/⚠️ | {timeline_issues}个时间矛盾（仅Standard+） |

## ⚠️ 问题详情

（按严重程度排列每个问题的详细描述和修复建议）

## 💡 建议操作

- 运行 `/ink-resolve` 处理消歧积压
- 通过 `/ink-plan` 延期逾期伏笔
- 手动修正主角状态：`ink.py state ...`
```

保存到：`${PROJECT_ROOT}/.ink/audit_reports/audit_{timestamp}.md`

## 自动提醒机制

本 skill 不自动执行。但在 `/ink-5` 完成后，若 `current_chapter % 50 == 0`，ink-5 会输出提醒：
```
📋 已达到50章检查点，建议运行 /ink-audit standard 进行数据对账
```
