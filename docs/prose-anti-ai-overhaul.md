# Prose Anti-AI Overhaul -- 架构与运维手册

> 版本: 2026-04 | 分支: `ralph/prose-anti-ai-overhaul` | 性质: 七层深层重构

## 一、架构概览

```
                    +---------------------------+
                    |  prose_overhaul_enabled   |  <-- 总开关 (config/anti-detection.yaml)
                    +---------------------------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
   +------------------+ +-----------+ +-----------------------+
   | colloquial.yaml  | | anti-detc | | parallel-pipeline.yaml|
   | enabled: true     | | enabled:  | | enable_explosive: true|
   +------------------+ +-----------+ +-----------------------+
              |                |                |
              v                v                v
   +------------------+ +-----------+ +-----------------------+
   | colloquial-checker| | anti-detection| | explosive_retriever|
   | (C1-C5 5维白话度) | | (ZT 零容忍)  | | (RAG 爆款示例)     |
   +------------------+ +-----------+ +-----------------------+
              |                |                |
              |     +----------+-----------+    |
              |     |                      |    |
              v     v                      v    v
   +-------------------------------------------------+
   |              polish-agent / writer-agent          |
   |  (simplification_pass / hard_block_rewrite)       |
   +-------------------------------------------------+
                              |
                              v
   +-------------------------------------------------+
   |              directness-checker (D1-D7)           |
   |  (全场景激活, tier: explosive_hit/standard)       |
   +-------------------------------------------------+
```

## 二、七层改造清单

| 层 | US | 描述 | 文件 |
|----|-----|------|------|
| 1 | US-001 | 5条标点AI指纹零容忍规则 | `config/anti-detection.yaml` |
| 2 | US-002 | 装逼词黑名单三域 + 替换映射 | `ink-writer/assets/prose-blacklist.yaml` |
| 3 | US-003 | simplification_pass 接入替换映射 | `ink_writer/prose/simplification_pass.py` |
| 4 | US-004 | 5维白话度核心算法 | `ink_writer/prose/colloquial_checker.py` |
| 5 | US-005 | colloquial-checker pipeline注册 | `config/colloquial.yaml`, `step3_runner.py` |
| 6 | US-006 | directness-checker 全场景激活 | `ink_writer/prose/directness_checker.py` |
| 7 | US-007 | D6嵌套深度 + D7修饰链长 | `ink_writer/prose/directness_checker.py` |
| 8 | US-008 | explosive_hit 阈值桶 | `reports/seed_thresholds.yaml` |
| 9 | US-009 | L12 对话+动作驱动律 | `ink-writer/agents/writer-agent.md` |
| 10 | US-010 | 爆款示例RAG索引构建 | `scripts/build_explosive_hit_index.py` |
| 11 | US-011 | 爆款示例语义检索器 | `ink_writer/retrieval/explosive_retriever.py` |
| 12 | US-012 | writer-agent Step 2A检索注入 | `ink_writer/retrieval/inject.py` |
| 13 | US-013 | Hard Block Rewrite Mode | `ink-writer/agents/polish-agent.md` |
| 14 | US-014 | 5+5基线校准 | `scripts/calibrate_anti_ai_thresholds.py` |
| 15 | US-015 | E2E对照评估 | `scripts/e2e_anti_ai_overhaul_eval.py` |
| 16 | US-016 | 本文档 + 回滚开关 | `docs/prose-anti-ai-overhaul.md` |

## 三、阈值表

### directness-checker 7 维度 (D1-D7)

| 维度 | 含义 | explosive_hit green/yellow | standard green/yellow | 方向 |
|------|------|---------------------------|----------------------|------|
| D1 | 修辞密度 | ≤0.015 / ≤0.03 | ≤0.025 / ≤0.04 | lower |
| D2 | 形动比 | ≤0.12 / ≤0.16 | ≤0.16 / ≤0.19 | lower |
| D3 | 抽象词密度(/100字) | ≤0.05 / ≤0.10 | ≤0.078 / ≤0.14 | lower |
| D4 | 句长中位数 | 10-15 / 6-20 | 13-18 / 8-22 | mid |
| D5 | 空段率 | ≤30% / ≤50% | ≤50% / ≤68% | lower |
| D6 | 嵌套深度(子句/句) | ≤1.3 / ≤1.8 | ≤1.5 / ≤2.0 | lower |
| D7 | 修饰链长(的字数) | ≤1.2 / ≤2.0 | ≤1.5 / ≤2.5 | lower |

### colloquial-checker 5 维度 (C1-C5)

| 维度 | 含义 | green/yellow | 方向 |
|------|------|-------------|------|
| C1 | 成语密度(/千字) | ≤3.0 / ≤5.0 | lower |
| C2 | 四字格排比密度(/千字) | ≤6.0 / ≤10.0 | lower |
| C3 | 抽象名词链命中(/千字) | ≤1.0 / ≤2.0 | lower |
| C4 | 多层的修饰链密度(/千字) | ≤1.5 / ≤3.0 | lower |
| C5 | 抽象主语率 | ≤0.2 / ≤0.4 | lower |

### anti-detection ZT 零容忍

| 规则ID | 描述 | 类型 | 阈值 |
|--------|------|------|------|
| ZT_EM_DASH | 双破折号 —— | regex | 任意≥1 |
| ZT_AI_QUOTES | 智能引号 "" '' «» | regex | 任意≥1 |
| ZT_HYPHEN_AS_DASH | 中文间ASCII '-` | regex | 任意≥1 |
| ZT_DENSE_DUNHAO | 顿号密度 | density | >3/千字 |
| ZT_ELLIPSIS_OVERUSE | 省略号过用 | density | >8/千字 |

## 四、A/B 开关清单

| 开关 | 文件 | 键 | 默认值 | 作用 |
|------|------|-----|--------|------|
| 总开关 | `config/anti-detection.yaml` | `prose_overhaul_enabled` | `true` | false时三个子开关全强制false |
| 白话度门禁 | `config/colloquial.yaml` | `enabled` | `true` | false时colloquial-checker跳过 |
| 零容忍清单 | `config/anti-detection.yaml` | `enabled` | `true` | false时anti-detection全跳过 |
| 爆款检索 | `config/parallel-pipeline.yaml` | `enable_explosive_retrieval` | `true` | false时writer-agent不用RAG |

## 五、回滚 SOP

### 快速降级（1分钟）

按顺序修改三个配置文件：

1. `config/anti-detection.yaml` -- 设 `prose_overhaul_enabled: false`
   ```yaml
   prose_overhaul_enabled: false
   ```
2. 可选：`config/colloquial.yaml` -- 设 `enabled: false`（若仅关白话门禁）
3. 可选：`config/parallel-pipeline.yaml` -- 设 `enable_explosive_retrieval: false`（若仅关RAG）

### 验证回归

```bash
# 跑完整回归测试集
pytest tests/prose/ tests/anti_detection/ tests/polish/ tests/eval/ --no-cov

# 跑回滚验证测试
pytest tests/integration/test_prose_overhaul_rollback.py --no-cov
```

### 提交回滚

```bash
git add config/anti-detection.yaml config/colloquial.yaml config/parallel-pipeline.yaml
git commit -m "rollback: disable prose anti-AI overhaul"
```

### 部分回滚（保留部分改造）

若只想关某个子模块，只改对应的开关：

- 只关白话度检查：`config/colloquial.yaml` `enabled: false`
- 只关零容忍：`config/anti-detection.yaml` `enabled: false`
- 只关爆款RAG：`config/parallel-pipeline.yaml` `enable_explosive_retrieval: false`

## 六、依赖关系

```
US-002 (黑名单) ──> US-003 (替换映射) ──> US-004 (白话度) ──> US-005 (pipeline)
US-001 (零容忍) ──────────────────────────────────────────────────> US-013 (硬阻断)
US-006 (全场景) ──> US-007 (D6/D7) ──> US-008 (阈值桶) ──> US-014 (校准)
US-010 (索引构建) ──> US-011 (检索器) ──> US-012 (注入)
```

## 七、性能指标

| 指标 | 目标 | 实际 |
|------|------|------|
| 破折号密度 | ≤0.2/千字 | 0.1 (mock) |
| 嵌套深度 | ≤1.5 | 1.2 (mock) |
| 成语密度 | ≤3.0/千字 | 2.0 (mock) |
| 四字格密度 | ≤6.0/千字 | 4.0 (mock) |
| 对话占比 | ≥0.40 | 0.45 (mock) |

## 八、known-issues

1. `check_zero_tolerance()` 对极短文本返回 `None`（而非空列表）-- 这是设计，调用方需 `is not None` 检查
2. D4 句长中位数 mid-is-better 对极短句（<8字）触发 red -- 写测试 fixture 时用 13+ 字正常句
3. 三个开关独立：`prose_overhaul_enabled` 作为总开关强制子开关，但子开关也可单独关闭
4. `explosive_retriever` 首次加载 sentence-transformers 需 ~30s；测试用 mock 模式跳过
