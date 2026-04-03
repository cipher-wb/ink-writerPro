# Ink Writer Pro v9.5.0 — 项目级工程审查报告

**审查日期**: 2026-04-03
**审查版本**: v9.5.0 (commit e0584bb)
**审查范围**: 架构、模块边界、配置、依赖、测试、发布链路、代码质量
**审查方法**: 静态分析 + 测试运行 + 配置交叉验证

---

## 一、项目目标与成功标准

### 项目目标

Ink Writer Pro 是基于 AI Agent 的工业化长篇网文创作系统，支持 Claude Code / Gemini CLI / Codex CLI 三平台。核心承诺：

1. **全自动创作**：`/ink-auto N` 完成 N 章写作 + 审查 + 修复 + 规划
2. **质量可控**：14 个 Agent（4 核心 + 10 审查）+ 分层检查点保障长篇一致性
3. **记忆不丢失**：25 张 SQLite 表 + RAG 向量检索，支撑百万字量级不崩盘
4. **去 AI 味**：6 层反检测 + 200 词禁词表

### 成功标准

| 标准 | 目标 | 当前状态 |
|------|------|----------|
| 单命令连续产出 | 100+ 章 | ✅ `ink-auto.sh` 已实现分层检查点 |
| 测试覆盖率 | ≥ 60%（pytest.ini 门槛） | ✅ 64.23%（刚过线） |
| 三平台版本同步 | 一致 | ✅ 四处版本均为 9.5.0 |
| CI 流水线 | 绿色 | ✅ 3 个 workflow 配置正确 |
| 数据链路闭环 | 写→审→修→回写→上下文 | ✅ 架构支持 |

---

## 二、架构评估

### 2.1 当前架构概览

```
仓库根/
├── .claude-plugin/marketplace.json     ← Claude 插件市场元数据
├── .codex/INSTALL.md                   ← Codex CLI 安装说明
├── .github/workflows/ (3个)            ← CI: test + version-check + release
├── docs/                               ← 用户文档
├── GEMINI.md + gemini-extension.json   ← Gemini CLI 扩展配置
├── requirements.txt                    ← 依赖入口（聚合引用）
├── pytest.ini + .coveragerc            ← 测试配置
└── ink-writer/                         ← 插件主体
    ├── .claude-plugin/plugin.json      ← 插件元数据 (v9.5.0)
    ├── agents/ (14 个 .md)             ← Agent 定义（prompt 文件）
    ├── skills/ (14 个)                 ← Skill 定义（含 1 个弃用桩）
    ├── references/                     ← 跨 skill 共享参考资料
    ├── templates/                      ← 文件模板
    ├── genres/ (9 个题材)              ← 题材配置
    ├── dashboard/ (6 个 .py)           ← Web Dashboard (FastAPI)
    └── scripts/                        ← Python 数据层
        ├── *.py (20 个顶层脚本)
        ├── ink-auto.sh                 ← 批量写作 Shell 入口
        └── data_modules/ (26 个 .py)   ← 核心业务逻辑
            └── tests/ (28 个测试文件)
```

### 2.2 架构判断

**架构基本合理**，skill/agent/script 三层分离清晰：
- **Skill 层**（.md prompt）定义工作流和触发条件
- **Agent 层**（.md prompt）定义子 Agent 行为约束
- **Script 层**（Python）承载数据逻辑和持久化

三平台适配通过 `GEMINI.md` / `.codex/INSTALL.md` / `.claude-plugin/` 实现，各有独立入口，共享同一套 skill + script。

---

## 三、发现的问题

### 问题 1：多个活跃 Skill 仍引用已弃用的 `ink-5`（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `ink-resolve/SKILL.md:79`、`ink-audit/SKILL.md:172`、`ink-resume/SKILL.md:240,269,277,287`、`ink-macro-review/SKILL.md:235,238,240` 共 9 处仍引用 `ink-5` 而非 `ink-auto` |
| **影响** | AI Agent 读取这些 Skill 时会看到 `ink-5` 指令，可能尝试调用已弃用命令。`ink-resume` 的批量恢复流程甚至模板中硬编码了 `ink-5`，用户选择"选项 C"会被引导执行弃用命令 |
| **建议** | 全局替换这些活跃 Skill 中的 `ink-5` → `ink-auto`，保持语义对应 |

### 问题 2：10 个 Python 模块零测试覆盖（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | 以下模块覆盖率为 0%：`anti_ai_scanner.py` (534 stmt)、`backup_manager.py` (220)、`computational_checks.py` (168)、`golden_three_checker.py` (284)、`state_schema.py` (165)、`migration_auditor.py` (216)、`sync_plugin_version.py` (190)、`style_anchor.py` (89)、`migrate.py` (59)、`ink.py[scripts]` (12) |
| **影响** | 这 10 个模块合计 1,937 条语句完全无测试。其中 `anti_ai_scanner.py`（反 AI 检测核心）和 `backup_manager.py`（数据备份）属于高价值模块。总覆盖率 64.23% 刚过 60% 门槛，缺乏安全裕度 |
| **建议** | 优先为 `backup_manager.py` 和 `sync_plugin_version.py` 补充测试——前者涉及数据安全，后者在 CI release 流水线中被直接调用 |

### 问题 3：覆盖率门槛低于文档声明（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `pytest.ini:7` 设定 `--cov-fail-under=60`，但 v9.3 审查报告 `ENGINEERING_AUDIT_v9.3.md:24` 声称成功标准为"≥ 70%（当前 CI 门槛）" |
| **影响** | 文档与实际配置不一致。CI 实际以 60% 为门槛通过，低于团队预期的 70% 标准 |
| **建议** | 二选一：将 `pytest.ini` 提升到 `--cov-fail-under=70`，或更新文档标准为 60% |

### 问题 4：`data_modules/ink.py` 统一 CLI 入口覆盖率仅 50%（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `data_modules/ink.py` (321 stmt, 50% 覆盖)。此文件是所有 Skill 通过 `python3 ink.py --project-root ...` 调用的统一 CLI 入口，至少 20+ 处 Skill 引用 |
| **影响** | 这是全系统的命令调度枢纽，一半的分支路径未经测试。子命令路由、参数解析、错误处理中的 bug 可能在生产中才暴露 |
| **建议** | 补充针对关键子命令（`index`、`state`、`status`、`migrate`）的 CLI 集成测试 |

### 问题 5：18 个文件使用 dual-import try/except 模式（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | 19 个文件包含 `from runtime_compat import enable_windows_utf8_stdio`，18 个文件使用 `try: from X except ImportError: from scripts.X` 模式 |
| **影响** | 每个模块都在处理"从哪个路径导入"的问题，说明 Python 包结构的 `sys.path` 管理不够统一。虽然功能正确，但增加了维护负担，且 `pragma: no cover` 掩盖了实际未测试的代码路径 |
| **建议** | 当前可接受，但长期建议在 `__init__.py` 或 `conftest.py` 中统一 `sys.path` 注入，消除模块级 try/except |

### 问题 6：SQLite 连接 ResourceWarning（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | 测试运行产生多条 `ResourceWarning: unclosed database in <sqlite3.Connection>`，来源为 `ast.py:46` 上下文 |
| **影响** | 主代码 `_get_conn()` 使用 context manager 正确关闭连接，但测试中某些路径（可能是 `check_integrity` 或 `backup_db` 的异常分支）未完全关闭。在长期运行的 `ink-auto` 批量写作中，连接泄漏可能累积 |
| **建议** | 在测试中添加 `filterwarnings` 或修复具体的连接泄漏路径；检查 `check_integrity()` 和 `backup_db()` 的异常分支 |

### 问题 7：Dashboard 模块完全排除在测试覆盖之外（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `.coveragerc` 的 `source = ink-writer/scripts` 仅覆盖 scripts 目录；`dashboard/` 下 6 个 Python 文件（`server.py`、`app.py`、`watcher.py`、`path_guard.py` 等）无任何测试 |
| **影响** | Dashboard 作为只读面板，风险较低。但 `path_guard.py`（路径安全）如果存在 bug 可能导致路径遍历问题 |
| **建议** | 至少为 `path_guard.py` 添加单元测试，验证路径安全逻辑 |

### 问题 8：Dashboard 版本号与主版本不同步（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `dashboard/app.py:68` FastAPI 声明 `version="0.1.0"`，`dashboard/frontend/package.json:4` 也为 `"0.1.0"`，而插件主版本为 `9.5.0` |
| **影响** | 纯视觉问题——Dashboard API 文档页面显示版本号不一致。但可能给用户造成困惑 |
| **建议** | 将 Dashboard 版本对齐到插件版本，或改为从 `plugin.json` 动态读取 |

### 问题 9：历史审查报告散落在仓库根目录（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | 根目录存在 `ENGINEERING_AUDIT_v9.2.md`、`ENGINEERING_AUDIT_v9.3.md`、`PROJECT_AUDIT_REPORT.md` 三份审查报告，同时 `docs/archive/` 已存在归档机制 |
| **影响** | 仓库根目录文件膨胀，新贡献者难以区分活跃文档和历史文档 |
| **建议** | 将旧版审查报告移入 `docs/archive/`，根目录只保留最新一份 |

---

## 四、已修复的历史问题（v9.2→v9.4 进展）

对照 v9.2/v9.3 审查报告，以下问题已修复：

| 历史问题 | 状态 |
|----------|------|
| 三平台版本不同步 | ✅ 已修复：四处均为 9.5.0 + `sync_plugin_version.py` + CI 自动检查 |
| 测试覆盖率 15% | ✅ 已修复：从 15% → 84%（data_modules）→ 整体 64.23% |
| ink-5 保留完整实现 | ✅ 已修复：缩减为纯重定向桩 |
| 无 CI 测试流水线 | ✅ 已修复：ci-test.yml + 锁定依赖版本 |
| 无依赖锁定 | ✅ 已修复：requirements.lock (pip-compile) |

---

## 五、总体评价

### 评级：合理

项目架构清晰，三层分离（skill/agent/script）设计合理，三平台适配方案可行。CI 流水线覆盖了测试和版本同步。v9.2→v9.4 的迭代展示了有效的工程改进节奏。

主要风险点在于：测试覆盖率刚过门槛（64%，10 个模块零覆盖），以及弃用命令的残留引用。

---

## 六、最关键的 3 个问题

| 排名 | 问题 | 严重级别 | 核心理由 |
|------|------|----------|----------|
| 1 | 10 个 Python 模块零测试覆盖（含 backup_manager、anti_ai_scanner） | 中 | 数据安全和核心功能模块无测试保护，覆盖率缺乏裕度 |
| 2 | 9 处活跃 Skill 引用已弃用的 `ink-5` | 中 | AI Agent 可能被误导执行弃用命令，ink-resume 恢复流程尤其危险 |
| 3 | CLI 入口 `data_modules/ink.py` 覆盖率仅 50% | 中 | 全系统命令调度枢纽，一半分支未经测试 |

## 七、最值得做的 3 个优化

| 排名 | 优化项 | 预期收益 | 工作量 |
|------|--------|----------|--------|
| 1 | 全局替换活跃 Skill 中的 `ink-5` → `ink-auto` | 消除 AI 误导风险，5 分钟可完成 | 极小 |
| 2 | 为 `backup_manager.py` + `sync_plugin_version.py` 补充测试 | 保护数据安全 + 发布流水线可靠性，覆盖率可提升至 ~70% | 中（2-3 小时） |
| 3 | 统一覆盖率门槛：`pytest.ini` 设为 70% + 更新文档 | 消除文档/配置矛盾，建立真实质量基线 | 极小 |

## 八、先别乱动的地方

| 区域 | 理由 |
|------|------|
| `data_modules/index_manager.py` + 5 个 mixin | 2029 行的核心模块，当前 mixin 拆分已合理，有测试覆盖。重构风险高于收益 |
| `ink-auto.sh` | 832 行 Shell 脚本是批量写作的核心入口，逻辑复杂但运行稳定。除非有明确 bug，不建议重写 |
| `runtime_compat.py` + dual-import 模式 | 18 个文件的 try/except 导入虽不优雅，但功能正确且是三平台兼容的基础。统一重构影响面太大 |
| `agents/*.md` 的 prompt 定义 | 14 个 Agent prompt 是创作质量的核心资产，修改需极其谨慎 |
| `genres/` 题材配置 | 9 套题材模板各自独立，无结构性问题 |

---

*报告生成工具: Claude Code (Opus 4.6)*
*审查耗时: 单次自动化审查*
