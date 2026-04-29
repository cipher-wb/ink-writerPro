# 阶段 3C：端到端场景清单

> 本文件为自然语言场景，不包含代码。  
> 优先级：P0 = 核心成功路径；P1 = 常见次要路径；P2 = 增强体验路径。  
> 执行状态：本阶段仅编写场景，未执行测试。

| # | 场景描述 | 前置条件 | 操作步骤 | 预期结果 | 关联模式 | 优先级(P0/P1/P2) |
|---:|---|---|---|---|---|---|
| 1 | 新手用 Quick 从零开书并写首批章节 | 空目录，插件已安装，用户接受 Quick 方案 | 执行 `/ink-init --quick`，选择方案 1；执行 `/ink-plan`；执行 `/ink-auto 5` | 项目结构、设定集、大纲、正文、审查报告陆续生成；每章通过 verify 后推进状态 | Quick Mode / Daily Workflow | P0 |
| 2 | Quick 使用用户蓝本跳过方案选择 | 空目录已有一份完整蓝本 md | 执行 `/ink-init --quick --blueprint <蓝本.md>` | 蓝本转换为 quick draft；跳过平台/激进度询问和方案三选一；项目在当前目录初始化 | Quick Mode / v27 Bootstrap | P1 |
| 3 | Deep 模式完整交互后初始化项目 | 用户希望强控制书名、主角、金手指、世界观 | 执行 `/ink-init`；逐步回答 6 段问题；最终确认 | 结构化参数传给 `ink.py init`；生成与 Quick 等价的项目骨架，但语义来自用户回答 | Deep Mode | P0 |
| 4 | Deep 充分性闸门拦截信息不足 | 用户在主角欲望、金手指代价等字段回答过短 | 执行 `/ink-init` 并给出含糊回答 | LLM 按 Deep 充分性闸门继续追问，不应写入半成品项目 | Deep Mode | P1 |
| 5 | 日常工作流连续产出 5 章并触发审查 | 项目已 init 且有第 1 卷章纲 | 执行 `/ink-auto 5` | 每章依次 context/write/check/polish/verify；第 5 章后触发 review+fix 检查点 | Daily Workflow / Auto Checkpoint | P0 |
| 6 | `/ink-resume` 恢复 Ctrl+C 中断任务 | `/ink-auto` 在第 12 章写作中断，`.ink/workflow_state.json.current_task` 存在 | 执行 `/ink-resume` | 从可恢复步骤继续或给出明确失败原因；不重复覆盖已完成章节 | Daily Workflow | P0 |
| 7 | 消歧积压在 20 章检查点被提醒 | `.ink/state.json` 中 `disambiguation_pending` 超过 20 | 写到第 20 章后进入 checkpoint，或执行 `ink.py disambig-check` | 输出 warning/critical 等级；不阻断写作，但提示需要 `/ink-resolve` | Daily Workflow / Auto Checkpoint | P1 |
| 8 | Debug 状态、报告、开关三条命令可用 | 项目已有 `.ink-debug/events.jsonl` | 执行 `/ink-debug-status`、`/ink-debug-report --since 1d --severity warn`、`/ink-debug-toggle layer_c off` | status 展示 24h 摘要；report 生成 markdown；toggle 写项目级 override | Debug Mode | P0 |
| 9 | Debug invariant 捕获 writer 字数过短 | Debug master 与 layer C 开启，写章结果低于平台硬下限 | 跑一次写章链路或直接触发 invariant 采集 | `.ink-debug/events.jsonl` 记录 `writer.short_word_count`；warn+ 进入 SQLite | Debug Mode | P1 |
| 10 | macOS 中文与空格路径下 CLI 可解析项目根 | macOS，项目路径含中文和空格 | 执行 `python ink-writer/scripts/ink.py --project-root "<中文 空格路径>" where` | 输出 resolve 后项目路径；不因 shell quoting 或 UTF-8 失败 | Cross-Platform Mode | P0 |
| 11 | Windows PowerShell sibling 与 bash sibling 行为一致 | Windows 环境或 CI 模拟，插件目录存在 `.ps1` sibling | 分别执行 PowerShell 入口与 bash 等价入口 | 两者传参、编码、退出码与文件产出一致 | Cross-Platform Mode | P1 |
| 12 | Claude Code 插件安装后 slash command 可见 | 用户用 Claude Code marketplace 安装插件 | 执行安装命令后重启/刷新 Claude Code；输入 `/ink-auto` | slash command 可见，脚本路径解析到插件内 `scripts` | External Environments | P0 |
| 13 | Gemini CLI extension 安装后能调用相同脚本 | 用户使用 Gemini CLI 安装 extension | 执行 Gemini extension 安装；触发 ink 相关命令 | extension 能定位脚本与数据目录；路径兼容 macOS/Linux | External Environments | P1 |
| 14 | Codex CLI symlink 安装后不丢资源文件 | `~/.codex/ink-writer` 指向项目或插件目录 | 执行 Codex CLI 下的 ink 命令 | symlink 解析后仍能找到 skills、scripts、data、templates | External Environments | P1 |
| 15 | v27 空目录放一份蓝本后 `/ink-auto` 自动初始化 | 空目录只有一份非黑名单蓝本 md | 执行 `/ink-auto 5` | 自动扫描蓝本、转换 quick draft、子进程跑 Quick init；完成后尝试 plan/auto | v27 Bootstrap Mode | P0 |
| 16 | v27 完全空目录进入 7 题交互 bootstrap | 空目录无 md 或只有 README/AGENTS/`.draft.md` | 执行 `/ink-auto 5`，回答 7 个问题 | 写出 `.ink-auto-blueprint.md`；继续转换和 Quick init | v27 Bootstrap Mode | P1 |
| 17 | 第 20 章检查点输出标准审计和 Tier2 | 项目已写到第 19 章且第 20 章 verify 通过 | 完成第 20 章或执行 `ink.py checkpoint-level --chapter 20` | checkpoint JSON/流程包含 review、standard audit、Tier2、消歧检查 | Auto Checkpoint Internals | P0 |
| 18 | 已完结项目再次 `/ink-auto` 不继续写新章 | `.ink/state.json.progress.is_completed=true` | 执行 `/ink-auto 5` | 状态检测为 completed；提示已完结或安全退出，不生成新正文 | Daily Workflow / v27 State Detector | P1 |
| 19 | 损坏的 `.ink/state.json` 不造成崩溃级联 | 项目目录存在坏 JSON 的 `.ink/state.json` | 执行状态检测、`where`、checkpoint 辅助命令 | fail-soft 回到未初始化/无积压等安全值；给出可诊断提示 | Quick / Daily / Auto Checkpoint | P1 |
| 20 | 书名、角色名、路径包含中英混排与 Emoji | 项目标题和主角名包含中文、英文、空格、Emoji | 执行 init、plan、where、debug report | 文件名与 JSON/Markdown UTF-8 正常；CLI 输出不乱码；必要时清理非法文件名字符 | Cross-Platform / Quick / Debug | P1 |

## 阶段 0/1 报告勘误

无。
