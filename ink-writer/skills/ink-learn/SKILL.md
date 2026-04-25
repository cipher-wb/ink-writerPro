---
name: ink-learn
description: 从当前会话和审查数据中提取成功模式，分析写作趋势，生成复用建议，写入 project_memory.json
allowed-tools: Read Write Bash Grep
---

# /ink-learn

## Project Root Guard（必须先确认）

环境设置（bash 命令执行前）：
```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
```


## 目标
- 从审查数据和章节正文中**自动提取**成功模式和失败模式
- 分析写作趋势，发现规律性问题和亮点
- 生成可被后续章节 context-agent 消费的复用建议
- 追加到 `.ink/project_memory.json`

## 运行模式

### 模式 A：手动记录（用户输入）
```bash
/ink-learn "本章的危机钩设计很有效，悬念拉满"
```

### 模式 B：自动分析（基于审查数据）
```bash
/ink-learn --auto
```

### 模式 C：趋势报告（统计分析）
```bash
/ink-learn --report
```

## 数据模型

```json
{
  "version": 2,
  "patterns": [
    {
      "id": "p_001",
      "pattern_type": "hook|pacing|dialogue|payoff|emotion|combat|opening|transition",
      "description": "危机钩设计：用倒计时制造紧迫感",
      "source_chapters": [100, 105],
      "quality": "success|failure|neutral",
      "review_score_context": 88,
      "tags": ["危机钩", "倒计时", "高评分"],
      "reuse_count": 0,
      "learned_at": "2026-02-02T12:00:00Z",
      "auto_extracted": false
    }
  ],
  "trend_snapshots": [
    {
      "snapshot_at": "2026-02-02T12:00:00Z",
      "chapter_range": "80-100",
      "avg_score": 86.5,
      "top_patterns": ["危机钩", "迪化误解"],
      "weak_dimensions": ["节奏控制"],
      "recommendations": ["减少连续Quest章节", "增加Fire线互动"]
    }
  ],
  "style_fingerprint": {
    "avg_sentence_length": 18,
    "short_sentence_ratio": 0.35,
    "dialogue_ratio": 0.28,
    "paragraph_avg_length": 65,
    "updated_at": "2026-02-02T12:00:00Z"
  }
}
```

## 执行流程

### 模式 A：手动记录

1. 读取 `"$PROJECT_ROOT/.ink/state.json"`，获取当前章节号
2. 读取 `"$PROJECT_ROOT/.ink/project_memory.json"`，若不存在则初始化
3. 解析用户输入，归类 pattern_type
4. 读取当前章节的 `review_metrics`（若有），附加 `review_score_context`
5. 去重检查（相似 description 且同 pattern_type → 合并 source_chapters）
6. 追加记录并写回文件

### 模式 B：自动分析

1. 读取最近 5 章的审查数据：
   ```bash
   python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index get-recent-review-metrics --limit 5
   ```
2. 对每章审查数据，提取：
   - **高分维度**（dimension_score ≥ 85）→ 标记为 `success` 模式
   - **低分维度**（dimension_score ≤ 65）→ 标记为 `failure` 模式
   - **被修复的 critical 问题**（issues 中有 fix 记录）→ 标记为 `failure` 模式并记录根因
3. 对高分章节（overall_score ≥ 85），读取正文并提取：
   - 开头类型（动作开场/对话开场/悬念开场/场景开场）
   - 钩子类型和强度
   - 对话密度和风格特征
4. 写入 `project_memory.json`，自动标记 `auto_extracted: true`

### 模式 C：趋势报告

1. 读取 `project_memory.json` 全部记录
2. 读取最近 20 章审查数据：
   ```bash
   python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index get-recent-review-metrics --limit 20
   ```
3. 生成趋势分析：
   - **分数趋势**：最近 20 章的 overall_score 走势（上升/稳定/下降）
   - **维度强弱**：6 维度中哪些持续高分、哪些持续低分
   - **模式热度**：哪些成功模式被频繁复用、哪些失败模式反复出现
   - **风格指纹**：对最近 5 章正文做统计（句长/短句占比/对话比例/段落长度），与历史对比
4. 生成复用建议：
   - 下一章推荐使用的模式（基于成功模式 + 避免重复）
   - 需要关注的弱项维度
   - 文风漂移警告（若风格指纹与历史差异 > 20%）
5. 将趋势快照写入 `project_memory.json → trend_snapshots`
6. 输出报告：

```markdown
# 写作趋势分析报告

## 分数趋势（最近 20 章）
{平均分} / {最高分} / {最低分} / {走势}

## 维度强弱分析
| 维度 | 平均分 | 趋势 | 建议 |
|------|--------|------|------|

## 成功模式 TOP 5
| 模式 | 出现次数 | 平均关联分 | 示例章节 |
|------|---------|-----------|---------|

## 反复出现的问题 TOP 3
| 问题 | 出现次数 | 根因 | 修复建议 |
|------|---------|------|---------|

## 文风指纹对比
| 指标 | 当前（最近5章） | 历史平均 | 偏差 |
|------|---------------|---------|------|

## 下一章建议
- 推荐模式：{list}
- 关注维度：{list}
- 风格提醒：{list}
```

## 约束
- 不删除旧记录，仅追加
- 避免完全重复的 description（相似度 > 80% 且同 pattern_type → 合并 source_chapters）
- 趋势快照最多保留 10 条，超出时删除最早的
- 风格指纹每次只保留最新值（覆盖更新）
- 自动提取的模式标记 `auto_extracted: true`，与手动记录区分

## M5 自动 case 提案（M5 P3）

短期 project_memory 之外，M5 引入"自动从 blocked 章节抽出失败模式 → 提议 pending case"通道。每周限 5 条，由编辑/产品 `ink case approve` 升格为长期 case。

### --auto-case-from-failure

```bash
python3 -c "from ink_writer.learn.auto_case import propose_cases_from_failures; \
from ink_writer.case_library.store import CaseStore; from pathlib import Path; \
proposed = propose_cases_from_failures( \
    case_store=CaseStore(Path('data/case_library')), \
    base_dir=Path('data'), \
    cases_dir=Path('data/case_library/cases'), \
    throttle_path=Path('config/ink_learn_throttle.yaml')); \
print(f'proposed: {[c.case_id for c in proposed]}')"
```

<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价）：

```powershell
python3 -c @"
from ink_writer.learn.auto_case import propose_cases_from_failures
from ink_writer.case_library.store import CaseStore
from pathlib import Path
proposed = propose_cases_from_failures(
    case_store=CaseStore(Path('data/case_library')),
    base_dir=Path('data'),
    cases_dir=Path('data/case_library/cases'),
    throttle_path=Path('config/ink_learn_throttle.yaml'))
print(f'proposed: {[c.case_id for c in proposed]}')
"@
```

读法：
- 扫最近 7 天 (`pattern_window_days`) blocked 章节 evidence_chain，统计 `cases_violated` 组合频次。
- 频次 ≥ `min_pattern_occurrences` (默认 2) 的组合 → 写 `data/case_library/cases/CASE-LEARN-NNNN.yaml`（status=pending、severity=P2、tags 含 `m5_auto_learn`）。
- 每周硬上限 `max_per_week` (默认 5)；阈值改 `config/ink_learn_throttle.yaml`。
- 编辑 `ink case approve CASE-LEARN-NNNN` 后才进入长期 case 闭环。

### --promote

短期 `project_memory.json`（ink-learn 模式 A/B/C 的 `patterns` 数组）→ 长期 case 桥。重复 ≥ 3 次的 success/failure 模式回灌为 `CASE-PROMOTE-NNNN.yaml`（pending）。

```bash
python3 -c "from ink_writer.learn.promote import promote_short_term_to_long_term; \
from ink_writer.case_library.store import CaseStore; from pathlib import Path; \
proposed = promote_short_term_to_long_term( \
    project_memory_path=Path('.ink/<book>/project_memory.json'), \
    case_store=CaseStore(Path('data/case_library')), \
    cases_dir=Path('data/case_library/cases'), \
    min_occurrences=3); \
print(f'promoted: {[c.case_id for c in proposed]}')"
```

<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价）：

```powershell
python3 -c @"
from ink_writer.learn.promote import promote_short_term_to_long_term
from ink_writer.case_library.store import CaseStore
from pathlib import Path
proposed = promote_short_term_to_long_term(
    project_memory_path=Path('.ink/<book>/project_memory.json'),
    case_store=CaseStore(Path('data/case_library')),
    cases_dir=Path('data/case_library/cases'),
    min_occurrences=3)
print(f'promoted: {[c.case_id for c in proposed]}')
"@
```

读法：
- 读 `.ink/<book>/project_memory.json` 的 `patterns: [{text, kind, count}, ...]`。
- `count >= min_occurrences` (默认 3) 的模式 → 写 `data/case_library/cases/CASE-PROMOTE-NNNN.yaml`。
- `kind=failure` → severity=P2；`kind=success`（或其它）→ severity=P3。
- tags 含 `m5_promote` + `kind`；`source.ingested_from='ink_learn_promote'`。
- 缺 project_memory.json 时返回空 list 不抛错。
- 编辑 `ink case approve CASE-PROMOTE-NNNN` 后才进入长期 case 闭环。
