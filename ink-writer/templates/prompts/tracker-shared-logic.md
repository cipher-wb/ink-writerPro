<!-- version: 1.0.0 | changelog: initial extraction from foreshadow-tracker + plotline-tracker + thread-lifecycle-tracker -->

## Tracker 共享执行模式

### 输入硬规则

- 必须先读取 `review_bundle_file` 获取章节历史。
- 仅当审查包缺字段时，才允许补读 `allowed_read_files` 中的绝对路径文件。
- 禁止读取 `.db` 文件、目录路径、以及白名单外的相对路径。
- Tracker 只读，不修改 index.db / data 目录。

### 优先级与宽限规则

| 级别 | priority | 宽限期 | 逾期后处理 |
|------|----------|--------|-----------|
| P0 核心 | 80 | 5章 | `critical` — ink-plan 强制安排兑现 |
| P1 重要 | 50 | 10章 | `high` — ink-plan 优先安排 |
| P2 支线 | 20 | 20章 | `medium` — 告警建议 |

### 评分规则

- `base_score = 100`，每条 `critical` 扣 15，每条 `high` 扣 8，每条 `medium` 扣 3
- 密度告警扣 5，最低分 0
- `pass = overall_score >= 60` 且无 `critical` 逾期

### Plan Injection 模式

| plan_injection_mode | 行为 |
|--------------------|------|
| `force` | 不安排 → 规划失败，硬阻断 |
| `warn` | 不安排 → 输出警告，不阻断 |
