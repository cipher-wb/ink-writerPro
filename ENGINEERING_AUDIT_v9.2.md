# Ink Writer Pro v9.2.0 — 项目级工程审查报告

> 审查日期：2026-04-03  
> 审查版本：v9.2.0 (commit 0ade786)  
> 审查人：Claude Code (Opus 4.6)  
> 审查范围：架构、模块边界、配置、依赖、测试、发布链路

---

## 一、项目目标与成功标准

### 项目目标

Ink Writer Pro 是一个面向 AI CLI 平台（Claude Code / Gemini CLI / Codex CLI）的工业级长篇网文创作系统。核心价值主张：

1. **自动化长篇创作**：14 个 AI Agent 协同，支撑百万字级网文的持续自动化生产
2. **Harness-First 架构**：确定性门控 + 结构化评估 + 状态持久化 + 反馈闭环
3. **三平台部署**：Claude Code（主推）、Gemini CLI、Codex CLI
4. **持久记忆**：25 表 SQLite + 可选 RAG 语义检索，解决 LLM 长程遗忘问题

### 隐含成功标准

- 跨会话写作不丢状态
- 每章 2200+ 字，质量通过 10 Agent 审查
- `/ink-auto N` 可无人值守批量写作，中断可恢复
- 配置变更不破坏已有项目

---

## 二、架构评估：当前架构是否支撑目标

### 架构总览

```
ink-writer/                    ← 插件根目录
├── .claude-plugin/            ← Claude Code 插件元数据
├── agents/          (14 个)   ← Agent 定义（.md prompt 文件）
├── skills/          (14 个)   ← Skill 定义（每个一个 SKILL.md）
├── scripts/                   ← Python 后端 + Shell 编排
│   ├── data_modules/          ← 核心数据链（IndexManager, StateManager, RAG...）
│   │   └── tests/             ← 单元测试（25 个）
│   ├── ink-auto.sh            ← 800 行 Bash 批量编排器
│   └── *.py                   ← 独立功能脚本（22 个）
├── dashboard/                 ← FastAPI 只读 Web 看板
├── templates/                 ← 题材模板
├── references/                ← 共享参考文档
└── genres/                    ← 题材特定配置
```

### 架构判定：**部分合理**

**合理之处：**

- Agent/Skill 分层清晰：Agent 定义行为模式，Skill 定义用户入口，脚本实现数据逻辑
- 延迟导入机制（`__init__.py` lazy export）有效避免了 Python 启动慢和循环导入
- 环境初始化统一收口到 `env-setup.sh`，消除了 Skill 间重复
- `index_types.py` 已从 `index_manager.py` 抽出，解耦了 mixin ↔ manager 循环依赖
- Schema 版本追踪已在 IndexManager 和 RAGAdapter 中实现
- `path_guard.py` 对 Dashboard 做了路径穿越防护

**不合理之处：** 见下方结构性问题列表。

---

## 三、结构性问题

### 问题 1：scripts/ 与 data_modules/ 边界模糊（双层 Python 模块混居）

| 项 | 内容 |
|----|------|
| **严重级别** | 🟠 中 |
| **证据** | `scripts/` 下有 22 个独立 .py 文件（共 11,374 行），`data_modules/` 下有 32 个 .py 文件（共 16,293 行）。两层之间存在大量交叉导入：`scripts/*.py` 频繁 `from data_modules.xxx import ...`（见 `extract_chapter_context.py` 中 7 处、`archive_manager.py` 2 处等）。部分功能难以判断归属：`state_schema.py` 在 `scripts/` 而 `state_manager.py` 和 `state_validator.py` 在 `data_modules/`，功能高度重叠。 |
| **影响** | (1) 新增模块时不清楚放哪层；(2) `scripts/` 不是 Python package（有 `__init__.py` 但无 `setup.py`），靠 `sys.path.insert` 强制注入，IDE 静态分析失效；(3) 大文件集中在 `scripts/` 层（`extract_chapter_context.py` 68K、`anti_ai_scanner.py` 45K、`status_reporter.py` 47K），缺乏模块化拆分。 |
| **建议** | 将 `scripts/` 中的核心逻辑模块（state_schema、backup_manager、archive_manager 等）迁入 `data_modules/` 或新建 `core/` package。`scripts/` 仅保留 CLI 入口和 Shell 脚本。不急于行动，建议在下一个大版本时统一整理。 |

---

### 问题 2：800 行 Bash 编排器承载过重（ink-auto.sh）

| 项 | 内容 |
|----|------|
| **严重级别** | 🟠 中 |
| **证据** | `ink-auto.sh` 800 行，包含：项目探测、大纲检查、CLI 检测（claude/gemini/codex 三分支）、分层检查点逻辑（5/10/20 章）、审查报告解析（`grep -qiE "critical|high|严重|错误"`）、修复调度、运行报告生成、信号处理等。其中审查报告解析使用正则匹配中文关键词（`严重|错误|不一致|漂移|失衡|逾期`），脆弱且难以测试。 |
| **影响** | (1) Bash 无单元测试框架，这 800 行完全没有测试覆盖；(2) 正则解析审查报告是脆弱耦合——报告格式变化会静默失效；(3) 三平台 CLI 适配在 Bash 中用字符串匹配实现，维护成本高。 |
| **建议** | 将检查点逻辑、报告解析、统计计数等抽为 Python 函数（可测试），Bash 仅做最外层进程编排。 |

---

### 问题 3：测试覆盖率极低且分布失衡

| 项 | 内容 |
|----|------|
| **严重级别** | 🔴 高 |
| **证据** | CI 门槛 `--cov-fail-under=15`，实际覆盖率 15.44%。`data_modules/` 的 32 个模块中，有 **24 个模块无直接测试**，包括核心模块：`index_manager.py`（含 25 张表的 DDL）、`state_manager.py`（1720 行）、`entity_linker.py`、`query_router.py`、`snapshot_manager.py`、`writing_guidance_builder.py`。`scripts/` 层 22 个 .py 文件完全不在覆盖率统计范围内（`.coveragerc` 的 `source` 仅指向 `data_modules`）。Dashboard（FastAPI 应用）零测试。 |
| **影响** | (1) 核心数据链（index/state/entity）改动风险极高，无回归保护；(2) 15% 门槛形同虚设，无法捕获退化；(3) `scripts/` 层的大文件（extract_chapter_context 68K、status_reporter 47K）变更完全裸奔。 |
| **建议** | 短期：将门槛提升到 25%，优先为 `index_manager`、`state_manager`、`entity_linker` 补写核心路径测试。中期：将 `scripts/` 纳入覆盖率统计。长期目标 50%+。 |

---

### 问题 4：Dashboard 的 CORS 全开放

| 项 | 内容 |
|----|------|
| **严重级别** | 🟡 低（当前仅本地使用） |
| **证据** | `dashboard/app.py:72` 设置 `allow_origins=["*"]`。 |
| **影响** | 如果用户在公网暴露 Dashboard，任意域名可跨域访问。当前 Dashboard 为只读且有 path_guard 防护，风险可控。但如果未来增加写入接口，风险会升级。 |
| **建议** | 将默认 CORS 收窄为 `["http://localhost:*", "http://127.0.0.1:*"]`，或通过环境变量配置。低优先级。 |

---

### 问题 5：弃用 Skill（ink-5）仍保留完整实现

| 项 | 内容 |
|----|------|
| **严重级别** | 🟡 低 |
| **证据** | `skills/ink-5/SKILL.md` 标注"⚠️ 已弃用"，但保留了完整的执行逻辑（非空壳重定向）。README 和 GEMINI.md 均标注已弃用。`skill.md` 的描述中已有重定向提示。 |
| **影响** | 用户仍可执行 `/ink-5`，会运行旧逻辑而非重定向到 `/ink-auto 5`。增加维护负担且可能产生行为差异。 |
| **建议** | 将 `ink-5/SKILL.md` 缩减为纯重定向桩（仅输出弃用提示 + 自动调用 `/ink-auto 5`），或在下一大版本直接移除。 |

---

### 问题 6：根目录 requirements.txt 是间接引用，缺乏锁定

| 项 | 内容 |
|----|------|
| **严重级别** | 🟡 低 |
| **证据** | 根 `requirements.txt` 内容为 `-r ink-writer/scripts/requirements.txt` + `-r ink-writer/dashboard/requirements.txt`。`scripts/requirements.lock` 和 `dashboard/requirements.lock` 已存在（pip-compile 生成），但根目录无对应 lock 文件。CI 使用 `pip install -r ink-writer/scripts/requirements.lock`，跳过了 dashboard 依赖。 |
| **影响** | (1) 用户按 README 执行 `pip install -r requirements.txt` 安装的是无锁定版本；(2) CI 不验证 dashboard 依赖。 |
| **建议** | 在根目录生成合并的 `requirements.lock`，或在 README 中引导用户使用 lock 文件。低优先级。 |

---

### 问题 7：.coveragerc 存在两份，语义冲突

| 项 | 内容 |
|----|------|
| **严重级别** | 🟡 低 |
| **证据** | 根目录 `.coveragerc` source 为 `ink-writer/scripts/data_modules`，omit 包含 `*/ink.py`、`*/style_anchor.py`、`*/cli_args.py`。`scripts/.coveragerc` source 为 `data_modules`，omit 仅有 `*/tests/*`。两份配置的 omit 范围不一致。 |
| **影响** | 从不同目录运行 `pytest` 会得到不同的覆盖率数字。根目录多排除了 3 个文件，可能掩盖这些文件的覆盖率退化。 |
| **建议** | 统一为一份 `.coveragerc`，放在根目录，删除 `scripts/.coveragerc`。`pytest.ini` 已配置从根目录运行。 |

---

### 问题 8：大文件缺乏模块化拆分

| 项 | 内容 |
|----|------|
| **严重级别** | 🟡 低 |
| **证据** | `extract_chapter_context.py` 68,050 字节（~1800 行）、`anti_ai_scanner.py` 45,447 字节（~1200 行）、`status_reporter.py` 47,203 字节（~1300 行）、`init_project.py` 35,467 字节、`workflow_manager.py` 34,646 字节。 |
| **影响** | 单文件过大增加认知负荷和合并冲突概率，但当前不影响运行时。 |
| **建议** | 不急于拆分。当这些文件因功能需求需要修改时，顺带拆分。 |

---

## 四、不是问题的地方（经审查确认合理）

| 方面 | 判定 |
|------|------|
| `.gitignore` | 覆盖全面：`__pycache__`、`.coverage`、`.ink/`、`dist/`、`.DS_Store` 等均已排除 |
| Git 历史中无敏感文件 | `git ls-files` 无 `__pycache__`、`.pyc`、`.coverage` |
| 无硬编码路径 | `scripts/` 和 `data_modules/` 中未发现 `/Users/cipher` 或 `/home/` 硬编码 |
| 环境初始化 | `env-setup.sh` 统一处理 `CLAUDE_PLUGIN_ROOT` 推断，逻辑清晰 |
| 循环依赖处理 | `index_types.py` 已从 `index_manager.py` 抽出，延迟导入机制有效 |
| Schema 版本追踪 | `IndexManager.SCHEMA_VERSION = 1`，`RAG_SCHEMA_VERSION = "2"`，均有迁移逻辑 |
| 安全防护 | Dashboard 有 `path_guard.py` 路径穿越防护；`security_utils.py` 存在 |
| 依赖锁定 | `requirements.lock` 由 pip-compile 生成，CI 使用锁定版本 |
| 三平台适配 | 通过 `GEMINI.md` + `gemini-extension.json` + 各 Skill 内适配实现，非代码分叉 |
| 版本同步 | `sync_plugin_version.py --check` + CI Plugin Version Check 保障一致性 |
| 发布流程 | `plugin-release.yml` workflow_dispatch 手动触发，有版本验证 + tag 创建 |

---

## 五、综合评价

### 1. 总体评价：**部分合理**

架构设计理念清晰（Agent/Skill/Script 三层分离 + Harness-First），工程基础设施已有 CI、锁定依赖、版本同步等保障。但核心问题在于**测试覆盖率过低**（15%）和**模块边界不够清晰**（scripts/ vs data_modules/ 双层混居），这两个问题会随着系统复杂度增长而放大风险。

### 2. 最关键的 3 个问题

| 排名 | 问题 | 理由 |
|------|------|------|
| **#1** | 测试覆盖率 15%，核心模块裸奔 | 25 张表的 IndexManager、1720 行的 StateManager 无测试，任何改动都是在走钢丝 |
| **#2** | 800 行 Bash 编排器不可测试 | ink-auto 是用户最常用的命令，其检查点/修复/报告解析逻辑完全无测试保护 |
| **#3** | scripts/ 与 data_modules/ 边界模糊 | 导致新模块归属不清、大文件堆积、覆盖率统计遗漏 |

### 3. 最值得做的 3 个优化

| 排名 | 优化 | 投入产出比 |
|------|------|-----------|
| **#1** | 为 IndexManager + StateManager + EntityLinker 补核心路径测试，门槛提至 25% | 高 ROI：保护最易出错的数据链，工作量可控（3-5 天） |
| **#2** | 将 ink-auto.sh 的检查点判断 + 报告解析抽为 Python 模块 | 中 ROI：可测试 + 可复用，Bash 仅做进程编排 |
| **#3** | 统一 .coveragerc 为一份 + 将 scripts/ 纳入覆盖率统计 | 高 ROI：10 分钟完成，立即消除覆盖率盲区 |

### 4. 哪些地方先别动

| 区域 | 理由 |
|------|------|
| **Agent 定义文件（agents/*.md）** | 14 个 Agent prompt 是经过实际写作验证的，改动需要端到端回归，当前没有自动化手段验证 prompt 变更的效果 |
| **Skill 引用链（skills/*/references/）** | 每个 Skill 的参考文档是写作质量的知识基座，改动可能影响生成质量但无法自动检测 |
| **extract_chapter_context.py（68K）** | 虽然大，但它是上下文构建的核心引擎，拆分前需要先补测试，否则重构引入的 bug 无法捕获 |
| **data_modules/__init__.py 的延迟导入机制** | 当前工作正常且解决了实际问题（循环导入 + 启动性能），不要为了"更优雅"而改它 |
| **ink-auto.sh 的信号处理和进程管理** | 跨平台进程控制在 Bash 中已经过调试，贸然迁移到 Python subprocess 可能引入新问题 |

---

## 附录：项目统计

| 指标 | 数值 |
|------|------|
| Git 管理文件数 | 327 |
| 总代码行数 | ~90,000 |
| Python 代码（scripts/ + data_modules/） | ~27,700 行 |
| Agent 定义 | 14 个，共 3,731 行 |
| Skill 定义 | 14 个 |
| Shell 脚本 | 3 个（ink-auto.sh 800 行 + env-setup.sh 61 行 + migrate 脚本） |
| 测试文件 | 25 个 |
| 测试覆盖率 | 15.44%（门槛 15%） |
| CI Workflows | 3 个（test / version-check / release） |
| 依赖 lock 文件 | 2 个（scripts + dashboard） |
