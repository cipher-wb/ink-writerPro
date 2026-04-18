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
