# Ink Writer

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-purple.svg)](https://claude.ai/claude-code)
[![Version](https://img.shields.io/badge/Version-6.3.0-green.svg)](ink-writer/.claude-plugin/plugin.json)

## 项目简介

`Ink Writer` 是基于 Claude Code 的**工业化长篇网文创作系统**，通过 8 Skills + 11 Agents + 80+ Python 模块构建了从初始化到发布的完整写作流水线。

**核心能力**：
- **防幻觉三定律**（大纲即法律 / 设定即物理 / 发明需识别）+ 写作权限卡
- **9 维审查体系**（3 核心 + 6 条件审查器，含读者模拟器）+ 统一评分权重
- **7 道去AI味防线**（防检测源头写作 → 风格转译 → anti-detection-checker 统计检测 → 终检修复 → 安全校验 → 长线监控 → 充分性闸门拦截）
- **Strand Weave 三线编织**（Quest/Fire/Constellation 节奏系统）+ 25 章自动检查点
- **38 种题材支持** + 9 个反套路库全覆盖
- **统一标准模式**：所有章节始终以最高规格执行完整 9 Step 流程，不降级不简化
- **批量连写模式** `--batch N`：一次连写多章，每章严格执行完整 9 Step 流程，质量与单章一致

### 系统架构

```
Skills (8)     ink-init → ink-plan → ink-write (支持 --batch 连写) → ink-review
               ink-query / ink-resume / ink-learn / ink-dashboard

Agents (12)    context-agent / data-agent
               consistency / continuity / ooc / anti-detection (核心 4)
               reader-pull / high-point / pacing / golden-three
               proofreading / reader-simulator (条件 6)

Data Layer     index.db (SQLite) + state.json + vectors.db
               review_library.jsonl + quality_baseline.json

References     genre-profiles / core-constraints / reading-power
               strand-weave / review-bundle-schema / 9 反套路库
```

### 写作流水线（9 Step）

```
Step 0    预检 + 权限卡        Step 2A.5  字数校验
Step 1    上下文构建            Step 2B    风格适配
Step 2A   正文起草              Step 3     多Agent审查（3+6 checker）
Step 4    润色 + Anti-AI        Step 4.5   改写安全校验
Step 5    Data Agent 回写       Step 6     Git 精确备份
```

批量模式下，以上 9 Step 会严格串行重复 N 次，每章独立走完全流程。

详细文档：

- 架构与模块：`docs/architecture.md`
- 命令详解：`docs/commands.md`
- RAG 与配置：`docs/rag-and-config.md`
- 题材模板：`docs/genres.md`
- 运维与恢复：`docs/operations.md`
- 文档导航：`docs/README.md`

## 快速开始

### 1) 安装插件（官方 Marketplace）

```bash
claude plugin marketplace add cipher-wb/ink-writer --scope user
claude plugin install ink-writer@ink-writer-marketplace --scope user
```

> 仅当前项目生效时，将 `--scope user` 改为 `--scope project`。

### 2) 安装 Python 依赖

```bash
python -m pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writer/HEAD/requirements.txt
```

说明：该入口会同时安装核心写作链路与 Dashboard 依赖。

### 3) 初始化小说项目

在 Claude Code 中执行：

```bash
/ink-init
```

说明：`/ink-init` 会在当前 Workspace 下按书名创建 `PROJECT_ROOT`（子目录），并在 `workspace/.claude/.ink-current-project` 写入当前项目指针。

### 4) 配置 RAG 环境（必做）

进入初始化后的书项目根目录，创建 `.env`：

```bash
cp .env.example .env
```

最小配置示例：

```bash
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_embed_api_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_rerank_api_key
```

### 5) 开始使用

```bash
/ink-plan 1           # 生成第 1 卷大纲
/ink-write            # 写一章（完整 9 Step 标准流程）
/ink-write --batch 5  # 连续写 5 章（每章完整执行标准流程）
/ink-write --batch    # 默认连续写 5 章
/ink-review 1-5       # 审查第 1-5 章
```

`--batch N` 会自动从 `state.json` 读取当前进度，依次写第 `current + 1` 到 `current + N` 章。每章严格执行完整的 Step 0 → Step 6 流程，与手动逐章执行 `/ink-write` 完全一致。

**批量模式保障机制**：
- **串行执行**：第 i 章完整通过充分性闸门和验证后，才开始第 i+1 章
- **章号交叉验证**：每章开始前从 `state.json` 重新读取进度，与预期章号比对，不一致则暂停
- **章间清理**：自动清理上一章的 workflow 残留状态，确保每章干净启动
- **失败处理**：单章失败时按回滚规则重试，重试仍失败则暂停并询问用户
- **完成报告**：全部写完后输出汇总（完成数/总字数/平均评分/各章概览）

如需排查本地 CLI / 插件目录 / 项目根解析问题，可直接运行统一预检：

```bash
python -X utf8 "<CLAUDE_PLUGIN_ROOT>/scripts/ink.py" --project-root "<WORKSPACE_ROOT>" preflight
```

### 6) 启动可视化面板（可选）

```bash
/ink-dashboard
```

说明：
- Dashboard 为只读面板（项目状态、实体图谱、章节/大纲浏览、追读力查看）。
- 前端构建产物已随插件发布，使用者无需本地 `npm build`。

### 7) Agent 模型设置（可选）

本项目所有内置 Agent 默认配置为：

```yaml
model: inherit
```

表示子 Agent 继承当前 Claude 会话所用模型。

如果要单独给某个 Agent 指定模型，编辑对应文件（`ink-writer/agents/*.md`）的 frontmatter，例如：

```yaml
---
name: context-agent
description: ...
tools: Read, Grep, Bash
model: sonnet
---
```

常见可选值：`inherit` / `sonnet` / `opus` / `haiku`（以 Claude Code 当前支持为准）。

## 更新简介

| 版本 | 说明 |
|------|------|
| **v6.3.0 (当前)** | 新增防AI检测体系：Step 2A 源头防检测写作指南 + `anti-detection-checker` 核心审查器（6层统计特征检测）+ Step 4 AI味定向修复 + 充分性闸门拦截。 |
| **v6.2.0** | 删除 `--fast`/`--minimal` 模式，统一为标准模式（最高规格）；所有章节始终执行完整 9 Step 流程。 |
| **v6.1.0** | 新增 `--batch N` 批量连写模式，支持一次连续写多章，每章完整执行 9 Step 流程。 |
| **v6.0.0** | **大版本升级 — 22 项深度优化**。详见下方 v6.0.0 更新详情。 |
| **v5.5.4** | 补齐写作链提示词强约束（流程硬约束、中文思维写作约束、Step 职责边界）；统一中文化审查/润色/Agent 报告文案。 |
| **v5.5.3** | 新增统一 `preflight` 预检命令；写作链 CLI 示例统一为 UTF-8 运行方式。 |
| **v5.5.0** | 新增只读可视化 Dashboard Skill（`/ink-dashboard`）与实时刷新能力。 |
| **v5.4.4** | 引入官方 Plugin Marketplace 安装机制。 |
| **v5.3** | 引入追读力系统（Hook / Cool-point / 微兑现 / 债务追踪） |

### v6.0.0 更新详情

**综合评分从 86 分（A-）提升到 91 分（A），22 项改进，覆盖全部 4 个优化阶段。**

#### P0 紧急修复（3 项）

| # | 修复项 | 说明 |
|---|--------|------|
| 1 | 跨平台兼容 | ink-plan 中 3 处 PowerShell 语法替换为 bash `cat <<'EOF'` |
| 2 | 字数校验 | 新增 Step 2A.5，5 档判定（<1500 必须补写 / >4000 必须精简）+ 豁免条件 |
| 3 | proofreading 调度 | proofreading-checker 正式纳入 ink-write/ink-review 审查流程 |

#### P1 核心优化（7 项）

| # | 修复项 | 说明 |
|---|--------|------|
| 4 | state.json 保护 | 禁止直写铁律 + data-agent 并发写入保护 5 条规则 |
| 5 | 批次间衔接校验 | ink-plan 新增 5 项校验（钩子/时间/Strand/反派/角色状态） |
| 6 | Token 预算 | 黄金三章（ch1-3）从 5000 → 8000 tokens |
| 7 | 职责边界铁律 | Step 2A/2B/4 职责矩阵表 + 2B 自检零偏差 |
| 8 | 改写安全校验 | 新增 Step 4.5（快照 + diff + 5 项检查 + 违规恢复） |
| 9 | ~~审查智能降级~~ | ~~已在 v6.2.0 移除~~ — 统一为标准模式，不再降级 |
| 10 | 续写上下文 | ink-resume 所有续写路径强制先执行 Step 1 |

#### P2 体验优化（8 项）

| # | 修复项 | 说明 |
|---|--------|------|
| 11 | 评分权重统一 | 7 个 checker 权重表 + 总分公式 + critical 上限 60 分 |
| 12 | 审查包规范 | 新建 review-bundle-schema.md（10 字段 + 读取规则） |
| 13 | Git 精确备份 | `git add .` → 精确指定正文/state/index/summaries |
| 14 | 跨卷伏笔追踪 | ink-query 新增 4 级风险等级跨卷伏笔查询 |
| 15 | ink-learn 升级 | 3 模式分析引擎（手动/自动/趋势）+ 风格指纹 |
| 16 | 全局健康度 | ink-query 新增一键查询（进度/审查趋势/Strand/伏笔/债务/风险） |
| 17 | 反套路库补全 | 新增历史/末世/悬疑 3 库，共 9 库覆盖 38 种题材 |
| 18 | 文风一致性 | proofreading-checker 新增第 5 层（5 项指标 vs 近 5 章基线） |

#### P3 长远架构（4 项）

| # | 修复项 | 说明 |
|---|--------|------|
| 19 | SQLite 迁移指南 | 3 阶段渐进策略 + DDL + 双写 + 回滚方案 |
| 20 | 成本控制策略 | 预算表 + 批量优化 + 仪表盘 `status --focus cost` |
| 21 | 审查历史库 | 高分章节自动采集 + 质量基线 + review_library.jsonl |
| 22 | 读者模拟器 | 新增 reader-simulator Agent（6 类画像 + 情绪曲线 + 弃读风险 + 读者独白） |

## 插件发版

推荐使用 GitHub Actions 的 `Plugin Release` 工作流统一发版：

1. 先在本地同步版本信息：
   ```bash
   python -X utf8 ink-writer/scripts/sync_plugin_version.py --version 6.0.0 --release-notes "本次版本说明"
   ```
2. 提交并推送版本变更（`README.md`、`plugin.json`、`marketplace.json`）。
3. 打开仓库的 Actions 页面，选择 `Plugin Release`。
4. 输入与当前仓库元数据一致的 `version`（例如 `5.5.4`）和用于 GitHub Release 的 `release_notes`。
5. 工作流会执行以下动作：
   - 校验 `plugin.json`、`marketplace.json` 与 README 当前版本已经一致
   - 校验当前版本与输入的 `version` 一致
   - 创建并推送 `vX.Y.Z` Tag
   - 创建同名 GitHub Release

日常开发中，`Plugin Version Check` 会在 Push / PR 时自动校验版本信息是否一致。

## 开源协议
本项目使用 `GPL v3` 协议，详见 `LICENSE`。

## Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=cipher-wb/ink-writer&type=Date)](https://star-history.com/#cipher-wb/ink-writer&Date)

## 致谢

本项目使用 **Claude Code + Gemini CLI + Codex** 配合 Vibe Coding 方式开发。  
灵感来源：[Linux.do 帖子](https://linux.do/t/topic/1397944/49)

## 贡献

欢迎提交 Issue 和 PR：

```bash
git checkout -b feature/your-feature
git commit -m "feat: add your feature"
git push origin feature/your-feature
```
