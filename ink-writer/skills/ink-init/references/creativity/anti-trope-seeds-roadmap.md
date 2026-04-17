---
name: anti-trope-seeds-roadmap
description: Layer 2 种子库建设路线图，明示 Phase-Seed-1（1000 条初版）分 10 批交互流程与 Phase-Seed-∞ 增量触发条件。
type: reference
version: v1.0
---

# 种子库建设路线图

本路线图配套 `anti-trope-seeds.json`（骨架）与 `anti-trope-seeds-schema.json`（schema），说明从 skeleton → v1.0 → v1.x 的全阶段分工。Ralph 自动化阶段只负责骨架与 schema；1000 条正式种子由 Ralph 完成后的人工交互会话按本文件流程分 10 批产出。

## 阶段总览

| 阶段 | 规模 | 版本 | 执行方式 |
|------|------|------|----------|
| skeleton | 10-20 条 example | v1.0-skeleton | Ralph 本 PRD 自动化产出 |
| Phase-Seed-1 | 1000 条（10 类 × 100 条） | v1.0 | 交互会话分 10 批 × 每批 20 条 review 入库（100 条成品 = 150 候选 → 过滤到 100） |
| Phase-Seed-∞ | 每次 100-200 条增量 | v1.1 / v1.2 / ... | 触发条件驱动，单独会话补充 |

## Phase-Seed-1：初版 1000 条

### 分批计划（10 批）

每批覆盖 1 个 category，100 条正式入库，生成过程如下：

1. **候选生成** — LLM 生成 150 条候选（含 value / rarity 初判 / genre_tags / example_pairing）。
2. **联网反查** — WebSearch 抽样核实 30 条，过滤"榜单高频/已被模板化"的重复项。
3. **去重合并** — 按 value 语义去重，剔除与现有种子 value 重复 ≥80% 的条目。
4. **稀有度均衡** — 强制达成本批稀有度分布硬约束（见下表）。
5. **用户 review** — 呈现 20 条样本（覆盖全稀有度段）供人工确认；整体标签/措辞接受后批量入库。
6. **落库** — 追加 100 条进 `anti-trope-seeds.json`，`total += 100`，`changelog` 增记录一行，`version` 维持 v1.0 直到 10 批全部完成。

### 10 批顺序（建议）

1. profession 职业 → 2. era 时代 → 3. conflict 冲突 → 4. worldview 世界观 → 5. emotion 情感 → 6. taboo 禁忌 → 7. mythology 神话 → 8. taboo_language 禁忌语言 → 9. body_feature 身体特征 → 10. object 物件。

### 稀有度分布硬约束（每 100 条批次内生效）

| rarity | 占比下限 | 占比上限 | 约束说明 |
|--------|----------|----------|----------|
| 5 极稀缺 | **≥20%** | 35% | 高反套路价值，是扰动引擎的核武器 |
| 4 稀缺 | ≥30% | 45% | 主力供给层 |
| rarity 4 + rarity 5 合计 | **≥50%** | 75% | 硬约束：高稀缺占比超过一半 |
| 3 中等 | 15% | 30% | 场景铺垫层 |
| 2 常见 | 5% | 15% | 保留是为了给角色锚定日常 |
| 1 很常见 | 0% | 10% | 允许为零 |

未达分布的批次必须回到第 1 步补生成稀缺段候选，不得放宽标准硬塞。

### 10 类 × 稀有度矩阵（全库达成目标）

1000 条全部落地后，整库达成同一分布（表中占比同上）。`anti-trope-seeds-schema.json` 的字段层面已强制 `rarity` 取值 1-5，但占比需由入库审查人工把关。

## Phase-Seed-∞：增量补充

### 触发条件

- **自动 A**：抽取统计显示某 category 抽取集中度 >30%（同一 seed 近 30 次抽取中出现 ≥10 次）。
- **自动 B**：用户在同一次 `/ink-init --quick` 会话内连续 3 次"重随"仍不满意。
- **手动**：维护者或作者主动触发。

### 单次补充规模与流程

- 单次补充 **100-200 条**，流程沿用 Phase-Seed-1 的六步（生成 150 候选 → WebSearch 反查 → 去重 → 稀有度均衡 → 20 条 review → 入库 100 条），补充可覆盖单 category 或跨 category。
- 补充后版本号规则：v1.0 → v1.1 → v1.2 ...，每次写入 `anti-trope-seeds.json` frontmatter 的 `version` + `changelog`（含 `version / date / delta / note`）。

### 补充质量门槛（比初版更严格）

- 新增条目 **rarity ≥4 占比 ≥60%**（Phase-Seed-1 为 ≥50%）。
- 新增条目须规避近 30 天内 `data/market-trends/cache-*.md` 的共通套路词（US-007 联网缓存）。
- 每条新 seed 必须附 `example_pairing`，且示例不得与库内已有 example 重复 ≥70%。

## 范围外说明

- **OQ-10 `/ink-seeds add` 单条贡献命令** 不计入本 PRD 范围，后续独立 PRD 实施；当前仅支持批量补充。
- Ralph 阶段不得直接在骨架上追加正式种子（避免跳过 review 流程）；skeleton 文件中的 example 种子与正式 1000 条物理分离，`total` 字段显式排除 example。

## 下游接入

- `perturbation-engine.md`（US-003）从本库按激进度档位抽取 N 对扰动。
- `golden-finger-rules.md`（US-004）可参考 profession/worldview/taboo 三类作为金手指维度灵感池。
- `SKILL.md` Quick Step 0 将 `anti-trope-seeds.json` 列为 L1 必读。
