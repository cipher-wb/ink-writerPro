# Ink Writer Pro v9.6.0 — 项目级工程审查报告

**审查日期**: 2026-04-03
**审查版本**: v9.6.0 (commit 5e2685a)
**审查方法**: 测试运行 + 覆盖率分析 + 配置交叉验证 + 代码静态分析
**对比基线**: v9.4 审查报告 (ENGINEERING_AUDIT_v9.4.md)

---

## 一、项目目标与成功标准

### 项目目标

Ink Writer Pro 是基于多 AI Agent 协作的工业化长篇网文创作系统，支持 Claude Code / Gemini CLI / Codex CLI 三平台。核心承诺：

1. **全自动创作**：`/ink-auto N` 完成 N 章写作 + 审查 + 修复 + 规划
2. **质量可控**：14 个 Agent（4 核心 + 10 审查）+ 分层检查点保障长篇一致性
3. **记忆不丢失**：25 张 SQLite 表 + RAG 向量检索，支撑百万字量级不崩盘
4. **去 AI 味**：6 层反检测 + 200 词禁词表

### 成功标准当前达成情况

| 标准 | 目标 | 当前状态 | 变化 |
|------|------|----------|------|
| 单命令连续产出 | 100+ 章 | ✅ `ink-auto.sh` (809行) 分层检查点 | 不变 |
| 测试覆盖率 | ≥ 70%（pytest.ini 门槛） | ✅ 70.77%（594 passed, 0 failed） | ↑ 从 64.23% 提升到 70.77% |
| 三平台版本同步 | 一致 | ✅ 四处版本均为 9.6.0 | 不变 |
| CI 流水线 | 绿色 | ✅ 3 个 workflow 配置正确 | 不变 |
| 数据链路闭环 | 写→审→修→回写→上下文 | ✅ 架构支持 | 不变 |
| Dashboard 版本对齐 | 与主版本一致 | ✅ app.py + frontend package.json 均为 9.6.0 | ✅ 已修复（v9.4 时为 0.1.0） |

---

## 二、架构评估

### 2.1 当前架构概览

```
仓库根/
├── .claude-plugin/marketplace.json     ← Claude 插件市场元数据 (v9.6.0)
├── .codex/INSTALL.md                   ← Codex CLI 安装说明
├── .github/workflows/ (3个)            ← CI: test + version-check + release
├── docs/ (6文档 + archive/)            ← 用户文档
├── GEMINI.md + gemini-extension.json   ← Gemini CLI 扩展配置 (v9.6.0)
├── requirements.txt                    ← 依赖入口（聚合引用）
├── pytest.ini + .coveragerc            ← 测试配置
└── ink-writer/                         ← 插件主体
    ├── .claude-plugin/plugin.json      ← 插件元数据 (v9.6.0)
    ├── agents/ (14 个 .md)             ← Agent 定义（prompt 文件）
    ├── skills/ (14 个, 含 1 个弃用桩)  ← Skill 定义
    ├── references/                     ← 跨 skill 共享参考资料
    ├── templates/                      ← 文件模板
    ├── genres/ (9 个题材)              ← 题材配置
    ├── dashboard/ (FastAPI + React)     ← Web Dashboard (只读)
    │   └── frontend/ (Vite + React 19)
    └── scripts/                        ← Python 数据层 (55个 .py)
        ├── *.py (20 个顶层脚本)
        ├── ink-auto.sh (809行)          ← 批量写作 Shell 入口
        ├── requirements.lock           ← pip-compile 锁定依赖
        └── data_modules/ (34 个 .py)   ← 核心业务逻辑
            └── tests/ (34 个测试文件)
```

### 2.2 架构判断

**架构合理**，三层分离（skill/agent/script）清晰稳定：

- **Skill 层**（.md prompt）：定义工作流和触发条件，14 个 skill 覆盖完整创作链路
- **Agent 层**（.md prompt）：定义子 Agent 行为约束，14 个 agent 各司其职
- **Script 层**（Python）：承载数据逻辑和持久化，55 个 Python 文件 + 34 个测试文件
- **Dashboard 层**（FastAPI + React）：只读可视化面板，path_guard 防穿越

三平台适配通过各自独立入口实现，共享同一套 skill + script，设计合理。

---

## 三、v9.4→v9.5 已修复的历史问题

| 历史问题 | 状态 |
|----------|------|
| 覆盖率仅 64.23%，刚过 60% 门槛 | ✅ 已修复：提升至 70.77%，门槛升至 70% |
| Dashboard 版本号不同步（0.1.0 vs 9.6.0） | ✅ 已修复：app.py 和 frontend/package.json 均对齐 |
| 9 处活跃 Skill 引用已弃用的 ink-5 | ✅ 已修复：仅剩 ink-5 自身桩文件和 ink-auto 的背景说明 |
| 覆盖率门槛低于文档声明（60% vs 70%） | ✅ 已修复：pytest.ini 已设为 `--cov-fail-under=70` |
| backup_manager.py 零测试覆盖 | ✅ 已修复：覆盖率从 0% 提升至 98% |
| state_schema.py 零测试覆盖 | ✅ 已修复：覆盖率从 0% 提升至 98% |
| computational_checks.py 零测试覆盖 | ✅ 已修复：覆盖率从 0% 提升至 97% |
| style_anchor.py 零测试覆盖 | ✅ 已修复：覆盖率从 0% 提升至 100% |
| sync_plugin_version.py 覆盖率低 | ✅ 已修复：覆盖率提升至 93% |

**评价**：v9.5 在测试覆盖上取得了显著进展，10 个零覆盖模块中已修复 5 个，整体覆盖率从 64% 提升到 71%。

---

## 四、发现的问题

### 问题 1：security_utils.py 无测试文件，覆盖率仅 37%（严重：高）

| 维度 | 详情 |
|------|------|
| **证据** | `security_utils.py` (589行, 202 stmt, 覆盖率 37%)。无对应测试文件 `test_security*.py`。该模块包含 `sanitize_filename()`、`sanitize_commit_message()`、`create_secure_directory()`、`atomic_write_json()`、`read_json_safe()` 等 12 个安全关键函数 |
| **影响** | 这是专门为修复安全审计发现的路径遍历和命令注入漏洞而创建的模块（文件头注释明确说明），是系统安全防线的核心。63% 的代码路径未经测试，安全函数的边界条件（恶意输入、路径遍历尝试）可能存在未发现的漏洞 |
| **建议** | **最高优先级**补充测试：至少覆盖 `sanitize_filename` 的边界输入、`atomic_write_json` 的并发场景、`create_secure_directory` 的权限检查 |

### 问题 2：status_reporter.py 覆盖率仅 36%（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `status_reporter.py` (1244行, 589 stmt, 覆盖率 36%)。378 条语句未覆盖。该模块是 `ink-query` 和 `ink-dashboard` 的核心数据源，负责角色活跃度分析、伏笔深度分析、爽点节奏分布等 7 项分析功能 |
| **影响** | 作为系统"宏观俯瞰"的核心输出层，超过 60% 的分析逻辑未经测试。错误的分析结果会误导作者决策，且该模块直接面向用户输出 |
| **建议** | 为核心分析函数（角色活跃度、伏笔紧急度排序）补充测试 |

### 问题 3：update_state.py 覆盖率仅 39%（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `update_state.py` (633行, 274 stmt, 覆盖率 39%)。166 条语句未覆盖。该脚本是 data-agent 通过 `python3 update_state.py` 调用的状态更新入口 |
| **影响** | 状态更新是数据链路闭环的关键环节（写→审→修→**回写**→上下文）。低覆盖率意味着角色状态回写、伏笔标记等核心操作在边界条件下可能出错 |
| **建议** | 现有测试仅覆盖 `add-review` 子命令（从文件名 `test_update_state_add_review_cli.py` 可见），需扩展到其他状态更新路径 |

### 问题 4：CLI 入口 data_modules/ink.py 覆盖率仅 50%（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `data_modules/ink.py` (321 stmt, 50% 覆盖)，160 条语句未覆盖。此文件是所有 Skill 通过 `python3 ink.py --project-root ...` 调用的统一 CLI 入口 |
| **影响** | 全系统的命令调度枢纽，一半的分支路径未经测试。参数解析、子命令路由中的 bug 可能在生产中才暴露 |
| **建议** | 补充针对关键子命令（`index`、`state`、`status`、`migrate`）的 CLI 集成测试 |

### 问题 5：anti_ai_scanner.py 和 golden_three_checker.py 零测试覆盖（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `anti_ai_scanner.py` (534 stmt, 0% 覆盖) 和 `golden_three_checker.py` (284 stmt, 0% 覆盖) 两个顶层脚本完全无测试 |
| **影响** | `anti_ai_scanner.py` 是"去 AI 味"的核心组件，534 条语句完全盲区。`golden_three_checker.py` 负责黄金三章检查。两者合计 818 条语句拉低整体覆盖率 |
| **建议** | 注意 `data_modules/` 下已有对应的 `anti_ai_lint.py` (77%) 和 `golden_three.py` (80%)，顶层文件可能是早期独立脚本。需确认：若为弃用代码应删除，若仍活跃应补测试 |

### 问题 6：migration_auditor.py 零测试覆盖（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `migration_auditor.py` (216 stmt, 0% 覆盖)。该模块用于 `ink-migrate` 的迁移审计 |
| **影响** | 迁移场景不频繁，但一旦执行，审计失败可能导致数据迁移遗漏。风险可接受但存在 |
| **建议** | 低优先级。迁移完成后可考虑归档 |

### 问题 7：jieba 分词依赖未声明在 requirements.txt 中（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `rag_adapter.py:39` 使用 `import jieba`（带 try/except 降级），但 jieba 未出现在 `requirements.txt` 或 `requirements.lock` 中 |
| **影响** | jieba 是可选依赖，有 fallback（单字分词），但缺少声明意味着：(1) 用户不知道可以安装它来提升 RAG 质量；(2) CI 环境下始终走降级路径，未测试主路径 |
| **建议** | 在 requirements.txt 中添加为可选依赖并注释说明，或在 README 中提及 |

### 问题 8：SQLite ResourceWarning 连接泄漏仍存在（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | 测试运行产生 9 条 `ResourceWarning: unclosed database in <sqlite3.Connection>`，来源于 `ast.py:46` 上下文。当前版本仅报 2 warnings（pytest 汇总），但实际有 9 处 |
| **影响** | 主代码使用 context manager 正确关闭连接，泄漏主要在测试路径。在长时间运行的 `ink-auto` 批量写作中，如果生产代码也有类似路径，可能导致连接累积 |
| **建议** | 低优先级。在 conftest.py 中添加 `filterwarnings` 抑制，或修复具体的连接关闭路径 |

### 问题 9：workflow_manager.py 覆盖率 58%（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `workflow_manager.py` (996行, 459 stmt, 覆盖率 58%)。192 条语句未覆盖，主要集中在 541-996 行 |
| **影响** | 该模块管理写作工作流状态，后半部分（复杂工作流逻辑）缺少测试覆盖 |
| **建议** | 中优先级。补充后半段工作流逻辑的测试 |

### 问题 10：历史审查报告仍散落在仓库根目录（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | 根目录存在 `ENGINEERING_AUDIT_v9.4.md`，`docs/archive/` 中已有 v9.2、v9.3 等旧报告（含 9 份归档文件） |
| **影响** | 仓库根目录文件持续膨胀。每次审查新增一份报告文件 |
| **建议** | 审查完成后将旧版报告移入 `docs/archive/`，根目录只保留最新一份 |

---

## 五、总体评价

### 评级：合理

项目架构清晰稳定，v9.5 在工程质量上有显著提升：

- **测试覆盖率**从 64% → 71%，成功跨越 70% 门槛
- **5 个零覆盖模块**已补齐测试（backup_manager 98%、state_schema 98%、computational_checks 97%、style_anchor 100%、sync_plugin_version 93%）
- **版本同步**四处一致（含 Dashboard 对齐修复）
- **ink-5 残留**已清理到仅剩自身桩文件

主要风险点：安全模块 `security_utils.py` 无测试（37%），以及 3 个中等覆盖率的关键模块（status_reporter 36%、update_state 39%、ink.py 50%）。

---

## 六、最关键的 3 个问题

| 排名 | 问题 | 严重级别 | 核心理由 |
|------|------|----------|----------|
| 1 | `security_utils.py` 无测试文件，覆盖率 37% | **高** | 安全防线的核心模块，专为修复路径遍历/命令注入而创建，63% 代码路径未经验证 |
| 2 | `status_reporter.py` 覆盖率 36%（1244行） | 中 | 面向用户的分析输出层，64% 的分析逻辑未测试，错误输出会误导创作决策 |
| 3 | `update_state.py` 覆盖率 39%（633行） | 中 | 数据链路闭环的"回写"环节，现有测试仅覆盖单一子命令 |

## 七、最值得做的 3 个优化

| 排名 | 优化项 | 预期收益 | 工作量 |
|------|--------|----------|--------|
| 1 | 为 `security_utils.py` 创建完整测试文件 | 安全防线获得测试保护，覆盖率预估提升 2-3%，消除最高风险问题 | 中（2-3 小时） |
| 2 | 确认 `anti_ai_scanner.py` 和 `golden_three_checker.py` 的存废 | 若为弃用代码，删除后覆盖率立即提升约 5%；若活跃则补测试 | 小（30 分钟） |
| 3 | 扩展 `update_state.py` 测试到全部子命令 | 补齐数据链路闭环的测试保护，覆盖率提升 1-2% | 中（1-2 小时） |

## 八、先别乱动的地方

| 区域 | 理由 |
|------|------|
| `data_modules/index_manager.py` + 5 个 mixin | 2029 行核心模块，mixin 拆分合理，覆盖率已达 80-99%。重构风险远高于收益 |
| `ink-auto.sh` | 809 行 Shell 脚本是批量写作的核心入口，运行稳定。除非有明确 bug 不建议动 |
| `runtime_compat.py` + dual-import 模式 | 17 个文件的 try/except 导入虽不优雅，但是三平台兼容的基础，功能正确 |
| `agents/*.md` 的 prompt 定义 | 14 个 Agent prompt 是创作质量的核心资产，修改需极其谨慎 |
| `data_modules/rag_adapter.py` | 1612 行，覆盖率 85%，RAG 核心逻辑复杂但稳定 |
| `data_modules/state_manager.py` | 1720 行，覆盖率 90%，状态管理核心，已有充分测试保护 |
| `genres/` 题材配置 | 9 套题材模板各自独立，无结构性问题 |

---

## 九、覆盖率全景（v9.5 快照）

### 零覆盖模块（仍需关注）

| 模块 | 语句数 | 说明 |
|------|--------|------|
| `anti_ai_scanner.py` | 534 | 可能与 data_modules/anti_ai_lint.py 功能重叠 |
| `golden_three_checker.py` | 284 | 可能与 data_modules/golden_three.py 功能重叠 |
| `migration_auditor.py` | 216 | 迁移审计，使用频率低 |
| `scripts/ink.py` (顶层) | 12 | 入口桩文件 |

### 低覆盖率模块（< 50%）

| 模块 | 语句数 | 覆盖率 | 说明 |
|------|--------|--------|------|
| `runtime_compat.py` | 43 | 28% | 平台兼容层，pragma 掩盖 |
| `status_reporter.py` | 589 | 36% | 分析输出层，缺口最大 |
| `security_utils.py` | 202 | 37% | **安全模块，最高风险** |
| `update_state.py` | 274 | 39% | 状态回写入口 |
| `data_modules/ink.py` | 321 | 50% | CLI 调度枢纽 |

### 高覆盖率模块（> 90%，值得肯定）

| 模块 | 覆盖率 | 说明 |
|------|--------|------|
| `backup_manager.py` | 98% | v9.5 新增，↑98% |
| `state_schema.py` | 98% | v9.5 新增，↑98% |
| `computational_checks.py` | 97% | v9.5 新增，↑97% |
| `snapshot_manager.py` | 97% | — |
| `style_anchor.py` | 100% | v9.5 新增，↑100% |
| `entity_linker.py` | 98% | — |
| `index_chapter_mixin.py` | 99% | — |
| `index_debt_mixin.py` | 98% | — |
| `writing_guidance_builder.py` | 96% | — |
| `api_client.py` | 96% | — |
| `config.py` | 94% | — |
| `sql_state_manager.py` | 94% | — |
| `state_validator.py` | 94% | — |
| `sync_plugin_version.py` | 93% | v9.5 提升 |
| `cli_output.py` | 93% | — |

**总计：594 passed, 0 failed, 2 warnings | 整体覆盖率 70.77%**

---

*报告生成工具: Claude Code (Opus 4.6)*
*审查方法: 测试运行 + 覆盖率分析 + 配置交叉验证 + 代码静态分析*
*对比基线: ENGINEERING_AUDIT_v9.4.md*
