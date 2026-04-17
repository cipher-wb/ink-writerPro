# US-006 数据层与记忆系统审计报告

> **审计范围**：SQLite 表 schema、state.json、foreshadow/plotline/incremental_extract 子模块、实体消歧流
> **审计方式**：只读，基于代码证据（schema 定义 + INSERT/SELECT 点位）
> **审计时间**：2026-04-17
> **被审版本**：ink-writer v13.8.0（`IndexManager.SCHEMA_VERSION = 2`，`StateModel.schema_version = 9`/v11）

---

## Executive Summary

项目数据层**实际规模小于宣称**：不是"30+ 张表混合架构"，而是 **4 个独立 SQLite 数据库 + 1 个 JSON 视图缓存**：

| 数据库文件 | 位置 | 管理器 | 表数 | 角色 |
|-----------|------|-------|------|------|
| `.ink/index.db` | project | `IndexManager` | **34** | 主库，叙事/实体/记忆 |
| `.ink/vectors.db` | project | `rag_adapter.py` | **4** | 场景向量 + BM25 |
| `.ink/style_samples.db` | project | `style_sampler.py` | **1** | 风格采样 |
| `.ink/parallel_locks.db` | project | `chapter_lock.py` | **1** | 并发章锁 |
| `.ink/cache_metrics.db` | project | `prompt_cache/metrics.py` | **1** | Prompt cache 统计 |
| （全局 style_rag） | benchmark | `style_rag_builder.py` | 1 | 读风格样本库 |
| **JSON** | `.ink/state.json` | `StateManager` + `SQLStateManager` | n/a | 视图缓存 |
| **JSON** | `.ink/preferences.json`、`project_memory.json`、`golden_three_plan.json` | 多处 | n/a | 偏好/记忆/计划 |

**关键健康问题**：

1. **v13 "单一事实源"架构未彻底落地**：docs 承诺"SQLite 是唯一事实源、state.json 为视图缓存"，但现网仍有 ~6 个 skill/agent 直接读写 state.json（例如 `ink-resolve` 直接读 `disambiguation_pending`）。`rebuild_state_json()` 确实能从 SQLite 重建，但大量代码不经过它。
2. **孤儿表 / 仅定义未使用**：`protagonist_knowledge` 表建了但生产代码零 INSERT / 零 SELECT（仅被 agent 规格文档提及）。`incremental_extract` 模块 `compute_entity_diff()` 仅被测试用例调用，生产数据流未接入。
3. **schema 版本号严重不一致**：`IndexManager.SCHEMA_VERSION = 2`（写入 `schema_meta`），而 `StateModel` 默认 `schema_version = 9`，`sql_state_manager.rebuild_state_dict()` 默认写 `9`，migrations 推到 `v11`。读取端到底信哪一个？没有 evidence 表明有一处在验证。
4. **表定义分散**：40 张表散落在 `index_manager.py`、`rag_adapter.py`、`style_sampler.py`、`metrics.py`、`chapter_lock.py` 5 个不同模块，外加 `migration_auditor.py` 还重复了 2 张 v9 表的 DDL。schema 漂移高风险。

整体健康评级：**可运行但有技术债**。核心写路径（`entities/aliases/state_changes/relationships/plot_thread_registry`）干净、读写一致；边缘表（知识门控、增量抽取、明暗线注册表）生命周期不闭合。

---

## 一、完整表清单

### 1.1 `index.db`（34 张表，全部由 `IndexManager._init_db()` 统一建表）

> 源文件：`ink-writer/scripts/data_modules/index_manager.py`（2238 行）

| # | 表名 | 引入版本 | INSERT 来源 | SELECT 消费者 | 健康 |
|---|------|---------|-------------|---------------|------|
| 1 | `schema_meta` | v5.1 | `index_manager.py:291`（仅 `schema_version`） | 无消费者 | 孤儿表 |
| 2 | `chapters` | v5.0 | `index_chapter_mixin.py:21` | `sql_state_manager.py:960`、`dashboard/app.py`、`measure_baseline.py`、`context_manager.py` | OK |
| 3 | `scenes` | v5.0 | `index_chapter_mixin.py:78` | `context_manager.py`、`index_chapter_mixin.py` | OK |
| 4 | `appearances` | v5.0 | `index_chapter_mixin.py:163`、`sql_state_manager.py:401` | `index_observability_mixin.py:158`、`context_manager.py:298,603` | OK |
| 5 | `entities` | v5.1 | `index_entity_mixin.py:102,423` | 18+ 处（entities 最热读表）| OK |
| 6 | `aliases` | v5.1 | `sql_state_manager.py`（via entity_mixin） | `index_entity_mixin.py`、`sql_state_manager.py:711` | OK |
| 7 | `state_changes` | v5.1 | `index_entity_mixin.py:326` | 消费者 6+ 处 | OK |
| 8 | `relationships` | v5.1 | `index_entity_mixin.py:430` | 消费者 10+ 处 | OK |
| 9 | `relationship_events` | v5.5 | `index_entity_mixin.py:580` | `index_entity_mixin.py`、`context_manager.py` | OK |
| 10 | `override_contracts` | v5.3 | `index_debt_mixin.py:35` | `index_debt_mixin.py`（9 处）、`context_manager.py` | OK |
| 11 | `chase_debt` | v5.3 | `index_debt_mixin.py:174` | 12 处 | OK |
| 12 | `debt_events` | v5.3 | `index_debt_mixin.py:447` | `index_debt_mixin.py` | OK |
| 13 | `chapter_reading_power` | v5.3 | `index_reading_mixin.py:120` | 11 处（dashboard/context/measure_baseline） | OK |
| 14 | `invalid_facts` | v5.4 | `index_observability_mixin.py:50` | `index_observability_mixin.py:86,98` | OK |
| 15 | `review_metrics` | v5.4 | `index_reading_mixin.py:625` | `measure_baseline.py:211`、`context_manager.py`、`dashboard/app.py` | OK |
| 16 | `chapter_memory_cards` | v5.4 | `index_reading_mixin.py:255` | `context_manager.py`、`build_chapter_index.py` | OK |
| 17 | `plot_thread_registry` | v5.4 | `index_reading_mixin.py:373`、`update_state.py:77` | `foreshadow/tracker.py:59,249`、`plotline/tracker.py:55,231`、`sql_state_manager.py:923`、`context_manager.py` | **热表** |
| 18 | `timeline_anchors` | v5.4 | `index_reading_mixin.py:478` | `context_manager.py`、`index_reading_mixin.py` | OK |
| 19 | `candidate_facts` | v5.4 | `index_reading_mixin.py:561` | `index_reading_mixin.py:605`、`index_observability_mixin.py:215` | 半孤儿 |
| 20 | `rag_query_log` | v5.4 | `index_observability_mixin.py:118` | `index_observability_mixin.py`（内部统计）| 可观测 |
| 21 | `tool_call_stats` | v5.4 | `index_observability_mixin.py:139` | `measure_baseline.py:82`、`index_observability_mixin.py` | OK |
| 22 | `writing_checklist_scores` | Phase F | `index_reading_mixin.py:754` | `index_reading_mixin.py:799,813`、`dashboard/app.py:509` | OK |
| 23 | `narrative_commitments` | P0-3 | `index_manager.py:1038` | `index_manager.py:1074,1084,1096`、`extract_chapter_context.py:736` | OK |
| 24 | `character_evolution_ledger` | v6.4 | `index_manager.py:1112`、`voice_fingerprint/fingerprint.py:184` | `voice_fingerprint/fingerprint.py:102,139,147` | OK |
| 25 | `plot_structure_fingerprints` | v6.4 | `index_manager.py:1219` | `index_manager.py:1242,1255`、`context_manager.py:407` | OK |
| 26 | `volume_metadata` | v6.4 | `index_manager.py:1270` | `index_manager.py:1297,1301,1309` | OK |
| 27 | `protagonist_knowledge` | v8.2 | **（生产代码零 INSERT）** | **（生产代码零 SELECT）** | **孤儿表** ⚠️ |
| 28 | `harness_evaluations` | v9.0 | `index_manager.py:1668` | `context_manager.py`、审查管线 | OK |
| 29 | `computational_gate_log` | v9.0 | （CLI/审查工具内部） | `migration_auditor.py:178,299` | 外部写，轻度消费 |
| 30 | `state_kv` | v13.0 | `sql_state_manager.py:730,763` | `sql_state_manager.py:738,747`、`rebuild_state_dict()` | **v13 关键表** |
| 31 | `disambiguation_log` | v13.0 | `sql_state_manager.py:776,812` | `sql_state_manager.py:785` | 见问题 2 |
| 32 | `review_checkpoint_entries` | v13.0 | `sql_state_manager.py:825,852` | `sql_state_manager.py:834` | OK |
| 33 | `negative_constraints` | v2 schema | `index_manager.py:1361`（via `save_negative_constraints`） | `index_manager.py:1390`、consistency-checker | OK |
| 34 | *索引条目*（`idx_*`） | 散布 | — | — | — |

**字段维度补丁（ALTER TABLE 动态添加）**（`_ensure_column` 机制，`index_manager.py:829-835, 988`）：

- `chapter_reading_power.notes`、`payload_json`
- `review_metrics.review_payload_json`
- `plot_thread_registry.atmospheric_snapshot`（v6.4）
- `chapter_memory_cards.theme_presence`（v6.4）
- `chapter_memory_cards.scene_exit_snapshot`（US-003 预留）
- `character_evolution_ledger.voice_fingerprint_json`（v10）

### 1.2 `vectors.db`（4 张表，由 `rag_adapter.py` 建表）

| 表名 | 写入 | 读取 |
|------|------|------|
| `vectors` | `rag_adapter.py:473` | `rag_adapter.py:292,303,314,323,347`（RAG 查询）|
| `bm25_index` | `rag_adapter.py:605` | `rag_adapter.py`（hybrid 检索）|
| `doc_stats` | `rag_adapter.py:611` | `rag_adapter.py`（BM25 归一化）|
| `rag_schema_meta` | `rag_adapter.py:211`（schema_version） | 无消费者（仅写）|

`vectors_migrating`：临时迁移表，迁移完 RENAME 为 `vectors`（`rag_adapter.py:198`）。

### 1.3 独立数据库（各自 1 张表）

| DB | 表 | 写入 | 读取 |
|----|------|------|------|
| `style_samples.db` | `samples` | `style_sampler.py:118` | `style_sampler.py` |
| `parallel_locks.db` | `chapter_locks` | `chapter_lock.py:78,134` | `chapter_lock.py:71` |
| `cache_metrics.db` | `cache_events` | `prompt_cache/metrics.py:95` | `prompt_cache/metrics.py:116,151` |
| （benchmark）global style_rag | `style_fragments` | `benchmark/style_rag_builder.py:279` | `benchmark/style_rag_builder.py:324+` |

---

## 二、孤儿表 / 半孤儿表

### 2.1 `protagonist_knowledge`（**完全孤儿**）

**Evidence**：
- 建表：`index_manager.py:866-884`
- INSERT：0 处（`Grep "INSERT.*protagonist_knowledge"` 无命中）
- SELECT：0 处（`Grep "FROM protagonist_knowledge"` 无命中）
- agent 规格文档 `ink-writer/agents/data-agent.md:460` 声称"此数据写入 `protagonist_knowledge` 表（`state process-chapter` 统一落库）"，但 `state_manager.py` 与 `sql_state_manager.process_chapter_entities()` 均不处理 `protagonist_knowledge_events`。

**影响**：Layer 5 知识门控（consistency-checker）依赖此表，但表永远是空的。当前走 `protagonist_knowledge_gate`（Context Contract 字段，内存传递），所以功能可能还在工作，但这张表纯属死代码。

### 2.2 `schema_meta`（写 1 次，永不读）

**Evidence**：
- INSERT：`index_manager.py:291` 每次 `_init_db` 写入 `SCHEMA_VERSION`
- SELECT：0 处（`Grep "FROM schema_meta"` 无命中）
- `migration_auditor.py` 有验证基础设施但不查 `schema_meta`

**影响**：升级检测完全靠 `state.json.schema_version`，这张 SQLite 表毫无用处。

### 2.3 `rag_schema_meta`（同上，写 1 次不读）

### 2.4 `incremental_extract`（**整个模块孤儿**）

**Evidence**：
- `ink_writer/incremental_extract/differ.py` 定义 `compute_entity_diff()`
- 生产代码 `import` 0 次（仅 `tests/incremental_extract/test_incremental_extract.py` 使用）
- 没有表关联（该模块不直接操作 SQLite，是一个基于内存 dict 的 diff）

**影响**：本模块声称"增量边界定义"，但 data-agent/sql_state_manager 的写入路径是"整章全量重写"，从未调用 `compute_entity_diff`。"增量抽取"实际未实现。

### 2.5 `candidate_facts`（半孤儿：生产写、消费弱）

**Evidence**：
- INSERT：`index_reading_mixin.py:561`（每章写）
- SELECT：`index_reading_mixin.py:605`（`get_candidate_facts`）仅由 `index_observability_mixin.py:215` 的 stats 计数调用
- `ink-resolve` skill 文档（`SKILL.md:37-45`）确实声称从 `candidate_facts` 读取，但实际走的是 `sqlite3` CLI 而非 Python API，需手动运行

**影响**：候选事实不断积累但没有自动提升为正式事实的机制，ink-resolve 需人工介入。

---

## 三、state.json vs SQLite 字段对齐（docs/state-sqlite-migration-guide.md 对照）

docs 承诺的三阶段迁移路径，当前实际落地情况如下：

### 3.1 Phase 1（高频字段）— 状态：**部分落地**

| 字段 | 目标表 | 实际状态 | Evidence |
|------|--------|---------|---------|
| `progress.current_chapter` | `project_progress` | **表未创建** | `project_progress` 表在整个代码库 0 次出现 |
| `progress.current_volume` | `project_progress` | 同上 | — |
| `strand_tracker` | `strand_tracker_entries` | **表未创建**，走 `state_kv` 代替 | `SELECT ... FROM strand_tracker_entries` 0 命中 |
| `chapter_meta` | `chapter_meta` | 走 `chapters` + `chapter_reading_power` 重建（`sql_state_manager.py:956-984`）| OK |
| `review_checkpoints` | `review_checkpoints` | 实际表名为 `review_checkpoint_entries` | 命名漂移 |

**结论**：docs 里声明的 `project_progress` / `strand_tracker_entries` 表**从未创建**。实际路径是 v13 架构用统一的 `state_kv` 键值表兜底。docs 未同步更新。

### 3.2 Phase 2（中频字段）— 状态：**v13 一步到位**

docs 建议的 `protagonist_snapshots`、`disambiguation_log` 两张表：

| 字段 | docs 目标表 | 实际表 | 状态 |
|------|------------|--------|------|
| `protagonist_state` | `protagonist_snapshots`（按章快照）| `state_kv["protagonist_state"]`（单 JSON） | **未按章快照**。历史状态只能在 `state_changes` 表中回溯 |
| `plot_threads.foreshadowing` | `foreshadowing` 表 | `plot_thread_registry` with `thread_type='foreshadowing'` | ✅ 统一在 `plot_thread_registry` |
| `disambiguation_warnings` | `disambiguation_log` | `disambiguation_log`（存在）| ✅ 但 ink-resolve 未切换 |

### 3.3 Phase 3（state.json 降级为配置文件）— 状态：**部分落地，存在双写路径**

v13 架构（`docs/memory_architecture_v13.md`）承诺 "state.json ← rebuild_state_json()（视图缓存）"。当前现实：

- ✅ `SQLStateManager.rebuild_state_dict()` / `rebuild_state_json()` 实现完整（`sql_state_manager.py:860-917`）
- ✅ `StateManager.flush()` 在写时同步 state_kv（`state_manager.py:420-467`）
- ❌ `ink-resolve` 仍然 `json.loads(Path('...state.json'))` 读取 `disambiguation_pending`（`ink-resolve/SKILL.md:28-33`）
- ❌ `update_state.py` 直接写 state.json（而非 state_kv）
- ❌ `init_project.py` 直接写 state.json
- 📝 README/agent 规格中仍大量引用 state.json 作为事实源

**结论**：v13 是"SQLite 为写事实源、state.json 为读视图"，但并非"SQLite 为唯一事实源"。

### 3.4 state.json 字段集合 vs state_kv keys

根据 `state_schema.py` 和 `rebuild_state_dict()`：

| state.json 顶层字段 | 存储位置 | 是否出现在 state_kv |
|--------------------|---------|---------------------|
| `schema_version` | state_kv:"schema_version" | ✅ |
| `project_info` | state_kv | ✅ |
| `progress` | state_kv | ✅ |
| `protagonist_state` | state_kv | ✅ |
| `relationships` | state_kv + `relationships` 表 | ✅（重复存储）|
| `disambiguation_warnings` | `disambiguation_log` table | ❌（不在 kv）|
| `disambiguation_pending` | `disambiguation_log` table | ❌ |
| `world_settings` | state_kv | ✅ |
| `plot_threads` | `plot_thread_registry` → 重建 | ❌（重建视图）|
| `review_checkpoints` | `review_checkpoint_entries` | ❌ |
| `chapter_meta` | `chapters` + `chapter_reading_power` | ❌（重建视图）|
| `strand_tracker` | state_kv | ✅ |
| `harness_config` | state_kv | ✅ |
| `hook_contract_config` | state_kv | ✅ |
| `voice_fingerprint_config` | state.json only（v10 迁移）| ❌ 可能是遗漏 |
| `plotline_lifecycle_config` | state.json only（v11 迁移）| ❌ 可能是遗漏 |

**⚠️ `voice_fingerprint_config` / `plotline_lifecycle_config`**：v10/v11 migrations 只写 state.json，未进入 state_kv。`rebuild_state_dict()` 只处理 v9 以前的 key list（`sql_state_manager.py:993-997`），这两个 config 不在 `kv_keys` 列表中。**如果 state.json 被清空并从 SQLite 重建，这两个 config 将丢失。**

---

## 四、伏笔（Foreshadow）生命周期

### 4.1 表设计（`plot_thread_registry`）

字段：`thread_id, title, content, thread_type='foreshadowing', status, priority, planted_chapter, last_touched_chapter, target_payoff_chapter, resolved_chapter, related_entities, notes, confidence, payload_json, atmospheric_snapshot`

### 4.2 代码对齐

- **写入**：
  - `index_reading_mixin.py:373` `save_plot_thread()`（每章写伏笔更新）
  - `update_state.py:77` 同步一条伏笔到 `plot_thread_registry`
- **读取 / 分析**：
  - `foreshadow/tracker.py:50-80` 加载 active 伏笔
  - `foreshadow/tracker.py:233-298` 热力图（heatmap）
  - `sql_state_manager.py:925-954`（`_rebuild_plot_threads`）重建 state.json 视图
  - `context_manager.py` 将伏笔注入上下文
- **判定**：
  - `_classify_overdue()`：根据 `target_payoff_chapter + grace` 判定逾期
  - `_classify_silent()`：根据 `last_touched_chapter` 判定沉默
  - `build_plan_injection()`：产生 forced_payoffs 注入 ink-plan

### 4.3 健康度

- ✅ 表字段覆盖完整（含 priority、confidence、target_payoff_chapter、last_touched_chapter）
- ✅ 写路径单一（`save_plot_thread`）
- ✅ 读路径清晰（tracker 扫描 + context 注入）
- ⚠️ `resolved_chapter` / `status='resolved'` 的转换逻辑分散：`tracker.py` 只读不写，谁写 resolved？grep 发现由 data-agent 提取时由 `save_plot_thread(status='resolved', resolved_chapter=N)` 更新。闭环存在但没有显式的 "resolve_foreshadow" API。

---

## 五、明暗线（Plotline）追踪

### 5.1 表设计

**复用 `plot_thread_registry`**（通过 `thread_type='plotline'` 区分）。`line_type` (main/sub/dark) 存储在 `payload_json`。

### 5.2 代码对齐

- **写入**：同伏笔（`save_plot_thread` 统一入口）
- **读取**：`plotline/tracker.py:46-86` 加载 active plotlines，从 `payload_json` 解析 `line_type`
- **判定**：
  - `main_max_gap=3`, `sub_max_gap=8`, `dark_max_gap=15`
  - `_classify_inactive()`：超出 gap 阈值视为断更

### 5.3 健康度

- ✅ 读写闭环
- ⚠️ **类型字段嵌在 JSON**：`line_type` 存 `payload_json` 而不是独立列，无法建索引、不能直接 SQL 过滤。如果明暗线数量多，性能会变差（目前通过 `thread_type='plotline'` 先过滤再 JSON 解析）。
- ✅ `state_schema.py:114` 有 `plotline_registry` 字段但实际未用（`PlotThreads.plotline_registry`），实际走 `plot_thread_registry` 表。JSON 与 SQLite 命名重复。

---

## 六、实体消歧（ink-resolve）数据流

### 6.1 理论流程（文档）

```
Data Agent 提取低置信实体 (conf < 0.5)
    ↓
写入 disambiguation_pending
    ↓
ink-resolve 呈现给用户
    ↓
用户决策（合并/新建/跳过/删除）
    ↓
执行 register-alias 或 create-entity
    ↓
清理 pending
```

### 6.2 实际流程（代码）

**写入端**：
- `sql_state_manager.py:812`（bulk_add_disambiguation_entries）写入 `disambiguation_log` 表
- `state_manager.py` 兼容写法：同时写 state.json 的 `disambiguation_pending` 列表

**读取端**：
- `ink-resolve/SKILL.md:28-33`：**直接读 state.json**（`json.loads(Path('...state.json'))` 然后 `state.get('disambiguation_pending', [])`）
- `ink-resolve/SKILL.md:36-44`：读 `candidate_facts` 通过 `sqlite3` CLI

**处理端**：
- Step 3 执行 `ink.py index register-alias` 或 `create-entity`
- Step 4 清理：**更新 state.json 移除条目**（未经过 `resolve_disambiguation_entry` SQLite 方法）

### 6.3 健康度问题

- ⚠️ **双写但单读**：`disambiguation_log` 表被正确写入、正确提供 `resolve_disambiguation_entry(id)` API，但 `ink-resolve` skill 完全不用。它读 state.json、更新 state.json。
- ⚠️ 如果 SQLite 是真的单一事实源，`rebuild_state_json()` 会把 `disambiguation_log` 重建回 state.json。但如果 ink-resolve 先更新了 state.json、下次章节写入时 `StateManager.flush()` 又用 SQLite 重建，**ink-resolve 的修改可能被覆盖**。
- ✅ 低置信度阈值机制（0.5/0.8）在 `config.py:195-196` 配置，agent 规格文档 `entity-management-spec.md` 有清晰定义

---

## 七、增量抽取（incremental_extract）

### 7.1 模块设计

`ink_writer/incremental_extract/differ.py` 提供 `compute_entity_diff(current, prior, chapter, prior_chapter)`：
- 对比两章实体字段，产出 `new/changed/unchanged/removed` 分桶
- 配置项 `always_extract_protagonist`、`diff_confidence_threshold=0.8`、`max_prior_state_age=5`

### 7.2 代码对齐

- **调用者**：**仅测试**（`tests/incremental_extract/test_incremental_extract.py`）
- **生产代码 import**：0 次（Grep 确认）
- **不与 SQLite 交互**：模块注释说"加载 chapter N-1 的实体快照（from index.db state_changes + entities）"，但 `differ.py` 接收的是内存 list，没有任何 `sqlite3.connect`

### 7.3 健康度

- ❌ **模块未接线到数据流**。data-agent 的写入路径是"整章全量"，state_changes 直接追加，未做 diff
- 📝 配置文件 `config/incremental-extract.yaml` 可能存在但 loader 默认值兜底，不报错

---

## 八、Top 3 数据问题

### 问题 1：v13 "单一事实源"架构未闭合，ink-resolve 绕过 SQLite 写回路径

**Evidence**：
- `docs/memory_architecture_v13.md:33`"SQLite 为唯一事实源，state.json 降级为视图缓存"
- `ink-resolve/SKILL.md:28-33,75` 直接读写 state.json
- `sql_state_manager.py:796` 定义了 `resolve_disambiguation_entry(id)` 但无调用者

**影响**：多进程 / 并发写场景下，`rebuild_state_json()` 可能覆盖 ink-resolve 的修改；审计时 SQLite 和 state.json 不一致。

**修复方向**：ink-resolve Step 4 应改为调用 `sqlite3 ink.py ... disambiguation resolve --id N`，然后调 `rebuild_state_json` 刷视图。

### 问题 2：孤儿表 `protagonist_knowledge` 与孤儿模块 `incremental_extract` 均为死代码

**Evidence**：
- `protagonist_knowledge`：建表 `index_manager.py:866`，INSERT 0 处、SELECT 0 处（Grep 穷举）
- `incremental_extract`：`compute_entity_diff` 仅在 tests 中被调用
- 两者都有 agent 规格文档引用，但规格与实现脱节

**影响**：维护负担、schema 漂移、新手误读认为功能存在。

**修复方向**：
- (a) 移除或实现 `protagonist_knowledge`（目前知识门控走 Context Contract 内存，不需要表）
- (b) 把 `incremental_extract` 接入 data-agent 流程，或明确标注为 `experimental/archived`

### 问题 3：schema 版本漂移三处不一致

**Evidence**：
- `IndexManager.SCHEMA_VERSION = 2`（`index_manager.py:274`）→ 写入 `schema_meta` 表（无人读）
- `StateModel.schema_version = 9`（`state_schema.py:290`）→ 默认值
- `migrate.py` 最新 migration 推到 `v11`（plotline_lifecycle_config）
- `state-sqlite-migration-guide.md` 用 `schema_version 8→9` 描述 v13 架构
- `rebuild_state_dict()` 默认 `int(kv.get("schema_version", 9))`

另外 **Phase 1 宣称的表从未创建**：`project_progress`、`strand_tracker_entries`、`protagonist_snapshots` 全部 0 命中。

**影响**：未来迁移（v11→v12 等）无法通过 SQLite 端检测状态，只能读 state.json；docs 描述的 DDL 与实际 DDL 对不上，新贡献者容易看错。

**修复方向**：
- 统一：`IndexManager.SCHEMA_VERSION` 与 `state.schema_version` 保持同步（或拆成 "index_db_version" 与 "state_version"）
- 更新 `state-sqlite-migration-guide.md` 以反映 v13 架构（state_kv 替代单独分表）

---

## 九、整体健康评估

**数据层健康：中等偏上。核心写路径健壮（entities/aliases/state_changes/relationships/plot_thread_registry 读写对称），但 v13 "单一事实源"仅完成 60%——SQLite 已就绪但多个 skill/migration 仍直写 state.json，外加 2 张孤儿表 + 1 个孤儿模块 + 3 处 schema 版本号漂移，形成中等技术债。**

---

## 附录 A：完整表名索引

34 tables in `index.db`: `schema_meta` · `chapters` · `scenes` · `appearances` · `entities` · `aliases` · `state_changes` · `relationships` · `relationship_events` · `override_contracts` · `chase_debt` · `debt_events` · `chapter_reading_power` · `invalid_facts` · `review_metrics` · `chapter_memory_cards` · `plot_thread_registry` · `timeline_anchors` · `candidate_facts` · `rag_query_log` · `tool_call_stats` · `writing_checklist_scores` · `narrative_commitments` · `character_evolution_ledger` · `plot_structure_fingerprints` · `volume_metadata` · `protagonist_knowledge` · `harness_evaluations` · `computational_gate_log` · `state_kv` · `disambiguation_log` · `review_checkpoint_entries` · `negative_constraints`

4 tables in `vectors.db`: `vectors` · `bm25_index` · `doc_stats` · `rag_schema_meta`

1 table each: `samples`（style_samples.db）· `chapter_locks`（parallel_locks.db）· `cache_events`（cache_metrics.db）· `style_fragments`（benchmark）

**Total: 41 SQLite tables across 5 databases.**

## 附录 B：关键文件路径

- **主 schema**: `/Users/cipher/AI/ink/ink-writer/ink-writer/scripts/data_modules/index_manager.py` (2238 行)
- **state 管理器**: `/Users/cipher/AI/ink/ink-writer/ink-writer/scripts/data_modules/sql_state_manager.py` (1130 行)
- **state schema**: `/Users/cipher/AI/ink/ink-writer/ink-writer/scripts/state_schema.py`
- **迁移**: `/Users/cipher/AI/ink/ink-writer/ink-writer/scripts/migrate.py`
- **RAG vectors**: `/Users/cipher/AI/ink/ink-writer/ink-writer/scripts/data_modules/rag_adapter.py`
- **Foreshadow tracker**: `/Users/cipher/AI/ink/ink-writer/ink_writer/foreshadow/tracker.py`
- **Plotline tracker**: `/Users/cipher/AI/ink/ink-writer/ink_writer/plotline/tracker.py`
- **Incremental extract**: `/Users/cipher/AI/ink/ink-writer/ink_writer/incremental_extract/differ.py` (orphan)
- **ink-resolve skill**: `/Users/cipher/AI/ink/ink-writer/ink-writer/skills/ink-resolve/SKILL.md`
- **v13 arch doc**: `/Users/cipher/AI/ink/ink-writer/docs/memory_architecture_v13.md`
- **迁移指南**: `/Users/cipher/AI/ink/ink-writer/ink-writer/references/state-sqlite-migration-guide.md`（已过期）
- **实体管理规范**: `/Users/cipher/AI/ink/ink-writer/ink-writer/references/entity-management-spec.md`
