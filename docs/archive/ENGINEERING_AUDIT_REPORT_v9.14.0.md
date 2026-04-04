# ink-writer 项目级工程审查报告

> **审查日期**: 2026-04-04
> **审查版本**: v9.13.0 (commit da41da1)
> **审查范围**: 架构、模块边界、配置、依赖、测试、发布链路
> **平台限定**: macOS (Darwin 25.4.0)

---

## 一、项目目标与成功标准

### 项目定位

**Ink Writer Pro** 是一套基于 Claude Code 插件体系的工业级长篇网文创作系统，通过 14 个 AI Agent 协同 + 数据管线自动化，覆盖从项目初始化、大纲规划、逐章写作、多维审查到数据管理的全流程。

### 核心成功标准

| 标准 | 当前状态 |
|------|----------|
| 单章 ≥2200 字，质量一致 | ✅ 由 computational-gate 硬门控 |
| 跨 100+ 章人物/伏笔一致性 | ✅ 25 表 SQLite + entity_linker |
| 通过 AI 检测（6 层过滤 + 200 词禁表）| ✅ anti_ai_scanner + anti-detection-checker |
| 中断自动恢复 | ✅ workflow_manager + /ink-resume |
| 支持 38 种网文类型 | ✅ genres/ 模板目录 |
| 单命令批量写作 `/ink-auto N` | ✅ ink-auto.sh 编排 |

**结论**: 项目目标清晰，当前实现已基本覆盖所有成功标准。

---

## 二、架构评估

### 2.1 整体分层

```
┌─────────────────────────────────────────────┐
│  Skills 层 (13 个 SKILL.md，用户交互入口)      │
├─────────────────────────────────────────────┤
│  Agents 层 (14 个 Agent 提示词规范)            │
├─────────────────────────────────────────────┤
│  Scripts 层 (Python 后端 CLI + 数据管线)       │
│  ├── ink.py (入口)                            │
│  ├── data_modules/ (38 模块 + 5 mixin)        │
│  ├── workflow_manager / status_reporter       │
│  └── extract_chapter_context / init_project   │
├─────────────────────────────────────────────┤
│  Dashboard 层 (FastAPI + React 只读面板)       │
├─────────────────────────────────────────────┤
│  存储层 (state.json + index.db SQLite)         │
└─────────────────────────────────────────────┘
```

### 2.2 架构判断

**架构能否支撑目标？→ 能。**

- **Harness-First 架构 (v9.0+)**: 确定性检查前置于 LLM 调用，避免浪费 token
- **Lazy Import 模式**: `data_modules/__init__.py` 使用 `__getattr__` 延迟加载，无循环依赖
- **Mixin 组合**: IndexManager 通过 5 个 mixin 拆分职责（chapter/entity/debt/reading/observability）
- **JSON + SQLite 混合存储**: state.json 轻量元数据 + index.db 重查询，filelock 并发控制
- **Schema 版本管理**: `SCHEMA_VERSION = 5.4`，装饰器注册迁移函数，迁移前自动备份

**无循环依赖**，导入关系为清晰的 DAG：
```
config ← api_client ← rag_adapter
                     ← context_manager
index_types ← index_manager ← sql_state_manager
                             ← context_manager
state_manager ← entity_linker ← context_manager
```

---

## 三、发现的结构性问题

### 问题 1：`sys.path` 注入代替正式包管理

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟡 中 |
| **证据** | `ink.py:15-17`、`extract_chapter_context.py` 顶部均有 `sys.path.insert(0, scripts_dir)`；测试 conftest.py 同理；dashboard 测试亦通过 `sys.path.insert` 定位模块 |
| **影响** | 无 `pyproject.toml` / `setup.py`，不可 `pip install -e .`。IDE 静态分析困难，import 路径在不同执行上下文下不一致（需 try/except 双路径导入，如 `status_reporter.py:94-100`） |
| **建议** | 在当前 Claude Code 插件分发模式下属于可接受的架构限制。**暂不改动**，除非计划支持 PyPI 分发。若需改善 IDE 体验，可添加一个最小 `pyproject.toml`（仅声明 `[project]` + `[tool.setuptools]`），不影响插件分发 |

---

### 问题 2：大函数未拆分

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟡 中 |
| **证据** | |
| | `index_manager.py:_init_db()` — **649 行**，在单个方法中创建 ~30 张表 |
| | `index_manager.py:main()` — **767 行**，CLI 参数解析 + 命令分发混在一起 |
| | `state_manager.py:save_state()` — **197 行**，锁获取 + 磁盘读取 + 多字段合并 + SQLite 同步 + 原子写入 |
| | `state_manager.py:_sync_pending_patches_to_sqlite()` — **152 行** |
| | `extract_chapter_context.py` — **1702 行**，过程式，缺少类结构 |
| **影响** | 可测试性降低，单一职责违反，新增子命令需在 767 行函数中找插入点 |
| **建议** | 优先拆分 `_init_db()` → 表定义工厂；`main()` → 使用 argparse subparsers 或独立 handler 函数；`save_state()` → 提取 `_merge_pending_patches()` 和 `_atomic_write()` |

---

### 问题 3：宽泛异常捕获（`except Exception` 静默吞错）

| 项目 | 详情 |
|------|------|
| **严重级别** | 🔴 高 |
| **证据** | `status_reporter.py` 中至少 **5 处** 使用 `except Exception:` 后直接赋值 `None` 或空列表，无日志记录 |
| | 第 347 行：`except Exception: record = None` |
| | 第 398 行：`except Exception: known_character_names = []` |
| | 第 437 行：`except Exception: characters = []` |
| | `project_locator.py:57`：`except Exception: resolved = p.expanduser()` |
| **影响** | 数据库损坏、字段缺失、类型错误等真实 Bug 被静默吞掉，调试时无迹可寻。在长篇创作中，角色列表静默变空会导致连贯性检查失效 |
| **建议** | 替换为具体异常类型 + `logger.warning()`。建议新增 `data_modules/exceptions.py` 定义 `InkException` 层级 |

---

### 问题 4：CI 只测 Python 3.14，不覆盖声明的最低版本 3.10

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟡 中 |
| **证据** | `.github/workflows/ci-test.yml` 固定 `python-version: '3.14'`；README 声明支持 `Python 3.10+` |
| **影响** | 用户在 3.10/3.11/3.12 上运行可能遇到语法或标准库差异（如 `tomllib` 3.11+ 才内置、f-string 嵌套引号 3.12+ 才支持——此问题在 commit e2c3944 已修复过一次） |
| **建议** | 鉴于项目仅面向 macOS 本地使用（Claude Code 插件），且 macOS 用户通常使用较新 Python，此问题优先级可降低。但建议 README 将最低版本声明修正为 3.12+（与实际兼容性一致），或在 CI 中添加 3.12 矩阵 |

---

### 问题 5：无 pre-commit hooks，质量门仅在 CI 端

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟢 低 |
| **证据** | 项目根目录无 `.pre-commit-config.yaml`。无 ruff/black/mypy 本地检查 |
| **影响** | 开发者推送后才发现格式/lint 问题，CI 往返成本高 |
| **建议** | 对于单人开发项目，CI 端守门已足够。如果团队扩展，可添加 pre-commit（ruff + mypy）。**当前可不动** |

---

### 问题 6：无 mypy / 静态类型检查配置

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟢 低 |
| **证据** | 无 `mypy.ini`、`pyproject.toml [tool.mypy]` 或 `.mypy.ini`。类型注解覆盖率参差：`status_reporter.py` 返回类型 91.7%，`app.py` 返回类型仅 21.2%，参数注解普遍稀疏 |
| **影响** | 对于大量 Dict/Optional 操作的数据管线代码，缺少静态检查增加运行时类型错误风险 |
| **建议** | 可添加最小 mypy 配置（`check_untyped_defs = True`），逐模块启用。但考虑项目以 Agent 提示词为核心、Python 为数据管线辅助的定位，**优先级低** |

---

### 问题 7：Dashboard 全局可变状态

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟢 低 |
| **证据** | `dashboard/app.py:27-35` 中 `_project_root: Path | None = None` 为模块级可变全局变量，在 `create_app()` 中重赋值 |
| **影响** | 若创建多个 FastAPI 实例（测试场景），可能产生竞态。Dashboard 为只读单实例服务，实际风险极低 |
| **建议** | 可通过 FastAPI 依赖注入（`Depends`）传递 `project_root`。**当前可不动** |

---

### 问题 8：备份无轮转策略

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟢 低 |
| **证据** | `backup_manager.py` 将备份存入 `.ink/backups/`，无文件数量或大小上限 |
| **影响** | 长期运行的大型项目（200+ 章）可能积累大量备份文件 |
| **建议** | 添加简单轮转：保留最近 N 份（如 10 份），删除更旧的。约 2 小时工作量 |

---

### 问题 9：23 个模块缺少专用测试

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟢 低 |
| **证据** | 30 个模块有对应 `test_*.py`，23 个没有。缺失的主要是：`schemas.py`（数据类定义）、6 个 index mixin、`cli_args.py`、`cli_output.py`、`observability.py`、`snapshot_manager.py`、`query_router.py`、`genre_profile_builder.py` 等工具模块 |
| **影响** | 当前 84.58% 覆盖率已超阈值。缺失测试的多为类型定义、辅助工具或已被其他测试间接覆盖的模块 |
| **建议** | 按风险排序补充：`snapshot_manager.py`（缓存逻辑）> `query_router.py`（命令路由）> index mixin 单元测试。低优先级 |

---

### 问题 10：无正式 CHANGELOG

| 项目 | 详情 |
|------|------|
| **严重级别** | 🟢 低 |
| **证据** | 无 `CHANGELOG.md`。版本历史仅在 README 表格 + Git tag release notes 中记录 |
| **影响** | 用户和开发者难以快速了解跨版本变更。对于插件用户而言，README 表格基本够用 |
| **建议** | **当前可不动**。如果面向更多用户分发，再补充 CHANGELOG |

---

## 四、亮点（做得好的地方）

| 方面 | 评价 |
|------|------|
| **版本同步** | `sync_plugin_version.py` 跨 5 个文件保持版本一致，CI 自动校验 ✅ |
| **安全性** | `path_guard.py` 防目录穿越、`security_utils.py` 防注入、SQL 全部参数化查询 ✅ |
| **Schema 迁移** | 装饰器注册 + 自动备份 + 迁移审计器，生产级别 ✅ |
| **可观测性** | `observability.py` 输出 JSONL 结构化日志，支持性能分析 ✅ |
| **并发控制** | `filelock.FileLock` 保护 state.json 写入 ✅ |
| **依赖管理** | lock 文件提交 Git + CI 锁定安装，可复现构建 ✅ |
| **测试质量** | 980 个测试，84.58% 覆盖率，以集成测试为主（45/46 文件使用真实临时文件系统）✅ |
| **Mixin 组合** | IndexManager 5 个 mixin 清晰拆分职责 ✅ |
| **优雅降级** | SQLite 同步可选、filelock 可选、jieba 可选，核心功能不受影响 ✅ |

---

## 五、总结

### 1. 总体评价：✅ 合理

项目架构清晰，分层合理，无循环依赖。数据管线设计成熟（Schema 版本化、迁移审计、并发锁）。安全意识强。测试覆盖率健康。版本管理自动化。在 Claude Code 插件分发模式下，当前技术选型是合理的。

### 2. 最关键的 3 个问题

| 排名 | 问题 | 严重级别 | 核心风险 |
|------|------|----------|----------|
| **#1** | 宽泛异常捕获静默吞错（问题 3） | 🔴 高 | 数据异常被隐藏，长篇创作中角色/伏笔丢失无感知 |
| **#2** | 大函数未拆分（问题 2） | 🟡 中 | `_init_db` 649 行、`main` 767 行，可维护性差 |
| **#3** | CI 版本覆盖不足（问题 4） | 🟡 中 | 声明支持 3.10+ 但只测 3.14，曾因此出过兼容 Bug |

### 3. 最值得做的 3 个优化

| 排名 | 优化 | 预估工作量 | 收益 |
|------|------|------------|------|
| **#1** | 修复 `status_reporter.py` 的 5 处 `except Exception` → 具体异常 + 日志 | 2-3 小时 | 消除最大调试盲区 |
| **#2** | 拆分 `index_manager.py:main()` 767 行 → 独立 handler 函数 | 半天 | 降低新增子命令的维护成本 |
| **#3** | README 最低版本声明从 3.10 修正为 3.12（或 CI 添加 3.12 矩阵） | 30 分钟 | 消除版本承诺与实际兼容性的偏差 |

### 4. 先别乱动的地方

| 区域 | 原因 |
|------|------|
| **`sys.path` 注入机制** | 这是 Claude Code 插件分发模式的必然产物。改成正式包需要大面积重构入口点、测试 fixture、CI 流程，收益不匹配。除非计划上 PyPI |
| **`data_modules/__init__.py` 的 lazy import** | 当前工作良好，无循环依赖。改成 eager import 反而可能引入问题 |
| **index_manager 的 mixin 拆分方式** | 5 个 mixin 已经是合理的组合模式，进一步拆分为独立类会破坏现有 API |
| **Dashboard 全局变量** | 只读单实例服务，依赖注入改造的收益极低 |
| **测试中的 mock 密集模块**（如 `test_backup_manager.py` 138 处 mock）| 这些 mock 的是 Git/subprocess 等系统调用，是合理的隔离策略。替换为真实 Git 操作会大幅增加测试复杂度和运行时间 |

---

*报告生成方式: 4 个并行审查 Agent 分别检查项目结构/测试/依赖/代码质量，结果综合后人工校验输出*
