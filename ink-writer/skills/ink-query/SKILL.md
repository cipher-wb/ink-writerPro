---
name: ink-query
description: Queries project settings for characters, powers, factions, items, and foreshadowing. Supports urgency analysis and golden finger status. Activates when user asks about story elements or /ink-query.
allowed-tools: Read Grep Bash AskUserQuestion
---

# Information Query Skill

## Project Root Guard（必须先确认）

- Claude Code 的“工作区根目录”不一定等于“书项目根目录”。常见结构：工作区为 `D:\wk\xiaoshuo`，书项目为 `D:\wk\xiaoshuo\凡人资本论`。
- 必须先解析真实书项目根（必须包含 `.ink/state.json`），后续所有读写路径都以该目录为准。
- **禁止**在插件目录 `${CLAUDE_PLUGIN_ROOT}/` 下读取或写入项目文件

环境设置（bash 命令执行前）：
```bash
export WORKSPACE_ROOT="${INK_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  if [ -d "$PWD/scripts" ] && [ -d "$PWD/skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$PWD"
  elif [ -d "$PWD/../scripts" ] && [ -d "$PWD/../skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$(cd "$PWD/.." && pwd)"
  else
    echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT，且无法从当前目录推断插件根目录" >&2
    exit 1
  fi
fi

if [ -z "${CLAUDE_PLUGIN_ROOT}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/skills/ink-query" ]; then
  echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT 或缺少目录: ${CLAUDE_PLUGIN_ROOT}/skills/ink-query" >&2
  exit 1
fi
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT}/skills/ink-query"

if [ -z "${CLAUDE_PLUGIN_ROOT}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT 或缺少目录: ${CLAUDE_PLUGIN_ROOT}/scripts" >&2
  exit 1
fi
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"

export PROJECT_ROOT="$(python3 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## Workflow Checklist

Copy and track progress:

```
信息查询进度：
- [ ] Step 1: 识别查询类型
- [ ] Step 2: 加载对应参考文件
- [ ] Step 3: 加载项目数据 (state.json)
- [ ] Step 4: 确认上下文充足
- [ ] Step 5: 执行查询
- [ ] Step 6: 格式化输出
```

---

## Reference Loading Levels (strict, lazy)

- L0: 先识别查询类型，不预加载全部参考。
- L1: 所有查询仅加载基础数据流规范。
- L2: 仅按查询类型加载对应专题参考。

### L1 (minimum)
- [system-data-flow.md](references/system-data-flow.md)

### L2 (conditional by query type)
- 伏笔查询：[foreshadowing.md](references/advanced/foreshadowing.md)
- 节奏查询：[strand-weave-pattern.md](../../references/shared/strand-weave-pattern.md)
- 标签格式查询：[tag-specification.md](references/tag-specification.md)

Do not load two or more L2 files unless the user request clearly spans multiple query types.

## Step 1: 识别查询类型

| 关键词 | 查询类型 | 需加载 |
|--------|---------|--------|
| 角色/主角/配角 | 标准查询 | system-data-flow.md |
| 境界/筑基/金丹 | 标准查询 | system-data-flow.md |
| 伏笔/紧急伏笔 | 伏笔分析 | foreshadowing.md |
| 金手指/系统 | 金手指状态 | system-data-flow.md |
| 节奏/Strand | 节奏分析 | strand-weave-pattern.md |
| 标签/实体格式 | 格式查询 | tag-specification.md |
| 健康度/全局/总览 | 全局健康度 | system-data-flow.md + foreshadowing.md |

## Step 2: 加载对应参考文件

**所有查询必须执行**：
```bash
cat "${SKILL_ROOT}/references/system-data-flow.md"
```

**伏笔查询额外执行**：
```bash
cat "${SKILL_ROOT}/references/advanced/foreshadowing.md"
```

**节奏查询额外执行**：
```bash
cat "${SKILL_ROOT}/../../references/shared/strand-weave-pattern.md"
```

**标签格式查询额外执行**：
```bash
cat "${SKILL_ROOT}/references/tag-specification.md"
```

## Step 3: 加载项目数据

```bash
cat "$PROJECT_ROOT/.ink/state.json"
```

## Step 4: 确认上下文充足

**检查清单**：
- [ ] 查询类型已识别
- [ ] 对应参考文件已加载
- [ ] state.json 已加载
- [ ] 知道在哪里搜索答案

**如有缺失 → 返回对应 Step**

## Step 5: 执行查询

### 标准查询

| 关键词 | 搜索目标 |
|--------|---------|
| 角色/主角/配角 | 主角卡.md, 角色库/ |
| 境界/实力 | 力量体系.md |
| 宗门/势力 | 世界观.md |
| 物品/宝物 | 物品库/ |
| 地点/秘境 | 世界观.md |

### 伏笔紧急度分析

**三层分类**（来自 foreshadowing.md）：
- **核心伏笔**: 主线剧情 - 权重 3.0x
- **支线伏笔**: 配角/支线 - 权重 2.0x
- **装饰伏笔**: 氛围/细节 - 权重 1.0x

**紧急度公式**：
```
紧急度 = (已过章节 / 目标章节) × 层级权重
```

**状态判定**：
- 🔴 Critical: 超过目标 OR 核心 >20 章
- 🟡 Warning: >80% 目标 OR 支线 >30 章
- 🟢 Normal: 计划范围内

**快速分析**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" status -- --focus urgency
```

### 金手指状态

输出包含：
- 基本信息（名称/类型/激活章节）
- 当前等级和进度
- 已解锁技能及冷却
- 待解锁技能预览
- 升级条件
- 发展建议

### Strand 节奏分析

**快速分析**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" status -- --focus strand
```

**检查警告**：
- Quest >5 连续章
- Fire >10 章未出现
- Constellation >15 章未出现

### 全局健康度查询（关键词：健康度/全局/总览）

> 一键查看项目整体状态，适用于长时间未操作后快速恢复上下文。

**执行命令**：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" status -- --focus all
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index get-recent-review-metrics --limit 10
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" index get-debt-summary
```

**输出结构**：

```markdown
# 项目全局健康度报告

## 创作进度
- 当前章节: 第 {N} 章 / 目标 {total} 章（{percent}%）
- 当前卷: 第 {V} 卷
- 最近写作时间: {date}

## 审查质量趋势
- 最近 10 章平均分: {avg_score}
- 最近 10 章分数走势: {trend}（上升/稳定/下降）
- 未解决 critical 问题: {count} 个

## Strand 三线平衡
- Quest 占比: {q}%（最近出现: 第 {ch} 章）
- Fire 占比: {f}%（最近出现: 第 {ch} 章）
- Constellation 占比: {c}%（最近出现: 第 {ch} 章）
- 平衡状态: {健康/预警/失衡}

## 伏笔健康度
- 活跃伏笔: {total} 条
- 紧急伏笔（即将到期）: {urgent} 条
- 逾期伏笔（已超目标章）: {overdue} 条
- 跨卷伏笔（跨越 2 卷以上）: {cross_volume} 条

## 债务状态
- 活跃 Override 债务: {count} 条
- 逾期债务: {overdue_count} 条

## 风险预警
{按严重度排序的风险项列表}
```

### 跨卷伏笔追踪（伏笔查询增强）

> 长篇项目中跨越多卷的伏笔最容易遗忘。本查询专门追踪跨卷伏笔状态。

**触发条件**：伏笔查询时自动附加，或用户明确查询"跨卷伏笔"。

**执行逻辑**：
1. 从 `state.json → plot_threads.foreshadowing` 读取全部伏笔
2. 对每条伏笔，判断 `planted_chapter` 和 `target_chapter` 是否跨卷（对照 `总纲.md` 的卷次范围）
3. 按风险等级排序输出

**跨卷伏笔风险等级**：

| 等级 | 条件 | 建议 |
|------|------|------|
| 极高 | 核心伏笔 + 已跨 2 卷以上未回收 | 当前卷内必须回收或显式提及 |
| 高 | 支线伏笔 + 已跨 2 卷以上未回收 | 本卷内安排提及或部分回收 |
| 中 | 核心伏笔 + 跨 1 卷未回收但在目标范围内 | 持续追踪，确保按计划回收 |
| 低 | 装饰伏笔 + 跨卷 | 可选回收，不回收也不影响主线 |

**输出格式**：
```markdown
## 跨卷伏笔追踪

| 伏笔内容 | 层级 | 埋设 | 目标 | 跨卷数 | 风险 | 建议 |
|---------|------|------|------|--------|------|------|
| {content} | 核心 | 第1卷·第5章 | 第3卷·第80章 | 2卷 | 极高 | 第2卷内需显式提及 |
```

## Step 6: 格式化输出

```markdown
# 查询结果：{关键词}

## 概要
- **匹配类型**: {type}
- **数据源**: state.json + 设定集 + 大纲
- **匹配数量**: X 条

## 详细信息

### 1. Runtime State (state.json)
{结构化数据}
**Source**: `.ink/state.json` (lines XX-XX)

### 2. 设定集匹配结果
{匹配内容，含文件路径和行号}

## 数据一致性检查
{state.json 与静态文件的差异}
```
