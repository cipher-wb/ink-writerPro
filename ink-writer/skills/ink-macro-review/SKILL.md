---
name: ink-macro-review
description: Multi-tier macro review for long-form novels. Tier2 runs every 50 chapters (subplot health, character arcs, conflict dedup, commitment audit). Tier3 runs every 200 chapters (cross-volume analysis). Activates when user asks for macro review or /ink-macro-review.
allowed-tools: Read Grep Bash AskUserQuestion Agent
---

# Macro Review Skill（宏观审查）

## 用途

弥补 per-chapter 审查的盲区：检测跨50章以上的结构性问题，包括子情节健康度、角色弧线、冲突模式重复、叙事承诺管理、主题一致性。

> **与每章金丝雀检查的关系**：ink-write Step 0.7 已在每章写作前执行轻量版的主角状态同步、角色停滞（40+章）、冲突重复（30章窗口）、时间线链条（10章窗口）、遗忘伏笔（30+章沉默）检查。本 skill 的 Tier2/Tier3 仍然不可替代，因为它提供：
> - 50/200 章窗口的**综合统计分析**（不仅是单条 top-5 检查）
> - **跨卷弧线**完整性评估（volume_metadata 级别）
> - **全量叙事承诺**清单（不限于 top 5 遗忘线程）
> - **主题呈现**频率与缺席段分析
> - **详细审查报告**（markdown 格式存档，供回溯参考）

## Project Root Guard

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
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

#### 2.7 风格漂移检测（v7.0.5 新增）

> 对比最近10章的风格指标与前10章的风格锚点，检测写作风格是否发生显著漂移。

```bash
python3 -X utf8 -c "
import sys, json
sys.path.insert(0, '${SCRIPTS_DIR}/data_modules')
try:
    from style_anchor import save_anchor, check_drift
    from pathlib import Path
    project_root = '${PROJECT_ROOT}'
    anchor_path = Path(project_root) / '.ink' / 'style_anchor.json'

    # 若锚点不存在且已有 ≥10 章，自动生成
    if not anchor_path.exists():
        result = save_anchor(project_root)
        print(f'📌 {result}')

    # 执行漂移检测
    report = check_drift(project_root)
    if report['status'] == 'skip':
        print(f'⏭️ 风格漂移检测跳过: {report[\"reason\"]}')
    elif report['drift_count'] == 0:
        print(f'✅ 风格漂移检测通过: 最近10章风格与锚点一致')
    else:
        print(f'⚠️ 检测到 {report[\"drift_count\"]} 项风格漂移:')
        for w in report['warnings']:
            print(f'  - {w[\"metric\"]}: 锚点={w[\"anchor_mean\"]}, 当前={w[\"current_mean\"]}, '
                  f'偏离={w[\"deviation_pct\"]}% ({w[\"severity\"]})')
except Exception as e:
    print(f'⚠️ 风格漂移检测跳过（模块不可用）: {e}')
"
```

**处理规则**：
- WARNING 级，不阻断审查
- 首次运行时若锚点不存在且已有 ≥10 章，自动生成锚点
- 偏离 > 2σ 标记 medium，> 3σ 标记 high
- 进行中项目需运行一次 Tier2 自动生成锚点（只读操作，不修改已有数据）

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

## 执行方式说明

Tier2/Tier3 **不调用 Checker Agent**，直接通过 SQL 查询 + 统计分析执行。与 per-chapter 的 ink-review（通过 Task 调用 Checker Agent）完全不同。宏观审查的分析维度（跨50/200章窗口）超出单章 Checker 的设计范围。

## 禁止事项

- 宏观审查本身**不修改**任何章节文件（纯只读分析）
- 不替代 per-chapter 的 ink-review（两者互补）
- **不调用 Checker Agent**（Tier2/Tier3 使用直接 SQL 分析，不走 Agent 路径）

> 注：宏观审查产出的报告会由 `ink-fix` skill 消费，`ink-fix` 负责根据报告内容执行正文修复和数据库修复。宏观审查自身保持只读。

## 与 ink-auto 的集成

ink-auto 在检查点自动触发宏观审查：
- `% 20 == 0` → 自动运行 Tier2 + ink-fix 修复
- `% 200 == 0` → 自动运行 Tier3 + ink-fix 修复

也可手动运行：
- `/ink-macro-review Tier2`
- `/ink-macro-review Tier3`
