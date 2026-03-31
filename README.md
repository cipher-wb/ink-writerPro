# Ink Writer Pro

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-7.0.5-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple.svg)](https://claude.ai/claude-code)

基于 Claude Code 的**工业化长篇网文创作系统**。支持 200 万字（600+ 章）连续创作，每章自动执行 9 步标准流程（上下文→写作→审查→润色→数据回写），跨会话状态持久化，防幻觉三定律 + 11 Agent 审查 + 去 AI 味 + 节奏控制。

| 版本 | 说明 |
|------|------|
| **v7.0.5 (当前)** | B0-B3 综合优化：补全 Agent 定义、权重校准、预算分层、批量恢复、风格锚定、情感层增强 |
| **v7.0.1** | 金丝雀健康扫描、里程碑强制审查、index.db 完整性检查 |

---

## 安装

### 前置条件

- **Claude Code**（Anthropic 官方 CLI）— [安装指南](https://docs.anthropic.com/en/docs/claude-code/overview)
- **Python 3.10+** — [下载地址](https://www.python.org/downloads/)

### Mac / Linux

```bash
# 1. 添加插件源
claude plugin marketplace add cipher-wb/ink-writerPro --scope user

# 2. 安装插件
claude plugin install ink-writer@ink-writer-marketplace --scope user

# 3. 安装 Python 依赖
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

### Windows

```powershell
# 1. 添加插件源
claude plugin marketplace add cipher-wb/ink-writerPro

# 2. 安装插件
claude plugin install ink-writer@ink-writer-marketplace

# 3. 安装 Python 依赖
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

> Windows 不需要加 `--scope user`。如果 `pip` 提示找不到，试试 `pip3`。

### 验证安装

打开 Claude Code，输入 `/ink-init`，看到初始化引导说明安装成功。

### 后续更新

**Mac / Linux：**
```bash
claude plugin install ink-writer@ink-writer-marketplace --scope user
```

**Windows：**
```powershell
claude plugin install ink-writer@ink-writer-marketplace
```

---

## 使用

```bash
/ink-init              # 初始化小说项目（交互式收集设定）
/ink-plan 1            # 生成第 1 卷详细大纲
/ink-write             # 写一章（完整 9 Step 流程）
/ink-5                 # 连续写 5 章 + Full 审查 + 自动修复
/ink-review 1-5        # 审查第 1-5 章
/ink-query             # 查询项目状态（角色/伏笔/节奏）
/ink-audit             # 数据对账（检测累积误差）
/ink-macro-review      # 宏观审查（50章/200章里程碑）
/ink-resume            # 中断恢复
/ink-dashboard         # 可视化面板（只读）
```

## 架构

```
Skills (11)    ink-init / ink-plan / ink-write / ink-5 / ink-review
               ink-query / ink-audit / ink-macro-review / ink-resolve
               ink-resume / ink-dashboard

Agents (11)    context-agent / data-agent
               consistency / continuity / ooc / anti-detection (核心 4)
               reader-pull / high-point / pacing / proofreading
               reader-simulator / golden-three (条件 6)

Data Layer     index.db (SQLite 23 表) + state.json + vectors.db (RAG)

References     38 种题材模板 + 9 反套路库 + 核心约束 + 追读力体系
```

## 写作流水线（9 Step）

```
Step 0    预检 + 权限卡           Step 2B    风格适配
Step 1    上下文构建（8 板块）     Step 3     多 Agent 审查
Step 2A   正文起草（≥2200 字）    Step 4     润色 + Anti-AI
Step 2A.5 字数校验               Step 4.5   改写安全校验
Step 5    Data Agent 回写        Step 6     Git 备份
```

## v7.0 核心特性

解决 200 万字连续创作的三大问题：

**数据完整性**
- `narrative_commitments` 表：追踪誓言/承诺/预言，consistency-checker 自动检测违反
- `character_evolution_ledger` 表：角色性格弧线 + 台词样本，复出时自动加载演变轨迹
- chapter_meta 自动 flush + strand_tracker 裁剪，防止 state.json 膨胀
- Data Agent 闪回检测，防止回忆章节导致主角状态回退

**上下文增强**
- 总纲加载 + 故事骨架智能采样（第 1 章 + 高分章 + 最近章）
- 伏笔氛围快照（种植现场 200-300 字原文，解决时回调增强共鸣）
- 关系演变轨迹注入（消费 relationship_events 表）
- 伏笔 urgent 窗口 5→10 + 逾期硬阻断

**宏观质量保障**
- 主题脊柱追踪：核心主题连续缺席 15 章自动告警
- 冲突结构指纹：50 章内同模式 ≥3 次自动检测
- `/ink-audit`：Quick / Standard / Deep 三级数据对账
- `/ink-macro-review`：Tier2（每 50 章）/ Tier3（每 200 章）宏观审查

## RAG 配置（可选）

在项目根目录创建 `.env`：

```bash
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_key
```

## 文档

- `docs/architecture.md` — 架构与模块
- `docs/commands.md` — 命令详解
- `docs/rag-and-config.md` — RAG 配置
- `docs/genres.md` — 38 种题材模板
- `docs/operations.md` — 运维与恢复

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。

## 致谢

使用 Claude Code + Gemini CLI + Codex 配合 Vibe Coding 开发。
