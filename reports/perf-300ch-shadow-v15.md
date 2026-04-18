# 300 章 Shadow 压测报告（v15 / US-017）

> **SMOKE 模式**（章数 <300）：本次运行仅用于骨架验证，下表不是 300 章真数字。

本报告由 `python -m benchmark.e2e_shadow_300` 生成，**零 LLM 调用**。
writer-agent / polish / checker 全部以 mock 形式替代（读文件生成章节、
模拟 data-agent payload），仅 data-agent Step 5 的 DB 写入走真实 Python 路径。

## 运行命令

```bash
# smoke（CI 默认，5 章）
python -m benchmark.e2e_shadow_300 --chapters 5 \
    --report reports/perf-300ch-shadow-v15.md

# 全量（用户手动触发，300 章）
python -m benchmark.e2e_shadow_300 --chapters 300 \
    --report reports/perf-300ch-shadow-v15.md

# 真 retriever 延迟（需首次加载 sentence-transformers，~30s）
python -m benchmark.e2e_shadow_300 --chapters 300 --real-retriever
```

## G1 — 单章 wall time（pipeline ingest 路径，零 LLM）

| 指标 | 值 |
|------|----|
| 平均 | 13.80 ms |
| p95 | 38.89 ms |
| 样本数 | 5 |

## G2/G3 — state.json / index.db 体积里程碑

| 章号 | state.json (KB) | index.db (KB) | 累计 wall (s) |
|------|-----------------|---------------|---------------|
| 5 | 0.71 | 432.00 | 0.069 |

## G4 — context-agent pack size（mock 估算）

| 指标 | 值 |
|------|----|
| 平均 char | 1418 |
| 估算 token | 834 |
| 样本数 | 5 |

## G5 — SemanticChapterRetriever.recall 延迟

| 指标 | 值 |
|------|----|
| p50 | 0.001 ms |
| p95 | 0.001 ms |
| 样本数 | 1 |

## 趋势示意

```mermaid
graph LR
    A[第1章] --> B[第50章]
    B --> C[第100章]
    C --> D[第200章]
    D --> E[第300章]
    A -.state.json/index.db 随章数线性增长.-> E
```

## 注意事项

- **真数字待人工触发**：300 章 full run 约需 10-30 分钟（纯 Python IO，无 LLM）。
  CI 默认仅跑 5 章 smoke（`tests/benchmark/test_shadow_runner_smoke.py`），避免 CI 超时。
- **README FAQ "100 章 7 小时"未更新**：需 full run 产出真数字后再改写。
  TODO：运行 `--chapters 100` 后用 G1 实测数据替换 FAQ 文案。
- G4/G5 mock 默认关闭真 retriever（避免 sentence-transformers 加载），
  用 `--real-retriever` 开启真实 FAISS 检索延迟测量。
