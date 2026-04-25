# 🔁 M-SESSION-HANDOFF.md — 新会话单文件 catch-up

**最后更新**：2026-04-25（M3 完成后）
**用途**：新 Claude Code 会话开始时**第一件事 cat 这份文件**，5 分钟接上完整上下文

---

## ⚡ TL;DR — 新 AI 会话最常见的对话开场

**用户说什么 → 你应该立刻做什么**：

| 用户说 | 你的第一动作 |
|---|---|
| "继续" / "接着干" / "推 M4" / "开 M4" | 调 `superpowers:brainstorming` skill → cat `docs/superpowers/M4-PREPARATION-NOTES.md` → 按 PRE-NOTES 的 brainstorm 题逐题问用户 |
| "看进度" / "M4 怎么样了" / "进度如何" | 跑 `jq -r '.userStories[] | "\(.id) \(if .passes then "✅" else "⬜" end)"' prd.json + git log --oneline -8 + ps -ef | grep ralph` 给当前快照 |
| "M3 跑完没" / 想看回顾 | cat `docs/superpowers/M-ROADMAP.md` 顶部 Status 行 + cat 本文件 §3 快照 |
| 提到具体 case / chunk / agent | 这些是 ink-writer 项目的核心概念；详见本文件 §4 |
| "重新开始" / "新功能" | 不要打断 5 周 roadmap，先确认这是 roadmap 内还是 roadmap 外的需求 |

---

## §1 项目本质（30 秒读完）

- **项目**：`/Users/cipher/AI/小说/ink/ink-writer/`，AI 写网文工具（v23.0.0 baseline）
- **痛点**：起点编辑（星河）评编辑评分 30/100
- **方案哲学**："病例（case）" 是产线唯一真相源；编辑差评 → case → checker → 阻断重写 → 通过 → 复发监测
- **5 周 roadmap**：M1 → M2 → M3 → M4 → M5（顺序依赖；详见 `docs/superpowers/M-ROADMAP.md`）

---

## §2 当前进度快照（2026-04-25 12:50 PM）

| Milestone | 状态 | 完成日期 | branch / tag | commit count |
|---|---|---|---|---|
| **M1** 基础设施 + Qdrant + symlink 修复 | ✅ | 2026-04-24 | `m1-foundation` | 17 US |
| **M2** 数据资产（cases 完整 / corpus_chunks deferred）| 🟡 partial | 2026-04-25 | `m2-data-assets-partial` | 12 US |
| **M3** P1 下游闭环（**质量拐点**）| ✅ | 2026-04-25 | `m3-p1-loop` | 14 US |
| **M4** P0 上游策划层 | ⚪ 待启动 | — | TBD | TBD |
| **M5** Dashboard + 自进化 + 用户接口 | ⚪ 待启动 | — | TBD | TBD |

**60% 进度（3/5 milestone 完成 + 1 partial）**。

**全部 push 到 GitHub**（remote: `https://github.com/cipher-wb/ink-writerPro.git`）。

---

## §3 M3 实际产出（最近一次完成）

### 已交付的 14 个 US

| US | 实际产出 | 关键 commit |
|---|---|---|
| US-001 | `config/checker-thresholds.yaml` + `thresholds_loader.py` | `1261ad9` |
| US-002 | `evidence_chain.json` schema + writer + `EvidenceChainMissingError` | `7072ca9` |
| US-003 | `ink_writer/writer_self_check/` agent | `f502226` |
| US-004 | `ink_writer/checkers/conflict_skeleton/` LLM 主观判断 | `1ed5c7d` |
| US-005 | `ink_writer/checkers/protagonist_agency/` LLM 主观判断 | `4b29ed9` |
| US-006 | `block_threshold_wrapper` 升级现有 3 checker | `859d2ff` |
| US-007 | `polish-agent` 改 prompt 接收 case_id 驱动 | `c2c0738` |
| US-008 | `rewrite_loop/orchestrator` 主调度 | `b404e36` |
| US-009 | `dry_run.py` counter + auto-switch | `5b89fa5` |
| US-010 | `human_review.py` 4 版保留 + needs_human_review.jsonl | `f30274a` |
| US-011 | `ink-write SKILL.md` Step 1.5 集成新循环 | `29ed915` |
| US-012 | `dry_run_report.py` 5 章后聚合报告 | `270838c` |
| US-013 | `tests/integration/test_m3_e2e.py` 8 用例 | `4564984` |
| US-014 | tag `m3-p1-loop` + ROADMAP 更新 | `8c395c3` |
| Followup | baseline doc/test 同步（23→26 agents, 17→19 checkers）| `3e5dc19` |

### M3 关键产物（M4/M5 复用）

- **新增 7 个 Python 子包**：`writer_self_check / checkers/{conflict_skeleton,protagonist_agency} / rewrite_loop / evidence_chain / checker_pipeline.{thresholds_loader,block_threshold_wrapper}`
- **新增 4 个 agent.md**：writer-self-check / conflict-skeleton-checker / protagonist-agency-checker + polish-agent.md M3 改造章节
- **新增 1 个 config**：`config/checker-thresholds.yaml`（M3 全部阈值 + dry-run 控制）
- **全量 pytest**：3700+ passed / 0 failed / coverage **82.75%**（M2 baseline 82.72% 略升）

---

## §4 项目核心概念（与 AI 对话时常见词）

| 概念 | 含义 | 文件位置 |
|---|---|---|
| **case** | 病例（产线唯一真相源）；编辑差评 → case → checker → 阻断 | `data/case_library/cases/CASE-2026-NNNN.yaml` 共 403 个 |
| **chunk** | 范文段落级切片（M3 期为空，M2 deferred）| `data/corpus_chunks/` (M3 期空) |
| **rule** | editor-wisdom 抽取的写作规则（v23 已有 402 条）| `data/editor-wisdom/rules.json` |
| **checker** | 章节质量检查 agent | `ink-writer/agents/*-checker.md`（共 26 个 agent，含 19 个 checker）|
| **writer-self-check** | M3 新增章末合规检查（rule_compliance + cases）| `ink_writer/writer_self_check/` |
| **rewrite_loop** | M3 阻断重写主循环（max 3 + cases 排序 + needs_human_review）| `ink_writer/rewrite_loop/` |
| **evidence_chain** | 每章交付必带的审计 JSON | `data/<book>/chapters/<chapter>.evidence.json` |
| **dry-run** | M3 5 章观察后 auto-switch 真阻断的护栏 | `data/.dry_run_counter` 持久化 |
| **ralph** | 自主循环 AI agent 系统（每个 US 一个 fresh claude 实例）| `scripts/ralph/ralph.sh` |
| **prd.json / progress.txt** | ralph 跨迭代记忆 | 仓库根 |

---

## §5 实际可用的 LLM / 基础设施配置

```bash
# ~/.claude/ink-writer/.env (已配)
EMBED_BASE_URL=https://open.bigmodel.cn/api/paas/v4/embeddings
EMBED_MODEL=embedding-3                         # 智谱 embedding-3, 2048 维
EMBED_API_KEY=649dde58...
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash                            # M2 切片用；M3 推荐改 glm-4.6
LLM_API_KEY 复用 EMBED_API_KEY                   # 智谱 BigModel 同一 key
LLM_MIN_INTERVAL=0.2                             # throttling

# Docker / Qdrant
docker ps                                         # ink-writer-qdrant Up 13+ hours
curl http://127.0.0.1:6333/readyz                 # HTTP 200
```

**LLM 选型实战教训**（M2 期间踩过的坑）：
- glm-5.1 RPM 配额极低（1302 rate limit 死锁）
- glm-4.6 单本切片 9min 仅 4 chunks 太慢
- glm-4-flash 0.54s/call 速度好但质量稍降；M2 切片用它
- M3 调用量小（每章 ~9 调用），可用 glm-4.6 提质量

---

## §6 启动 M4 的标准流程

```bash
# 1. 用户说"开 M4" / "继续" / "接着干"
# 2. 你立刻做：

# Step A: 确认上下文（30 秒）
cat docs/superpowers/M-ROADMAP.md | head -30
cat docs/superpowers/M4-PREPARATION-NOTES.md | head -50

# Step B: 调 brainstorming skill
# (在对话中用 Skill 工具调 superpowers:brainstorming)

# Step C: brainstorm 14+ 题（按 PRE-NOTES Part C 列出的题逐一问用户）

# Step D: 用户答完后写 spec
# 文件：docs/superpowers/specs/<日期>-m4-p0-planning-design.md

# Step E: 调 writing-plans skill
# 文件：docs/superpowers/plans/<日期>-m4-p0-planning.md

# Step F: 调 prd skill
# 文件：tasks/prd-m4-p0-planning.md

# Step G: 调 ralph skill
# - 归档当前 prd.json (M3) → archive/2026-04-25-m3-p1-loop/
# - 重置 progress.txt（保留 codebase patterns 段）
# - 写新 prd.json (M4)，branch ralph/m4-p0-planning

# Step H: 启动后台 ralph
bash scripts/ralph/ralph.sh --tool claude <US 数> > scripts/ralph/run.log 2>&1 &

# Step I: 监控（每 9-22 分钟 watcher 一次或等用户主动问）
```

---

## §7 M4 brainstorm 准备（已完成）

**预备文件**：`docs/superpowers/M4-PREPARATION-NOTES.md`（如不存在请第一时间创建——内容详见 spec §3 P0 + §9 M4）

**M4 摘要**：
- **范围**：4 个 ink-init checker + 3 个 ink-plan checker + LLM 高频起名词典 + 起点 top200 简介库
- **核心解决**：spec §1.3 诊断的 5/8 上游策划期扣分（题材老套 / 凹设定 / 起名 AI 味 / 金手指出场太晚 / 金手指能力不清晰）
- **依赖**：M1 case_library + M2 LLMClient（不依赖 M3 / 不依赖 M2 chunks）
- **可与 M3 dry-run 并行**：M3 跑下游章节，M4 跑上游策划期；M3 dry-run 5 章后 review 报告才决定切真阻断

**预期 14-15 US**（与 M3 节奏一致，估 5 小时）。

---

## §8 不在 5 周 roadmap 内的 follow-up（按需）

- **M2 corpus_chunks 实跑**（spec §6 P2 完整）：详见 `docs/superpowers/M2-FOLLOWUP-NOTES.md` A 选项（换 LLM provider 重跑 ingest，$1-2 + 1-2 小时）。可在 M5 完成后做。
- **真实 ink-write 跑通验证**：M3 dry-run 5 章产出 evidence_chain.json + dry_run_report.md 验证产线效果。需要先准备一本测试书（用 ink-init quick 模式）+ 真实跑 ink-write 命令。
- **chunk_borrowing 实际计算**：M2 chunks 补完后激活（M3 期为 null 占位）。

---

## §9 失败模式与护栏（给未来会话）

- **失败模式 1**：会话断片导致 roadmap 丢失
  - 护栏：本文件 + project memory + progress.txt 末尾 "Long-Term Roadmap Reminder" 三重保险
- **失败模式 2**：新会话 AI 不知道有 5 周 roadmap，开始建议"重新设计"
  - 护栏：MEMORY.md 顶行明确 "新会话第一件事 cat docs/superpowers/M-SESSION-HANDOFF.md"
- **失败模式 3**：跳过 brainstorm 直接写代码
  - 护栏：所有 milestone 必走 brainstorming → spec → plan → /prd → /ralph 五步流程
- **失败模式 4**：M2 chunks 缺席被忘记
  - 护栏：M2-FOLLOWUP-NOTES.md 永久存在 + ROADMAP M2 行标 🟡

---

## §10 关键人物 / 关键事实

- **作者**：cipher-wb (insectwb@gmail.com)
- **当前项目目录**：`/Users/cipher/AI/小说/ink/ink-writer/`
- **GitHub**：https://github.com/cipher-wb/ink-writerPro
- **核心痛点**：起点编辑评分 30/100 → 目标 60-70（6 个月内验证）
- **跨平台**：macOS + Windows 11；遵守 `CLAUDE.md` Windows 兼容守则（.sh + .ps1 + .cmd 三件套）
- **ralph 系统**：每个 user story 跑一个 fresh claude 实例（context 隔离），靠 git + progress.txt + prd.json 三件持久记忆

---

## 附录：本文件维护规约

- **每完成一个 milestone 必须更新本文件 §2 进度快照 + §3 实际产出**
- **每开始新 milestone 必须更新 memory + 创建 M<N>-PREPARATION-NOTES.md**
- **修改后必须 commit 到 git + push 到 origin（让 GitHub 也能查到）**
- **本文件是单文件 catch-up；具体细节散落在 M-ROADMAP / M<N>-FOLLOWUP / spec / plan 文件，本文件只做总线索**
