# Ink Writer Pro v9.3.0 — 项目级工程审查报告

**审查日期**: 2026-04-03  
**审查版本**: v9.3.0 (commit 10771b4)  
**审查范围**: 架构、模块边界、配置、依赖、测试、发布链路、代码质量

---

## 一、项目目标与成功标准

### 项目目标

Ink Writer Pro 是一个基于 AI Agent 的工业化长篇网文创作系统，支持 Claude Code / Gemini CLI / Codex CLI 三平台。核心承诺：

1. **全自动创作**：一条 `/ink-auto N` 命令完成 N 章写作 + 审查 + 修复 + 规划
2. **质量可控**：14 个 Agent（4 核心 + 10 审查）+ 分层检查点保障长篇一致性
3. **记忆不丢失**：25 张 SQLite 表 + RAG 向量检索，支撑百万字量级不崩盘
4. **去 AI 味**：6 层反检测 + 200 词禁词表

### 成功标准

- 单命令可稳定连续产出 100+ 章（含自动检查点）
- 测试覆盖率 ≥ 70%（当前 CI 门槛）
- 三平台版本同步、CI 流水线绿色
- 数据链路闭环：写作 → 审查 → 修复 → 数据回写 → 下一章上下文

---

## 二、架构评估

### 2.1 当前架构

```
仓库根/
├── .claude-plugin/marketplace.json     ← Claude 插件市场元数据
├── .github/workflows/                  ← CI（3 个 workflow）
├── .codex/INSTALL.md                   ← Codex CLI 安装说明
├── docs/                               ← 用户文档
├── GEMINI.md + gemini-extension.json   ← Gemini CLI 扩展配置
├── requirements.txt                    ← 依赖入口（引用子目录）
├── pytest.ini + .coveragerc            ← 测试配置
└── ink-writer/                         ← 插件主体
    ├── .claude-plugin/plugin.json      ← 插件元数据 (v9.3.0)
    ├── agents/ (14 个 .md)             ← Agent 定义（prompt 文件）
    ├── skills/ (14 个 SKILL.md)        ← Skill 定义（workflow 文件）
    ├── references/                     ← 跨 skill 共享参考资料
    ├── templates/                      ← 文件模板
    ├── genres/                         ← 38 种题材配置
    ├── scripts/                        ← Python 数据层 + Shell 脚本
    │   ├── data_modules/ (26 个 .py)   ← 核心业务逻辑
    │   ├── data_modules/tests/ (27 个) ← 单元测试
    │   ├── ink-auto.sh (817 行)        ← 批量写作主脚本
    │   └── env-setup.sh                ← 环境初始化
    └── dashboard/                      ← FastAPI + Vue 可视化面板
        ├── app.py + server.py          ← 后端
        └── frontend/                   ← 前端（已构建 dist/）
```

### 2.2 架构判断：**合理**

当前架构清晰地分为三层：

- **编排层**（Skills/Agents .md 文件）：由 AI 平台解释执行，定义 workflow
- **数据层**（scripts/data_modules/*.py）：确定性逻辑，可测试
- **展示层**（dashboard/）：只读面板，独立部署

这种"Harness-First"设计思路正确：用确定性代码约束不确定的 AI 行为。模块间通过 CLI（ink.py 统一入口）解耦，避免了 Python 导入耦合。

---

## 三、发现的结构性问题

### 问题 1：测试覆盖率与 CI 门槛存在"幻觉"

**严重级别**: 🟠 HIGH

**证据**:

- `.coveragerc` 的 `[run] source` 只覆盖 `ink-writer/scripts/data_modules`
- 实际覆盖率 **84.48%**（通过 CI 的 70% 门槛）
- 但以下模块 **完全未被覆盖**（0% coverage）：
  - `style_anchor.py` (89 行) — 0%
  - `cli_args.py` (45 行) — 69%（接近门槛）
- 以下模块覆盖不足（<25%）：
  - `checkpoint_utils.py` — 78%（已有专项测试，但 CLI 入口部分未覆盖）
  - `anti_ai_lint.py` — 77%

- **更关键的是**：`scripts/` 目录下的 12 个独立脚本（`ink.py`, `init_project.py`, `workflow_manager.py`, `computational_checks.py`, `migrate.py`, `migration_auditor.py` 等）**完全不在覆盖率统计范围内**。这些脚本合计约 2000+ 行，全部是盲区。

**影响**: CI 的 70% 门槛看起来健康，但实际只覆盖了 `data_modules` 子包。`scripts/` 根目录的脚本层完全不在监控中。

**建议**: 扩大 `.coveragerc` 的 `source` 到 `ink-writer/scripts`（排除 tests），或在 CI 中分层报告覆盖率。

---

### 问题 2：`checkpoint` 子命令未注册到 ink.py CLI

**严重级别**: 🟡 MEDIUM

**证据**:

- `ink-writer/scripts/data_modules/checkpoint_utils.py` 定义了 3 个 CLI 入口函数：
  - `cli_checkpoint_level()` (L156)
  - `cli_report_check()` (L170)  
  - `cli_disambig_check()` (L181)
- `ink-writer/scripts/data_modules/ink.py`（统一 CLI 入口）中 **没有注册 `checkpoint` 子命令**
- `ink-auto.sh` 中没有调用这些 Python CLI 函数，而是在 Bash 中用内联 Python 重新实现了同等逻辑（L181-216, L600+）

**影响**: `checkpoint_utils.py` 的 CLI 入口是死代码。v9.3.0 把检查点逻辑提取为 Python 模块是正确的方向，但 Bash 侧尚未迁移过来，导致同一逻辑存在两份实现。

**建议**: 在 `ink.py` 中注册 `checkpoint` 子命令，然后将 `ink-auto.sh` 中的内联 Python 替换为 `python3 ink.py checkpoint ...` 调用。

---

### 问题 3：ink-auto.sh 中嵌入的 Python 片段使用 bare `except:`

**严重级别**: 🟡 MEDIUM

**证据**:

- `ink-auto.sh` 第 189、214、603 行的内联 Python 代码使用了 `except:` 而非 `except Exception:`
- 这些片段实现了章节号获取（L181-192）和卷号检测（L198-217）等关键流程控制逻辑

**影响**: `bare except` 会吞掉 `KeyboardInterrupt` 和 `SystemExit`，导致 Ctrl+C 中断信号可能被静默忽略。在批量写作的长时间运行场景中，这增加了无法正常中断的风险。

**建议**: 将 `except:` 改为 `except Exception:`。或者更好的做法是：迁移到 `checkpoint_utils.py` 的 CLI 调用（与问题 2 联动）。

---

### 问题 4：`style_anchor.py` 模块孤立，0% 覆盖率

**严重级别**: 🔵 LOW

**证据**:

- `ink-writer/scripts/data_modules/style_anchor.py` (89 行) 覆盖率 0%
- 没有被任何 Python 模块导入（`grep` 确认）
- 唯一引用在 `ink-writer/skills/ink-macro-review/SKILL.md` (L139)：`from style_anchor import save_anchor, check_drift`
- 该引用是 Skill 文档中的示例代码，由 AI Agent 在运行时动态执行

**影响**: 模块功能正常（AI Agent 运行时会 `import` 它），但无法通过自动化测试验证其正确性。一旦 API 不匹配或逻辑错误，只能在生产写作过程中发现。

**建议**: 为 `style_anchor.py` 补充基础测试（至少覆盖 `save_anchor` 和 `check_drift` 的正常路径）。

---

### 问题 5：`scripts/__init__.py` 遗留版本号 5.5.4

**严重级别**: 🟡 MEDIUM

**证据**:

- `ink-writer/scripts/__init__.py` (L7)：`__version__ = "5.5.4"`
- 插件版本已升至 9.3.0（`plugin.json`, `marketplace.json`, `gemini-extension.json` 均为 9.3.0）
- `sync_plugin_version.py --check` 的检查范围**不包含**此文件，因此 CI 未检测到不一致
- 该 `__version__` 虽然当前未被任何代码读取，但 `__init__.py` 的 `__version__` 是 Python 的标准内省接口

**影响**: 如果有人通过 `import scripts; scripts.__version__` 获取版本号，会得到错误的 5.5.4。虽然目前无人这么做，但这是一个等待被触发的 bug。

**建议**: 更新为 9.3.0，并将其纳入 `sync_plugin_version.py --check` 的检查范围。

---

### 问题 6：docs/architecture.md 数据过时

**严重级别**: 🔵 LOW

**证据**:

- `docs/architecture.md` (L33) 声称 "Skills (8个)" 和 "Agents (11个)"
- 实际有 **14 个 Skills**（含 ink-5 弃用桩）和 **14 个 Agents**
- 同文件 (L39) 描述 "Data Layer: state.json → index.db (渐进迁移中)"，但 v9.x 的迁移已通过 `ink-migrate` 完成

**影响**: 新用户或贡献者阅读架构文档时会产生错误认知。

**建议**: 更新 Skills/Agents 数量和数据层描述。

---

### 问题 7：Dashboard 无测试，且依赖未与主项目一起安装

**严重级别**: 🔵 LOW

**证据**:

- `ink-writer/dashboard/` 目录下 **没有任何测试文件**
- Dashboard 的依赖（`fastapi`, `uvicorn`, `watchdog`）在 `ink-writer/dashboard/requirements.txt` 中声明
- 根目录 `requirements.txt` 通过 `-r` 引用了它，但 CI 的 `ci-test.yml` (L34) 只安装 `ink-writer/scripts/requirements.lock`，不安装 dashboard 依赖
- Dashboard 中使用了全局变量 `_project_root`（`app.py` L32-33），多 worker 场景下可能有状态问题

**影响**: Dashboard 是只读面板，风险可控。但如果 FastAPI 升级导致 API 不兼容，不会有任何自动化检测。

**建议**: 保持现状即可。Dashboard 作为可选组件，短期内不需要测试。但若后续增加写入功能，需补充测试。

---

### 问题 8：测试中的 SQLite ResourceWarning

**严重级别**: 🔵 LOW

**证据**:

运行 `pytest` 时产生 7 个 `ResourceWarning: unclosed database in <sqlite3.Connection>` 警告。

- 业务代码中的 SQLite 连接均通过 `@contextmanager _get_conn()` 正确管理（`index_manager.py:925-934`, `rag_adapter.py:254-261`, `style_sampler.py:87-95`）
- 警告来自测试代码或 coverage 工具的交互问题

**影响**: 不影响功能，但在 CI 日志中产生噪音。

**建议**: 在 `pytest.ini` 中添加 `filterwarnings = ignore::ResourceWarning`，或在测试 fixture 中使用 `closing()` 包装。

---

## 四、总体评价

### 评级：✅ 合理

项目架构设计合理，"Harness-First"理念落地清晰。v9.0-v9.3 的迭代展现了扎实的工程化推进：

- 版本管理严谨（三平台 9.3.0 完全同步，CI 自动检查）
- 依赖管理规范（`pip-compile` 锁定版本，开发/锁定双轨制）
- 测试基础设施健全（27 个测试文件、338 个测试用例全通过、84.48% 覆盖率）
- 模块解耦得当（`index_types.py` 消除循环依赖、统一 CLI 入口、mixin 分离关注点）
- 安全意识到位（Dashboard CORS 收窄、`path_guard` 防穿越、`security_utils.py`）

---

### 最关键的 3 个问题

| 排名 | 问题 | 严重度 | 核心风险 |
|------|------|--------|---------|
| 1 | 覆盖率统计范围窄于实际代码范围 | HIGH | CI 绿灯给出虚假安全感 |
| 2 | checkpoint 子命令未注册 + Bash/Python 逻辑双写 | MEDIUM | 维护成本翻倍，修改一处忘改另一处 |
| 3 | ink-auto.sh 内联 Python 使用 bare except | MEDIUM | 长时间运行时可能吞掉中断信号 |

---

### 最值得做的 3 个优化

| 排名 | 优化 | 预期收益 | 工作量 |
|------|------|---------|--------|
| 1 | 扩大 `.coveragerc` source 范围到 `ink-writer/scripts` | 真实覆盖率可见，消除盲区 | 小（改 1 行配置 + 调整门槛） |
| 2 | 在 ink.py 注册 checkpoint 子命令，ink-auto.sh 调用统一入口 | 消除 Bash/Python 双写，checkpoint 逻辑可测试 | 中（需改 ink.py + ink-auto.sh） |
| 3 | 修复 `scripts/__init__.py` 版本号 + 纳入版本同步检查 | 消除版本遗留炸弹，防止未来误读 | 小（改 1 行 + sync_plugin_version.py 加检查点） |

---

### 先别乱动的地方

| 区域 | 原因 |
|------|------|
| `ink-auto.sh` 主循环逻辑 | 817 行的核心脚本，逻辑复杂但经过实战验证。除了 bare except 修复和 checkpoint 迁移外，不要做结构性重构 |
| `data_modules/` 的模块拆分 | 当前 mixin 拆分（index_chapter_mixin, index_entity_mixin, index_debt_mixin, index_reading_mixin, index_observability_mixin）已经合理，不需要进一步拆分 |
| Agents/Skills 的 .md 文件 | 这些是 prompt 文件，其"正确性"由写作质量决定，不是工程审查的范畴 |
| Dashboard 前端 | 已构建的 dist/ 工作正常，后端是只读 API，不需要大改 |

---

*报告完*
