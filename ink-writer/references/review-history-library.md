# 审查历史库（Review History Library）

> **目标**：从审查历史中提取高分章节的成功模式，建立项目专属的质量基线，供后续章节的 Context Agent 和 Checker 参考。
>
> **原则**：数据驱动——基于真实审查分数而非主观判断筛选样本。

## 一、数据采集

### 自动采集（每章 Step 5 完成后触发）

Data Agent 在完成常规数据回写后，检查本章审查分数：

```python
if review_score >= 85:
    # 提取本章的成功模式特征，写入 review_library
    extract_success_patterns(chapter, review_metrics)
```

### 采集内容

对每个高分章节（overall_score ≥ 85），提取以下特征：

```json
{
  "chapter": 100,
  "overall_score": 92,
  "dimension_scores": {"设定一致性": 95, "追读力": 90, ...},
  "success_features": {
    "opening_type": "动作开场",
    "opening_hook_words": 150,
    "hook_type": "危机钩",
    "hook_strength": "strong",
    "coolpoint_types": ["越级反杀", "打脸权威"],
    "coolpoint_count": 2,
    "micropayoff_count": 3,
    "strand": "quest",
    "dialogue_ratio": 0.32,
    "avg_sentence_length": 18,
    "short_sentence_ratio": 0.38,
    "anti_ai_score": 22,
    "word_count": 2350
  },
  "genre": "xianxia",
  "chapter_type": "关键战斗章",
  "extracted_at": "2026-03-26T10:00:00Z"
}
```

### 存储位置

```
.ink/review_library.jsonl     # 每行一个高分章节记录（追加写入）
```

使用 JSONL 格式（每行一个 JSON 对象），支持增量追加、不需全量读取。

## 二、基线计算

### 项目质量基线（每 10 章自动更新）

从 review_library 中统计项目专属基线：

```json
{
  "baseline_version": 3,
  "sample_count": 25,
  "chapter_range": "1-80",
  "computed_at": "2026-03-26T10:00:00Z",
  "quality_baseline": {
    "avg_overall_score": 87.3,
    "avg_dimension_scores": {
      "设定一致性": 89.1,
      "连贯性": 86.5,
      "人物塑造": 88.0,
      "追读力": 85.2,
      "爽点密度": 84.7,
      "节奏控制": 82.3
    },
    "style_baseline": {
      "avg_dialogue_ratio": 0.30,
      "avg_sentence_length": 19,
      "avg_short_sentence_ratio": 0.35,
      "avg_word_count": 2280,
      "avg_anti_ai_score": 25
    },
    "pattern_baseline": {
      "top_opening_types": ["动作开场", "对话开场", "悬念开场"],
      "top_hook_types": ["危机钩", "悬念钩", "渴望钩"],
      "top_coolpoint_types": ["越级反杀", "装逼打脸", "反派翻车"],
      "avg_micropayoff_per_chapter": 2.3
    }
  }
}
```

存储位置：`.ink/quality_baseline.json`

### 基线更新触发

- 每新增 10 个高分样本（review_library 行数 % 10 == 0）
- 用户手动执行 `/ink-learn --report`
- 新卷开始时（卷级基线重置建议）

## 三、消费方式

### Context Agent 消费

Step 1 构建创作执行包时，读取基线并生成指导：

```markdown
## 风格基线参考（来自项目审查历史库）

本项目高分章节特征：
- 开场类型偏好：{top_opening_types}
- 对话占比：{avg_dialogue_ratio}（本章建议：{建议值}）
- 句长控制：均长 {avg_sentence_length} 字，短句占比 {avg_short_sentence_ratio}
- 钩子类型偏好：{top_hook_types}
- 微兑现频率：{avg_micropayoff_per_chapter} 次/章
```

### Checker 消费

审查器使用基线作为评分参考：
- **pacing-checker**：用 `avg_word_count` 判断本章是否偏长/偏短
- **high-point-checker**：用 `top_coolpoint_types` 判断爽点类型是否单调
- **reader-pull-checker**：用 `avg_micropayoff_per_chapter` 作为微兑现达标基线
- **proofreading-checker**：用 `style_baseline` 作为文风一致性基线

### ink-learn 消费

`/ink-learn --report` 的趋势分析中，将当前章节与基线对比：
- 高于基线的维度 → 标记为当前强项
- 低于基线的维度 → 标记为需要关注
- 风格偏离基线 > 20% → 输出文风漂移警告

## 四、CLI 命令

```bash
# 查看审查历史库统计
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index review-library stats

# 查看当前质量基线
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index review-library baseline

# 手动触发基线更新
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index review-library update-baseline

# 导出高分章节列表
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index review-library list --min-score 85
```

## 五、数据安全

- `review_library.jsonl` 和 `quality_baseline.json` 纳入 Git 管理（不含敏感信息）
- 基线更新不删除历史数据，只追加新版本
- 回滚：删除 `quality_baseline.json` 后重新计算即可
- 清理：`review_library.jsonl` 超过 500 行时，自动归档旧数据到 `review_library.archive.jsonl`
