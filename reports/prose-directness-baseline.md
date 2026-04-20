# Prose Directness Baseline Report

- Generated: 2026-04-20
- Source: `reports/prose-directness-stats.json`
- Total chapters: **1487** from **50** books

> 本报告消费 US-001 产出的 5 维度直白密度扫描结果，为 US-005 directness-checker
> 提供 P25/P50/P75 基线与 Green/Yellow/Red 阈值推荐；机器可读版见同目录
> `seed_thresholds.yaml`。

## 场景样本分布

| Scene | Chapters | 占比 |
|-------|----------|------|
| golden_three | 150 | 10.1% |
| combat | 0 | 0.0% |
| other | 1337 | 89.9% |

> _combat 场景 0 样本：US-001 启发式无法从 `ch###.txt` 文件名识别战斗标题，运行期将继承 `golden_three` 阈值（快节奏高激活区，直白诉求同向）。_

## 每场景 5 维度百分位

### golden_three (n=150)

| Metric | P25 | P50 | P75 | min | max |
|--------|-----|-----|-----|-----|-----|
| D1 修辞密度 (比喻+排比/总句数) | 0.0114 | 0.0247 | 0.0399 | 0.0000 | 0.1818 |
| D2 形容词-动词比 | 0.1288 | 0.1595 | 0.1872 | 0.0678 | 0.2814 |
| D3 抽象词密度 (每 100 字) | 0.0314 | 0.0776 | 0.1434 | 0.0000 | 0.3570 |
| D4 句长中位数 (词) | 13.0000 | 15.0000 | 17.6250 | 9.0000 | 512.5000 |
| D5 空描写段数 | 31.0000 | 50.5000 | 68.2500 | 5.0000 | 226.0000 |

### combat (n=0)

> _样本为空_——阈值继承自 `golden_three`。

### other (n=1337)

| Metric | P25 | P50 | P75 | min | max |
|--------|-----|-----|-----|-----|-----|
| D1 修辞密度 (比喻+排比/总句数) | 0.0096 | 0.0216 | 0.0382 | 0.0000 | 0.2857 |
| D2 形容词-动词比 | 0.1318 | 0.1565 | 0.1827 | 0.0389 | 0.3264 |
| D3 抽象词密度 (每 100 字) | 0.0321 | 0.0834 | 0.1447 | 0.0000 | 0.8475 |
| D4 句长中位数 (词) | 13.0000 | 15.0000 | 18.0000 | 7.0000 | 44.0000 |
| D5 空描写段数 | 27.0000 | 37.0000 | 52.0000 | 2.0000 | 185.0000 |

## 推荐阈值（directness-checker 消费）

评分规则（映射到 PRD US-005 的 0-10 分制）：

- **lower_is_better**（D1 / D2 / D3 / D5）：
  `value ≤ P50` → Green（score ≥ 8）；
  `P50 < value ≤ P75` → Yellow（6 ≤ score < 8）；
  `value > P75` → Red（score < 6，触发重写）。
- **mid_is_better**（D4 句长）：`[P25, P75]` → Green；
  外扩 1 个 IQR → Yellow；更远 → Red。

### golden_three

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| D1 修辞密度 (比喻+排比/总句数) | ≤ 0.0247 | ≤ 0.0399 | > 0.0399 |
| D2 形容词-动词比 | ≤ 0.1595 | ≤ 0.1872 | > 0.1872 |
| D3 抽象词密度 (每 100 字) | ≤ 0.0776 | ≤ 0.1434 | > 0.1434 |
| D4 句长中位数 (词) | [13.00, 17.62] | [8.38, 22.25] | outside yellow band |
| D5 空描写段数 | ≤ 50.5000 | ≤ 68.2500 | > 68.2500 |

### other

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| D1 修辞密度 (比喻+排比/总句数) | ≤ 0.0216 | ≤ 0.0382 | > 0.0382 |
| D2 形容词-动词比 | ≤ 0.1565 | ≤ 0.1827 | > 0.1827 |
| D3 抽象词密度 (每 100 字) | ≤ 0.0834 | ≤ 0.1447 | > 0.1447 |
| D4 句长中位数 (词) | [13.00, 18.00] | [8.00, 23.00] | outside yellow band |
| D5 空描写段数 | ≤ 37.0000 | ≤ 52.0000 | > 52.0000 |

## 推荐 checker 阈值常量（Python 风格，示例）

```python
# 黄金三章 + 战斗/高潮/爽点场景；directness-checker 可 import
RHETORIC_MAX = 0.0247  # P50 → Green upper bound
RHETORIC_RED = 0.0399  # P75 → Red lower bound
ADJ_VERB_MAX = 0.1595  # P50 → Green upper bound
ADJ_VERB_RED = 0.1872  # P75 → Red lower bound
ABSTRACT_MAX = 0.0776  # P50 → Green upper bound
ABSTRACT_RED = 0.1434  # P75 → Red lower bound
SENT_LEN_GREEN_LOW = 13.00  # P25
SENT_LEN_GREEN_HIGH = 17.62  # P75
EMPTY_PARA_MAX = 50.5000  # P50 → Green upper bound
EMPTY_PARA_RED = 68.2500  # P75 → Red lower bound
```

## 跨书对比（D1 修辞 + D3 抽象词 均值）

### 最直白 Top 5

| Book | D1+D3 mean |
|------|-----------|
| 西游：拦路人！ | 0.0136 |
| 状元郎 | 0.0252 |
| 我，枪神！ | 0.0297 |
| 重回1982小渔村 | 0.0322 |
| 1979黄金时代 | 0.0502 |

### 最华丽 Top 5

| Book | D1+D3 mean |
|------|-----------|
| 神明调查报告 | 0.4085 |
| 异度旅社 | 0.3528 |
| 亡灵法师，召唤055什么鬼？ | 0.2437 |
| 真君驾到 | 0.2419 |
| 仙业 | 0.1885 |

## 机器可读输出

同目录 `seed_thresholds.yaml` 包含完整 percentile 与阈值常量，供 US-005 directness-checker / US-010 现有 checker 微调消费。
