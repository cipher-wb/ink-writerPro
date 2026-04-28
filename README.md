# Ink Writer Pro

[![Version](https://img.shields.io/badge/Version-26.3.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-blue.svg)]()

**一条命令，自动写 10 章并审查修复。** AI 驱动的长篇网文写作工具，专为起点/番茄等平台的商业连载设计。

---

## 功能亮点

- **一条命令批量产出**：`/ink-auto 10` 自动写 10 章，每章 2200+ 字，写完自动审查、自动修复、大纲不够自动生成
- **写 300 章不崩**：30+ 张数据表记录角色状态、伏笔、时间线，跨章语义检索确保前后一致
- **过 AI 检测**：基于 117 本起点标杆统计校准，标点指纹零容忍 + 装逼词黑名单 + 白话度门禁 + 直白度七维评分 + 爆款示例 RAG few-shot + Hard Block Rewrite Mode，从标点、词汇、句式、结构多层消除 AI 痕迹
- **288 条编辑建议内化**：起点金牌编辑的写作建议结构化为硬约束，不符合直接拦截重写
- **快速开书**：`/ink-init --quick` 一键生成 3 套完整方案（书名/角色/冲突/金手指），选一个直接开写
- **断点续写**：中途断了用 `/ink-resume` 从断点继续，已写章节一字不丢
- **Debug Mode 自我观察**（v26.3+）：写作全链路自动记录"AI 偷懒/契约脱节/工作流偏航"等事件到 `<project>/.ink-debug/`（JSONL + SQLite 双层），`/ink-debug-report` 一键出双视图 markdown 喂给 AI，闭环改 SKILL.md。零侵入、默认开、`INK_DEBUG_OFF=1` 一键关。详见 [docs/USER_MANUAL_DEBUG.md](docs/USER_MANUAL_DEBUG.md)
- **跨平台**：macOS + Windows 原生支持，同一套数据格式，无缝切换。Windows 特有故障速查：[docs/windows-troubleshooting.md](docs/windows-troubleshooting.md)

---

## 系统要求

| 组件 | 最低版本 |
|------|----------|
| Python | 3.12+ |
| Claude Code | 最新版 |

**支持平台**：macOS 12+ / Windows 10/11（原生，无需 WSL）

---

## 安装

### Claude Code（推荐）

**macOS / Linux：**

```bash
# 1. 安装插件
claude plugin marketplace add cipher-wb/ink-writerPro --scope user

# 2. 启用
claude plugin install ink-writer@ink-writer-marketplace --scope user

# 3. 安装依赖
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

**Windows（PowerShell）：**

```powershell
# 1. 安装 Python 3.12+
winget install Python.Python.3.12

# 2. 安装依赖
py -3 -m pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt

# 3. 安装插件
claude plugin marketplace add cipher-wb/ink-writerPro --scope user
claude plugin install ink-writer@ink-writer-marketplace --scope user
```

验证：打开 Claude Code，输入 `/ink-init`，看到引导界面即安装成功。

### Gemini CLI

```bash
cd /path/to/ink-writerPro
gemini extensions install .
pip install -r requirements.txt
```

### Codex CLI

```bash
git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer
mkdir -p ~/.agents/skills
ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer
pip install -r ~/.codex/ink-writer/requirements.txt
export CLAUDE_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"
```

### RAG 配置（推荐）

写作前配置 Embedding API 可启用语义检索，大幅提升长篇记忆一致性：

**macOS / Linux：**
```bash
# ModelScope（免费）
echo "EMBED_API_KEY=你的ModelScope密钥" >> ~/.claude/ink-writer/.env

# 或 OpenAI
echo "EMBED_BASE_URL=https://api.openai.com/v1" >> ~/.claude/ink-writer/.env
echo "EMBED_MODEL=text-embedding-3-small" >> ~/.claude/ink-writer/.env
echo "EMBED_API_KEY=你的OpenAI密钥" >> ~/.claude/ink-writer/.env
```

**Windows：**
```powershell
# ModelScope（免费）
echo "EMBED_API_KEY=你的ModelScope密钥" >> "$env:USERPROFILE\.claude\ink-writer\.env"

# 或 OpenAI
@"
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=你的OpenAI密钥
"@ | Out-File -Append "$env:USERPROFILE\.claude\ink-writer\.env" -Encoding utf8
```

不配置也能写，系统自动使用 BM25 关键词检索（精度略低但完全可用）。

---

## 快速上手

### 快速模式（推荐新手）

```
/ink-init --quick      # 生成 3 套小说方案，选一个直接开写
/ink-plan 1            # 规划第 1 卷大纲
/ink-auto 20           # 自动写 20 章 + 审查 + 修复
```

### 深度模式（完全掌控）

```
/ink-init              # 交互式采集（书名/题材/角色/世界观/金手指/创意约束）
/ink-plan 1            # 规划大纲
/ink-auto 20           # 写作
```

### 日常工作流

```
/ink-auto 5~10         # 每天产出 1~2 万字
                       # 每 5 章自动审查修复，每 20 章深度结构分析
                       # 大纲写完自动生成下一卷，全程无需干预
/ink-resume            # 中断了从断点继续
/ink-resolve           # 偶尔处理消歧积压
```

---

## 命令速查

| 命令 | 说明 |
|------|------|
| `/ink-init` | 创建新项目（深度交互采集设定） |
| `/ink-init --quick` | 快速模式：生成 3 套方案，选一个直接开写 |
| `/ink-auto N` | **主力命令**：写 N 章 + 自动审查修复 + 自动规划 |
| `/ink-plan N` | 规划第 N 卷大纲 |
| `/ink-write` | 手动写一章（完整流水线） |
| `/ink-review 1-5` | 手动审查指定章节 |
| `/ink-resume` | 中断恢复，从断点继续 |
| `/ink-fix` | 自动修复审查发现的问题 |
| `/ink-audit` | 数据一致性审计 |
| `/ink-macro-review` | 跨 50/200 章宏观结构分析 |
| `/ink-query` | 查询角色/伏笔/关系状态 |
| `/ink-resolve` | 处理低置信度实体消歧 |
| `/ink-learn` | 提取成功写作模式 |
| `/ink-dashboard` | 启动可视化管理面板 |
| `/ink-migrate` | 旧版项目迁移到新架构 |
| `/ink-debug-status` | 看 Debug Mode 当前状态（开关 + 24h 摘要） |
| `/ink-debug-report` | 出 markdown 双视图报告（喂给 AI 做软件迭代） |
| `/ink-debug-toggle` | 临时切换 debug 开关，无需手编 yaml |

---

## FAQ

**Q: 写到 300 章会不会前后矛盾？**
A: 30+ 张表记录所有角色/伏笔/时间线状态，跨章语义检索自动召回相关上下文。伏笔超期自动报警，配角再出场自动加载历史状态。

**Q: `/ink-auto 100` 中途崩了怎么办？**
A: 分层检查点：每 5 章 review+fix / 每 10 章 audit quick / 每 20 章 audit standard / 每 50 章 Tier2 完整 + drift 检测 / 每 200 章 Tier3 跨卷分析。用 `/ink-resume` 从断点继续。

**Q: 支持什么题材？**
A: 37 种题材模板覆盖修仙、玄幻、都市、末世、言情、悬疑、规则怪谈、系统流、电竞、历史穿越等。

**Q: 能过起点审核吗？**
A: 七层文笔反 AI 改造（标点指纹零容忍/装逼词黑名单+替换映射/白话度五维门禁/直白度七维评分/writer-agent 对话+动作驱动律/爆款示例 RAG few-shot/Hard Block Rewrite Mode）+ 117 本标杆统计校准 + 288 条编辑建议硬约束 + 场景写作技法，从标点、词汇、句式、结构多层面接近人类写作。

**Q: Windows 上怎么用？**
A: 和 Mac 完全一样。装好 Python 3.12+ 和 Claude Code，安装插件后直接用。所有 `/ink-*` 命令在两个平台上行为一致。底层 PowerShell 脚本（`.ps1`）和 bash 脚本（`.sh`）并行维护，SKILL.md 按平台自动选择。遇到 UTF-8 乱码 / PowerShell 执行策略 / symlink 权限 / index.db 锁冲突等 Windows 特有问题，见 [docs/windows-troubleshooting.md](docs/windows-troubleshooting.md)。

**Q: 不配置 RAG 能用吗？**
A: 能用。系统自动 fallback 到 BM25 关键词检索，精度略低但完全可用。推荐配置 Embedding API 以获得最佳效果。

**Q: 并发写章节（parallel>1）安全吗？**
A: 安全。`PipelineManager` 接入 `ChapterLockManager`（asyncio.Lock + SQLite WAL 行锁 + filelock 兜底），单章读写互斥串行化。推荐 `parallel <= 4`。

---

## 验证安装

**macOS / Linux：**
```bash
python3 -c "import ink_writer; print('OK')"
```

**Windows：**
```powershell
py -3 -c "import ink_writer; print('OK')"
```

看到 `OK` 即安装成功。打开 Claude Code 输入 `/ink-init` 确认插件加载正常。

---

## 版本历史

| 版本 | 说明 |
|------|------|
| **v26.3.0 (当前)** | **Debug Mode v0.5 — 软件自观察 + 离线迭代闭环**。新增"上帝视角"观察层：写作流程自动记录 AI 偷懒/契约脱节/硬错误等事件到 `<project>/.ink-debug/`（JSONL + SQLite 双层），不打断主流程。3 上游接入（Claude Code hooks / 5 个已有 checker 输出标准化 / 5 个轻量 invariant）→ 单 collector 总线 → 2 下游消费（per-chapter 收尾摘要 / per-batch markdown 报告 + `/ink-debug-report` 双视图）。9 条 acceptance 全过、73 个测试零回归。配套 `docs/USER_MANUAL_DEBUG.md` 使用说明书 + spec/plan 全程 brainstorm 记录。回滚：`master_enabled: false` 或 `INK_DEBUG_OFF=1` 一键关。v1.0 押后：layer D 对抗复核 / 自动 fix PR / 跨项目聚合 / 周报 cron。 |
| v26.2.0 | 新增番茄小说平台模式（fanqie）：init 可选平台 → plan/write/auto/checker/prose 全链路按平台区分。番茄独有：1500字/章、每500字爽点、直白打脸冲突、章末钩子硬阻断、colloquial 强制激进档、反AI追加25字复合句规则。 |
| **v26.1.0** | **Prose Anti-AI Overhaul — 文笔反 AI 味 + 爆款白话化深层重构** — 七层改造根治三大痛点：AI 化标点、行文绕读着累、装逼词藻堆叠。**第 1 层**：5 条标点 AI 指纹零容忍规则（双破折号/智能引号/英式连字符/过密顿号/过用省略号）。**第 2-3 层**：90+ 装逼词黑名单 × 3 域 + replacement_map 爆款替换。**第 4-5 层**：colloquial-checker 白话度 C1-C5 五维门禁 + directness-checker 扩展 D1-D7 七维全场景爆款档。**第 6 层**：writer-agent L12 对话+动作驱动律 + 爆款示例 RAG few-shot（语义检索引擎 + prompt 注入）。**第 7 层**：polish-agent Hard Block Rewrite Mode（三门禁任一 red → 全章 LLM 重写 → 复检 → hard_blocked exit code 2）。**评估+回滚**：5+5 基线校准脚本 + E2E 旧/新 pipeline 对照评估 + 三个独立回滚开关 + 总开关保证可降级。pytest 3808 → 3865 passed（+57 新测试，零回归）。`ralph/prose-anti-ai-overhaul`。 |
| v26.0.0 | **5 周质量治理 roadmap 100% 完成 — M3 + M4 + M5 三大 milestone 一次性发布** — 起点编辑评分 30/100 → 60+/100 的工业化产线**结构闭环**。**M5（v26）**：Layer 4 复发追踪（resolved → regressed 升 severity）+ Layer 5 元规则浮现（N=5 + LLM similarity > 0.80 提议合并 → 用户审批 `ink meta-rule {list,approve,reject}`）+ dashboard "M5 Case 治理" 标签页（4 大指标 + M3/M4 dry-run counter + 切换推荐）+ 周报 CLI（`ink dashboard report --week N` 输出 `reports/weekly/<year>-W<NN>.md`）+ A/B 通道（`config/ab_channels.yaml` + `--channel A\|B` flag + evidence_chain 加 channel 字段，向后兼容）+ user_corpus history-travel 样例 + ink-learn 改造（`--auto-case-from-failure` 每周限 5 + `--promote` 短期 → 长期）+ 作者手册 `docs/USER_MANUAL.md` 5 节 + 编辑反馈手册 `docs/EDITOR_FEEDBACK_GUIDE.md` 3 节。case schema 加 3 字段（`recurrence_history` / `meta_rule_id` / `sovereign`）向后兼容现有 410 active cases。pytest 3593 → 3808 passed（M3+M4+M5 累计 +215 新测试，零回归；含 `tests/integration/test_m4_e2e.py` 7 用例 + `tests/integration/test_m5_e2e.py` 6 用例）。tag `m5-final` 已 push 到 origin。 |
| v25.0.0 | **M4 P0 上游策划层 — ink-init / ink-plan 阶段强制策划期审查** — 在开新书阶段把 spec §1.3 编辑诊断的 5/8 上游扣分（题材老套 / 金手指模糊 / AI 起名 / 主角动机牵强 / 金手指出场过晚 / 主角骨架级被动 / 章节钩子稀疏）阻断在策划期。新增 7 个 checker：4 个 ink-init（`genre-novelty-checker` LLM 比对起点 top200 / `golden-finger-spec-checker` 4 维度 LLM / `naming-style-checker` 纯规则起名词典 / `protagonist-motive-checker` 3 维度 LLM）+ 3 个 ink-plan（`golden-finger-timing-checker` regex+LLM 双重 / `protagonist-agency-skeleton-checker` 卷骨架级 / `chapter-hook-density-checker`）。配套 2 个数据资产：起点 top200 简介库爬虫（合规：robots.txt + 1 req/s 限速 + UA 礼貌；如反爬触发则 manual-fallback）+ LLM 高频起名词典 331 条 + 24 首字 + 24 末字字根模式（`data/market_intelligence/llm_naming_blacklist.json`）。7 个上游 seed cases（`CASE-2026-M4-0001~0007`）batch approve 入活。`planning_evidence_chain.json` schema（复用 M3 evidence_chain + `phase` 字段向后兼容）+ `--skip-planning-review` 紧急绕过 + `data/.planning_dry_run_counter` 独立护栏。`ink-init` / `ink-plan` SKILL.md 末尾追加 Step 99 章节（含 PowerShell sibling）。tag `m4-p0-planning`。 |
| v24.0.0 | **M3 P1 下游闭环 — writer-self-check + 阻断重写 + evidence_chain** — 30→50 分质量拐点。把 M2 备齐的 403 cases 注入 writer 链路：写完比对 → 阻断 → 病例驱动重写 → 通过 → 复发监测。新增 `ink_writer/writer_self_check/`（rule_compliance + cases_addressed/violated）+ 2 个章节级 checker（`conflict-skeleton-checker` + `protagonist-agency-checker`）+ rewrite_loop orchestrator（max 3 轮 + 一次一个 case 按 severity 排序 + needs_human_review 兜底 + 4 版保留）+ 现有 3 checker 升级阻断（`reader_pull / sensory_immersion / high_point` 通过 `block_threshold_wrapper`）+ `evidence_chain.json` schema 强制必带（缺则 `EvidenceChainMissingError`）+ dry-run 5 章 auto-switch 真阻断 + 自动出 dry_run_report 报告 + ink-write SKILL.md Step 1.5 集成。`config/checker-thresholds.yaml` 集中阈值（M3 8 段）。LLM 切 glm-4.6（M2 切片用 glm-4-flash）。pytest 3593 → 3700+ passed（M2 partial baseline + M3 +14 US 新测试零回归）。tag `m3-p1-loop`。 |
| v23.0.0 | **章节字数硬上限对等硬下限 — 删除 LLM 自行豁免路径** — 修复上下限非对称硬化：旧版 `check_word_count` 对超 max_words 仅返回 `severity='soft'`、`ink-auto.sh` 只卡 <2200 单侧、SKILL.md 2A.5 的 >4000 字规则有"关键战斗章/高潮章/卷末章可放行"被 LLM 自我滥用豁免、用户写入 `preferences.json` 的 `pacing.chapter_words` 无任何 caller 读取（实际事故：第 1 章写出 1 万字审查仅软警告放行）。v23 让字数上限与下限对等硬约束，彻底删除 LLM 自行豁免路径：(1) `check_word_count` 新增 `max_words_hard/max_words_soft` 双阈值，超 hard 必返 `severity='hard'`；(2) 新增 `ink_writer/core/preferences.py::load_word_limits` 读取 `pacing.chapter_words` ±500 推导 `[min, max_hard]`，硬下限 2200 永不降（`MIN_WORDS_FLOOR` 红线）；(3) `extract_chapter_context.build_chapter_context_payload` 注入 `target_words_min/max` 透传到执行包，writer-agent 起草阶段硬约束；(4) `ink-auto.sh/ps1` 对称增补 `> MAX_WORDS_HARD` 分支 + 精简循环 `SHRINK_MAX_ROUNDS=3`（下限补写 1 轮不变零回归）；(5) SKILL.md 2A.5 删除按章型/百分比的 LLM 自判豁免条款（`关键.*章.*豁免 \| 上浮 33%` 全仓零匹配）。pytest 3206 → 3593 passed（US-001/002/003/004/006 累计 +40 新测试：word_count 双阈值 4 + preferences 加载 14 + execution pack 注入 7 + ink-auto 上限分支 14 + E2E fixture 5；零回归） |
| v22.0.0 | **场景感知直白化 — 黄金三章 + 战斗/高潮/爽点** — 用户反馈"文邹邹、读起来费劲"的根因：writer-agent L10b/L10e 全局感官丰富度硬约束（每 800 字非视觉感官、主导感官轮换含触觉+嗅觉）在爽点场景产出冗余描写。v22 建立场景感知直白化链路：context-agent 暴露 `scene_mode`（7 值 + 优先级）→ writer-agent `## Directness Mode` 硬约束（每句服务剧情/心理/冲突；禁抽象形容词堆叠、空境描写、本体抽象比喻；强动词+具体名词）→ 新 `directness-checker`（5 维度 0-10 评分，消费 50 本起点 1487 章基线阈值）→ polish-agent `## Simplification Pass`（107 条黑名单 + 长句拆分 + 修辞压缩 + 70% 字数下限保护）→ editor-wisdom 新增 simplicity 主题域（14 条规则，场景感知召回≥5）。冲突解耦：Directness Mode 激活时 L10b/L10e + sensory-immersion-checker 暂挂；prose-impact / flow-naturalness 12 条 rule codes 在 arbitration 阶段软豁免，checker 本体零 prompt drift。激活判定单源 `directness_checker.is_activated`。M-1~M-7 corpus-grounded 验证：AI-heavy fixture 缩短 26.91% / 直白 Top-5 × ch1-3 均分 9.33 / 黑名单命中 2/章 / 句长中位数对齐 benchmark IQR / 非直白零退化。pytest 3206 → 3548 passed（+342 新测试，零回归） |
| v21.0.0 | **跨平台端到端审计与双端一等公民** — 9 类风险全盘扫描（`scripts/audit_cross_platform.py` 202 findings → 3 合法 fixture，C1~C9 逐类清零）；Mac + Windows 双端 e2e smoke 脚本（`scripts/e2e_smoke.{sh,ps1,cmd}` + `e2e_smoke_harness.py`）支持中文+空格路径，Mac 本地实跑 3 章 init/write/verify/cleanup 全绿；ralph.sh COMPLETE 信号行锚定 + `pipefail` + LLM_EXIT 诊断日志；ink-auto `run_cli_process` / `Invoke-CliProcess` 子进程退出码日志 + checkpoint-utils Python stderr 入 debug log（原 `/dev/null` 黑洞）；pytest 跨平台 marker 统一（`@pytest.mark.windows` / `@pytest.mark.mac`）+ 仓库红线守护禁用 `skipif(sys.platform)` 回退；docs/windows-troubleshooting.md 12 条故障速查。Mac 字节级一致承诺全程保持，全量 pytest 3021 → 3206 passed（+185 新测试，零回归） |
| v20.0.0 | **前三章全文注入 — 从根上消灭前后文细节遗忘** — 写第 N 章时硬注入 n-1/n-2/n-3 三章完整正文 + n-4~n-10 摘要，让 writer-agent 以前三章全文为首要参考，彻底解决摘要驱动写作的细节丢失。三 agent 同步改造：context-agent 硬注入 `recent_full_texts`、writer-agent 新增"首要参考"段与起草前 pre-draft checklist（位置/道具/伏笔/对白四项）、continuity-checker 五层校验并回填 `evidence:{source_chapter,excerpt}` 证据。Token 预算 protected sections 不参与超预算裁剪，双档阈值 soft 60k / hard 180k。pytest 2984 → 3021 passed（+37 新测试，零回归） |
| v19.0.0 | **Windows 原生兼容** — macOS/Windows 双平台一等公民支持。新增 PowerShell 脚本（`.ps1` + `.cmd`）与 bash 脚本字节级等价；Python 全量 `encoding="utf-8"` 补齐 + asyncio Proactor 策略 + symlink 降级 + UTF-8 stdio 引导；CI 矩阵加 `windows-latest`；SKILL.md 双平台执行块；`.sh` 文件字节不变，Mac 零影响。pytest macOS 2984 passed / Windows 2890 passed，双平台零回归 |
| v18.0.0 | v17 审查 9 条 Red 全量收口（Green 合格 83.0/100）— retrieval_top_k 5->15、分类别召回、drift_detector 分批查询、drift debt 增量持久化、ChapterLockManager 接入、asyncio 并发路径持锁测试、SQL ORDER BY DESC LIMIT 下推、reflection agent 消费链路、editor-wisdom 解除 5000 字硬截断、creativity validator 接入 Quick Mode、arbitrate_generic 扩展到章>=4。过审概率 [75%,85%]->[90%,100%]，总分 71.1->83.0 |
| v16.0.0 | Milestone C 收口（工程卫生 + 正式发版）— Skill 规范 30/30、Agent SDK 优化、长记忆 BM25+2 层压缩+reflection、import cycle 消除、日志规范化、章 1-3 仲裁。pytest 2738->2843 |
| v15.9.0 | Milestone A+B 收口（止血 + creativity + 压测骨架）— 并发根治、step3 Phase B 真 LLM、分层检查点 5/10/20/50/200、creativity 子系统、anti-detection ZT 扩展、300 章 Shadow 压测骨架、Q1-Q8 质量仪表盘。pytest 2310->2738 |
| v15.0.0 | v14 审计完结 + 架构统一 |
| v14.0.0 | 深度健康审计修复（38 US）— Blocker 全修、Memory SQL-first 全链路、step3 Phase A、dormant tests 激活、Style RAG 3 档降级。pytest 2071->2310 |
| v13.8.0 | ink-init --quick 创意生成架构级升级 — 三层创意体系 + 金手指三重硬约束 + 4 档激进度 + 三档语言风格 + 敏感词分级 + 书名 7 种修辞标签 |
| v13.7.0 | 文笔沉浸感架构 — 电影镜头切换/感官轮换/信息密度/环境情绪共振四大法则 + 3 个新 checker |
| v13.6.0 | 爽点密集化与主线加速架构级改造 |
| v13.5.0 | Narrative Coherence Engine：否定约束管线全链路闭环 |
| v13.0.0 | Deep Review & Perfection：27 US / 6 Phase 端到端优化 |
| v12.0.0 | 编辑星河写作智慧集成：288 份编辑建议 -> 364 条原子规则 -> FAISS 向量索引 |
| v9.0.0 | Harness-First 架构 |
| v8.0.0 | 14 Agent 全规范化 + 风格锚定 |

---

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。
