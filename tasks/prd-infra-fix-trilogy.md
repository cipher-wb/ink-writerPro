# PRD: 基础设施三轮修复（preflight + 设定集同步 + checker 模型兼容）

## Introduction

`/ink-auto` 批量写作流程中发现三个独立但均导致流程中断或数据漂移的基础设施缺陷：

1. **preflight 预检假阳性阻断**：全面 preflight（`ink_writer.preflight.cli`）因路径解析和 env var 加载问题，在项目实际满足条件时仍报 4 项失败
2. **设定集增量未自动同步**：ink-plan Step 7 和 ink-write 写后流程均缺少自动回写机制，设定集 markdown 文件与 index.db 实体表长期不一致
3. **checker agent 模型不兼容**：策划期审查 agent 的 JSON 输出指令仅适配 glm-4.6，deepseek-v4-pro 输出格式不兼容导致解析失败

三个问题互不重叠，可并行交付。

## Goals

- preflight 不再因 CWD / env var 加载问题产生假阳性阻断
- 设定集文件（`设定集/*.md`）与 `index.db` 实体表保持同步，消除手动步骤
- 策划期 checker agent 在任何 session 模型下 JSON 解析成功率 ≥ 95%

---

## P0 — preflight 路径与环境变量修复

### US-P0-001: preflight CLI 支持 --project-root 并解析绝对路径

**Description:** As a 写作者, I want `python -m ink_writer.preflight.cli` 无论从哪个 CWD 运行都能正确找到项目文件，so that `/ink-auto` 的 `claude -p` 子进程不会因路径错误产生假阳性阻断。

**Root cause:** `ink_writer/preflight/cli.py:43-45` 三个默认值使用相对路径 `Path("benchmark/reference_corpus")` / `Path("data/case_library")` / `Path("data/editor-wisdom/rules.json")`。当 `claude -p` 子进程 CWD ≠ PROJECT_ROOT 时（ink-auto.sh 不 cd，子进程继承用户 shell 的 CWD），路径解析失败。

**Fix:**
- `cli.py` 新增 `--project-root` 参数
- `_build_config()` 中，若 `--project-root` 传入，将三个相对路径 join 到 `project_root` 后 resolve 为绝对路径
- `ink-writer/skills/ink-write/SKILL.md` Step 0 的 preflight 命令增加 `--project-root "${PROJECT_ROOT}"` 参数

**Acceptance Criteria:**
- [ ] `cli.py` 支持 `--project-root`，传入后所有路径基于 project_root 解析
- [ ] 不传 `--project-root` 时行为不变（向后兼容）
- [ ] 从 `/tmp` 运行 `python -m ink_writer.preflight.cli --project-root /path/to/project` 时，6 项检查的路径全部解析正确
- [ ] ink-write SKILL.md Step 0 命令包含 `--project-root`
- [ ] 在 PROJECT_ROOT = `/Users/cipher/AI/小说/ink/ink-writer` 的项目上执行 preflight，`reference_corpus_readable` 报告 `1487 files readable`（而非"为空"）
- [ ] Typecheck/lint 通过

### US-P0-002: EMBED_API_KEY / RERANK_API_KEY 检查从 DataModulesConfig 读取

**Description:** As a 写作者, I want preflight 的 API Key 检查从项目配置系统读取而不仅仅是裸环境变量，so that 在 `~/.claude/ink-writer/.env` 中已配置的 key 能被正确识别。

**Root cause:** `ink_writer/preflight/checks.py:98-100` 的 `check_embedding_api_reachable()` 和 `check_rerank_api_reachable()` 仅检查 `os.environ.get("EMBED_API_KEY")`。但实际项目中 key 存储在 `~/.claude/ink-writer/.env`，仅在 shell 启动时通过 env-setup.sh 加载。`claude -p` 子进程不会自动 source 这个文件。

**Fix:**
- `check_embedding_api_reachable()` / `check_rerank_api_reachable()` 改为接受可选的 `project_root` 参数
- 若传入 `project_root`，使用 `DataModulesConfig.from_project_root()` 读取 `embed_api_key` / `rerank_api_key`
- 若未传入 project_root，fallback 到 `os.environ`（保持向后兼容）
- `checker.py:_run_all_checks()` 将 project_root 透传给这两个检查函数

**Acceptance Criteria:**
- [ ] 当项目 `~/.claude/ink-writer/.env` 中 `EMBED_API_KEY` 已配置但 `os.environ["EMBED_API_KEY"]` 不存在时，preflight 仍报告 `embedding_api_reachable: OK`
- [ ] `RERANK_API_KEY` 同理
- [ ] 不传 project_root 时，行为与原先一致（只检查 os.environ）
- [ ] Typecheck/lint 通过

### US-P0-003: Qdrant 检查默认使用 in-memory 模式

**Description:** As a 写作者, I want preflight 不对本地 Qdrant 服务做硬性要求，so that 没有 Docker 或独立 Qdrant 进程的项目也能通过预检。

**Root cause:** `cli.py` 的 `--qdrant-in-memory` 默认 `False`，导致 preflight 去连 `127.0.0.1:6333`。大多数开发者本地没有运行 Qdrant。

**Fix:**
- `cli.py` 中 `--qdrant-in-memory` 默认值改为 `True`
- 或：新增自动检测逻辑 —— 若项目配置文件未显式指定外部 Qdrant 连接信息，自动切 `qdrant_in_memory=True`

**Acceptance Criteria:**
- [ ] 不传 `--qdrant-host` / `--qdrant-port` 时，默认走 in-memory 模式，检查通过
- [ ] 显式传 `--no-qdrant-in-memory` 时，行为与原先一致（连接外部 Qdrant）
- [ ] Typecheck/lint 通过

### US-P0-004: 统一 ink-auto.sh 与 ink-write Step 0 的 preflight 入口

**Description:** As a 写作者, I want 简单 preflight（`ink.py preflight`）和全面 preflight（`ink_writer.preflight.cli`）使用同一套检查逻辑，so that ink-auto.sh 启动阶段的预检结果与每章写作的预检结果一致。

**Root cause:** 两套 preflight 独立实现，检查项不同：
- `ink.py preflight`（ink_writer/core/cli/ink.py:227-355）：检查脚本/项目/索引/Embedding API 连通性
- `ink_writer.preflight.cli`：检查 reference_corpus / case_library / editor_wisdom / qdrant / embed / rerank

ink-auto.sh 用简版通过后，进入写作循环的 `claude -p` 子进程再跑全面 preflight 却失败，造成矛盾。

**Fix 方案:** 两种选择（实施时确认）：
- 方案 A（推荐）：`ink.py preflight` 内部委托给 `ink_writer.preflight.checker.run_preflight()`，加 `--project-root` 传递
- 方案 B：`ink-auto.sh:338` 的简版 preflight 调用改为全面 preflight CLI（带正确 --project-root）

**Acceptance Criteria:**
- [ ] 两个入口的检查结果一致（相同项目、相同参数 → 相同 pass/fail）
- [ ] ink-auto.sh 预检失败原因与 ink-write Step 0 预检失败原因可对照
- [ ] Typecheck/lint 通过

---

## P1 — 设定集自动同步

### US-P1-001: 新增 `scripts/sync_settings.py` 自动回写工具

**Description:** As a 写作者, I want 新角色/势力/地点能自动从 index.db 和大纲回写到 `设定集/` 文件，so that 不需要在每次 ink-plan 或连续写作后手动更新设定集。

**Root cause:** ink-plan Step 7 有规范但无自动化脚本（纯 AI 手动执行 Read/Write/Edit）。ink-write 的 data-agent 提取新实体到 `index.db` 但从不写回 `设定集/`。两个缺口导致设定集 markdown 文件与数据库实体表脱节。

**Fix:**
- 新建 `scripts/sync_settings.py`，功能：
  1. 读取 `index.db` entities 表，找出 `设定集/` 文件中未覆盖的实体（按 name + tier 匹配）
  2. 读取所有卷大纲文件（`大纲/第*卷-详细大纲.md`），提取大纲中声明的角色/势力/地点
  3. 按 entity_type 分类写入对应设定集文件：
     - 角色 → `设定集/主角组.md` 或 `设定集/角色卡/` （按 tier 决定）
     - 势力 → `设定集/世界观.md` 的势力章节
     - 地点 → `设定集/世界观.md` 的地点章节
     - 反派 → `设定集/反派设计.md`
  4. 写入策略：增量追加，格式与现有条目一致（含首次出场章、关系、红线）
  5. 冲突检测：若大纲声明的信息与设定集已有条目冲突，输出 `BLOCKER` 列表到 stdout 并 exit 1
- CLI 接口：
  ```bash
  python scripts/sync_settings.py --project-root "$PROJECT_ROOT" [--dry-run] [--volume N]
  ```

**Acceptance Criteria:**
- [ ] 运行后，`设定集/` 文件中出现新增角色（如郑伯元、三叔、宋知意、郑海、马文斌）的条目
- [ ] 重复运行幂等（不会重复追加相同条目）
- [ ] `--dry-run` 模式只输出差异，不修改文件
- [ ] 冲突检测命中时 exit 1，输出冲突详情
- [ ] 人眼审查：新增条目的格式与现有条目一致
- [ ] Typecheck/lint 通过

### US-P1-002: ink-plan Step 7 改为调用脚本

**Description:** As a 写作者, I want ink-plan 完成后设定集自动同步，so that 不用收到"请手动回写"的提示。

**Fix:**
- `ink-writer/skills/ink-plan/SKILL.md` 的 Step 7 从 AI 手动操作改为：
  ```bash
  python3 -X utf8 "${SCRIPTS_DIR}/sync_settings.py" --project-root "$PROJECT_ROOT" --volume {volume_id}
  ```
- Step 8 校验 #7 的检查逻辑改为读取脚本返回值

**Acceptance Criteria:**
- [ ] ink-plan 执行 Step 7 时不再出现 AI 手动 Read/Write/Edit 设定集文件的 trace
- [ ] Step 8 校验 #7 依然生效（脚本 exit 1 时 BLOCKER 触发）
- [ ] 向后兼容：若 `sync_settings.py` 不存在，Step 7 回退到原先的 AI 手动模式

### US-P1-003: ink-write Step 5.5 增加自动同步调用

**Description:** As a 写作者, I want 每章写完后设定集自动吸纳新增实体，so that 连续写作 50 章后设定集不会严重过时。

**Fix:**
- `ink-writer/skills/ink-write/SKILL.md` Step 5.5（Data Agent 完成后）增加：
  ```bash
  python3 -X utf8 "${SCRIPTS_DIR}/sync_settings.py" --project-root "$PROJECT_ROOT" 2>/dev/null || true
  ```
- 失败不阻断写作流程（设定集同步是 best-effort）

**Acceptance Criteria:**
- [ ] 每章 writing 完成后自动触发 settings sync
- [ ] sync 失败不影响章节 writing 成功状态
- [ ] 连续写 5 章后，`设定集/` 中可见所有新增角色的条目

---

## P2 — checker agent 模型兼容性

### US-P2-001: 加固 agent spec 的 JSON 输出指令

**Description:** As a 写作者, I want 策划期审查 agent 在 deepseek-v4-pro 模型下也能正确输出 JSON，so that Step 99 审查不再因"基础设施故障"假阳性阻断。

**Root cause:** `protagonist-agency-skeleton-checker` 和 `chapter-hook-density-checker` 的 agent spec prompt 中的 JSON 输出指令仅适配 glm-4.6 的输出格式。deepseek-v4-pro 可能在 JSON 外包裹 markdown fence，或字段名/结构有差异，导致调用方 JSON 解析失败。

**Fix:**
- 更新两个 agent spec 文件，JSON 输出指令部分：
  1. 显式禁止 markdown fence：`Do NOT wrap the JSON in markdown code fences (```json). Output raw JSON only.`
  2. 指定精确 JSON Schema 示例（字段名/类型/必填）
  3. 增加 retry 指令：`If your previous output was not valid JSON, output the raw JSON object only, with no other text.`
- 同时在 `ink-writer/agents/` 中新增 `shared/json-output-rules.md` 引用文件，所有 LLM checker agent 统一引用

**Acceptance Criteria:**
- [ ] `protagonist-agency-skeleton-checker` 在 deepseek-v4-pro 下输出裸 JSON（无 markdown fence）
- [ ] `chapter-hook-density-checker` 同上
- [ ] 解析端成功提取 JSON（不再报"JSON解析失败"）
- [ ] 同样兼容 glm-4.6（不引入回归）
- [ ] 新增 `agents/shared/json-output-rules.md` 文件

### US-P2-002: 调用层增加 JSON 解析容错

**Description:** As a 开发者, I want checker 的 JSON 解析逻辑能容错处理常见格式差异，so that 未来切换模型时不会再次出现同类故障。

**Fix:**
- 在 checker 调用层（`ink_writer/checker_pipeline/llm_checker_factory.py` 或 `ink_plan_review.py`）增加 JSON 提取函数：
  1. 尝试直接 `json.loads()`
  2. 若失败，用 regex 提取首个 `{...}` 或 `[...]` 块再解析
  3. 若仍失败，strip markdown fence（```` ```json ... ``` ````）再解析
  4. 三次尝试全部失败 → 抛明确的 `CheckerJSONParseError` 含原始输出片段

**Acceptance Criteria:**
- [ ] JSON 容错逻辑在 `llm_checker_factory.py` 或共享 util 中实现
- [ ] 单元测试覆盖：裸 JSON / markdown-fenced JSON / 含前缀文本的 JSON / 含后缀文本的 JSON
- [ ] 所有现有 checker 的 JSON 解析路径走新容错逻辑
- [ ] 解析失败时抛出的错误消息包含原始输出前 200 字符（便于诊断）
- [ ] Typecheck/lint 通过

---

## Functional Requirements

- FR-1: `ink_writer.preflight.cli` 必须支持 `--project-root` 参数
- FR-2: preflight API Key 检查必须同时支持 `os.environ` 和 `DataModulesConfig` 两个来源
- FR-3: preflight Qdrant 检查默认使用 in-memory 模式
- FR-4: `scripts/sync_settings.py` 必须能从 index.db + 大纲增量回写设定集文件
- FR-5: ink-plan Step 7 和 ink-write Step 5.5 必须自动调用 sync_settings.py
- FR-6: checker agent spec 必须包含 model-agnostic JSON 输出指令
- FR-7: checker JSON 解析路径必须包含 3 级容错

## Non-Goals

- 不重构 preflight 的整体架构（只修复路径/环境问题）
- 不改动设定集文件的格式规范
- 不替换 checker agent 的底层 LLM 调用链（只修 prompt + 容错）
- 不同步非实体类设定（如修炼体系细节、世界观哲学层面）
- 不在此 PRD 中处理 editor-wisdom / live-review 模块的其他问题

## Technical Considerations

- **preflight 路径**: 所有路径解析集中在 `cli.py:_build_config()` 中，改为基于 `project_root` resolve 绝对路径后传递给 `PreflightConfig`
- **env var 加载**: `DataModulesConfig.from_project_root()` 已实现从 `.env` 文件读取，`checks.py` 复用即可
- **设定集同步**: 首次运行时从头扫描 index.db 全量实体表 + 所有大纲文件，后续运行可考虑增量（但不在本 PRD 范围内）
- **JSON 容错**: 提取函数建议放在 `ink_writer/core/infra/json_util.py`，供 checker pipeline 和 planning_review 共用
- **向后兼容**: P0 和 P2 的修改均保持 API 向后兼容（默认参数不变或新增可选参数）

## Success Metrics

- `/ink-auto 10` 从启动到第 1 章开始写作，preflight 阶段零假阳性阻断
- 连续写 10 章后，`设定集/` 中新增角色条目数 ≥ index.db 中同期新增实体数
- Step 99 策划期审查在 deepseek-v4-pro 下 `chapter-hook-density` 和 `protagonist-agency-skeleton` 不再因 JSON 解析失败而报"基础设施故障"

## Open Questions

- P0 US-P0-004（统一 preflight 入口）：实施时具体选方案 A（ink.py 委托）还是方案 B（ink-auto.sh 改用全面 CLI）？
- P1 `sync_settings.py` 的实体匹配策略：name 精确匹配还是模糊匹配？（建议精确 + alias 匹配，避免误覆盖）
- P2 agent spec 更新后是否需要在 glm-4.6 环境下回归测试？（建议至少手动跑一次确认无回归）
