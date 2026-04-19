# Ink Writer Pro

[![Version](https://img.shields.io/badge/Version-18.0.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)

**一条命令，自动写 10 章并审查修复。** AI 驱动的长篇网文写作工具，专为起点/番茄等平台的商业连载设计。

---

## 功能亮点

- **一条命令批量产出**：`/ink-auto 10` 自动写 10 章，每章 2200+ 字，写完自动审查、自动修复、大纲不够自动生成
- **写 300 章不崩**：30+ 张数据表记录角色状态、伏笔、时间线，跨章语义检索确保前后一致
- **过 AI 检测**：基于 117 本起点标杆统计校准，10 层反 AI 检测（`anti-detection-checker` 第 0/1/2/3/3.5/4/5/5.5/6/8.5 层）+ 场景写作技法，从源头写出人类特征文字
- **288 条编辑建议内化**：起点金牌编辑的写作建议结构化为硬约束，不符合直接拦截重写
- **快速开书**：`/ink-init --quick` 一键生成 3 套完整方案（书名/角色/冲突/金手指），选一个直接开写
- **断点续写**：中途断了用 `/ink-resume` 从断点继续，已写章节一字不丢

---

## 安装

前提：**Python 3.12+**，以下三种平台选一个。

### Claude Code（推荐）

```bash
# 1. 安装插件
claude plugin marketplace add cipher-wb/ink-writerPro --scope user

# 2. 启用
claude plugin install ink-writer@ink-writer-marketplace --scope user

# 3. 安装依赖
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

验证：打开 Claude Code，输入 `/ink-init`，看到引导界面即安装成功。

### Gemini CLI

```bash
cd /path/to/ink-writerPro
gemini extensions install .
pip install -r requirements.txt
```

> Gemini CLI 审查步骤串行执行，速度较慢。

### Codex CLI

```bash
git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer
mkdir -p ~/.agents/skills
ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer
pip install -r ~/.codex/ink-writer/requirements.txt
# 加到 .bashrc / .zshrc：
export CLAUDE_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"
```

### RAG 配置（推荐）

写作前配置 Embedding API 可启用语义检索，大幅提升长篇记忆一致性：

```bash
# ModelScope（免费）
echo "EMBED_API_KEY=你的ModelScope密钥" >> ~/.claude/ink-writer/.env

# 或 OpenAI
echo "EMBED_BASE_URL=https://api.openai.com/v1" >> ~/.claude/ink-writer/.env
echo "EMBED_MODEL=text-embedding-3-small" >> ~/.claude/ink-writer/.env
echo "EMBED_API_KEY=你的OpenAI密钥" >> ~/.claude/ink-writer/.env
```

不配置也能写，系统自动使用 BM25 关键词检索（精度略低但完全可用）。

---

## 快速上手

### 方式一：快速模式（推荐新手）

```bash
# 1. 一键生成 3 套小说方案
/ink-init --quick

# 2. 选一个方案（输入 1/2/3），或混搭（如「1的书名+2的主角」）
# 3. 系统自动创建项目、填充设定

# 4. 规划第 1 卷大纲
/ink-plan 1

# 5. 开始写作
/ink-auto 20    # 自动写 20 章 + 审查 + 修复
```

### 方式二：深度模式（完全掌控）

```bash
# 1. 交互式采集（书名/题材/角色/世界观/金手指/创意约束）
/ink-init

# 2. 规划大纲
/ink-plan 1

# 3. 写作
/ink-auto 20
```

### 日常工作流

```bash
/ink-auto 5~10          # 每天产出 1~2 万字
# 每 5 章自动审查修复，每 20 章深度结构分析
# 大纲写完自动生成下一卷，全程无需干预

/ink-resume             # 中断了从断点继续
/ink-resolve            # 偶尔处理消歧积压
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

---

## FAQ

**Q: 写到 300 章会不会前后矛盾？**
A: 30+ 张表记录所有角色/伏笔/时间线状态，跨章语义检索自动召回相关上下文。伏笔超期自动报警，配角再出场自动加载历史状态。

**Q: `/ink-auto 100` 中途崩了怎么办？**
A: 分层检查点（v16 US-008）：每 **5** 章 review+fix / 每 **10** 章 audit quick / 每 **20** 章 audit standard+Tier2（浅）/ 每 **50** 章 Tier2（完整）+ drift 检测 / 每 **200** 章 Tier3 跨卷分析。某章写崩不影响已完成章节，用 `/ink-resume` 从断点继续。

**Q: 支持什么题材？**
A: 37 种题材模板覆盖修仙、玄幻、都市、末世、言情、悬疑、规则怪谈、系统流、电竞、历史穿越等。

**Q: 能过起点审核吗？**
A: 10 层反 AI 检测（`anti-detection-checker` 第 0/1/2/3/3.5/4/5/5.5/6/8.5 层）+ 117 本标杆统计校准 + 288 条编辑建议硬约束 + 场景写作技法，从句式、结构、风格多层面接近人类写作。

**Q: 检查点会不会很慢？**
A: 100 章总检查点开销约 7 小时，占总时间 7-14%。每 5 章检查约 15 分钟，不影响整体效率。

**Q: 不配置 RAG 能用吗？**
A: 能用。系统自动 fallback 到 BM25 关键词检索，精度略低但完全可用。推荐配置 Embedding API 以获得最佳效果。

**Q: 并发写章节（parallel>1）安全吗？**
A: ✅ **v15.9.0 起 `parallel>1` 已安全**。`PipelineManager` 在 v16 US-002 中接入 `ChapterLockManager`（同进程 `asyncio.Lock` 快速路径 + SQLite WAL 行锁跨进程 + `filelock` 兜底），单章读写与 `state.json` / `index.db` 更新均互斥串行化。推荐 `parallel ≤ 4` 以平衡吞吐与磁盘/LLM 端限流；更高并发在磁盘 IOPS 允许下技术上可行，但收益边际递减。

---

## 如何验证（v16.0.0 人感验证 SOP）

v15.9.0 引入 300 章 Shadow 压测骨架（US-017）+ Q1-Q8 质量仪表盘（US-018），所有自动化指标均可 **零 LLM 费** 复现。v16.0.0 Milestone C 在此之上补齐工程卫生：Skill 规范 30/30、Agent SDK 优化、长记忆 BM25+2 层压缩+reflection、import cycle 消除、日志规范化、章 1-3 仲裁。但自动化指标只能覆盖"不崩"；"好看不好看"需要**人**读。

**三档验证手段**：

1. **自动化（秒级）**：
   - `python3 -m benchmark.e2e_shadow_300 --chapters 300 --out reports/perf-300ch-v15.md` 跑 G1-G5 性能指标（单章耗时 / checkpoint 开销 / 内存峰值 / 崩溃率 / lock 争用）。
   - `python3 scripts/quality_dashboard.py --project <path> --out reports/quality-300ch-v15.md` 查 Q1-Q8（角色漂移 / 伏笔回收率 / 命名重复 / 爽点密度等，SQL 直查 index.db）。
   - `python3 scripts/verify_docs.py` 文档-代码数字一致性。

2. **人感验证（推荐，无可替代）**：**压测后自己读 100 / 200 / 300 三章各 10 分钟**（共 ~30 min），关注 ① 剧情是否还记得 50 章前的伏笔 / 角色状态 ② 文笔是否 AI 味（重复句式 / 空洞形容词） ③ 爽点是否还在 ④ 主角行为是否 OOC。**这是替代 AI 审读员的唯一手段**——LLM 审读会被 checker 自己的偏见污染，只有读者大脑才是真 ground truth。

3. **零回归守卫**：`pytest --no-cov` 须报 `2984 passed, 19 skipped`（v18.0.0 baseline，v16.0.0 为 2843，v15.9.0 为 2738）；任何新 US 只能让这个数字单调上涨。

---

## 版本历史

| 版本 | 说明 |
|------|------|
| **v18.0.0 (当前)** | **v17 审查 9 条 Red 全量收口（Green 合格 83.0/100）** — US-001 editor-wisdom retrieval_top_k 5→15；US-002 opening/taboo/hook 分类别召回各 ≥3 条（每章注入覆盖率 3.9% → 11.6%）；US-003 drift_detector IN+GROUP BY 分批查询（1000 章 <3s）；US-004 drift debt 增量持久化 `.ink/drift_debts.db`；US-005 PipelineManager 接入 ChapterLockManager（v15 F-003 真收口，`parallel>1` 安全）；US-006 asyncio 并发路径 10-task 持锁测试；US-007 progression/context_injection SQL ORDER BY DESC LIMIT 下推；US-008 reflection agent 消费链路显式 wire；US-009 editor-wisdom checker 解除 5000 字硬截断；US-010 creativity validator 真接入 ink-init Quick Mode（v15 F-007 真收口）；US-011 arbitrate_generic 扩展到章 ≥4；US-012 arbitration 合并矩阵配置化；US-013 anti_detection ZT 扩展到 8 条 + paired pos/neg 测试（v15 F-008 真收口）。**过审概率 [75%, 85%] → [90%, 100%]**（+15 pp），总分 71.1 → 83.0（+11.9），pytest 2843→2984 零回归。详见 `reports/audit-v18-pass-report.md` |
| v16.0.0 | **Milestone C 收口（工程卫生 + 正式发版）** — US-020 Skill 规范 30/30 修复（ink-plan allowed-tools 补齐 + CI frontmatter 审计 `scripts/verify_docs.py` 扩展 skill/agent name/description/tools 必填守卫 + high-priv tools 未附理由 warn）；US-021 **Agent SDK 优化**（prompt_cache 命中率观测 + checker 模型选型 haiku/sonnet 分层 + batch API 骨架）；US-022 **长记忆范式升级**（BM25 关键词 + 向量双路召回 + 章级/卷级 2 层压缩 + reflection-agent 每 50 章回溯沉淀）；US-023 **architecture_audit 扫描扩展**（孤儿 Python/Markdown/agent 清理 + 死代码告警）；US-024 **日志规范化**（JSON 结构化日志 + DB/state.json 来源字段统一）；US-025 **import cycle 解构**（foreshadow/plotline tracker Python 合并，切断 state ↔ index 循环依赖）；US-026 章 1-3 checker 冲突仲裁表 + ANTHROPIC_API_KEY 入口守卫 + CLAUDE.md 精简；US-027 本次发版（reports/v16-release-audit.md + tests/release/test_v16_gates.py 版本一致性 + 全维度 sanity）。**本轮明确排除**：AI 审读员（F-010b，LLM 会被 checker 偏见污染，依旧走人读 100/200/300 章 SOP）+ 真 LLM 压测（FIX-16，成本高后续单独 PRD）。pytest 2738→2843 全绿零回归 |
| v15.9.0 | **Milestone A+B 收口（止血 + creativity + 压测骨架）** — US-001~002 并发根治（ChapterLockManager 接入 PipelineManager，`parallel>1` 安全）；US-003~005 step3_runner **Phase B** 真 LLM 落地（5 gate checker_fn + polish_fn 接真 claude-sonnet-4-6，enforce E2E 阻断+降级审计）；US-006~008 FIX-11 残留清理+CI 门禁、LLM 显式 timeout、ink-auto 分层检查点 5/10/20/50/200 正式化；US-009~013 **creativity 子系统** Python 实装（name_validator 陈词+书名黑名单 / gf_validator 金手指三重约束 / sensitive_lexicon L0-L3 密度 / 扰动引擎+5 次重抽降档 / Quick Mode SKILL.md 集成）；US-014~016 anti-detection ZT 正则扩展+连接词密度、黄金三章阈值软化+整章重写逃生门、文笔维度 merged_fix_suggestion；US-017 **300 章 Shadow 压测骨架**（benchmark/e2e_shadow_300，G1-G5 性能指标，零 LLM 费）；US-018 **Q1-Q8 质量指标仪表盘**（SQL 直查，零费用，reports/quality-300ch-v15.md）；pytest 2310→2738 全绿零回归 |
| v15.0.0 | v14 审计完结 + 架构统一（FIX-17 反向传播 + FIX-18 Progressions + FIX-11 双包合并 breaking + 覆盖率 30→70） |
| v14.0.0 | **深度健康审计修复（v13 Step 2 + Step 3 合计 38 US）** — Blocker 全修（依赖声明 + pyproject + CI smoke + PipelineManager 诚实降级）；FIX-03A Memory v13 **SQL-first** 全链路闭环（StateManager.flush 顺序反转 + save_external_state + archive_manager / update_state / ink-resolve 全部迁移）；**FIX-04 step3_runner Phase A 上线**（5 个孤儿 Python gate 接入生产 + shadow 模式 + CLI + env mode 开关）；tests/editor_wisdom +227 dormant tests 激活；Step 3.5 Harness Gate 改读 index.db.review_metrics；Retriever 单例化；Style RAG 3 档降级（FAISS→subprocess 构建→SQLite fallback）；LLM + 章级 timeout；API Key 入口护栏；创意指纹 5 字段入库；孤儿表 / 僵尸 agent / 死代码清理 ~603KB；scripts/verify_docs.py CI 校验文档-代码数字一致性。pytest 2071→2310 全绿零回归 |
| v13.8.0 | ink-init --quick 创意生成架构级升级 — 三层创意体系（元规则库 M01-M10 + 种子库 schema + 扰动引擎）+ 金手指三重硬约束（非战力维度/代价可视化/一句话爆点）+ 4 档激进度（1 保守/2 平衡/3 激进/4 疯批）+ 三档语言风格（V1 文学狂野/V2 烟火接地气/V3 江湖野气）+ L0-L3 敏感词分级+档位密度矩阵 + 书名 7 种修辞标签（双关/谐音/对仗/反讽/矛盾/具象配抽象/时空错置）+ 江湖绰号库 110 条+书名模板 170 条 + 陈词黑名单扩展（神帝/至尊/龙傲天 后缀+姓×名末字笛卡儿积）+ 起点番茄双平台榜单联网反向建模（90 天缓存） + 方案输出创意指纹板块 |
| **v13.7.0** | 文笔沉浸感架构 — 电影镜头切换/感官轮换/信息密度/环境情绪共振四大法则 + prose-impact/sensory-immersion/flow-naturalness 3 个新 checker + polish Layer 9 兜底 + 24 条新文笔规则（EW-0365~0388）+ 第一章 4 项爽点硬阻断 |
| **v13.6.0** | 爽点密集化与主线加速架构级改造：大纲层爽点密度/前置原则/第1章闭环，正文层L7-L10四条新铁律，审查层卖点密度/摄像头检测/OOC本能违反/文笔工艺质量，润色层文笔工艺兜底 |
| **v13.5.0** | Narrative Coherence Engine：否定约束管线（Data→Context→Writer→Checker全链路）、场景退出快照、Writer自洽回扫(Step 2A.1)、角色连续性📌预警、O7否定约束违反检测、L9枚举完整性检测。从根源杜绝凭空编造和章内矛盾 |
| **v13.4.0** | Token & Time 优化：审查包按checker瘦身(-30% Step3)、logic计算型预检、Step 2B条件降级、Context空值裁剪、Data-Agent纯JSON输出、Prompt结构cache优化。目标30min→20min，token整体-35%，质量零下降（内置验证脚本） |
| **v13.3.0** | 字数上限收紧（4000字硬上限）+ 双层进度条（内层12步骤/外层章节级 + 检查点子步骤追踪） |
| **v13.2.0** | **Logic Fortress 逻辑防崩体系**：新增 MCC 强制合规清单、logic-checker（8层章内微观逻辑验证）、outline-compliance-checker（6层大纲合规验证），Writer-Agent 5条逻辑铁律 + MCC自检机制，Step 3 硬阻断门禁，两层防线消除大纲偏离和章内逻辑矛盾 |
| v13.1.0 | **效率优化与项目瘦身**：ink-init --quick 快速随机模式、防重复角色命名系统、项目文件清理、README 面向用户重写 |
| v13.0.0 | **Deep Review & Perfection**：27 US / 6 Phase 端到端优化。追读力+爽点调度器+情绪心电图+Style RAG+句式多样性硬门禁+SQLite记忆图谱+伏笔/明暗线生命周期追踪+人物语气指纹+双agent目录消除+章节并发+prompt cache |
| v12.0.0 | **编辑星河写作智慧集成**：288份编辑建议→364条原子规则→FAISS向量索引，editor-wisdom-checker + 硬门禁闭环 |
| v11.5.0 | 跨章遗忘bug根因修复：previous_chapters窗口扩展+伏笔空值兜底+SQL schema对齐 |
| v11.4.0 | 写作质量提升：TTR词汇多样性+首句钩子+伏笔分级+角色语气指纹+微观意外感+反套路检测 |
| v11.3.0 | 工程深度审查全量修复(22项)：计算型闸门+死亡状态标准化+mega-summary+伏笔统一+黄金三章契约 |
| v11.0.0 | Style RAG风格参考库(3295片段)+统计层修复+记忆系统升级 |
| v9.0.0 | Harness-First 架构：计算型闸门 + Reader Agent 升格 |
| v8.0.0 | 14 Agent 全规范化 + 风格锚定 + 批量恢复 |

---

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。
