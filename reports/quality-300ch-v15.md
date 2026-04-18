# Q1-Q8 Quality Dashboard — 300-chapter shadow (v15)

> US-018 骨架产出。每 50 章采样一次 `collect_quality_metrics(project_root, (1, ch))`
> — 全部来自 SQL 直查（`.ink/index.db` + `state_kv`），**零 LLM 调用，零费**。
>
> 本文件是**骨架**：所有"真数字"栏位待用户手动触发 `python -m benchmark.e2e_shadow_300 --chapters 300`
> 后由 runner 写入 `benchmark/300chapter_run/shadow_full_metrics.json.quality_samples[]`，
> 再回填本文件。当前 smoke 运行（<300 章）视为骨架验证，不代表生产数字。

## 运行指令

```bash
# smoke（5 章，秒级）— 验证骨架链路
python -m benchmark.e2e_shadow_300 --chapters 5

# FULL（300 章，预计 10-30 min；无 LLM 调用）
python -m benchmark.e2e_shadow_300 --chapters 300 \
  --out benchmark/300chapter_run/shadow_full_metrics.json

# 仅看质量指标（不跑全压测；需已有 .ink/index.db）
python - <<'PY'
from ink_writer.quality_metrics import collect_quality_metrics
from pathlib import Path
print(collect_quality_metrics(Path(".ink-current-project-dir"), (1, 300)).to_dict())
PY
```

## 指标定义

| 编号 | 名称                          | SQL 源                                          | 单位 | 健康阈值（草案） |
| ---- | ----------------------------- | ----------------------------------------------- | ---- | ---------------- |
| Q1   | progression cross-chapter conflicts | `character_progressions` 前后切片 `from/to` 不连续 | 次   | < 5 / 300ch      |
| Q2   | foreshadow 埋设/回收比         | `plot_thread_registry.status` resolved vs 已埋 | 比率 | ≥ 0.6            |
| Q3   | propagation_debt 累积           | `.ink/propagation_debt.json` status='open'     | 条   | < 10             |
| Q4   | review_metrics.passed 比例      | `review_metrics` score≥0.8 且 critical=0       | 比率 | ≥ 0.85           |
| Q5   | consistency-checker critical 累积 | `review_metrics.critical_issues` + payload    | 次   | < 20             |
| Q6   | continuity-checker critical 累积  | `review_metrics.critical_issues` + payload    | 次   | < 20             |
| Q7   | candidate_facts 未消歧堆积       | `candidate_facts.status='candidate'`           | 条   | < 50             |
| Q8   | state_kv vs index.db 漂移       | 进度/实体数/前置活动数 三项对比                | 次   | = 0              |

## 300 章采样表（TODO：真数字待触发 FULL 运行后回填）

| 章次  | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 |
| ----- | -- | -- | -- | -- | -- | -- | -- | -- |
| 50    | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 100   | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 150   | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 200   | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 250   | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 300   | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Dashboard /quality 页面

**状态：TODO**（US-018 简化范围内延后）。骨架/指标/CLI 均已就绪，dashboard 前端页面留待后续 US
落地（浏览器手动验证在本 US 不可行——本轮无 ink-writer dashboard 启动路径的自动化 MCP 测试环境）。

建议下一步：
1. 在 `ink-writer/dashboard/` 新增 `/quality` 路由，读取 `benchmark/300chapter_run/shadow_*_metrics.json.quality_samples`。
2. 前端可复用 G2/G3 milestone 的趋势图组件，把 Q1-Q8 放折线图。
3. 真数字栏位回填本文件。

## 语义说明

- 任何 Q_n 为 `null`：表示底层表缺失（早期项目 / 部分迁移）。**不要**当作 0。
- `chapter_range` 采用闭区间 `[start, end]`；Q3 读 JSON 时会用 `chapter_detected` 过滤。
- Q4 / Q5 / Q6 在 `review_metrics` 行上以 **overlap** 判定是否纳入范围
  （`start_chapter <= end` AND `end_chapter >= start`）。
- Q8 目前只比对三把钥匙（current_chapter / entity_count / foreshadow_active）。后续可加更多。

## 相关代码

- `ink_writer/quality_metrics/collectors.py` — Q1-Q8 函数 + `QualityReport`
- `ink_writer/quality_metrics/__init__.py`    — `from ink_writer.quality_metrics import collect_quality_metrics`
- `tests/quality_metrics/test_collectors.py`  — 22 个单测（含 missing-table / range / 端到端）
- `benchmark/e2e_shadow_300.py` — `ShadowRunner._snapshot_quality` / `ShadowMetrics.quality_samples`
