---
name: ink-auto
description: 跨会话无人值守智能批量写作。每章独立 CLI 会话，内置分层检查点（审查+修复+审计+宏观审查）和自动大纲生成。用法：/ink-auto [章数]
allowed-tools: Bash Read
---

# 跨会话无人值守智能批量写作（ink-auto）

## 解决的问题

使用小上下文模型（如 200k）时，单章写作消耗 60-70% 上下文。`/ink-5` 在同一会话连写 5 章会导致上下文溢出和降智。此外，用户需要手动执行 `/ink-review`、`/ink-audit`、`/ink-macro-review`、`/ink-plan` 等指令，流程碎片化。

## 原理

每章启动全新 CLI 进程，进程退出 = 上下文自然清零。等价于手动：
```
/ink-write → /clear → /ink-write → /clear → ...
```

内置智能分层检查点（v16 US-008 正式化 5 档）：每 5/10/20/50/200 章自动触发不同级别的质量检查和修复。缺失大纲时自动启动 ink-plan 生成。

## 用法

```
/ink-auto        → 默认写 5 章（串行）
/ink-auto 10     → 写 10 章（串行）
/ink-auto 100    → 写 100 章（全自动，含检查点和自动规划）
/ink-auto 1      → 写 1 章（测试用）
```

### 并发模式

```
/ink-auto --parallel 4 20  → 4 章并发写 20 章
/ink-auto -p 4 10          → 同上简写
```

并发模式委托给 `ink_writer.parallel.PipelineManager` asyncio 编排器：
- 每批 N 章并发写作，使用独立 CLI 进程
- ✅ `parallel ≤ 4` 已接 `ChapterLockManager` 验证安全：章节级 `async_chapter_lock` 独占 + Step 5 data-agent `state_update_lock` 串行化 `state.json` / `index.db` 写入；跨进程走 SQLite WAL + filelock 兜底（见 `ink_writer/parallel/chapter_lock.py`、`tests/parallel/test_chapter_lock_integration.py`）。`parallel > 4` 仍建议下调以平衡磁盘/LLM 限流。
- 检查点在每批完成后统一运行
- 单章失败触发重试，批次失败中止后续

## 终极自动化模式（v27 新增）

未初始化项目下运行 `/ink-auto N` 触发自动 bootstrap：

| CWD 状态 | 行为 |
|----------|------|
| 顶层有非黑名单 `.md` 蓝本 | 读取最大那份 → 转 quick draft → 自动 init → 自动 plan → 写 N 章 |
| 空目录（无 `.md`） | 弹 7 题问答 → 落盘 `.ink-auto-blueprint.md` → 同上 |
| 已 init 但缺当前章卷大纲 | 自动 plan → 写 N 章 |
| 已 init + 已写一半 | 直接写 N 章（沿用现有逻辑） |
| 已 init + 已完结 | 报错"项目已完结" |

**蓝本黑名单**：`README.md` / `CLAUDE.md` / `TODO.md` / `CHANGELOG.md` / `LICENSE.md` / `CONTRIBUTING.md` / `AGENTS.md` / `GEMINI.md` / `*.draft.md`。

**蓝本模板**：`ink-writer/templates/blueprint-template.md`，必填字段 5 个：题材方向 / 核心冲突 / 主角人设 / 金手指类型 / 能力一句话。

### 回滚开关

| 环境变量 | 默认 | 关闭后行为 |
|---------|------|-----------|
| `INK_AUTO_INIT_ENABLED` | `1` | `0` → 退化到现状（state.json 缺失 → exit 1） |
| `INK_AUTO_BLUEPRINT_ENABLED` | `1` | `0` → 跳过蓝本扫描，蓝本 `.md` 也走 7 题 |
| `INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED` | `1` | `0` → 空目录直接报错 |

## 平台感知（v26.2）

ink-auto 本身不改 —— plan → write → review → polish 的编排器逻辑不变，
平台差异已下沉到各阶段。auto 启动时从 `.ink/state.json` 读取 `project_info.platform`
并自动传递给每个子步骤。

## 执行方式

调用 `ink-auto.sh` shell 脚本。脚本自动检测项目路径和 CLI 平台。

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
```


解析用户参数（章数），然后执行：

```bash
bash "${SCRIPTS_DIR}/ink-auto.sh" ${章数:-5}
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
& "$env:SCRIPTS_DIR/ink-auto.ps1" $(if ($args[0]) { $args[0] } else { 5 })
```


## 智能检查点系统

写作过程中，根据章节号自动触发分层质量检查：

| 触发条件 | 操作 | 预估耗时 |
|----------|------|----------|
| **每 5 章** (5,10,15…) | ink-review Core（最近 5 章）+ **自动修复** | ~20-30min |
| **每 10 章** (10,20,30…) | + ink-audit quick + **自动修复数据问题** | +5min |
| **每 20 章** (20,40,60…) | + ink-audit standard + ink-macro-review Tier2（浅版）+ **自动修复** + 消歧积压检查 | +40min |
| **每 50 章** (50,100,150…) | + Tier2（完整版）+ `propagation.drift_detector` 跨章漂移检测 | +15min |
| **每 200 章** (200,400…) | + Tier3 跨卷分析（支线健康/人物弧/承诺审计） | +30min |

检查点累加触发：第 200 章会同时执行 5/10/20/50/200 全部层级（Tier3 覆盖 Tier2 + audit standard + review）。

### 检查点覆盖内容

- **可读性**：文笔质量、修辞重复、段落结构
- **逻辑性**：设定一致、时间线连贯、因果链完整
- **人物一致性**：OOC 检测、角色弧光追踪
- **伏笔管理**：过期伏笔预警、伏笔收回验证、新伏笔预埋
- **追读力**：钩子质量、微兑现密度、章末悬念
- **数据健康**：state.json↔index.db 同步、消歧积压
- **宏观结构**：支线健康、冲突去重、承诺审计、风格漂移

### 全检查点自动修复（ink-fix skill）

**每个检查点操作都包含自动修复**，不只是审查。修复由 `ink-fix` skill 统一执行：

- **审查修复**：ink-review 内置修复（Step 7 选项A） + ink-fix 二次补刀。修复设定矛盾、逻辑断裂、OOC、追读力不足、AI味过重、文笔质量等正文问题。
- **审计修复**：ink-fix 读取审计报告，修复 state.json/index.db 数据不一致、过期伏笔标记、幽灵实体、摘要缺失。
- **宏观审查修复**：ink-fix 读取宏观报告，对**已写章节正文**执行定向修复（支线停滞补回调、角色弧光补微推进、承诺兑现补伏笔、风格漂移修正），同时注入约束影响后续写作。

修复流程：检查报告 → 检测 critical/high/严重问题 → 无问题跳过 → 有问题加载 ink-fix skill → 解析报告 → 分类修复正文+数据库 → 验证 → git commit

**安全边界**：不改剧情走向、不删大纲事件、不改角色核心决策、单章修复 ≤ 5 处、修后字数 ∈ `[MIN_WORDS, MAX_WORDS_HARD]`（默认 `[2200, 5000]`，由 `preferences.pacing.chapter_words ± 500` 推导；硬下限 2200 不可降、硬上限无豁免路径，v23 US-005）。

所有修复操作记录在运行报告中。

## 自动大纲生成

写作前检测章节大纲是否存在：

1. 批量启动前：扫描并预报缺失大纲（给用户5秒 Ctrl+C 机会）
2. 每章写作前：检查该章大纲
3. 若缺失：自动判断所属卷号 → 启动 ink-plan 生成完整卷大纲
4. 同一卷只尝试一次，生成失败则中止批量写作

## 消歧处理（ink-resolve）

ink-resolve 需要用户交互，无法全自动运行。ink-auto 的处理方式：
- 每20章自动检查消歧积压数量
- 积压 > 20 条：输出提醒
- 积压 > 100 条：输出强烈警告
- 不阻断批量写作，用户可择机手动执行 `/ink-resolve`

## 脚本运行过程（只读参考）

### 批量启动前预检

1. 基础预检（`preflight`）：校验项目结构、脚本完整性
2. **大纲覆盖扫描**（预报模式）：扫描所有 N 章大纲，缺失时预报但不中止

### 主循环

脚本内部循环 N 次，每次：

1. 从 `state.json` 读取当前章节号，计算下一章
2. **逐章大纲检查**：缺失则自动启动 ink-plan 生成
3. 清理上一轮的 workflow 残留状态（`workflow clear`）
4. 启动全新 CLI 进程执行完整 ink-write 流程
5. 等待进程退出（阻塞调用，保证串行）
6. 冷却 10 秒（确保 git/index 异步操作完成）
7. 多重验证：章节文件 + 字数 ∈ `[MIN_WORDS, MAX_WORDS_HARD]`（默认 `[2200, 5000]`；低于下限走 1 轮补写重试，高于上限走 3 轮精简循环 `SHRINK_MAX_ROUNDS=3`）+ state 更新 + 摘要
8. 验证失败则用 ink-resume 重试一次
9. 仍失败则中止，输出详细错误报告
10. **检查点评估**：根据章节号触发审查/审计/宏观审查

### 错误处理

| 失败场景 | 处理方式 |
|----------|----------|
| 审查/审计/宏观审查失败 | 记录警告，继续写作（非阻断） |
| 大纲生成失败 | **中止批量写作**（唯一阻断性检查点失败） |
| 章节写作失败 | 重试一次，仍失败则中止 |

## 关键保证

- **与 /ink-write 完全等价**：每个 CLI 会话通过 Skill 工具正式加载 ink-write SKILL.md
- **严格串行**：上一章完成并验证通过后才开始下一章
- **多实例安全**：可同时在不同终端运行不同小说，互不干扰
- **优雅中断**：Ctrl+C 终止当前会话，已完成章节不回滚
- **智能检查点**：每5/10/20章自动质检，发现问题立即修复
- **自动规划**：大纲缺失时自动生成，无需手动介入
- **异常必报告**：任何失败都输出详细诊断信息到终端和日志

## 环境变量（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `INK_AUTO_COOLDOWN` | 章节间冷却秒数 | 10 |
| `INK_AUTO_CHECKPOINT_COOLDOWN` | 检查点操作间冷却秒数 | 15 |

## 支持平台

自动检测 PATH 中可用的 CLI 工具：

| 平台 | 调用方式 |
|------|----------|
| Claude Code | `claude -p` + `--permission-mode bypassPermissions` |
| Gemini CLI | `gemini --yolo` |
| Codex CLI | `codex --approval-mode full-auto` |

## 运行报告

每次执行 `/ink-auto` 完成（或中断）后，自动在 `.ink/reports/` 目录生成一份 Markdown 运行报告：

```
{PROJECT_ROOT}/.ink/reports/auto-{timestamp}.md
```

报告内容：
- **基本信息**：开始/结束时间、总耗时、计划/完成章数、终止原因
- **统计摘要**：写作/审查/修复/审计/宏观审查/自动规划各执行几次
- **执行时间线**：每个事件的时间戳、状态、描述——完整还原执行过程

适用场景：晚上 `/ink-auto 30` 后睡觉，早上看报告即知全部执行情况。

## 日志

所有操作的详细日志保存在：
```
{PROJECT_ROOT}/.ink/logs/auto/
  ch{NNNN}-{timestamp}.log          # 章节写作日志
  review-ch{start}-{end}-{ts}.log   # 审查日志
  fix-{type}-{ts}.log               # 自动修复日志
  audit-{depth}-{ts}.log            # 审计日志
  macro-{tier}-{ts}.log             # 宏观审查日志
  plan-vol{N}-{ts}.log              # 大纲生成日志
```

## 完成报告

批量写作完成后输出统计摘要：
```
═══════════════════════════════════════
  ink-auto 完成报告
═══════════════════════════════════════
  📝 写作：10 章
  🔍 审查：2 次（含自动修复 1 次）
  📊 审计：1 次
  🔭 宏观审查：0 次
  📋 自动规划：1 卷
  📂 日志：.ink/logs/auto
═══════════════════════════════════════
```

## Debug Mode 集成

> 详见：`docs/superpowers/specs/2026-04-28-debug-mode-design.md`、`docs/USER_MANUAL_DEBUG.md`

**每章收尾**（写完一章/跑完一章流程后，紧接下一章前），运行 auto_step_skipped invariant 检查本章实际跑过的 step 序列是否完整：

```bash
python3 -c "
from pathlib import Path
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.auto_step_skipped import check as check_steps
from ink_writer.debug.collector import Collector
import os, sqlite3

project_root = Path(os.environ['PROJECT_ROOT'])
run_id = os.environ['INK_AUTO_RUN_ID']
chapter = int(os.environ['CHAPTER'])
cfg = load_config(global_yaml_path=Path('config/debug.yaml'), project_root=project_root)

# 从 events.jsonl 已索引到的 incidents 中聚合本章+本批已触发的 step 序列。
db = cfg.base_path() / 'debug.db'
actual_steps = []
if db.exists():
    conn = sqlite3.connect(db)
    actual_steps = [r[0] for r in conn.execute(
        \"SELECT DISTINCT step FROM incidents WHERE run_id=? AND chapter=? AND step IS NOT NULL\",
        (run_id, chapter),
    )]
    conn.close()
expected = (cfg.invariants.get('auto_step_skipped', {})
            .get('expected_steps', {}).get('ink-auto', []))
inc = check_steps(actual_steps=actual_steps, expected_steps=expected,
                  run_id=run_id, chapter=chapter)
if inc is not None:
    Collector(cfg).record(inc)
"
```

**每批次收尾**（一次 /ink-auto 调用结束）调用 alerter 生成批次报告：

```bash
python3 -c "
from pathlib import Path
from ink_writer.debug.config import load_config
from ink_writer.debug.alerter import Alerter
import os
project_root = Path(os.environ['PROJECT_ROOT'])
run_id = os.environ['INK_AUTO_RUN_ID']
cfg = load_config(global_yaml_path=Path('config/debug.yaml'), project_root=project_root)
Alerter(cfg).batch_report(run_id=run_id)
"
```

环境变量需求：`PROJECT_ROOT` / `INK_AUTO_RUN_ID` / `CHAPTER`。
集成由 ink-auto 编排逻辑负责注入；当未设置或 master_enabled=false 时这两段命令都会 no-op（`load_config` / `batch_report` 内部已 fail-soft）。
