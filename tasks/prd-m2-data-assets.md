# PRD: M2 Data Assets — Corpus Chunking + Cases Conversion

## Introduction

落地 spec §9 M2（详见 `docs/superpowers/specs/2026-04-24-m2-data-assets-design.md`）：把 30 本范文（M1 修好的 1487 章节文件）加工成段落级 chunks（带 4 维加权 quality_score + multi-value genre + 8 种 scene_type）入 Qdrant，把 402 条 editor-wisdom rules 按 severity 分流转换为 case_library 中的 cases（236 active P1 + 147 pending P2 + 19 pending P3+info_only），让 M3 P1 下游闭环（writer-self-check + 病例反向召回）有真实数据可用。

本期不做：M3-M5 内容（router 改造 / writer 注入 / user_corpus / 起点 top200 / interactive 审批 / FAISS 退役）。

详细 plan：`docs/superpowers/plans/2026-04-24-m2-data-assets.md`（2999 行 / 12-task TDD）。

## Goals

- 30 本范文切片入 Qdrant `corpus_chunks` collection，≥ 2500 chunks 可检索
- 402 条 editor-wisdom rules 按 severity 分流转 cases（236 active + 166 pending）
- 三个新 CLI 子命令可用：`ink corpus ingest/rebuild/watch` + `ink case approve --batch` + `ink case convert-from-editor-wisdom`
- 复用 M1 已建组件（ingest_case / Qdrant CORPUS_CHUNKS_SPEC / preflight），不重建任何基础设施
- 跨平台（macOS + Windows 11）行为一致，遵守 CLAUDE.md Windows 兼容守则
- API 成本一次实跑 < $30（实测预期 $3-10 / Haiku 全程）

## User Stories

### US-001: corpus_chunking 包骨架 + config + 测试目录
**Description:** 作为开发者，我需要先把 corpus_chunking 包骨架 + dataclasses + config + pytest 注册做好，让后续 11 个 task 的 TDD 步骤能直接跑测试。

**Acceptance Criteria:**
- [ ] 新增 `scripts/corpus_chunking/__init__.py` + `scripts/corpus_chunking/models.py` + `scripts/corpus_chunking/prompts/.gitkeep` + `tests/corpus_chunking/__init__.py` + `tests/corpus_chunking/conftest.py`
- [ ] `models.py` 暴露 `RawChunk` / `TaggedChunk` / `QualityBreakdown` / `IngestReport` / `SourceType` 5 个类型；`TaggedChunk.quality_score` property 用 4 维加权（默认 30/30/20/20）
- [ ] 新增 `config/corpus_chunking.yaml`：scene_segmenter / chunk_tagger / chunk_indexer 三段配置（spec §3.5）
- [ ] `pytest.ini` 的 testpaths 行尾追加 `tests/corpus_chunking`（保持单行不换行）
- [ ] 新增 `tests/corpus_chunking/test_models.py` 含 3 用例：`test_raw_chunk_serializes` / `test_tagged_chunk_round_trip`（验加权计算）/ `test_ingest_report_aggregates`
- [ ] `pytest tests/corpus_chunking/test_models.py -v --no-cov` 输出 3 passed
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes

### US-002: scene_segmenter（Haiku 切场景边界）
**Description:** 作为切片管线第一段，我需要 scene_segmenter 用 Haiku 4.5 识别 8 种场景边界（opening / face_slap / flexing / emotional_climax / twist / combat / crisis / chapter_hook），切成 200-800 字 RawChunk 列表，超长按句号边界二次切分。

**Acceptance Criteria:**
- [ ] 新增 `scripts/corpus_chunking/scene_segmenter.py` 暴露 `segment_chapter(*, client, cfg, book, chapter, text) -> list[RawChunk]` + `SegmenterConfig` dataclass
- [ ] 新增 `scripts/corpus_chunking/prompts/scene_segmenter.txt` 含 8 种 scene_type 列表 + 切片规则 + 严格 JSON 输出格式 + `{book}/{chapter}/{chapter_text}` 占位符
- [ ] chunk_id 规则：`CHUNK-{book}-{chapter}-§{N}`（章节内序号 1..M）
- [ ] JSON 解析失败重试 max_retries 次；仍失败返空列表（caller 决定写 failures.jsonl）
- [ ] 输出 chunk > max_chunk_chars 自动按句号边界二次切分（找最近的 。/！/？）
- [ ] 新增 `tests/corpus_chunking/test_scene_segmenter.py` 含 4 用例：`test_segment_chapter_happy_path` / `test_segment_retries_on_invalid_json` / `test_segment_returns_empty_after_max_retries` / `test_segment_rechunks_oversize_output`
- [ ] `pytest tests/corpus_chunking/test_scene_segmenter.py -v --no-cov` 输出 4 passed
- [ ] `pytest tests/audit/test_cli_entries_utf8_stdio.py tests/core/test_safe_symlink.py` 全绿（audit 红线扫全仓 .py）
- [ ] Typecheck passes

### US-003: chunk_tagger（Haiku 打 6 标签 + 4 维加权 quality_score）
**Description:** 作为切片管线第二段，我需要 chunk_tagger 用 Haiku 给 RawChunk 打 6 个标签（scene_type / tension_level / character_count / dialogue_ratio / hook_type / borrowable_aspects）+ 4 维 quality_breakdown（tension/originality/language_density/readability），genre 不让 LLM 判（防跨书漂移）从 caller 传入。

**Acceptance Criteria:**
- [ ] 新增 `scripts/corpus_chunking/chunk_tagger.py` 暴露 `tag_chunk(*, client, cfg, chunk, genre, ingested_at, source_type) -> TaggedChunk` + `TaggerConfig` dataclass
- [ ] 新增 `scripts/corpus_chunking/prompts/chunk_tagger.txt` 含 6 标签 + 4 维度独立打分 + 严格 JSON 输出格式
- [ ] 4 维加权由 tagger 内部完成（不依赖 LLM 自己加权），权重从 cfg.quality_weights 读取
- [ ] genre 字段从 caller 传入（manifest.json 继承），LLM 输出不影响最终 chunk.genre
- [ ] LLM 失败重试后仍失败 → 返回 scene_type=`tagging_failed` + quality_score=0 + borrowable_aspects=[`tagging_failed`] 的 TaggedChunk（不丢数据，schema 仍合法）
- [ ] 新增 `tests/corpus_chunking/test_chunk_tagger.py` 含 3 用例：`test_tag_chunk_happy`（验加权分 0.83 = 0.9*0.3+0.8*0.3+0.7*0.2+0.9*0.2）/ `test_tag_chunk_failure_returns_zero_quality` / `test_tag_chunk_uses_passed_genre_not_llm`
- [ ] `pytest tests/corpus_chunking/test_chunk_tagger.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes

### US-004: embedding_client + chunk_indexer
**Description:** 作为切片管线第三段，我需要 EmbeddingClient（Qwen3-Embedding-8B / modelscope endpoint，含 batching + 指数退避重试）+ chunk_indexer（TaggedChunk → 向量化 → Qdrant batch upsert，UUID5 幂等，metadata.jsonl 备份，失败 chunks 落 unindexed.jsonl）。

**Acceptance Criteria:**
- [ ] 新增 `scripts/corpus_chunking/embedding_client.py` 暴露 `EmbeddingClient` + `EmbeddingConfig` + `EmbeddingError`；`embed_batch(texts, *, _sleep=time.sleep) -> list[list[float]]`，按 batch_size 分批，每批 max_retries+1 次重试退避（1s/2s/4s）
- [ ] 新增 `scripts/corpus_chunking/chunk_indexer.py` 暴露 `index_chunks(*, chunks, qdrant_client, embedder, cfg, metadata_path, unindexed_path) -> int`（返回成功 indexed 数）+ `IndexerConfig` + `_stable_uuid_from_id(chunk_id)`
- [ ] point id 用 `uuid.uuid5(NAMESPACE_URL, chunk_id)` 字符串保证幂等；payload 用 `chunk.to_dict()` 全量
- [ ] Qdrant upsert 失败的 batch → chunks 写入 `unindexed_path` jsonl（单行 `{chunk_id, error}`）；不阻断后续 batches
- [ ] 成功 indexed 的 chunks 同时 append 到 `metadata_path` jsonl（独立备份）
- [ ] 新增 `tests/corpus_chunking/test_embedding_client.py` 含 4 用例：`test_embed_batch_returns_vectors` / `test_embed_batch_chunks_input_by_batch_size`（5 条 batch_size=2 → 3 calls）/ `test_embed_retries_on_429` / `test_embed_raises_after_max_retries`
- [ ] 新增 `tests/corpus_chunking/test_chunk_indexer.py` 含 4 用例：`test_index_chunks_upserts_to_qdrant` / `test_index_chunks_writes_metadata_jsonl` / `test_index_chunks_records_qdrant_failure_in_unindexed` / `test_index_chunks_uuid5_is_idempotent_id`
- [ ] `pytest tests/corpus_chunking/test_embedding_client.py tests/corpus_chunking/test_chunk_indexer.py -v --no-cov` 输出 8 passed
- [ ] Typecheck passes

### US-005: ink corpus ingest CLI
**Description:** 作为运维者，我需要 `ink corpus ingest` CLI 串起 segmenter → tagger → indexer，支持 `--book` 单本摄入、`--resume` 断点续摄、`--dry-run` 不写 Qdrant 验证质量、`--dir` 自定义目录（M5 user_corpus 复用）。

**Acceptance Criteria:**
- [ ] 新增 `scripts/corpus_chunking/cli.py` 暴露 `main(argv) -> int` 永不 raise（顶层 try/except SystemExit 转 rc）
- [ ] argparse 顶层 `--config`（默认 `config/corpus_chunking.yaml`）+ subparsers `ingest/rebuild/watch`
- [ ] `ingest` 子命令 args：`--dir`（默认 `benchmark/reference_corpus`）/ `--book`（过滤单本）/ `--resume` / `--dry-run`
- [ ] 单本摄入流程：`_read_manifest_genre(book_dir)` → 顺序处理 `chapters/ch*.txt` → `segment_chapter` → `tag_chunk` → `index_chunks`（除非 --dry-run）→ append jsonl 文件
- [ ] `--resume` 调 `_already_indexed(book, chapter, chunks_raw.jsonl)` 跳过已 indexed 章节
- [ ] segmenter 失败章节 → 写 `failures.jsonl`（含 book/chapter/error），不阻断后续章节
- [ ] 输出格式：每书一行 `[i/N] {book:25s} chunks=N tagged=N indexed=N failures=N` + 末尾 `TOTAL chunks=N tagged=N indexed=N failures=N`
- [ ] sys.path 三段式 bootstrap（`_REPO_ROOT` + `_INK_SCRIPTS`）+ 顶层调 `enable_windows_utf8_stdio()`（audit 红线要求）
- [ ] 新增 `tests/corpus_chunking/test_cli.py` 含 2 用例：`test_ingest_dry_run_does_not_call_qdrant`（mock anthropic + 验证 build_qdrant_client / build_embedding_client 未被调）/ `test_ingest_resume_skips_indexed_chapters`（直接测 `_already_indexed` helper）
- [ ] `pytest tests/corpus_chunking/test_cli.py -v --no-cov` 输出 2 passed
- [ ] `pytest tests/audit/test_cli_entries_utf8_stdio.py tests/core/test_safe_symlink.py` 全绿
- [ ] Typecheck passes

### US-006: ink corpus rebuild CLI
**Description:** 作为运维者，我需要 `ink corpus rebuild --yes` 在防误触前提下清空 corpus_chunks collection + 删除 5 个 jsonl 文件 + 重新 ensure_collection + 触发 ingest 全量；支持 `--book` 仅清理单本不动 collection。

**Acceptance Criteria:**
- [ ] 替换 `_cmd_rebuild` stub 为完整实现：无 `--yes` → rc=2 + stderr 提示
- [ ] `--yes` 全量：删 chunks_raw.jsonl / chunks_tagged.jsonl / metadata.jsonl / failures.jsonl / unindexed.jsonl 5 个文件 → `qdrant.delete_collection("corpus_chunks")`（容错：不存在不阻断）→ `ensure_collection(CORPUS_CHUNKS_SPEC)` 重建 → 调 `_cmd_ingest` 重新摄入
- [ ] `--yes --book <name>`：仅 filter 3 个 jsonl 文件中非该书的行后写回，不动 collection（单书清理）
- [ ] 追加 2 用例到 `tests/corpus_chunking/test_cli.py`：`test_rebuild_without_yes_refuses` / `test_rebuild_with_yes_clears_collection`（mock `_build_qdrant_client` + `_cmd_ingest`，验 `qdrant.delete_collection` 被调）
- [ ] `pytest tests/corpus_chunking/test_cli.py -v --no-cov` 输出 4 passed
- [ ] Typecheck passes

### US-007: ink corpus watch CLI（polling 30s）
**Description:** 作为运维者，我需要 `ink corpus watch --dir <path>` 用 polling（默认 30s）扫描 mtime 变化，新文件或 mtime 变化触发 `_ingest_single_file`（resume 模式），Ctrl+C 优雅退出。`--iterations` 仅供测试 break 循环。

**Acceptance Criteria:**
- [ ] 替换 `_cmd_watch` stub + 新增 `_ingest_single_file(file_path, cfg)` helper
- [ ] argparse `watch` 子命令：`--dir` 必填 / `--interval` 默认 30 / `--iterations` 默认 -1（无限）
- [ ] 启动时记录 `seen: dict[Path, float]` mtime；每次循环 rglob `*.txt` 比对 mtime，新增/变化 → 触发 `_ingest_single_file`
- [ ] `_ingest_single_file` 失败时 stderr warn 不阻断后续循环
- [ ] `KeyboardInterrupt` 优雅退出 + stderr 提示
- [ ] `_ingest_single_file` 推断 `book_dir = file_path.parent.parent` + 调 `_ingest_book(resume=True, dry_run=False)`
- [ ] 追加 1 用例到 `tests/corpus_chunking/test_cli.py`：`test_watch_detects_new_file_and_triggers_ingest`（patch `_ingest_single_file` + iterations=2 + interval=0）
- [ ] `pytest tests/corpus_chunking/test_cli.py -v --no-cov` 输出 5 passed
- [ ] Typecheck passes

### US-008: 30 本范文 ingest 实跑 + 抽样 50 chunks 人工核
**Description:** 作为质量验收者，我需要把 30 本范文（M1 修好的 1487 章节文件）真跑一遍 ingest，验证 Qdrant `corpus_chunks` collection points_count ≥ 2500 + 抽样 50 chunks 人工核 scene_type 合理度 ≥ 80% + failures < 30 章 + unindexed < 5 chunks。

**Acceptance Criteria:**
- [ ] 启动 Qdrant：`scripts/qdrant/start.sh` 后 `curl -s http://127.0.0.1:6333/readyz` 返 200
- [ ] EMBED_API_KEY 已在 `.env` 配置（按 `docs/rag-and-config.md`）
- [ ] 单本 dry-run smoke：`python -m scripts.corpus_chunking.cli ingest --book 诡秘之主 --dry-run` 输出非空 + `data/corpus_chunks/chunks_tagged.jsonl` 第一行解析后 scene_type 合理 / quality_score ∈ [0,1] / genre=["异世大陆"] / text 是真实诡秘之主原文
- [ ] 全量真跑：`rm data/corpus_chunks/{chunks_raw,chunks_tagged,metadata}.jsonl 2>/dev/null && python -m scripts.corpus_chunking.cli ingest 2>&1 | tee /tmp/m2_ingest.log`，输出 30 行进度 + 1 行 TOTAL，总 chunks ≥ 2500
- [ ] Qdrant collection 验证：`curl -s http://127.0.0.1:6333/collections/corpus_chunks` 返 `points_count >= 2500` 且 `status=green`
- [ ] 抽样 50 chunks（seed=42）人工浏览：scene_type 分类合理度 ≥ 80% / quality_score 分布合理 / 没有明显切坏的 chunks（写入 `/tmp/m2_sample_50.jsonl` + 自查）
- [ ] `wc -l data/corpus_chunks/failures.jsonl` < 30 章；`wc -l data/corpus_chunks/unindexed.jsonl` < 5
- [ ] 把实跑 stats（TOTAL chunks / Qdrant points / 抽样合理度 / failures / Learnings）追加到 `progress.txt`
- [ ] 实跑成本 < $30（实际 Haiku 估 $3-10）

### US-009: rules_to_cases 转换器 + 单测
**Description:** 作为转换器作者，我需要 `rules_to_cases.py` 把 editor-wisdom rules.json 按 `severity` 分流转 case：hard→active P1 / soft→pending P2 / info→pending P3+`info_only` tag；observable 用占位文本（含 rule_id）；基于 raw_text=`rule + " | " + why` 的 sha256 dedup（M1 ingest_case 已实现的机制）保证幂等。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/rules_to_cases.py` 暴露 `convert_rules_to_cases(*, rules_path, library_root, dry_run, ingested_at) -> ConvertReport` + `map_rule_to_case_kwargs(rule, *, ingested_at) -> dict` + `ConvertReport` dataclass
- [ ] `_SEVERITY_MAP = {"hard": ("P1", "active"), "soft": ("P2", "pending"), "info": ("P3", "pending")}`
- [ ] `map_rule_to_case_kwargs` 字段映射（spec §5.2）：
  - `tags = ["from_editor_wisdom", rule.category]`，severity=info 额外加 `info_only`
  - `failure_description = f"{rule} — 理由：{why}"` 若 why 非空否则只 rule
  - `raw_text = f"{rule} | {why}"`（dedup key）
  - `scope_chapter` = applies_to 同名直传，空时 `["all"]`
  - `scope_genre = ["all"]`（M2 默认）
  - `source.reviewer = "星河编辑"`、`source.ingested_from = source_files[0]` 或 None
  - `observable = [f"待 M3 dry-run 后基于实际触发样本细化（rule_id: {rule.id}）"]`
- [ ] `ConvertReport` 字段：created / skipped (sha256 dedup hit) / failed / by_severity / by_category / failures
- [ ] `dry_run=True` 时 created 计 "would-create" 数但不调 ingest_case；store 留空
- [ ] 新增 `tests/case_library/test_rules_to_cases.py` 含 6 用例：`test_map_hard_rule_to_active_p1` / `test_map_soft_rule_to_pending_p2` / `test_map_info_rule_to_pending_p3_with_info_only_tag` / `test_map_observable_uses_placeholder_with_rule_id` / `test_convert_creates_cases_idempotently`（连跑两次 → 第二次全 skipped）/ `test_convert_dry_run_does_not_write`
- [ ] `pytest tests/case_library/test_rules_to_cases.py -v --no-cov` 输出 6 passed
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes

### US-010: ink case convert-from-editor-wisdom CLI 集成
**Description:** 作为运维者，我需要 `ink case convert-from-editor-wisdom` 子命令调 `convert_rules_to_cases` 全量摄入 v23 `data/editor-wisdom/rules.json`，支持 `--rules` 自定义路径 + `--dry-run` 只统计；stdout 打印 `created=N skipped=N failed=N` + `by_severity={...}`。

**Acceptance Criteria:**
- [ ] 修改 `ink_writer/case_library/cli.py` 在 `_build_parser()` 内 `sub` 上加 `convert-from-editor-wisdom` 子命令：`--rules`（默认 `data/editor-wisdom/rules.json`）+ `--dry-run`
- [ ] `main()` dispatch 内追加：调 `convert_rules_to_cases` → 打印 `created=N skipped=N failed=N` + `by_severity={...}` + 失败前 10 条到 stderr → return 0 if failed==0 else 1
- [ ] 新增 `tests/case_library/test_cli_convert.py` 含 3 用例：`test_convert_subcommand_creates_cases`（2 条 rule yaml → assert created=2 + store.list_ids() len=2）/ `test_convert_idempotent`（第二次跑 skipped=1）/ `test_convert_dry_run`（store.list_ids() 空）
- [ ] 实跑 smoke：`python -m ink_writer.case_library.cli --library-root /tmp/m2_smoke convert-from-editor-wisdom --dry-run` 输出 `created=402 skipped=0 failed=0` + `by_severity={'hard': 236, 'soft': 147, 'info': 19}`
- [ ] `pytest tests/case_library/test_cli_convert.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes

### US-011: ink case approve --batch <yaml> CLI
**Description:** 作为人类审批者，我需要 `ink case approve --batch <yaml>` 一次性审批多个 pending case：approve→active / reject→retired / defer→pending+note。yaml schema 校验失败 rc=3；单 case 失败不阻断其余；ingest_log.jsonl 写 approval 事件审计。

**Acceptance Criteria:**
- [ ] 新增 `schemas/case_approval_batch_schema.json`：`approvals` array minItems=1，每项 required `case_id`（pattern `^CASE-[0-9]{4}-[0-9]{4}$`）+ `action` enum [approve/reject/defer]，可选 `note`，additionalProperties false
- [ ] 新增 `ink_writer/case_library/approval.py` 暴露 `apply_batch_yaml(*, yaml_path, library_root) -> ApprovalReport` + `ApprovalReport(applied, failed, failures)` dataclass
- [ ] `_ACTION_TO_STATUS = {"approve": ACTIVE, "reject": RETIRED, "defer": PENDING}`
- [ ] yaml 校验用 `Draft202012Validator(schema).validate(data)`（raises ValidationError）
- [ ] 逐 case：`store.load` → 改 `case.status` → `store.save` → `store.append_ingest_log({event:"approval", case_id, action, note, at: utc_iso})`；CaseNotFoundError / 其他异常计入 failures 不阻断
- [ ] 修改 `ink_writer/case_library/cli.py` 加 `approve` 子命令：`--batch <yaml_path>`；catch `ValidationError` rc=3，否则 rc=0/1（按 failed 数）
- [ ] 新增 `tests/case_library/test_cli_approve.py` 含 3 用例：`test_approve_batch_three_actions`（create 3 pending → yaml 三 action → assert 3 case status active/retired/pending）/ `test_approve_batch_invalid_yaml_returns_3` / `test_approve_batch_unknown_case_records_failure_continues`（不存在的 case_id 不阻断后续）
- [ ] `pytest tests/case_library/test_cli_approve.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes

### US-012: M2 e2e 集成测试 + 全量验收 + tag m2-data-assets
**Description:** 作为发布门禁，我需要一个 5 用例的 e2e 集成测试覆盖 spec §6.2，跑全量 pytest 确保零回归，跑 6 项验收命令确认所有指标达标，最后打 tag `m2-data-assets` 并更新 M-ROADMAP.md（M2 ⚪ → ✅）。

**Acceptance Criteria:**
- [ ] 新增 `tests/integration/test_m2_e2e.py` 含 5 用例：
  - `test_rules_conversion_creates_402_cases_with_severity_split`（实跑 v23 rules.json：created=402 + by_severity={hard:236,soft:147,info:19}；rules.json 缺失则 skip）
  - `test_active_pending_counts_after_conversion`（active=236 + pending=166）
  - `test_approve_batch_yaml_changes_status`（5 case yaml + 各 action → status 正确）
  - `test_corpus_ingest_resume_skips_indexed_chapters`（直接测 `_already_indexed` helper）
  - `test_chunking_pipeline_e2e_with_one_chapter_mocked`（in-memory Qdrant 8 维测试 collection；mock anthropic+embedder；1 章 → segment → tag → index → assert collection.points_count==1）
- [ ] `pytest tests/integration/test_m2_e2e.py -v --no-cov` 输出 5 passed（或 1 skipped if rules.json missing）
- [ ] 全量回归 `pytest -q` 全绿，覆盖率 ≥ 70（M1 baseline 82.72%）
- [ ] 6 项验收命令全过：(1) `pytest -q` 全绿 + cov ≥ 70；(2) Qdrant readyz HTTP 200；(3) corpus_chunks points_count ≥ 2500；(4) `data/case_library/cases/` 下 ≥ 400 个 yaml 文件；(5) `python -m ink_writer.case_library.cli status active` 输出 ≥ 200 行；(6) `python -m ink_writer.case_library.cli status pending` 输出 ≈ 166 行
- [ ] 打 tag：`git tag -a m2-data-assets -m "M2 complete: corpus chunking + cases conversion (≥100 active cases + ≥2500 corpus chunks)"`
- [ ] 更新 `docs/superpowers/M-ROADMAP.md`：顶部 Status 改为含 "M1 ✅ + M2 ✅"；进度表 M2 行：状态从 ⚪ → ✅ + 完成日期填实际日期 + PRD/Plan/branch 列填实际路径
- [ ] Typecheck passes

## Functional Requirements

- FR-1: `scripts/corpus_chunking/` 是 M2 切片管线的唯一入口包，含 segmenter/tagger/indexer/embedding_client/cli/models/prompts 子模块
- FR-2: scene_segmenter 必须用 Haiku 4.5（`claude-haiku-4-5-20251001`），切 200-800 字 chunks，超长按句号边界二次切分
- FR-3: chunk_tagger 输出 6 标签（scene_type / tension_level / character_count / dialogue_ratio / hook_type / borrowable_aspects）+ 4 维 quality_breakdown（tension / originality / language_density / readability）；4 维加权权重默认 30/30/20/20
- FR-4: chunk_tagger 的 `genre` 字段必须从 caller 传入（manifest.json 继承），LLM 推测的 genre 被忽略
- FR-5: chunk_indexer 用 Qwen3-Embedding-8B 4096 维向量化 + Qdrant `corpus_chunks` collection（M1 已 ensure）+ UUID5(NAMESPACE_URL, chunk_id) 作为 point id 保证幂等
- FR-6: 失败处理三层不变量：`chunks_raw.jsonl ⊇ chunks_tagged.jsonl ⊇ Qdrant collection`（原文不丢、tag 失败 quality_score=0 仍入库、index 失败写 unindexed.jsonl）
- FR-7: `ink corpus ingest` 默认摄入 `benchmark/reference_corpus/`，支持 `--book` 单本 / `--resume` 跳过已 indexed 章节 / `--dry-run` 不写 Qdrant / `--dir` 自定义目录
- FR-8: `ink corpus rebuild --yes` 全量必须先 delete_collection + ensure_collection 再触发 ingest；无 `--yes` rc=2
- FR-9: `ink corpus watch --dir <path>` 用 polling 扫 mtime 变化（不依赖 watchdog 库）；`--iterations` 仅供测试
- FR-10: rules_to_cases 按 rule.severity 分流：hard→active P1 / soft→pending P2 / info→pending P3+`info_only` tag
- FR-11: rules_to_cases 的 dedup 用 `raw_text = rule + " | " + why` 的 sha256（复用 M1 ingest_case 已实现的机制）
- FR-12: rules_to_cases 的 `failure_pattern.observable` 字段用占位文本 `"待 M3 dry-run 后基于实际触发样本细化（rule_id: EW-XXXX）"`，绕过 schema minItems:1 同时不污染 M3 数据
- FR-13: `ink case approve --batch <yaml>` 三种 action：approve→active / reject→retired / defer→pending+note；yaml schema 校验失败 rc=3
- FR-14: `ink case approve --batch` 单 case 失败不阻断后续；ingest_log.jsonl 写 `event=approval` 事件
- FR-15: `ink case convert-from-editor-wisdom` 默认从 `data/editor-wisdom/rules.json` 全量摄入；输出 `created=N skipped=N failed=N` + `by_severity={...}`
- FR-16: 所有新增 Python 文件用 `open(... encoding="utf-8")`；CLI 入口 `__main__` 块调 `enable_windows_utf8_stdio()`（audit 红线要求）
- FR-17: 新增 `.py` 不能用 `os.symlink` / `Path.symlink_to` 裸调用（audit 红线 `tests/core/test_safe_symlink.py`）
- FR-18: 新增 testpath `tests/corpus_chunking` 必须注册到 `pytest.ini`，否则 pytest 不收集
- FR-19: M2 完成时 `pytest -q` 全绿 + 覆盖率 ≥ 70（M1 baseline 82.72% 不被破坏）
- FR-20: M2 完成时 `git tag m2-data-assets` 已打 + `docs/superpowers/M-ROADMAP.md` M2 行更新为 ✅

## Non-Goals (Out of Scope)

- M3 内容：召回路由改造（`router.py` 加 case_aware/genre_filtered）/ writer 侧注入修改（`writer_injection.py`）/ 病例反向召回接线（`case_retriever.py`）/ writer-self-check / conflict-skeleton-checker / protagonist-agency-checker / polish-agent 改造 / `config/checker-thresholds.yaml`
- M4 内容：4 个 ink-init checker（genre-novelty / golden-finger-spec / naming-style / protagonist-motive）/ 3 个 ink-plan checker / LLM 高频起名词典 / 起点 top 200 简介库
- M5 内容：dashboard 扩展 / Layer 4 复发追踪 / Layer 5 元规则浮现 / `data/case_library/user_corpus/` 接口 / A/B 通道 / `ink case approve --interactive` 模式
- 不替换现有 23 个 checker 的算法
- 不替换 Embedding (Qwen3-Embedding-8B) / Reranker (jina-reranker-v3)
- 不退役 FAISS（M2 双写保留；待 M3 决定）
- 不重写 `ink-writer/scripts/ink-auto.sh` / `ink-writer/scripts/ink-auto.ps1`
- 不用 LLM 自动抽 observable（占位即可）→ M3+ 按需
- 不在 chunking 阶段做角色识别 NER（character_count 用 LLM 估）
- 不引入 `watchdog` 库（用 polling 替代以避免跨平台行为不一致）

## Design Considerations

- **复用 M1 已建组件**：`ingest_case`（M1 US-007）/ `CaseStore` / `CaseIndex` / `CORPUS_CHUNKS_SPEC`（M1 US-012）/ `ensure_collection` / preflight，不重建任何基础设施
- **配置驱动**：`config/corpus_chunking.yaml` 集中管理 model / batch_size / quality_weights / Qdrant collection 名 / Embedding API base_url；跑前修改即生效（不入 LLM cache）
- **Schema 是契约**：`schemas/case_approval_batch_schema.json` + `schemas/case_schema.json`（M1）+ 隐式 chunk schema（`TaggedChunk.to_dict()`）三者共同定义跨阶段数据流
- **错误层级**：`EmbeddingError` / `CaseLibraryError` / `CaseNotFoundError`；CLI 层永不 raise（顶层 try/except SystemExit/Exception 转 rc）
- **跨目录 CLI 入口模板**：`scripts/*/` 下脚本用 sys.path 三段式 bootstrap（`_REPO_ROOT` + `_INK_SCRIPTS`）+ `# noqa: E402` 抑制 ruff "import not at top"，复刻 M1 progress.txt 已记录的 pattern

## Technical Considerations

- **依赖**：openai-python（Qwen modelscope endpoint 兼容 OpenAI 格式）+ anthropic（Haiku 4.5）+ qdrant-client（M1 已装 ~=1.12，实测 1.17.1）+ pyyaml（已装）+ jsonschema（已装 ~=4.26）
- **API 配置**：EMBED_API_KEY / RERANK_API_KEY 在 `.env`（按 `docs/rag-and-config.md` 三级加载顺序）；M2 不需要 RERANK（M3 才用 reranker）
- **Qwen3-Embedding-8B**：4096 维，cosine distance，与 M1 `CORPUS_CHUNKS_SPEC.vector_size=4096` 对齐；embed_batch_size=32 与 modelscope rate limit 对齐；429 限流指数退避（1s/2s/4s）
- **Haiku 4.5 模型 ID**：`claude-haiku-4-5-20251001`；scene_segmenter max_tokens=8192（章节可能 3500 字 + 输出 chunks 列表）；chunk_tagger max_tokens=2048
- **跨平台**：所有 `.sh` 字节级保留；新建 Python 文件 `open(... encoding="utf-8")`；CLI `__main__` 调 `enable_windows_utf8_stdio()`；遵守 `CLAUDE.md` Windows 兼容守则
- **测试隔离**：`QdrantClient(":memory:")` 用于全部单元测试；e2e 测试用 8 维测试 collection 加快 in-memory；不依赖外部 docker
- **覆盖率门禁**：`pytest.ini` 当前 `--cov-fail-under=70`；新模块必须自带测试，避免覆盖率拖低
- **API 成本预算**：单次 ingest 实跑 < $30（实测 Haiku 估 $3-10）；预算容多次 prompt 调优试错
- **幂等性**：所有"创建型"操作（segment_chapter / tag_chunk / index_chunks / convert_rules_to_cases / approve）都要幂等（重跑产物相同）

## Success Metrics

- 12 个 user story 全部 `passes: true`
- `pytest -q` 全绿，覆盖率 ≥ 70（M1 baseline 82.72%）
- M2 新增测试 ≥ 30 个，**全绿**
- Qdrant `corpus_chunks` collection points_count ≥ 2500
- `data/case_library/cases/` 下 ≥ 400 个 yaml 文件
- 抽样 50 chunks 人工核 scene_type 合理度 ≥ 80%
- failures.jsonl 失败章节 < 30（< 3.3%）；unindexed.jsonl < 5
- API 实跑成本 < $30
- `git tag m2-data-assets` 已打成功
- `docs/superpowers/M-ROADMAP.md` M2 行更新为 ✅
- M3 启动时所有依赖（chunks 库 + cases 库 + CLI）就绪可用

## Open Questions

- Q-1: M3 dry-run 阶段如果发现 236 active rules 中有大量"假阳性阻断"，是否需要批量退回 pending？预期通过 `ink case approve --batch` 反向操作 yaml（action: defer）解决。
- Q-2: chunk_tagger 的 `borrowable_aspects` 是自由字符串数组，未来 M3 召回时需不需要做归并（如 sensory_grounding / sensory_detail 合并）？本期不归并，M3 dry-run 后视召回精度决定。
- Q-3: 是否需要在 US-008 实跑后立即跑一次 `ink case approve --batch` 把某些误标的 hard rule 退回 pending？建议本期不做（保持 M2 数据"忠实于 v23 现状"），M3 dry-run 时统一审视。
