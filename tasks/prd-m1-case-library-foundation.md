# PRD: M1 Case Library Foundation + Qdrant Migration

## Introduction

落地 spec §9 M1（详见 `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md`）：
- Case Library 基础设施（YAML 一案一文件 + sqlite 倒排索引 + jsonl 打包 + 摄入审计）
- Vector DB 从 FAISS 迁到 Qdrant（单机 docker；payload filter / 增量 / 可观测性）
- Preflight Health Checker（6 项启动前检查 + 失败自动建 infra_health 病例）
- reference_corpus 软链接修复（方案 A 硬拷贝；解决项目搬迁后绝对路径软链接全断的悄悄退化问题）
- 集成 preflight 到 ink-write SKILL.md 的 Step 0

本 PRD 不做：M2-M5 内容（segmenter / writer-self-check / ink-init checker / dashboard 等）。

详细 plan：`docs/superpowers/plans/2026-04-23-m1-foundation-and-qdrant-migration.md`（17-task TDD 步骤表）。

## Goals

- 病例可以创建、查询、删除（CRUD 闭环）
- Qdrant 在 docker 中可启动、可被 Python 客户端访问、可作为 FAISS 替代品承载向量索引
- ink-write 启动前必跑 preflight；任一基础设施失败 → 阻断写作 + 自动建 infra_health 病例
- 不再出现"参考库悄悄失效"的状况（reference_corpus 链接断会被 preflight 立即报告）
- 所有改动跨平台（macOS + Windows 11）行为一致；遵守 CLAUDE.md Windows 兼容守则
- 不重建 Embedding/Reranker 基座，不替换现有 23 个 checker，不动既有 ink-learn / project_memory.json

## User Stories

### US-001: 修复 reference_corpus 断链（方案 A 硬拷贝）
**Description:** 作为运维者，我需要一个幂等脚本把 `benchmark/reference_corpus/<书名>/chapters/*.txt` 里所有指向 `/Users/cipher/AI/ink/...`（无"小说"层级）的断链替换为来自 `benchmark/corpus/<书名>/chapters/*.txt` 的硬拷贝，让 corpus 重新可读。

**Acceptance Criteria:**
- [ ] 新增 `scripts/maintenance/__init__.py` + `scripts/maintenance/fix_reference_corpus_symlinks.py`
- [ ] 暴露 `fix_reference_corpus_symlinks(reference_root: Path, corpus_root: Path) -> FixReport` 函数 + `main(argv)` CLI
- [ ] 处理三种文件状态：断链（删除 + cp 原文）、已是真实文件（跳过）、原文不存在（记录到 missing_paths）
- [ ] 默认参数：`--reference-root benchmark/reference_corpus`、`--corpus-root benchmark/corpus`
- [ ] 新增 `tests/maintenance/__init__.py` + `tests/maintenance/test_fix_reference_corpus_symlinks.py`，至少覆盖 3 个用例：`test_fix_replaces_broken_symlinks_with_hard_copies`、`test_fix_skips_already_real_files`、`test_fix_records_missing_source`
- [ ] 实跑 `python scripts/maintenance/fix_reference_corpus_symlinks.py` 输出 `fixed=N skipped=0 missing_source=0`，N 等于实际章节文件数；`head -c 80 benchmark/reference_corpus/诡秘之主/chapters/ch001.txt` 输出真实中文正文
- [ ] 所有新增 `open()` 带 `encoding="utf-8"`（CLAUDE.md Windows 兼容守则）
- [ ] `pytest tests/maintenance -q --no-cov` 全绿
- [ ] Typecheck passes
**Priority:** 1

### US-002: 测试基础设施（pytest.ini + qdrant-client 依赖 + 包骨架）
**Description:** 作为开发者，我需要把新增的 `case_library / qdrant / preflight / maintenance` 测试目录注册到 pytest，把 `qdrant-client` 加入依赖，并准备好空的包骨架，让后续 task 的 TDD 步骤能直接跑测试。

**Acceptance Criteria:**
- [ ] `pytest.ini` 的 `testpaths` 行尾追加 `tests/case_library tests/qdrant tests/preflight tests/maintenance`（保持单行不换行）
- [ ] `requirements.txt` 末尾新增一行：`qdrant-client~=1.12            # Vector DB（M1 起替换 FAISS，详见 docs/superpowers/specs/2026-04-23-...md §8）`
- [ ] 本机 `pip install "qdrant-client~=1.12"` 成功；`python -c "import qdrant_client; print(qdrant_client.__version__)"` 输出 `1.12.x`
- [ ] 创建空文件：`ink_writer/case_library/__init__.py`、`ink_writer/qdrant/__init__.py`、`ink_writer/preflight/__init__.py`
- [ ] 创建空文件：`tests/case_library/__init__.py`、`tests/qdrant/__init__.py`、`tests/preflight/__init__.py`
- [ ] `pytest -q --no-cov` 在不引入新失败的前提下通过（M1 之前已知失败可保留）
- [ ] Typecheck passes
**Priority:** 2

### US-003: Case JSON Schema + validate_case_dict
**Description:** 作为 Case 库使用者，我需要一份权威的 JSON Schema 描述 Case 的结构，并提供 `validate_case_dict()` 在保存/加载/摄入前强制校验，错误信息含 JSON 指针。

**Acceptance Criteria:**
- [ ] 新增 `schemas/case_schema.json`，遵守 spec §3.2 字段：`case_id`（pattern `^CASE-[0-9]{4}-[0-9]{4}$`）、`title`、`status` enum（pending/active/resolved/regressed/retired）、`severity` enum（P0-P3）、`domain` enum（writing_quality/infra_health）、`layer` array of enum（upstream/downstream/reference_gap/infra_health, minItems:1）、`tags`、`scope.{genre,chapter,trigger}`、`source.{type,reviewer,raw_text,ingested_at,ingested_from}` (required: type/raw_text/ingested_at)、`failure_pattern.{description,observable}`（required: 全部，observable minItems:1）、`bound_assets.{rules,corpus_chunks,checkers}`、`resolution.{introduced_at,validation_chapters,regressed_at,related_cases}`、`evidence_links` array
- [ ] 新增 `ink_writer/case_library/errors.py` 含 `CaseLibraryError`、`CaseValidationError`、`CaseNotFoundError`、`DuplicateCaseError`
- [ ] 新增 `ink_writer/case_library/schema.py` 提供 `validate_case_dict(case: dict) -> None`，使用 `jsonschema.Draft202012Validator`，失败时 raise `CaseValidationError` 含 JSON 指针（如 `/source/raw_text: 'raw_text' is a required property`）
- [ ] schema 文件只加载一次（`@lru_cache`），路径用 `Path(__file__).resolve().parent.parent.parent / "schemas" / "case_schema.json"`
- [ ] 新增 `tests/case_library/conftest.py` 提供 `sample_case_dict` 和 `tmp_case_dir` fixtures
- [ ] 新增 `tests/case_library/test_schema.py` 含 7 个用例：`test_minimum_valid_case_passes`、`test_missing_required_case_id_raises`、`test_invalid_status_raises`、`test_invalid_severity_raises`、`test_invalid_domain_raises`、`test_layer_must_be_array`、`test_case_id_pattern_enforced`
- [ ] `pytest tests/case_library/test_schema.py -v --no-cov` 输出 7 passed
- [ ] Typecheck passes
**Priority:** 3

### US-004: Case Models (dataclass + 枚举)
**Description:** 作为内存表示，我需要 `Case` dataclass 和对应枚举（CaseStatus / CaseSeverity / CaseDomain / CaseLayer / SourceType），以及 `from_dict / to_dict` 供 YAML 与 JSON 间无损往返。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/models.py` 定义：`CaseStatus`、`CaseSeverity`、`CaseDomain`、`CaseLayer`、`SourceType`（皆继承 `str, Enum`），`Scope`（genre/chapter/trigger 三字段）、`Source`（type/raw_text/ingested_at + reviewer/ingested_from optional）、`FailurePattern`（description/observable）、`Case`（含 case_id/title/status/severity/domain/layer/tags/scope/source/failure_pattern/bound_assets/resolution/evidence_links）
- [ ] `Case.from_dict(data)` 接受 schema 验证过的 dict 还原 dataclass；`Case.to_dict()` 反向，要求 round-trip 后再过 `validate_case_dict` 仍通过
- [ ] `to_dict()` 对 None optional 字段（trigger/reviewer/ingested_from）省略不写出
- [ ] 枚举接受任意未知字符串构造时 raise `ValueError`（验证 `CaseStatus("unknown")` 抛错）
- [ ] 新增 `tests/case_library/test_models.py` 含 3 个用例：`test_case_round_trip`、`test_case_unknown_status_rejected`、`test_case_to_dict_omits_empty_optional_blocks`
- [ ] `pytest tests/case_library/test_models.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes
**Priority:** 4

### US-005: Case Store（YAML 一案一文件 + jsonl 打包 + ingest_log）
**Description:** 作为持久化层，我需要 `CaseStore` 把 Case 一案一文件写到 `library_root/cases/CASE-YYYY-NNNN.yaml`，并提供加载、列出、jsonl 打包、追加 `ingest_log.jsonl` 等功能。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/store.py`，含 `CaseStore(library_root: Path)` 类，自动 `mkdir -p library_root/cases`
- [ ] `save(case)`：写入 `cases/{case_id}.yaml`，使用 `yaml.safe_dump(allow_unicode=True, sort_keys=False, default_flow_style=False)`，写前再过 `validate_case_dict()`；返回写入路径
- [ ] `load(case_id)`：读 yaml（`encoding="utf-8"`），过 schema 校验，返回 `Case`；不存在 raise `CaseNotFoundError`
- [ ] `list_ids()`：返回 `cases/CASE-*.yaml` 的 stem 列表
- [ ] `iter_cases()`：generator，按 case_id 升序 yield 全量 `Case`
- [ ] `pack_jsonl(out_path)`：导出全量为 jsonl（一行一案，`ensure_ascii=False`），返回写入条数
- [ ] `append_ingest_log(event: dict)`：追加 `library_root/ingest_log.jsonl`，每行 JSON
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] 新增 `tests/case_library/test_store.py` 含 7 个用例：`test_save_then_load`、`test_save_writes_yaml_with_utf8`（验中文与 yaml 解析）、`test_load_missing_raises`、`test_save_invalid_case_raises`、`test_list_returns_all_case_ids`、`test_pack_jsonl_emits_one_line_per_case`、`test_append_ingest_log`
- [ ] `pytest tests/case_library/test_store.py -v --no-cov` 输出 7 passed
- [ ] Typecheck passes
**Priority:** 5

### US-006: Case Index（sqlite 倒排查询）
**Description:** 作为查询层，我需要 `CaseIndex` 在 `library_root/index.sqlite` 维护 tag/layer/genre/chapter/status 的倒排表，build 是 destructive 重建（DROP+CREATE）以保持权威数据是 YAML 文件。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/index.py`，含 `CaseIndex(sqlite_path: Path)` 类
- [ ] `build(store)`：执行 schema (`DROP+CREATE` 5 张表 `cases / case_tags / case_layers / case_genres / case_chapters`，含 column index)，逐案 INSERT，返回索引案数
- [ ] `query_by_tag(tag) -> list[str]`、`query_by_layer(layer)`、`query_by_genre(genre)`、`query_by_chapter(chapter)`、`query_by_status(status)`：各返回排序 case_id 列表
- [ ] 重复 build 是幂等的（DROP+CREATE 保证）
- [ ] 新增 `tests/case_library/test_index.py` 含 6 个用例：`test_build_index_creates_sqlite`、`test_query_by_tag`、`test_query_by_layer`、`test_query_by_genre`、`test_query_by_status`、`test_rebuild_is_idempotent`；用 fixture 装 2 个 case（不同 status/layer/genre/tags）覆盖各倒排
- [ ] `pytest tests/case_library/test_index.py -v --no-cov` 输出 6 passed
- [ ] Typecheck passes
**Priority:** 6

### US-007: Case Ingest（sha256 去重 + 自动分配 case_id）
**Description:** 作为摄入入口，我需要 `ingest_case()` 按 raw_text 的 SHA-256 去重；首次创建分配下一个 `CASE-YYYY-NNNN` id，重复调用返回已存在的 case_id 且不修改文件；并写入 ingest_log 审计。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/ingest.py` 暴露 `IngestResult(case_id, created, raw_text_hash)` 与 `ingest_case(store, *, title, raw_text, domain, layer, severity, tags, source_type, ingested_at, failure_description, observable, reviewer=None, ingested_from=None, scope_genre=None, scope_chapter=None, initial_status="active")`
- [ ] `_hash_raw_text(raw_text)` 用 `sha256(raw_text.encode("utf-8")).hexdigest()`
- [ ] `_find_existing_by_hash` 遍历 `store.iter_cases()` 比对 `source.raw_text` hash；命中返回 case_id
- [ ] `_allocate_case_id`：扫描已有 `CASE-YYYY-` 前缀，取最大流水 +1；若无则从 `0001` 开始（zero-case `0000` 不冲突）
- [ ] 新案：构造 `Case` → `store.save()` → `store.append_ingest_log({"event":"ingest", "case_id":..., "raw_text_hash":..., "at": iso_utc_now})`
- [ ] 重复案：返回 `IngestResult(case_id=existing, created=False)` 且不写 store / 不写 log
- [ ] 新增 `tests/case_library/test_ingest.py` 含 3 个用例：`test_ingest_creates_case`（assert created=True 且 case_id 形如 CASE-2026-NNNN）、`test_ingest_same_text_is_deduplicated`（同 raw_text 二次调用 created=False 且 case_id 一致）、`test_ingest_appends_ingest_log`
- [ ] `pytest tests/case_library/test_ingest.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes
**Priority:** 7

### US-008: ink case CLI（list / show / create / status / rebuild-index）
**Description:** 作为人类操作者，我需要一个 `ink case` 子命令族能列出全部病例、显示单案、按状态过滤、创建新案、重建 sqlite 索引。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/cli.py` 暴露 `main(argv) -> int`，永不 raise（错误时返回非 0 + 写 stderr）
- [ ] argparse 顶层支持 `--library-root <path>` 默认 `data/case_library`
- [ ] 子命令 `list`：调 `store.list_ids()`，按字母序逐行打印 case_id；返回 0
- [ ] 子命令 `show <case_id>`：load 后用 `yaml.safe_dump(allow_unicode=True, sort_keys=False)` 打印；NotFound 返回 2 + stderr
- [ ] 子命令 `status <pending|active|resolved|regressed|retired>`：迭代全量，过滤 `case.status.value == status` 的 case_id 输出
- [ ] 子命令 `create`：必须接收 `--title --raw-text --domain --layer --severity --tags --source-type --ingested-at --failure-description --observable`（layer/tags/observable/scope-genre/scope-chapter 用 `action="append"`），可选 `--reviewer --ingested-from --scope-genre --scope-chapter --initial-status`；调 `ingest_case()`，新案打印 `case_id`，重复打印 `<case_id> (already existed; raw_text dedup)`；CaseValidationError 返回 3
- [ ] 子命令 `rebuild-index`：构造 `CaseIndex(library_root/"index.sqlite")` 并 build，打印 `indexed=<n>`
- [ ] 新增 `tests/case_library/test_cli.py` 含 3 个用例：`test_cli_create_then_list_then_show`、`test_cli_status_filters_by_status`、`test_cli_rebuild_index_creates_sqlite`
- [ ] `pytest tests/case_library/test_cli.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes
**Priority:** 8

### US-009: CASE-2026-0000 零号病例（infra_health 第一案）
**Description:** 作为产线"吃自己狗粮"的示范，我需要一个幂等脚本登记 CASE-2026-0000——记录 reference_corpus 软链接全断的事故，对应 P0 / infra_health domain / infra_health layer，并绑定 preflight-reference-corpus-readable checker。

**Acceptance Criteria:**
- [ ] 新增 `scripts/case_library/__init__.py` + `scripts/case_library/init_zero_case.py` 暴露 `init_zero_case(library_root: Path) -> bool`（返回 True=新建，False=已存在）+ `main(argv)` CLI（默认 `--library-root data/case_library`）
- [ ] case_id=`CASE-2026-0000`、status=ACTIVE、severity=P0、domain=INFRA_HEALTH、layer=[INFRA_HEALTH]、tags=["reference_corpus","symlink","silent_degradation"]、source.type=INFRA_CHECK、source.reviewer="self"、source.ingested_at="2026-04-23"、source.ingested_from="benchmark/reference_corpus/"
- [ ] failure_pattern.observable 至少含 2 条：`"broken symlink count under reference_corpus/*/chapters > 0"`、`"corpus_root readable file count < min_files threshold"`
- [ ] bound_assets.checkers 含 `{"checker_id": "preflight-reference-corpus-readable", "version": "v1", "created_for_this_case": True}`
- [ ] 二次调用 init 是 no-op（不抛错，store.list_ids() 中 `CASE-2026-0000` 仅出现一次）
- [ ] 新增 `tests/case_library/test_zero_case.py` 含 2 个用例：`test_zero_case_is_infra_health_active`、`test_zero_case_init_is_idempotent`
- [ ] 实跑 `python scripts/case_library/init_zero_case.py` 打印 `created`；产物 `data/case_library/cases/CASE-2026-0000.yaml` 存在且能被 `validate_case_dict` 通过
- [ ] `pytest tests/case_library/test_zero_case.py -v --no-cov` 输出 2 passed
- [ ] Typecheck passes
**Priority:** 9

### US-010: Qdrant Docker 部署 + 启动/停止脚本（Mac + Windows）
**Description:** 作为运维者，我需要 docker compose 启动 Qdrant 1.12.4 单机服务（端口 6333 REST + 6334 gRPC），并提供对称的 `.sh` / `.ps1` 启停脚本（PS 必须 UTF-8 BOM）。

**Acceptance Criteria:**
- [ ] 新增 `scripts/qdrant/docker-compose.yml`：`qdrant/qdrant:v1.12.4` 镜像，container_name `ink-writer-qdrant`，restart `unless-stopped`，映射 6333:6333、6334:6334，volume `./storage:/qdrant/storage`，env `QDRANT__LOG_LEVEL: INFO`
- [ ] 新增 `scripts/qdrant/start.sh`（chmod +x）：`docker compose up -d` + 30 秒 ready 轮询（curl `http://127.0.0.1:6333/readyz`），ready 后打印 `Qdrant is ready.` 退 0；超时退 1
- [ ] 新增 `scripts/qdrant/stop.sh`（chmod +x）：`docker compose down`
- [ ] 新增 `scripts/qdrant/start.ps1`（**UTF-8 BOM**，PS 5.1 兼容）：等价语义，使用 `Invoke-WebRequest -UseBasicParsing` + `Start-Sleep -Seconds 1` 轮询
- [ ] 新增 `scripts/qdrant/stop.ps1`（UTF-8 BOM）
- [ ] 新增 `scripts/qdrant/README.md`：写明启动命令（mac/win 双语）、端点 (6333/6334)、storage 持久化目录提醒
- [ ] `.gitignore` 追加 `scripts/qdrant/storage/`（确认 `grep -n "scripts/qdrant/storage" .gitignore` 命中）
- [ ] 实跑 `scripts/qdrant/start.sh` 后 `curl -s http://127.0.0.1:6333/readyz` 返回 200，`curl -s http://127.0.0.1:6333/collections` 返回 `{"result":{"collections":[]},"status":"ok",...}`
- [ ] 本任务无 pytest（基础设施任务），靠 curl 验证
**Priority:** 10

### US-011: Qdrant 客户端封装（client.py + 错误类）
**Description:** 作为 Python 调用层，我需要 `get_client_from_config(QdrantConfig)` 在连接失败时立即 raise `QdrantUnreachableError`（force `get_collections()` 探活），并提供进程级单例 `get_qdrant_client()`。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/qdrant/errors.py` 含 `QdrantError`、`QdrantUnreachableError`
- [ ] 新增 `ink_writer/qdrant/client.py` 暴露：`QdrantConfig` dataclass（host="127.0.0.1", port=6333, timeout=5.0, memory=False, api_key=None）、`get_client_from_config(config)`、`get_qdrant_client(config=None)`（singleton）、`reset_singleton_for_tests()`
- [ ] `get_client_from_config`：`memory=True` 返 `QdrantClient(":memory:")`；否则构造 HTTP client 并立刻调 `get_collections()`，捕获 `(ResponseHandlingException, UnexpectedResponse, ConnectionError, OSError)` 转 `QdrantUnreachableError(f"Qdrant at {host}:{port} unreachable: {err}")`
- [ ] 新增 `tests/qdrant/conftest.py` 提供 `in_memory_client` fixture（`QdrantClient(":memory:")`）
- [ ] 新增 `tests/qdrant/test_client.py` 含 2 个用例：`test_in_memory_client_via_helper`（assert `get_collections().collections == []`）、`test_unreachable_raises`（用 `port=1` 强制连接失败，pytest.raises QdrantUnreachableError）
- [ ] `pytest tests/qdrant/test_client.py -v --no-cov` 输出 2 passed
- [ ] Typecheck passes
**Priority:** 11

### US-012: Qdrant Payload Schema（collection 定义）
**Description:** 作为索引契约，我需要冻结生产 collection 名称与 payload 索引字段，让 M2 chunker 与 FAISS 迁移脚本目标一致。两个 collection：`editor_wisdom_rules` 和 `corpus_chunks`，dim=4096（Qwen3-Embedding-8B），cosine。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/qdrant/payload_schema.py` 暴露：`CollectionSpec(name, vector_size, indexed_payload_fields, distance=Distance.COSINE)` frozen dataclass、`EDITOR_WISDOM_RULES_SPEC`、`CORPUS_CHUNKS_SPEC`、`ensure_collection(client, spec) -> bool`
- [ ] `EDITOR_WISDOM_RULES_SPEC.name == "editor_wisdom_rules"`，`vector_size == 4096`，`indexed_payload_fields = {"category":"keyword","applies_to":"keyword","scoring_dimensions":"keyword"}`
- [ ] `CORPUS_CHUNKS_SPEC.name == "corpus_chunks"`，`vector_size == 4096`，`indexed_payload_fields = {"genre":"keyword","scene_type":"keyword","quality_score":"float","source_type":"keyword","source_book":"keyword","case_ids":"keyword"}`
- [ ] `ensure_collection`：collection 已存在 → 返 False；不存在 → `client.create_collection(name, vectors_config=VectorParams(size, distance))` + 对每个 payload field 调 `create_payload_index`，返 True
- [ ] 字段类型映射 `_FIELD_TYPE_MAP = {"keyword": KEYWORD, "float": FLOAT, "integer": INTEGER, "bool": BOOL}`
- [ ] 新增 `tests/qdrant/test_payload_schema.py` 含 3 个用例：`test_collection_specs_have_expected_names_and_dims`、`test_corpus_chunks_payload_has_filter_fields`、`test_ensure_collection_creates_then_skips`（用 `in_memory_client` fixture）
- [ ] `pytest tests/qdrant/test_payload_schema.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes
**Priority:** 12

### US-013: FAISS → Qdrant 迁移脚本（含幂等支持）
**Description:** 作为一次性迁移工具，我需要把 FAISS index + metadata.jsonl 升级到 Qdrant collection，使用 UUID5 衍生 point id 保证重跑幂等。支持 preset (`editor_wisdom_rules`, `corpus_chunks`) 与自定义 spec。

**Acceptance Criteria:**
- [ ] 新增 `scripts/qdrant/__init__.py` + `scripts/qdrant/migrate_faiss_to_qdrant.py`
- [ ] 暴露 `MigrationReport(collection, uploaded, skipped=0)` + `migrate_faiss_index(client, spec, faiss_index_path, metadata_jsonl, batch_size=256) -> MigrationReport` + `main(argv) -> int`
- [ ] CLI 必填 `--preset {editor_wisdom_rules,corpus_chunks} --faiss-index --metadata`，可选 `--qdrant-host (默认127.0.0.1) --qdrant-port (默认6333)`
- [ ] 流程：`ensure_collection` → 加载 FAISS index 与 metadata.jsonl → 校验 `index.ntotal == len(metadata)` 否则 raise `ValueError`（不允许半迁移）→ `index.reconstruct_n(0, n, vectors)` 还原向量 → 分批 upsert
- [ ] point id 用 `uuid.uuid5(NAMESPACE_URL, original_id)` 字符串；payload 复制 metadata 全字段并新增 `original_id`（防 metadata 缺 id 时 raise `ValueError("metadata row {i} missing 'id' field")`）
- [ ] 新增 `tests/scripts/test_migrate_faiss_to_qdrant.py` 含 2 个用例：`test_migration_uploads_all_vectors`（用 fake faiss index + jsonl + in-memory client，assert `points_count == n`）、`test_migration_is_idempotent`（连续两次跑 `points_count` 不变）
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] `pytest tests/scripts/test_migrate_faiss_to_qdrant.py -v --no-cov` 输出 2 passed
- [ ] Typecheck passes
**Priority:** 13

### US-014: 6 个独立 preflight check 函数
**Description:** 作为 preflight 基础，我需要 6 个独立 check 函数：`check_reference_corpus_readable`、`check_case_library_loadable`、`check_editor_wisdom_index_loadable`、`check_qdrant_connection`、`check_embedding_api_reachable`、`check_rerank_api_reachable`，每个返回 `CheckResult(name, passed, detail)`，**永不 raise**。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/preflight/errors.py` 含 `PreflightError(failed_check_names: list[str], message: str)`
- [ ] 新增 `ink_writer/preflight/checks.py` 暴露 `CheckResult` dataclass + 6 个 check 函数
- [ ] `check_reference_corpus_readable(reference_root, *, min_files=100)`：扫 `*.txt`，断链（`is_symlink() and not exists()`）→ 失败 + `"{n} broken symlink(s)"`；可读数 < min_files → 失败 + `"readable file count {x} below min_files={n}"`；通过 → `"{n} files readable"`
- [ ] `check_case_library_loadable(library_root)`：library_root / cases 必须存在且为目录；通过则返 `"{n} cases on disk"`
- [ ] `check_editor_wisdom_index_loadable(rules_path)`：文件必须存在且 JSON 可解析；通过返 `"{n} rules indexed"`
- [ ] `check_qdrant_connection(*, client=None, config=None)`：调 `get_client_from_config(config or QdrantConfig())` + `get_collections()`；`QdrantUnreachableError` → 失败；其他异常 → 失败 `"unexpected error: {err}"`（`# noqa: BLE001` 必须，因为 preflight 永不向上抛）
- [ ] `check_embedding_api_reachable()`：`os.environ.get("EMBED_API_KEY")` 缺失 → 失败 `"EMBED_API_KEY not set"`
- [ ] `check_rerank_api_reachable()`：同上，`RERANK_API_KEY`
- [ ] 新增 `tests/preflight/conftest.py` 通过 `from tests.qdrant.conftest import in_memory_client  # noqa: F401` 共享 fixture
- [ ] 新增 `tests/preflight/test_checks.py` 含 10 个用例：`test_reference_corpus_pass`、`test_reference_corpus_fail_when_below_min`、`test_reference_corpus_fail_when_broken_symlink`、`test_case_library_loadable_pass`、`test_case_library_loadable_fail_when_missing`、`test_editor_wisdom_index_loadable_pass`、`test_editor_wisdom_index_loadable_fail_when_missing`、`test_qdrant_connection_pass_with_in_memory_client`、`test_embedding_api_reachable_no_key`（用 monkeypatch.delenv）、`test_rerank_api_reachable_no_key`
- [ ] `pytest tests/preflight/test_checks.py -v --no-cov` 输出 10 passed
- [ ] Typecheck passes
**Priority:** 14

### US-015: Preflight checker 聚合 + 自动建 infra_health case
**Description:** 作为编排层，我需要 `run_preflight(config, *, raise_on_fail=False, auto_create_infra_cases=False)` 跑齐 6 项检查产 `PreflightReport`；可选地让失败自动调 `ingest_case()` 建 infra_health 病例（sha256 去重防重复）；可选地 raise `PreflightError`。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/preflight/checker.py` 暴露 `PreflightConfig`（reference_root/case_library_root/editor_wisdom_rules_path/qdrant_config/qdrant_in_memory/require_embedding_key/require_rerank_key/min_corpus_files=100）+ `PreflightReport(results, all_passed property, failed property)` + `run_preflight(config, *, raise_on_fail=False, auto_create_infra_cases=False)`
- [ ] qdrant_in_memory=True 时构造 `QdrantConfig(memory=True)` 注入 check_qdrant_connection
- [ ] 顺序跑：reference_corpus / case_library / editor_wisdom_index / qdrant；按 require_embedding_key/require_rerank_key 决定是否追加 embedding/rerank 检查
- [ ] auto_create_infra_cases=True 且有失败时：对每个失败 check 调 `ingest_case(store, title=f"preflight failure: {check.name}", raw_text=f"preflight check failed: {check.name}: {check.detail}", domain="infra_health", layer=["infra_health"], severity="P0", tags=["preflight", check.name], source_type="infra_check", ingested_at=date.today().isoformat(), failure_description=check.detail, observable=[f"{check.name}.passed == False"])`，sha256 去重保证重复运行不会膨胀
- [ ] raise_on_fail=True 且有失败 → raise `PreflightError(failed_names, f"preflight failed: {failed_names}")`
- [ ] 新增 `tests/preflight/test_checker.py` 含 3 个用例：`test_all_pass_returns_clean_report`、`test_failed_check_creates_infra_case`（assert 至少一个新案 domain==infra_health 且 title 含 `editor_wisdom_index_loadable`）、`test_failed_check_without_raise_returns_failed_report`
- [ ] `pytest tests/preflight/test_checker.py -v --no-cov` 输出 3 passed
- [ ] Typecheck passes
**Priority:** 15

### US-016: ink preflight CLI + 集成到 ink-write SKILL.md（Step 0）
**Description:** 作为 ink-write 的启动门禁，我需要 `python -m ink_writer.preflight.cli --auto-create-infra-cases --raise-on-fail` 命令，并把它写入 `ink-writer/skills/ink-write/SKILL.md` 的 Step 0（含 PowerShell sibling 块）。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/preflight/cli.py` 暴露 `main(argv) -> int`，永不 raise（顶层 `try/except Exception` 转 stderr + 返 2）
- [ ] argparse 支持：`--reference-root`（默认 `benchmark/reference_corpus`）、`--case-library-root`（默认 `data/case_library`）、`--editor-wisdom-rules`（默认 `data/editor-wisdom/rules.json`）、`--qdrant-in-memory`（store_true）、`--qdrant-host`（默认 127.0.0.1）、`--qdrant-port`（默认 6333）、`--require-embedding-key/--no-require-embedding-key`（默认 True）、`--require-rerank-key/--no-require-rerank-key`（默认 True）、`--min-corpus-files`（默认 100）、`--auto-create-infra-cases`（store_true）、`--raise-on-fail`（store_true）
- [ ] 输出格式首行 `all_passed=True|False`，后续每行 `  [OK ] <name>: <detail>` 或 `  [FAIL] <name>: <detail>`
- [ ] 返回值：all_passed=True 返 0；False 返 1；顶层异常返 2
- [ ] 修改 `ink-writer/skills/ink-write/SKILL.md`：在"Project Root Guard"环境设置块之后插入 `## Step 0 — Preflight Health Check（M1 起强制）` 章节，包含 bash 命令块 + `<!-- windows-ps1-sibling -->` + powershell 命令块；要求"退出码非 0 时不要继续后续 step"
- [ ] 新增 `tests/preflight/test_cli.py` 含 2 个用例：`test_cli_runs_in_minimal_mode`（all 通过，rc=0，stdout 含 `all_passed=True`）、`test_cli_failed_returns_nonzero`（缺 rules.json，rc!=0，stdout 含 `all_passed=False`）
- [ ] `grep -n "ink_writer.preflight.cli" ink-writer/skills/ink-write/SKILL.md` 至少匹配 2 行（bash + ps1）
- [ ] `pytest tests/preflight/test_cli.py -v --no-cov` 输出 2 passed
- [ ] Typecheck passes
**Priority:** 16

### US-017: M1 端到端集成测试 + 验收
**Description:** 作为发布门禁，我需要一个 end-to-end 测试覆盖"preflight 失败 → 自动建 infra_health 病例 → ink case list 能看到"的完整链路；并跑全量 pytest 确保零回归；最后打 tag `m1-foundation`。

**Acceptance Criteria:**
- [ ] 新增 `tests/integration/test_m1_e2e.py` 含 2 个用例：
  - `test_preflight_fail_creates_infra_case_visible_via_cli`：故意不创建 reference_root 触发 check 失败 → 调 preflight CLI 用 `--auto-create-infra-cases` rc!=0 输出 `all_passed=False` → 调 case CLI `list` 能看到至少 1 个 case_id → 每个新 case 必须 `domain.value=="infra_health"` 且 `severity.value=="P0"`
  - `test_preflight_pass_creates_no_new_cases`：清洁环境跑 preflight rc=0 输出 `all_passed=True`，调 case CLI `list` stdout 为空
- [ ] `pytest tests/case_library tests/qdrant tests/preflight tests/maintenance tests/scripts/test_migrate_faiss_to_qdrant.py tests/integration/test_m1_e2e.py -v --no-cov` M1 全套绿（约 35-40 测试）
- [ ] `pytest -q` 项目全量绿，覆盖率 ≥ 70（pytest.ini 现行门禁不被破坏）
- [ ] 实跑 `scripts/qdrant/start.sh` + `python -m ink_writer.preflight.cli --auto-create-infra-cases --no-require-embedding-key --no-require-rerank-key` 输出 `all_passed=True`
- [ ] 验收 6 项全过：(1) `pytest -q` 通过 + 覆盖率 ≥ 70；(2) Qdrant readyz 200；(3) `fix_reference_corpus_symlinks.py` 报 `missing_source=0`；(4) preflight CLI 全过；(5) `init_zero_case.py` 输出 `created` 或 `already_exists`；(6) `grep -n "ink_writer.preflight.cli" ink-writer/skills/ink-write/SKILL.md` 命中
- [ ] 打 tag `git tag -a m1-foundation -m "M1 complete: case_library + qdrant + preflight + symlink fix"`
- [ ] Typecheck passes
**Priority:** 17

## Functional Requirements

- FR-1: `data/case_library/cases/CASE-YYYY-NNNN.yaml` 是病例的权威存储格式（YAML）；`index.sqlite` 与 `cases.jsonl` 是派生物，可随时重建。
- FR-2: 病例 schema 由 `schemas/case_schema.json` 强制；任何 save/load/ingest 路径必须在写入或读出后过 `validate_case_dict()`，违反 → raise `CaseValidationError`。
- FR-3: 病例摄入按 `source.raw_text` 的 SHA-256 去重，重复摄入返回已存在 case_id 而不修改文件，且不写 ingest_log。
- FR-4: 病例 case_id 形如 `CASE-YYYY-NNNN`（`^CASE-[0-9]{4}-[0-9]{4}$`），按 ingested_at 年份分配下一可用流水号。
- FR-5: `ink case list/show/create/status/rebuild-index` CLI 子命令必须可用，`main(argv)` 返回 int 永不 raise。
- FR-6: Qdrant 1.12.4 通过 docker compose 启动在 6333（REST）+ 6334（gRPC）；持久化目录 `scripts/qdrant/storage/` 不入 git。
- FR-7: 启动 / 停止脚本 `start.sh / stop.sh / start.ps1 / stop.ps1` 全部存在，`.ps1` 必须 UTF-8 BOM；ready 检测 30 秒超时。
- FR-8: `ink_writer.qdrant.client.get_client_from_config(config)` 在不可达时立即 raise `QdrantUnreachableError`（强制 `get_collections()` 探活）。
- FR-9: 生产 collection 名固定为 `editor_wisdom_rules`（dim=4096, cosine）和 `corpus_chunks`（dim=4096, cosine, 含 6 个 payload 索引字段）；`ensure_collection` 幂等。
- FR-10: `migrate_faiss_index` 用 UUID5（NAMESPACE_URL）生成 point id 实现幂等；`index.ntotal != len(metadata)` 必须 raise（拒绝半迁移）。
- FR-11: Preflight 6 项检查：reference_corpus_readable / case_library_loadable / editor_wisdom_index_loadable / qdrant_connection / embedding_api_reachable / rerank_api_reachable；每个返回 `CheckResult(name, passed, detail)` 永不 raise。
- FR-12: `run_preflight(config, *, raise_on_fail=False, auto_create_infra_cases=False)` 是 preflight 唯一入口；auto_create_infra_cases 为每个失败建 P0 / infra_health 病例，sha256 去重防重复。
- FR-13: `python -m ink_writer.preflight.cli` 输出首行 `all_passed=True|False`，后续每行 `[OK ]/[FAIL] <name>: <detail>`；返回 0/1/2。
- FR-14: `ink-writer/skills/ink-write/SKILL.md` 必须有 `Step 0 — Preflight Health Check`，包含 bash + Windows PowerShell sibling 块，要求退出码非 0 阻断后续 step。
- FR-15: `CASE-2026-0000` 是项目唯一的零号病例（infra_health / P0），由 `scripts/case_library/init_zero_case.py` 幂等创建。
- FR-16: 所有新增 Python 文件使用 `open(... encoding="utf-8")` 与 `Path.read_text(encoding="utf-8")`；面向用户的 CLI 入口 `if __name__ == "__main__":` 处需保持与 v23 现有惯例一致（不强制额外调用 `enable_windows_utf8_stdio` 除非新建 stdio 重度脚本）。
- FR-17: `pytest -q` 项目全量必须 pass，覆盖率 ≥ 70（不破坏 `pytest.ini` 现行 `--cov-fail-under=70` 门禁）。

## Non-Goals (Out of Scope)

- M2 内容：场景级切片管线 / corpus_chunks 入库 / 起点 top200 简介库 / editor-wisdom rules → cases 批量转换
- M3 内容：writer-self-check / conflict-skeleton-checker / protagonist-agency-checker / polish-agent 改造 / `config/checker-thresholds.yaml`
- M4 内容：4 个 ink-init checker / 3 个 ink-plan checker / LLM 高频起名词典
- M5 内容：dashboard 扩展 / Layer 4 复发追踪 / Layer 5 元规则浮现 / user_corpus 接口 / A/B 通道
- 不替换现有 23 个 checker 的算法，不替换 Embedding (Qwen3-Embedding-8B) / Reranker (jina-reranker-v3)
- 不删除 FAISS（M1 双写阶段保留；M2 才退役）
- 不批量审批 pending cases（除 CASE-2026-0000 外，本期不创建任何业务 case）
- 不接入 ink-init / ink-plan / ink-review 阶段（除 ink-write Step 0 外）
- 不做 Web UI / Dashboard / 编辑器界面
- 不做模型微调 / 多模型并行
- 不重写 `ink-writer/scripts/ink-auto.sh` / `ink-writer/scripts/ink-auto.ps1`（除非阻断逻辑产生新需求；本期不动）

## Design Considerations

- **配置驱动的目录路径**：Case Library 默认根 `data/case_library`，Qdrant 持久化默认 `scripts/qdrant/storage/`，preflight CLI 全部参数化便于 CI/CD 与 tests
- **Schema 是契约**：`schemas/case_schema.json` 与 `ink_writer/case_library/models.py` enum 必须保持同步；`models.from_dict()` round-trip 后再过 schema 验证
- **错误层级**：`CaseLibraryError` / `QdrantError` / `PreflightError` 三个独立基类；CLI 层永不 raise（顶层 try/except 转 exit code）
- **CLI 命名一致**：`ink case <subcommand>` / `ink preflight`；未来 M2 加 `ink corpus` / `ink dashboard` 时按相同 convention
- **可观测性优先**：所有失败必须有 `detail` 字段；preflight 报告必须包含每条 check 的 name + passed + detail；不做"silent fail"

## Technical Considerations

- **依赖**：仅新增 `qdrant-client~=1.12`；既有 `jsonschema~=4.26`、`PyYAML~=6.0`、`numpy~=2.4`、`faiss-cpu~=1.13` 全部复用
- **Qdrant 版本锁定**：`qdrant/qdrant:v1.12.4`（与 client 1.12 对齐）；docker volume 持久化保证 dev 数据不丢
- **Embedding 向量维度**：4096（Qwen3-Embedding-8B）固定写死在 `payload_schema.py`；M2 起若维度变化需同步改 spec + schema + 迁移脚本
- **跨平台**：`.sh` 完全保留 mac/linux 行为；`.ps1` UTF-8 BOM 必需（PS 5.1）；新建 Python 文件用 `open(... encoding="utf-8")`；遵守 `CLAUDE.md` Windows 兼容守则
- **测试隔离**：`QdrantClient(":memory:")` 用于全部单元测试；端到端测试不依赖外部 docker（这点本期不做，后续 M2 视需要补 integration test marker）
- **测试目录注册**：`pytest.ini` `testpaths` 必须扩展，否则新测试不会被收集
- **覆盖率门禁**：`pytest.ini` 当前 `--cov-fail-under=70`；新模块必须自带测试，避免覆盖率拖低
- **幂等性**：所有"创建型"操作（init_zero_case / migrate_faiss_index / ensure_collection / preflight infra case 创建）必须幂等，重跑不出问题
- **不动既有 FAISS**：M1 双写阶段两套并存；ink_writer/retrieval/router.py 等调用方仍走 FAISS（M2 切换）；本期不动既有 retrieval 路径
- **零号病例 CASE-2026-0000 是约定**：保留 0000 给 infra_health "吃自己狗粮"示范；业务 case 从 0001 起编号

## Success Metrics

- 17 个 user story 全部 `passes: true`
- `pytest -q` 项目全量绿，覆盖率 ≥ 70
- M1 新增测试 ≥ 35 个，**全绿**
- `python -m ink_writer.preflight.cli` 一行命令出 `all_passed=True/False` 报告，秒级返回
- `python scripts/maintenance/fix_reference_corpus_symlinks.py` 报 `missing_source=0`
- `curl http://127.0.0.1:6333/readyz` 返回 200
- `git tag -a m1-foundation -m "M1 complete..."` 打成功
- 新增代码全部跨平台（mac + win）行为一致；无 .ps1 缺失 / 无 UTF-8 缺失

## Open Questions

- Q-1: Qdrant 双写期长度（spec §6.3 风险 7 提"7 天"），M1 是否需要在 client.py 实现"双写抽象层"，还是 M2 切换时再做？**建议本期不做**，client.py 仅暴露单一 Qdrant 通道，FAISS 仍由现有 retrieval 路径单独使用，互不干扰。
- Q-2: 6 项 preflight 是否需要可配置的"忽略列表"（例如 dev 机暂时关闭 embedding key 检查）？**当前已通过 `--no-require-embedding-key/--no-require-rerank-key` 提供**；其他 4 项暂不开放豁免（理由：保持产线红线）。
- Q-3: `ink preflight` 是否要进入顶层 `ink` 命令树？**M1 不做**，先用 `python -m ink_writer.preflight.cli`；M5 `ink dashboard` 一并整合。
