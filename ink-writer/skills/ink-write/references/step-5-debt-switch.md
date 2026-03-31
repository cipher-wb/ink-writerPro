# Step 5 Debt Switch

## 默认策略

- 债务利息默认关闭。
- 只有两种情况允许开启：
  - 用户明确要求开启；
  - 项目已显式启用债务追踪。

## 执行命令

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index accrue-interest --current-chapter {chapter_num}
```

## 执行后要求

- 在 Step 5 输出中标注本次是否执行了利息计算。
- 若执行，输出结果摘要：处理债务数、累计利息、是否出现逾期。
- 若未执行，明确标注 `debt_interest: skipped (default off)`。

## 债务交互规则

### 同章创建与偿还

- **允许**同一章同时创建新 Override Contract 并偿还旧债务
- 偿还判定：本章实现了旧 Override 的 `payback_plan` 中承诺的补偿内容
- 偿还操作由 Data Agent 在 Step 5 执行：将对应债务 `status` 从 `active` 改为 `repaid`
- 新创建的 Override 和偿还操作互不影响

### 逾期债务处理

- 当 `due_chapter` 已过但债务未偿还时，`status` 变为 `overdue`
- `overdue` 债务不阻塞新 Override 的创建，但在 Macro-Review Tier2 中会被标记为高风险
- `overdue` 债务的利息继续累积（若利息功能已开启）
- 连续 3+ 个 `overdue` 债务时，reader-pull-checker 的软评分额外扣 5 分/个

### 每章 Override 上限

- 每章最多提交 2 个 Override Contract
- 超出时，checker 应标记为 `high` 级问题："Override 过度使用，建议修复而非覆盖"
