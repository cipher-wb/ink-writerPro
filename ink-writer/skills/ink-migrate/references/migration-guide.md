# 迁移指南：v8.x → v9.0

## 迁移前须知

- 迁移是**可选的**。不迁移也能正常使用所有现有功能。
- 迁移后的新功能：Reader Verdict 评分趋势分析、ink-auto 增强输出、计算型闸门日志。
- 迁移过程不修改章节正文和大纲文件。

## 迁移内容

### state.json 变更

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 5/6 → 7 |
| `harness_config.computational_gate_enabled` | bool | Step 2C 计算型闸门开关 |
| `harness_config.reader_verdict_mode` | string | `core`=每章快速评分 |
| `harness_config.reader_verdict_thresholds` | object | pass/enhance/rewrite 阈值 |

### index.db 新表

#### harness_evaluations

存放 reader_verdict 7 维评分历史，用于趋势分析。

| 列名 | 类型 | 说明 |
|------|------|------|
| chapter | INTEGER | 章节号 |
| hook_strength | REAL | 开头抓取力 0-10 |
| curiosity_continuation | REAL | 好奇心维持 0-10 |
| emotional_reward | REAL | 情绪回报 0-10 |
| protagonist_pull | REAL | 主角吸引力 0-10 |
| cliffhanger_drive | REAL | 追更驱动 0-10 |
| filler_risk | REAL | 注水风险 0-10 |
| repetition_risk | REAL | 重复风险 0-10 |
| total | REAL | 总分 -20~50 |
| verdict | TEXT | pass/enhance/rewrite |
| review_depth | TEXT | core/full+ |

#### computational_gate_log

存放 Step 2C 计算型闸门检查日志。

| 列名 | 类型 | 说明 |
|------|------|------|
| chapter | INTEGER | 章节号 |
| pass | INTEGER | 1=通过, 0=失败 |
| checks_run | INTEGER | 检查项数 |
| checks_passed | INTEGER | 通过项数 |
| hard_failures | TEXT | JSON: 硬失败列表 |
| soft_warnings | TEXT | JSON: 软警告列表 |

## 不迁移的影响

| 功能 | 不迁移 | 迁移后 |
|------|--------|--------|
| 日常写作 (ink-auto/ink-write) | ✅ 正常 | ✅ 正常 |
| Step 2C 计算型闸门 | ✅ 正常运行 | ✅ + 日志入库 |
| Reader Verdict 评分 | ✅ 正常输出 | ✅ + 历史趋势分析 |
| ink-auto 增强输出 | ⚠️ 回退旧格式 | ✅ 完整新格式 |
| 所有旧命令 | ✅ 正常 | ✅ 正常 |
