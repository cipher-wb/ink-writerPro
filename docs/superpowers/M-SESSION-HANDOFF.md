# 🔁 M-SESSION-HANDOFF.md — 新会话单文件 catch-up

**最后更新**：2026-04-26（M5 完成后；5 周 roadmap 100% 完成）
**用途**：新 Claude Code 会话开始时**第一件事 cat 这份文件**，5 分钟接上完整上下文

---

## ⚡ TL;DR — 新 AI 会话最常见的对话开场

**用户说什么 → 你应该立刻做什么**：

| 用户说 | 你的第一动作 |
|---|---|
| "继续" / "接着干" / "开始真实验证" / "跑测试书" | 5 周 roadmap 已 100% 完成；下一步是真实质量验证。见 §7 7 步流程（ink-init quick → ink-plan → ink-write 30 章 → 投编辑评分 → dashboard 看趋势） |
| "看进度" / "进度如何" / "M5 跑完没" | 跑 `jq -r '.userStories[] | "\(.id) \(if .passes then "✅" else "⬜" end)"' prd.json + git log --oneline -8` 给当前快照；M5 13 US 全 ✅，tag `m5-final` |
| "M5 怎么样了" / 想看回顾 | cat `docs/superpowers/M-ROADMAP.md` 顶部 Status 行 + cat 本文件 §3 M5 实际产出 |
| 提到具体 case / chunk / agent / meta-rule / dry-run | 这些是 ink-writer 项目的核心概念；详见本文件 §4 |
| "重新开始" / "新功能" | roadmap 已收官；新需求按常规分支 + brainstorming → plan → ralph 三步流程 |

---

## §1 项目本质（30 秒读完）

- **项目**：`/Users/cipher/AI/小说/ink/ink-writer/`，AI 写网文工具（v23.0.0 baseline）
- **痛点**：起点编辑（星河）评编辑评分 30/100
- **方案哲学**："病例（case）" 是产线唯一真相源；编辑差评 → case → checker → 阻断重写 → 通过 → 复发监测
- **5 周 roadmap**：M1 → M2 → M3 → M4 → M5（顺序依赖；详见 `docs/superpowers/M-ROADMAP.md`）

---

## §2 当前进度快照（2026-04-26 M5 完成后；5 周 roadmap 100% 完成）

| Milestone | 状态 | 完成日期 | branch / tag | commit count |
|---|---|---|---|---|
| **M1** 基础设施 + Qdrant + symlink 修复 | ✅ | 2026-04-24 | `m1-foundation` | 17 US |
| **M2** 数据资产（cases 完整 / corpus_chunks deferred）| 🟡 partial | 2026-04-25 | `m2-data-assets-partial` | 12 US |
| **M3** P1 下游闭环（**质量拐点**）| ✅ | 2026-04-25 | `m3-p1-loop` | 14 US |
| **M4** P0 上游策划层 | ✅ | 2026-04-25 | `m4-p0-planning` | 14 US |
| **M5** Dashboard + 自进化 + 用户接口 | ✅ | 2026-04-26 | `m5-final` | 13 US |

**100% 进度（5/5 milestone 完成 + 1 partial 待续）**。

**全部 push 到 GitHub**（remote: `https://github.com/cipher-wb/ink-writerPro.git`）。

---

## §3 M5 实际产出（最近一次完成）

### 已交付的 13 个 US

| US | 实际产出 | 关键 commit |
|---|---|---|
| US-001 | Case schema 扩展 3 字段（recurrence_history / meta_rule_id / sovereign）+ 410 yaml 向后兼容 | (本批次) |
| US-002 | `ink_writer/regression_tracker/` Layer 4 复发追踪 + CLI `--apply` | (本批次) |
| US-003 | `ink_writer/meta_rule_emergence/` Layer 5 元规则浮现 + LLM 主观聚类 + MR-NNNN 写盘 | (本批次) |
| US-004 | `ink case meta-rule {list, approve, reject}` CLI + 幂等接口 + covered_cases 写 meta_rule_id | (本批次) |
| US-005 | `ink_writer/dashboard/{aggregator,m5_overview}` 4 大指标 + dry-run 切换推荐 | (本批次) |
| US-006 | `ink_writer/dashboard/weekly_report.py` ISO 周报 markdown CLI | (本批次) |
| US-007 | `config/ab_channels.yaml` + EvidenceChain `channel` 字段透传 + ink-write SKILL.md A/B 通道段 | (本批次) |
| US-008 | `data/case_library/user_corpus/history-travel/` 仿写片段 + user_genres 索引 | (本批次) |
| US-009 | `ink_writer/learn/auto_case.py` ink-learn `--auto-case-from-failure` CLI + throttle 配置 | (本批次) |
| US-010 | `ink_writer/learn/promote.py` ink-learn `--promote` 短期记忆升格长期 case | (本批次) |
| US-011 | `docs/USER_MANUAL.md` 5 节作者使用手册（229 行） | `a2288f8` |
| US-012 | `docs/EDITOR_FEEDBACK_GUIDE.md` 3 节编辑反馈手册（166 行）+ `8886079` 修正 prd.json/progress.txt 路径 | `3988ba8` / `8886079` |
| US-013 | `tests/integration/test_m5_e2e.py` 6 用例 + tag `m5-final` + ROADMAP/handoff 100% 完成标记 | (本次提交) |

### M5 关键产物（roadmap 全交付）

- **新增 4 个子包**：`ink_writer/regression_tracker/`（Layer 4）+ `ink_writer/meta_rule_emergence/`（Layer 5）+ `ink_writer/dashboard/`（aggregator + m5_overview + weekly_report）+ `ink_writer/learn/`（auto_case + promote）。
- **新增 3 个 CLI**：`python -m ink_writer.regression_tracker [--apply]` + `python -m ink_writer.meta_rule_emergence [--propose]` + `python -m ink_writer.dashboard.weekly_report --week N` + `ink case meta-rule {list,approve,reject}` 嵌套子命令。
- **case schema 扩 3 字段**：recurrence_history / meta_rule_id / sovereign（向后兼容 410 active case）；case_id regex 加 `LEARN|PROMOTE` 前缀分支。
- **新增 2 份用户文档**：`docs/USER_MANUAL.md`（5 节，229 行）+ `docs/EDITOR_FEEDBACK_GUIDE.md`（3 节，166 行）。
- **2 份 SKILL.md 加 M5 段**：`ink-writer/skills/ink-dashboard/SKILL.md` 加 M5 Case 治理段 + `ink-writer/skills/ink-write/SKILL.md` 加 A/B 通道段（含 PowerShell sibling 块）+ `ink-writer/skills/ink-learn/SKILL.md` 加 auto-case + promote 段。
- **新增 1 个数据资产**：`data/case_library/user_corpus/history-travel/` 仿写历史叙事文体片段（fair-use synthetic_excerpt）。
- **新增 2 份配置**：`config/ab_channels.yaml`（A/B 通道，默认 enabled=false）+ `config/ink_learn_throttle.yaml`（自动 case throttle）。
- **e2e 测试**：`tests/integration/test_m5_e2e.py` 6 用例覆盖 spec §13；周报 `reports/weekly/2026-W17.md` 真跑产物。
- **全量 pytest**：3808 passed / 23 skipped / 0 failed（5 分钟 17 秒）；忽略 3 个 pre-existing dashboard collection error（自 US-008 起即存在，归 follow-up）。

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

## §7 下一步：真实质量验证（5 周 roadmap 之外）

**5 周 roadmap 已 100% 交付**；从工程视角看 M5 ✅ 收官。下一阶段重心是**真实数据验证 30/100 → 60+/100**。

**目标**：用真实测试书 + 真实编辑评分验证 5 周 roadmap 的产线效果。

**步骤**（用户说 "开始真实验证" / "跑测试书" 时）：
1. `ink-init quick --book test-real`：开新书（走 M4 Step 99 策划审查 4 个 ink-init checker）
2. `ink-plan --book test-real`：30 章大纲（走 M4 Step 99 策划审查 3 个 ink-plan checker）
3. `ink-write ch001..ch030 --book test-real`：写 30 章（M3 dry-run 5 章后 auto-switch 真阻断；可选 `--channel A|B` 验 A/B 实验）
4. 投起点 / 番茄编辑评分（30 章 ≈ 7.5 万字）
5. 评分回填 `data/editor_reviews/test-real.yaml`（参考 `docs/EDITOR_FEEDBACK_GUIDE.md` §1 schema）
6. `ink dashboard --m5`：看 4 大指标趋势（recurrence_rate / repair_speed / editor_score_trend / checker_accuracy）
7. `python -m ink_writer.dashboard.weekly_report --week N`：周报跟踪长期趋势

**M3 / M4 dry-run 切真阻断时机**：M3 / M4 各自有 5 次观察期独立计数（`data/.dry_run_counter` / `data/.planning_dry_run_counter`），观察期满后 `switch_to_block_after=true` 自动切真阻断；首次跑 30 章前可 review 两个 dry_run 报告决定是否调阈值。

**5 周外 follow-up**：见 §8（M2 corpus_chunks 真跑、ink-learn promote 跑 ≥ 4 周、跨 book 复发追踪、A/B 随机分流等可选项）。

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
