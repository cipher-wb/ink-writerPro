# Ink Writer Pro v13.8.0 深度健康审计总报告 (v5)

> **审计周期**：2026-04-17 单日完成 12 份子审计（US-001 ~ US-012）
> **审计范围**：架构/主链路/checker/RAG/创意/数据层/工程/死代码/承诺/bug/开源对比 全维度
> **审计模式**：只读，不修改任何源码；每个发现附 `file:line` 证据
> **执行者**：Claude Opus 4.7（1M context），分 12 个独立子任务
> **受审版本**：ink-writer v13.8.0（HEAD=349f651）
> **用户画像**：作者自用（非对外发布），语言锐利，不避讳批评

---

## Executive Summary

### 健康度总评：**54 / 100**（分维度分拆如下）

| 维度 | 分数 | 评语 |
|------|:---:|------|
| 工程骨架 / 功能密度 | **72** | 14 skill + 17 checker + 34 表 + 4 SQLite DB + 三套 RAG，功能面广 |
| 测试基建 | **55** | 2028 tests、0 collect error、测试/源码 60%；但覆盖率门禁 70% 名存实亡（实测 13.6%） |
| 质量防线（checker + gate） | **50** | 规格完备、Python 实现齐全，但核心门禁 **5/5 无生产调用者**，全靠 LLM 自律 |
| 落地度 / 规格-生产对齐 | **40** | Memory v13 文档与代码方向相反、creativity 引擎仅 markdown 伪代码、Style RAG 开箱即 broken |
| 文档诚信度 | **50** | README 承诺兑现率 88.9%；但 agent/checker/table 数量 3 处漂移、性能声称零实证 |
| 工程卫生（依赖/日志/异常） | **35** | 6 个核心依赖未声明（CI 绿是幻觉）、432 print vs 14 logging、`api_client.py` retry 用 print |
| 独特定位 | **90** | 全球唯一把起点/番茄编辑审核规则 RAG 化为硬约束，无直接竞品 |

### 三句话结论

1. **功能密度全球一流，工程卫生严重滞后**：ink-writer 在"中文网文商业连载 × 高自动化 × 硬门禁质检"这个交叉赛道**几乎无对手**（US-012），但代码层面沉积了 15+ 次大改造的尾巴，形成系统性"规格完备 + 生产未接入"断层。
2. **最危险的病根不是某个具体 bug，而是"文档以为做了、代码实际没做"的错配**：Memory v13 架构方向相反、Step 3.6-3.10 五个 Python 门禁零生产调用、Creativity 扰动引擎全是 markdown 伪代码、Style RAG 开箱即 broken。用户跑一次 `/ink-auto` 看上去全绿，实则一半质检是 LLM 在演。
3. **可修复，路径清晰**：12 份子报告的发现相互印证，修复并不需要推倒重来——补齐 `ink_writer/` 的 6 个依赖声明 / 接入 `CheckerRunner` + 5 个 gate / 切换 ink-resolve 走 SQLite，这三件事就能把分数从 54 推到 70+。

### 一句话回答用户 Q1-E："这个项目现在处于什么水平"

> **"功能是 A 级作家助手，工程是 C+ 实习生交付。代码量和规格深度远超开源同类，但落地率只有 60%——规格-代码 gap 是整个项目的头号技术债，其它问题本质都是它的次级症状。"**

---

## Top 10 Findings（全项目最严重，按严重度排序）

| # | 严重度 | 标题 | 核心证据 | 影响 | 子报告 |
|---|:---:|------|---------|------|--------|
| 1 | 🔴 Blocker | **PipelineManager 并发未接 ChapterLockManager**，docstring 声称保护实际零引用 | `ink_writer/parallel/pipeline_manager.py:5,177-181`（docstring vs 代码）；全文件 0 次 `ChapterLockManager` import | N 章并发时多进程写同一 `state.json` + `index.db`，角色 fingerprint / plotline 状态可能 lost update | [10](docs/audit/10-bug-scan.md) |
| 2 | 🔴 Blocker | **`ink_writer/` 6 个核心依赖未声明**（numpy/faiss-cpu/PyYAML/jsonschema/sentence-transformers/anthropic），CI 绿是幻觉 | `scripts/requirements.txt:4-10` 仅 3 包；`ink_writer/**/*.py` 17 文件顶层 `import yaml/numpy/faiss/jsonschema/sentence_transformers` 零 try/except | 干净 runner 第一次 `/ink-init --quick` 就 ImportError；开源用户按 README 安装直接翻车 | [7](docs/audit/07-engineering-quality.md) |
| 3 | 🔴 Blocker | **Memory v13 文档方向与代码相反**：docs 说"SQLite 是事实源、state.json 是视图"，代码先写 state.json 再同步 SQL | `ink-writer/scripts/data_modules/state_manager.py:413-421` 先 `atomic_write_json(state.json)`，`:467` 同步失败仅 warning | 新开发者/AI 被误导、`ink-resolve` 直写 state.json 绕过 SQL → SQLite 和 JSON 漂移 | [1](docs/audit/01-version-archaeology.md) · [6](docs/audit/06-data-layer-audit.md) |
| 4 | 🟠 Critical | **checker_pipeline 249 行 + 25 测试，零生产调用者**；Step 3 并发编排全靠 LLM 遵守 prompt | `Grep "from ink_writer.checker_pipeline"` 全仓仅 `__init__.py` + tests；`runner.py:174-178` 定义 cancel_event 但永远不触发 | v13 规划的"统一 Python orchestration + 早失败"从未兑现；并发度可被 LLM 随意改变无审计 | [2](docs/audit/02-writing-pipeline-trace.md) · [3](docs/audit/03-checker-matrix.md) |
| 5 | 🟠 Critical | **Step 3.6-3.10 五个 Python 门禁规格完备、生产零调用** | `Grep "from ink_writer\." ink-writer/scripts/` 从未命中 reader_pull/emotion/anti_detection/voice_fingerprint/plotline；`hook_retry_gate.py:86`、`emotion_gate.py:86`、`anti_detection_gate.py:130`、`ooc_gate.py:87`、`plotline/tracker.py:129` 均完整 | 追读力/情绪/AI味/语气/明暗线全部阈值判定由 LLM 主观执行；"2 次重试阻断"纸上谈兵 | [2](docs/audit/02-writing-pipeline-trace.md) |
| 6 | 🟠 Critical | **Step 3.5 Harness Gate 读死路径**：`step3_harness_gate.py:18-85` 读 `.ink/reports/review_ch*.json`，上游无任何代码产出该文件 | 生产只写 `index.db.review_metrics`、`harness_evaluations`；`step3_harness_gate.py:24` 命中 `if not reports_dir.exists(): return  # 无报告默认通过` | Harness gate 100% 静默 PASS，等同未实现 | [2](docs/audit/02-writing-pipeline-trace.md) · [3](docs/audit/03-checker-matrix.md) |
| 7 | 🟠 Critical | **Style RAG 开箱即 broken** + **semantic_recall 10 个项目零激活** | `data/style_rag/` 目录默认不存在，`StyleRAGRetriever()` 抛 `FileNotFoundError`；用户环境 10 个 AI 项目均有 `.ink/vectors.db`（远端 RAG），均无 `.ink/chapter_index/`（本地 FAISS） | "三套 RAG 协同"在默认部署下实际只有 editor_wisdom 一套工作；style_rag 被 `style_sampler.py` SQLite 平行路径绕过，FAISS retriever 在生产中从未被消费 | [4-static](docs/audit/04-rag-audit.md) · [4-live](docs/audit/04-rag-live-trace.md) |
| 8 | 🟠 Critical | **Creativity 引擎全为 markdown 伪代码**：扰动算法/GF三重校验/V1V2V3分档/5次重抽降档 全仓零 Python | `grep -r 'def draw_perturbation\|def pick_pattern' --include='*.py'` 命中 0；`init_project.py` 903 行 0 次 `quick/aggression/perturbation/meta_rule` | 所谓"硬约束校验 + 重抽/降档"完全依赖 LLM 每次运行时自觉执行；同一 prompt 不同 session 结果漂移 | [5](docs/audit/05-creativity-audit.md) |
| 9 | 🟠 Critical | **创意指纹字段不落盘**：`init_project.py` 903 行不识别 `meta_rules_hit/perturbation_pairs/gf_checks/style_voice/market_avoid` 等 Quick 产物 | `init_project.py` CLI 参数表（:787-802）+ `state_schema.py` 数据模型均无上述字段 | 创意产物无法被下游 plan/write/review 读取做一致性校验；用户重跑 `--quick` 后档位信息丢失 | [5](docs/audit/05-creativity-audit.md) |
| 10 | 🟠 Critical | **性能承诺零实证**：README FAQ "100 章 7 小时"公式反推 ≈ 12.5 小时；`benchmark/300chapter_run/metrics.json` wall_time=8.1s、G1-G5 全 0 | `scripts/run_300chapter_benchmark.py:215-245` 不收集真实指标；`reports/v13_acceptance.md:8` "总耗时 8s \| FAIL" | 用户按 README 规划时间，实际操作时差 78%；无任何 300 章端到端证据 | [9](docs/audit/09-promise-vs-reality.md) |
| 11 | 🟡 Major | **孤儿表 + 孤儿模块 + 僵尸 agent** | `protagonist_knowledge` 表建了 INSERT/SELECT 各 0 处；`ink_writer/incremental_extract/` 生产 import 0；`foreshadow-tracker.md`/`plotline-tracker.md` 已合并仍存在 | 维护负担 2-3 倍；新开发者误以为功能存在 | [1](docs/audit/01-version-archaeology.md) · [6](docs/audit/06-data-layer-audit.md) · [8](docs/audit/08-unused-resources.md) |
| 12 | 🟡 Major | **pytest 覆盖率门禁名存实亡**：`pytest.ini:8` 声明 `--cov-fail-under=70`，`scripts/` 实测 13.62% | `state_manager.py (9%)`、`extract_chapter_context.py (0%)`、`step3_harness_gate.py (0%)`、`init_project.py (8%)` 近乎零覆盖 | "门禁存在"是错觉，核心文件处于祈祷式上线；CI 绿靠只跑子集 | [7](docs/audit/07-engineering-quality.md) |
| 13 | 🟡 Major | **双 Python 包 / 双 scripts 目录未真解决**（US-402 只处理 agent 层） | `ink_writer/`（下划线）17 子目录 + `ink-writer/scripts/data_modules/`（横杠下划线）37 文件，`pytest.ini:3` 两个都加 pythonpath | 新模块放哪没明文规则、tab 补全选错、`from ink_writer.x` vs `from data_modules.x` 易拼错 | [1](docs/audit/01-version-archaeology.md) |
| 14 | 🟡 Major | **API Key 护栏缺失** + **per-file `except continue` 假成功** | `03_classify.py:188-197`、`05_extract_rules.py:224-233` 不校验 `ANTHROPIC_API_KEY`；`:128-132` 和 `:154-160` 全文件失败仍输出"Classified: 288 (API calls: 0)" | 无 key 时跑全量仍显"success"，误导式成功；`smoke_test.py:22-24` 有正确 skip 但未复用 | [7](docs/audit/07-engineering-quality.md) · [10](docs/audit/10-bug-scan.md) |
| 15 | 🟡 Major | **日志严重失衡**：`api_client.py` retry 用 print 污染 stdout | `ink-writer/scripts/` 432 print / 14 文件用 logging；`api_client.py:163,177,183,189,360,372,376,382` 8 处 retry 警告用 print | Embed API 抖动时 stdout 疯狂刷 retry 日志；无法 LOG_LEVEL=ERROR 抑制；dashboard 输出被污染 | [7](docs/audit/07-engineering-quality.md) |
| 16 | 🟡 Major | **Retriever 每章重建**：`step3_harness_gate.py:131-135` 每调一次新建 `Retriever()`，每次加载 bge 模型 ~30s | 20 章 × 30s = 10 min 纯模型加载；`writer_injection.py:63`、`context_injection.py:71` 同模式 | 批量写作性能显著劣化；与 CLAUDE.md Top3#1 "延迟加载"承诺部分违反 | [10](docs/audit/10-bug-scan.md) |
| 17 | 🔵 Minor | **LLM 调用无超时**：`editor_wisdom/llm_backend.py:44` `client.messages.create()` 未设 timeout（SDK 默认 10 min） | checker 并行时可能堆积 N×10min；单章卡住无自动 kill | 偶发会话阻塞 | [7](docs/audit/07-engineering-quality.md) · [10](docs/audit/10-bug-scan.md) |
| 18 | 🔵 Minor | **镜头/感官/句式节奏 4-5 重覆盖** | `polish-agent.md:264,277,290` 明写"SHOT_MONOTONY 对应 writer L10d / prose-impact 镜头多样性 / proofreading 6B.1" | polish-agent 可能收到冲突/重复的 fix_prompt，token 膨胀 | [3](docs/audit/03-checker-matrix.md) |
| 19 | 🔵 Minor | **schema 版本三处漂移**：`IndexManager=2` / `StateModel=9` / `migrate.py→11` | `index_manager.py:274` / `state_schema.py:290` / `migrate.py` | 无一处在验证一致性；docs 的 DDL 与实际 DDL 对不上 | [6](docs/audit/06-data-layer-audit.md) |
| 20 | 🔵 Minor | **双平台 90 天缓存零落盘** | `ls data/market-trends/` 仅 `README.md`，零 `cache-*.md`；`grep 'market-trends' ink_writer/ scripts/` 0 命中 | v13.8 发布后无一次真实 WebSearch 缓存产生；清理代码全仓零实现 | [5](docs/audit/05-creativity-audit.md) · [8](docs/audit/08-unused-resources.md) |

*注：Top 10 按严重度排序（Blocker > Critical > Major > Minor），编号至 20 以完整呈现核心发现。*

---

## 叠屋架地图（系统性断层可视化）

### A. 规格完备 + 生产未接入（最危险断层）

```
┌─────────────────────── SPEC 规格齐备 ──────────────────────┐
│                                                              │
│  ink-write SKILL.md (2201 行)   pipeline-dag.md  agents/*.md │
│       │                              │                │       │
│       │ 声明                          │ 声明           │ 声明   │
│       ▼                              ▼                ▼       │
│  ┌─────────────┐              ┌──────────────┐  ┌────────────┐│
│  │ CheckerRunner│              │ Step 3.6-3.10│  │Step 3.5    ││
│  │ asyncio gate │              │ 5 Python Gate│  │harness_gate││
│  │ 249 行 + 25 T│              │ (5 模块齐全) │  │ 读 死 路径  ││
│  └─────┬───────┘              └──────┬───────┘  └─────┬──────┘│
│        │                             │                │       │
│  ╳ 零生产引用                   ╳ 零生产引用      ╳ 永远 PASS   │
│        │                             │                │       │
│        └─── LLM Task 并发调度 + prompt 层 max=2 ────────┘      │
│              (靠 LLM 自律，不可审计)                            │
└──────────────────────────────────────────────────────────────┘

┌─────────────── Creativity 子系统（US-005）─────────────────┐
│                                                              │
│  meta-creativity-rules.md  anti-trope-seeds.json (1012条)    │
│  perturbation-engine.md    golden-finger-rules.md            │
│  style-voice-levels.md     naming/ 4 json (110+170+...)      │
│       │                                                      │
│       │ 数据层 structured OK                                  │
│       ▼                                                      │
│  ┌────────────────────────────────────────────────┐          │
│  │  "引擎层" 全部是 markdown 伪代码:               │          │
│  │    def draw_perturbation_pairs(...)  ← 0 Python │          │
│  │    gf_checks = [GF1,GF2,GF3]         ← LLM 自报 │          │
│  │    stable_hash(timestamp+genre)      ← 0 Python │          │
│  │    for attempt in range(1,6)         ← LLM 自律 │          │
│  └────────────────────────────────────────────────┘          │
│       │                                                      │
│       ▼                                                      │
│  init_project.py (903 行) 0 次 quick/aggression/             │
│   perturbation/meta_rule → 创意指纹不落盘                     │
└──────────────────────────────────────────────────────────────┘

┌─────────────── Style RAG 子系统（US-004）──────────────────┐
│                                                              │
│  benchmark/style_rag.db (3295 片段) ──┐                      │
│                                       ▼                      │
│  scripts/build_style_rag.py ──→ data/style_rag/ (默认不存在) │
│                                       │                      │
│                                       ▼                      │
│  StyleRAGRetriever() ────× FileNotFoundError                 │
│                                                              │
│  实际走平行路径:                                               │
│  context-agent → style_sampler.py.get_benchmark_samples      │
│                  (直查 SQLite, 绕过 FAISS)                    │
│                                                              │
│  结论: Skill/Agent 文档声称的 build_polish_style_pack()       │
│        在默认部署中几乎从未被消费                              │
└──────────────────────────────────────────────────────────────┘
```

### B. 多实现并存（同一能力多入口）

| 能力 | 实现 1 | 实现 2 | 实现 3 | 问题 |
|------|-------|-------|-------|------|
| 伏笔追踪 | agents/foreshadow-tracker.md | agents/thread-lifecycle-tracker.md | `ink_writer/foreshadow/tracker.py` | 3 份并存；overlap=0.667 |
| 明暗线追踪 | agents/plotline-tracker.md | agents/thread-lifecycle-tracker.md | `ink_writer/plotline/tracker.py` | 同上 |
| State 存储 | `state.json` | `state_kv` SQLite | StateManager + SQLStateManager 双 manager | 双写，v13 未闭合 |
| Golden Three | `ink_writer/editor_wisdom/golden_three.py` | `ink-writer/scripts/data_modules/golden_three.py` | — | 两文件 hash 不同、逻辑不同 |
| Python 运行时核心 | `ink_writer/`（17 子目录） | `ink-writer/scripts/data_modules/`（37 py） | — | 双包，pythonpath 都加 |
| 脚本目录 | `/scripts/`（审计/基准） | `/ink-writer/scripts/`（运行时） | — | 同名不同职 |
| OOC 语音检测 | ooc-checker.md (speech_profile) | flow-naturalness-checker.md (维度 4 对话辨识 + 维度 7 voice 一致性) | voice-fingerprint Python gate | 三重覆盖 |
| 镜头多样性 | prose-impact-checker | proofreading-checker Layer 6B | editor-wisdom-checker SHOT_MONOTONY | 3-4 重 |
| 感官丰富度 | prose-impact-checker | sensory-immersion-checker | proofreading Layer 6A | 3 重 |
| 句式节奏 CV | anti-detection Layer 1 | proofreading 6B | prose-impact | 3 重 |

### C. 旧 schema / 死表 / 死字段

```
index.db (34 表):
├── schema_meta              ← 写 1 次 SCHEMA_VERSION=2，永不读 [孤儿]
├── protagonist_knowledge    ← 建表，生产 INSERT=0、SELECT=0 [完全孤儿]
├── rag_schema_meta          ← 写 1 次 schema_version，永不读 [孤儿]
├── candidate_facts          ← 每章写入，消费只有统计计数 [半孤儿]
├── review_checkpoint_entries ← 实际命名 (docs 写 review_checkpoints，不一致)
├── state_kv                  ← v13 关键表，已用
├── disambiguation_log        ← 写对了，但 ink-resolve 不从此读 [双写单读]
└── 其它 28 张全部健康

docs 声称但从未创建的表:
  ✗ project_progress
  ✗ strand_tracker_entries
  ✗ protagonist_snapshots

docs 声称单一事实源，代码实际双写路径:
  state_manager.py:413 atomic_write_json(state.json)  ← 先
  state_manager.py:420 _sync_state_to_kv(disk_state)  ← 后
  state_manager.py:467 except: logger.warning         ← 同步失败只 warn
  
  ink-resolve/SKILL.md:28 json.loads(Path('.../state.json'))  ← 直读 JSON
  update_state.py:24    atomic_write_json(state.json)          ← 直写 JSON
  init_project.py:...   atomic_write_json(state.json)          ← 直写 JSON

schema 版本号 3 处漂移:
  IndexManager.SCHEMA_VERSION = 2     (index_manager.py:274)
  StateModel.schema_version = 9       (state_schema.py:290)
  migrate.py 最新 migration → v11     (migrate.py)
  读取端从无一处在校验一致性
```

### D. 僵尸规格 + 僵尸 Agent

```
v13 文档声称 merged 但文件仍在:
  ink-writer/agents/foreshadow-tracker.md   (5134 B) [僵尸]
  ink-writer/agents/plotline-tracker.md      (4748 B) [僵尸]
    └── 已被 thread-lifecycle-tracker.md 替代
        agent_topology_v13.md:57/64 明标 MERGED
        overlap ratio 0.667 (全表最高)

docs/ 根下 v1-v4 engineering-review:
  engineering-review-report.md    (18687 B)
  engineering-review-report-v2.md (15621 B)
  engineering-review-report-v3.md (7852 B)
  engineering-review-report-v4.md (8116 B)
    └── 已被 docs/audit/ v13.8 新审计体系完全替代

docs/archive/ 14 份 v9.x 历史审查:
  v9.2 / 9.3 / 9.4 / 9.6 / 9.8 / v9.14.0  (共 245.2 KB)

archive/ 9 个 PRD 历史快照:
  2026-04-15-editor-wisdom-v1/fix
  2026-04-16-* (x 6)
  2026-04-17-combat-pacing-overhaul
    └── 总 264.6 KB
```

---

## 分维度发现汇总

### US-001 版本考古 + 目录结构（[01-version-archaeology.md](docs/audit/01-version-archaeology.md)）

- **双 Python 包未真解决**：`ink_writer/`（下划线，17 子目录）+ `ink-writer/scripts/data_modules/`（37 py 文件），`pytest.ini:3` 两个都加入 pythonpath。CLAUDE.md 声称 US-402 已消除双目录——只消除了 agent 层。
- **Memory v13 "单一事实源"代码方向相反**：`state_manager.py:413-421` 先写 state.json，再同步 state_kv；`:467` 同步失败只 warning。
- **README 版本历史从 v9 直接跳 v11**：`docs/archive/` 存有 v9.2/9.3/9.4/9.6/9.8/9.14 共 6+ 份审查报告，README 完全未记录。
- **Skills 数量声明错误**：docs/architecture.md:35 + GEMINI.md:37-38 声称 "14 + 5 弃用桩"，磁盘 14 个、无弃用桩；`ink-fix` 新 skill 反而被遗漏。
- **每子包复制独立 config.py / fix_prompt_builder.py**：11 个 config.py + 6 个 fix_prompt_builder.py，结构 90% 相似，典型复制粘贴。

### US-002 主写作链路端到端追踪（[02-writing-pipeline-trace.md](docs/audit/02-writing-pipeline-trace.md)）

- **前半段稳健（bash + 脚本确定性），后半段靠 LLM 自律**：Step 0-2C 真实运行；Step 3 起 14+ checker + 5 Python gate 全靠 LLM 读 SKILL.md 自己调度。
- **Python 并发 checker 框架完全悬空**：`ink_writer/checker_pipeline/CheckerRunner` 249 行 + 25 测试，生产调用者 0；`is_hard_gate + cancel_event` 机制永远不触发。
- **Step 3.6-3.10 五 gate 零生产调用**：`Grep "from ink_writer\." ink-writer/scripts/` 从未命中 reader_pull/emotion/anti_detection/voice_fingerprint/plotline。
- **Step 3.5 Harness Gate 读死路径**：`step3_harness_gate.py:18-85` 读 `.ink/reports/review_ch*.json`，上游无任何代码产出；24 行命中 `if not reports_dir.exists(): return  # 默认通过`。
- **Step 5.5 Cascading Data Fix 无代码实现**：SKILL.md 行 1948-1984 描述详尽，零 Python。

### US-003 14+ Checker 职责矩阵（[03-checker-matrix.md](docs/audit/03-checker-matrix.md)）

- **实际 16 checker + 3 tracker + 1 无实现引用（voice-fingerprint）**：比 README 声明更多，但 checker_pipeline 整体孤儿。
- **硬门禁是四重混合而非一票否决**：(1) 9 个文档级 hard block；(2) 综合评分 + critical cap 50/55/60；(3) Python 后置闸 4 条规则；(4) editor-wisdom retry loop 终态 blocked.md。
- **镜头/感官/句式节奏 4-5 重覆盖**：`polish-agent.md:264,277,290` 显式写 "对应规则码 SHOT_MONOTONY（writer-agent L10d / prose-impact-checker 镜头多样性 / proofreading 6B.1）"。
- **僵尸 tracker**：foreshadow-tracker.md + plotline-tracker.md 已合并入 thread-lifecycle-tracker（`thread-lifecycle-tracker.md:220`），两个旧文件仍在且被 `tests/prompts/test_prompt_templates.py:222` 白名单引用。
- **voice-fingerprint 规格-引用不匹配**：polish-agent.md:40/135/144 引用但无对应 agent md；实际由 `ink_writer/voice_fingerprint/ooc_gate.py` Python 模块实现。

### US-004 RAG 三系统深度审查 + 运行时实测（[04-rag-audit.md](docs/audit/04-rag-audit.md) · [04-rag-live-trace.md](docs/audit/04-rag-live-trace.md)）

| 子系统 | 默认激活 | 实测结论 |
|-------|---------|---------|
| editor_wisdom | **100%** | 索引 364 条 FAISS 可查；writer/context/polish 三注入 markdown 均正确产出 |
| style_rag | **0%（FAISS）** | `data/style_rag/` 默认不存在，Retriever 抛 FileNotFoundError；构建耗 27s / 3295 vectors / 512d；实际被 `style_sampler.py` SQLite 平行路径绕过 |
| semantic_recall | **0%（所有 10 项目）** | 构建脚本可用（10s 完成 140 章 build），但用户环境 10 个 ink 项目全部无 `.ink/chapter_index/`；有 `.ink/vectors.db`（远端 API RAG） |

- **索引规则条数文档漂移**：CLAUDE.md + PRD 说 288，实际索引 364、源 JSON 388。
- **Retriever 加载慢**：首次 17.06s（含 sentence-transformers + FAISS）；`step3_harness_gate.py:135` 每章新建一次，20 章 = 10 min 纯加载。
- **三套 RAG 无冲突优先级协议**：editor_wisdom 禁"时间标记开头"，style_rag 样本中存在"第二天"开头——polish 同时接到两种指令，无代码层仲裁。

### US-005 创意系统审查（[05-creativity-audit.md](docs/audit/05-creativity-audit.md)）

- **数据层结构化到位**：种子库 1012 条 / R4+R5=50.4% / R5=20.2% / Draft-07 schema + 10 pytest 静态校验；绰号 110 条、书名模板 170 条（V1=54/V2=57/V3=59）、陈词黑名单多层分类。
- **"引擎"全是 markdown 伪代码**：`draw_perturbation_pairs` / `gf_checks` / `stable_hash` / 5 次重抽降档循环，`grep` 全仓命中 0 个 Python 函数定义。
- **`init_project.py` 903 行对创意字段零感知**：grep `quick|aggression|perturbation|meta_rule|market_avoid` 全 0 命中；`state_schema.py` 数据模型无对应字段。
- **双平台 90 天缓存未落地**：`data/market-trends/` 自 v13.8 发布至今只有 README.md，零 `cache-*.md`；清理代码全仓零实现。

### US-006 数据层与记忆系统（[06-data-layer-audit.md](docs/audit/06-data-layer-audit.md)）

- **不是"30+ 表混合架构"，是 4 SQLite + 1 JSON 视图**：index.db(34) + vectors.db(4) + style_samples.db(1) + parallel_locks.db(1) + cache_metrics.db(1) + benchmark style_rag(1)，合计 41 表。
- **孤儿表 / 死代码**：`protagonist_knowledge`（INSERT=0, SELECT=0）、`schema_meta`（写 1 次永不读）、`rag_schema_meta`（同）、`incremental_extract/differ.py`（生产 import=0）。
- **docs 声称未创建的表**：`project_progress` / `strand_tracker_entries` / `protagonist_snapshots` 全部 0 次 CREATE TABLE。
- **双写但单读（disambiguation）**：`disambiguation_log` 表被正确写入、`resolve_disambiguation_entry(id)` API 存在但 0 调用者；`ink-resolve/SKILL.md:28` 直接 `json.loads(state.json)`。
- **schema 3 处漂移 + 两个 config 丢失风险**：`voice_fingerprint_config` / `plotline_lifecycle_config` v10/v11 migrations 只写 state.json 未进 state_kv，`rebuild_state_dict()` 的 `kv_keys` 不包含这两个，若重建 state.json 会丢失。

### US-007 工程质量全面体检（[07-engineering-quality.md](docs/audit/07-engineering-quality.md)）

| 维度 | 评级 | 关键问题 |
|------|:---:|---------|
| 测试 | B- | 2028 tests 规模合格；覆盖率门禁 70% 幻觉（实测 13.62%）；核心 state_manager 9%、extract_chapter_context 0%、step3_harness_gate 0% |
| 错误处理 | C+ | 95 处宽捕获；20-30 处静默 swallow；LLM 无显式 timeout |
| 配置 | B | SoT 清晰 `.env > env > yaml > 默认`；13 份 YAML 模块独占；扣分在 13 处 load_config 未抽象 |
| 日志 | D+ | 432 print / 14 logging 文件；`api_client.py` retry 警告用 print 污染 stdout |
| 依赖 | D | **6 个核心依赖未声明**（numpy/faiss/yaml/jsonschema/sentence-transformers/anthropic）；`pyproject.toml` 无 `[project]` 元信息 |
| 文档 | C | `operations.md` / `CLAUDE.md` 对齐良好；`README.md` "38 种模板"实际 37、"14 Agents + 10 Checkers"实际 24/17；`architecture.md` 说 25 表实际 34；`agent_topology_v13.md` 未跟上 v13.6-v13.8 |

**整体工程质量评级：C+**（功能密度远超同类，边界收敛明显不足）。

### US-008 死代码与未使用资源（[08-unused-resources.md](docs/audit/08-unused-resources.md)）

- **Python 层零死代码**：`ink_writer/` 66 模块 100% 被引用，0 不可达函数（按 AST 启发式含属性访问）。
- **37 个路径 / 约 603 KB 可立即 `rm`**：
  - `archive/` 9 子目录 18 文件（264.6 KB）
  - `docs/archive/` 14 份 v9.x 历史审查（245.2 KB）
  - `docs/engineering-review-report(-v2/v3/v4).md`（49.1 KB）
  - `ink-writer/agents/{foreshadow,plotline}-tracker.md`（9.6 KB）
- **9 个 references/ md 需确认**（约 35 KB）：context-contract-v2 / preferences-schema / project-memory-schema / return-work-template / review-bundle-schema / review-history-library / shared/command-reference + harness-architecture + severity-standard。
- **"Python 代码层维护远好于文档层"**：66 模块全活 vs references/ 34 md 中 9 个（26%）全仓零引用。

### US-009 README 承诺 vs 代码兑现（[09-promise-vs-reality.md](docs/audit/09-promise-vs-reality.md)）

- **承诺兑现率 88.9%**（22 完全 + 4 部分 / 27 项）。
- **F1 "300 章不矛盾"**：基础设施齐全（30+ 表、三路召回、伏笔超期报警），但**从未真实压测**。
- **F2 "100 章 7 小时"**：`reports/v13_acceptance.md` "总耗时 8s \| FAIL"；SKILL.md 内部耗时公式反推 **12.5 小时**，与 FAQ 差 78%。
- **F3 "8 层反 AI 检测"**：实际 10 层（0/1/2/3/3.5/4/5/5.5/6/8.5），标号跳号缺 7/8 主层；宣传"8 层"约数。
- **F5 "38 种题材模板"**：实际 37 个；genre 深度库仅 9 个题材。
- **v11.0 Style RAG**：数据齐备（3295 SQLite），但 FAISS 索引开箱即缺，README 未声明需 `build_style_rag.py`。

### US-010 静态 Bug 扫描（[10-bug-scan.md](docs/audit/10-bug-scan.md)）

- **整体风险 MEDIUM-HIGH**：1 Blocker + 2 Critical + 若干 High。
- **Blocker**：PipelineManager 并发未接 ChapterLockManager，docstring 声称保护实际零引用；pipeline_manager.py:177-181 多章 subprocess 竞争同一 state.json + index.db。
- **Critical**：`03_classify.py` / `05_extract_rules.py` 无入口 API Key 校验，per-file `except continue` 导致全失败仍显示"API calls: 0"假成功。
- **Critical**：Retriever 无全局单例，`step3_harness_gate.py:131-135` 每章新建，20 章 ≈ 10 min 纯模型加载。
- **High**：`pipeline_manager.py:296-297` stdin.write 无 drain（大 prompt >64KB 可能截断）；6 处 `except Exception: return False` 静默吞（如 `_check_outline` 把所有错误当"大纲不存在"触发冤枉生成）。
- **基础卫生良好**：零裸 except、零可变默认参数、零未关闭文件句柄、主包无用户可控 SQL 注入。

### US-011 本总报告

### US-012 开源同类项目横向对比（[11-competitive-analysis.md](docs/audit/11-competitive-analysis.md)）

- **独特定位**：全球唯一把"起点/番茄编辑审核规则"作为硬约束嵌入全链路的 AI 网文写作工具。
- **无直接对手**：Sudowrite/Novelcrafter 英文主、不理解网文平台；AutoNovel (656 stars) 最相似但英文无中文网文规则；AI_NovelGenerator (4.4k stars) 有网文 hint 但审查薄弱、无编辑规则层。
- **可借鉴设计 3 条**：
  1. **AutoNovel 5 层共同演化 + 反向传播**：下游发现矛盾向上冒泡修订 canon.md（当前 ink-writer Pipeline 单向前进，Step 3 review 只能章内修复）；
  2. **Novelcrafter Progressions**（动态进展追踪）：`character_progressions(character_id, chapter_no, dimension, from, to, cause)` 表；
  3. **Sudowrite Series Folder**（跨书知识继承）：`~/.claude/ink-writer/library/` + `ink-init --inherit=book_id`。
- **需反思警示**：NovelAI 扩大上下文路线已被自证不可持续（8k 后退化），ink-writer 走结构化 + RAG 是对的；Wordcraft "全自动不可行"的结论已被 v13 硬门禁部分证伪，保持自动化路线但持续加厚 checker 栈。

---

## 可删除清单（37 条 / ~603 KB，来自 US-008）

直接可执行的清理命令（**不影响运行时**，Python 层零耦合）：

```bash
cd /Users/cipher/AI/ink/ink-writer

# A. archive/ 历史 PRD 快照 (264.6 KB / 18 文件 / 9 目录)
rm -rf archive/2026-04-15-editor-wisdom-v1/
rm -rf archive/2026-04-15-editor-wisdom-fix/
rm -rf archive/2026-04-16-deep-review-and-perfection/
rm -rf archive/2026-04-16-ink-optimization/
rm -rf archive/2026-04-16-logic-fortress/
rm -rf archive/2026-04-16-narrative-coherence/
rm -rf archive/2026-04-16-token-optimization/
rm -rf archive/2026-04-16-wordcount-and-progress/
rm -rf archive/2026-04-17-combat-pacing-overhaul/

# B. docs/archive/ v9.x 14 份历史审查 (245.2 KB)
rm -rf docs/archive/

# C. docs/ 根下 v1-v4 旧 engineering-review 报告 (49.1 KB)
rm docs/engineering-review-report.md
rm docs/engineering-review-report-v2.md
rm docs/engineering-review-report-v3.md
rm docs/engineering-review-report-v4.md

# D. 已 merged 的僵尸 agent 规格 (9.6 KB)
# ⚠️ 注意：需同步更新 tests/prompts/test_prompt_templates.py:222 兼容白名单
rm ink-writer/agents/foreshadow-tracker.md
rm ink-writer/agents/plotline-tracker.md

# E. 仓库卫生（已在 .gitignore 但被手动 commit）
rm -f .DS_Store ink-writer/scripts/.DS_Store .coverage
```

**不建议立即删除（需 owner review）的 9 个 references/**：context-contract-v2.md / preferences-schema.md / project-memory-schema.md / return-work-template.md / review-bundle-schema.md / review-history-library.md / shared/command-reference.md + harness-architecture.md + severity-standard.md（约 35 KB）——建议集中迁入 `docs/specs/` 或在文件顶部标 `deprecated: true`。

---

## 修复优先级建议

### Phase 1：Blocker（必须立即修，0-3 天）

| # | 修复项 | 涉及文件 | 复杂度 | 天数 |
|---|--------|---------|:---:|:---:|
| P1.1 | 声明 `ink_writer/` 6 个核心依赖（numpy/faiss-cpu/PyYAML/jsonschema/sentence-transformers/anthropic），并同步 CI workflow | `pyproject.toml` / `requirements.txt` / `.github/workflows/ci-test.yml` | S | 0.5 |
| P1.2 | PipelineManager 接入 ChapterLockManager 或明确文档为"仅串行安全" | `ink_writer/parallel/pipeline_manager.py` | M | 1.5 |
| P1.3 | 确认 Memory v13 方向：文档改 or 代码改；统一 `StateManager.flush()` 写入顺序（SQL 先，JSON 后） | `state_manager.py` / `memory_architecture_v13.md` | M | 1 |

**Phase 1 合计**：**3 项**，3 天。

### Phase 2：Critical（本月内修，1-4 周）

| # | 修复项 | 涉及文件 | 复杂度 | 天数 |
|---|--------|---------|:---:|:---:|
| P2.1 | 为 Step 3.6-3.10 五 gate + CheckerRunner 写生产接线（新建 `step3_gates_runner.py` 串联 5 gate） | `ink_writer/checker_pipeline/runner.py` + 新 orchestrator | L | 3 |
| P2.2 | 修复 Step 3.5 Harness Gate 死路径：改读 `index.db.review_metrics` | `ink-writer/scripts/step3_harness_gate.py` | S | 0.5 |
| P2.3 | Style RAG 索引自动构建（`ink-init` 末段调用 `build_style_rag.py`） + 降级到 SQLite 采样 | `scripts/build_style_rag.py` / `init_project.py` | M | 1.5 |
| P2.4 | Creativity 指纹字段入库：扩展 `state_schema.py` + `init_project.py` 接收 `meta_rules_hit/perturbation_pairs/gf_checks/style_voice/market_avoid` | `state_schema.py` / `init_project.py` | M | 2 |
| P2.5 | `03_classify.py` / `05_extract_rules.py` 入口 API Key 校验 + 连续 N 次失败 abort | 2 文件 | S | 0.5 |
| P2.6 | `step3_harness_gate.py` / `writer_injection.py` / `context_injection.py` Retriever 全局单例（functools.lru_cache 或 module-level 缓存） | 3 文件 | S | 0.5 |
| P2.7 | `ink-resolve` 切换走 SQLite `resolve_disambiguation_entry(id)`，停止直写 state.json | `skills/ink-resolve/SKILL.md` | M | 1 |
| P2.8 | pytest 覆盖率门禁改为现实值 `--cov-fail-under=30` 并为 state_manager / extract_chapter_context / step3_harness_gate 补集成测试 | `pytest.ini` + 3 测试 | L | 3 |

**Phase 2 合计**：**8 项**，12 天。

### Phase 3：Major（本季度内修，1-3 月）

| # | 修复项 | 涉及文件 | 复杂度 | 天数 |
|---|--------|---------|:---:|:---:|
| P3.1 | 物理删除僵尸 agent + 37 条 `rm` 清单执行 | shell | S | 0.5 |
| P3.2 | 删除孤儿表 `protagonist_knowledge` / `schema_meta` / `rag_schema_meta` + 归档 `incremental_extract/` 或接入 data-agent | `index_manager.py` / `migrate.py` | M | 2 |
| P3.3 | 日志规范化：`api_client.py` 8 处 retry print → logger.warning；其它 non-CLI print 迁移 | `api_client.py` + ~20 文件 | M | 2 |
| P3.4 | 双 Python 包合并策略决策（或在 CLAUDE.md 明文规定"什么进 ink_writer，什么进 data_modules"） | `CLAUDE.md` + 大规模目录调整 | XL | 5-10 |
| P3.5 | 文档对齐：README（38→37 templates, agent/checker 数量）、architecture.md、agent_topology_v13.md 补 v13.6-v13.8 新 checker；引入 `scripts/verify_docs.py` CI 校验 | 3 md + 1 py | M | 2 |
| P3.6 | LLM 调用加显式 timeout（`editor_wisdom/llm_backend.py`）+ `pipeline_manager.py` 加 `asyncio.wait_for` 章级 timeout | 2 文件 | S | 1 |
| P3.7 | PipelineManager `stdin.drain()` + 6 处 `except Exception` 区分 FileNotFoundError vs 其它 | `pipeline_manager.py` | S | 0.5 |
| P3.8 | Double 平台 90 天缓存落地（Python 层 WebSearch 封装 + clean_expired_cache()） | 新文件 | M | 2 |
| P3.9 | schema 版本号 3 处统一（或文档拆成 `index_db_version` / `state_version` 两个独立概念） | `index_manager.py` / `state_schema.py` | S | 0.5 |

**Phase 3 合计**：**9 项**，约 15-20 天。

### Phase 4：Minor（有空修）

- 合并镜头/感官/句式节奏的 fix_prompt（跨 checker merged_fix_suggestion）
- agent 样板复用（50+ 处重复 preamble 提取）
- 每个 `ink_writer/<module>/config.py` 抽象成基类
- DDL f-string → `sqlite3.complete_statement` 或 identifier quoting
- `chapter_lock.py` threading.local → asyncio.Lock（修复前置 P1.2 才暴露）
- 删除 `data/style_rag/` 或 `.gitignore` 策略统一
- 死代码：`writer_injection.py:65-71` 不可达 return 清理

**Phase 4 合计**：约 7-10 项，有空修即可。

---

## 横向对比摘要（来自 [US-012](docs/audit/11-competitive-analysis.md)）

### ink-writer 独特定位

> **全球唯一把起点/番茄编辑审核规则作为硬约束嵌入全链路的 AI 网文写作工具**。在"中文长篇商业连载 × 高自动化 × 硬门禁质检"象限**几乎无对手**。

### 可借鉴设计（3 条，高优先级）

1. **AutoNovel 5 层共同演化 / 反向传播**（最值得借鉴）
   - 新增 `ink_writer/propagation/` 模块 + Step 5 后 canon-drift-detector
   - 产出 `propagation_debt.json` 供下次 `/ink-plan` 主动消费
   - `ink-macro-review` 每 50 章触发 propagation 清算
   - **解决痛点**：当下 Pipeline 单向前进，卷一伏笔在卷三无法自圆不会倒回改卷二大纲

2. **Novelcrafter Progressions 动态进展追踪**
   - 扩 `ink_writer/foreshadow/` → `ink_writer/progression/`
   - 新表 `character_progressions(character_id, chapter_no, dimension, from_value, to_value, cause)`
   - `context-agent` 的 3-layer pack 增加"本章之前的角色演进摘要"
   - **解决痛点**：配角在 80 章后 OOC，或立场渐变无可审计追踪

3. **Sudowrite Series Folder 跨书知识继承**
   - 新增 `~/.claude/ink-writer/library/`：用户级跨项目知识库
   - `ink-init --inherit=book_id` 参数：从 library 导入角色/世界观/文风锚点
   - **低改动高回报**：目录层 + 两个 CLI 参数
   - **面向真实用户**：商业长篇作者一辈子写几十本，沉淀"个人风格资产"

### 需警示的做法（已被行业证伪）

- NovelAI "扩大上下文" 路线（8k 后退化）—— ink-writer 的 state.json + vectors.db + RAG 路线是对的，不要因 Claude/GPT 长 context 倒退
- AI_NovelGenerator 硬编码 120 章上限 —— ink-writer 理论无上限是关键优势
- LibriScribe "纯 agent 名目"陷阱 —— agent 数量不等于能力；继续走审慎合并路线

---

## 下一步：Step 2 修复 PRD 候选 User Story 清单

按优先级排序，作为 Step 2 "修复 PRD" 的直接输入。

| US | 优先级 | 标题 | 一句话描述 | 主要涉及文件 | 预期改动量 |
|---|:---:|------|----------|---------|:---:|
| FIX-01 | P0 | **`ink_writer/` 6 依赖声明 + CI 修复** | 消除 CI 绿的幻觉；让干净 runner 也能跑 | `pyproject.toml` / `requirements.txt` / `ci-test.yml` | S（0.5d） |
| FIX-02 | P0 | **PipelineManager 并发安全** | 接入 ChapterLockManager 或文档明确仅串行 | `pipeline_manager.py` | M（1.5d） |
| FIX-03 | P0 | **Memory v13 单一方向决策** | 确定 SQL-first 还是 JSON-first；统一写入顺序；更新 docs | `state_manager.py` / `memory_architecture_v13.md` | M（1d） |
| FIX-04 | P1 | **Step 3 Python Gate 生产接线** | 写 `step3_gates_runner.py` 串联 5 gate + CheckerRunner；Step 3.5 改读 index.db | `checker_pipeline/` + 5 gate + 新 orchestrator | L（3d） |
| FIX-05 | P1 | **Style RAG 自动构建 + 降级** | `ink-init` 自动建 FAISS 或优雅降级到 style_sampler SQLite | `init_project.py` / `build_style_rag.py` | M（1.5d） |
| FIX-06 | P1 | **Creativity 指纹字段入库** | `state_schema.py` 扩字段；`init_project.py` 消费 Quick 输出 | `state_schema.py` / `init_project.py` | M（2d） |
| FIX-07 | P1 | **ink-resolve 走 SQL + disambiguation 单读** | 停止直写 state.json；调用 `resolve_disambiguation_entry(id)` | `skills/ink-resolve/SKILL.md` | M（1d） |
| FIX-08 | P1 | **Retriever 单例 + lazy load 完整化** | `step3_harness_gate.py` / injection 函数用 functools.lru_cache | 3 文件 | S（0.5d） |
| FIX-09 | P1 | **API Key 护栏 + 失败 abort** | `03_classify.py` / `05_extract_rules.py` 入口校验 + 连续 N 次失败 abort | 2 文件 | S（0.5d） |
| FIX-10 | P1 | **coverage 门禁现实化 + 3 核心文件补测试** | pytest.ini 改 30%；state_manager / extract_chapter_context / step3_harness_gate 补 integration | pytest.ini + 3 测试 | L（3d） |
| FIX-11 | P2 | **双 Python 包合并策略** | 要么合并 `ink_writer/` + `data_modules/`，要么 CLAUDE.md 明文规则 | CLAUDE.md + 大规模目录 | XL（5-10d） |
| FIX-12 | P2 | **死代码大清理** | 37 条 `rm` + 删孤儿表 + 归档 `incremental_extract` + 删僵尸 agent | 多 | S-M（1d） |
| FIX-13 | P2 | **日志规范化** | api_client.py retry print → logger；non-CLI print 迁移 | ~20 文件 | M（2d） |
| FIX-14 | P2 | **LLM + Pipeline 显式 timeout** | `llm_backend.py` 加 timeout；`pipeline_manager.py` 章级 wait_for | 2 文件 | S（1d） |
| FIX-15 | P2 | **文档对齐 + CI 校验** | README / architecture / agent_topology 数字对齐；新增 verify_docs.py | 3 md + 1 py | M（2d） |
| FIX-16 | P3 | **性能 benchmark 真实压测** | 修 `run_300chapter_benchmark.py` 让它真的收集 G1-G5 + 至少跑 1 次 100 章 | 1 py + 1 真运行 | L（3d + token） |
| FIX-17 | P3 | **AutoNovel 反向传播借鉴** | 新增 `ink_writer/propagation/` + canon-drift-detector + ink-macro-review 集成 | 新模块 | XL（5-7d） |
| FIX-18 | P3 | **Progressions 动态进展追踪** | 新表 + context-agent 集成 + 与 ooc-checker 合并使用 | schema + context | L（3d） |

**合计 18 个 US**，其中 P0 **3 个**、P1 **7 个**、P2 **5 个**、P3 **3 个**。

---

## 附录 A：审计数据来源（reproducible）

- 子审计报告：`docs/audit/01-version-archaeology.md` ~ `docs/audit/11-competitive-analysis.md`
- 工具产物：`reports/architecture_audit.md`（85 unused module candidates）
- 静态扫描：`scripts/audit/scan_unused.py`（可 `--json` 复现）
- `pytest --collect-only` 实测：2028 tests, 0 error, 1.84s
- `pytest --cov` 实测：`ink-writer/scripts/` 总覆盖 13.62%
- RAG live trace：`/Users/cipher/AI/重生2013/` 140 章真实项目
- 版本：v13.8.0（HEAD=349f651）
- 审计日期：2026-04-17

## 附录 B：核心文件路径索引

- **Memory v13 核心**：`ink-writer/scripts/data_modules/state_manager.py:413-467`、`sql_state_manager.py:860-917`
- **并发 Blocker**：`ink_writer/parallel/pipeline_manager.py:5,177-181`、`chapter_lock.py`
- **孤儿 checker_pipeline**：`ink_writer/checker_pipeline/runner.py:174-178,232-233`
- **5 Python Gate**：`ink_writer/reader_pull/hook_retry_gate.py:86` / `emotion/emotion_gate.py:86` / `anti_detection/anti_detection_gate.py:130` / `voice_fingerprint/ooc_gate.py:87` / `plotline/tracker.py:129`
- **Harness Gate 死路径**：`ink-writer/scripts/step3_harness_gate.py:18-85`
- **Retriever 重复加载**：`ink-writer/scripts/step3_harness_gate.py:131-135`、`ink_writer/editor_wisdom/writer_injection.py:63`
- **Creativity 数据层**：`ink-writer/skills/ink-init/references/creativity/{meta-creativity-rules.md,perturbation-engine.md,golden-finger-rules.md,style-voice-levels.md,anti-trope-seeds.json}`、`data/naming/{nicknames,surnames,given_names,blacklist,book-title-patterns}.json`
- **数据层管理器**：`ink-writer/scripts/data_modules/index_manager.py`(2238 行) / `sql_state_manager.py`(1130 行)
- **孤儿表**：`index_manager.py:866-884`（protagonist_knowledge）
- **性能 benchmark**：`scripts/run_300chapter_benchmark.py:215-245`、`reports/v13_acceptance.md:8`、`benchmark/300chapter_run/metrics.json`

## 附录 C：本次审计未覆盖场景（Known Gaps）

- 完整 `/ink-auto` 端到端 live run（避免污染真实项目，改为三套 RAG 单元级 live trace）
- EMBED_API_KEY 缺失的降级路径（用户环境本有 key）
- 远端 RAG API（智谱 embedding-3）的实际调用
- Windows / Linux 多平台兼容性（仅测 macOS）
- 100/200/300 章真实压测的数值（G1-G5 指标从无真实采集）

---

**报告结束。**

总计 12 份子审计 → 1 份总报告，聚焦"规格-代码 gap"这条主线。3 个 Blocker、8 个 Critical、9 个 Major——问题虽多，但修复路径清晰、成本有限（Phase 1+2 约 15 天工作量）。项目本身的独特性和功能密度值得这笔投入。
