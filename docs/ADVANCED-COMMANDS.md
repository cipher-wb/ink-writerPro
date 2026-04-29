# 高级命令参考

> 本文档收纳 12 个**日常不必用**的工具命令。日常写作只需 5 个核心命令（见 [HOW-IT-WORKS-FOR-CIPHER.md](HOW-IT-WORKS-FOR-CIPHER.md)）。
> 本文档面向：开发者、出问题排查、高级定制。

## 命令分层

```
日常 5 个（必学）
├── /ink-init              开新书
├── /ink-init --quick      快速开新书（3 套方案选 1）
├── /ink-plan              生成卷大纲
├── /ink-auto N            批量写 N 章 ★主力
├── /ink-resume            中断后续写
└── /ink-resolve           处理消歧积压

高级 12 个（出问题 / 想定制时再看）
├── 写作类
│   ├── /ink-write         手动写单章（ink-auto 内部用）
│   ├── /ink-review        手动审章（ink-auto 自动每 5 章触发）
│   └── /ink-fix           手动修章
├── 数据/学习类
│   ├── /ink-audit         数据审计（ink-auto 自动每 10 章触发）
│   ├── /ink-macro-review  宏观审查（ink-auto 自动每 20 章触发）
│   ├── /ink-learn         失败案例 → 规则沉淀
│   └── /ink-query         查 RAG 知识库
├── 维护类
│   └── /ink-migrate       老项目迁移到新版本
└── Debug/观测类
    ├── /ink-debug-toggle  开关 debug 模式
    ├── /ink-debug-status  查 debug 状态
    ├── /ink-debug-report  生成 debug 报告
    └── /ink-dashboard     启 Web UI 看实时数据
```

---

## 写作类

### `/ink-write`

手动写单章。**通常你不需要直接调用**——`/ink-auto N` 内部就是循环调它 N 次。

什么时候你想手动调：
- 想看单章完整流程的输出
- 调试某一章的某个 step 出问题
- 用 `--batch N` 在前台跑一小批不让 ink-auto 接管

### `/ink-review`

手动审章。`/ink-auto` 自动每 5 章触发一次，所以你**几乎不需要**手动调。

手动调的场景：
- 怀疑某章质量但 ink-auto 没报错 → 单独 review
- 想用更严格的模式审查（指定 `--mode strict`）

### `/ink-fix`

手动修章。`/ink-review` 发现问题后，`/ink-fix` 按报告修。

`/ink-auto` 的"每 5 章 review+fix"自动触发了——你**几乎不需要**手动调。

---

## 数据/学习类

### `/ink-audit`

数据审计。检查 `.ink/index.db` 和 state.json 是否一致、伏笔是否漂移、实体识别是否有漏洞。

`/ink-auto` 每 10 章自动触发 quick mode（轻量），每 20 章自动触发 standard mode（含 Tier 2 宏观）。

### `/ink-macro-review`

宏观审查。看整体节奏、追读力、人物弧线趋势。`/ink-auto` 每 20 章自动触发。

### `/ink-learn`

把"AI 失败案例"沉淀成新规则。流程：
1. 跑一段时间后 `.ink/observability/call_trace.jsonl` 攒了一堆失败事件
2. `/ink-learn` 把它们 LLM 提取成 rule candidate
3. 你审核 → 进 `data/editor-wisdom/rules.json`

**新人 0-100 章不需要碰**。等你写完一卷再说。

### `/ink-query`

查 RAG 知识库。直接问"这个金手指有什么爆款例子"等问题，从 editor-wisdom + live-review 两个 RAG 库检索答案。

---

## 维护类

### `/ink-migrate`

老项目迁移工具。如果你有 v22 之前版本的项目，运行 `/ink-migrate` 自动升级 schema。

**新建项目用不到**。

---

## Debug/观测类

> 这 4 个命令默认开启，零侵入。Debug Mode 把每一步异常事件写到 `<project>/.ink-debug/` 下（JSONL + SQLite 双层）。

### `/ink-debug-toggle`

打开/关闭 debug 模式。env var 等价：`INK_DEBUG_OFF=1` 关。

### `/ink-debug-status`

看当前 debug 模式状态、累计事件数、最新事件类型。

### `/ink-debug-report`

生成 debug 报告（双视图 markdown）。喂给 AI 改 SKILL.md 用——闭环改进。

详见 [docs/USER_MANUAL_DEBUG.md](USER_MANUAL_DEBUG.md)。

### `/ink-dashboard`

启动 Web UI 看实时数据（`http://localhost:8080`）。看 chapter 字数趋势、checker 评分分布、API 调用耗时等图表。

**如果你只用终端不需要 UI**，这个永远不开就行。

---

## 环境变量参考

跑 `/ink-auto` 时可临时调整行为：

| 变量 | 默认 | 作用 |
|---|---|---|
| `INK_AUTO_REVIEW_CONCURRENCY` | 8 | Step 3 审查并发数；遇 API 限流降到 4 或 2 |
| `INK_AUTO_FAST_REVIEW` | 0 | 1 = 跳过 6 个条件 checker（黄金三章自动保护） |
| `INK_AUTO_CHAPTER_TIMEOUT` | 3600 | 单章超时（秒） |
| `INK_AUTO_PLAN_TIMEOUT` | 3600 | 单卷大纲超时（秒） |
| `INK_AUTO_INIT_TIMEOUT` | 1800 | 自动初始化超时（秒） |
| `INK_AUTO_STALL_THRESHOLD` | 0 | 0=关闭主动 SIGTERM；>0 时三信号无变化超过 N 秒提前终止 |
| `INK_AUTO_HEARTBEAT_INTERVAL` | 30 | 心跳间隔（秒） |
| `INK_AUTO_INIT_ENABLED` | 1 | 0 = 关闭 v27 空目录自动 init |
| `INK_AUTO_FAST_REVIEW` | 0 | 1 = 第 4 章及之后启用快速审查 |
| `INK_AUTO_QUIET_LINEBUF` | 0 | 1 = 静默"未检测到 stdbuf"启动提示 |
| `INK_DEBUG_OFF` | 0 | 1 = 关闭 Debug Mode |

例：

```bash
# 跑 5 章，审查并发降到 4 防限流
INK_AUTO_REVIEW_CONCURRENCY=4 /ink-writer:ink-auto 5

# 第 4 章后用快速审查（前 3 章保留完整审查）
INK_AUTO_FAST_REVIEW=1 /ink-writer:ink-auto 10

# 单章超时设 90 分钟（极慢的 LLM）
INK_AUTO_CHAPTER_TIMEOUT=5400 /ink-writer:ink-auto 5
```

---

## 排查路径

| 症状 | 看哪 |
|---|---|
| 启动报"未检测到已初始化项目"但项目其实有 | `find_project_root` 解析问题，参考 [HOW-IT-WORKS-FOR-CIPHER.md](HOW-IT-WORKS-FOR-CIPHER.md) |
| Embedding API 返回空 | [SETUP-EMBEDDING-API-FOR-CIPHER.md](SETUP-EMBEDDING-API-FOR-CIPHER.md) |
| Step 3 25-30 分钟没动 | LLM 调 sub-agent 的常态，不是卡住，watchdog 60min 兜底 |
| 章节文件 < 2200 字（番茄 < 1500）| 自动归档到 `.ink/recovery_backups/partial_chapters/`，重跑会从该章接着写 |
| `/ink-auto` 输出心跳但没看到 step 进度 | 装 `brew install coreutils` 拿 `gstdbuf` 拿到行缓冲 |
| 想看实时进度细节 | 装 coreutils + 看 `.ink/logs/auto/ch*.log` |

---

## 想了解更深层

| 主题 | 文档 |
|---|---|
| 软件 5 分钟入门 | [HOW-IT-WORKS-FOR-CIPHER.md](HOW-IT-WORKS-FOR-CIPHER.md) |
| API 配置 | [SETUP-EMBEDDING-API-FOR-CIPHER.md](SETUP-EMBEDDING-API-FOR-CIPHER.md) |
| 整体架构 | [architecture.md](architecture.md) |
| 数据流 | [agent_topology_v13.md](agent_topology_v13.md) |
| RAG 配置 | [rag-and-config.md](rag-and-config.md) |
| 用户手册（完整）| [USER_MANUAL.md](USER_MANUAL.md) |
| Debug 模式 | [USER_MANUAL_DEBUG.md](USER_MANUAL_DEBUG.md) |
| Windows 故障速查 | [windows-troubleshooting.md](windows-troubleshooting.md) |
| Editor-Wisdom 集成 | [editor-wisdom-integration.md](editor-wisdom-integration.md) |
| Live-Review 集成 | [live-review-integration.md](live-review-integration.md) |
| Prose Anti-AI 改造 | [prose-anti-ai-overhaul.md](prose-anti-ai-overhaul.md) |
