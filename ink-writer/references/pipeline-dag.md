---
name: pipeline-dag
description: ink-write 9步写作流水线的步骤依赖关系图（DAG），定义硬门控和续跑规则
---

# ink-write 流水线步骤依赖关系图 (DAG)

> 本文件为 `ink-write/SKILL.md` 中 Step 前置验证协议的形式化表达。每个步骤启动前必须验证前置步骤已完成。

## DAG 总览

```
Step 0（环境验证）
  │
  ├── Step 0.5（工作流初始化）
  │     │
  │     ├── Step 0.6（Context Contract 全量包，按需）
  │     │     │
  │     │     ├── Step 0.7（金丝雀健康扫描）
  │     │     │     │
  │     │     │     └── Step 0.8（设定权限校验）
  │     │     │           │
  │     │     │           └── Step 1（上下文构建）────── ★ context-agent
  │     │     │                 │
  │     │     │                 └── Step 2A（正文起草）── ★ writer-agent
  │     │     │                       │
  │     │     │                       └── Step 2A.5（字数校验）── ⛔ 硬门控
  │     │     │                             │
  │     │     │                             └── Step 2B（风格适配）── 内联执行
  │     │     │                                   │
  │     │     │                                   └── Step 3（多Agent审查）── ★ 10 checkers
  │     │     │                                         │
  │     │     │                                         └── Step 4（润色）── ★ polish-agent
  │     │     │                                               │
  │     │     │                                               └── Step 4.5（改写安全校验）── ⛔ 硬门控
  │     │     │                                                     │
  │     │     │                                                     └── Step 5（数据回写）── ★ data-agent
  │     │     │                                                           │
  │     │     │                                                           └── Step 6（Git 备份）
```

## 硬门控（Hard Gate）

以下步骤转换包含硬性阻断条件：

| 转换 | 阻断条件 | 阻断行为 |
|------|----------|---------|
| → Step 2A.5 | 草稿未生成或文件不存在 | 阻断，报错 |
| Step 2A.5 → Step 2B | 字数 < 2200 | 阻断，回到 Step 2A 补写（最多2轮） |
| Step 3 → Step 4 | `save-review-metrics` 未成功 | 阻断，必须先落库 |
| Step 3 → Step 4 | 存在 TIMELINE_ISSUE severity ≥ high | 阻断，必须先修复 |
| Step 3 → Step 5 | chapter ≤ 3 且 golden-three-checker.pass = false | 阻断，必须先回 Step 4 修复 |
| Step 4.5 → Step 5 | 发现 critical 违规（剧情事实变更/设定违规/大纲偏离） | 恢复快照段落，最多1轮修正 |
| Step 4 → Step 5 | `anti_ai_force_check = fail`（2轮后仍fail） | 记录问题清单，由用户决定 |

## 并步检测

- 若 `workflow_state.json` 中存在 `status: "in_progress"` 的 Step 且不是当前 Step → **阻断**
- 输出错误：`"❌ 检测到 Step {X} 仍在执行中，禁止并行启动 Step {Y}"`

## 续跑映射

当通过 `/ink-resume` 续跑时，按 `current_step.id` 定位：

| current_step | 续跑行为 | 禁止操作 |
|-------------|---------|---------|
| Step 1 | 完成执行包构建，进入 Step 2A | — |
| Step 2A | 继续/重写正文 | 不得重复 Step 1 |
| Step 2B | 继续风格适配 | 不得跳去 Step 4/5 |
| Step 3 | 完成审查、汇总、落库 | — |
| Step 4 | 基于现有审查结论润色 | — |
| Step 5 | 重跑 Data Agent | Step 1-4 视为已通过 |
| Step 6 | Git 备份与收尾 | — |

## 步骤-Agent 映射

| 步骤 | 执行者 | 调用方式 |
|------|--------|---------|
| Step 0-0.8 | 主流程 | 内联（Bash 命令） |
| Step 1 | context-agent | 脚本优先，Agent 兜底 |
| Step 2A | writer-agent | 主流程内联执行 |
| Step 2A.5 | 主流程 | 内联（字数检测） |
| Step 2B | 主流程 | 内联（加载 style-adapter.md） |
| Step 3 | 10 checker agents | Task 调用（max 并发 2） |
| Step 4 | polish-agent | 主流程内联执行 |
| Step 4.5 | 主流程 | 内联（diff 校验） |
| Step 5 | data-agent | Task 调用 |
| Step 6 | 主流程 | 内联（Git 命令） |
