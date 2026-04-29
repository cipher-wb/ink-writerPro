# Ink Writer 软件运作逻辑——给小白的 5 分钟讲解

> 写给作者本人 cipher 的速查版。事实底座：`docs/analysis/00-codemap.md` + `01-modes/*.md` + 源码逐行核对。
> 写作日期：2026-04-29。

---

## 一句话定位

这套软件本质是一个 **"挂着让 AI 自动写网文"的脚手架**。核心价值不是 AI 模型本身，而是**一大堆硬规则**：

- 不让 AI 写出 AI 味（反检测：标点零容忍、装逼词黑名单、句式多样性）
- 不让 AI 跑题（每章 5 个 checker 把关，不过就重写）
- 不让 AI 偷懒（章节字数 / 钩子密度 / 主角能动性都有阈值）
- 不让设定漂移（实体管理、伏笔追踪、明暗线追踪）

AI 是引擎，软件是缰绳。

---

## 用户视角的命令分层

### 你日常真正会用的（5 个）

| 命令 | 干啥 | 何时用 |
|---|---|---|
| `/ink-init` 或 `/ink-init --quick 2` | 开新书：3 套方案选 1，落盘项目骨架 | 开新书第 1 步 |
| `/ink-plan 1` | 为第 1 卷生成完整大纲（节拍/时间线/章纲） | init 完成后 |
| `/ink-auto 10` | 批量写 10 章 + 每 5/10/20 章自动审查 | 日常主力 |
| `/ink-resume` | 上次挂了/Ctrl+C → 接着干 | 中断后 |
| `/ink-resolve` | 实体识别歧义堆积警告 → 人工裁决 | 看到 ⚠️ 时 |

### 你日常不必碰的工具命令（12 个）

- 维护类：`/ink-review`（手动审章）、`/ink-fix`（手动修章）、`/ink-audit`（10 章一次的审计，ink-auto 自动调）、`/ink-macro-review`（20 章一次的宏观审查，ink-auto 自动调）、`/ink-migrate`（旧项目迁移）
- 学习类：`/ink-learn`（把失败案例沉淀成规则）、`/ink-query`（查 RAG 知识库）
- 观测类：`/ink-dashboard`（启 web UI）、`/ink-debug-toggle/status/report`（debug 模式控制）

---

## 数据流（5 层，全程在小说项目目录里）

```
你的输入                  AI 加工产物              落盘到哪
═══════════════════════════════════════════════════════════════════
蓝本.md 或 7 题问答  →   3 套差异化方案     →   .ink/state.json + 设定集 6 文件
                  ↓                                     ↓
              选 1 套，敲定                       总纲.md + 主角卡.md + 金手指.md ...
                  ↓                                     ↓
                  ↓     →    第 1 卷节拍/时间线   →   大纲/第N卷-*.md
                  ↓                                     ↓
                  ↓     →    每章正文 + 摘要      →   正文/第N章.md + .ink/summaries/
                  ↓                                     ↓
                  ↓     →    各种 checker 报告    →   reports/auto-<时间戳>.md
```

### checker 闸门分布

- **ink-init 后**（4 个）：题材新颖度 / 金手指规格 / 起名风格 / 主角动机
- **ink-plan 后**（3 个）：金手指出场时机 / 主角能动性骨架 / 章节钩子密度
- **每章 polish 后**（5 个）：直白模式 / 反 AI 味 / 句式多样性 / 白话度 / 7 维度直度
- 不过 → Hard Block Rewrite Mode 重写 → 反复直到通过

---

## v27 的"梦想形态"= 你想要的"纯 /ink-auto"

设计文档里早已规划：

```
空目录里只放 1 份"蓝本.md" → /ink-auto 10 → 自动初始化 + 自动 plan + 写 10 章
```

或者**完全空目录**：自动启动 7 题快速问答 → 落盘蓝本 → 自动 init+plan+写。

代码也写了 → 见 `ink-writer/scripts/ink-auto.sh:826-941`，3 个开关全默认打开（`INK_AUTO_INIT_ENABLED` / `INK_AUTO_BLUEPRINT_ENABLED` / `INK_AUTO_INTERACTIVE_BOOTSTRAP_ENABLED`）。

**但有 bug 卡死了这条路径**——见下文。

---

## 失败兜底设计（3 层）

| 层 | 触发 | 行为 |
|---|---|---|
| 章节级 | 单章写得太短 / checker 不过 | 自动重试 1-3 次（不同 prompt 微调） |
| 批次级 | Ctrl+C / 进程崩溃 / 大纲生成失败 | 状态留在 `.ink/workflow_state.json`，`/ink-resume` 接着干 |
| 文件级 | 重写前先备份 | `.ink/recovery_backups/` 留旧版本 |

⚠️ **R1 bug 绕过了所有兜底**——因为它在 init 完成后、主循环之前的"自动 plan"环节炸的，根本没进重试逻辑。

---

## 已确认的核心 bug

### R1：`auto_plan_volume` 未定义函数

`ink-auto.sh` 在 line 535 和 line 933 调用 `auto_plan_volume`，但**全项目找不到这个函数定义**。

**症状**：
- 走 v27 路径（你想要的纯 `/ink-auto`）：init 跑完 → `auto_plan_volume` 报 command not found → `set -e` 退出 1 → 屏幕显示 `❌ 第N卷大纲生成失败`，根因不可见
- 走 quick mode S1 状态（已 init 没写过章）：同样撞墙

**修复方向**：
- 选项 A（短期）：把 `auto_plan_volume "$_vol" "$BATCH_START"` 改成调用 `claude -p` 子进程跑 `/ink-plan $_vol`
- 选项 B（中期）：实现 `auto_plan_volume` shell 函数，里面真的调 plan skill
- 选项 C（长期）：把 init/plan/auto 全部的子进程编排都迁到 ink-auto.sh 的同一套 `run_cli_process` 框架

### R3：`local _vol` 用在非函数体

ink-auto.sh:931 在 `if [[ -z "$PROJECT_ROOT" ]]` 块里用 `local _vol`，bash 会报 `local: can only be used in a function`。`set -e` 让它直接退出。

**修复**：把 `local _vol` 改成 `_vol=` 或者把 v27 块整体包进函数。

---

## 仓库地图（按你日常会接触的频次排）

```
ink-writer/                          ← 你 cd 进去的小说项目目录（你创建的）
├── 蓝本.md                          ← 你写的 1 份输入
├── .ink/                            ← 软件内部状态（自动维护，不用动）
│   ├── state.json                   ← 总状态：当前章/卷/进度/preferences
│   ├── workflow_state.json          ← 当前任务的 step-by-step 状态机
│   ├── summaries/                   ← 每章 ≤500 字摘要（用于跨章上下文）
│   ├── index.db                     ← SQLite 实体/伏笔/明暗线索引
│   └── recovery_backups/            ← 重写前的备份
├── 设定集/                          ← 6 个 md，世界观/主角/金手指/反派/...
├── 大纲/                            ← 总纲 + 卷节拍/时间线/章纲
├── 正文/                            ← 第N章.md（最终交付物）
└── reports/                         ← auto-<时间戳>.md 运行报告
```

软件本身在另一个目录（你正在看的 `/Users/cipher/AI/小说/ink/ink-writer/`），**它不应该被放进你的小说项目目录**。

---

## 给"看不清楚"的应急口令

任何时候你想知道"现在啥状态"，3 条命令：

```bash
# 1. 当前在哪一章/卷
cd <你的小说项目目录>
python -m ink_writer.core.cli.ink state

# 2. 上次跑到哪一步（含中断信息）
python -m ink_writer.core.cli.ink workflow detect

# 3. 最近一次审查报告
ls -lt reports/ | head -5
cat reports/<最新一份>.md
```

如果 `state` 报错说"未找到 .ink/state.json"——意味着这个目录**还没初始化**，需要 `/ink-init` 或者放蓝本.md 跑 v27（修了 R1 之后）。
