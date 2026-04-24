# M2 数据资产 — 切片管线 + 病例库种子 (Design Spec)

**Status**: ready-for-plan
**Date**: 2026-04-24
**Author**: cipher-wb（产品）+ brainstorming co-pilot
**Baseline**: v23.0.0 + M1 (`m1-foundation` tag)
**Target version**: v24.x（5 周 M1-M5 的第 2 步）
**Quality target**: 段落级范文召回可用 + 病例库 ≥ 100 active cases

---

## 1. 背景与问题陈述

### 1.1 M1 已交付（前提）

- Case Library 基础设施可用：CaseStore + CaseIndex + ingest_case + CLI（list/show/create/status/rebuild-index）
- Qdrant 替代 FAISS：单机 docker，已建 `editor_wisdom_rules` 与 `corpus_chunks` 两个 collection（`CORPUS_CHUNKS_SPEC` 已 freeze）
- Preflight 6 项健康检查 + 自动建 infra_health 病例 + 已写入 `ink-write` Step 0
- reference_corpus 软链接修复（1487 章节文件可读）
- CASE-2026-0000 零号病例（infra_health 第一案）已入库
- M1 验收：`pytest -q` 全绿、coverage 82.72%、`m1-foundation` git tag 已打

### 1.2 M2 要解决的问题

M1 完成时 case_library 仅有 **1 个 case（zero-case）**，Qdrant 的 `corpus_chunks` collection **完全为空**。M3 P1 下游闭环（`writer-self-check` / 病例反向召回）需要"真实数据"才能工作——具体来说：

- 段落级范文 chunks（带 `quality_score / genre / scene_type / borrowable_aspects`）让 writer 能"按场景借鉴"
- 病例库 ≥ 100 active cases 让 polish-agent 能"按 case 驱动重写"

M2 的使命就是把现有的两份"原始资产"加工成 M3 可消费的形态：

| 原始资产 | M2 加工动作 | M2 产物 |
|---|---|---|
| `benchmark/reference_corpus/` 30 本 (≈ 900 章 / 1487 文件) | 切片 + 打标 + 向量化 | ≈ 2700 chunks 入 Qdrant |
| `data/editor-wisdom/rules.json` (402 条) | rule → case 转换 + severity 分流 | 402 cases (≈ 236 active + 166 pending) |

### 1.3 与原 spec §6/§9 的偏差

原 spec 写"288 条 editor-wisdom rules"，brainstorm 中实测 v23 已有 **402 条**（数据自然增长）。原 spec 假设的 `scoring_dimensions` 字段实际不存在（v23 实际 schema 是 `id/category/rule/why/severity/applies_to/source_files`）。本 spec 用 `severity` 字段做 active/pending 分流，更直接也更忠实于现状。

### 1.4 设计原则

1. **复用 M1 已建组件**（`ingest_case` / `CORPUS_CHUNKS_SPEC` / `CaseStore`），不重建任何基础设施
2. **占位优于过度设计**：observable 字段先放占位文本，M3 dry-run 后基于真实日志细化
3. **YAGNI**：user_corpus / interactive 审批 / 起点 top 200 简介库等留给 M4/M5
4. **跨平台**：所有新 CLI / 脚本遵守 CLAUDE.md Windows 兼容守则
5. **可观测**：每次摄入都产出 ConvertReport / IngestReport，便于审计

---

## 2. 整体架构

### 2.1 数据流

```
原始资产 1: benchmark/reference_corpus/<book>/chapters/*.txt
                                              (M1 修好的 1487 文件)
  │
  ▼
[scene_segmenter Haiku] 识别 8 种场景边界 + 200-800 字
  │
  ▼ chunks_raw.jsonl  (chunk_id, source_book, source_chapter, char_range, text)
  │
  ▼
[chunk_tagger Haiku] 8 种 scene_type + 4 维 quality_score + multi-value genre
                     + borrowable_aspects + tension/dialogue 等
  │
  ▼ chunks_tagged.jsonl  (新增 7 字段)
  │
  ▼
[chunk_indexer Qwen3-Embedding-8B] 向量化 → Qdrant CORPUS_CHUNKS_SPEC
  │
  ▼ data/corpus_chunks/{metadata.jsonl, qdrant collection}


原始资产 2: data/editor-wisdom/rules.json (402 条)
  │
  ▼
[rules_to_cases 转换器] rule → case + severity 分流
  │
  ▼ severity=hard → status=active (≈ 236 案)
    severity=soft → status=pending (≈ 147 案)
    severity=info → status=pending + tag=info_only (≈ 19 案)
  │
  ▼
data/case_library/cases/CASE-2026-NNNN.yaml
```

### 2.2 七大组件

| # | 组件 | 职责 |
|---|---|---|
| 1 | `scripts/corpus_chunking/scene_segmenter.py` | LLM 切场景边界 → chunks_raw.jsonl |
| 2 | `scripts/corpus_chunking/chunk_tagger.py` | LLM 打 scene_type/genre/quality/borrowable_aspects |
| 3 | `scripts/corpus_chunking/chunk_indexer.py` | Qwen3 向量化 + Qdrant upsert |
| 4 | `scripts/corpus_chunking/embedding_client.py` | Qwen3 API 封装 + 退避重试 |
| 5 | `scripts/corpus_chunking/cli.py` | `ink corpus ingest / rebuild / watch` |
| 6 | `ink_writer/case_library/rules_to_cases.py` + cli 扩展 | rule → case 转换 + `ink case convert-from-editor-wisdom` + `ink case approve --batch` |
| 7 | `tests/integration/test_m2_e2e.py` | M2 端到端验收 |

### 2.3 与 M1 资产复用

| M1 资产 | M2 中的角色 | 改不改 |
|---|---|---|
| `ink_writer/case_library/{store, schema, ingest, models}` | `rules_to_cases` 直接复用 `ingest_case` | 不动 |
| `ink_writer/qdrant/{client, payload_schema}` | `chunk_indexer` 直接复用 `CORPUS_CHUNKS_SPEC` + `ensure_collection` | 不动 |
| `ink_writer/preflight/cli` | `corpus ingest` 启动前可选调健康检查 | 不动 |
| `scripts/maintenance/fix_reference_corpus_symlinks.py` | M2 ingest 实跑前 dev 环境前置 | 不动 |
| `scripts/case_library/init_zero_case.py` | 不动；M2 创建业务 case 从 0001 起 | 不动 |
| FAISS 旧索引 | 不动并存；spec §8 双写策略 | 不动 |

### 2.4 边界（明确不做的事）

- ❌ 不做召回路由改造（`router.py` 加 case_aware/genre_filtered）→ M3
- ❌ 不做 writer 侧注入修改（`writer_injection.py`）→ M3
- ❌ 不做病例反向召回接线（`case_retriever.py`）→ M3
- ❌ 不做 user_corpus 接口 → M5
- ❌ 不做起点 top 200 简介库 → M4
- ❌ 不退役 FAISS（保留双写）
- ❌ 不做 `ink case approve --interactive` 模式 → M5（dashboard 配套）
- ❌ 不用 LLM 自动抽 observable → M3+ 按需

---

## 3. 切片管线详细设计

### 3.1 scene_segmenter

**输入**：`benchmark/reference_corpus/<book>/chapters/chXXX.txt` 一章
**输出**：1 章 → 3-6 个 chunks，append 到 `data/corpus_chunks/chunks_raw.jsonl`

**Prompt 关键约束**（写入 `prompts/scene_segmenter.txt`）：
- 识别 8 种场景边界：`opening / face_slap / flexing / emotional_climax / twist / combat / crisis / chapter_hook`
- 每个 chunk 200-800 字（< 200 合并到相邻；> 800 按句号边界二次切分）
- 必须输出 `char_range: [start, end]`（可追溯）
- 严格 JSON 输出（出错重试 3 次 → 跳过该章 + 写 `failures.jsonl`，不阻断）

**chunk_id 规则**：
```
"CHUNK-{book}-{chXXX}-§{N}"        (字符串形式，N 是章节内序号 1..M)
进 Qdrant 时转 UUID5(NAMESPACE_URL, chunk_id)   (沿用 M1 US-013 的幂等 pattern)
```

**幂等性**：同一 (book, chapter, content_hash) → 相同 chunk_id 序列。重跑覆盖原数据。

### 3.2 chunk_tagger

**输入**：`chunks_raw.jsonl` 一行
**输出**：原 chunk + 7 个新字段，写入 `chunks_tagged.jsonl`

**新增字段 schema**：

```json
{
  "chunk_id": "CHUNK-诡秘之主-ch003-§2",
  "source_book": "诡秘之主",
  "source_chapter": "ch003",
  "char_range": [1234, 1890],
  "text": "...",
  "scene_type": "identity_reveal",
  "genre": ["异世大陆", "玄幻"],
  "tension_level": 0.85,
  "character_count": 1,
  "dialogue_ratio": 0.0,
  "hook_type": "identity_secret",
  "borrowable_aspects": ["psychological_buffer", "sensory_grounding", "emotional_progression"],
  "quality_score": 0.92,
  "quality_breakdown": {
    "tension": 0.95,
    "originality": 0.90,
    "language_density": 0.92,
    "readability": 0.90
  },
  "source_type": "builtin",
  "ingested_at": "2026-04-25"
}
```

**Prompt 关键约束**（`prompts/chunk_tagger.txt`）：
- LLM 必须输出严格 JSON
- 4 维 quality_score 单独打分（tension/originality/language_density/readability），tagger 内部加权（不依赖 LLM 自己加权）
- `genre` 字段从 `benchmark/reference_corpus/<book>/manifest.json` 继承（**不让 LLM 重判**），保证同书 chunks genre 一致

**Batch 策略**：5 chunks / 调用，节省 token 上下文费用

### 3.3 chunk_indexer

**输入**：`chunks_tagged.jsonl`
**输出**：Qdrant `corpus_chunks` collection（M1 已 ensure_collection）

**流程**：
1. 读 chunks_tagged.jsonl，按 256 一 batch
2. 每 batch：调 Qwen3-Embedding-8B (云 API) → 4096 维 vectors（embed_batch_size=32 与 API rate 对齐）
3. 构造 `qdrant_client.PointStruct(id=UUID5, vector=vec, payload=chunk_dict)`
4. `client.upsert(collection_name="corpus_chunks", points=batch)`
5. 同时把 chunk metadata append 到 `data/corpus_chunks/metadata.jsonl`（独立备份，便于离线复算）

**幂等性**：UUID5 derived from chunk_id → 重跑相同 chunk 覆盖同 point id

**失败处理**：
- Qwen API 限流（429）→ 指数退避（1s/2s/4s）重试 3 次
- Qdrant upsert 失败 → 退避重试 3 次 → 仍失败：写入 `data/corpus_chunks/unindexed.jsonl` + 跑结束时报告，不阻断

### 3.4 错误处理 / 幂等性矩阵

| 组件 | 失败场景 | 处理 |
|---|---|---|
| scene_segmenter | LLM JSON 解析失败 | 重试 3 → 跳过该章 + `failures.jsonl` |
| scene_segmenter | LLM 输出超 800 字 chunk | 二次切分（按句号边界）|
| chunk_tagger | LLM JSON 解析失败 | 重试 3 → 标 `quality_score=0.0, tags=["tagging_failed"]`，仍入 jsonl（不丢数据）|
| chunk_indexer | Embedding API 限流 | 指数退避 |
| chunk_indexer | Qdrant upsert 失败 | 退避重试 → 写 `unindexed.jsonl` |

**关键不变量**：`chunks_raw.jsonl ⊇ chunks_tagged.jsonl ⊇ Qdrant collection`（原文永远存在，tagger 失败不丢原 chunk，indexer 失败不丢 tagged chunk）

### 3.5 配置 (`config/corpus_chunking.yaml`)

```yaml
scene_segmenter:
  model: claude-haiku-4-5-20251001
  min_chunk_chars: 200
  max_chunk_chars: 800
  max_retries: 3
chunk_tagger:
  model: claude-haiku-4-5-20251001
  batch_size: 5
  quality_weights:
    tension: 0.3
    originality: 0.3
    language_density: 0.2
    readability: 0.2
  max_retries: 3
chunk_indexer:
  embedding_model: Qwen/Qwen3-Embedding-8B
  embedding_base_url: https://api-inference.modelscope.cn/v1
  qdrant_collection: corpus_chunks
  upsert_batch_size: 256
  embed_batch_size: 32
```

热更新：跑前修改 yaml 就生效。

### 3.6 钩子插入点

| 文件 | 改动 |
|---|---|
| `scripts/corpus_chunking/__init__.py` | **新增** |
| `scripts/corpus_chunking/scene_segmenter.py` | **新增** |
| `scripts/corpus_chunking/chunk_tagger.py` | **新增** |
| `scripts/corpus_chunking/chunk_indexer.py` | **新增** |
| `scripts/corpus_chunking/embedding_client.py` | **新增**（Qwen API 封装 + 退避）|
| `scripts/corpus_chunking/prompts/scene_segmenter.txt` | **新增** |
| `scripts/corpus_chunking/prompts/chunk_tagger.txt` | **新增** |
| `config/corpus_chunking.yaml` | **新增** |
| `data/corpus_chunks/` | **新增产物目录** |
| `tests/corpus_chunking/` | **新增** + 注册到 `pytest.ini` testpaths |

---

## 4. CLI 设计

### 4.1 `ink corpus` 三件套

#### a) `ink corpus ingest`

```bash
ink corpus ingest                              # 默认全量摄入 reference_corpus
ink corpus ingest --book 诡秘之主              # 只摄入指定书
ink corpus ingest --book 诡秘之主 --resume     # 断点续摄（跳过已 indexed 章节）
ink corpus ingest --dir <path>                 # 摄入自定义目录（M5 user_corpus 复用）
ink corpus ingest --dry-run                    # 只跑 segmenter+tagger，不写 Qdrant
```

**输出格式**：
```
[1/30] 诡秘之主            chunks=87  tagged=87  indexed=87  failures=0
[2/30] 1979黄金时代        chunks=92  tagged=92  indexed=92  failures=0
...
TOTAL chunks=2734  tagged=2730  indexed=2728  failures=4
```

**退出码**：0 全成功 / 1 有 failures（不阻断）/ 2 致命错误（如 Qdrant 不可达）

#### b) `ink corpus rebuild`

```bash
ink corpus rebuild --yes                       # 必须 --yes 才执行
ink corpus rebuild --yes --book 诡秘之主       # 只重建一本
```

**流程**：confirm `--yes` → 删除 metadata jsonl 文件 → `client.delete_collection("corpus_chunks")` + `ensure_collection(CORPUS_CHUNKS_SPEC)` 重建 → 调 ingest 全量

#### c) `ink corpus watch`

```bash
ink corpus watch --dir <path> --interval 30    # 默认 30 秒扫一次
```

**流程**：polling 扫描 mtime + content hash → 变化触发 ingest 单文件 → Ctrl+C 优雅退出

**为什么 polling 不用 watchdog**：跨平台行为不一致；spec §6.4 实时性要求不高，polling 30s 简单可靠

### 4.2 `ink case approve --batch <yaml>`

**Batch yaml 模式**（M2 主推）：

```yaml
# tasks/m2-case-approval-batch-1.yaml
approvals:
  - case_id: CASE-2026-0042
    action: approve         # pending → active
  - case_id: CASE-2026-0043
    action: reject          # pending → retired
  - case_id: CASE-2026-0044
    action: defer           # pending → pending + 写 notes
    note: "需要看 M3 dry-run 是否真有这种失败模式"
```

**流程**：读 yaml + schema 校验 → 逐 case load → 改 status → save → append_ingest_log → 输出每 case 一行结果 + 总统计

### 4.3 CLI 错误处理统一规则

| 场景 | 行为 |
|---|---|
| Qdrant 不可达 | rc=2 + 提示"先 `scripts/qdrant/start.sh`" |
| EMBED_API_KEY 缺失 | rc=2 + 提示"在 .env 设 EMBED_API_KEY" |
| LLM 调用失败 | 重试 3 次后跳过该单元，写 failures.jsonl，最后报告 |
| yaml 校验失败 | rc=3 + stderr 显示具体哪行错 |
| Ctrl+C | 优雅退出（保存当前进度，下次 `--resume` 续上）|

### 4.4 钩子插入点

| 文件 | 改动 |
|---|---|
| `scripts/corpus_chunking/cli.py` | **新增**（含 ingest/rebuild/watch 三子命令）|
| `ink_writer/case_library/cli.py` | 扩展（新增 `approve --batch` + `convert-from-editor-wisdom` 子命令）|
| `schemas/case_approval_batch_schema.json` | **新增**（yaml 校验 schema）|
| `tests/corpus_chunking/test_cli.py` | **新增** |
| `tests/case_library/test_cli_approve.py` | **新增** |

---

## 5. rules → cases 转换器

### 5.1 v23 rules.json 实际 schema

```json
{
  "id": "EW-0001",
  "category": "taboo",                        // 14 类（含 v22 新增 prose_*）
  "rule": "用AI生成高潮情节的多个版本细纲...",
  "why": "编辑星河指出顶级作者的真实AI用法...",
  "severity": "hard",                          // hard/soft/info
  "applies_to": ["all_chapters"],              // all_chapters/golden_three/high_point/climax/combat
  "source_files": ["001_AI写小说...md"]
}
```

**总数 402 条**，severity 分布：
- `hard`: 236（硬约束，自动 active）
- `soft`: 147（软建议，pending 等审批）
- `info`: 19（信息性，pending + tag=info_only）

### 5.2 rule → case 字段映射

| rule 字段 | case 字段 | 处理 |
|---|---|---|
| `id` | `bound_assets.rules[0].rule_id` | 直传 |
| `category` | `tags[0]` + (severity-derived tag) | category 入 tags |
| `rule` | `failure_pattern.description` (前半) | 与 why 合并 |
| `why` | `failure_pattern.description` (后半) | + " — 理由：" + why |
| `severity` | `case.severity` + `case.status` | 见 5.3 分流 |
| `applies_to` | `scope.chapter` | 同名直传（Q9 决定）|
| `source_files` | `source.ingested_from` | 取 `source_files[0]` |
| (无) | `scope.genre` | 默认 `["all"]`（M2），M4 题材策划层细化 |
| (无) | `source.raw_text` | `rule + " | " + why`（sha256 dedup key）|
| (无) | `source.type` | 固定 `"editor_review"` |
| (无) | `source.reviewer` | 固定 `"星河编辑"` |
| (无) | `source.ingested_at` | 跑日期（today ISO）|
| (无) | `failure_pattern.observable` | 占位（见 5.4）|

### 5.3 severity → case.severity + case.status 分流

| rule.severity | case.severity | case.status | 数量 | 说明 |
|---|---|---|---|---|
| `hard` | **P1** | **active** | 236 | 硬约束直接生效 |
| `soft` | P2 | pending | 147 | 软建议待审批 |
| `info` | P3 | pending（额外 tag `info_only`）| 19 | 仅信息性参考 |

**M2 末尾 case 库状态**：236 active + 166 pending + CASE-2026-0000 = **237 active / 166 pending / 共 403 cases**——**远超 M-ROADMAP "≥ 100 active" 目标**。

> 接受的副作用：236 active rules 在 M3 上线时可能炸出大量阻断。spec §6.1 已声明 M3 强制 dry-run 1 周观察后切真阻断；M2 不需要额外护栏。

### 5.4 解决 schema 冲突：observable 必填 minItems:1

case schema 要求 `failure_pattern.observable` minItems:1，但 rule 的 `rule + why` 不是 observable 格式。

**采用占位策略**（YAGNI）：

```yaml
failure_pattern:
  description: "<rule> — 理由：<why>"
  observable:
    - "待 M3 dry-run 后基于实际触发样本细化（rule_id: EW-XXXX）"
```

理由：M3 dry-run 时每条 case 触发后会产生真实日志，从日志反推 observable check 比凭空设计更准。本期占位让 schema 校验通过即可。

### 5.5 ConvertReport

```python
@dataclass
class ConvertReport:
    created: int
    skipped: int          # already existed (sha256 dedup)
    failed: int           # validation / IO error
    by_severity: dict[str, int]  # {"hard": 236, "soft": 147, "info": 19}
    by_category: dict[str, int]  # {"opening": 102, "taboo": 73, ...}
    failures: list[tuple[str, str]]  # (rule_id, error_msg)
```

### 5.6 转换器 CLI

```bash
ink case convert-from-editor-wisdom                    # 默认从 v23 rules.json 全量
ink case convert-from-editor-wisdom --rules <path>     # 自定义 rules 文件
ink case convert-from-editor-wisdom --dry-run          # 只统计，不写
```

**幂等性**：基于 `raw_text = rule + " | " + why` 的 sha256 hash 去重（M1 US-007 ingest_case 已实现的机制）。重跑：所有 402 → `skipped=402, created=0`。

### 5.7 钩子插入点

| 文件 | 改动 |
|---|---|
| `ink_writer/case_library/rules_to_cases.py` | **新增** |
| `ink_writer/case_library/cli.py` | 扩展（新增 `convert-from-editor-wisdom` 子命令）|
| `tests/case_library/test_rules_to_cases.py` | **新增** |
| `data/case_library/cases/` | 跑后多 402 个 yaml 文件 |

---

## 6. 实施计划

### 6.1 12 US 顺序（按依赖关系）

| US | 标题 | 关键依赖 |
|---|---|---|
| US-001 | `scripts/corpus_chunking/` 包骨架 + config + 测试目录 + pytest.ini 注册 | M1 |
| US-002 | scene_segmenter（Haiku 切场景边界 + prompt + 重试 + failures.jsonl）| US-001 |
| US-003 | chunk_tagger（Haiku 打 6 标签 + 4 维加权 quality_score）| US-002 |
| US-004 | embedding_client + chunk_indexer（Qwen3 + Qdrant batch upsert + UUID5 幂等）| US-003 + M1 US-012 |
| US-005 | `ink corpus ingest` CLI（含 --book / --resume / --dry-run）| US-001~004 |
| US-006 | `ink corpus rebuild` CLI（含 --yes 防误触）| US-005 |
| US-007 | `ink corpus watch` CLI（polling 30s）| US-005 |
| US-008 | 30 本范文 ingest 实跑 + 抽样 50 chunks 人工核 + 入库验证 | US-005 |
| US-009 | `rules_to_cases.py` 转换器 + 单测 | M1 US-007 |
| US-010 | `ink case convert-from-editor-wisdom` CLI 集成 + 幂等测试 | US-009 |
| US-011 | `ink case approve --batch <yaml>` CLI（含 yaml schema 校验）| M1 US-008 |
| US-012 | M2 e2e 集成测试 + 全量验收 + tag `m2-data-assets` | 全部 |

### 6.2 e2e 测试设计（US-012）

```python
# tests/integration/test_m2_e2e.py
def test_chunking_pipeline_e2e_with_one_chapter(tmp_path):
    """1 章诡秘之主 → segmenter → tagger → indexer → 能从 Qdrant 检索回。"""

def test_rules_conversion_creates_402_cases_with_severity_split(tmp_case_dir):
    """v23 rules.json 全量 → assert by_severity={hard:236, soft:147, info:19}。"""

def test_active_pending_counts_after_conversion(tmp_case_dir):
    """assert active==237 (含 zero-case)，pending==166 (147 soft + 19 info)。"""

def test_approve_batch_yaml_changes_status(tmp_case_dir):
    """yaml 列 5 个 case + approve/reject/defer → 5 case status 正确改变。"""

def test_corpus_ingest_resume_skips_indexed_chapters(tmp_path):
    """第二次 ingest 跳过已 indexed 章节 → fixed=0 skipped=N。"""
```

### 6.3 工作量预估

| 类别 | 数量 |
|---|---|
| 新增 Python 模块 | 6 |
| 改造 Python 模块 | 1（`ink_writer/case_library/cli.py` 加 approve + convert）|
| 新增 prompts | 2 |
| 新增 config | 1 |
| 新增 testpaths | `tests/corpus_chunking` |
| 新增测试 | 8-10 个测试文件 |
| 新增 yaml schema | 1 |
| API 成本 | $3-10 实跑（切片+打标）+ 0（Qwen embedding 已含在 modelscope 订阅）|
| ralph 跑完时间 | 12 US × ~22 分钟 ≈ **4.5 小时** |

### 6.4 风险与护栏

| # | 风险 | 触发 | 护栏 |
|---|---|---|---|
| 1 | LLM 切片误切（边界判断错）| scene_segmenter 输出 < 200 / > 800 字 | 二次切分 + quality_score < 0.6 进人工复审；US-008 实跑后抽 50 chunks 人工核 |
| 2 | 236 hard rules 一次 active 在 M3 炸大量阻断 | M3 dry-run 上线日 | spec §6.1 已声明 M3 dry-run 1 周观察，M2 不需额外护栏（设计意图）|
| 3 | placeholder observable 在 M3 前看着像没填完 | 任何时候 | 文本明确写"待 M3 dry-run 后基于实际触发样本细化（rule_id: EW-XXXX）"，不会被误用 |
| 4 | Qwen3-Embedding API 限流 | 大批量入库 | embedding_client 内置指数退避；batch 32 与 API rate limit 对齐 |
| 5 | Qdrant collection 容量爆炸 | US-008 实跑 | 4096 维 × 2700 ≈ 80 MB，单机 Docker 远够；监控 `du -sh scripts/qdrant/storage/` |
| 6 | rules.json 字段未来变更 | 跨版本 | rules_to_cases 只用 7 个字段，新字段被忽略不破坏 |
| 7 | 同 rule+why 重复出现（rules.json 内部重复）| 当前 v23 数据 | sha256 dedup 自动处理；ConvertReport 报告 skipped 数量 |
| 8 | watch 模式 polling 30s 漏掉新文件 | mtime 精度问题 | 用 hash 而非纯 mtime（双保险）；spec §6.4 实时性要求不高 |

### 6.5 验收标准（M2 结束）

| 指标 | 验收线 |
|---|---|
| `pytest -q` 全绿 | 必过 + 覆盖率 ≥ 70（M1 baseline 82.72%）|
| Qdrant `corpus_chunks` 可检索 | `curl /collections/corpus_chunks/points/search` 返 200 |
| corpus chunks 入库数 | ≥ 2500（实测期望 ≈ 2700）|
| failures.jsonl 失败章节数 | < 30 章（占总 ~900 章节的 < 3.3%）|
| case 总数 | ≥ 400（402 业务 + zero-case ≈ 403 期望）|
| active cases | ≥ 200（236 hard + zero-case ≈ 237 期望）|
| pending cases | ≈ 166 |
| `ink corpus ingest --resume` 幂等 | 重跑 indexed 数不变 |
| `ink case convert-from-editor-wisdom` 幂等 | 重跑 created=0 skipped=402 |
| `ink case approve --batch` 可用 | 5 case yaml 跑通 |
| `git tag m2-data-assets` | 已打 |

### 6.6 不在本期范围

- ❌ 召回路由改造 → M3
- ❌ writer 侧注入修改 → M3
- ❌ 病例反向召回接线 → M3
- ❌ user_corpus 接口 → M5
- ❌ 起点 top 200 简介库 → M4
- ❌ FAISS 退役（双写保留）→ 待 M3 决定
- ❌ ink case approve interactive → M5
- ❌ 用 LLM 自动抽 observable → M3+ 按需

---

## 7. 关键决议记录

| 决议 | 选择 | 决议依据 |
|---|---|---|
| 切片模型 | Haiku 4.5 全程（Q1）| 场景边界识别本质是分类，Haiku 够用；总成本 < $10 |
| chunk 字数范围 | 200-800 字（Q2）| spec §6.1 默认；适合"完整场景单元" |
| 切片处理顺序 | 一次全切（Q3）| 节省切换开销；信任质量护栏（quality_score < 0.6 复审）|
| scene_type 标签集合 | spec §6.1 默认 8 种（Q4）| YAGNI；M3 dry-run 后视召回率扩展 |
| quality_score 算法 | 4 维加权（tension/originality/language_density/readability）（Q5）| 4 维直接对应编辑扣分项；分维度便于 M3 调权 |
| genre 标签来源 | 复用 `manifest.json` + 校对（Q6）| 作者权威标注；多值；半小时校对 |
| rules → cases 粒度 | 一对一 402 case（Q7）| 忠实原始规则；可追溯；M-ROADMAP "≥ 100 active" 轻松达成 |
| 转换后默认状态 | severity-based 分流（Q8 修订）| v23 没 scoring_dimensions；severity 字段更直接 |
| applies_to 映射 | 同名直传（Q9）| editor-wisdom v22 已与 case scope.chapter enum 完全对齐 |
| 起点 top 200 简介库 | 移到 M4（Q10）| M2 用不到，M4 `genre-novelty-checker` 才用 |
| API 成本预算 | < $30（Q11）| 实测 $3-5 即可，预算容多次试错 |
| M1 → M2 联调测试 | 不补（Q12）| M1 US-017 已覆盖核心链路；M2 US-009 本身是大型 integration |
| 整体范围 | 方案 B 标准版 12 US | 忠实 spec §9 M2；不提早做 M5 内容 |
| observable 字段 | 占位 + M3 细化 | YAGNI；M3 dry-run 日志反推更准 |

---

## 8. 后续步骤

1. 用户 review 本 spec
2. 调用 `superpowers:writing-plans` skill 生成 12-task implementation plan
3. `/prd` → `tasks/prd-m2-data-assets.md`
4. `/ralph` → `prd.json` + branch `ralph/m2-data-assets`
5. 后台启动 ralph：`bash scripts/ralph/ralph.sh --tool claude 12`
6. M2 跑完后：验收 + 打 tag `m2-data-assets` + 更新 `M-ROADMAP.md`（M2 ✅）
7. 进入 M3（依赖 M1 + M2，是 30 → 50 分质量拐点）

---

## 附录 A：关联文档

- `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` — M1-M5 总 spec（§6 P2 + §9 M2）
- `docs/superpowers/M-ROADMAP.md` — 5 周 milestone 进度跟踪
- `docs/superpowers/M2-PREPARATION-NOTES.md` — M2 brainstorm 准备材料（12 题已答完）
- `docs/superpowers/plans/2026-04-23-m1-foundation-and-qdrant-migration.md` — M1 实施 plan（已完成）
- `data/editor-wisdom/rules.json` — 输入资产（402 条规则）
- `benchmark/reference_corpus/` — 输入资产（30 本范文 / 1487 章节）
- `prd.json` / `progress.txt` — ralph 当前 PRD 与跨迭代记忆
