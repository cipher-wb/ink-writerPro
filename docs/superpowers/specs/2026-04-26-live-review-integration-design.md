# Live-Review 模块 — 174 份星河直播稿融入 ink-writer 创作链路 (Design Spec)

**Status**: ready-for-plan
**Date**: 2026-04-26
**Author**: cipher-wb（产品）+ brainstorming co-pilot
**Baseline**: master @ 43e5fe0（M1✅ + M2🟡 + M3✅ + M4⚪ + M5⚪ 5 周 roadmap 进行中；与 M2/M4 数据线并行不交叉）
**Target version**: v26.x（5 周 roadmap 之外的独立特性，可与 M5 并行落地）
**Quality target**: 174 份直播稿全量产出 → 三类产物（作品病例 / 题材接受度信号 / 新原子规则候选）→ 接入 init / write / review 三个阶段，使新书选材命中星河打分 ≥60 分签约线的概率显著提升
**Origin spec**: 无前置 spec，本次首次设计
**Brainstorm 记录**: 本次 6 题苏格拉底问答（C / B / A / D+B / B / B），见 §10 决策追溯

---

## 1. 背景与问题陈述

### 1.1 现状

ink-writer 项目已具备完整的"星河编辑写作建议" RAG 知识库 `editor-wisdom`：
- 数据源：288 份小红书 / 抖音"经验帖"（中位数 1099 字 / 篇）
- 产物：80+ 原子规则（`rules.json`）+ FAISS 向量索引 + 10 主题域归类 MD
- 接入：`context-agent` (Board 12) / `writer-agent` 硬约束段 / `ink-review` Step 3.5 硬门禁 / `polish-agent` 修复循环

同时项目已具备完整的病例驱动 rewrite 闭环（M3 P1 已交付）：
- `data/case_library/cases/`（410+ YAML 病例，schema `schemas/case_schema.json`）
- `writer_self_check` / `rule_compliance` / `rewrite_loop` 模块（最多 3 check + 2 polish）
- `_id_alloc.py` 锁式 ID 分配 + `evidence_chain` 证据落档

### 1.2 待解决的问题

用户在桌面 `~/Desktop/星河审稿/` 累积了 **174 份起点编辑星河 B 站直播录像字幕稿**（每份 3.5 小时，中位数 30000+ 字）。每份直播按以下结构进行：

> 主播逐封读取观众投稿邮件中的小说前三章 → 边读边犀利点评 → 给打分（满分 100，60+ 视为可签约）→ 写邮件回复作者。一天直播平均点评 10+ 篇小说。

抽样 2 份（`BV11YFEzkEVu` / `BV12yBoBAEEn`）确认数据中包含：
1. **明确的打分信号**："68 吧"、"70+ 现实"、"一眼签约"、"我知道我不能签约"
2. **逐条改稿建议**："3 分钟太长改 1 分钟"、"日本人物不会说真恶心"、"金手指要在第 3 章前显化"
3. **题材风险信号**："我很少签这种设定类的书啊"
4. **原作品片段引用**：可还原"哪本书 → 多少分 → 为什么"的完整因果链

### 1.3 与现有 `editor-wisdom` 的关系（已抽样比对）

| 维度 | editor-wisdom（已存）| live-review（本次新增）|
|---|---|---|
| 来源平台 | 小红书 + 抖音 | B 站直播录像 |
| 形态 | 编辑加工过的**经验帖** | 未加工的**逐稿口语点评** |
| 单份字数 | 中位数 1099 字 | 中位数 30000+ 字 |
| 抽取颗粒度 | **抽象规则**（"金手指要低成本高收益"）| **具体反例**（"脚臭设定不行" / "3 分钟→1 分钟"）|
| 含分数？ | ❌ | ✅ |
| 含原作品引用？ | ❌（自己的科普）| ✅ |
| 适合的产物 | rules.json（已做）| **作品病例 + 题材信号 + 新规则候选** |

→ 内容主题约 30-40% 重叠，但**形态完全不同 → 应作独立模块并列共存**，不替换不合并。

### 1.4 设计原则

1. **复用现有架构**：`case_library` schema / `_id_alloc.py` / `editor-wisdom` rules.json 召回链路 / `evidence_chain` 落档全复用
2. **与 editor-wisdom 并列不交叉**：本模块产出独立 domain；rules.json 增量回流时走"人工审核"门禁
3. **现有 410 份病例零影响**：扩 `case_schema.json` 仅追加**可选** `live_review_meta` block + bump `schema_version` 到 1.1，旧病例不动
4. **ralph 自主执行友好**：每个 US 自包含 + 验收条目机器可检验 + 失败可单点回滚 + 长任务拆分为"机制由 ralph 验证、跑批由人工触发"
5. **三阶段全链路接入**：init（题材选材辅助）/ write（规则回流后自动覆盖）/ review（新 checker 挂硬门禁）
6. **跑批可观测可重跑**：jsonl 增量 dump + `--resume` 断点续跑 + 失败可跳过已完成

---

## 2. 整体架构

### 2.1 数据流

```
174 份 BV*_raw.txt（~/Desktop/星河审稿/）
        │
        ▼
┌─────────────────────────────────────┐
│ Pipeline A: 切分管线 (LLM 主导)      │
│  ① 单文件冒烟 extract_one.py         │
│  ② 5 份小批 schema 验证             │
│  ③ 全量批跑 run_batch.py            │
│     - jsonl 增量 dump                │
│     - --resume 断点续跑              │
│     - 失败可跳过已完成               │
└─────────────────────────────────────┘
        │
        ▼ data/live-review/extracted/<bvid>.jsonl
        │
        ▼
┌─────────────────────────────────────┐
│ Pipeline B: 三类产物分发             │
└─────────────────────────────────────┘
   │            │              │
   ▼            ▼              ▼
① 作品病例   ② 题材接受度    ③ 新原子规则候选
                                 (人工审核闸)
   │            │              │
   ▼            ▼              ▼
data/case_   data/live-       data/editor-
library/     review/          wisdom/
cases/       genre_           rules.json
live_review/ acceptance.json  (回流增量)
CASE-LR-
2026-NNNN.yaml
   │            │              │
   ▼            ▼              ▼
┌────────────┐ ┌────────────┐ ┌─────────────┐
│ review     │ │ ink-init   │ │ writer-agent│
│ Step 3.5   │ │ 题材选材   │ │ context     │
│ 硬门禁     │ │ 检索+告警  │ │ 已注入(N/A) │
│ (新 checker│ │ (D+B 组合) │ │             │
│ live-      │ │            │ │             │
│ review-    │ │            │ │             │
│ checker)   │ │            │ │             │
└────────────┘ └────────────┘ └─────────────┘
```

### 2.2 组件清单

| 组件 | 路径 | 职责 |
|---|---|---|
| 切分管线 | `scripts/live-review/extract_one.py` | 单份直播稿 → jsonl，纯 LLM 切分 |
| 全量批跑 | `scripts/live-review/run_batch.py` | 调度 174 份，断点续跑、失败跳过 |
| 病例转换器 | `scripts/live-review/jsonl_to_cases.py` | jsonl → `CASE-LR-*.yaml` |
| 题材聚合器 | `scripts/live-review/aggregate_genre.py` | jsonl → `genre_acceptance.json` |
| 规则候选器 | `scripts/live-review/extract_rule_candidates.py` | jsonl → `rule_candidates.json` 待人工审核 |
| 题材检索器 | `ink_writer/live_review/genre_retrieval.py` | 题材关键词 → Top-K 案例 + 通病 |
| init 注入 | `ink_writer/live_review/init_injection.py` | 用户题材输入 → 检索结果 + 阈值告警 UI |
| review checker | `ink-writer/agents/live-review-checker.md` | 章节文本 → 命中 `live_review` domain 病例阻断分 |
| 新 schema | `schemas/live_review_extracted.schema.json` + `schemas/live_review_genre_acceptance.schema.json` | jsonl 与聚合产物校验 |
| schema 扩展 | `schemas/case_schema.json`（schema_version 1.0 → 1.1）| 追加 `live_review_meta` 可选 block |
| 配置 | `config/live-review.yaml` | 总开关 / 阈值 / model / 注入开关 |

### 2.3 与已有资产的关系

| 已有资产 | 本模块中的角色 | 改不改 |
|---|---|---|
| `data/case_library/cases/` | 新病例存到子目录 `live_review/`，复用 `_id_alloc.py` 但 prefix `CASE-LR-` | 加目录不动结构 |
| `schemas/case_schema.json` | 追加可选 `live_review_meta`，bump schema_version 1.0 → 1.1 | 兼容性扩展 |
| `data/editor-wisdom/rules.json` | 新规则候选**经人工审核后**追加，源标记 `source: live_review` | 增量追加不删 |
| `ink-writer/agents/`（33 个 checker）| 新增第 34 个 `live-review-checker.md` | 加文件不动现有 |
| `ink-review` Step 3.5 硬门禁 | 新 checker 与现有 `editor-wisdom-checker` **并列** | 加并列不替换 |
| `ink-init` 流程 | 在题材确定阶段插入 `init_injection.py` 调用（D+B 组合）| 加 hook 不动现有 |
| `_id_alloc.py` | 复用 `allocate_case_id(prefix="CASE-LR-")`，现有按 prefix 分 counter file (`.id_alloc_{sanitized}.cnt`) 自动隔离 | 不动 helper，零新增 |

---

## 3. 数据 Schema

### 3.1 切分管线中间产物（jsonl，每文件一行 = 一本被点评小说）

文件位置：`data/live-review/extracted/<bvid>.jsonl`

JSON Schema：`schemas/live_review_extracted.schema.json`（新建）

```jsonc
{
  "$schema_version": "1.0",
  "bvid": "BV12yBoBAEEn",            // 必填，B 站视频 ID（从文件名 BV*_raw.txt 正则提取，pattern: r"^(BV[\w]+)_raw\.txt$"）
  "source_path": "/abs/path/to/raw.txt", // 必填
  "source_line_total": 3245,         // 必填，原稿总行数
  "extracted_at": "2026-04-27T10:30:00Z", // 必填，ISO8601
  "model": "claude-sonnet-4-6",      // 必填
  "extractor_version": "1.0.0",      // 必填，便于回溯
  "novel_idx": 3,                    // 必填，本份直播稿中第几本被点评的（0-based）
  "line_start": 105,                 // 必填，原稿中本本小说点评起始行
  "line_end": 192,                   // 必填，结束行（含）
  "title_guess": "都市重生律师文",     // 必填，LLM 推断的标题/简介
  "title_confidence": 0.7,           // 必填，0-1
  "genre_guess": ["都市", "重生", "职业流"], // 必填，多标签数组
  "score": 68,                       // 可空（unknown 时 null）
  "score_raw": "68 吧是吧",           // 必填（raw quote of the score utterance）
  "score_signal": "explicit_number", // 枚举: explicit_number | sign_phrase | fuzzy | unknown
  "verdict": "borderline",           // 枚举: pass(>=60) | fail(<60) | borderline(55-65) | unknown
  "overall_comment": "...",          // 必填，1-3 句话总评
  "comments": [                      // 必填，数组（可空）
    {
      "dimension": "节奏",            // 必填，10 主题域之一（与 editor-wisdom 对齐：opening/hook/character/pacing/highpoint/golden_finger/taboo/genre/ops/simplicity/misc）
      "severity": "negative",         // 枚举: negative | positive | neutral
      "content": "开篇 800 字铺设定，应该 200 字内见冲突",
      "raw_quote": "我觉得好拖沓这点 我觉得拖沓兄弟 就是读着不爱看你这个设定",
      "raw_line_range": [110, 117]    // 在原稿中的行范围
    }
  ]
}
```

### 3.2 case_schema.json 扩展（schema_version 1.0 → 1.1）

仅追加可选 block，不修改任何现有字段：

```yaml
# 现有字段不变...
case_id: CASE-LR-2026-0001
title: ...
status: active
severity: P2  # 由 score 推导：score<55→P0, 55-60→P1, 60-65→P2, >65→P3
domain: live_review  # 新 domain 值
layer:
  - planning  # 多数为 planning（题材/选材问题）
  - golden_three  # 也常 golden_three（黄金三章）
tags: [...]
scope: {...}
source:
  type: live_review_extraction  # 新 type 值
  raw_text: ...
  ingested_at: '2026-04-27'
  reviewer: claude-sonnet-4-6
  ingested_from: data/live-review/extracted/<bvid>.jsonl
failure_pattern:
  description: ...
  observable: [...]
bound_assets:
  checkers:
    - checker_id: live-review-checker
      version: v1
      created_for_this_case: false  # 该 checker 服务全部 live_review domain
resolution: {...}
evidence_links: []

# === 新增可选 block ===
live_review_meta:
  source_bvid: BV12yBoBAEEn
  source_line_range: [105, 192]
  score: 68
  score_raw: "68 吧是吧"
  score_signal: explicit_number
  verdict: borderline
  title_guess: 都市重生律师文
  genre_guess: [都市, 重生, 职业流]
  overall_comment: ...
  comments:
    - dimension: 节奏
      severity: negative
      content: ...
      raw_quote: ...
```

### 3.3 题材接受度信号

文件位置：`data/live-review/genre_acceptance.json`

JSON Schema：`schemas/live_review_genre_acceptance.schema.json`（新建）

```jsonc
{
  "$schema_version": "1.0",
  "updated_at": "2026-04-27T10:30:00Z",
  "total_novels_analyzed": 1734,    // 174 份 × 平均 10 本 估算
  "min_cases_per_genre": 3,          // 低于此值的不计入聚合
  "genres": {
    "都市/重生/职业流": {
      "case_count": 12,
      "score_mean": 65.4,
      "score_median": 68,
      "score_p25": 55,
      "score_p75": 72,
      "verdict_pass_rate": 0.58,     // verdict in {pass} 的占比
      "common_complaints": [          // top-N 高频差评维度
        {"dimension": "节奏", "frequency": 0.7, "examples": ["开头拖沓", "金手指来得太晚"]},
        {"dimension": "金手指", "frequency": 0.5, "examples": ["..."]}
      ],
      "case_ids": ["CASE-LR-2026-0001", "CASE-LR-2026-0017", "..."]
    },
    "校园/双女主": {
      "case_count": 5,
      "score_mean": 42.0,
      "verdict_pass_rate": 0.0,
      "common_complaints": [...],
      "case_ids": [...]
    }
  }
}
```

---

## 4. 三大阶段接入方式

### 4.1 init 阶段：题材选材辅助（D + B 组合）

**入口**：`ink-init` 在用户敲定题材关键词后调用 `init_injection.py:check_genre`。

**D（反向检索式辅助）— 主路径**：

```
用户输入: "我想写都市重生当律师"
        │
        ▼
[语义检索 genre_retrieval.py]
  embed("都市重生律师") + cosine search over CASE-LR-*.yaml.live_review_meta.title_guess
        │
        ▼
返回 Top-3 相似案例 + 该题材聚合 (genre_acceptance.json)
        │
        ▼
init UI 输出:
  📚 星河直播相似案例（174 份直播 × 10+ 本/份）：
    ① 《都市重生当律师》65 分 — 节奏不错但金手指出现太晚（BV12yBoBAEEn）
    ② 《重生律师事务所》52 分 — 设定杂糅、主角动机模糊
    ③ 《回到 86 年当律师》72 分 — 开头钩子强、人物立体
  🎯 该题材统计：均分 65.4 / 签约率 58% / 主要差评：节奏(70%) 金手指(50%)
  💡 写作建议：开头 800 字内见冲突；金手指第 3 章前显化
```

**B（阈值告警 + 二次确认）— 兜底**：

```
若 genre_acceptance.json 中匹配 genre 的 score_mean < init_genre_warning_threshold(默认 60)
        │
        ▼
init UI 追加:
  ⚠️ 风险提示：星河直播该题材均分 42 / 签约率 0%
  主要差评：禁忌内容(80%)、人设崩塌(60%)
  
  是否继续？(y/n)
        │
        ▼
y → 写 evidence_chain.warn(genre_low_acceptance)，通行
n → 返回题材选择步骤
```

**未匹配时**（用户题材在 174 份里没出现过）：
```
init UI 输出:
  ℹ️ 该题材在星河 174 份直播中未出现样本，无历史接受度数据。
  建议：从星河偏好题材 Top 10 中选择类似方向（系统流 / 无敌流 / 穿越权谋）
  Top 10 列表来自 genre_acceptance.json verdict_pass_rate Top 10
        │
        ▼
（不阻断，仅提示）
```

### 4.2 write 阶段：间接生效（无新增直接接入点）

write 阶段**不**新增 hook 点。本模块对 write 阶段的影响通过两条**间接路径**生效：

**路径 A — 规则回流（覆盖 write/polish 阶段）**：US-LR-009 实现的 `extract_rule_candidates.py` 产出 `rule_candidates.json`，经 US-LR-010 人工审核后由 `promote_approved_rules.py` 追加到 `data/editor-wisdom/rules.json` 时打标 `source: live_review`。editor-wisdom 模块的 `retriever.py` / `writer_injection.py` / `polish_injection.py` 一行不改，rules.json 变更后向量索引重建即自动生效。

**路径 B — 病例驱动 polish（覆盖 review→polish 循环）**：US-LR-012 的 live-review-checker 在 review 阶段命中 violations 时，通过现有 polish-agent 修复链路反向影响章节文本。

**人工审核闸**（路径 A）：
- `rule_candidates.json` 跟 `rules.json` 用同一个 schema（`schemas/editor-rules.schema.json`）但放独立文件
- 审核工具：`scripts/live-review/review_rule_candidates.py`（CLI 列表 → 标记 `approved: true/false` → 仅 approved 写入 rules.json）
- 去重：审核前自动跑 cosine similarity > 0.85 与现有 80+ 规则比对，标 `dup_with: [EW-XXXX]`

### 4.3 review 阶段：live-review-checker 硬门禁

**新 checker**：`ink-writer/agents/live-review-checker.md`

**输入**：当前章节文本 + 题材标签 + 章节序号
**召回**：从 `data/case_library/cases/live_review/` 中召回 Top-K 病例（按题材语义相似度）
**评分**：对每个 dimension 给 0-1 分，综合分数 ∈ [0, 1]
**门禁**：
- `hard_gate_threshold: 0.65`（对应 65 分，比签约线 60 高一档作 buffer）
- `golden_three_threshold: 0.75`（黄金三章更严）
**触发后**：写 `evidence_chain.violations[*]` + 触发现有 polish 循环（最多 2 次）

**与 editor-wisdom-checker 的关系**：**并列**，两 checker 都不通过才阻断；任一通过即放行。配置 `inject_into.review: true` 可关。

---

## 5. User Stories 拆分（共 14 条，按 priority 排序）

### P0 — Schema 与基础设施（必须最先，后续 US 全依赖）

#### US-LR-001: schema 定义 + case_schema.json 扩展 + 向后兼容测试
- 新建 `schemas/live_review_extracted.schema.json`、`schemas/live_review_genre_acceptance.schema.json`
- 扩展 `schemas/case_schema.json`：bump `$schema_version` 1.0 → 1.1，追加可选 `live_review_meta` block
- 新建 `tests/case_library/test_schema_backward_compat.py`：遍历 `data/case_library/cases/*.yaml`（410+ 份），断言全部仍能用 schema_version 1.1 解析通过
- 新建 `tests/live_review/test_schema_validation.py`：用 fixture jsonl 验证新 schema 接受合法 / 拒绝缺字段

#### US-LR-002: live_review ID 分配器封装 + 配置文件
- **不**新建独立分配器：复用 `ink_writer/case_library/_id_alloc.py:allocate_case_id(cases_dir, prefix="CASE-LR-")`，现有实现按 prefix 分 counter file（`.id_alloc_{sanitized}.cnt`）天然隔离 `CASE-` 与 `CASE-LR-`
- 新建 `ink_writer/live_review/__init__.py`（空 module 占位）
- 新建 `ink_writer/live_review/case_id.py:allocate_live_review_id(cases_dir: Path) -> str` 作为薄封装：调用 `allocate_case_id(cases_dir, prefix="CASE-LR-")`；目的是让消费方（jsonl_to_cases.py）有明确语义 API
- 新建 `config/live-review.yaml`：enabled / model / extractor_version / hard_gate_threshold / golden_three_threshold / init_genre_warning_threshold / init_top_k / min_cases_per_genre / batch（input_dir / output_dir / resume_from_jsonl / skip_failed / log_progress）/ inject_into.{init, review} 全部字段（与 §8 配置示例一字不差）
- 新建 `tests/live_review/test_case_id.py`：4 worker spawn 并发分配 `CASE-LR-`，断言序列严格 `CASE-LR-2026-0001..0004` 无空洞；同进程交替分配 `CASE-` 与 `CASE-LR-` 两 prefix 各自单调递增不串号
- 新建 `tests/live_review/test_config.py`：用 fixture yaml 验证默认值加载、字段缺省 fallback、enabled=false 时所有 inject_into 强制 false

### P1 — 切分管线

#### US-LR-003: LLM 切分 prompt 设计 + mock 单元测试
- 新建 `scripts/live-review/prompts/extract_v1.txt`：含 schema 描述 + 5 个 few-shot 例子（标题识别 / 打分识别 / 维度归类 / 边界识别 / 模糊场景）
- 新建 `ink_writer/live_review/extractor.py:extract_from_text(raw_text, model) -> List[ExtractedNovel]`
- 新建 `tests/live_review/test_extractor_mock.py`：用 fixture LLM 返回固定 JSON，断言 parse / schema 校验 / 错误处理（LLM 返回非法 JSON / 缺字段 / score 超 0-100）三类异常被 fail-loud

#### US-LR-004: 单文件冒烟脚本 extract_one.py
- 新建 `scripts/live-review/extract_one.py`：参数 `--bvid <id>` / `--input <raw.txt>` / `--model <name>` / `--out <path>` / `--mock-llm <fixture.json>`（测试用）
- 输出 `data/live-review/extracted/<bvid>.jsonl`（每行一本小说）
- 注入点：脚本内部的 LLM 调用走 `ink_writer/live_review/extractor.py:extract_from_text`，该函数支持 `mock_response: dict | None = None` 参数让测试旁路真 LLM
- **ralph 验收（全部 mock，不烧 API key）**：
  - 新建 `tests/live_review/fixtures/raw_BV12yBoBAEEn.txt`（截取真实直播稿前 200 行 + 后 200 行做 fixture）+ `tests/live_review/fixtures/mock_extract_BV12yBoBAEEn.json`（手工编写 3 本小说的预期输出，含 score 68 / 不能签约 / 一眼签约 三类 score_signal）
  - 新建 `tests/live_review/test_extract_one_smoke.py`：用 `--mock-llm fixture.json` 跑 extract_one.py 全流程，断言 (1) 生成 jsonl 文件 (2) 行数 == 3 (3) 全部用新 schema 校验通过 (4) score_signal 分布含 explicit_number / sign_phrase / fuzzy 三类
  - `python3 -m pytest tests/live_review/test_extract_one_smoke.py --no-cov -q` 全过
  - `ruff check scripts/live-review/extract_one.py ink_writer/live_review/extractor.py` 无新增错误
- **用户后续手动触发实跑**（§12 §M-1）：拿真实 LLM key 跑 1 份 BV12yBoBAEEn 真实数据，人工抽检 jsonl 合理性

#### US-LR-005: 多份模式 + schema 一致性验证脚本
- 修改 `scripts/live-review/extract_one.py` 支持 `--bvids <id1,id2,...>` 多份模式（也可独立成 `extract_many.py`，作者酌情）
- 新建 `scripts/live-review/validate_jsonl_batch.py`：扫 `--jsonl-dir`，对每个 jsonl 跑 schema 校验 + 统计 (novel_count, score_signal 分布, score 非空比例)，输出报告 `reports/live-review-validation-<timestamp>.md`，失败时退出码非 0 + stderr 列哪份/哪行/哪字段
- **ralph 验收（全部 mock）**：
  - 新建 `tests/live_review/fixtures/mock_extract_5_files/` 含 5 份 fixture mock_extract_*.json（手编，覆盖：含明确打分 / 含模糊打分 / 含 unknown / 含极少小说(2 本) / 含极多小说(15 本)）
  - 新建 `tests/live_review/test_extract_many.py` 用 mock 5 份跑通，断言每份 jsonl 出现、schema 全过、validate_jsonl_batch.py 退出码 0
  - 新建 `tests/live_review/test_validate_jsonl_batch.py`：覆盖 (a) 正常 5 份 → 退出 0 (b) 故意 1 份 score 字段非数值 → 退出非 0 + stderr 含 bvid + 行号 + 字段名
  - `python3 -m pytest tests/live_review/ --no-cov -q` 全过；`ruff check scripts/live-review/ ink_writer/live_review/` 无新增错误
- **用户后续手动触发**（§12 §M-2）：用真实 5 个 BV 真实跑（实际烧钱 ≈ $0.5），人工 review `reports/live-review-validation-*.md` 看 score_signal 分布是否合理（`explicit_number` 占比期望 ≥ 30%）

#### US-LR-006: 全量批跑脚本 run_batch.py（仅验证机制，不实跑 174 份）
- 新建 `scripts/live-review/run_batch.py`：参数 `--input-dir` / `--output-dir` / `--limit N` / `--resume` / `--skip-failed` / `--mock-llm-dir <fixture_dir>`（测试用，每个 BV 对应 `<fixture_dir>/<bvid>.json`）
- 实现：
  - 扫描 `--input-dir` 下所有 `BV*_raw.txt` → 列表
  - 检查 `--output-dir` 下哪些 `<bvid>.jsonl` 已存在 → 跳过（`--resume`）
  - 失败时写 `data/live-review/extracted/_failed.jsonl`（含 bvid / error / traceback），继续下一个
  - 跑批进度日志：每完成 1 份 print `[N/total] <bvid> done in Xs`
  - 退出码：全部成功 → 0；部分失败但 `--skip-failed` → 0；非 `--skip-failed` 且有失败 → 1
- **ralph 验收（全部 mock）**：
  - 新建 `tests/live_review/fixtures/mock_batch/` 下 5 个 fixture txt + 4 个 mock json（故意第 3 个无对应 mock json）
  - 新建 `tests/live_review/test_run_batch.py`：(a) 5 文件全 mock 齐 → 5 个 jsonl 生成、_failed.jsonl 不存在、退出码 0 (b) 1 文件无 mock → `--skip-failed` 模式下 4 成功、_failed.jsonl 含 1 条、退出码 0；非 `--skip-failed` 模式 → 退出码 1 (c) `--resume` 模式：先跑 3 个、再跑 5 个 → 第二次只增量处理 2 个新的 (d) `--limit 2` 模式：只处理前 2 个
  - `python3 -m pytest tests/live_review/test_run_batch.py --no-cov -q` 全过
  - `ruff check scripts/live-review/run_batch.py` 无新增错误
- **用户后续手动触发**（§12 §M-3）：用真实 LLM key 一行命令跑全量 174 份（`python3 scripts/live-review/run_batch.py --input-dir ~/Desktop/星河审稿 --output-dir data/live-review/extracted --resume --skip-failed`，预计 1-3h、$15-25 Sonnet 估算）

### P2 — 三类产物分发

#### US-LR-007: jsonl → CASE-LR-*.yaml 转换器
- 新建 `scripts/live-review/jsonl_to_cases.py`：参数 `--jsonl-dir` / `--cases-dir` / `--dry-run`
- 转换逻辑：
  - 每行 jsonl → 一个 yaml 病例
  - severity 推导：`score<55→P0, 55-60→P1, 60-65→P2, >65→P3, score==null→P3`
  - title 字段：`{title_guess}（{verdict} / {score}分）`
  - layer：根据 `comments[*].dimension` 推导（**完整规则表**）：
    - 含 `opening` 或 `hook` 或 `golden_finger` 任一 → `[planning, golden_three]`
    - 含 `genre` 或 `taboo` → `[planning]`
    - 含 `pacing` 或 `highpoint` → `[planning, chapter]`
    - 含 `character` → `[planning, character]`
    - 含 `simplicity` → `[chapter]`（直白度问题章节级处理）
    - 默认（仅 `ops` 或 `misc`）→ `[planning]`
    - 多个 dimension 命中多 layer 时取并集去重
  - failure_pattern.description：拼 `overall_comment` + 高 severity comments
  - bound_assets.checkers：固定 `[live-review-checker:v1:false]`
  - source.ingested_from：jsonl 路径
- **ralph 验收（fixture jsonl，无 LLM 调用）**：
  - 新建 `tests/live_review/fixtures/sample_5_files.jsonl`（手编 5 份 jsonl，每份 3-5 本小说，覆盖各 dimension / severity P0-P3 全部分支）
  - 新建 `tests/live_review/test_jsonl_to_cases.py`：跑 jsonl_to_cases.py 后断言 (1) yaml 数量 == jsonl 总行数 (2) 全部用 schema_version 1.1 校验通过 (3) case_id 严格递增（CASE-LR-2026-0001..N）(4) 同 bvid 多本不冲突 (5) severity 推导正确（含全部 5 类 P0/P1/P2/P3+null）(6) layer 推导覆盖完整规则表全部分支
  - `python3 -m pytest tests/live_review/test_jsonl_to_cases.py --no-cov -q` 全过；现有 `tests/case_library/` 不修改即通过（无回归）
  - `ruff check scripts/live-review/jsonl_to_cases.py` 无新增错误

#### US-LR-008: 题材聚合器 aggregate_genre.py
- 新建 `scripts/live-review/aggregate_genre.py`：扫所有 `CASE-LR-*.yaml` → 聚合到 `genre_acceptance.json`
- 聚合规则：
  - `genre` key：取 `live_review_meta.genre_guess` 多标签的**笛卡尔积单标签**（即一本书 [都市,重生] 算两次）
  - `min_cases_per_genre: 3` 以下不写入
  - 统计：mean / median / p25 / p75 / pass_rate
  - common_complaints：dimension frequency Top-N（N 默认 5）
- **ralph 验收（fixture yaml，无 LLM）**：
  - 新建 `tests/live_review/fixtures/sample_30_cases/CASE-LR-2026-NNNN.yaml`（手编 30 份，覆盖 5+ genre × 不同分布以验证统计：含至少 1 个 case_count<3 的 genre（不应入聚合）+ 1 个 score 全 null 的 genre + 1 个 verdict 全 fail 的 genre）
  - 新建 `tests/live_review/test_aggregate_genre.py`：跑 aggregate_genre.py 后断言 (1) 输出用 `schemas/live_review_genre_acceptance.schema.json` 校验通过 (2) 各题材 mean/median/p25/p75/pass_rate 与手算一致（误差 < 0.01）(3) case_count<3 的 genre 不出现 (4) common_complaints 频率排序正确
  - `python3 -m pytest tests/live_review/test_aggregate_genre.py --no-cov -q` 全过
  - `ruff check scripts/live-review/aggregate_genre.py` 无新增错误

#### US-LR-009: 规则候选抽取器 extract_rule_candidates.py
- 新建 `scripts/live-review/extract_rule_candidates.py`：扫所有 jsonl → 用 LLM 提取**通用规则**（剥离作品语境的抽象建议）
- 输出 `data/live-review/rule_candidates.json`（schema 用 `schemas/editor-rules.schema.json`，但额外加 `dup_with: [EW-XXXX]?` / `approved: bool? = null` / `source_bvids: [string]`）
- 自动去重：cosine similarity > 0.85 与现有 `data/editor-wisdom/rules.json` 比对，标 `dup_with`
- 不自动写入 rules.json，等人工审核
- **ralph 验收（mock LLM extract，无真 API 调用）**：
  - 复用 US-LR-007 fixture jsonl + 新建 `tests/live_review/fixtures/mock_rule_extract.json`（mock LLM 返回 5 条候选规则，其中 2 条故意与现有 rules.json 中前 2 条规则语义相近以触发 dup_with）
  - 新建 `tests/live_review/test_extract_rule_candidates.py`：跑脚本后断言 (1) 输出 5 条候选 (2) 至少 2 条 dup_with 字段非空 (3) source_bvids 字段正确填充 (4) 用 `schemas/editor-rules.schema.json` 校验通过（含扩展字段）(5) approved 字段全部为 null
  - `python3 -m pytest tests/live_review/test_extract_rule_candidates.py --no-cov -q` 全过
  - `ruff check scripts/live-review/extract_rule_candidates.py` 无新增错误
- **用户后续手动触发**（§12 §M-6）：用真实 LLM key 跑全量 jsonl 抽规则候选（一次跑批，预计 < 10 分钟、$1-3 估算）

#### US-LR-010: 规则候选审核 CLI（人工闸）
- 新建 `scripts/live-review/review_rule_candidates.py`：交互式 CLI，逐条展示候选 + dup_with → 用户输 `y/n/s(skip)/q` → 写回 candidates 文件 `approved: true/false`
- 提交工具 `scripts/live-review/promote_approved_rules.py`：把 `approved: true` 的规则**追加**到 `rules.json`（生成新 `EW-NNNN` ID，prefix 不变；元数据加 `source: live_review` / `source_bvids`）
- **ralph 验收（fixture，无 LLM）**：
  - 新建 `tests/live_review/fixtures/sample_rule_candidates.json`（5 条候选：3 标 `approved: true` / 2 标 `approved: false`；其中 2 条 dup_with 命中 EW-0001 / EW-0002）
  - 新建 `tests/live_review/test_review_rule_candidates.py`：用 stdin pipe 模拟用户输入 `y\nn\ny\ns\ny\n`，断言交互后 candidates 文件 approved 字段写回正确
  - 新建 `tests/live_review/test_promote_approved_rules.py`：(1) 在 tmp_path 复制现存 rules.json fixture (含 EW-0001..EW-0080) → 跑 promote → 断言只有 3 条 approved 的写入 / ID 严格递增到 EW-0083 / 现有 80 条 EW 全部内容字节级不变 / 新规则 source 字段值为 `live_review` / source_bvids 字段非空
  - `python3 -m pytest tests/live_review/test_review_rule_candidates.py tests/live_review/test_promote_approved_rules.py --no-cov -q` 全过
  - `ruff check scripts/live-review/review_rule_candidates.py scripts/live-review/promote_approved_rules.py` 无新增错误
- **用户后续手动触发**（§12 §M-7）：跑 review_rule_candidates.py 人工逐条审核 → 跑 promote_approved_rules.py 提交审核通过的规则 → 跑现有 `ink editor-wisdom rebuild` 重建向量索引（仅步骤 06）

### P3 — 三阶段接入

#### US-LR-011: 题材语义检索器 + init 注入
- 新建 `ink_writer/live_review/genre_retrieval.py:retrieve_similar_cases(query, top_k=3) -> List[CaseSummary]`：用现有 `editor-wisdom` 同款 BAAI/bge-small-zh-v1.5 模型 + FAISS 索引（独立索引文件 `data/live-review/vector_index/`），底层基于 case yaml 的 `live_review_meta.title_guess + overall_comment`
- 新建 `ink_writer/live_review/init_injection.py:check_genre(user_genre_input) -> dict`：先 retrieve、再查 `genre_acceptance.json`、组装 D+B 组合 UI 输出（dict，含 `similar_cases` / `genre_stats` / `warning_level: ok|warn|block` / `suggested_actions`）
- 索引构建脚本 `scripts/live-review/build_vector_index.py`
- 修改 `ink-writer/skills/ink-init/SKILL.md`：Step 99 后加 `Step 99.5 — live-review 题材审查`，调用 `init_injection.check_genre`，UI 渲染（终端 ASCII 输出，与现有 ink-init 风格对齐）
- **ralph 验收（fixture yaml，向量索引允许真模型加载——bge 模型本地运行无 API 费用）**：
  - 复用 US-LR-008 fixture sample_30_cases + 复用其聚合后的 fixture genre_acceptance.json
  - 新建 `tests/live_review/test_genre_retrieval.py`：用 fixture 跑 build_vector_index → retrieve_similar_cases，断言：(a) query "都市重生律师" 返回 Top-3 相似案例（其中预期含特定 fixture case_id）(b) cosine 排序单调递减
  - 新建 `tests/live_review/test_init_injection.py`：5 个 query 覆盖（已覆盖 / 未覆盖 / 低分预警 / 中分常规 / 极端高分）→ 断言 warning_level 分别为 ok/ok/warn/ok/ok 且各字段结构正确
  - 新建 `tests/live_review/test_skill_step_99_5.py`：模拟 ink-init 调用 init_injection.check_genre 输入 fixture，断言返回 dict 结构与 SKILL.md 描述对齐（含 similar_cases 数组 / genre_stats dict / warning_level 枚举 / suggested_actions 字符串列表）
  - `python3 -m pytest tests/live_review/test_genre_retrieval.py tests/live_review/test_init_injection.py tests/live_review/test_skill_step_99_5.py --no-cov -q` 全过
  - `ruff check ink_writer/live_review/genre_retrieval.py ink_writer/live_review/init_injection.py scripts/live-review/build_vector_index.py` 无新增错误
- **用户后续手动触发**（§12 §M-8）：跑全量 case yaml 后跑一次 `python3 scripts/live-review/build_vector_index.py` 重建索引

#### US-LR-012: live-review-checker agent + ink-review 集成
- 新建 `ink-writer/agents/live-review-checker.md`：spec 文件，schema 与现有 33 个 checker 对齐（`{{PROMPT_TEMPLATE:checker-input-rules.md}}` 引用 / 输出 `{score, dimensions, violations, cases_hit}`）
- 新建 `ink_writer/live_review/checker.py`：实现 retriever（按章节文本 cosine 召回 Top-K live_review 病例）+ LLM 评分（每 dimension 0-1）
- 修改 `ink-writer/skills/ink-review/SKILL.md`：Step 3.5 后追加 `Step 3.6 — live-review 硬门禁`（与现有 editor-wisdom Step 3.5 **并列**，不替换）
- 阻断逻辑：score < hard_gate_threshold(0.65) → 写 violations + 触发现有 polish-agent 修复循环
- 配合 `config/live-review.yaml:inject_into.review: true` 控制总开关
- **ralph 验收（mock LLM checker，bge 索引真跑）**：
  - 新建 `tests/live_review/fixtures/sample_chapter_violating.txt`（手编 800 字章节，故意触发已知 fixture cases 的多条违规如开头铺设定 / 主角动机模糊 / 金手指出场太晚）+ `tests/live_review/fixtures/mock_live_review_checker_response.json`（mock LLM 返回 score 0.45 + violations 3 条）
  - 新建 `tests/live_review/test_checker.py`：(a) 用 mock 跑 checker → 断言返回结构 {score, dimensions, violations, cases_hit} (b) score 0.45 < hard_gate 0.65 → review_gate 应阻断
  - 新建 `tests/live_review/test_review_step_3_6.py`：mock LLM checker + mock polish-agent，跑 ink-review Step 3.6 → 断言：(1) live-review-checker 被调用 (2) violations 写入 evidence_chain (3) polish 循环触发 (4) 配 `inject_into.review: false` 时 Step 3.6 完全短路（不调用 checker）
  - `python3 -m pytest tests/live_review/test_checker.py tests/live_review/test_review_step_3_6.py --no-cov -q` 全过
  - 现有 `tests/` 目录所有测试不修改即通过（无回归）
  - `ruff check ink_writer/live_review/checker.py ink-writer/agents/live-review-checker.md` 无新增错误（注意 .md 文件不需 ruff，仅检查 .py）

### P4 — 端到端验证 + 文档

#### US-LR-013: 端到端冒烟脚本（不依赖真实 API）
- 新建 `scripts/live-review/smoke_test.py`：
  - 检查 vector_index 是否存在，缺则重建（用 fixture cases）
  - 跑 fixture init query → 断言 D+B 组合 UI 输出符合预期
  - 跑 fixture 章节文本 → 断言 review 阶段 live-review-checker 被调用、违反时阻断
- 输出 `reports/live-review-smoke-report.md`，含每步耗时 + 检查结果
- 默认全部走 mock LLM；带 `--with-api` flag 时走真 LLM（需 ANTHROPIC_API_KEY）
- **ralph 验收（mock 模式）**：
  - 跑 `python3 scripts/live-review/smoke_test.py`（不带 --with-api）→ 退出码 0 + `reports/live-review-smoke-report.md` 存在 + 报告中所有 check item 标 PASS
  - 新建 `tests/live_review/test_smoke.py`：runs `smoke_test.py` via subprocess, 断言退出码 0 + 报告生成
  - `python3 -m pytest tests/live_review/test_smoke.py --no-cov -q` 全过
  - `ruff check scripts/live-review/smoke_test.py` 无新增错误
- **用户后续手动触发**（§12 §M-9）：跑 `python3 scripts/live-review/smoke_test.py --with-api` 端到端跑真 LLM 一次（验证 mock 与真实输出形态一致）

#### US-LR-014: 用户文档 docs/live-review-integration.md
- 写 `docs/live-review-integration.md`，结构对齐 `docs/editor-wisdom-integration.md`：架构 mermaid / 数据流 / 主题域 / 如何添加新数据 / 如何调阈值 / FAQ / smoke test / **§"用户手动操作清单"完整列出 §M-1..§M-9 步骤命令与预期产物**
- 在 `CLAUDE.md` 顶部"编辑智慧模块"段后追加 1 段说明 live-review 模块的存在 + 链接（结构对称）
- **ralph 验收**：
  - 文件存在性：`test -f docs/live-review-integration.md`
  - mermaid 块语法合法（用 `python3 -c "import re; assert all(...) for block in re.findall(r'```mermaid(.*?)```', open('docs/live-review-integration.md').read(), re.S)"` 或调用 `mmdc --validate-only` 若可用）
  - 内部链接：`python3 scripts/live-review/check_links.py docs/live-review-integration.md`（新建简单 link 检查脚本，扫 `[text](path)` 中相对路径全部存在）
  - CLAUDE.md 含 "live-review" 字符串：`grep -q live-review CLAUDE.md`
  - 新建 `tests/live_review/test_docs.py` 把上面 4 项断言包成 pytest case

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 切分错切（边界识别失败） | 整本病例错位 | US-LR-004 单文件冒烟人工抽查 + US-LR-005 5 份小批 schema 校验 + jsonl 完整保留可重跑 |
| LLM 返回非法 JSON | 管线中断 | extractor 内 fail-loud（不 silent fallback），`run_batch.py` 失败跳过 + 写 `_failed.jsonl` |
| schema 演化破坏现有 410 份病例 | 现有 rewrite_loop 全炸 | US-LR-001 强制向后兼容测试（遍历全部 410 份） + 新字段全 optional |
| 新规则与现有 80+ 重叠 | rules.json 噪声增加、召回质量下降 | US-LR-009 自动 cosine 去重 + US-LR-010 人工审核闸 + 标 `dup_with` 便利筛选 |
| 题材信号统计意义不足 | init 提示误导用户 | `min_cases_per_genre: 3` 下限 + 低于此值的 genre 在 init UI 标 "样本不足" |
| ralph 一轮跑 174 份耗时 3h+ | 单 commit 失败回滚成本大 | US-LR-006 仅验证**机制**，实际全量跑批由用户手动一行命令触发（脚本本身已被 ralph 验证） |
| 174 份 LLM 跑批费用失控 | 用户成本意外 | `config/live-review.yaml:model` 可切 Sonnet/Haiku，批跑前先小批估算费用、用户确认后再跑 |
| live-review-checker 假阳性阻断 | 写作流被拦截 | hard_gate_threshold 默认 0.65 偏宽松、`inject_into.review: false` 紧急关、与 editor-wisdom-checker 并列（任一通过即放行） |
| 已有 ink-init / ink-review SKILL.md 修改破坏其他流程 | 其他题材项目受影响 | `config/live-review.yaml:enabled: false` 总开关 + Step 99.5 / Step 3.6 通过 enabled flag 短路 |

---

## 7. 测试策略

| 层级 | 内容 | 覆盖 US |
|---|---|---|
| 单元测试 | 每个组件 mock LLM / 文件系统 | US-LR-001 / 003 / 007 / 008 / 009 / 011 / 012 |
| 集成测试 | 5 份 fixture jsonl 全管线跑通 | US-LR-005 / 007 / 008 / 011 |
| 向后兼容 | 410+ 份现存病例 + editor-wisdom 流程不受影响 | US-LR-001（必须）|
| 端到端 | init / review 双阶段 fixture 冒烟 | US-LR-013 |
| 失败处理 | LLM 返回非法 JSON / 损坏 raw.txt / 网络断 | US-LR-003 / 006 |
| 并发安全 | live_review_id_counter 4 worker spawn 互斥 | US-LR-002 |

---

## 8. 配置示例

`config/live-review.yaml`：

```yaml
enabled: true
model: claude-sonnet-4-6  # 或 claude-haiku-4-5（节省 6x 费用，可能漏微弱信号）
extractor_version: "1.0.0"

# 切分管线
batch:
  input_dir: "/Users/cipher/Desktop/星河审稿"
  output_dir: "data/live-review/extracted"
  resume_from_jsonl: true
  skip_failed: true
  log_progress: true

# review 门禁
hard_gate_threshold: 0.65       # 对应 65 分（高于 60 签约线一档作 buffer）
golden_three_threshold: 0.75    # 黄金三章更严

# init 注入
init_genre_warning_threshold: 60  # 题材均分低于此值触发 B（二次确认）
init_top_k: 3                     # D（反向检索）返回 Top-K 案例

# 聚合
min_cases_per_genre: 3

# 注入开关（独立可关）
inject_into:
  init: true     # ink-init Step 99.5
  review: true   # ink-review Step 3.6（与 editor-wisdom Step 3.5 并列）
```

---

## 9. 验收标准（PRD 整体完成的判定）

1. ✅ `data/live-review/extracted/` 至少含 5 份验证用 jsonl，schema 全部校验通过
2. ✅ `data/case_library/cases/live_review/` 至少含 30+ `CASE-LR-*.yaml`（来自 5 份 jsonl 的转换产物），全部用 schema_version 1.1 校验通过
3. ✅ `data/live-review/genre_acceptance.json` 含至少 5 个 genre（每个 ≥3 cases）
4. ✅ `data/live-review/rule_candidates.json` 含 ≥ 5 条候选（≥ 1 条 dup_with）
5. ✅ ink-init 跑 fixture query "都市重生律师" 输出含 D+B 组合 UI（相似案例 + 题材统计 + 必要时风险提示）
6. ✅ ink-review 跑 fixture 章节文本，live-review-checker 触发并写 violations
7. ✅ `tests/live_review/` 全过、`tests/case_library/test_schema_backward_compat.py` 全过、`pytest --no-cov -q` 整库不引入新 fail
8. ✅ ruff check 在新增模块（`ink_writer/live_review/`、`scripts/live-review/`）无新增错误
9. ✅ 端到端 smoke_test.py 退出码 0
10. ✅ `docs/live-review-integration.md` 完成
11. ⏳ **后续由用户手动**：跑全量 174 份（`scripts/live-review/run_batch.py`）→ 跑 jsonl_to_cases / aggregate_genre / extract_rule_candidates → 跑 review_rule_candidates 人工审核 → 跑 promote_approved_rules

---

## 10. 决策追溯（Brainstorm 6 题）

| Q | 选项 | 决策 | 影响 |
|---|---|---|---|
| Q1：174 份与 288 份关系 | A 同源 / B 独立 / C 抽样判断 | **C** → 抽样判断后定为独立模块 | 不替换 editor-wisdom，并列共存 |
| Q2：MVP 优先 vs 全量到位 | A MVP / B 全量 / C 双轨 | **B** | 三类产物全做（病例 + 题材 + 规则）|
| Q3：作品边界识别策略 | A 纯 LLM / B 规则+LLM 校正 / C 全规则 | **A** | 切分管线纯 LLM（费用 $15-25 估算）|
| Q4：init 阶段题材信号形态 | A 硬阻断 / B 风险提示 / C Top/Bottom 引导 / D 反向检索 | **D + B** | 主路径 D（检索式辅助）+ 兜底 B（阈值告警）|
| Q5：作品病例与 case_library 关系 | A 直接合并 / B 新 domain + 扩 schema / C 完全独立 | **B** | 扩 case_schema.json 加可选 block + 新 checker agent |
| Q6：ralph 执行粒度 | A 单 US 跑全量 / B 分层 US 链 / C 代码 ralph 数据人工 | **B** | 14 条 US，跑批 US 仅验证机制，全量由用户手动触发 |

---

## 11. 不在本次范围（YAGNI）

- ❌ 不实际跑 174 份全量批跑（脚本验证后由用户手动启动）
- ❌ 不做"自动从 rule_candidates 写入 rules.json"（永远要人工闸）
- ❌ 不替换 / 不删除现有 editor-wisdom 模块
- ❌ 不修改现有 410 份病例 yaml
- ❌ 不为 live-review 单独建独立 RAG 服务（复用 editor-wisdom 同款 bge 模型）
- ❌ 不在 plan 阶段（卷大纲 / 章节骨架）介入（plan 只继承 init 决策的题材，不再二次审查）
- ❌ 不做 web UI / dashboard，所有交互走 CLI
- ❌ 不做 dimension 标签自定义（10 主题域固定，与 editor-wisdom 对齐）

---

## 12. 用户手动操作清单（ralph 跑完所有 14 条 US 之后由你执行）

> ⚠️ 所有需要真实 ANTHROPIC_API_KEY、烧 LLM 费用、或人工判断的步骤都集中在这里。ralph 完成 14 条 US 后**不会**自动跑这些步骤——你要按顺序手动跑。每步前会先列预期效果、命令、产物、估算费用。

### §M-1：单文件冒烟（可选 / 推荐先跑）

**做什么**：跑 1 份真实数据 `BV12yBoBAEEn` 验证 LLM 切分形态合理（这份已知含明确 68 分点评，作为 gold reference）

**前置**：US-LR-004 已通过；`export ANTHROPIC_API_KEY=...`

**命令**：
```bash
python3 scripts/live-review/extract_one.py \
  --bvid BV12yBoBAEEn \
  --input ~/Desktop/星河审稿/BV12yBoBAEEn_raw.txt \
  --out data/live-review/extracted/BV12yBoBAEEn.jsonl
```

**预期产物**：`data/live-review/extracted/BV12yBoBAEEn.jsonl`，至少 1 行含 `score: 68 + dimension 含'设定'/'节奏'`

**估算费用**：$0.10-0.20（Sonnet）

**人工抽检要点**：行数是否合理（应该 5-15 本）、score_signal 分布、人名/标题识别是否合理

### §M-2：5 份小批跑（可选 / 推荐先跑验证形态稳定再上全量）

**做什么**：跑 5 份不同形态的真实数据（含明确打分 / 模糊打分 / 多本 / 单本）验证 prompt 鲁棒性

**前置**：US-LR-005 已通过；`§M-1` 通过

**命令**：从 `data/live-review/sample_bvids.txt` 读取 5 个 BV ID（PRD 实施时由 ralph 在 US-LR-005 中预填），然后：
```bash
python3 scripts/live-review/extract_one.py \
  --bvids BV1,BV2,BV3,BV4,BV5 \
  --input-dir ~/Desktop/星河审稿 \
  --output-dir data/live-review/extracted

python3 scripts/live-review/validate_jsonl_batch.py \
  --jsonl-dir data/live-review/extracted
```

**预期产物**：`data/live-review/extracted/<bvid>.jsonl` × 5 + `reports/live-review-validation-*.md`

**估算费用**：$0.5-1.0

**人工 review**：打开 validation 报告，看 `explicit_number` 占比是否 ≥ 30%、score 非空比例是否 ≥ 50%

### §M-3：全量批跑 174 份（必做 · 高峰期长任务）

**做什么**：跑全量 174 份直播稿生成 jsonl

**前置**：US-LR-006 已通过；§M-2 通过且 validation 报告满意

**命令**：
```bash
python3 scripts/live-review/run_batch.py \
  --input-dir ~/Desktop/星河审稿 \
  --output-dir data/live-review/extracted \
  --resume \
  --skip-failed \
  2>&1 | tee logs/live-review-batch-$(date +%Y%m%d-%H%M).log
```

**预期产物**：
- `data/live-review/extracted/BV*.jsonl` × ≤174（已存在的会被 `--resume` 跳过）
- `data/live-review/extracted/_failed.jsonl`（含失败列表，正常应 < 5%）

**估算费用**：$15-25（Sonnet）/ $3-5（Haiku，配 `model: claude-haiku-4-5`）

**估算时长**：1-3 小时（取决于并发度，PRD 默认无并发，串行）

**注意**：可中断，下次跑同命令会自动 `--resume`

### §M-4：jsonl 转病例 yaml（必做）

**做什么**：把全量 jsonl 转成 case_library 病例

**前置**：US-LR-007 已通过；§M-3 完成

**命令**：
```bash
python3 scripts/live-review/jsonl_to_cases.py \
  --jsonl-dir data/live-review/extracted \
  --cases-dir data/case_library/cases/live_review
```

**预期产物**：`data/case_library/cases/live_review/CASE-LR-2026-NNNN.yaml` × N（N 估算 1500-2000 = 174 × 平均 10 本/份）

**估算费用**：$0（纯转换无 LLM 调用）

**估算时长**：< 5 分钟

### §M-5：题材聚合（必做）

**做什么**：聚合所有 case yaml 到 `genre_acceptance.json`

**前置**：US-LR-008 已通过；§M-4 完成

**命令**：
```bash
python3 scripts/live-review/aggregate_genre.py \
  --cases-dir data/case_library/cases/live_review \
  --out data/live-review/genre_acceptance.json
```

**预期产物**：`data/live-review/genre_acceptance.json`，含 ≥ 20 个 genre 的统计

**估算费用**：$0

### §M-6：规则候选抽取（必做）

**做什么**：从 jsonl 抽通用规则候选

**前置**：US-LR-009 已通过；§M-3 完成

**命令**：
```bash
python3 scripts/live-review/extract_rule_candidates.py \
  --jsonl-dir data/live-review/extracted \
  --out data/live-review/rule_candidates.json
```

**预期产物**：`data/live-review/rule_candidates.json`，含 N 条候选（N 估算 50-150）

**估算费用**：$1-3（Sonnet）

**估算时长**：5-15 分钟

### §M-7：人工审核规则候选 + 提交 + 重建 editor-wisdom 索引（必做）

**做什么**：人工逐条审核新规则 → 提交审核通过的 → 重建 RAG 索引让 write 阶段能召回

**前置**：US-LR-010 已通过；§M-6 完成

**命令**：
```bash
# 7-A: 交互式审核（CLI 逐条 y/n/s/q）
python3 scripts/live-review/review_rule_candidates.py \
  --candidates data/live-review/rule_candidates.json

# 7-B: 提交审核通过的（仅写入 approved: true 的项）
python3 scripts/live-review/promote_approved_rules.py \
  --candidates data/live-review/rule_candidates.json \
  --rules data/editor-wisdom/rules.json

# 7-C: 重建 editor-wisdom 向量索引（让新规则被 retriever 召回）
ink editor-wisdom rebuild  # 或 python3 -m ink_writer.editor_wisdom.rebuild
```

**预期产物**：`rules.json` 增加若干 `EW-XXXX` 条目（含 `source: live_review`）+ `data/editor-wisdom/vector_index/` 重建

**估算时长**：人工审核 1-2 小时（取决于候选数）；rebuild < 5 分钟

### §M-8：构建 live_review 向量索引（必做）

**做什么**：构建 init 阶段题材检索用的向量索引

**前置**：US-LR-011 已通过；§M-4 完成

**命令**：
```bash
python3 scripts/live-review/build_vector_index.py \
  --cases-dir data/case_library/cases/live_review \
  --out-dir data/live-review/vector_index
```

**预期产物**：`data/live-review/vector_index/index.faiss` + 元数据

**估算时长**：< 10 分钟（bge-small-zh-v1.5 本地 CPU 跑）

### §M-9：端到端真 LLM smoke 验证（可选）

**做什么**：用真实 LLM 跑一次 init→review 端到端，验证 mock 与真实输出形态一致

**前置**：US-LR-013 已通过；§M-7 + §M-8 完成

**命令**：
```bash
python3 scripts/live-review/smoke_test.py --with-api
```

**预期产物**：`reports/live-review-smoke-report.md` 全部 PASS

**估算费用**：$0.50-1.00

---

## 13. 总体里程碑（你看完做了什么时跑哪些 §M）

```
  ralph 跑 14 条 US（机器全自动）
        │
        ▼
  §M-1 单文件冒烟（10 分钟，可选）
        │
        ▼
  §M-2 5 份小批（30 分钟，推荐）
        │
        ▼
  §M-3 全量 174 份（1-3 小时，必做）─── 这是最耗时的一步
        │
        ▼
  §M-4 → §M-5（< 10 分钟，无费用）
        │
        ▼
  §M-6（< 15 分钟，~$2）
        │
        ▼
  §M-7（人工审核 1-2 小时）─── 这是最耗你精力的一步
        │
        ▼
  §M-8（< 10 分钟，无费用）
        │
        ▼
  §M-9 真 LLM smoke（5 分钟，~$1，可选）
        │
        ▼
  ✅ 完工，下次开新书在 ink-init 时自动用上 174 份直播经验
```

**总投入**（除 ralph 自动部分外）：你的精力 ≈ 2-3 小时（主要在 §M-7 审核），LLM 费用 ≈ $20-30（Sonnet）/ $5-8（Haiku），墙钟时间 ≈ 4-6 小时（其中 §M-3 可挂机）

---

**End of Spec**
