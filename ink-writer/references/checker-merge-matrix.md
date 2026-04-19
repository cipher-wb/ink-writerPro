# Checker Merge Matrix (US-016 / F-011)

> 文笔维度 checker 之间存在高度重叠：同一"镜头单调 / 感官沙漠 / 句式平坦 / voice 漂移 / 对话失辨"问题，可能被 3-5 个 checker 同时命中。
>
> polish-agent 若直接消费 N 份 checker report，会收到重复甚至冲突的修复指令，token 膨胀且修复方向打架。本 matrix 规定**按写作维度去重**：每个维度有一位**主 checker**，其他命中同维度的 checker 视为**从 checker**，其 `fix_suggestion` / `violations` 归并到主 checker 的 fix_prompt 下，polish-agent 最终只消费合并后的 `merged_fix_suggestion.json`。

## Matrix

| 维度 (dimension)    | 主 checker (master)       | 从 checker (slaves)                                                | 合并策略 |
| ------------------- | ------------------------- | ------------------------------------------------------------------ | -------- |
| 镜头 (shot)         | prose-impact-checker      | proofreading-checker (SHOT_MONOTONY), editor-wisdom-checker        | 主 fix_prompt + 从 violations 合并去重 |
| 感官 (sensory)      | sensory-immersion-checker | prose-impact-checker (SENSORY_RICHNESS), editor-wisdom-checker     | 主 fix_prompt + 从 violations 合并去重 |
| 句式节奏 (rhythm)   | flow-naturalness-checker  | prose-impact-checker (SENTENCE_RHYTHM), proofreading-checker (6B.2)| 主 fix_prompt + 从 violations 合并去重 |
| voice               | ooc-checker               | voice-fingerprint / anti-detection-checker (voice drift 部分)      | 主 fix_prompt + 从 violations 合并去重 |
| 对话 (dialogue)     | flow-naturalness-checker  | ooc-checker (对话 voice 部分), prose-impact-checker (对话插入)     | 主 fix_prompt + 从 violations 合并去重 |

> 其他写作维度（逻辑 / 连续性 / 大纲 / 钩子 / 情绪）由独立 checker 主导，不在本 matrix 去重范围；它们的 fix_prompt 继续走 polish-agent 原有的 `*_fix_prompt` 字段，单独传递。

## Checker → Dimension 反查表

用于快速判断某 checker 的输出应归入哪些维度（一个 checker 可能覆盖多个维度）。

| Checker                     | 参与维度                     | 角色                         |
| --------------------------- | ---------------------------- | ---------------------------- |
| prose-impact-checker        | 镜头 / 感官 / 句式节奏 / 对话| 镜头主；感官/句式/对话从     |
| sensory-immersion-checker   | 感官                         | 感官主                       |
| flow-naturalness-checker    | 句式节奏 / 对话              | 句式节奏主 / 对话主          |
| ooc-checker                 | voice / 对话                 | voice 主 / 对话从            |
| proofreading-checker        | 镜头 / 句式节奏              | 全部为从（SHOT / SENTENCE）  |
| editor-wisdom-checker       | 镜头 / 感官                  | 全部为从                     |
| anti-detection-checker      | voice                        | 从（voice drift 维度）       |

## 合并算法

见 `ink_writer/checker_pipeline/merge_fix_suggestion.py`：

1. 对每份 checker report，按 matrix 把其 `violations` / `issues` / `fix_suggestion` 归入对应维度的"主 checker bucket"。
2. 若同一维度出现多个 violation 且 `type` 相同 → 仅保留 severity 最高的一条（critical > high > medium > low）。
3. 若主 checker 缺失（只有从 checker 命中）→ 降级为"主 fix_prompt = 从 checker 的 fix_suggestion 拼接"。
4. 输出 `merged_fix_suggestion.json`：

```json
{
  "shot": {
    "master_checker": "prose-impact-checker",
    "violations": [{"type": "SHOT_MONOTONY", "severity": "high", "source_checkers": ["prose-impact-checker", "proofreading-checker"], "suggestion": "..."}],
    "fix_prompt": "【镜头】..."
  },
  "sensory": { "master_checker": "sensory-immersion-checker", "violations": [...], "fix_prompt": "..." },
  "rhythm":  { "master_checker": "flow-naturalness-checker",  "violations": [...], "fix_prompt": "..." },
  "voice":   { "master_checker": "ooc-checker",               "violations": [...], "fix_prompt": "..." },
  "dialogue":{ "master_checker": "flow-naturalness-checker",  "violations": [...], "fix_prompt": "..." }
}
```

polish-agent 按此结构在 Layer 9 一次性消费，避免重复修复同一段落。

## Generic Arbitration（章 ≥4，US-011 / AUDIT-V17-R008）

> US-016 的维度归并（上方 matrix）解决的是**同一章节内多 checker 维度重叠**；US-011 补的 `arbitrate_generic` 解决**同一 symptom 被 3 个重叠 checker 重复报 issue** 的二次放大问题。两者正交互补：
>
> - 先走 US-016 dimension-merge（产出 5 维 `merged_fix_suggestion.json`）。
> - 再走 US-011 `arbitrate_generic`（产出 `arbitration.json`，按 `symptom_key` 去重 fix_prompt）。
> - polish-agent 最终同时消费两份产物，按优先级 P0 → P3 改写。

### 重叠 checker 合并规则（章 ≥4）

| 重叠 checker triad                                                        | symptom_key 归一化来源 | 合并策略 |
| ------------------------------------------------------------------------- | ---------------------- | -------- |
| prose-impact-checker + sensory-immersion-checker + flow-naturalness-checker | `type` 字段归一化（lower + 非 alnum→`_`）；缺失时回退 `symptom_key` / `category` | `arbitrate_generic` 按 `symptom_key` 分桶；桶内 P2 > P3 > P4；最高优先级 `fix_prompt` 保留，其余同方向并入 `context_addendum`，反向冲突进 `dropped` |

### 优先级映射（severity → priority）

| checker severity  | priority |
| ----------------- | -------- |
| critical / high   | P2       |
| medium / warning / low | P3   |
| info              | P4（不合并，仅上下文） |

> 黄金三章的 P0（golden-three-checker） / P1（highpoint-checker）保留给 `arbitrate`，`arbitrate_generic` 不与之抢位。

### 数据流与输出契约

1. `parallel.pipeline_manager._run_checkpoint` 调 `ink-review` 写入 `.ink/index.db.review_metrics.review_payload_json`。
2. checkpoint 末尾逐章调 `_arbitrate_chapter_issues(ch)`（章 ≥4 触发），内部：
   - `IndexManager.read_review_metrics(ch)` 拉行；
   - `collect_issues_from_review_metrics(row)` 抽 `checker_results[三重 checker].violations` → `list[Issue]`；
   - `arbitrate_generic(ch, issues)` 按 `symptom_key` 去重；
   - 输出写 `.ink/arbitration/ch{:04d}.json`。
3. polish-agent 在 Layer 9 读 `arbitration.json`（若存在）并按 `merged_fixes` 顺序应用。

### 契约与约束

- **Green G003 / NG-3**：`arbitrate_generic` **不合并或删减 16 个 checker spec**；仅合并它们在 `index.db.review_metrics` 中的运行时 issue 输出。
- **黄金三章原路径保留**：章 1-3 仍走 `arbitrate`（`mode="golden"`，issue_id 前缀 `ARB-`）；章 ≥4 走 `arbitrate_generic`（`mode="generic"`，issue_id 前缀 `ARBG-`）。两路径共享内部 `_bucketize_and_merge`，输出 schema 对齐。
- **零回归（pytest baseline 2847）**：`arbitrate_generic` 对 ch < 4 返回 `None`，不触发任何旧调用链变更。

### 参考实现

- `ink_writer/editor_wisdom/arbitration.py::arbitrate_generic`
- `ink_writer/editor_wisdom/arbitration.py::collect_issues_from_review_metrics`
- `ink_writer/parallel/pipeline_manager.py::_arbitrate_chapter_issues`
- 测试：`tests/harness/test_arbitrate_generic.py`（章 50 triple-checker 合并 → 单 fix_prompt）
