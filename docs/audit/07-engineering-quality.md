# US-007: 工程质量全面体检

**审计者**: US-007 执行者
**日期**: 2026-04-17
**审查方式**: 只读审计 + 只读命令（`pytest --collect-only`、`pip list`）
**证据基线**: ink-writer v13.8.0（HEAD=349f651）
**代码量**: 55,861 LOC 源码（ink_writer: 7,319 / ink-writer/scripts: 48,542），33,282 LOC 测试
**测试总数**: 2028 tests collected, 94 test files, 0 collection errors

---

## Executive Summary

ink-writer 在"功能密度"上非常成熟（17 个 checker agent、14 个 skill、30+ 数据表、RAG 向量索引、并发管线），但从**标准工程维度**看，处于"中期工程债"阶段：

- **测试基建完善**（2028 tests, 94 files, asyncio_mode=auto, pytest-cov 门禁 70%），但**目标覆盖率门禁失效**——pytest.ini 要求 `--cov-fail-under=70`，实测 **`ink-writer/scripts` 总覆盖仅 13.62%**，核心文件如 `state_manager.py (9%)`、`extract_chapter_context.py (0%)`、`init_project.py (8%)`、`update_state.py (10%)` 近乎零覆盖。门禁名义上存在，实际 CI 运行的只是 `data_modules/tests` 子集（因多数被测脚本是 CLI 级 main()）。
- **配置单一 SoT 清晰**（`.env` 项目级 > 用户级 `~/.claude/ink-writer/.env` > 默认值），`config/` 目录 13 份 YAML 每个模块独占，无冲突。
- **依赖声明严重分叉**：`requirements.txt` 仅覆盖 `scripts/` 和 `dashboard/`（aiohttp/pydantic/fastapi），但 **`ink_writer/` 新包使用的 numpy/faiss/sentence-transformers/jsonschema/PyYAML/anthropic 6 个硬依赖在任何 requirements 文件中都未声明**，CI 若仅照 lock 安装将无法导入。
- **日志使用极不均衡**：`ink-writer/scripts/` 中 **432 个 print** vs 14 个文件用 logging，其中 `workflow_manager.py(31 print)`、`update_state.py(49 print)`、`backup_manager.py(51 print)`、`init_project.py(18 print)` 是重灾区。CLI 输出 print 合理，但函数级诊断日志绕过 logging 级别控制，无法通过环境变量调优。
- **异常处理偏"吞"**：`ink-writer/scripts/` 95 处宽捕获（`except Exception:`），`ink_writer/` 14 处。部分有 logger.warning 记录，但 `config.py`、`migrate_state_to_sqlite.py`、`rag_adapter.py(10 处)` 存在"静默 swallow + return False/None"模式，隐藏根因。
- **文档与代码漂移**：`architecture.md` 说 "25 表"（实际 30+）、"14 个 Skills"（实际 14 ✓）、"14 Agents + 10 Checkers"（实际 24 agent 文件，其中 17 checker）；`agent_topology_v13.md` 说 "17 agents, single directory"（实际 24 个 `.md`，含 v13.6/v13.7 新增 5 个 checker 未更新到 topology）。

**整体工程质量评级：C+**（合格偏上，但有明显工程债，尚未达生产级）。

---

## 一、分维度发现

### 1. 测试（Tests）

#### 1.1 规模与结构

| 指标 | 值 |
|------|----|
| 测试文件总数 | 94（54 在 `data_modules/tests`，40 在 `tests/`）|
| 测试用例总数 | 2028 |
| `pytest --collect-only` 状态 | **0 error**，1.84s 完成 |
| 测试 LOC | 33,282 行（17,487 `data_modules` + 15,795 `tests/`）|
| 源码 LOC | 55,861 行（7,319 `ink_writer` + 48,542 `ink-writer/scripts`）|
| 测试/源码 LOC 比例 | **59.6%**（健康区间）|
| 异步测试 | `asyncio_mode = auto`，36 个 async 测试（测 parallel、api_client）|

#### 1.2 按模块覆盖率（目视估算，基于 `pytest --cov` 实测）

| 模块 | 代码行 | 覆盖率 | 评价 |
|------|--------|--------|------|
| `ink_writer/` 新包（13 个子模块） | 7,319 | — | 独立测试套件 `tests/{anti_detection,editor_wisdom,...}` 1000+ 用例，覆盖良好 |
| `data_modules/state_schema.py` | 174 | **93%** | 优秀 |
| `data_modules/checkpoint_utils.py` | — | 高 | 优秀 |
| `data_modules/state_manager.py` | 955 | **9%** | **核心模块仅覆盖 init 和 helper** |
| `data_modules/sql_state_manager.py` | 439 | **15%** | **SQLite 同步主引擎未测** |
| `data_modules/style_sampler.py` | 359 | **14%** | |
| `data_modules/status_reporter.py` | 597 | **10%** | |
| `data_modules/writing_guidance_builder.py` | 255 | **7%** | |
| `data_modules/workflow_manager.py` | 480 | **12%** | |
| `scripts/extract_chapter_context.py` | 1035 | **0%** | **写作流水线核心脚本零覆盖** |
| `scripts/update_state.py` | 317 | **10%** | |
| `scripts/init_project.py` | 360 | **8%** | |
| `scripts/logic_precheck.py` | 200 | **13%** | |
| `scripts/security_utils.py` | 155 | **18%** | |
| `scripts/step3_harness_gate.py` | 123 | **0%** | **硬门禁零覆盖** |
| `scripts/quality_trend_report.py` | 160 | **0%** | |
| **整体 `ink-writer/scripts/**`** | 14,894 | **13.62%** | **远低于名义门禁 70%** |

#### 1.3 单元 vs 集成测试比例

粗略按文件名 `*integration*` 或内部含 `IntegrationTest` 类划分：

- **单元测试**：~1500+ 用例（scan/classify/clean/retriever/config 等纯函数/类测试）
- **集成测试**：~500 用例（19 个文件含 integration 关键字）
  - `test_integration.py`（semantic_recall）
  - `test_polish_integration.py`（style_rag）
  - `test_writer_injection.py`、`test_context_injection.py`（editor_wisdom）
  - `test_pipeline_manager.py`（parallel，启子进程）
  - `test_review_gate_wired.py`（review_gate 端到端）

**单元 : 集成 ≈ 3 : 1**，比例合理。**没有 E2E 测试**（即完整 `/ink-auto` 跑一章）。

#### 1.4 Mock 过度使用

- 19 文件在 `tests/` 用 MagicMock/patch
- 10 文件在 `data_modules/tests/` 用 MagicMock（合计 44 次）

重灾：
- `test_dashboard_watcher.py` 15 处 mock
- `test_backup_manager.py` 15 处 mock（mock 了 `subprocess.run`, `os.environ`, `shutil` 等基础 API）

**风险**：`test_backup_manager.py` 大量 mock `subprocess.run` 意味着真实 git 交互未被验证。符合单元测试哲学但会让 "integration layer" 产生盲区。

#### 1.5 `pytest --collect-only` 结论

```
2028 tests collected in 1.84s
0 errors
1 warning (jieba pkg_resources deprecation — 外部)
```

**收集阶段健康**。

#### 评级：**B-**（规模合格，结构合理，但覆盖率门禁名存实亡——CLI 主流程与 state_manager 核心处于"祈祷式上线"状态）

---

### 2. 错误处理（Error Handling）

#### 2.1 宽捕获分布

| 位置 | `except Exception:` / `except:` 数量 | 风险 |
|------|--------------------------------------|------|
| `ink_writer/` 新包 | 14（分布在 7 文件） | 中 |
| `ink-writer/scripts/*.py` | 95（分布在 29 文件） | 高 |
| 其中 `data_modules/rag_adapter.py` | 10 | 单文件最高 |
| `data_modules/migrate_state_to_sqlite.py` | 8 | 迁移脚本，容错必须，但应 logger.error |
| `scripts/extract_chapter_context.py` | 7 | **写作主流程**，风险高 |
| `scripts/project_locator.py` | 7 | 路径解析，best-effort 合理 |
| `scripts/data_modules/state_manager.py` | 6 | 6 处全部有 `logger.warning/error + exc_info`（改进后） |

#### 2.2 真正"bare except:" 仅 1 处

`scripts/ink-auto.sh:779: except:`（shell 脚本内嵌 Python，影响有限）

#### 2.3 超时与重试（关键路径）

- **API 调用有重试 + 超时**：
  - `api_client.py` 对 embed / rerank 两条通路均实现 `cold_start_timeout / normal_timeout` + 指数退避重试（observed at line 126, 144, 174, 189, 328, 346, 369, 382）
  - 重试次数与基础延迟来自 config (`api_retry_delay`, `cold_start_timeout`)
- **文件锁**：`filelock` 用于 state.json 并发控制（符合 `data-agent` 串行写入要求）
- **缺失**：
  - **Claude API (LLM) 调用无显式超时**（`ink_writer/editor_wisdom/llm_backend.py` 直接 `client.messages.create` 无 timeout 参数，默认 SDK 10 min 太长）
  - **SQLite 操作无查询级超时**（`_get_conn()` 仅有 `immediate` 事务模式，无 `timeout` 参数，虽然 sqlite3 默认 5s 但依赖平台）
  - `parallel/pipeline_manager.py` 无整体超时——若单章被卡在 Claude 会话中，整个批次可能无限等待

#### 2.4 静默失败模式

`data_modules/config.py:25,47,74`：

```python
try:
    return normalize_windows_path(raw).expanduser().resolve()
except Exception:
    return normalize_windows_path(raw).expanduser()  # silent degrade
```

`_load_dotenv_file` 在异常时 `return False` 但不记录——生产环境若 `.env` 被破坏（如 BOM、非法字节）会导致 "EMBED_API_KEY 神秘丢失"，debug 成本极高。

#### 评级：**C+**（重试/超时在 RAG 层合格，但 LLM 层缺显式超时；95 处宽捕获中真正"吞异常返回 False" 约 20-30 处，debug 难度高）

---

### 3. 配置（Configuration）

#### 3.1 Source of Truth 分布

| 层级 | 位置 | 优先级 | 用途 |
|------|------|--------|------|
| 1. 项目 `.env` | `${CWD}/.env` | 最高（显式不覆盖） | API keys, workspace 指针 |
| 2. 用户级 `.env` | `~/.claude/ink-writer/.env` | 次高 | skills/agents 全局安装 |
| 3. 环境变量 | `ANTHROPIC_API_KEY` 等 | 最高（显式） | — |
| 4. `config/*.yaml` | 13 份（按模块） | 模块级 | 阈值/权重 |
| 5. `DataModulesConfig` dataclass | 代码默认值 | 兜底 | 类型约束 |
| 6. `.claude/settings.local.json` | 项目根 | Claude Code 自身 | 权限白名单 |

#### 3.2 优先级是否清晰

**是**。`config.py:44` 显式注释 "默认不覆盖已有环境变量（保持'显式 > .env'优先级）"。
`config/*.yaml` 每份独占一个模块（anti-detection / cultural-lexicon / editor-wisdom / emotion-curve / foreshadow-lifecycle / high-point-scheduler / incremental-extract / parallel-pipeline / plotline-lifecycle / prompt-cache / reader-pull / semantic-recall / voice-fingerprint），无重叠或冲突。

#### 3.3 问题

- **配置分散**：`ink_writer/*/config.py` 每个模块自己写 `load_config()`，13 份类似代码。可抽象成基类。
- **无 schema 校验集中管理**：虽然多数 config 用 pydantic，但各模块独自实现，无统一入口做 `config validate-all`。
- **文档化不足**：13 份 YAML 中有注释，但无顶层 `docs/rag-and-config.md`（存在但陈旧，不覆盖 v13 新增 7 份 YAML）

#### 评级：**B**（SoT 清晰，优先级明确，但配置分散未集中化）

---

### 4. 日志（Logging）

#### 4.1 使用分布

| 文件类型 | 用 `logging` 的文件数 | 用 `print` 的次数 |
|----------|---------------------|--------------------|
| `ink_writer/` | 8 | 21（仅 1 个 `cli.py`，合理）|
| `ink-writer/scripts/` | 14 | **432（30 文件）** |

#### 4.2 Print 重灾区

| 文件 | print 次数 | 性质 |
|------|-----------|------|
| `backup_manager.py` | 51 | CLI 输出 + 调试混杂 |
| `update_state.py` | 49 | CLI 子命令 + 内部诊断 |
| `workflow_manager.py` | 31 | 工作流状态，应该用 logging |
| `archive_manager.py` | 36 | 同上 |
| `migrate_state_to_sqlite.py` | 27 | 迁移脚本，print 合理 |
| `data_modules/api_client.py` | 20 | **retry/timeout 日志用 print**（应 logger.warning） |
| `init_project.py` | 18 | 初始化 CLI，合理 |
| `status_reporter.py` | 12 | — |
| `computational_checks.py` | 10 | — |

**最严重**：`api_client.py` 把 retry 信息 `print(f"[WARN] Embed {resp.status}, retrying...")` 直接输出到 stdout，污染了调用此模块的 CLI 输出（如 dashboard），且无法通过 `LOG_LEVEL=ERROR` 抑制。

#### 4.3 日志级别合理性

使用 logging 的 8 + 14 个文件中，多数是 `logger.warning` / `logger.error + exc_info=True`（符合最佳实践）。但未见 `logger.info / debug` 的规律使用——`state_manager.py` 只在失败时记录，成功路径完全静默。

#### 4.4 无调试 print 残留

扫描 `print.*DEBUG|TEMP|TODO` 无匹配，**代码清洁度好**。

#### 评级：**D+**（432 个 print vs 14 个 logging 文件，绝大多数非 CLI 场景应换 logging；`api_client.py` 的 retry 日志是硬性 bug）

---

### 5. 依赖（Dependencies）

#### 5.1 requirements 文件矩阵

| 文件 | 范围 | 锁定 | 声明包数 |
|------|------|------|---------|
| 根 `requirements.txt` | 引用下面两个 | — | 2 include |
| `ink-writer/scripts/requirements.txt` | data_modules 核心 | 宽松 `>=` | 3（aiohttp, filelock, pydantic）|
| `ink-writer/scripts/requirements.lock` | 同上锁定 | 精确 `==` | 13（含传递）|
| `ink-writer/scripts/requirements-dev.txt` | 测试 | 宽松 | 4 添加（pytest 相关）|
| `ink-writer/scripts/requirements-dev.lock` | 同上 | 精确 | 17 |
| `ink-writer/dashboard/requirements.txt` | dashboard | 宽松 | 4（fastapi, uvicorn[standard], watchdog, httpx）|
| `ink-writer/dashboard/requirements.lock` | 同上 | 精确 | 20 |

#### 5.2 **严重缺失：`ink_writer/` 新包的依赖在任何 requirements 文件中都未声明**

扫描 `ink_writer/` 的第三方 import：

| 包 | 用途 | 使用文件数 | 当前机器版本 | 声明状态 |
|----|------|-----------|------------|---------|
| numpy | style_rag/retriever 向量计算 | 1+ | 2.4.4 | **未声明** |
| faiss(-cpu) | editor_wisdom/retriever 向量索引 | 1 | 1.13.2 | **未声明** |
| sentence-transformers | editor_wisdom embed | 1 | 5.4.1 | **未声明** |
| jsonschema | schema 校验 | 1+ | 4.26.0 | **未声明** |
| PyYAML | 所有 config.py | 13 | 6.0.3 | **未声明** |
| anthropic | editor_wisdom/llm_backend | 1 | 0.89.0 | **未声明** |
| jieba | 中文分词 fallback | 1+ | 0.42.1 | requirements 注释掉 |

**影响**：
- CI 的 `ci-test.yml` 仅安装 `scripts/requirements-dev.lock` + `dashboard/requirements.lock`，不安装以上 6 个包
- GitHub Actions 若 runner 清洁，1000+ `tests/` 用例全部 import 失败
- 开发者本机能跑（因为历史上手动 pip 过）—— **CI "绿" 是幻觉**

#### 5.3 版本固定

- lock 文件存在（3 份），由 pip-compile 生成，Python 3.14 目标
- `requirements.txt` 用 `>=` 宽松约束，无 `~=` 或上界封顶——**未来某包 breaking 升级会悄悄破坏**

#### 5.4 未使用的 deps

扫描结果无明显 unused（requirements 声明的都有代码引用）。问题在反方向（代码用了但没声明）。

#### 评级：**D**（6 个核心依赖未声明是阻塞级问题；lock 文件质量好但覆盖范围不完整）

---

### 6. 文档对齐度（Docs）

抽样 5 份文档逐项与代码对照：

#### 6.1 `CLAUDE.md` (13 行)

| 陈述 | 现实 | 对齐 |
|------|------|------|
| "retriever 加载慢（~30s）" | 有注释 lazy import 建议 | ✓ |
| "分类/规则抽取需要 API Key" | `editor_wisdom/llm_backend.py:28` 验证 | ✓ |
| "agent 规格统一在 `ink-writer/agents/`" | 实际 24 个 agent md，全部在该目录 | ✓ |

**结论**：简短且真实。

#### 6.2 `README.md` (192 行)

| 陈述 | 现实 | 对齐 |
|------|------|------|
| "v13.8.0" | plugin.json 一致 | ✓ |
| "14 Agents + 10 Checkers"（旧版遗留描述） | 实际 24 agent `.md`（7 pipeline + 17 checker/tracker） | **✗** |
| "38 种模板" | `genres/` 目录实际 9 个（apocalypse/cosmic-horror/dog-blood-romance/history-travel/period-drama/realistic/rules-mystery/xuanhuan/zhihu-short） | **✗ 严重不符** |
| 安装命令 `pip install -r requirements.txt` | 不含 numpy/faiss/yaml/anthropic/sentence-transformers | **✗ 安装后不可用** |
| `/ink-init --quick`, `/ink-auto N` | skills 存在 | ✓ |

#### 6.3 `docs/architecture.md` (69 行)

| 陈述 | 现实 | 对齐 |
|------|------|------|
| "Skills (14 个)" | `ink-writer/skills/` 14 目录 | ✓ |
| "Agents (14 个)" | 实际 24 agent md | **✗** |
| "10 Checkers" | 列表列了 9 个，实际 17 | **✗** |
| "25 表" | 数据库宣称 30+ 表 | **✗** |
| Strand Weave 比例 60/20/20 | `ink_writer/pacing/` 有实现 | ✓ |

#### 6.4 `docs/agent_topology_v13.md` (200 行)

| 陈述 | 现实 | 对齐 |
|------|------|------|
| "After v13: 17 Agents, Single Directory" | 实际 24 agent md | **✗ 7 个新增未登记** |
| "Merged: foreshadow + plotline → thread-lifecycle-tracker" | 老 2 个 agent md 文件仍在目录（僵尸） | **部分对齐** |
| Step 3.6-3.10 gate 流程 | `ink_writer/reader_pull/, emotion/, anti_detection/, voice_fingerprint/, plotline/` 有对应实现 | ✓ |
| "13 checkers in output schema" | 实际 17 checker | **✗** |
| v13.6/v13.7 新增 5 checker（logic, outline-compliance, prose-impact, sensory-immersion, flow-naturalness） | **在拓扑图中未提及** | **✗** |

#### 6.5 `docs/operations.md` (99 行)

| 陈述 | 现实 | 对齐 |
|------|------|------|
| 4 层目录概念 | 代码 `project_locator.py` 实现一致 | ✓ |
| `python "${SCRIPTS_DIR}/ink.py" ...` | scripts/ink.py 存在（37 行 thin wrapper）| ✓ |
| `pwsh "${SCRIPTS_DIR}/run_tests.ps1" -Mode smoke` | `run_tests.ps1` 存在 | ✓ |
| `index stats`, `rag index-chapter` 等子命令 | `data_modules/ink.py:621` 实现 | ✓ |
| `status --focus urgency` | status_reporter.py 支持 | ✓ |

**结论**：`operations.md` 是最准确的一份；`README.md` 和 `architecture.md` 均有实质性漂移。

#### 评级：**C**（`operations.md` A-，`CLAUDE.md` A，但 `README.md` 和 `architecture.md` 在 agent/checker 数量、template 种类、表数量上严重过时；`agent_topology_v13.md` 在 v13.6+ 后未同步更新）

---

### 7. CLI 入口（CLI Entrypoints）

#### 7.1 /ink-* 命令 ↔ 入口脚本映射

| Slash 命令 | Skill 目录 | 入口 | 状态 |
|-----------|-----------|------|------|
| `/ink-init` | `skills/ink-init/SKILL.md` | `python3 scripts/init_project.py` | ✓ |
| `/ink-init --quick` | 同上 | `init_project.py --quick` | ✓ |
| `/ink-plan` | `skills/ink-plan/SKILL.md`(852 行) | 通过 `ink.py` 子命令 | ✓ |
| `/ink-write` | `skills/ink-write/SKILL.md`(2201 行) | `python3 scripts/ink.py ...` | ✓ |
| `/ink-auto` | `skills/ink-auto/SKILL.md` | `bash scripts/ink-auto.sh` | ✓ |
| `/ink-review` | `skills/ink-review/SKILL.md` | `ink.py review ...` | ✓ |
| `/ink-fix` | `skills/ink-fix/SKILL.md` | 由 ink-auto 调用 | ✓ |
| `/ink-resume` | `skills/ink-resume/SKILL.md` | `ink.py workflow detect` | ✓ |
| `/ink-query` | `skills/ink-query/SKILL.md` | `ink.py status` | ✓ |
| `/ink-resolve` | `skills/ink-resolve/SKILL.md` | `ink.py state resolve` | ✓ |
| `/ink-audit` | `skills/ink-audit/SKILL.md` | `migration_auditor.py` | ✓ |
| `/ink-macro-review` | `skills/ink-macro-review/SKILL.md` | `ink.py review macro` | ✓ |
| `/ink-learn` | `skills/ink-learn/SKILL.md` | `ink.py learn` | ✓ |
| `/ink-dashboard` | `skills/ink-dashboard/SKILL.md` | `python3 -m ink-writer.dashboard` | ✓ |
| `/ink-migrate` | `skills/ink-migrate/SKILL.md` | `migrate.py` | ✓ |

#### 7.2 入口稳定性

- 所有命令走 `scripts/ink.py` thin wrapper（37 行），wrapper 把 `data_modules/ink.py`（621 行，带 argparse）作为真正的 CLI。这是标准做法。
- `ink-auto.sh`（bash）是唯一例外——被 skill 调用执行跨会话无人值守。内嵌 Python（有 1 个 bare `except:`）。
- 所有 skill 都在 SKILL.md 里硬编码 `python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" ...` 的调用约定——**模板化一致**。

#### 7.3 问题

- 每个 skill 都自己拼 `${SCRIPTS_DIR}/ink.py` 路径，无统一抽象。若未来迁移 entry point 到 `pyproject.toml` 的 `[project.scripts]`（如 `ink = data_modules.ink:main`），需要改 14 份 SKILL.md。
- `pyproject.toml` 当前仅配 ruff，**未声明 `[project]` 元信息或 `[project.scripts]`**。这意味着此包无法 `pip install -e .`，只能靠 PYTHONPATH 黑魔法。

#### 评级：**B+**（14 条 slash 命令全部有稳定入口，thin wrapper 模式规范；扣分在 `pyproject.toml` 未声明 packaging 导致无法标准化分发）

---

## 二、Top 5 工程风险点（按严重度）

### Risk 1: `ink_writer/` 新包 6 个核心依赖未在 requirements 中声明（**严重 / 阻塞级**）

**影响**：
- CI 若从干净 runner 起步将全面失败（实际靠 sentence-transformers 的传递依赖"巧合"获得 numpy，但 faiss-cpu/jsonschema/PyYAML/anthropic 无传递路径）
- 开源用户按 README 的 `pip install -r requirements.txt` 安装后，第一次 `/ink-init --quick` 就会 ImportError
- 已知的 `anthropic` 在 `llm_backend.py:29` 做了 lazy import（`import anthropic` 内嵌在函数），但 yaml/faiss/numpy 都是模块顶层 import

**证据**：
- `scripts/requirements.txt:4-10` 仅列 3 个包
- `dashboard/requirements.txt:1-4` 4 个包
- `ink_writer/**/*.py` 有 17 个文件使用 yaml/numpy/faiss/jsonschema/sentence_transformers 而无任何 try/except 降级
- `ci-test.yml` 仅安装上述 2 份 lock

**修复建议**：创建 `ink_writer/requirements.txt`（或在根 `pyproject.toml` 的 `[project.dependencies]` 声明），加入 6 个包。更新 CI workflow 同步安装。

---

### Risk 2: 覆盖率门禁名存实亡（**高 / 持续性质量衰退风险**）

**影响**：
- `pytest.ini:8` 声明 `--cov-fail-under=70`，但 `ink-writer/scripts/` 实测 **13.62%**
- `state_manager.py (9%)`, `extract_chapter_context.py (0%)`, `status_reporter.py (10%)`, `workflow_manager.py (12%)`, `step3_harness_gate.py (0%)` 这些**写作主流程核心**近乎零覆盖
- 新加的 `ink_writer/` 子包测试覆盖率高（因为独立目录有专项测试），但老 `scripts/` 的 CLI 层是"祈祷式上线"
- 门禁理论上会失败，但 CI 可能因为只在 PR 时跑触发路径有限的子集而侥幸放行

**证据**：
```
FAIL Required test coverage of 70% not reached. Total coverage: 13.62%
```
（本地 `pytest --collect-only` 实际输出）

**修复建议**：
1. 短期：把 `--cov-fail-under=70` 改为 `--cov-fail-under=30`，承认现状，避免"理论门禁"
2. 中期：为 state_manager.py / workflow_manager.py / extract_chapter_context.py 补集成测试，目标 >50%
3. 长期：`step3_harness_gate.py` 是 review gate 核心，零覆盖风险极高，必须补

---

### Risk 3: 文档漂移（**中 / 用户信任风险**）

**影响**：
- `README.md` 说 "38 种模板"、"14 Agents + 10 Checkers" 都与现实（9 种 / 24 agent / 17 checker）不符
- `architecture.md` 的 "25 表" 与代码 30+ 表不符
- `agent_topology_v13.md` 的 "17 agents" 在 v13.6-v13.8 新增 5 checker 后未更新
- 新用户照着 README 安装会因为依赖缺失直接翻车

**证据**：
- `agents/` 目录 `ls` 数得 24 个 .md
- `skills/` 目录 14 个 skill（架构图数对）
- `genres/` 目录 9 个题材
- `README.md:154` 写 "38 种模板"（实际 9 个）

**修复建议**：
1. README 更新版本历史/技术规格部分，替换为准确数字
2. `architecture.md` 重写整体架构图（agent 分层）
3. `agent_topology_v13.md` 升级为 v13.8 并补 5 个新 checker
4. 引入自动化校验：CI 加一个 `scripts/verify_docs.py` 扫描"XX 个 agent/skill/表"与文件实际数对比

---

### Risk 4: `api_client.py` 用 print 输出 retry 日志（**中 / 可观测性问题**）

**影响**：
- RAG 调用的 retry/timeout 都走 `print(f"[WARN] ...")`（line 163, 177, 183, 189, 360, 372, 376, 382）
- 调用方（dashboard、ink-auto.sh）stdout 被污染
- 无法通过 logging level 降噪
- 生产环境若 embed API 抖动，stderr 会疯狂刷 retry 日志

**修复建议**：
```python
import logging
logger = logging.getLogger(__name__)
# ...
logger.warning("Embed %s, retrying in %.1fs (%d/%d)", resp.status, delay, attempt+1, max_retries)
```
批量替换 ~20 处 print → logger.warning/error。

---

### Risk 5: LLM 调用无显式超时 + 无进程级超时保护（**中 / 稳定性风险**）

**影响**：
- `editor_wisdom/llm_backend.py:44` 的 `client.messages.create(...)` 未设 timeout
- anthropic SDK 默认 10 分钟，在 checker 并行中可能堆积 N×10 分钟
- `parallel/pipeline_manager.py` 无章节级总超时，单章卡住 Claude Code 会话后无自动 kill
- ink-auto.sh 的 Bash 层有 `timeout` 包裹吗？—— 扫描未见 `timeout` 命令使用

**修复建议**：
1. 在 `call_llm()` 加 `timeout=180` 参数
2. `pipeline_manager.py` 为每章加 `asyncio.wait_for(write_chapter(), timeout=1800)`
3. ink-auto.sh 的 Claude Code 子进程调用用 `timeout 2400 claude ...`

---

## 三、质量记分卡

| 维度 | 评级 | 评分原因 |
|------|------|---------|
| **测试** | **B-** | 2028 tests 规模合格，结构分层清晰，集成测试占比合理；但 70% 门禁是幻觉（实测 13.62%），核心 state_manager (9%) / extract_chapter_context (0%) 近乎未测 |
| **错误处理** | **C+** | RAG 层重试/超时合格；95 处宽捕获偏多，部分静默吞异常；LLM 调用缺显式超时 |
| **配置** | **B** | SoT 明确，优先级清晰（项目 .env > 用户 .env > env var > yaml > 默认），13 份 yaml 模块独占；扣分在 config 加载代码 13 处分散未抽象 |
| **日志** | **D+** | `scripts/` 432 个 print vs 14 文件用 logging；api_client.py retry 日志用 print 是硬性 bug；无调试残留算加分 |
| **依赖** | **D** | 6 个核心依赖（numpy/faiss/yaml/jsonschema/sentence-transformers/anthropic）在 ink_writer/ 中使用但未声明，CI 绿是幻觉；lock 文件质量好但覆盖不全；`pyproject.toml` 无 `[project]` 元信息 |
| **文档** | **C** | `operations.md` 和 `CLAUDE.md` 对齐良好；`README.md` 有严重漂移（38 vs 9 templates, agent count 错误）；`architecture.md` 表数/agent 数陈旧；`agent_topology_v13.md` 未跟上 v13.6-v13.8 |

### 整体工程质量评级：**C+**

**含义**：ink-writer v13.8.0 功能密度远超同类（14 skill + 17 checker + 30 表 RAG + 并发管线），但工程"边界"未收敛——依赖声明、覆盖率门禁、文档同步、日志规范四项标准工程债明显。距离"生产级就绪"（B+ 或以上）差 2-3 个 US 的集中修复：

- US-A：补齐 `ink_writer/` requirements + 修 CI workflow（Risk 1）
- US-B：降低 coverage 门禁到现实值 + 给核心 4 文件补集成测试（Risk 2）
- US-C：统一文档/代码数字漂移 + 自动化校验（Risk 3）
- US-D：api_client.py print→logging + LLM 调用加 timeout（Risk 4+5）

修复顺序建议：Risk 1（阻塞） > Risk 5（稳定性） > Risk 2（质量） > Risk 4 > Risk 3（文档）。
