# 病例库驱动的质量治理 Overhaul (Design Spec)

**Status**: ready-for-plan
**Date**: 2026-04-23
**Author**: cipher-wb（产品） + brainstorming co-pilot
**Baseline**: v23.0.0
**Target version**: v24.x（5 周完成 M1-M5）
**Quality target**: 起点编辑评分 30 → 60-70，6 个月内验证

---

## 1. 背景与问题陈述

### 1.1 现状

v23 是工程上完整的网文写作流水线：
- 288 条编辑规则（`data/editor-wisdom/`）+ 30+ 本起点范文（`benchmark/reference_corpus/`）
- 23 个 checker agent（含 anti-detection / reader-pull / sensory-immersion / high-point ……）
- RAG 基座：Qwen3-Embedding-8B + jina-reranker-v3 + FAISS（QueryRouter auto: vector/bm25/hybrid/graph_hybrid）
- ink-init / ink-plan / ink-write / ink-review 全流水线 + ink-learn 局部学习
- v22 新增 simplicity 域 + 场景感知召回

### 1.2 实际产出

两本书前三章送起点编辑（星河）点评，**评分 30/100**：

| 题材 | 编辑扣分 |
|---|---|
| 修仙 | 题材老套、凹设定、无人物冲突、无代入感、不吸引读者 |
| 都市 | 金手指出场太晚、金手指能力不清晰、不爽、主角当摄像头 |

### 1.3 诊断

把扣分项映射到 v23 现有 checker：

| 扣分 | v23 checker 覆盖 | 阶段 |
|---|---|---|
| 题材老套 | ❌ 无 | 上游 ink-init |
| 凹设定 | ❌ 无 | 上游 ink-init |
| 无人物冲突 | ⚠️ 灰区（ooc 不管这个） | 章节级盲区 |
| 无代入感 | ✅ reader-pull / sensory-immersion | 下游（有但没拦住）|
| 金手指出场太晚 | ❌ 无 | 上游 ink-plan |
| 金手指能力不清晰 | ❌ 无 | 上游 ink-init |
| 不爽 | ✅ high-point | 下游（有但没拦住）|
| 主角当摄像头 | ⚠️ 灰区 | 章节级盲区 |

**核心结论**：
- 5/8 扣分属于上游策划期，现有架构无 checker 覆盖
- 3/8 扣分有 checker 但未拦住 → checker 阈值 + writer 服从度问题
- 用户对"参考库是否生效"的判断**完全凭直觉**（从未真正翻过 evidence chain）
- 问题不是缺库（库已有），而是**缺少病例驱动的闭环 + 上游策划期审查 + 可观测性**

### 1.4 设计原则

1. **病例（case）为唯一真相源**：编辑差评 → case → checker → 阻断/重写
2. **证据链强制**：每章交付必带 `evidence_chain.json`
3. **三层并行**：上游 P0 + 下游 P1 + 参考库 P2 同步推进
4. **可观测优先**：消除"靠感觉判断库有没有生效"
5. **与 v23 资产兼容**：不动原始数据、不替换基座

---

## 2. 整体架构

### 2.1 核心模型

> **「病例（case）」是产线唯一真相源。** 编辑差评 → case → 反向产出 (规则 + checker + 范文召回标签) → 注入 P0/P1/P2 → 章节 + 证据链 → 反查复发 → 关闭 case / 衍生新 case。

### 2.2 七大组件

```
                              ┌────────────────────────────────────┐
                  (D)         │  1. Case Library (病例库) ← 唯一真相 │
            星河点评摄入管线 →│     schema · tag · 关联资产         │
                              └────────────────┬───────────────────┘
                                               │ drives
        ┌─────────────────────┬────────────────┴──────┬─────────────────────┐
        ▼                     ▼                       ▼                     ▼
   2. P0 上游策划层      3. P1 下游闭环层      4. P2 参考库增强层    5. Evidence Chain
   (ink-init/ink-plan)   (writer + checker)    (retrieval refactor)  (强制子模块)
        │                     │                       │                     │
        └─────────────────────┴───────────┬───────────┴─────────────────────┘
                                          ▼
                          ┌──────────────────────────────────┐
                          │  6. 章节 + evidence_chain.json    │
                          └────────────────┬─────────────────┘
                                           │ 反查
                                           ▼
                          ┌──────────────────────────────────┐
                          │  7. Regression Loop (回归回路)    │
                          │  复发 → 病例升级 → 加固           │
                          └──────────────────────────────────┘
```

### 2.3 与 v23 资产兼容

| v23 已有 | 新架构里的角色 | 改不改 |
|---|---|---|
| 288 条编辑规则 (`data/editor-wisdom/rules.json`) | 病例库初始种子 | ETL 转换，不动源 |
| 30 本范文 (`benchmark/reference_corpus/`) | P2 切片管线输入 | 不动原文 |
| 23 个 checker | P1 改造对象 + 新增 9 个 | 改契约不改算法 |
| Qwen3-Embedding + jina-rerank | 直接复用 | 不动 |
| FAISS | **替换为 Qdrant**（payload filter / 增量 / 可观测性） | 替换 |
| ink-init / ink-plan / ink-write / ink-review | P0/P1 改造钩子 | 加新阶段不删旧 |
| editor-wisdom 摄入管线 (01_scan→06_build_index) | 复用 + 加 07_to_cases | 加一步 |
| ink-learn / project_memory.json | 单本书短期记忆 → 周期回灌长期 case_library | 兼容 |

### 2.4 边界（明确不做的事）

- ❌ 不替换 Embedding（Qwen3-Embedding-8B 中文顶尖，换无意义）
- ❌ 不替换 Reranker（jina-reranker-v3 顶尖）
- ❌ 不替换现有 23 个 checker（仅改契约 + 新增 9 个）
- ❌ 不搬走原始数据
- ❌ 不做"自动从 0 写新书 / 自动投稿"
- ❌ 不做 Web 编辑器界面
- ❌ 不做模型微调

### 2.5 三层并行的真正含义

不是三条独立产线，而是**一份病例数据流被三层各自消费**：
- `layer=upstream` 路由到 P0
- `layer=downstream` 路由到 P1
- `layer=reference_gap` 路由到 P2
- 多 layer 同时路由到多层

---

## 3. Case Library Schema

### 3.1 物理形态

```
data/case_library/
  ├── cases/                          # 一案一文件，git diff 友好
  │   ├── CASE-2026-0001.yaml
  │   └── ...
  ├── index.sqlite                     # 倒排索引（tag/genre/layer → case_id）
  ├── cases.jsonl                      # 全量打包（retrieval 启动时加载）
  └── ingest_log.jsonl                 # 摄入审计日志
```

**为什么不用单一 sqlite/json**：一案一文件 → git 协作友好、code review 看得清；sqlite 只做查询索引，权威数据永远是 yaml。

### 3.2 Case Schema

```yaml
case_id: CASE-2026-0001
title: "主角接到电话 3 秒就不慌，反应不真实"
status: active                  # pending | active | resolved | regressed | retired
severity: P1                    # P0 阻断 | P1 强警告 | P2 警告 | P3 提示
domain: writing_quality         # writing_quality | infra_health
layer: [downstream]             # upstream | downstream | reference_gap | infra_health（多选）

tags:
  - reader_immersion
  - protagonist_reaction
  - emotional_truth

scope:
  genre: [all]                  # all | xuanhuan | realistic | history-travel | ...
  chapter: [all]                # all | opening_only | golden_three | climax | combat | ...
  trigger: opening_3            # 何时主动检测此 case

source:
  type: editor_review           # editor_review | self_audit | regression | infra_check
  reviewer: 星河编辑
  raw_text: "主角接到电话3秒就不慌了，行为不真实"
  ingested_at: 2026-04-23
  ingested_from: 都市A/ch003

failure_pattern:
  description: "突发事件→主角理性恢复之间缺情绪缓冲"
  observable:
    - "突发事件后到理性反应之间字符数 < 200"
    - "缺生理反应描写（心跳/呼吸/手汗）"
    - "缺心理混乱过渡"

bound_assets:
  rules:
    - rule_id: R-emotional-buffer-001
      excerpt: "..."
  corpus_chunks:
    - chunk_id: CHUNK-诡秘之主-ch003-§2
      reason: "克莱恩身份切换 3 段渐进恐慌，模板可借鉴"
  checkers:
    - checker_id: protagonist-reaction-checker
      created_for_this_case: true

resolution:
  introduced_at: 2026-05-01
  validation_chapters: [都市A-ch010, 都市A-ch011]
  regressed_at: null
  related_cases: []

evidence_links:
  - chapter: 都市A-ch010
    evidence_chain: data/都市A/chapters/ch010.evidence.json
    case_status_in_chapter: passed
```

### 3.3 病例分类（domain × layer）

|  | upstream | downstream | reference_gap | infra_health |
|---|---|---|---|---|
| **writing_quality** | 题材老套、金手指晚、动机弱 | 无代入感、不爽、AI 味、当摄像头 | 同题材范文不足、规则覆盖不全 | — |
| **infra_health** | — | — | — | reference_corpus 链接断、API key 失效、向量索引损坏 |

**CASE-2026-0000**: `infra_health` 零号病例（reference_corpus 软链接断）— 吃自己狗粮的示范。

### 3.4 生命周期状态机

```
pending  ──(确认+绑定 checker)──→  active
active   ──(连续 N 章未触发)──→    resolved
resolved ──(再次触发)─────────→    regressed   ← 关键边！触发病例升级
regressed ──(加固方案上线)────→    active
*        ──(明确判定为伪)─────→    retired
```

`resolved → regressed` 触发 §6 Layer 4 复发追踪，自动升级 severity。

### 3.5 增量摄入接口

复用并扩展现有 `editor-wisdom` 管线（`01_scan` → `06_build_index`）+ 新增 **`07_to_cases`**：

```bash
# 单文件 / 目录摄入
ink case ingest --from ~/Desktop/星河编辑/2026-04-25-某某书.md

# 监听目录（自动）
ink case watch --dir ~/Desktop/星河编辑/

# 批量重建
ink case rebuild
```

**幂等性**：基于 `source.raw_text` 的 hash 去重。

### 3.6 Pre-flight Health Checker

`ink-write` 启动时自动运行：

```python
def preflight():
    checks = [
        check_reference_corpus_readable(min_files=100),
        check_editor_wisdom_index_loadable(),
        check_qdrant_connection(),
        check_embedding_api_reachable(),
        check_rerank_api_reachable(),
        check_case_library_loadable(),
    ]
    failed = [c for c in checks if not c.passed]
    if failed:
        raise PreflightError(create_infra_cases(failed))
```

任一失败 → 阻断写作 + 自动建 infra_health 病例。

---

## 4. P0 上游策划层（ink-init + ink-plan）

### 4.1 ink-init 阶段新增 4 个 checker

#### a) `genre-novelty-checker`
- 输入：书名 + 题材标签 + 一句话简介 + 主角设定 + 金手指描述
- 比对：reference_corpus 30 本 + 起点 top 200 简介库（**新增数据源**）
- 输出：top-3 相似书 + 余弦相似度 + 撞型维度
- 阈值：> 0.85 → P0 阻断；0.75-0.85 → P1 警告

#### b) `golden-finger-spec-checker`（4 维度）
| 维度 | 阈值 |
|---|---|
| 具象（能做什么 1 句话说清） | < 0.6 阻断 |
| 反差（与日常/普通人差距） | < 0.6 警告 |
| 可成长（等级/阈值/边界设计） | < 0.6 警告 |
| 代价（合理使用代价，防无敌） | < 0.5 警告 |

#### c) `naming-style-checker`
- 输入：主角名 / 主要角色名
- 比对：**LLM 高频起名词典**（新增 ≈ 300 条种子，含"林夜""叶凡""陈青山"等模板名）
- 阈值：AI 味 > 0.7 阻断；0.5-0.7 警告

#### d) `protagonist-motive-checker`
- 维度：动机是否主动 / 是否具体 / 是否有切肤之痛
- 阈值：任一维 < 0.6 警告

### 4.2 ink-plan 阶段新增 3 个 checker

#### a) `golden-finger-timing-checker`
- 大纲前 3 章必须出现金手指 + 第 3 章末必须有具体能力演示
- 未达成 → P0 阻断（打回大纲重写）

#### b) `protagonist-agency-skeleton-checker`（骨架级）
- 每章必须标注「主角主动决策点 / 被动反应点」
- 主动决策章节比例 < 40% → P0 阻断
- 连续 3 章无主动决策 → P1 警告

#### c) `chapter-hook-density-checker`
- 每章必须有：开章钩 + 章末悬念
- 前 3 章必须有金钩
- 未达 → P1 警告

### 4.3 钩子插入点

| 文件 | 改造 |
|---|---|
| `ink-writer/skills/ink-init/SKILL.md` | 末尾新增 Step 99：调 4 个 checker，产出 `planning_evidence_chain.json` init 段 |
| `ink-writer/skills/ink-plan/SKILL.md` | 大纲生成后 Step 99：调 3 个 checker，扩展 evidence chain |
| `ink-writer/agents/` | 新增 7 个 agent 规格 |
| `data/case_library/cases/` | 新增 7+ upstream 种子病例 |
| `data/market-trends/qidian_top200/` | **新增**起点 top 200 简介库 |
| `data/naming/llm_naming_blacklist.json` | **新增**首批 ≈ 300 条 |

### 4.4 P0 策划证据链

```json
{
  "phase": "ink-init",
  "book_id": "都市B",
  "produced_at": "2026-04-25T10:30:00Z",
  "checks": {
    "genre_novelty":    {"score": 0.72, "passed": true,  "top_similar": [...], "cited_cases": ["CASE-2026-0042"]},
    "golden_finger_spec": {"dims": {...}, "passed": true},
    "naming_style":     {"name": "...", "ai_smell": 0.3, "passed": true},
    "protagonist_motive": {"score": 0.81, "passed": true}
  },
  "blocked_cases": [],
  "warned_cases":  ["CASE-2026-0017"],
  "next_phase":    "ink-plan",
  "next_phase_must_check": ["golden_finger_timing", "protagonist_agency_skeleton", "chapter_hook_density"]
}
```

### 4.5 阻断策略

```
P0 阻断    → 必须修，否则不允许进入下一阶段
P1 警告    → 允许通过，但必须在 evidence chain 写明豁免理由（人类签字）
P2/P3 提示 → 自动记录，不阻断
```

### 4.6 数据成本

| 新增数据 | 一次性 | 维护 |
|---|---|---|
| 起点 top 200 简介库 | 1 天爬虫 | 季度刷新 |
| LLM 高频起名词典 | 半天 | 半年补充 |
| 7 个 upstream 种子病例 | 2 小时 | 持续累加 |

---

## 5. P1 下游闭环层（writer 服从度 + 阈值阻断 + 2 章节级 checker）

### 5.1 改造 A：writer 服从度（核心）

新增 `writer-self-check` agent，**强制环节**：

```
[召回] context-agent → 注入 writer prompt：
        - rules R[1..n]
        - chunks C[1..k]
        - cases CS[1..m]
   ↓
[写作] writer-agent 输出章节 X
   ↓
[写完比对] writer-self-check ← 新增
   ↓
   compliance_report.json:
     rule_compliance:    0.85
     chunk_borrowing:    0.72
     cases_addressed:    [CASE-2026-0017, ...]
   ↓
合规率 < 70% → 直接重写（不进 review，省下游算力）
合规率 ≥ 70% → 进 review 阶段
```

**消除"靠感觉判断库生效与否"**：每章合规率写入 evidence chain。

### 5.2 改造 B：checker 阈值升级（打分 → 阻断）

新增 `config/checker-thresholds.yaml`：

```yaml
reader-pull:
  block_threshold: 60
  warn_threshold: 75
  bound_cases: [CASE-2026-0008, ...]

sensory-immersion:
  block_threshold: 65
  warn_threshold: 78
  bound_cases: [...]

high-point:
  block_threshold: 70
  warn_threshold: 80
  bound_cases: [CASE-2026-0042, ...]

anti-detection:
  block_threshold: 70
  warn_threshold: 82
  bound_cases: [...]

conflict-skeleton:
  block_threshold: 60
  bound_cases: [CASE-2026-0011]

protagonist-agency:
  block_threshold: 60
  bound_cases: [CASE-2026-0023]
```

### 5.3 改造 C：2 个新章节级 checker

#### a) `conflict-skeleton-checker`
- 每章 ≥ 1 个显式冲突（人物立场对立 / 利益冲突 / 价值观碰撞）
- 三段结构：摩擦点 → 升级 → 临时收尾

#### b) `protagonist-agency-checker`（章节级）
- 主角在本章 ≥ 1 个主动决策
- 主角 ≥ 1 次推动剧情（vs 当摄像头）

### 5.4 重写机制（polish-agent 改造）

```
违规 → 关联 case_id → polish-agent 收到：
    "上次违反了 CASE-2026-0042（high-point 不爽），
     该 case 关联范文 CHUNK-诡秘之主-ch005-§3，
     该 case 关联规则 R-payoff-pacing-007，
     请重写第 N 段并满足以上"

重写后 → 再过 writer-self-check + 全部 checker
最多 3 轮 → 仍失败 → needs_human_review.jsonl（不丢稿）
```

**关键约束**：每次重写必须有 case_id 驱动（禁止空重写）。

### 5.5 Evidence Chain 完整形态

```json
{
  "chapter": "都市A-ch010",
  "produced_at": "2026-04-25T10:30:00Z",
  "phase_evidence": {
    "context_agent": {
      "recalled": {"rules": 12, "chunks": 5, "cases": 8},
      "recall_quality_avg": 0.82
    },
    "writer_agent": {
      "prompt_hash": "abc123",
      "compliance_report": {
        "rule_compliance": 0.87,
        "chunk_borrowing": 0.74,
        "cases_addressed": ["CASE-2026-0017"]
      }
    },
    "checkers": [
      {"id": "reader-pull", "score": 78, "blocked": false},
      {"id": "sensory-immersion", "score": 81, "blocked": false},
      {"id": "high-point", "score": 65, "blocked": true,
       "cases_hit": ["CASE-2026-0042"], "rewrite_triggered": true},
      {"id": "conflict-skeleton", "score": 72, "blocked": false},
      {"id": "protagonist-agency", "score": 80, "blocked": false},
      {"id": "anti-detection", "score": 88, "blocked": false}
    ],
    "polish_agent": {
      "rewrite_rounds": 1,
      "rewrite_drivers": ["CASE-2026-0042"],
      "final_score": 82
    }
  },
  "outcome": "delivered",
  "case_evidence_updates": [
    {"case_id": "CASE-2026-0017", "result": "passed"},
    {"case_id": "CASE-2026-0042", "result": "regressed", "trigger_severity_upgrade": true}
  ],
  "human_overrides": []
}
```

### 5.6 钩子插入点

| 文件 | 改造 |
|---|---|
| `ink-writer/agents/writer-agent.md` | 写完调 writer-self-check |
| `ink-writer/agents/writer-self-check.md` | **新增** |
| `ink-writer/agents/conflict-skeleton-checker.md` | **新增** |
| `ink-writer/agents/protagonist-agency-checker.md` | **新增**（章节级，与 ink-plan 骨架级互补）|
| `ink-writer/agents/polish-agent.md` | 接收 case_id 驱动重写 |
| `ink-writer/skills/ink-write/SKILL.md` | 新增"合规→阻断→重写"循环 |
| `ink-writer/skills/ink-review/SKILL.md` | 产出 evidence_chain.json |
| `config/checker-thresholds.yaml` | **新增**集中管理阈值 + cases 绑定 |

### 5.7 防死循环护栏

1. 最多 3 轮重写
2. 每次重写必须有 case_id 驱动
3. 第 3 次仍不通过 → 标记 `needs_human_review`，不删稿
4. 阈值热更新（不重启生效）
5. 重写历史保留至 `data/<book>/rewrite_history/`，可回滚

---

## 6. P2 参考库增强（段落切片 + 题材定向 + 病例反向 + 用户扩展）

### 6.1 改造 A：场景级切片管线

```
30 本范文（修复 symlink 后）
  ↓
[scene_segmenter] LLM 识别场景边界（开篇/打脸/装逼/情感升华/反转/战斗/危机/钩子结尾），每片 200-800 字
  ↓
[chunk_tagger] LLM 打标
  ↓
[chunk_indexer] 向量化入 Qdrant（带 payload）
  ↓
data/corpus_chunks/{metadata.jsonl, qdrant collection}
```

**chunk schema**：

```yaml
chunk_id: CHUNK-诡秘之主-ch003-§2
source_book: 诡秘之主
source_chapter: ch003
char_range: [1234, 1890]
text: "克莱恩盯着镜子里的脸，呼吸开始急促……"
scene_type: identity_reveal
genre: [异世大陆, 玄幻]
tension_level: 0.85
character_count: 1
dialogue_ratio: 0.0
hook_type: identity_secret
borrowable_aspects:
  - psychological_buffer
  - sensory_grounding
  - emotional_progression
quality_score: 0.92
source_type: builtin           # builtin | user
ingested_at: 2026-04-25
```

`borrowable_aspects` 是 chunk 与 case 的连接点。

### 6.2 改造 B：题材定向召回（路由升级）

新增 `config/retrieval-router.yaml`：

```yaml
default_routes:
  - rules:    case_aware       # 从 case 反向取规则
  - chunks:   genre_filtered   # 同题材范文段
  - style:    style_rag        # 现有保留
fusion: rrf
rerank: jina-reranker-v3
top_k:
  rules: 5
  chunks: 3
  style: 2

genre_isolation:
  enabled: true
  whitelist:
    - 都市 ↔ 现实
    - 修仙 ↔ 玄幻 ↔ 异世大陆
  cross_genre_cap: 1
```

### 6.3 改造 C：病例反向召回

```
当前章节请求：genre=都市, scene_type=金手指首次展示, target_emotion=爽
   ↓
[Step 1] 找适用 cases
   case_library 查询：layer=downstream + scope.genre 含都市
                    + scope.chapter 命中
   ↓ 命中：[CASE-2026-0042 不爽, CASE-2026-0017 主角被动, ...]
[Step 2] 反向取关联资产（rules / corpus_chunks）
   ↓
[Step 3] 题材二次过滤 + quality_score > 0.7
   ↓
[Step 4] RRF + jina rerank → 注入 writer prompt
```

**召回的每个 chunk 都有"为了规避具体失败模式而召"的明确目的**，比"哪段相关召哪段"精准得多。

### 6.4 改造 D：用户扩展接口

```
data/case_library/user_corpus/
  ├── history-travel/
  │   ├── 明朝那些事儿.txt
  │   ├── 明史摘抄.md
  │   └── _meta.yaml
  ├── xuanhuan/
  │   └── ...
  └── user_genres.yaml
```

CLI：

```bash
ink corpus ingest --dir data/case_library/user_corpus/history-travel/
ink corpus watch --dir data/case_library/user_corpus/
ink corpus rebuild
```

摄入流程：切片 → 自动打标 → 标 `source_type: user` → 入索引 → 自动产 pending case。

### 6.5 钩子插入点

| 文件 | 改造 |
|---|---|
| `scripts/corpus_chunking/scene_segmenter.py` | **新增** |
| `scripts/corpus_chunking/chunk_tagger.py` | **新增** |
| `scripts/corpus_chunking/chunk_indexer.py` | **新增** |
| `scripts/corpus_chunking/cli.py` | **新增**（`ink corpus ingest/watch/rebuild`）|
| `data/corpus_chunks/` | **新增产物目录** |
| `data/case_library/user_corpus/` | **新增用户目录** |
| `config/retrieval-router.yaml` | **新增** |
| `ink_writer/retrieval/router.py` | 加 `case_aware` + `genre_filtered` |
| `ink_writer/retrieval/case_retriever.py` | **新增** |
| `ink_writer/editor_wisdom/writer_injection.py` | 接收 case-driven 结果 |

### 6.6 防召回污染护栏

1. 题材隔离：跨题材召回必须显式 whitelist 且最多 1 条
2. 质量阈值：`quality_score < 0.7` 不进默认池
3. 去重：相似度 > 0.95 合并
4. 来源审计：可追溯到具体书/章/段
5. 用户优先级：`source_type=user` 略低权重（防低质用户料污染）
6. 最低多样性：top-K 不能全来自同一本书

### 6.7 数据成本

| 任务 | 工作量 | API 成本 |
|---|---|---|
| 30 本切片（≈ 2700 chunks） | 1 天 | $30-50 |
| 题材标签建模（10 题材） | 半天 | < $5 |
| 用户接口 CLI 测试 | 半天 | 可忽略 |

---

## 7. 自我进化机制（5 层闭环）

### 7.1 与 v23 已有的关系

v23 已有半套：
- `ink-learn` skill（手动 / 自动 / 趋势）
- `.ink/project_memory.json`（pattern 库，含 success/failure/neutral）

v23 缺：
1. 局限于单本书内部，无跨书
2. 只学内部审查得分，无外部反馈
3. 无复发追踪
4. 无强制闭环（pattern 不自动产 checker）
5. 无 A/B 对照

### 7.2 5 层闭环

```
┌─ Layer 5: 元规则浮现 (meta-rule emergence)
│      N 个相似 case 自动合并 → 升级产线 default
├─ Layer 4: 复发追踪 (regression tracking)
│      resolved → regressed 自动升级 severity
├─ Layer 3: 跨书共享 (cross-book learning)
│      case_library 全局；一本书 case 在所有书生效
├─ Layer 2: 内/外双信号 (dual feedback)
│      内部 checker 分 + 外部编辑/读者评 → 双重训练 case
└─ Layer 1: 病例闭环 (case loop)
        差评 → case → checker → 阻断/重写 → 通过
```

### 7.3 量化指标

```
Dashboard 周报：

┌─ 病例新增量    本周 +3   累计 47          ← 反馈在持续吸纳
├─ 病例消化率    87%       (active→resolved)← 修复速度
├─ 病例复发率    8%        (resolved→regress)← 越低越好
├─ 元规则浮现    本月 1 条                    ← 系统在自我归纳
├─ 编辑评分      均分 58 → 67 (+9)            ← 真实质量提升
├─ checker 准确率 78% → 89%                   ← 内部判定越来越准
└─ 跨书复用率   73%                           ← 一本书教训用到几本
```

### 7.4 防过拟合护栏

1. **主权 case** 标记：核心铁律不被任何浮现规则覆盖
2. **多源验证**：单一来源 case 升 P0 前需 ≥ 2 次独立验证
3. **回滚机制**：每次产线变更带版本号，一键 rollback
4. **A/B 通道**：可选 50% 章节生效，对比再全量

### 7.5 ink-learn 兼容路径

- `ink-learn` 改造为 case 生产工具之一
  - `--auto` success patterns → `case_type=pattern_success`（召回时优选模仿）
  - `--auto` failure patterns → 自动 propose pending case
- `project_memory.json` 作为单本书短期记忆
- `case_library/` 作为长期记忆（跨书、跨时间）
- 短期 → 长期：`ink-learn --promote` 周期回灌

---

## 8. RAG 基座决定

| 层 | 决定 | 理由 |
|---|---|---|
| Embedding | **保留** Qwen3-Embedding-8B | MTEB-zh 顶尖，换无质变 |
| Reranker | **保留** jina-reranker-v3 | 业界顶尖 |
| Vector DB | **从 FAISS 迁到 Qdrant** | 元数据过滤 / 增量 / 可观测性都是新方案的硬需求 |

**Qdrant 选型理由**：
- 原生 payload filter（题材白名单、scene_type 过滤）
- 增量友好（病例库 + 用户 corpus 持续摄入）
- 自带 dashboard（与 §7 进化指标对齐）
- 单机 docker 一行命令起，运维成本低
- `qdrant-client` Python SDK 成熟

**迁移策略**：
- M1 双写 7 天（FAISS 与 Qdrant 同时落数据）
- 灰度切流量
- 出问题立刻切回 FAISS

---

## 9. 实施计划（5 周里程碑）

### M1 / Week 1 — 基础设施 + Qdrant 迁移
- [ ] case schema 定稿（YAML + JSON Schema 验证）
- [ ] `data/case_library/` 目录 + sqlite 索引
- [ ] `ink case` CLI（list / show / create / status）
- [ ] **Qdrant docker 部署 + 健康检查**
- [ ] **FAISS → Qdrant 迁移脚本**
- [ ] **Qdrant payload schema 设计**（genre / scene_type / quality_score / source_type / case_ids）
- [ ] CASE-2026-0000（infra_health 零号病例）
- [ ] preflight health checker（6 项检查）
- [ ] **修复 reference_corpus 软链接**（方案 A 硬拷贝）

**交付物**：能 `ink case create`；`ink-write` 启动前必跑 preflight；Qdrant 上线运行。

### M2 / Week 2 — 数据资产
- [ ] `scripts/corpus_chunking/` 切片管线
- [ ] 30 本范文切片产出（≈ 2700 chunks）入 Qdrant
- [ ] `ink corpus ingest/watch/rebuild` CLI
- [ ] 288 条 editor-wisdom rules → 病例转换（07_to_cases）→ pending cases
- [ ] 批量审批合理 cases 置 active
- [ ] 起点 top 200 简介库爬取

**交付物**：段落级范文召回可用；病例库 ≥ 100 active cases。

### M3 / Week 3 — P1 下游闭环（**质量拐点**）
- [ ] `writer-self-check` agent
- [ ] `conflict-skeleton-checker` agent
- [ ] `protagonist-agency-checker` agent（章节级）
- [ ] `polish-agent` 改造（case_id 驱动重写）
- [ ] `config/checker-thresholds.yaml` + 热更新
- [ ] reader-pull / sensory-immersion / high-point 阈值阻断升级
- [ ] **dry-run 模式**：跑 5 章观察后切真阻断

**交付物**：跑一章新章节，evidence_chain.json 出现合规率数字。**30 → 50 分关键节点。**

### M4 / Week 4 — P0 上游策划层
- [ ] 4 个 ink-init checker
- [ ] 3 个 ink-plan checker
- [ ] LLM 高频起名词典（≈ 300 条种子）
- [ ] `planning_evidence_chain.json` schema + 落档
- [ ] ink-init / ink-plan SKILL.md 增加 Step 99
- [ ] 上游 cases 批量编写

**交付物**：开新书强制走策划期审查。

### M5 / Week 5 — 证据链可视化 + 自进化 + 用户扩展
- [ ] `ink dashboard` 扩展（病例复发率 / 修复速度 / 编辑分趋势 / checker 准确率）
- [ ] Layer 4 复发追踪触发
- [ ] Layer 5 元规则浮现
- [ ] `data/case_library/user_corpus/` + history-travel 样例
- [ ] A/B 通道（可选 50% 章节生效）
- [ ] 文档：作者使用手册 + 编辑反馈录入手册

**交付物**：完整闭环上线 + 周报自动产出。

---

## 10. 工作量预估

| 类别 | 数量 |
|---|---|
| 新增 agent 规格 | 9 个 |
| 改造 agent 规格 | 3 个（writer-agent / polish-agent / context-agent）|
| 新增 Python 模块 | ≈ 12 个 |
| 改造 Python 模块 | ≈ 4 个 |
| 改造 SKILL.md | 4 个（ink-init / ink-plan / ink-write / ink-review）|
| 新增 CLI 命令 | `ink case *` / `ink corpus *` / `ink dashboard` 扩展 |
| 新增配置 | `checker-thresholds.yaml` / `retrieval-router.yaml` |
| 新增数据集 | corpus_chunks（自动） + 起点 top200 简介 + LLM 起名词典 |
| 文档 | 编辑反馈录入手册 + 病例 schema 文档 + 评估手册 |

**API 成本**：M2 一次性切片 ≈ $30-50；后续每章额外开销（self-check + chunker）≈ +$0.05/章。

---

## 11. 风险与护栏

| # | 风险 | 触发 | 护栏 |
|---|---|---|---|
| 1 | writer-self-check 算力翻倍 | M3 上线 | 提供采样验证（每 N 章查 1 章）；评分 ≥ 90 直接跳过 |
| 2 | 阈值过严锁死写作 | M3/M4 上线 | M3 强制 dry-run 1 周；阈值热更新 + 一键回滚 |
| 3 | 切片质量参差 | M2 切片完成 | 抽样人工核对 50 chunks；quality_score < 0.6 进人工复审 |
| 4 | case schema 演进破兼容 | 任意时点 | schema 带 version；迁移脚本随 schema 同发 |
| 5 | 编辑反馈断档 | 任意时点 | 手动录入兜底；ink-learn 自动从内部审查发现疑似 case |
| 6 | 过拟合到单一编辑偏好 | M5 之后 | 主权 case + 多源验证 + A/B 通道 |
| 7 | Qdrant 迁移过程查询不可用 | M1 切换日 | 双写 7 天 + 灰度切流量 + 出问题切回 FAISS |

---

## 12. 验收标准（M5 结束）

| 指标 | 验收线 |
|---|---|
| 病例库 active cases | ≥ 100 |
| corpus chunks 入库 | ≥ 2500 |
| pre-flight health checker 命中率 | 100%（产线问题不再悄悄退化）|
| 章节平均 rule_compliance | > 0.80 |
| 重写率 | 30% - 50%（说明 checker 真在拦）|
| 编辑评分提升 | 30 → 50+（**核心质量验证**）|
| dashboard 周报生成 | 自动 |
| 用户扩展接口可用 | 至少跑通 history-travel 一案 |

---

## 13. 不在本期范围

- ❌ 重建 Embedding / Reranker
- ❌ 替换现有 23 个 checker
- ❌ 自动从 0 写新书 / 自动投稿
- ❌ 起点榜单实时同步（季度刷新即可）
- ❌ 多模型并行 / 模型微调
- ❌ Web 编辑器界面
- ❌ 移动端

---

## 14. 关键决议记录

| 决议 | 选择 | 决议依据 |
|---|---|---|
| 范围边界 | P0+P1+P2 三块并行（用户选 c） | 上下游均有伤，分批太慢 |
| 架构骨架 | 病例库 C + 证据链 B 强制子模块（用户选 b）| 反馈环最短 + 可观测顶配 |
| 修复 reference_corpus | 方案 A 硬拷贝 | 跨平台、跨搬迁、永不再断 |
| infra_health 病例 | 纳入设计 | 防"悄悄退化" |
| Vector DB | 迁 Qdrant | 元数据过滤是新方案硬需求 |
| Embedding / Reranker | 不换 | 中文顶尖，换无质变 |
| writer-self-check 模式 | 默认全量，可降级采样 | 关键可观测信号，不能省 |
| 重写次数上限 | 3 轮 | 平衡效果与成本 |

---

## 15. 后续步骤

1. 用户 review 本 spec
2. 调用 superpowers:writing-plans skill 生成 5 周 implementation plan
3. 按 M1 → M5 顺序执行；每 milestone 结束 user 验收
4. M3 dry-run 数据回归本 spec，决定是否调整阈值

---

## 附录 A：关联文档

- `docs/editor-wisdom-integration.md` — 现有编辑智慧管线
- `docs/rag-and-config.md` — 现有 RAG 与配置
- `docs/references/review-history-library.md` — 现有审查历史 schema
- `ink-writer/skills/ink-learn/SKILL.md` — 现有学习模块
- `prd.json` — Ralph PRD
- `CLAUDE.md` — 项目开发指南（含 Windows 兼容守则）
