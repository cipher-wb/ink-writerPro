# Prose Anti-AI Overhaul — 文笔反 AI 味 + 爆款白话化深层重构

> 版本: 2026-04 | 分支: `ralph/prose-anti-ai-overhaul` | 16 User Stories

## 架构概览（七层改造）

```
                      ┌──────────────────────────────┐
                      │   config/anti-detection.yaml  │  ← 总开关 prose_overhaul_enabled
                      │   config/colloquial.yaml      │
                      │   config/parallel-pipeline.yaml│
                      └──────────────┬───────────────┘
                                     │
   ┌─────────────────────────────────┼─────────────────────────────────┐
   │                                 │                                 │
   ▼                                 ▼                                 ▼
┌──────────┐                 ┌──────────────┐                ┌────────────────┐
│ 第 1 层   │                 │  第 2-3 层    │                │ 第 4-5 层       │
│ 标点零容忍 │                 │  装逼词黑名单  │                │ 白话度+直白度   │
│ US-001   │                 │  US-002,003  │                │ US-004..008    │
│ em-dash  │                 │  90+ 词 × 3域 │                │ C1-C5 + D1-D7 │
│ 智能引号  │                 │  + 替换映射   │                │ 全场景激活     │
└────┬─────┘                 └──────┬───────┘                └──────┬─────────┘
     │                              │                               │
     └──────────────────────────────┼───────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌───────────┐  ┌──────────────┐  ┌──────────────┐
            │ 第 6 层    │  │ 第 7 层       │  │ 第 8 层       │
            │ writer-agent│  │ polish-agent  │  │ 评估+回滚     │
            │ L11 驱动律  │  │ Hard Block    │  │ US-014..016  │
            │ + RAG few-shot│ │ Rewrite Mode  │  │              │
            │ US-009..012 │  │ US-013        │  │              │
            └───────────┘  └──────────────┘  └──────────────┘
```

## 阈值表

| 维度 | 描述 | 爆款档 green | 爆款档 yellow | 标准档 green | 标准档 yellow |
|------|------|-------------|--------------|-------------|--------------|
| D1 | 修辞密度 | ≤ 1.5% | ≤ 3.0% | ≤ 2.0% | ≤ 4.0% |
| D2 | 形动比 | ≤ 12% | ≤ 16% | ≤ 15% | ≤ 20% |
| D3 | 抽象词密度 | ≤ 5% | ≤ 10% | ≤ 8% | ≤ 12% |
| D4 | 句长中位数 | 10-15 | 6-20 | 8-18 | 5-25 |
| D5 | 空描写率 | ≤ 5% | ≤ 10% | ≤ 8% | ≤ 15% |
| D6 | 嵌套深度 | ≤ 1.3 | ≤ 1.5 | ≤ 1.5 | ≤ 2.0 |
| D7 | 修饰链长 | ≤ 1.0 | ≤ 1.5 | ≤ 1.5 | ≤ 2.5 |
| C1 | 成语密度 | ≤ 2/千字 | ≤ 3/千字 | ≤ 4/千字 | ≤ 6/千字 |
| C2 | 四字格密度 | ≤ 4/千字 | ≤ 6/千字 | ≤ 6/千字 | ≤ 8/千字 |

## A/B 开关清单

| 开关 | 文件 | 默认值 | 作用 |
|------|------|--------|------|
| `prose_overhaul_enabled` | `config/anti-detection.yaml` | `true` | **总开关** — false 时所有子开关被强制 false |
| `enabled` | `config/colloquial.yaml` | `true` | 白话度 checker 开关 |
| `enable_explosive_retrieval` | `config/parallel-pipeline.yaml` | `true` | 爆款示例 RAG 检索开关 |
| `max_hard_block_retries` | `config/anti-detection.yaml` | `1` | 硬阻断最大重写次数（0=不重写直接阻断） |
| `INK_STEP3_RUNNER_MODE` | 环境变量 | `enforce` | Step 3 模式（off/shadow/enforce） |
| `INK_STEP3_LLM_CHECKER` | 环境变量 | (auto) | LLM checker 开关（off=stub） |
| `INK_STEP3_LLM_POLISH` | 环境变量 | (auto) | LLM polish 开关（off=stub） |

## 回滚 SOP

### 紧急回滚（一键关闭所有新功能）

```bash
# 1. 编辑 config/anti-detection.yaml，将 prose_overhaul_enabled 改为 false
#    这会将 colloquial + hard_block_rewrite 全部禁用

# 2. 设置 Step 3 为 shadow 模式（只记录不阻断）
export INK_STEP3_RUNNER_MODE=shadow

# 3. 跑回归测试确认旧行为恢复
pytest tests/checker_pipeline/ tests/prose/ -x

# 4. 提交回滚 commit
git add config/anti-detection.yaml
git commit -m "rollback: disable prose anti-ai overhaul"
```

### 逐层回滚

1. **只关闭爆款 RAG**: `enable_explosive_retrieval: false` → writer-agent 回退旧提示词
2. **只关闭白话度检查**: `enabled: false` in `config/colloquial.yaml` → 跳过 C1-C5
3. **只关闭硬阻断重写**: `max_hard_block_retries: 0` → 不重写，直接按原逻辑阻断
4. **只关闭标点零容忍**: comment out ZT rules in `anti-detection.yaml`

## 模块文件索引

| 文件 | 用途 |
|------|------|
| `ink_writer/prose/colloquial_checker.py` | C1-C5 白话度五维量化 |
| `ink_writer/prose/directness_checker.py` | D1-D7 直白度七维评分 |
| `ink_writer/prose/simplification_pass.py` | 装逼词自动替换 |
| `ink_writer/retrieval/explosive_retriever.py` | 爆款示例语义检索引擎 |
| `ink_writer/retrieval/inject.py` | prompt 注入 helper |
| `ink_writer/checker_pipeline/hard_block_rewrite.py` | 硬阻断全章重写逻辑 |
| `ink_writer/checker_pipeline/step3_runner.py` | Step 3 编排器 |
| `scripts/build_explosive_hit_index.py` | 从 corpus 构建爆款索引 |
| `scripts/calibrate_anti_ai_thresholds.py` | 5+5 基线校准 |
| `scripts/e2e_anti_ai_overhaul_eval.py` | 旧/新 pipeline 对照评估 |
| `config/anti-detection.yaml` | 总开关 + 标点零容忍规则 |
| `config/colloquial.yaml` | 白话度 checker 配置 |
| `reports/seed_thresholds.yaml` | 双档阈值定义 |

## 已知限制

- 爆款 RAG 索引需预先构建（`python3 scripts/build_explosive_hit_index.py`）
- 阈值校准需人工确认（mock 模式仅生成近似值）
- hard_block_rewrite 依赖 ANTHROPIC_API_KEY 进行 LLM 重写
