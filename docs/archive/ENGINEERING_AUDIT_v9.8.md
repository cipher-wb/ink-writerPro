# ink-writer v9.8.0 项目级工程审查报告

**审查日期**: 2026-04-03  
**审查范围**: 架构、模块边界、配置、依赖、测试、发布链路  
**代码版本**: `db59d64` (master)

---

## 一、项目目标与成功标准

**项目定位**: 多平台（Claude Code / Gemini CLI / Codex CLI）AI 辅助长篇网文创作系统。

**成功标准**（从架构和文档推断）:

| 标准 | 说明 |
|------|------|
| **可靠写作流水线** | 14 个 Agent + 14 个 Skill 协同完成单章 6 步流水线 (context → draft → polish → check → data → backup) |
| **数据一致性** | state.json + index.db (25 表) + vectors.db 三层存储保持同步 |
| **多平台可用** | 同一 Python 后端适配 Claude Code / Gemini / Codex 三种宿主 |
| **工程质量** | CI 自动化测试、版本同步、依赖锁定、覆盖率门槛 |
| **可持续迭代** | 从 v8 到 v9 有迁移工具，架构允许新增 Agent/Checker 不动核心 |

---

## 二、架构总览

```
用户 ─→ Skill (SKILL.md) ─→ env-setup.sh ─→ ink.py (CLI Router)
                                                  │
                    ┌─────────────────────────────┼──────────────────────┐
                    ▼                             ▼                      ▼
            StateManager              IndexManager (5 Mixins)     RAGAdapter
            (state.json)              (index.db, 25 tables)       (vectors.db)
                    │                             │
                    └──── SQLStateManager ────────┘
                    
Agent 层: writer / polish / context / data + 10 Checkers
Dashboard: FastAPI (app.py) + React SPA (App.jsx)
```

**架构评价**: 分层清晰，CLI → 数据模块 → 存储的三层分离合理。Mixin 模式控制了 IndexManager 的膨胀。延迟导入 (`__getattr__`) 消除了循环依赖。

---

## 三、发现的结构性问题

### P0 — 严重

#### 1. Git Tag 与版本号严重脱节

| 项目 | 值 |
|------|-----|
| **严重级别** | P0 |
| **证据** | `git describe` 输出 `v7.0.1-34-gdb59d64`；最新 tag 为 `v7.0.1`。而 plugin.json / package.json / marketplace.json 均声明 `9.8.0`。34 个 commit 横跨 v7.0.1 → v9.8.0 无任何 tag。 |
| **影响** | 发布流水线 `plugin-release.yml` 依赖手动 dispatch 创建 tag。但从 v7.0.1 之后从未使用过——所有 v8.x/v9.x 版本号都只存在于文件里，git history 中无法按版本定位回退点。`git describe` 给出的版本信息无法被任何工具消费。 |
| **建议** | 在当前 HEAD 补打 `v9.8.0` tag 并推送。后续每次 bump 版本时必须走 `plugin-release.yml` 或手动打 tag，保证 metadata 版本 = git tag。 |

---

### P1 — 高

#### 2. Dashboard 和前端零测试覆盖

| 项目 | 值 |
|------|-----|
| **严重级别** | P1 |
| **证据** | `ink-writer/dashboard/tests/` 目录不存在。`app.py` (531 行)、`watcher.py`、`path_guard.py` 无任何测试。前端 `App.jsx` (897 行) 无测试框架（package.json 中无 vitest/jest/@testing-library）。CI (`ci-test.yml`) 仅做 `import path_guard; import watcher` 冒烟验证。 |
| **影响** | Dashboard 的路径遍历防护 (`path_guard.py`) 和认证逻辑 (`INK_DASHBOARD_TOKEN`) 无测试保障。前端状态逻辑（897 行 JSX）重构时无安全网。 |
| **建议** | (1) 为 `path_guard.py` 补路径遍历攻击测试（安全敏感）。(2) 为 `app.py` 的 API endpoint 写 pytest + httpx 集成测试。(3) 前端暂不急——只读面板，风险可控。 |

#### 3. 核心流水线模块 `workflow_manager.py` 覆盖率仅 58%

| 项目 | 值 |
|------|-----|
| **严重级别** | P1 |
| **证据** | `workflow_manager.py` 459 行有效代码，192 行未覆盖 (58%)。未覆盖区域集中在 541-730 行（实际工作流编排逻辑）和 909-996 行（错误恢复路径）。 |
| **影响** | 这是 `ink-auto` 批量写作的核心编排器。写作中断恢复、步骤跳转等关键路径缺乏回归保护。项目整体 77% 覆盖率因此模块存在"高覆盖率、低关键路径覆盖"的假象。 |
| **建议** | 优先补充工作流编排的集成测试，尤其是中断恢复场景（541-730 行区域）。 |

#### 4. `status_reporter.py` 覆盖率仅 36%

| 项目 | 值 |
|------|-----|
| **严重级别** | P1 |
| **证据** | 1244 行代码，覆盖率 36%。包含角色活跃度分析、伏笔深度分析、爽点节奏分布等 7 个分析维度。 |
| **影响** | 宏观报告功能的可靠性无保障。作为面向用户的输出模块，错误直接影响用户信任。 |
| **建议** | 按功能维度逐步补测，优先覆盖伏笔紧急度排序（涉及数据聚合逻辑）。 |

---

### P2 — 中

#### 5. `migration_auditor.py` (461 行) 零覆盖

| 项目 | 值 |
|------|-----|
| **严重级别** | P2 |
| **证据** | 461 行代码，0% 覆盖率，无对应测试文件。 |
| **影响** | v8→v9 迁移审计工具。当前迁移期已过（v9 已稳定），影响收敛。但如果未来有 v10 迁移需求，此模块会被复用。 |
| **建议** | 优先级低于 workflow_manager，但应在下一个迭代中补充基本测试。 |

#### 6. CI 测试流水线不覆盖 Dashboard 变更

| 项目 | 值 |
|------|-----|
| **严重级别** | P2 |
| **证据** | `ci-test.yml` 的 `paths` 触发条件只包含 `ink-writer/scripts/**`，不包含 `ink-writer/dashboard/**`。Dashboard 代码变更不会触发 CI。 |
| **影响** | Dashboard 代码可以带着破坏性变更被合入 master，无 CI 拦截。 |
| **建议** | 在 `ci-test.yml` 的 paths 中增加 `ink-writer/dashboard/**`，并添加 Dashboard pytest 测试步骤。 |

#### 7. 发布流水线不运行测试

| 项目 | 值 |
|------|-----|
| **严重级别** | P2 |
| **证据** | `plugin-release.yml` 流程：版本校验 → 前端构建 → 打 tag → 创建 Release。全程无 `pytest` 步骤。 |
| **影响** | 理论上可以发布测试不通过的版本。虽然 push 触发的 `ci-test.yml` 会在之前运行，但 `workflow_dispatch` 手动触发时不受保护。 |
| **建议** | 在 `plugin-release.yml` 的 `Validate release metadata` 之后增加 `pytest` 步骤。 |

---

### P3 — 低

#### 8. `scripts/` 目录下的顶层模块未纳入 data_modules 包

| 项目 | 值 |
|------|-----|
| **严重级别** | P3 |
| **证据** | `workflow_manager.py` (996行)、`status_reporter.py` (1244行)、`update_state.py` (633行)、`migration_auditor.py` (461行) 等大型模块位于 `scripts/` 顶层而非 `scripts/data_modules/` 中。但它们被 `data_modules/ink.py` 通过相对路径导入。 |
| **影响** | 模块边界不一致——有些核心逻辑在 `data_modules/` 内（有 `__init__.py` 管理），有些在外面。增加新开发者理解成本。 |
| **建议** | 这是历史遗留，当前不影响功能。如果进行大规模重构时可考虑统一。**暂不要动**。 |

#### 9. 无代码格式化/Lint 工具

| 项目 | 值 |
|------|-----|
| **严重级别** | P3 |
| **证据** | 无 `pyproject.toml`（black/ruff 配置）、无 `.flake8`、无 `.eslintrc`、无 pre-commit hooks 配置。 |
| **影响** | 代码风格一致性依赖人工。对个人项目影响较小，但多人协作时会成为问题。 |
| **建议** | 可在后续考虑添加 `ruff` (替代 flake8+black，配置简单)。**当前优先级低**。 |

---

## 四、做得好的地方

| 方面 | 说明 |
|------|------|
| **依赖锁定** | `requirements.lock` (pip-compile) + `package-lock.json` 双锁，所有依赖版本可复现。依赖版本都较新，无已知漏洞。 |
| **版本同步机制** | `sync_plugin_version.py` 管理 5 文件版本一致性，CI 自动校验。解决了多平台发布时版本漂移的核心痛点。 |
| **延迟导入架构** | `data_modules/__init__.py` 的 `__getattr__` 模式消除了循环依赖，且不影响类型提示。 |
| **Mixin 分解** | IndexManager 的 5 个 Mixin（Chapter/Entity/Debt/Reading/Observability）让 25 表管理保持可维护。 |
| **降级模式** | RAGAdapter 在 embedding API 不可用时自动降级为 BM25，系统不中断。 |
| **覆盖率门槛** | 77% 覆盖率 + 70% 强制门槛 + CI 自动执行。747 个测试用例，14 秒完成。 |

---

## 五、总结

### 1. 总体评价：部分合理

架构和模块设计合理，数据链路和测试体系已具备工业级雏形。但发布链路（tag 缺失 + release 不跑测试）和 Dashboard 零测试是两个结构性短板，阻止了"合理"的完整评价。

### 2. 最关键的 3 个问题

| 排名 | 问题 | 原因 |
|------|------|------|
| **#1** | Git tag 与版本号脱节 | 34 个 commit 无 tag，发布流水线形同虚设，版本无法从 git 定位 |
| **#2** | `workflow_manager.py` 58% 覆盖率 | 写作流水线核心编排器，中断恢复路径无测试保护 |
| **#3** | Dashboard 零测试 + CI 不覆盖 | 安全模块 (path_guard) 无测试，代码变更无 CI 拦截 |

### 3. 最值得做的 3 个优化

| 排名 | 优化 | 收益 | 工作量 |
|------|------|------|--------|
| **#1** | 补打 v9.8.0 tag + 后续版本走 release 流水线 | 版本可追溯，回退有锚点 | 5 分钟 |
| **#2** | `plugin-release.yml` 增加 pytest 步骤 | 发布前自动守门 | 10 分钟 |
| **#3** | `workflow_manager.py` 补测试到 75%+ | 核心编排器有回归保护 | 2-3 小时 |

### 4. 先别乱动的地方

| 区域 | 原因 |
|------|------|
| **`scripts/` 顶层模块迁入 `data_modules/`** | 历史遗留但当前运行正常，挪动会涉及大量 import 路径变更和 CI 调整，风险高收益低 |
| **前端测试体系** | Dashboard 是只读面板，功能稳定，补前端测试的 ROI 远不如补后端测试 |
| **Lint / 格式化工具引入** | 个人项目，当前代码风格基本一致，强行引入会产生大量 format-only commit 污染 git history |
| **RAG 架构** | 降级模式已 work，不要在无明确性能问题时重构向量检索层 |
| **Mixin 架构** | 5 个 Mixin 分解合理，不要试图合并或进一步拆分 |

---

*报告生成于 2026-04-03，基于 commit `db59d64` (master) 的完整代码和 CI 配置审查。*
