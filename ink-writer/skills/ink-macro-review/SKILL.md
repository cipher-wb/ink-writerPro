---
name: ink-macro-review
description: Multi-tier macro review for long-form novels. Tier2 runs every 50 chapters (subplot health, character arcs, conflict dedup, commitment audit). Tier3 runs every 200 chapters (cross-volume analysis). Activates when user asks for macro review or /ink-macro-review.
allowed-tools: Read Grep Bash AskUserQuestion Agent
---

# Macro Review Skill（宏观审查）

## 用途

弥补 per-chapter 审查的盲区：检测跨50章以上的结构性问题，包括子情节健康度、角色弧线、冲突模式重复、叙事承诺管理、主题一致性。

## Project Root Guard

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

## 审查层级

用法：`/ink-macro-review [Tier2|Tier3]`，默认 Tier2。

---

### Tier 2（每50章/每卷边界）

**触发时机**：`current_chapter % 50 == 0` 或用户手动调用

**审查范围**：最近50章（或当前卷全部章节）

#### 2.1 子情节健康扫描

```bash
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT thread_id, title, content, planted_chapter, target_payoff_chapter, status,
         CASE
           WHEN target_payoff_chapter IS NOT NULL THEN (SELECT MAX(chapter) FROM chapters) - target_payoff_chapter
           ELSE NULL
         END as overdue_chapters
  FROM plot_thread_registry
  WHERE status = 'active'
  ORDER BY overdue_chapters DESC NULLS LAST;
"
```

分析：
- 列出所有活跃伏笔线程，按逾期程度排序
- 标记休眠30+章的线程为**高风险**
- 输出：哪些线程需要立即处理，哪些可以继续推迟

#### 2.2 角色弧线报告

```bash
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT entity_id, COUNT(*) as evolution_entries,
         MIN(chapter) as first_evolution, MAX(chapter) as last_evolution
  FROM character_evolution_ledger
  GROUP BY entity_id
  ORDER BY evolution_entries DESC;
"
```

结合 `entities` 表的 tier 信息：
- **核心角色**无演变记录 → 警告"角色停滞"
- **重要角色**50章无新记录 → 警告"角色发展停滞"
- 输出每个核心角色的弧线概述

#### 2.3 冲突模式去重报告

```bash
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT conflict_type, resolution_mechanism, COUNT(*) as count,
         GROUP_CONCAT(chapter) as chapters
  FROM plot_structure_fingerprints
  WHERE chapter >= (SELECT MAX(chapter) FROM chapters) - 50
  GROUP BY conflict_type, resolution_mechanism
  HAVING COUNT(*) >= 3
  ORDER BY count DESC;
"
```

分析：
- 列出重复3次以上的冲突模式
- 建议替代方案（不同conflict_type或resolution_mechanism）

#### 2.4 叙事承诺清单

```bash
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT id, chapter, commitment_type, entity_id, content, scope
  FROM narrative_commitments
  WHERE resolved_chapter IS NULL
  ORDER BY chapter ASC;
"
```

输出：所有活跃承诺列表，标注哪些可能被遗忘

#### 2.5 主题呈现分析（若有themes）

读取 `state.json` 的 `project_info.themes`，若非空：

```bash
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT chapter, theme_presence
  FROM chapter_memory_cards
  WHERE chapter >= (SELECT MAX(chapter) FROM chapters) - 50
    AND theme_presence IS NOT NULL AND theme_presence != '[]'
  ORDER BY chapter ASC;
"
```

统计每个主题的呈现频率和缺席段。

#### 2.6 健康报告综合（ink.py status）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" status --focus all --output "${PROJECT_ROOT}/.ink/tmp/health_snapshot.md"
```

整合 status_reporter 的角色掉线、伏笔逾期、节奏分析数据。

#### Tier 2 输出

```
审查报告/宏观审查-ch{start}-{end}.md
```

---

### Tier 3（每200章/小说里程碑）

**触发时机**：`current_chapter % 200 == 0` 或用户手动调用

**审查范围**：全书

在 Tier 2 全部内容基础上，增加：

#### 3.1 跨卷叙事弧分析

```bash
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "
  SELECT volume_id, title, start_chapter, end_chapter, arc_summary, resolution_status
  FROM volume_metadata
  ORDER BY volume_id ASC;
"
```

分析：
- 各卷弧线是否完整
- 卷间过渡是否有断裂感
- 全书节奏是否有"中段疲劳"

#### 3.2 全局伏笔健康度

统计全书伏笔：已解决数、活跃数、逾期数、平均解决跨度（章数）。
标记历史最长未解决线程。

#### 3.3 悬挂线程清理建议

对逾期50章以上的伏笔，建议：
- 在后续章节显式解决
- 或通过角色对话/内心独白自然过渡
- 或在下一卷总纲中安排解决

#### 3.4 全书冲突模式分析

统计全书所有 `conflict_type` + `resolution_mechanism` 组合的分布，生成占比表。
如果某组合占比超过30% → 警告

#### Tier 3 输出

```
审查报告/里程碑审查-ch{milestone}.md
```

---

## 禁止事项

- 宏观审查**不修改**任何章节文件（纯只读分析）
- 不替代 per-chapter 的 ink-review（两者互补）
- 不自动运行（仅在 ink-5 完成后提醒用户手动触发）

## 与 ink-5 的集成

ink-5 Phase 3 完成后，若当前章节触发里程碑：
- `% 50 == 0` → 提醒运行 `/ink-macro-review Tier2`
- `% 200 == 0` → 提醒运行 `/ink-macro-review Tier3`
