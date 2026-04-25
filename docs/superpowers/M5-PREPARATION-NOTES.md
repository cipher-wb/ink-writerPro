# M5 启动 Checklist & Brainstorm 准备

**Status**: 待启动（M4 ✅ 2026-04-25 已完成）
**M5 目标**: 完整闭环上线 + 周报自动产出 + 用户扩展接口
**预计周期**: 1 周（≈ 12-14 user stories）
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §3 P3 + §7 5 层闭环 + §9 M5

> ⚠️ **本文件用途**：M5 brainstorm 输入预备。**当用户说"开 M5"或"继续推"时**，按"M4 收尾确认"→"M5 brainstorm 启动"顺序执行。

---

## Part A — M4 收尾确认（已完成，仅核对）

- ✅ master HEAD `fdf6787` (US-014)
- ✅ tag `m4-p0-planning` 已 push 到 origin
- ✅ 14/14 US 全部 commit + e2e 7/7 PASS
- ✅ ROADMAP / handoff / agent_topology / architecture 全更新
- ✅ 7 个 checker + planning_review 编排层 + 7 个 seed cases 全活

---

## Part B — M4 实际产出对 M5 的影响

### B.1 M5 复用的 M1-M4 资产

| M1-M4 已建 | M5 中的角色 |
|---|---|
| `ink_writer/case_library/`（M1）+ 403+7=410 cases | M5 Layer 4/5 全部基于 case_library 字段操作 |
| `data/case_library/cases/CASE-2026-{NNNN,M4-NNNN}.yaml` | M5 添加 `recurrence_history` / `meta_rule_id` 字段 |
| `ink_writer/evidence_chain/`（M3）+ `planning_writer.py`（M4）| dashboard 数据源 + 复发率聚合输入 |
| `config/checker-thresholds.yaml`（M3）| dashboard 显示阈值 + Layer 5 元规则升级阈值 |
| `ink-writer/skills/ink-dashboard/`（v23 已有 Web 只读面板）| **改造扩展** — 加 case 治理面板（病例复发率/修复速度/编辑分趋势/checker 准确率）|
| `ink-writer/skills/ink-learn/`（v23 已有 pattern 提取）| **改造接 case_library** — `--auto` failure → pending case；`--promote` 短期记忆回灌长期 |
| `scripts/corpus_chunking/llm_client.LLMClient` | M5 LLM 调用（Layer 5 相似度 + 元规则归纳）复用 |

### B.2 M5 不依赖的事

- ❌ M2 corpus_chunks（仍 deferred；A/B 通道不依赖 chunks）
- ❌ M3 dry-run 真切换（M5 dashboard 仅显示 dry-run 状态，不强制切换）
- ❌ M4 真跑 ink-write（M5 测试用 fixture 数据 + history-travel 样例）

### B.3 M5 与现有"项目内会话级记忆"的边界

- `.ink/project_memory.json`（v23 单本书短期记忆）→ M5 不动；ink-learn 仍写它
- `data/case_library/`（跨书长期记忆）→ M5 加 Layer 4/5 字段 + Layer 3 已实现（M1）
- 两者通过 `ink-learn --promote` 桥接（spec §7.5 已述）

---

## Part C — M5 brainstorm 关键问题（≈ 13 题）

### C.1 Dashboard 扩展形态

**Q1**：M5 dashboard 用什么形态？
- a) **复用现有 `ink-dashboard` web 面板，加"M5 Case 治理"标签页**（与 v23 watchdog 框架同源）⭐
- b) 新建 `ink-case-dashboard` 独立 Web 面板（隔离 v23）
- c) CLI-only：`ink dashboard --m5-report` 输出 markdown 周报（无 Web）

### C.2 Dashboard 显示的 4 大指标

**Q2**：M5 dashboard 显示哪些指标（spec §7.3 量化指标对位）？
- a) **4 个核心指标**：病例复发率 / 修复速度（首次差评→resolved 平均天数）/ 编辑评分趋势 / checker 准确率（手工抽样 vs LLM 判定差异）⭐
- b) 6 个：再加 跨书复用率 + 元规则浮现速率
- c) 仅 3 个：去掉 checker 准确率（需手工抽样太麻烦）

### C.3 Layer 4 复发追踪算法

**Q3**：Layer 4 `resolved → regressed` 触发条件？
- a) **同一 book 内 evidence_chain 再次命中已 resolved case** + 升级 severity（hard→hard+1 或 hard 已是顶级则加 `recurrence_count`）⭐
- b) 跨 book 命中也算复发（更严，但可能误判跨书 case 复用）
- c) 只在同一 chapter 复发才算（最严，绕过率高）

### C.4 Layer 5 元规则浮现阈值

**Q4**：Layer 5 "N 个相似 case 自动合并"的 N 是多少？
- a) **N=5 + 相似度 > 0.80**（spec §7.3 默认；保守）⭐
- b) N=3 + 相似度 > 0.85（更激进，元规则浮现快但误合并风险高）
- c) N=7 + 相似度 > 0.75（更保守，几乎不浮现）

### C.5 元规则升级路径

**Q5**：元规则浮现后如何升级到产线 default？
- a) **写到 `data/case_library/meta_rules/` 新目录 + 提示用户审批**（用户审过才升 P0）⭐
- b) 自动升 P0（高风险但快）
- c) 仅 dashboard 警告，不实际改产线（最保守）

### C.6 user_corpus 范围

**Q6**：M5 user_corpus 实际接入什么？
- a) **history-travel 样例（《明朝那些事儿》摘抄 + _meta.yaml）+ ink corpus ingest CLI 跑通**（spec §3 P3 默认；history-travel 1 本验证）⭐
- b) 多题材：history-travel + xuanhuan + scifi 各 1 本（更全但范围大）
- c) 只跑通 CLI 不带样本（让用户自己塞）

### C.7 user_corpus 与 M2 chunks 关系

**Q7**：user_corpus 和 M2 corpus_chunks 是同一管线吗？
- a) **是**：user_corpus 走 M2 已建 corpus_chunking 管线（segmenter + tagger + indexer）+ 标 `source_type: user`；M2 实跑 deferred 状态保持，只验证 user_corpus 入库链路 ⭐
- b) 否：user_corpus 用单独管线（更复杂）

### C.8 A/B 通道实现

**Q8**：A/B 通道（spec §7.4 防过拟合护栏）怎么实现？
- a) **`config/ab_channels.yaml` + `--channel A|B|both`** flag 在 ink-write 选择走老规则还是新元规则；50% chapter 比例由 channel 配置决定 ⭐
- b) 强制 50%（ink-write 内部随机）
- c) 不实现（Q5 用户审批已经是护栏，A/B 太复杂）

### C.9 文档范围

**Q9**：作者使用手册 + 编辑反馈录入手册具体写什么？
- a) **作者手册：`docs/USER_MANUAL.md` 5 节（开新书 / 写章 / 看 dashboard / 录编辑反馈 / 应急绕过）；编辑反馈手册：`docs/EDITOR_FEEDBACK_GUIDE.md` 3 节（评分如何录入 / case 提案审批 / 复发申诉）**⭐
- b) 仅作者手册（编辑手册让产品自己写）
- c) 简版各 1 节

### C.10 ink-learn 改造范围

**Q10**：ink-learn 改造接 case_library 怎么做？
- a) **加 `--auto-case-from-failure`**：从 `evidence_chain.checkers` blocked + cases_violated 列表里识别新失败模式 → 自动 propose 到 `data/case_library/cases/CASE-LEARN-NNNN.yaml`（pending status）；`--promote` 把 project_memory.json 模式回灌长期 ⭐
- b) 仅 `--promote`（不自动 propose case）
- c) 不动 ink-learn（M5 之外）

### C.11 周报生成

**Q11**：周报怎么自动产出？
- a) **`ink dashboard report --week N` CLI** + dry-run 累计满 N 天后自动生成 + 输出 markdown 到 `reports/weekly/<date>.md`（用户主动跑 / cron 跑都行）⭐
- b) 自动 cron 强制（依赖 launchd / systemd，跨平台烦）
- c) 仅 dashboard Web 页面看（无 markdown 文件）

### C.12 dry-run 切换决策辅助

**Q12**：M5 dashboard 是否给"M3/M4 dry-run 切真阻断"决策辅助？
- a) **是**：dashboard 显示 M3/M4 各自的 counter + 推荐切换时机（如 5 章后通过率 > 60% 才推荐切真，否则继续 dry-run）⭐
- b) 不是：M3/M4 切换由用户独立判断
- c) 由 dashboard 自动切（高风险）

### C.13 主权 case 字段

**Q13**：spec §7.4 "主权 case" 怎么实现？
- a) **case yaml 加 `sovereign: true` 字段 + Layer 5 浮现时跳过这些 case**；M3/M4 已建 cases 默认 `sovereign: false`；用户手工标 `sovereign: true` 给核心铁律 ⭐
- b) 用 severity=critical 当作 sovereign（复用现有字段）
- c) 不实现 sovereign（依赖 N=5 阈值兜底）

---

## Part D — M5 预期 user story 草拟（≈ 13 个）

| US | 标题 | 关键依赖 |
|---|---|---|
| US-001 | M5 case schema 扩展（`recurrence_history` / `meta_rule_id` / `sovereign` 字段 + 向后兼容）| M1 case_library |
| US-002 | Layer 4 `regression_tracker` 模块：检测 resolved 复发 + 写 recurrence_history + 升级 severity | M3 evidence_chain |
| US-003 | Layer 5 `meta_rule_emergence` 模块：N=5 + sim > 0.80 自动合并 → meta_rules/ 目录 + 用户审批 | LLM (glm-4.6) |
| US-004 | Dashboard 扩展：Case 治理标签页（4 大指标 + dry-run counter + 切换推荐）| v23 ink-dashboard |
| US-005 | `ink dashboard report --week N` CLI 生成 markdown 周报 | US-002 + US-004 |
| US-006 | A/B 通道：`config/ab_channels.yaml` + `--channel` flag 集成 | M3/M4 evidence_chain |
| US-007 | user_corpus history-travel 样例 + `_meta.yaml` + `ink corpus ingest` 跑通 | M2 corpus_chunking |
| US-008 | ink-learn `--auto-case-from-failure` + `--promote` 改造 | M3 evidence_chain |
| US-009 | `docs/USER_MANUAL.md` 5 节（作者手册）| 全部 |
| US-010 | `docs/EDITOR_FEEDBACK_GUIDE.md` 3 节（编辑手册）| 全部 |
| US-011 | M5 e2e 集成测试（Layer 4 + Layer 5 + dashboard report + A/B + ink-learn 6 用例）| 全部 |
| US-012 | M5 验收 + tag `m5-final` + ROADMAP/handoff 5 周计划完成标记 | 全部 |
| US-013 | (备选) M2 corpus_chunks 实跑：换 LLM provider 重跑 ingest（如有时间）| M2 deferred |

**估时**：12-13 US × ~8 分钟（M5 涉及更多模块改造，节奏略慢于 M4）≈ **2 小时**

---

## Part E — M5 风险与护栏

| # | 风险 | 缓解 |
|---|---|---|
| 1 | Layer 5 元规则误合并（语义相似但不该合并）| 用户审批门禁 (Q5) + 主权 case (Q13) + 多源验证 (spec §7.4) |
| 2 | Layer 4 跨书复发误判 | Q3 默认仅同 book 内复发触发 |
| 3 | Dashboard 改 v23 已建组件破兼容 | 加新标签页不改前 N 个标签 + 改前 cat SKILL.md 全文 |
| 4 | A/B 通道混淆 evidence_chain | evidence_chain 加 `channel: A|B|null` 字段 + dashboard 分通道展示 |
| 5 | history-travel 样例下载 / 版权 | 用 `《明朝那些事儿》` 公开节选片段 + _meta.yaml 标 `license: fair_use_excerpt` + 仅 1-2 章 |
| 6 | ink-learn `--auto-case-from-failure` 误产太多 pending case | 阈值控制：每周最多自动 propose 5 个 case + 用户审批门禁 |
| 7 | 周报生成跨平台 (Win launchd / Linux cron) | Q11 默认手动跑 / 用户自己接 cron |

---

## Part F — M5 启动命令清单

```
# 用户在新会话或本会话里说："开 M5" / "继续推" / "继续"
# 我会自动：
1. cat docs/superpowers/M-ROADMAP.md 确认 M4 ✅
2. cat docs/superpowers/M-SESSION-HANDOFF.md 确认 catch-up
3. 进入 brainstorming skill，逐题问 Part C 的 13 个问题（推荐用户选 "全采用 ⭐" 快速通道）
4. 写 docs/superpowers/specs/<日期>-m5-final-design.md
5. 写 docs/superpowers/plans/<日期>-m5-final.md
6. /prd → tasks/prd-m5-final.md
7. /ralph → prd.json + branch ralph/m5-final + 归档 M4
8. nohup bash scripts/ralph/ralph.sh --tool claude 13 > scripts/ralph/run.log 2>&1 & disown
   （注：M4 经验，必须用 nohup + disown 避免 Bash tool 父进程 SIGHUP）
```

---

## Part G — 故意不预设的事

1. Layer 5 元规则的 prompt（让 LLM 总结 N 个 case 的共性 → 元规则文本）
2. Dashboard 4 大指标的具体 SQL/jq 公式（M5 brainstorm 时用户共同设计）
3. A/B 通道在 polish-loop 与 rewrite-loop 的具体接入点（依赖 M3 现有结构）
4. user_corpus history-travel 选哪几段节选（用户决定）
5. 元规则浮现的"相似度算法"（向量 cosine vs LLM 主观评分）

---

## Part H — M5 完成 = 5 周 roadmap 全部交付

M5 ✅ 后：
- 起点编辑评分 30 → 60+ 的工业化产线**结构上闭环**（M3 章节级 + M4 策划期 + M5 dashboard/学习）
- 真实质量验证仍需用户：跑 ink-init quick → ink-plan → ink-write 一本测试书（建议 ≥ 30 章）→ 真投编辑评 → dashboard 看趋势
- 5 周 100% 完成（M2 corpus_chunks deferred 仍在，M5 US-013 可选补完）

下一步（5 周外）：
- 真实测试书出 30 章 + 投编辑评 + 拿真实 30 → ? 分数据
- 编辑反馈量产后启用 ink-learn `--promote` 周期回灌
- M2 corpus_chunks 视实际质量需要决定补完
