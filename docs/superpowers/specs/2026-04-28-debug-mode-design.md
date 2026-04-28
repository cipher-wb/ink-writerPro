# Debug Mode 设计文档（v0.5 MVP）

**Status**: Draft
**Date**: 2026-04-28
**Owner**: cipher-wb
**Scope**: 新增"上帝视角观察 + 离线迭代修软件"的 debug 模式。在 ink-writer 全链路写作过程中，自动收集 AI 偷懒、契约脱节、工作流偏航、硬错误等事件，写入项目本地事件总线，定期产出 markdown 报告供人工 / 外接 Claude 分析，反向驱动 SKILL.md / checker / invariant 的迭代修复。

## 0. 目标 / 非目标

### 0.1 目标

主目标 = **形态②"修软件本身（离线迭代闭环）"**：

- 写作流程**不被打断**（除硬错误），事件只记录不拦截
- 通过结构化 incident bus 让"writer 本周第 14 次偷字数"这种**聚合信号**可见
- 输出标准化 markdown 报告，**直接喂外接 Claude 会话 / ultrareview 改 SKILL.md**

次目标：

- 形态①"运行时硬中断"：仅对 Python exception / 数据脏写等不可继续的硬错误，立即同步 stderr 红字提示
- 形态③"AI 元认知"：仅在 5 个**已知高频偷懒点**（writer 字数 / polish diff / review 维度 / context 必读 / auto 跳步）做轻量结构化判断，**不依赖 LLM 自报**

### 0.2 非目标（v0.5 不做）

- ❌ 自动改 SKILL.md / 自动开 PR（v1.0）
- ❌ LLM 对抗复核 agent（v1.0 layer D）
- ❌ 跨项目聚合脚本（v1.0）
- ❌ 周报 cron（v1.0，用户手动运行一行命令即可注册）
- ❌ 端到端运行时自愈（不在当前章节内 retry，避免 token 暴涨与状态污染）
- ❌ 全部 14+ checker 立即接入（v0.5 只接 5 个最常用：consistency / continuity / live-review / ooc / reader-simulator；其余渐进迁移）

## 1. 架构

### 1.1 三上游 + 一总线 + 多下游

```
 ┌───────────── 上游接入（写入侧） ─────────────┐
 │ A. Claude Code hooks                         │
 │    PreToolUse / PostToolUse / SubagentStop / │
 │    Stop / SessionEnd  →  hook_handler.py     │
 │                                              │
 │ B. 已有 checker agent（5 个）                │
 │    consistency / continuity / live-review /  │
 │    ooc / reader-simulator → checker_router   │
 │                                              │
 │ C. 5 个 invariant                            │
 │    writer 字数 / polish diff / review 维度 / │
 │    context 必读 / auto 跳步                  │
 └──────────────────┬───────────────────────────┘
                    │ 统一 incident schema
                    ▼
        ┌───────────────────────┐
        │  ink_debug.collector  │   ← 唯一写入入口
        └───────────┬───────────┘
                    │ severity routing
                    ▼
   ┌──────────────────────────────────────────┐
   │  events.jsonl (append-only, 真相源)      │
   └──────────────┬───────────────────────────┘
                  │ indexer (异步增量)
                  ▼
   ┌──────────────────────────────────────────┐
   │  debug.db (SQLite, 查询面)               │
   └──────────────┬───────────────────────────┘
                  │
 ┌────────────────┼─────────────────────────────┐
 │  下游消费                                    │
 │  • alerter   → /ink-write 收尾摘要           │
 │              → /ink-auto 批次自动报告        │
 │  • reporter  → /ink-debug-report (md)        │
 │  • cli       → /ink-debug-status / toggle    │
 │  • E（兜底） → 你拷贝 markdown 给外接 Claude │
 └──────────────────────────────────────────────┘
```

### 1.2 组件清单

| 模块 | 路径 | 职责 |
|---|---|---|
| `collector` | `ink_writer/debug/collector.py` | 唯一写入入口；master switch / severity 路由 / 异常吞掉不传染主流程 |
| `schema` | `ink_writer/debug/schema.py` | incident dataclass + JSON 序列化 + kind 命名校验 |
| `hooks_adapter` | `scripts/debug/hook_handler.py` + `.claude/settings.json` | Claude Code hooks → collector |
| `checker_router` | `ink_writer/debug/checker_router.py` | 把 5 个 checker 的 JSON 输出转 incident schema |
| `invariants/*` | `ink_writer/debug/invariants/*.py` | 5 个独立检测函数 |
| `indexer` | `ink_writer/debug/indexer.py` | 增量从 JSONL 同步到 SQLite |
| `reporter` | `ink_writer/debug/reporter.py` | SQLite → 双视图 markdown |
| `alerter` | `ink_writer/debug/alerter.py` | /ink-write 收尾摘要 + /ink-auto 批次触发 reporter |
| `cli` | `ink_writer/debug/cli.py` | `status` / `report` / `toggle` 入口 |
| `config` | `config/debug.yaml` + `<project>/.ink-debug/config.local.yaml` | 4 子开关 + severity 阈值 + 路径配置 |

### 1.3 数据流

**写入路径**（同步关键路径，单事件目标 < 5ms）：
源 → `collector.record(incident)` → 立即 append 到 events.jsonl → 立即 return；severity≥error 时**额外同步**到 stderr。

**索引路径**（异步，不阻塞写入）：
indexer 在每次 `/ink-write` / `/ink-auto` 收尾被 alerter 触发一次，把 watermark 之后的 JSONL 增量写入 SQLite。失败不阻塞主流程，下次重试。

**读取路径**：
`/ink-debug-status` / `/ink-debug-report` 只读 SQLite。如果 SQLite 落后，先触发一次 indexer 再查。

## 2. 检测层

### 2.1 Layer A：Claude Code hooks（外部黑盒观察）

注册 5 个 hook：`PreToolUse` / `PostToolUse` / `SubagentStop` / `Stop` / `SessionEnd`。

每个 hook 通过 `scripts/debug/hook_handler.py` 调 `collector.record(...)`：

- `PreToolUse` → severity=info，kind=`hook.pre_tool_use`，evidence={tool_name, args_summary}
- `PostToolUse` → severity=info（成功）/ warn（exit_code≠0）/ error（exception），kind=`hook.post_tool_use`，evidence={tool_name, duration_ms, exit_code, stderr_tail}
- `SubagentStop` → severity=warn，kind=`hook.subagent_stop`，evidence={agent_name, reason}
- `Stop` / `SessionEnd` → severity=info，触发 indexer + alerter

**不修改任何 skill 文件**。零侵入。

### 2.2 Layer B：已有 checker 输出标准化

5 个 checker（consistency / continuity / live-review / ooc / reader-simulator）的现有 JSON 报告路径不变；`checker_router.py` 提供 `route(checker_name, report_dict, run_context)` 函数，转成 incident records 落总线。

**接入方式**：在调用 checker 的位置（writer-agent / polish-agent / ink-review skill）末尾加一行 `checker_router.route(...)`。**不改 checker 自身。**

每条 violation → 一条 incident，severity 取 checker 报告里的字段（red→error / yellow→warn / green→info）。

### 2.3 Layer C：5 个 invariant

| invariant | 检测时机 | 命中条件 | severity | kind |
|---|---|---|---|---|
| `writer_word_count` | writer-agent 输出后 | `len(text) < platform_min_words` | warn | `writer.short_word_count` |
| `polish_diff` | polish-agent 前后 | `levenshtein_distance(before, after) < min_diff_chars` (默认 50)；用 `difflib.SequenceMatcher` 即可，不需要额外依赖 | warn | `polish.diff_too_small` |
| `review_dimensions` | review 报告生成后 | `len(report.dimensions) < min_dimensions_per_skill[skill]` | warn | `review.missing_dimensions` |
| `context_required_files` | context-agent 完成后 | 必读列表中有未读到的 skill 文件 | warn | `context.missing_required_skill_file` |
| `auto_step_skipped` | /ink-auto 每章收尾 | 期望 step 序列里有未触发的 step | warn | `auto.skill_step_skipped` |

**实现细节**：

- `writer_word_count`：`platform_min_words` 复用 `ink_writer/core/preferences.py` 的 `load_word_limits(project_root)`；找不到 `state.json.platform` 时按现有代码 fallback 到 `qidian` (2200)。
- `polish_diff`：用 `difflib.SequenceMatcher(None, before, after).ratio()` 转换；近似改动字符数 = `(1-ratio) * max(len)`。`before` 取 polish 入口前的草稿、`after` 取出口后。两者由 polish-agent 的钩子记录。
- `context_required_files`：必读列表来自 skill 自身约定的 "Context Contract"（已存在概念，参考 `ink-writer/skills/ink-write/SKILL.md` 中 context-agent 的契约段落）。如果 skill 没显式声明必读列表，invariant fail-soft（只记 info，不记 warn）。
- `auto_step_skipped`：期望 step 序列从 `config.invariants.auto_step_skipped.expected_steps` 读取；实际 step 序列由 alerter 在 /ink-auto 每章收尾时从 `events.jsonl` 中按 `kind=hook.post_tool_use` + `skill=ink-auto` 聚合得出。

每个 invariant 是独立 Python 函数 `check(context) -> Optional[Incident]`，由 collector 在对应时机被各 agent 调用。**纯结构化判断，不依赖 LLM。**

### 2.4 Layer D（v0.5 不做，保留扩展位）

LLM 对抗复核 agent，在 `/ink-macro-review` 时机跑一次"上 50 章 writer/polish/review 各自的契约履行得怎么样"。schema 已预留 `source=layer_d_adversarial`，v1.0 直接开 config flag 即接入。

## 3. 事件总线

### 3.1 incident JSONL schema

每条事件一行 JSON，**严格字段顺序**（便于 grep / 肉眼扫）：

```jsonc
{
  "ts": "2026-04-28T14:23:51.123Z",        // 必备，ISO8601 UTC
  "run_id": "auto-2026-04-28-batch12",      // 必备，关联到一次 /ink-write or /ink-auto
  "session_id": "cc-abc123",                // 可选
  "project": "因果剑歌",                     // 取自 .ink-current-project，找不到则 cwd basename
  "chapter": 142,                           // 可选
  "source": "layer_b_checker",              // 必备：layer_a_hook | layer_b_checker | layer_c_invariant | layer_d_adversarial | meta
  "skill": "ink-write",                     // 必备
  "step": "polish",                         // 可选
  "kind": "polish.diff_too_small",          // 必备，<step|source>.<problem>，全 snake_case
  "severity": "warn",                       // 必备：info | warn | error
  "message": "polish 前后 diff 仅 32 字符 < 阈值 50",
  "evidence": { "diff_chars": 32, "threshold": 50 },
  "trace": { "file": "...", "line": 42 }
}
```

**v0.5 保留 kind 白名单**（任何写入必须命中其一，否则在 strict mode 下抛 `meta.unknown_kind` 自我事件）：

| kind | 来源 | 说明 |
|---|---|---|
| `writer.short_word_count` | layer_c | writer 输出字数低于平台 floor |
| `polish.diff_too_small` | layer_c | polish 前后改动过少 |
| `review.missing_dimensions` | layer_c | review 报告维度数不达标 |
| `context.missing_required_skill_file` | layer_c | context-agent 漏读必读文件 |
| `auto.skill_step_skipped` | layer_c | /ink-auto 中某 step 未触发 |
| `hook.pre_tool_use` / `hook.post_tool_use` / `hook.subagent_stop` | layer_a | Claude Code hooks |
| `checker.<name>.<problem>` | layer_b | 5 个 checker 的 violation（如 `checker.consistency.character_drift`）|
| `meta.invariant_crashed` | meta | invariant 自身崩溃 |
| `meta.unknown_kind` | meta | 写入了不在白名单的 kind |
| `meta.collector_error` | meta | collector 自身错误（写到 collector.error.log，不进 JSONL）|

### 3.2 SQLite schema（debug.db）

```sql
CREATE TABLE incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  run_id TEXT NOT NULL,
  session_id TEXT,
  project TEXT,
  chapter INTEGER,
  source TEXT NOT NULL,
  skill TEXT NOT NULL,
  step TEXT,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  evidence_json TEXT,
  trace_json TEXT
);
CREATE INDEX idx_ts ON incidents(ts);
CREATE INDEX idx_kind_sev ON incidents(kind, severity);
CREATE INDEX idx_run_skill ON incidents(run_id, skill);

CREATE TABLE indexer_watermark (
  jsonl_path TEXT PRIMARY KEY,
  last_byte_offset INTEGER NOT NULL,
  last_indexed_ts TEXT NOT NULL
);
```

**索引策略**：仅 `warn+` 进 SQLite（默认阈值），`info` 仅留在 JSONL（事后大量分析用 grep / `jq` 即可）。

## 4. 开关与配置

### 4.1 全局默认 `config/debug.yaml`（仓库内提交）

```yaml
master_enabled: true                    # 总开关，默认开

layers:
  layer_a_hooks: true
  layer_b_checker_router: true
  layer_c_invariants: true
  layer_d_adversarial: false            # v1.0 才开

severity:
  jsonl_threshold: info                 # info+ 落 JSONL
  sqlite_threshold: warn                # warn+ 进 SQLite
  alert_threshold: warn                 # warn+ 触发收尾摘要
  stderr_threshold: error               # error 立即 stderr 红字

storage:
  base_dir: ".ink-debug"
  events_max_mb: 100
  archive_keep: 5

alerts:
  per_chapter_summary: true
  per_batch_report: true
  warn_window_days: 7
  warn_window_threshold: 5

invariants:
  writer_word_count: { enabled: true }              # 阈值复用 platform_min_words
  polish_diff: { enabled: true, min_diff_chars: 50 }
  review_dimensions:
    enabled: true
    min_dimensions_per_skill: { ink-review: 7 }
  context_required_files: { enabled: true }
  auto_step_skipped:
    enabled: true
    expected_steps:
      ink-auto: [context, draft, review, polish, extract, audit]

strict_mode: false                      # true 时未知 kind 抛 meta.unknown_kind 自我事件
```

### 4.2 项目级覆盖

`<project>/.ink-debug/config.local.yaml` 只列要改的字段，与全局配置**深合并**（dict 合并，list 完整覆盖）。

### 4.3 紧急关闭

环境变量 `INK_DEBUG_OFF=1`，优先级高于 yaml 任意配置；collector 入口第一行检查，命中立即 return。**不必改 yaml，临时排查时最快。**

### 4.4 切换粒度

- 单层关闭：改 yaml 的 `layers.layer_x: false`
- 单 invariant 关闭：改 yaml 的 `invariants.<name>.enabled: false`
- 一次性会话关闭：`INK_DEBUG_OFF=1 /ink-write`
- 全局长期关闭：`master_enabled: false`

## 5. 失败模式策略

**核心铁律：debug 不能炸掉写章节。**

| 故障 | 处置 | 是否影响主流程 |
|---|---|---|
| collector.record() 任意异常 | catch all → 写 `<project>/.ink-debug/collector.error.log` | ❌ 不影响 |
| `.ink-debug/` 目录不可写 | fallback 到 stderr 一行警告 + 主流程继续 | ❌ 不影响 |
| JSONL 写入失败（磁盘满 / 权限） | 同 collector 异常 | ❌ 不影响 |
| invariant 函数自身崩 | catch + 落 `meta.invariant_crashed` 自我事件 | ❌ 不影响 |
| indexer 失败 | log 到 `indexer.error.log`，下次 alerter 触发时重试 | ❌ 不影响 |
| `master_enabled=false` 或 `INK_DEBUG_OFF=1` | collector.record() 立即 return None，零开销 | ❌ 不影响 |
| events.jsonl 单文件 > 100MB | 自动 rotate 为 `events.YYYYMMDDHHMMSS.jsonl.gz`，保留最近 5 个 | ❌ 不影响 |
| severity=error 命中 | JSONL+stderr 立即同步 print（红色），仍 NOT raise | ❌ 不影响 |

**显式失败的唯一场景**：`strict_mode=true` 且写入未知 kind 时，**仅** 在测试环境抛 `ValueError`，生产环境永远 fail-soft（落 `meta.unknown_kind`）。

## 6. Windows 兼容（按 CLAUDE.md 守则）

- 所有 `open()` 强制 `encoding="utf-8"`，`Path.read_text/write_text` 同样
- collector / cli 入口调用 `runtime_compat.enable_windows_utf8_stdio()`
- ANSI 颜色：`stdout.isatty() and not os.environ.get("NO_COLOR")` 才输出色码，否则纯文本
- 路径全用 `pathlib.Path`
- 新增的 `.sh` CLI 入口必须配套 `.ps1` + `.cmd`：`ink-debug-status` / `ink-debug-report` / `ink-debug-toggle` 三个三套
- gzip rotate 用 Python 内置 `gzip` 模块（跨平台，不依赖系统 gzip 命令）

## 7. 分析与反馈

### 7.1 自动收尾告警

**整个 alerter 也受 `master_enabled` 与 `INK_DEBUG_OFF` 门控**：master off 时**不打印任何摘要、不触发任何报告生成**。这是 Section 5 表格中"master_enabled=false 零开销"的全链路体现，避免 master off 时仍残留可见副作用。

**每 `/ink-write` 末尾**（由 alerter 触发）：

```
📊 debug: 本章 3 warn / 0 error，最高频 kind: writer.short_word_count (本周第 14 次)
   完整报告：/ink-debug-report --since 1d
```

颜色：error≥1 红 / warn≥1 黄 / 全清绿。Windows 无 ANSI 时降级为纯文本前缀。

**每 `/ink-auto` 批次末尾**：自动跑 reporter 生成 `<project>/.ink-debug/reports/<date>-auto-batch-<N>.md`，并在终端 print 路径。

**告警触发条件**（追加进收尾摘要）：

- error 级 incident 任意 1 次 → 立即告警
- 同一 (skill, kind) 在 7 天内 ≥ 5 次 → 加进摘要
- 出现全新 kind（历史从未见过）→ 加进摘要

### 7.2 `/ink-debug-report` 双视图 markdown

```
# Debug Report: 2026-04-28 14:30 (since 7d)

## 视图 1：按发生位置（skill × kind × severity）

| skill | kind | severity | count | latest |
|---|---|---|---|---|
| ink-write | writer.short_word_count | warn | 14 | 2026-04-28 14:23 |
| ink-write | polish.diff_too_small | warn | 7 | 2026-04-28 11:02 |
| ink-auto | auto.skill_step_skipped | warn | 3 | 2026-04-28 09:15 |

## 视图 2：按疑似根因（人工标注 + 自动归并）

### 根因 A: writer 输出契约脱节（共 23 次）
- writer.short_word_count × 14
- polish.diff_too_small × 7（推测连锁：字数本就不足，polish 也没空间改）
- review.missing_dimensions × 2

→ 建议：复查 writer-agent SKILL.md 的字数硬约束位置 / 加 retry on short

### 根因 B: ink-auto 工作流偏航（共 3 次）
- auto.skill_step_skipped × 3（全部漏 audit step）

→ 建议：在 ink-auto SKILL.md 显式加"audit step 不可跳"的硬约束
```

视图 2 的"根因"在 v0.5 用规则归并（同 step 的 kind 归一组）；v1.0 用 LLM 归并。

### 7.3 外接 Claude SOP（兜底，零基础设施）

`USER_MANUAL_DEBUG.md` 第 4 节给出标准 4 步：

1. `/ink-debug-report --since 7d`
2. `cat <报告路径>`
3. 复制全文到新 Claude 会话或 ultrareview
4. Prompt: "请按这份 debug 报告分析根因，建议改哪些 SKILL.md 字段、加哪些新 invariant、加哪些 fixture"

## 8. CLI 命令

| 命令 | 用途 | 示例 |
|---|---|---|
| `/ink-debug-status` | 看 4 开关 + 24h 计数 + top3 kind | 无参 |
| `/ink-debug-report` | 生成双视图 markdown | `--since 7d` / `--since 1h` / `--run-id <id>` |
| `/ink-debug-toggle` | 临时改开关，无需手编 yaml | `layer_d on` / `master off` |

每个命令配套 `.sh` / `.ps1` / `.cmd` 三套入口，落 `scripts/debug/`。

## 9. 文件布局

```
# 项目目录（每本书）
<project>/
└── .ink-debug/
    ├── events.jsonl
    ├── events.20260428T142351.jsonl.gz   # rotate
    ├── debug.db
    ├── reports/
    │   └── 2026-04-28-auto-batch-12.md
    ├── collector.error.log
    ├── indexer.error.log
    └── config.local.yaml                  # 可选项目级覆盖

# 仓库内
config/debug.yaml                           # 全局默认
ink_writer/debug/
├── __init__.py
├── collector.py
├── schema.py
├── checker_router.py
├── indexer.py
├── reporter.py
├── alerter.py
├── cli.py
└── invariants/
    ├── __init__.py
    ├── writer_word_count.py
    ├── polish_diff.py
    ├── review_dimensions.py
    ├── context_required_files.py
    └── auto_step_skipped.py

scripts/debug/
├── hook_handler.py
├── ink-debug-status.{sh,ps1,cmd}
├── ink-debug-report.{sh,ps1,cmd}
└── ink-debug-toggle.{sh,ps1,cmd}

.claude/settings.json                       # 注册 hooks（更新现有文件）
docs/USER_MANUAL_DEBUG.md                   # 使用说明书
docs/superpowers/specs/2026-04-28-debug-mode-design.md   # 本文档
tests/debug/
├── __init__.py
├── test_collector.py
├── test_schema.py
├── test_indexer.py
├── test_invariants_writer.py
├── test_invariants_polish.py
├── test_invariants_review.py
├── test_invariants_context.py
├── test_invariants_auto.py
├── test_reporter.py
├── test_alerter.py
├── test_e2e_ink_write.py
├── test_disabled_mode.py
└── test_rotate.py
```

## 10. 测试矩阵

| 类型 | 文件 | 覆盖点 |
|---|---|---|
| unit | `test_collector.py` | master switch / severity 路由 / 异常吞掉不传染 / utf-8 写入 |
| unit | `test_schema.py` | kind 命名规范 / 必备字段缺失 / 未知 kind fail-soft |
| unit | `test_indexer.py` | 增量同步 / watermark 前进 / 损坏 JSONL 行跳过 |
| unit | `test_invariants_<5>.py` | 5 个 invariant 各自的命中 / 不命中 / 自身异常 catch |
| unit | `test_reporter.py` | 双视图 markdown 渲染 / 空数据时的友好输出 |
| unit | `test_alerter.py` | 摘要文案 / ANSI 颜色降级 / Windows 无 tty 时纯文本 |
| integration | `test_e2e_ink_write.py` | fake `/ink-write` → events.jsonl 有事件 → SQLite 可查 → status 输出非空 |
| integration | `test_disabled_mode.py` | master_enabled=false 或 INK_DEBUG_OFF=1 → `.ink-debug/` 零新增 |
| integration | `test_rotate.py` | 模拟 100MB+ → rotate 生成 .gz / 旧文件保留最近 5 个 |

## 11. v0.5 Acceptance Criteria

1. 在一个空项目跑 `/ink-write` 写一章 → `<project>/.ink-debug/events.jsonl` 至少有 N 条事件（N 由该章触发的 checker / invariant 数量决定）
2. SQLite 索引能查到刚写入的 warn+ 事件（`SELECT count(*) FROM incidents WHERE run_id=...`）
3. `/ink-debug-status` 输出：当前 4 个开关状态 + 最近 24h 各 severity 计数 + top3 频发 kind
4. `/ink-debug-report --since 1h` 输出双视图 markdown，文件落到 `<project>/.ink-debug/reports/`
5. `/ink-write` 收尾自动打印摘要行（带 ANSI 颜色 / Windows 降级纯文本），前提：`master_enabled: true` 且 `alerts.per_chapter_summary: true`
6. 把 `master_enabled: false`（无论改全局 yaml 还是设 `INK_DEBUG_OFF=1`）→ 重跑 `/ink-write` → `.ink-debug/` 不新增任何事件、不打印任何摘要
7. 删除 `<project>/.ink-debug/` → 重跑 `/ink-write` 不报错（自动重建）
8. 1 个 integration test 覆盖第 1-3 条
9. `docs/USER_MANUAL_DEBUG.md` 至少包含：3 命令置顶 / 默认配置说明 / "忘了怎么办" 速查 / 喂给 AI 的 4 步 SOP / v1.0 升级入口

## 12. v1.0 升级路径

v0.5 已经预留：

- `config.layers.layer_d_adversarial: false` → 改 true 即开层 D
- schema 已支持 `source=layer_d_adversarial` 与 `source=meta`
- reporter 视图 2 的"根因归并"已留 LLM 替换接口

v1.0 增加（按价值排序）：

| # | 新增 | 触发条件 |
|---|---|---|
| 1 | `ink_writer/debug/adversarial.py`（macro-review 时机的对抗复核 agent）| v0.5 跑 50+ 章后，根据数据决定是否需要 |
| 2 | `scripts/debug/auto_fix_pr.py`（incident → SKILL.md patch 草案）| 同上 + 至少 3 个根因被人工确认有重复模式 |
| 3 | `scripts/debug/aggregate_across_projects.py`（跨项目聚合）| 用户运行了 ≥2 本书时 |
| 4 | CronCreate 周报注册（用户运行一行命令即可）| 用户主动询问"能不能定时" |

## 13. Open Questions

- **Q1**：`run_id` 怎么定义最稳？候选：(a) 时间戳+skill 名，(b) Claude Code session id 截短，(c) 写章前生成 UUID。先用 (a)，看实际数据再调。
- **Q2**：layer B 接入 5 个 checker 的代码点是写在 checker_router 内部（侵入低）还是改 checker agent 模板（更显式）？倾向前者，但需要 prototype 时验证。
- **Q3**：`.ink-debug/` 是否应进 `.gitignore`？**应该**（事件流和单本书的 OS 用户绑定，不应跨机器同步），写 spec 时一并加。

## 14. 参考

- `CLAUDE.md` — Windows 兼容守则
- `ink_writer/scripts/runtime_compat.py` — UTF-8 stdio 共享原语
- `docs/superpowers/specs/2026-04-28-fanqie-min-words-floor-design.md` — 类似规模 spec 的样板
- `docs/superpowers/M-ROADMAP.md` — 5 周质量治理路线图（debug 模式可视为 M5 的工程基础）
