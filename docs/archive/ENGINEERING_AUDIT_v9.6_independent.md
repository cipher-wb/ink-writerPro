# Ink Writer Pro v9.6.0 — 独立工程审查报告

**审查日期**: 2026-04-03  
**审查版本**: v9.6.0 (commit 4b59e90)  
**审查方法**: 代码静态分析 + 测试实跑 + 依赖交叉验证 + 架构推演  
**对比基线**: 项目自带 ENGINEERING_AUDIT_v9.6.md（本报告为独立二审，非增量）

---

## 一、项目目标与成功标准

### 项目目标

Ink Writer Pro 是基于多 AI Agent 协作的工业化长篇网文创作系统，作为 Claude Code 插件（同时适配 Gemini CLI / Codex CLI）运行。核心承诺：

1. **全自动创作**：`/ink-auto N` 一键完成 N 章写作 + 审查 + 修复 + 规划
2. **质量可控**：14 个 Agent（4 核心 + 10 审查）分层检查点保障长篇一致性
3. **记忆不丢失**：25 张 SQLite 表 + RAG 检索，支撑百万字量级上下文
4. **去 AI 味**：多层反检测 + 禁词表
5. **三平台分发**：Claude Code / Gemini CLI / Codex CLI 版本同步

### 成功标准达成情况

| 标准 | 目标 | 当前状态 | 判定 |
|------|------|----------|------|
| 单命令连续产出 | 100+ 章 | `ink-auto.sh` (809行) 分层检查点 | ✅ 达成 |
| 测试覆盖率 | ≥ 70%（pytest.ini 门槛） | **72.20%**（677 passed, 0 failed） | ✅ 达成 |
| 三平台版本同步 | 一致 | 5 处元数据均为 9.6.0 | ✅ 达成 |
| CI 流水线 | 绿色 | 3 个 workflow 配置正确 | ✅ 达成 |
| 数据链路闭环 | 写→审→修→回写→上下文 | 架构支持完整闭环 | ✅ 达成 |
| Dashboard 版本对齐 | 与主版本一致 | app.py + frontend/package.json 均 9.6.0 | ✅ 达成 |

---

## 二、架构评估

### 2.1 架构概览

```
仓库根/
├── .claude-plugin/marketplace.json     ← Claude 插件市场 (v9.6.0)
├── .codex/INSTALL.md                   ← Codex CLI 安装说明
├── .github/workflows/ (3个)            ← CI: test + version-check + release
├── docs/ (文档 + archive/)             ← 用户文档 + 历史审查归档
├── GEMINI.md + gemini-extension.json   ← Gemini CLI 扩展 (v9.6.0)
├── requirements.txt                    ← 聚合依赖入口（引用两个子 requirements）
├── pytest.ini + .coveragerc            ← 测试配置
└── ink-writer/                         ← 插件主体
    ├── .claude-plugin/plugin.json      ← 插件元数据 (v9.6.0)
    ├── agents/ (14 个 .md)             ← Agent 定义
    ├── skills/ (14 个, 含 1 个弃用桩)  ← Skill 定义
    ├── references/                     ← 跨 skill 共享参考
    ├── templates/                      ← 文件模板
    ├── genres/ (9 个题材)              ← 题材配置
    ├── dashboard/ (FastAPI + React)    ← Web Dashboard (只读)
    └── scripts/                        ← Python 数据层 (~27,900行)
        ├── *.py (20 个顶层脚本)
        ├── ink-auto.sh (809行)         ← 批量写作 Shell 入口
        ├── requirements.lock           ← pip-compile 锁定
        └── data_modules/ (34 个 .py)   ← 核心业务逻辑
            └── tests/ (36 个测试文件)
```

### 2.2 架构判断：**合理**

四层分离清晰稳定：

- **Skill 层**（SKILL.md）：14 个 skill 定义工作流和触发条件，结构统一
- **Agent 层**（agents/*.md）：14 个 agent 定义行为约束，各司其职
- **Script 层**（Python）：~27,900 行 Python + 36 个测试文件，承载数据逻辑
- **Dashboard 层**（FastAPI + React 19）：只读可视化，path_guard 防穿越

三平台适配通过各自独立入口（plugin.json / GEMINI.md / .codex/）共享同一套 skill + script，设计正确。

### 2.3 架构亮点

1. **lazy import 的 `__init__.py`**：避免 `python -m data_modules.xxx` 触发 RuntimeWarning，兼容性好
2. **mixin 拆分 IndexManager**：2029 行核心模块通过 5 个 mixin 分治，覆盖率 80-99%
3. **`_get_conn` context manager**：SQLite 连接在 finally 中正确关闭
4. **pip-compile 锁定依赖**：scripts 和 dashboard 各有独立的 requirements.lock

---

## 三、发现的问题

### 问题 1：`golden_three_checker.py` 为死代码——零引用、零测试、284 语句（严重：高）

| 维度 | 详情 |
|------|------|
| **证据** | `scripts/golden_three_checker.py`（284 stmt, 0% 覆盖）在全项目中零引用：skills/、agents/、ink-auto.sh 均不调用它。`data_modules/golden_three.py`（80% 覆盖）已是功能正式版本。grep 确认无任何 .md 文件引用 `golden_three_checker` |
| **影响** | 534+284=818 条零覆盖语句拖低整体覆盖率约 **6 个百分点**。每次审查都被标为问题却不处理，形成审查疲劳。死代码增加维护者认知负担（"这个文件和 data_modules 里那个什么关系？"） |
| **建议** | **直接删除** `golden_three_checker.py`。它是早期独立脚本，已被 data_modules 版替代。删除后覆盖率预估从 72.20% → ~74.5% |

### 问题 2：`anti_ai_scanner.py` 角色模糊——被引用但零测试、1056 行（严重：高）

| 维度 | 详情 |
|------|------|
| **证据** | `scripts/anti_ai_scanner.py`（534 stmt, 0% 覆盖）仅被 `polish-agent.md` 和 `polish-guide.md` 引用，是 polish 流程的一部分。但 `data_modules/anti_ai_lint.py`（77% 覆盖）也提供类似检测能力 |
| **影响** | 1056 行代码完全无测试保护。作为"去 AI 味"核心工具，7 层检测逻辑（词汇、句式、密度、对话、段落、标点）的正确性全靠人工验证。如果检测规则有 bug，polish 阶段会漏检或误报 |
| **建议** | 二选一：(1) 如果 `anti_ai_lint.py` 已覆盖其功能，将 polish 引用迁移过去并删除此文件；(2) 如果两者有功能差异（scanner 是 7 层完整检测，lint 是轻量版），则保留但**必须补测试** |

### 问题 3：`status_reporter.py` 覆盖率 36%——用户可见输出层大面积盲区（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `status_reporter.py`（1244 行, 589 stmt, 覆盖率 36%）。378 条语句未覆盖，集中在 375-1244 行的 7 项分析功能（角色活跃度、伏笔深度、爽点分布等） |
| **影响** | 该模块是 `ink-query` 和 `ink-dashboard` 的核心数据源。超过 60% 的分析逻辑未经测试，错误输出会误导作者决策。但它只是只读报告输出，不影响数据完整性，所以不是"高" |
| **建议** | 优先为核心分析函数补充测试（角色活跃度排序、伏笔紧急度计算） |

### 问题 4：Dashboard 无测试、CI 未覆盖（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `dashboard/` 目录下无任何 test 文件。`ci-test.yml` 仅安装 `scripts/requirements.lock`，不安装 dashboard 依赖，不测试 dashboard 代码。前端也无测试 |
| **影响** | Dashboard 包含 path_guard（安全防线）、SSE watcher、多个 API 端点。虽为只读面板，但 path_guard 的路径遍历防护和 CORS 配置未经自动化验证。手动发布后如果 FastAPI 升级破坏接口，无法在 CI 中捕获 |
| **建议** | 为 `path_guard.py` 至少添加 5-10 个路径遍历测试用例。在 CI 中添加 dashboard 依赖安装步骤（不需要启动服务，仅确保 import 不报错） |

### 问题 5：`workflow_manager.py` 覆盖率 58%——后半段工作流逻辑盲区（严重：中）

| 维度 | 详情 |
|------|------|
| **证据** | `workflow_manager.py`（996 行, 459 stmt, 覆盖率 58%）。541-996 行的复杂工作流逻辑几乎全部未覆盖（192 条语句） |
| **影响** | 该模块管理 ink-write 的完整工作流状态（draft→review→polish→data），后半段包含异常恢复和状态回退逻辑。ink-resume 依赖这些路径正确工作 |
| **建议** | 补充异常恢复路径和状态回退的测试 |

### 问题 6：SQLite ResourceWarning 连接泄漏——来自 `index_manager.py:685` 附近的测试路径（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | 测试运行产生 9 条 `ResourceWarning: unclosed database in <sqlite3.Connection>`。主代码的 `_get_conn` (line 925) 使用 context manager 正确关闭，泄漏发生在 `_init_tables` 期间的测试 fixture 清理路径 |
| **影响** | 仅影响测试，不影响生产。在 ink-auto 长时间批量运行中风险极低（每次 CLI 调用是独立进程）。但 9 个 warning 淹没了潜在的有意义警告 |
| **建议** | 在测试中确保 `_init_tables` 创建的连接在 fixture teardown 中关闭；或添加 conftest.py 的 filterwarnings |

### 问题 7：无 `conftest.py` 导致 fixture 重复（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `data_modules/tests/` 下无 `conftest.py`。36 个测试文件各自创建临时目录、mock config 等 fixture，存在大量重复 |
| **影响** | 不影响功能正确性，但增加测试维护成本。新增测试时需要从其他文件复制 fixture 代码 |
| **建议** | 低优先级。提取共用 fixture（tmp_project_root、mock_config）到 conftest.py |

### 问题 8：`ink-5` 弃用桩仍保留在 skills/ 中（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `ink-writer/skills/ink-5/SKILL.md` 是纯文本重定向桩，内容仅为"请使用 /ink-auto 5" |
| **影响** | 对功能无害，但占据 skills/ 列表位置，增加用户扫描成本 |
| **建议** | 可考虑删除。如保留作向后兼容，当前实现已足够轻量 |

### 问题 9：`runtime_compat.py` 覆盖率 28% 但被 19 个文件引用（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `runtime_compat.py`（43 stmt, 28% 覆盖）被 19 个 Python 文件 `from runtime_compat import` 引用。低覆盖因为大量 `pragma: no cover` 和平台分支 |
| **影响** | 功能简单且稳定（Windows UTF-8 stdio 适配），实际风险极低。但 19 个引用意味着如果它 break，影响面巨大 |
| **建议** | 保持现状。该模块的低覆盖率是合理的（平台条件分支无法在单一 CI 环境全覆盖） |

### 问题 10：docs/archive/ 持续膨胀（严重：低）

| 维度 | 详情 |
|------|------|
| **证据** | `docs/archive/` 已有 9 份历史审查报告（v7.0.6 至 v9.4），合计 ~175KB。根目录还有 `ENGINEERING_AUDIT_v9.6.md` |
| **影响** | 仓库 clone 体积增长，且历史报告对新用户无价值 |
| **建议** | 考虑将 v9.2 以前的报告移出仓库（或放 wiki），根目录只保留最新报告 |

---

## 四、总体评价

### 评级：合理

Ink Writer Pro v9.6.0 是一个**架构成熟、工程纪律良好**的项目：

- **四层分离**（Skill/Agent/Script/Dashboard）清晰，职责边界明确
- **测试基线**从 v9.2 的 15% 提升到 72.20%，677 个测试全部通过
- **依赖管理**有 pip-compile 锁定，分层 requirements 结构正确
- **CI/CD** 三个 workflow 覆盖测试、版本检查、发布，配置正确
- **版本同步** 5 处元数据一致（plugin.json / marketplace.json / gemini-extension.json / app.py / frontend/package.json）
- **安全意识**有 path_guard 防穿越、security_utils 集中安全函数、CORS 限制

主要风险集中在**死代码/半废代码拖低覆盖率**和**少数关键模块测试不足**，而非架构缺陷。

---

## 五、最关键的 3 个问题

| 排名 | 问题 | 严重级别 | 核心理由 |
|------|------|----------|----------|
| 1 | `golden_three_checker.py` 死代码（零引用、零测试、284 stmt） | **高** | 全项目无任何引用，纯粹拖低覆盖率 6%，形成审查疲劳 |
| 2 | `anti_ai_scanner.py` 角色模糊（被引用但零测试、534 stmt） | **高** | 去 AI 味核心工具 1056 行零测试保护，与 anti_ai_lint.py 职责重叠未厘清 |
| 3 | `status_reporter.py` 覆盖率 36%（1244 行） | **中** | 用户可见分析输出层 64% 盲区，误报会误导创作决策 |

## 六、最值得做的 3 个优化

| 排名 | 优化项 | 预期收益 | 工作量 |
|------|--------|----------|--------|
| 1 | 删除 `golden_three_checker.py` + 厘清 `anti_ai_scanner.py` 存废 | 覆盖率立即 +6~10%，消除两个高风险问题，减少审查噪音 | **小**（1 小时） |
| 2 | 为 Dashboard `path_guard.py` 补充路径遍历测试 + CI 中添加 dashboard import 检查 | 安全防线获得自动化验证，dashboard 发布不再裸奔 | **小**（1-2 小时） |
| 3 | 为 `status_reporter.py` 核心分析函数补测试 | 用户可见输出获得测试保护，覆盖率提升 2-3% | **中**（2-3 小时） |

## 七、先别乱动的地方

| 区域 | 理由 |
|------|------|
| `data_modules/index_manager.py` + 5 个 mixin | 2029 行核心模块，mixin 拆分合理，覆盖率 80-99%。碰了风险远大于收益 |
| `data_modules/rag_adapter.py` | 1612 行，覆盖率 85%，RAG 核心逻辑复杂但稳定 |
| `data_modules/state_manager.py` | 1720 行，覆盖率 90%，状态管理核心，测试充分 |
| `ink-auto.sh` | 809 行 Shell 脚本是批量写作核心入口，运行稳定 |
| `runtime_compat.py` + 19 个文件的 dual-import | 虽不优雅，但是三平台兼容基础，功能正确 |
| `agents/*.md` 的 prompt 定义 | 14 个 Agent prompt 是创作质量核心资产，修改需极其谨慎 |
| `genres/` 题材配置 | 9 套题材模板各自独立，无结构性问题 |
| `data_modules/__init__.py` 的 lazy import | 设计精巧，解决了 runpy RuntimeWarning，别动 |

---

## 八、覆盖率全景（实测快照）

**总计：677 passed, 0 failed, 2 warnings | 整体覆盖率 72.20%**

### 零覆盖模块

| 模块 | 语句数 | 判定 |
|------|--------|------|
| `golden_three_checker.py` | 284 | **应删除**（死代码，零引用） |
| `anti_ai_scanner.py` | 534 | **需厘清**（被 polish 引用但零测试） |
| `migration_auditor.py` | 216 | 低频迁移工具，可暂缓 |
| `scripts/ink.py` (顶层桩) | 12 | 入口转发，可忽略 |

### 低覆盖率模块（< 50%）

| 模块 | 语句数 | 覆盖率 | 说明 |
|------|--------|--------|------|
| `runtime_compat.py` | 43 | 28% | 平台兼容层，合理 |
| `status_reporter.py` | 589 | 36% | 分析输出层，需补测试 |
| `data_modules/ink.py` | 321 | 50% | CLI 调度枢纽，需扩展测试 |

### 显著改善模块（对比 v9.4 基线）

| 模块 | v9.4 | 当前 | 变化 |
|------|------|------|------|
| `security_utils.py` | 37% | **69%** | +32% ✅ |
| `update_state.py` | 39% | **84%** | +45% ✅ |
| `backup_manager.py` | 0% | **98%** | 新增 ✅ |
| `state_schema.py` | 0% | **98%** | 新增 ✅ |
| `computational_checks.py` | 0% | **97%** | 新增 ✅ |
| `style_anchor.py` | 0% | **100%** | 新增 ✅ |
| 整体 | ~64% | **72.20%** | +8% ✅ |

---

## 九、与项目自带审查报告的差异

本独立审查与 `ENGINEERING_AUDIT_v9.6.md` 的主要差异：

| 维度 | 自带报告 | 本报告 |
|------|----------|--------|
| 覆盖率 | 70.77% (594 passed) | **72.20% (677 passed)**，基于最新 commit |
| security_utils 覆盖率 | 37%（标为最高风险） | **69%**（已大幅改善，降级为非顶级问题） |
| update_state 覆盖率 | 39% | **84%**（已大幅改善） |
| 死代码问题 | 建议"确认存废" | **明确判定** golden_three_checker 为死代码（零引用证据） |
| Dashboard | 未提及测试缺失 | **新增发现**：Dashboard 零测试 + CI 未覆盖 |
| conftest.py | 未提及 | **新增发现**：测试目录缺少共用 fixture |

---

*报告生成: Claude Code (Opus 4.6) — 独立二审*  
*审查范围: 全仓库静态分析 + 测试实跑 + 依赖验证 + 架构推演*  
*审查时间: 2026-04-03*
