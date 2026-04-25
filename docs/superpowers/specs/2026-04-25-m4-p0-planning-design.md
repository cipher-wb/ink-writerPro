# M4 P0 上游策划层 — ink-init / ink-plan 阶段强制策划审查 (Design Spec)

**Status**: ready-for-plan
**Date**: 2026-04-25
**Author**: cipher-wb（产品）+ brainstorming co-pilot
**Baseline**: v23.0.0 + M1 (`m1-foundation`) + M2 partial (`m2-data-assets-partial`) + M3 (`m3-p1-loop`)
**Target version**: v25.x（5 周 M1-M5 的第 4 步，**50 → 60+ 分质量拐点**）
**Quality target**: ink-init / ink-plan 阶段每次产出自带 `planning_evidence_chain.json` + 题材老套 / AI 起名 / 金手指出场过晚等 5/8 上游扣分点被阻断在策划期
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §3 P0 + §9 M4
**Brainstorm 记录**: `docs/superpowers/M4-PREPARATION-NOTES.md` Part C（15 题全采用 ⭐ 推荐）

---

## 1. 背景与问题陈述

### 1.1 M1/M2/M3 已交付（前提）

- **M1** ✅：Case Library 基础设施 + Qdrant + Preflight + reference_corpus symlink 修复
- **M2** 🟡：cases 完整（403 cases，hard 236 / soft 147 / info 19）+ corpus_chunking 管线（实跑 deferred）
- **M3** ✅：writer-self-check + 阻断重写 + evidence_chain.json 全链路落档（见 `tasks/prd-m3-p1-loop.md` 14 US 全 ✅）

### 1.2 M4 要解决的问题

Origin spec §1.3 编辑评分诊断里有 **8 项扣分**，其中 **5 项发生在策划期**（开书前），M3 全部覆盖不到：

| 扣分项 | 当前缺失 | M4 对应 checker |
|---|---|---|
| 题材老套 / 套用度高 | 没人比对起点 top200 | `genre-novelty-checker` |
| 金手指能力描述模糊 / 不清晰 | 仅靠 writer 心情判断 | `golden-finger-spec-checker` |
| 角色名 AI 味重（叶凡 / 林夜 / 陈青山）| 没起名词典 | `naming-style-checker` |
| 主角动机牵强 / 无法共鸣 | M3 章节级 protagonist-agency 太晚发现 | `protagonist-motive-checker` |
| 金手指出场太晚（前 3 章不出）| 没人卡时机 | `golden-finger-timing-checker` |
| 主角骨架级被动 / 大纲就缺主动决策 | M3 章节级太晚 | `protagonist-agency-skeleton-checker` |
| 章节钩子稀疏 / 大纲就钩子密度低 | 没人在大纲阶段查 | `chapter-hook-density-checker` |

加上配套的 **2 个数据资产**（起点 top200 简介库 + LLM 高频起名词典 ≈ 300 条）和 **7 个种子 case**（每 checker ≥1）+ ink-init/ink-plan SKILL.md Step 99 集成 + dry-run 5 章护栏，构成 M4 完整范围。

### 1.3 设计原则

1. **复用 M3 资产**：`config/checker-thresholds.yaml` / `evidence_chain.json` schema / `block_threshold_wrapper` / `thresholds_loader.py` / `LLMClient` wrapper 全复用
2. **与 M3 chapter 阶段平行不交叉**：M4 跑 ink-init / ink-plan 阶段；M3 跑 ink-write 章节阶段；可同时 dry-run 互不干扰
3. **阻断策略与 M3 完全一致**：P0 阻断 / P1 警告需豁免 / P2-P3 提示
4. **dry-run 5 次护栏**：避免 7 个新 checker 一次上线翻车（用独立 `data/.planning_dry_run_counter` 与 M3 区分）
5. **M2 chunks 缺席兼容**：M4 的 7 个 checker 全部不依赖 corpus_chunks
6. **独立紧急绕过 flag**：`--skip-planning-review` 在 ink-init / ink-plan 阶段写 `evidence_chain.warn`，但不阻塞用户开新书

---

## 2. 整体架构

### 2.1 数据流

```
[ink-init Quick/Detailed] 用户填字段 / LLM 生成 3 套方案
   │
   ▼
[现有] 方案落档（题材 / 主角设定 / 金手指 / 名字）
   │
   ▼
[NEW Step 99 ink-init 策划审查] ── 4 个 checker 串行
   │   genre-novelty / golden-finger-spec / naming-style / protagonist-motive
   │
   ▼
任一 < block_threshold + cases_hit
  → dry-run 期：写 planning_evidence_chain.json + 警告 + 通行
  → dry-run 完成后：阻断 + 提示用户改方案 / 加 --skip-planning-review
全部 ≥ threshold → 通行 + 写 planning_evidence_chain.json
   │
   ▼
[ink-plan] 卷大纲 / 节拍表 / 章节骨架生成
   │
   ▼
[NEW Step 99 ink-plan 策划审查] ── 3 个 checker 串行
   │   golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density
   │
   ▼
（同上阻断逻辑，写 planning_evidence_chain.json）
   │
   ▼
最终交付：data/<book>/setting.json + outline/*.md + planning_evidence_chain.json
```

### 2.2 七大 checker

| # | checker | 阶段 | 输入 | 关键依赖数据 |
|---|---|---|---|---|
| 1 | `genre-novelty-checker` | ink-init | 题材标签 + 主线一句话 | `data/market_intelligence/qidian_top200.jsonl` |
| 2 | `golden-finger-spec-checker` | ink-init | 金手指描述 | 无（LLM 主观判断 4 维度）|
| 3 | `naming-style-checker` | ink-init | 主角 / 重要配角名 | `data/market_intelligence/llm_naming_blacklist.json` |
| 4 | `protagonist-motive-checker` | ink-init | 主角动机段 | 无（LLM 主观判断 3 维度）|
| 5 | `golden-finger-timing-checker` | ink-plan | 卷大纲 + 章节骨架 | 无（前 3 章 regex / LLM 双重）|
| 6 | `protagonist-agency-skeleton-checker` | ink-plan | 卷骨架的章节摘要 | 无（LLM 主观判断）|
| 7 | `chapter-hook-density-checker` | ink-plan | 章节骨架的钩子标注 | 无（LLM 主观判断）|

### 2.3 与 M1/M2/M3 资产复用

| 已有资产 | M4 中的角色 | 改不改 |
|---|---|---|
| `ink_writer/case_library/{store, ingest, models}` | 7 个 checker 的 cases_hit 计算 | 不动 |
| `data/case_library/cases/` | 加 7+ 个上游 seed cases（M2 batch approve 流程入活）| 加文件不动结构 |
| `scripts/corpus_chunking/llm_client.LLMClient` | M4 全部 LLM 调用复用 | 不动 |
| `~/.claude/ink-writer/.env` 的 `LLM_MODEL=glm-4.6` | M4 沿用 | 不改 |
| `config/checker-thresholds.yaml` | M3 已建；M4 加 7 个 checker 段 | 加段不改结构 |
| `ink_writer/checker_pipeline/{thresholds_loader, block_threshold_wrapper}` | M4 7 个 checker 全部走这套 wrapper | 不动 |
| `data/<book>/chapters/<chapter>.evidence.json` schema | M4 派生 `data/<book>/planning_evidence_chain.json`（同结构）| 复用 schema |
| `ink-writer/skills/ink-init/SKILL.md`（22 节）| 末尾加 Step 99 策划审查 | 加章节不改前 22 节 |
| `ink-writer/skills/ink-plan/SKILL.md`（21 节）| 末尾加 Step 99 策划审查 | 加章节不改前 21 节 |

### 2.4 边界（明确不做的事）

- ❌ 不补 corpus_chunks（M2 deferred 状态保持）
- ❌ 不动 M3 已建的 5 个章节级 checker（reader-pull / sensory / high-point / conflict-skeleton / protagonist-agency）
- ❌ 不动 ink-write 阶段任何流程（M4 仅在 ink-init / ink-plan 阶段加阻断）
- ❌ 不做 P3 自进化 / dashboard → M5
- ❌ 不退役 FAISS / 不动 v22 simplicity 域
- ❌ 不做 interactive review 体验优化（M5 dashboard 配套）
- ❌ 不打包"M4 一次跑全 7 checker 的 CLI"（直接走 SKILL.md Step 99 调用即可）
- ❌ 不建立"上游 cases 持续扩充流水线"（与下游 case 库共享 ingest_case 工具，无需独立产线）

---

## 3. 七大 checker 详细设计

> 所有 checker 都遵循 M3 的 wrapper pattern：`checker.run(...) → CheckerReport` → `block_threshold_wrapper` → `polish-loop`（M4 的 polish-loop 实质上是"提示用户改方案 / dry-run 期写警告"）。下面只列**与 M3 不同的部分**。

### 3.1 `genre-novelty-checker`（ink-init）

**目的**：把当前书的题材标签 + 主线一句话与起点 top200 比对，找出过度雷同。

**输入**：
- `genre_tags`（如：["都市", "重生", "金融"]）
- `main_plot_one_liner`（如："2008 年金融危机重生抄底"）
- `data/market_intelligence/qidian_top200.jsonl`（每行：`{rank, title, author, genre_tags, intro_one_liner, intro_full}`）

**算法**：
1. 用 LLMClient（glm-4.6）按"题材重合度 + 卖点重合度"两个维度评分
2. 对 top200 逐条算 similarity（让 LLM 输出 0-1 分），取 top-5 最相似
3. `novelty_score = 1.0 - max(top5_similarities)`
4. `cases_hit = []`（如果触发 `CASE-2026-M4-0001`「题材老套」则记入，case 详见 §4.3）

**阈值**（写 `config/checker-thresholds.yaml` 新段）：
```yaml
genre_novelty:
  block_threshold: 0.40      # 与 top200 重合度 60%+ 阻断
  warn_threshold: 0.55
  dry_run: true
  case_ids: ["CASE-2026-M4-0001"]  # 题材老套种子 case
```

**LLM prompt 模板**（要点）：
- 严格 JSON 输出 `{rank: int, similarity: float, reason: str}` 每条
- max_tokens 控制（2048）

**单元测试**：
- 假 top200 fixture（10 条，含明显雷同的"都市重生金融抄底"）→ 当前书一致 → similarity 高 → 阻断
- 假 top200 + 当前书完全独特 → similarity 低 → 通过

### 3.2 `golden-finger-spec-checker`（ink-init）

**目的**：金手指描述要清晰、可证伪、有边界、有成长曲线 4 维度。

**输入**：`golden_finger_description`（≤ 500 字）

**算法**：
- LLM 按 4 维度各打 0-1 分：
  - clarity（清晰度）：能不能一句话说清楚做什么的
  - falsifiability（可证伪性）：是否会失败 / 有约束
  - boundary（能力边界）：什么不能做
  - growth_curve（成长曲线）：随章节怎么变强
- `score = mean(4 dim)`
- `cases_hit`：触发 CASE-2026-M4-0002「金手指模糊」

**阈值**：`block_threshold: 0.65`

### 3.3 `naming-style-checker`（ink-init）

**目的**：主角 / 重要配角名不踩 AI 模板（叶凡 / 林夜 / 陈青山 / 李逍遥 / 沈墨 ...）。

**输入**：
- `character_names`（list of dict：`[{role: "主角", name: "..."}, {role: "女主", name: "..."}]`）
- `data/market_intelligence/llm_naming_blacklist.json`（≈ 300 条 + 字根模式）

**词典格式**：
```json
{
  "version": "1.0",
  "exact_blacklist": ["叶凡", "林夜", "陈青山", "李逍遥", "沈墨", ...],
  "char_patterns": {
    "first_char_overused": ["叶", "林", "沈", "陈", "苏"],
    "second_char_overused": ["凡", "夜", "尘", "墨", "辰"]
  },
  "notes": "..."
}
```

**算法**：
1. exact match 命中 → score = 0
2. 双字组合模式命中（如 "X 凡" / "林 X"）→ score = 0.4
3. 单字模式命中 → score = 0.7
4. 全无命中 → score = 1.0
5. `overall = mean(per_name_scores)`

**阈值**：`block_threshold: 0.70`（容忍 1-2 个字根模式，禁止 exact match）

**Q3 数据来源**：手工汇总 ~150 条已知 AI 模板名 + LLM 扩充 150 条同 pattern → 共 ≈ 300 条。

### 3.4 `protagonist-motive-checker`（ink-init）

**目的**：主角动机要可共鸣、有具体目标、有内在冲突 3 维度。

**输入**：`protagonist_motive_description`（≤ 800 字）

**算法**：LLM 按 3 维度各打 0-1 分 → 平均。

**阈值**：`block_threshold: 0.65`

### 3.5 `golden-finger-timing-checker`（ink-plan）

**目的**：金手指必须在前 3 章出现（最晚第 3 章末尾）。

**输入**：
- `outline_volume_skeleton`（list of `{chapter_idx, summary}`）
- `golden_finger_keywords`（从 ink-init 阶段已确定的金手指描述提取）

**算法**：
1. regex 扫前 3 章 summary 是否含金手指关键词 → True/False
2. 如 False，让 LLM 二次判断（防 regex 漏判）
3. `passed = (regex_match or llm_match)`

**阈值**：硬阻断（`block_threshold: 1.0`），不通过即 P0。

### 3.6 `protagonist-agency-skeleton-checker`（ink-plan）

**目的**：在卷骨架级（不是章节级）查主角主动决策章节占比。

**输入**：`outline_volume_skeleton` 的章节摘要 list

**算法**：
1. LLM 对每章摘要打 `agency_score`（0-1）：主角是否主动驱动情节
2. `active_ratio = mean(agency_scores)`

**阈值**：`block_threshold: 0.55`

### 3.7 `chapter-hook-density-checker`（ink-plan）

**目的**：章节骨架的章末钩子密度。

**输入**：`outline_volume_skeleton` 的章节摘要 list

**算法**：
1. LLM 对每章打 `hook_strength`（0-1）：章末是否有诱导追读的钩子
2. `density = (count where hook_strength >= 0.5) / total_chapters`

**阈值**：`block_threshold: 0.70`

---

## 4. 数据资产

### 4.1 起点 top200 简介库（US-007）

**位置**：`data/market_intelligence/qidian_top200.jsonl`

**Schema**（每行 1 JSON）：
```json
{
  "rank": 1,
  "title": "...",
  "author": "...",
  "url": "https://...",
  "genre_tags": ["..."],
  "intro_one_liner": "...",
  "intro_full": "...",
  "fetched_at": "2026-04-25T12:00:00Z"
}
```

**采集**（US-007 范围）：
- `scripts/market_intelligence/fetch_qidian_top200.py`：BeautifulSoup + requests + 1 req/s 限速 + UA 礼貌 + 遵守 robots.txt
- 失败重试 3 次 + checkpoint 续爬
- 一次性跑完，长期不再重爬（手动每 6 个月 refresh）

**合规**：简介是公开数据，限速 + UA + robots.txt 遵守即合规。

### 4.2 LLM 高频起名词典（US-008）

**位置**：`data/market_intelligence/llm_naming_blacklist.json`

Schema 见 §3.3。

**构建**（US-008 范围）：
1. 手工汇总（约 1 小时）：浏览近年起点 / 番茄热门修仙 / 都市文，记录主角名 → ≈ 150 条 exact + 字根模式约 30 个
2. LLM 扩充：让 glm-4.6 按"AI 起名 pattern"生成 150 条同 pattern 名 → 人工审一遍（约 30 分钟）
3. 合并 → 300 条 exact + ≈ 30 个字根模式

### 4.3 上游 seed cases（US-013）

**位置**：`data/case_library/cases/CASE-2026-M4-NNNN.yaml`（7 个，编号 0001-0007）

| case_id | 标题 | 对应 checker | failure_pattern.observable（关键词） |
|---|---|---|---|
| CASE-2026-M4-0001 | 题材老套（与 top200 重合度高）| genre-novelty | "题材", "重生", "金融", "都市" 等高频组合 |
| CASE-2026-M4-0002 | 金手指模糊 | golden-finger-spec | "强大的能力", "无所不能" 等模糊词 |
| CASE-2026-M4-0003 | 主角名 AI 味重 | naming-style | exact match blacklist |
| CASE-2026-M4-0004 | 主角动机牵强 | protagonist-motive | "为了变强", "无聊" 等空洞动机 |
| CASE-2026-M4-0005 | 金手指出场过晚 | golden-finger-timing | 前 3 章 summary 无关键词 |
| CASE-2026-M4-0006 | 大纲主角骨架级被动 | protagonist-agency-skeleton | 章节摘要"被告知 / 听说 / 偶遇"高频 |
| CASE-2026-M4-0007 | 大纲钩子密度低 | chapter-hook-density | 章末"安然睡去 / 一切如常"高频 |

**入活流程**：US-013 创建 7 个 yaml + `ink case approve --batch CASE-2026-M4-*` 一次入活。

---

## 5. SKILL.md Step 99 集成

### 5.1 ink-init Step 99（US-012a）

在 `ink-writer/skills/ink-init/SKILL.md` 末尾追加：

```markdown
## Step 99：策划期审查（M4 必跑）

执行 4 个 checker（genre-novelty / golden-finger-spec / naming-style / protagonist-motive），写 planning_evidence_chain.json。

如检测到 dry-run 模式（counter < 5）：仅警告 + 写 evidence_chain.warn，继续。
检测到 real 模式（counter >= 5）：任一 checker P0 阻断 → 终止 ink-init + 提示用户改方案。

绕过：用户加 --skip-planning-review 时跳过 Step 99，但 evidence_chain.warn 记录 "skipped_planning_review"。

调用：
python -m ink_writer.planning_review.ink_init_review \
  --book {book_id} \
  --setting {setting_path}
```

### 5.2 ink-plan Step 99（US-012b）

类似结构，调用 `ink_writer.planning_review.ink_plan_review`，跑 3 个 checker。

### 5.3 dry-run 计数器（US-009）

`data/.planning_dry_run_counter`（与 M3 `data/.dry_run_counter` 独立）：
- 每次 ink-init / ink-plan Step 99 跑通 +1
- ≥ 5 → 切真阻断模式
- 配套 `dry_run_report.py` 仿 M3：5 次后聚合"过去 5 次策划审查命中 case 的频次 + 各 checker 平均分"

### 5.4 紧急绕过 flag

ink-init / ink-plan CLI 加 `--skip-planning-review`（存在即跳过 Step 99，但写 `planning_evidence_chain.warn = "skipped"`）。

---

## 6. evidence_chain 派生

### 6.1 `planning_evidence_chain.json` schema

复用 M3 `evidence_chain.json` schema，加 `phase` 字段区分：

```json
{
  "schema_version": "1.0",
  "phase": "planning",                 // M4 新增；chapter 阶段为 "writing"
  "book": "demo-001",
  "stage": "ink-init",                 // 或 "ink-plan"
  "started_at": "...",
  "ended_at": "...",
  "checkers": [
    {
      "checker": "genre-novelty",
      "score": 0.62,
      "passed": true,
      "cases_hit": [],
      "raw_report": {...}
    },
    ...
  ],
  "dry_run": true,
  "skipped": false,
  "skip_reason": null,
  "overall_passed": true
}
```

**写入路径**：`data/<book>/planning_evidence_chain.json`（每本 1 个，ink-init + ink-plan 各跑一次后追加 stage 段）。

**向后兼容**：M3 chapter `evidence_chain.json` 文件**不强制 backfill** `phase` 字段；M4 新增的 chapter 文件可选择写 `phase: "writing"`，loader 缺字段时 fallback 为 `"writing"`（兼容 M3 已写出文件）。

### 6.2 复用 M3 写入工具

`ink_writer/evidence_chain/writer.py` 已有的 writer 加 `write_planning_evidence_chain(...)` 方法，schema 同源。

---

## 7. 测试策略

| 层 | 范围 | 数量预估 |
|---|---|---|
| 单元 | 7 checker 各 ≥ 3 个 case（pass / borderline / fail）+ schema 解析 + thresholds 加载 + LLMClient mock | ~30 |
| 集成 | ink-init / ink-plan 端到端：mock LLM 返回固定分 → 验证 evidence_chain 写入 + dry-run 切换 + skip flag 生效 | 6-8 |
| e2e | 跑一本测试书 ink-init + ink-plan：4 + 3 checker 全跑通 + 产 planning_evidence_chain.json | 1 |

**全量 pytest 目标**：≥ 3700 passed（M3 baseline）+ ≥ 30 new passed / 0 failed / coverage **≥ 82%**。

---

## 8. 风险与护栏

| # | 风险 | 缓解 |
|---|---|---|
| 1 | 起点爬虫合规风险 | 简介公开数据 + robots.txt + UA 礼貌 + 1 req/s 限速 |
| 2 | LLM 起名词典覆盖不全 | dry-run 阶段发现新模板名加入词典持续扩充 |
| 3 | naming-style 误判（如"李明"）| `block_threshold` 设 0.70，容忍字根模式只 exact 阻断；dry-run 期可调 |
| 4 | 阻断 ink-init quick 流程让用户体验下降 | `--skip-planning-review` 紧急绕过（写 evidence_chain.warn） |
| 5 | 7 个 seed case 不够 dry-run 触发 | dry-run 后基于实际触发样本扩充 |
| 6 | ink-init / ink-plan SKILL.md 改动与 v23 现有流程冲突 | Step 99 加在末尾不改前 22/21 节；改动前 cat 全文确认 |
| 7 | M4 dry-run 计数器与 M3 混淆 | 独立 `data/.planning_dry_run_counter` |
| 8 | top200 爬虫单次跑失败需要重试 | checkpoint 续爬 + 失败重试 3 次 + 进度日志 |
| 9 | LLM 主观评分波动 | seed 固定 + temperature=0 + 同一 prompt 复用 M3 prompt 框架 |
| 10 | 7 个新 checker 调用量大（每次开新书 7 调用 + 重试）| glm-4.6 RPM 充足，预计每本书开 < 2 分钟跑完 |

---

## 9. user story 列表（14 US，全部 ralph 顺序执行）

| US | 标题 | 估时 | 依赖 |
|---|---|---|---|
| US-001 | M4 config 段加到 `config/checker-thresholds.yaml`（7 个 checker + planning_dry_run）| 5 min | M3 |
| US-002 | `planning_evidence_chain.json` schema 派生 + writer 扩展 + `EvidenceChainMissingError` 复用 | 8 min | M3 evidence_chain |
| US-003 | `genre-novelty-checker`（含 mock top200 fixture 测试）| 10 min | US-007 真数据后端 |
| US-004 | `golden-finger-spec-checker`（4 维度 LLM 主观）| 8 min | M3 |
| US-005 | `naming-style-checker`（exact + 字根模式 + LLM 扩充）| 10 min | US-008 真词典 |
| US-006 | `protagonist-motive-checker`（3 维度 LLM 主观）| 8 min | M3 |
| US-007 | 起点 top200 爬虫 + `data/market_intelligence/qidian_top200.jsonl` 实际产出 | 30 min | 独立 |
| US-008 | LLM 高频起名词典 ≈ 300 条 + `data/market_intelligence/llm_naming_blacklist.json` | 20 min | 独立 |
| US-009 | `golden-finger-timing-checker`（前 3 章 regex + LLM 双重）| 10 min | M3 |
| US-010 | `protagonist-agency-skeleton-checker`（卷骨架级）| 10 min | M3 |
| US-011 | `chapter-hook-density-checker`（卷骨架级）| 10 min | M3 |
| US-012 | ink-init / ink-plan SKILL.md 加 Step 99 策划审查 + `--skip-planning-review` flag + planning dry-run 计数器 + planning_dry_run_report.py | 20 min | US-001~011 |
| US-013 | 7 个上游 seed cases（CASE-2026-M4-0001~0007）+ `ink case approve --batch` 入活 | 15 min | M2 case_library |
| US-014 | M4 e2e 集成测试（6-8 用例）+ 跑一本测试书 ink-init + ink-plan 全链路验收 + tag `m4-p0-planning` + ROADMAP M4 ✅ + 更新 M-SESSION-HANDOFF.md §2/§3 + commit/push | 25 min | 全部 |

**总估时**：约 3 小时（与 M3 节奏一致；ralph 14 US fresh claude 各跑一轮）。

---

## 10. 验收

### 10.1 M4 验收清单（与 M3 同模式）

```bash
# (1) 全量 pytest 全绿 + 覆盖率 ≥ 82%
pytest -q

# (2) M4 全部模块导入成功
python3 -c "from ink_writer.planning_review import ink_init_review, ink_plan_review; \
            from ink_writer.checkers.genre_novelty import GenreNoveltyChecker; \
            from ink_writer.checkers.golden_finger_spec import GoldenFingerSpecChecker; \
            from ink_writer.checkers.naming_style import NamingStyleChecker; \
            from ink_writer.checkers.protagonist_motive import ProtagonistMotiveChecker; \
            from ink_writer.checkers.golden_finger_timing import GoldenFingerTimingChecker; \
            from ink_writer.checkers.protagonist_agency_skeleton import ProtagonistAgencySkeletonChecker; \
            from ink_writer.checkers.chapter_hook_density import ChapterHookDensityChecker; \
            print('M4 OK')"

# (3) load_thresholds 含 M4 7 段
python3 -c "from ink_writer.checker_pipeline.thresholds_loader import load_thresholds; \
            t = load_thresholds(); \
            assert all(k in t for k in ['genre_novelty','golden_finger_spec','naming_style', \
                                         'protagonist_motive','golden_finger_timing', \
                                         'protagonist_agency_skeleton','chapter_hook_density']); \
            print('thresholds OK')"

# (4) 7 个新 agent.md 存在
ls ink-writer/agents/{genre-novelty,golden-finger-spec,naming-style,protagonist-motive,\
golden-finger-timing,protagonist-agency-skeleton,chapter-hook-density}-checker.md

# (5) ink-init / ink-plan SKILL.md 集成
grep -c "Step 99" ink-writer/skills/ink-init/SKILL.md           # ≥ 1
grep -c "Step 99" ink-writer/skills/ink-plan/SKILL.md           # ≥ 1
grep -c "skip-planning-review" ink-writer/skills/ink-init/SKILL.md  # ≥ 1

# (6) 数据资产到位
test -f data/market_intelligence/qidian_top200.jsonl && wc -l data/market_intelligence/qidian_top200.jsonl   # 200
test -f data/market_intelligence/llm_naming_blacklist.json && python3 -c "import json; d=json.load(open('data/market_intelligence/llm_naming_blacklist.json')); assert len(d['exact_blacklist']) >= 250"

# (7) 7 个 seed case active
ls data/case_library/cases/CASE-2026-M4-*.yaml | wc -l           # ≥ 7
python3 -c "from ink_writer.case_library.store import CaseStore; s=CaseStore(); \
            assert sum(1 for c in s.iter_active() if c.id.startswith('CASE-2026-M4')) >= 7"

# (8) 跑一本测试书产 planning_evidence_chain.json
ink init quick --book demo-m4 ...  # 加 --skip-planning-review 是否生效
test -f data/demo-m4/planning_evidence_chain.json
python3 -c "import json; e=json.load(open('data/demo-m4/planning_evidence_chain.json')); \
            assert e['phase']=='planning'; assert len(e['checkers'])>=4"

# (9) git tag m4-p0-planning + push
git tag -l | grep m4-p0-planning
git ls-remote --tags origin | grep m4-p0-planning
```

### 10.2 ROADMAP / handoff 更新

- 更新 `docs/superpowers/M-ROADMAP.md` 进度跟踪表 M4 行 ⚪ → ✅
- 更新 `docs/superpowers/M-SESSION-HANDOFF.md` §2 进度快照 + §3 实际产出（按 M3 模式）
- 更新 memory `project_quality_overhaul_roadmap.md`

---

## 11. 故意延后的事（M5 / follow-up）

1. **M2 corpus_chunks 实跑**（origin spec §6 P2 完整）：换 LLM provider 重跑 ingest，可在 M5 完成后做（参考 `docs/superpowers/M2-FOLLOWUP-NOTES.md`）
2. **M4 dashboard 化**：M5 ink-dashboard 加 planning_evidence_chain.json 聚合可视化
3. **真实 ink-write 跑通 + dry-run 切真阻断**：M3 + M4 两条 dry-run 各跑 5 次后由用户判断切换
4. **chunk_borrowing 实际计算**：M2 chunks 补完后激活
5. **上游 cases 持续扩充**：dry-run 命中样本入库由用户审过 → batch approve（无独立产线）
6. **起点 top200 自动 refresh**：每 6 个月手动跑爬虫 refresh，无需 cron
