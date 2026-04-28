# Debug Mode 使用说明书

> **一句话**：开着不管，AI 写错的地方自动记到 `.ink-debug/`，需要时一键出报告喂给 AI 优化软件。
>
> **状态**：✅ v0.5 已实施 (2026-04-28)，全部 9 条 acceptance 通过。

---

## 0. 我现在该干嘛？

**最常用 3 命令（背下来 / 加书签）**：

```bash
/ink-debug-status        # 看现在咋样（开关 + 最近 24h 摘要）
/ink-debug-report        # 出 markdown 报告（喂给 AI）
/ink-debug-toggle <开关名> on|off    # 临时改开关，无需手编 yaml
```

**遇到问题不想被记录**：

```bash
export INK_DEBUG_OFF=1            # 当前 shell 全部 debug 写入立即停止
unset INK_DEBUG_OFF               # 恢复
```

---

## 1. 默认就是开的，什么都不用配

仓库内 `config/debug.yaml` 默认：

- `master_enabled: true`
- 4 个上游层 A/B/C 默认全开；D 关（v1.0 才开）
- info 级写 JSONL（细节流），warn+ 进 SQLite（可查询面）

**也就是说，你只要拉了仓库，写章节时 debug 已经在记了，不需要任何动作**。

---

## 2. 三命令详解

### 2.1 `/ink-debug-status` — 看现在咋样

无参。输出大致长这样：

```
[debug status] 项目: 因果剑歌
==============================================
开关: master=on  layer_a=on  layer_b=on  layer_c=on  layer_d=off
==============================================
最近 24h:
  info: 142
  warn: 8
  error: 0
==============================================
top3 频发 kind:
  1. writer.short_word_count   ×6
  2. polish.diff_too_small     ×1
  3. checker.consistency.character_drift  ×1
==============================================
完整报告：/ink-debug-report --since 1d
```

### 2.2 `/ink-debug-report` — 出 markdown 报告

参数：

- `--since 1h` / `--since 1d` / `--since 7d` （默认 1d）
- `--run-id <id>` 只看某次写章 / 某批 ink-auto
- `--severity warn` 过滤最低 severity

输出：`<project>/.ink-debug/reports/manual-YYYYMMDD-HHMM.md`，并在终端 print 路径。

报告包含**两个视图**：

1. **按发生位置**：`(skill × kind × severity)` 透视表，机器友好
2. **按疑似根因**：把同一根因下不同 kind 的 incident 归一组，人友好

### 2.3 `/ink-debug-toggle` — 临时改开关

```bash
/ink-debug-toggle layer_d on              # 开启 v1.0 对抗复核（前提是已实施）
/ink-debug-toggle layer_a off             # 临时关掉 hooks 层
/ink-debug-toggle master off              # 全关（等同 INK_DEBUG_OFF=1）
/ink-debug-toggle invariants.polish_diff off  # 关掉单个 invariant
```

底层是改 `<project>/.ink-debug/config.local.yaml`（项目级覆盖，不污染仓库 yaml）。重启 shell / 重跑 /ink-write 立即生效。

---

## 3. 配置速查

### 3.1 全局默认（仓库内 `config/debug.yaml`）

```yaml
master_enabled: true                    # 总开关

layers:
  layer_a_hooks: true                   # Claude Code hooks
  layer_b_checker_router: true          # 已有 5 个 checker 标准化
  layer_c_invariants: true              # 5 个 invariant
  layer_d_adversarial: false            # v1.0 才开

severity:
  jsonl_threshold: info                 # info+ 落 JSONL
  sqlite_threshold: warn                # warn+ 进 SQLite（被 status / report 看到）
  alert_threshold: warn                 # warn+ 触发收尾摘要
  stderr_threshold: error               # error 立即 stderr 红字

invariants:
  writer_word_count: { enabled: true }
  polish_diff: { enabled: true, min_diff_chars: 50 }
  review_dimensions: { enabled: true, min_dimensions_per_skill: { ink-review: 7 } }
  context_required_files: { enabled: true }
  auto_step_skipped:
    enabled: true
    expected_steps: { ink-auto: [context, draft, review, polish, extract, audit] }
```

### 3.2 项目级覆盖（`<project>/.ink-debug/config.local.yaml`）

只列要改的字段，**深合并**全局配置：

```yaml
# 例：本项目临时关掉 polish_diff invariant
invariants:
  polish_diff: { enabled: false }
```

### 3.3 紧急关闭

```bash
export INK_DEBUG_OFF=1
```

环境变量优先级**高于** yaml 任意配置；适合临时排查时用。

---

## 4. 喂给 AI 的标准 SOP（核心用法）

这是 debug 模式的最终目的——**让 log 变成软件改进**。

### 4 步走

```bash
# 1. 出最近 7 天报告
/ink-debug-report --since 7d
# → <project>/.ink-debug/reports/manual-20260428-1530.md

# 2. 看一眼报告（确认有内容）
cat <project>/.ink-debug/reports/manual-20260428-1530.md

# 3. 复制全文到新 Claude 会话 / ultrareview / 其它 AI 会话

# 4. 用这段 prompt（或类似）：
```

> 这是我 ink-writer 项目最近 7 天的 debug 报告。请按以下方式分析：
>
> 1. 找出**最高频根因**（视图 2 已经初步归并，请验证）
> 2. 对每个根因，建议**改哪些 SKILL.md** 字段（具体文件名 + 段落）
> 3. 是否需要**新增 invariant**？如果需要，给出 kind 命名 + 检测条件
> 4. 是否需要**新增 fixture / 测试**？如果需要，给出 fixture 名 + 触发条件
> 5. 输出格式：每个建议独立成段，标注优先级 P0/P1/P2

---

## 5. 忘了怎么办（常见情景速查）

| 情景 | 命令 |
|---|---|
| 不知道现在 debug 开没开 | `/ink-debug-status` |
| 想看最近一章有啥事件 | `/ink-debug-report --since 1h` |
| 想看本周整体 | `/ink-debug-report --since 7d` |
| 想看某一次 ink-auto 批次 | `/ink-debug-report --run-id auto-2026-04-28-batch12` |
| 临时关 debug | `export INK_DEBUG_OFF=1` |
| 永久关 debug（仅本机） | 改 `config/debug.yaml: master_enabled: false` |
| 永久关 debug（仅本项目） | `<project>/.ink-debug/config.local.yaml` 加 `master_enabled: false` |
| 重置 / 清空 debug 数据 | `rm -rf <project>/.ink-debug/` （会自动重建） |
| 想知道 .ink-debug/ 占多大 | `du -sh <project>/.ink-debug/` |
| 想 grep raw 事件流 | `grep <kind> <project>/.ink-debug/events.jsonl` |
| 想跑 SQL 直查 | `sqlite3 <project>/.ink-debug/debug.db "SELECT kind, COUNT(*) FROM incidents GROUP BY kind ORDER BY 2 DESC"` |
| 收尾摘要颜色乱码（Windows） | `set NO_COLOR=1`（cmd.exe）/ `$env:NO_COLOR=1`（PS） |

---

## 6. 文件长啥样

```
<project>/.ink-debug/
├── events.jsonl              # raw 事件流，append-only，一条 JSON 一行
├── events.20260428T142351.jsonl.gz   # 满 100MB 后自动 rotate（gzip 归档，保留最近 5 个）
├── debug.db                  # SQLite 索引，warn+ 事件
├── reports/                  # 自动 + 手动生成的 markdown 报告
│   ├── 2026-04-28-auto-batch-12.md   # /ink-auto 批次自动生成
│   └── manual-20260428-1530.md       # /ink-debug-report 手动生成
├── collector.error.log       # collector 自身错误（如果有）
├── indexer.error.log         # indexer 自身错误（如果有）
└── config.local.yaml         # 项目级配置覆盖（可选）
```

**`.ink-debug/` 已加进 `.gitignore`**：事件流不跨机器同步。

---

## 7. 收尾摘要长啥样

每次 `/ink-write` 写完最后会打印一行：

```
📊 debug: 本章 3 warn / 0 error，最高频 kind: writer.short_word_count (本周第 14 次)
   完整报告：/ink-debug-report --since 1d
```

颜色：
- error ≥ 1 → 🔴 红
- warn ≥ 1 → 🟡 黄
- 全清 → 🟢 绿

每次 `/ink-auto` 跑完一个批次会自动 print：

```
📋 debug: 批次报告已生成 → <project>/.ink-debug/reports/2026-04-28-auto-batch-12.md
```

---

## 8. 升级到 v1.0（什么时候 / 怎么升）

### 什么时候升？

**不要急着升**。先让 v0.5 跑 50+ 章，攒真实数据。如果出现以下任意 2 条，再考虑：

- v0.5 报告里**反复出现 3 个以上根因**且人工修了几轮还在复发 → 上 layer D 让对抗复核 agent 兜底
- 你想要**周报自动生成** → 注册 cron
- 你同时写了 ≥ 2 本书且想跨项目对比 → 跑跨项目聚合脚本

### 怎么升？

| v1.0 功能 | 入口 |
|---|---|
| layer D 对抗复核 | `config/debug.yaml: layers.layer_d_adversarial: true`（前提是已实施 `ink_writer/debug/adversarial.py`）|
| 自动 fix PR 草案 | 跑 `scripts/debug/auto_fix_pr.py --since 7d` |
| 跨项目聚合 | 跑 `scripts/debug/aggregate_across_projects.py` |
| 周报 cron | 跑 `scripts/debug/register_weekly_cron.sh` |

详见 `docs/superpowers/specs/2026-04-28-debug-mode-design.md` 第 12 节。

---

## 9. FAQ

**Q: debug 会不会拖慢写章？**
A: 单事件目标 < 5ms，索引异步。100 章下来感知应该不到 1 秒级别。如果你测出明显慢，按 acceptance criteria 第 1 条复盘。

**Q: AI 知道自己被监视吗？会不会演？**
A: layer A/B/C 全部是**外部观察 + 结构化判断**，不依赖 LLM 自报，AI 看不到 collector 的存在。layer D 才是 LLM 复核（v1.0），那时观察者悖论确实存在，是已知 tradeoff。

**Q: 我能直接让 AI 自动修 SKILL.md 吗？**
A: v0.5 不做。原因：AI 改自己的契约容易越改越糟，必须人审。v1.0 会出 patch 草案但仍要你 review 后再合。

**Q: 报告里 "疑似根因" 准吗？**
A: v0.5 的根因归并是**纯规则**（同 step 的 kind 归一组），可能粗糙；v1.0 用 LLM 归并。当前阶段把它当线索，不当结论。

**Q: events.jsonl 会爆盘吗？**
A: 单文件 100MB 自动 rotate gzip 归档，保留最近 5 个。**理论上限 ~500MB 压缩前 / 几十 MB 压缩后**。不爆。

**Q: 多本书共用 .ink-debug/ 吗？**
A: 不。每本书独立，`.ink-debug/` 在项目目录下。跨项目分析是 v1.0 的 aggregator 脚本。

---

## 10. 一句话备忘

```
平时不管 → /ink-debug-status 看一眼 → /ink-debug-report --since 7d 出报告 → 复制喂给 AI
```
