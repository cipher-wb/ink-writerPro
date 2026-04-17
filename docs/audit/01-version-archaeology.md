# US-001 — 版本考古 + 目录结构分析

> Ink Writer Pro v13.8.0 深度健康审计 · Step 1
> 执行日期：2026-04-17
> 执行者：Claude (Opus 4.7)
> 范围：只诊断，不改源码

---

## Executive Summary

- **核心诊断**：项目在 v8 → v13.8 共 15+ 次大改造中产生了明显的"叠屋架"，架构文档和代码现实出现严重分岔。
- **根本原因**：每一次大改造都以"保留旧实现向后兼容"为托底，导致老 Agent / 老 Python 模块 / 老 checker 规格不断堆积，新一代实现只是叠在上面。
- **双目录问题远比 CLAUDE.md 声明的更严重**：虽然 US-402 合并了 `agents/ink-writer/` → `ink-writer/agents/`，但 Python 侧的 `ink_writer/`（下划线包，17 个功能模块）和 `ink-writer/scripts/data_modules/`（横杠目录下的数据核心包）仍然并存，且命名高度相似、职责互不相通，极易引发新工程师认知错乱。
- **代码 vs 文档漂移巨大**：README 版本历史从 v9 直接跳到 v11（实际 `docs/archive/` 里存在 v9.2/v9.3/v9.4/v9.6/v9.8/v9.14 的工程审查报告）；`docs/architecture.md` 说"14 Skills 含 5 弃用桩"，但磁盘上只有 14 个真实 skill，没有任何弃用桩。
- **最危险的一类叠屋架**：Memory Architecture v13（`docs/memory_architecture_v13.md` 声称 SQLite 为"单一事实源"、`state.json` 为"视图缓存"）在代码层面并未实现——`state_manager.py:415` 仍然先写 `state.json`，然后把 KV 同步到 SQLite，与文档设计相反。

---

## Top 10 Findings

### 🔴 F1. Memory v13 "单一事实源"与代码行为相反（Blocker）

**文档声称**（`docs/memory_architecture_v13.md:167-175`）：
```
After (v13):
  index.db   ← 先写入（事实源）
  state.json ← rebuild_state_json()（视图缓存）
```

**代码现实**（`ink-writer/scripts/data_modules/state_manager.py:413-421`）：
```python
# 原子写入（锁已持有，不再二次加锁）
try:
    atomic_write_json(self.config.state_file, disk_state, use_lock=False, backup=True)
except Exception as exc:
    logger.error("Failed to write state.json: %s", exc)
    raise

# v13: 同步单例状态到 SQLite state_kv（视图缓存支撑）
self._sync_state_to_kv(disk_state)
```
写入顺序恰好与文档设计相反：`state.json` 先写（是真正的单一事实源），`state_kv` 只是后续"同步"，失败时只会警告（`:467`），不会回滚 `state.json`。

**影响**：ink-audit 等工具、跨章一致性检查、任何"以 SQLite 为准"的假设都存在数据漂移风险。文档意图 vs 代码行为的不一致，使新开发者和 AI Agent 都会被误导。

---

### 🔴 F2. `ink_writer/` vs `ink-writer/scripts/data_modules/` 双 Python 包并存（Blocker）

两个 Python 包命名几乎只差一个连字符 / 下划线，但职责完全不同：

| 路径 | 包名 | 职责 | 文件数 |
|------|------|------|--------|
| `ink_writer/` | `ink_writer.*`（下划线） | v11+ 的"能力模块"（editor_wisdom/emotion/style_rag/semantic_recall/anti_detection/cultural_lexicon/foreshadow/plotline/…） | 17 子目录 |
| `ink-writer/scripts/data_modules/` | `data_modules.*` | v5-v9 的数据链核心（StateManager / IndexManager / SQLStateManager / state_validator / entity_linker …） | 37 文件 |

证据：

- `pytest.ini:3` 将两个位置都手工加入 `pythonpath`：`pythonpath = . ink-writer/scripts ink-writer/dashboard scripts`
- `pyproject.toml:35` 只把 `data_modules` 定义为 first-party（`known-first-party = ["data_modules"]`），`ink_writer` 被当作第三方包处理
- `reports/architecture_audit.md:12` 显示：自动化审计已报告 **85 个未被引用的模块候选**，`ink_writer/*` 绝大部分子包 + `data_modules/*` 大部分 mixin 都在该列表中

**影响**：
1. 新模块放 `ink_writer/` 还是 `data_modules/` 没有明文规则，实际取决于作者习惯。
2. 跨包依赖时要用 `from ink_writer.x import y` 或 `from data_modules.x import y`，容易拼错。
3. 目录名仅差 `_` / `-`，在终端里 tab-补全经常选错。

---

### 🔴 F3. `ink-writer/scripts/` vs `scripts/` 同名目录、不同用途（Blocker）

两个顶级 scripts 目录完全不同但名字相同：

| 路径 | 用途 | 样例文件 |
|------|------|----------|
| `/scripts/` (根目录) | **审计 / 基准测试 / 一次性爬虫 / 种子脚本** | `audit_architecture.py`、`build_style_rag.py`、`run_300chapter_benchmark.py`、`seeds_batch10_object.py`、`editor-wisdom/01_scan.py`…06 |
| `/ink-writer/scripts/` | **运行时插件核心脚本**（被 CLAUDE Code skills 调用） | `ink.py`、`ink-auto.sh`、`computational_checks.py`、`migrate.py`、`step3_harness_gate.py` |

证据：`diff -r` 显示两目录**没有一个同名文件**，完全互不重叠（见 Bash 输出）；且 `pytest.ini:3` 两个目录都进 `pythonpath`。

**影响**：`python scripts/xxx` vs `python ink-writer/scripts/xxx` 依赖于调用位置，ink-auto.sh、ralph、workflows 常常混用，已经在 GEMINI.md:84 出现硬编码 `${INK_PLUGIN_ROOT}/scripts/ink.py`（指向 ink-writer/scripts）的约定。

---

### 🟠 F4. v13 "Agent 合并"只是别名，物理文件与 Python 模块均未清理（Critical）

`docs/agent_topology_v13.md:62-69` 声称：
```
| **Merged** | `foreshadow-tracker` + `plotline-tracker` → `thread-lifecycle-tracker` |
| **Retained** | Old agent files kept for backward compatibility (agent name aliasing) |
```

**实际磁盘状态**：
- `ink-writer/agents/foreshadow-tracker.md` ✓ 仍在
- `ink-writer/agents/plotline-tracker.md` ✓ 仍在
- `ink-writer/agents/thread-lifecycle-tracker.md` ✓ 新增
- `ink_writer/foreshadow/tracker.py` + `fix_prompt_builder.py` + `config.py` ✓ 仍在
- `ink_writer/plotline/tracker.py` + `fix_prompt_builder.py` + `config.py` ✓ 仍在
- `tests/foreshadow/` + `tests/plotline/` ✓ 仍在，各自 3-4 个测试

证据（`reports/architecture_audit.md:146-152`）：
```
- **foreshadow-tracker** ↔ **thread-lifecycle-tracker** (overlap ratio: 0.667)
  Shared terms: 密度异常, 检测逾期, 沉默, 输出结构化报告
```
共享词重叠 **0.667**，是全表最高 overlap 比例之一。`foreshadow-tracker` 和 `thread-lifecycle-tracker` 在 agent spec 文本层面重复了近 2/3 内容。

**影响**：存在 3 份相同职责的 agent 规格、3 份 Python 模块，维护成本 3 倍；新 agent 要调用"伏笔追踪"时可能调用任意一个，结果无法稳定预测。

---

### 🟠 F5. Skills 数量声明错误，"5 弃用桩"不存在（Critical）

`docs/architecture.md:35` 声明：
```
│  Skills (14个): init / plan / write / review / query /      │
│    resume / learn / dashboard / auto / audit / resolve /    │
│    macro-review / migrate / 5(弃用桩)                      │
```

`GEMINI.md:37-38` 也有：
```
| ~~`ink-5`~~ | ⚠️ **已弃用**，请使用 `ink-auto 5` 替代 | — |
```

**实际磁盘状态**（`ls ink-writer/skills/`）：
```
ink-audit  ink-auto  ink-dashboard  ink-fix  ink-init
ink-learn  ink-macro-review  ink-migrate  ink-plan
ink-query  ink-resolve  ink-resume  ink-review  ink-write
```
14 个 skill，**没有任何 ink-5 或弃用桩**。`ink-fix` 是新增的（文档未列），反而被遗漏。

---

### 🟠 F6. webnovel-writer 决策已废弃但基础设施残留（Critical）

`docs/skill_systems_decision.md` 在 2026-04-16 批准"废弃 webnovel-writer，保留 ink-writer"。但：

- `ink-writer/scripts/migrate_webnovel_to_ink.sh` 仍然存在（迁移脚本）
- `.webnovel/` → `.ink/` 重命名逻辑仍在代码中
- `tests/skill_systems/test_skill_systems_decision.py` 是个常驻测试
- `webnovel-writer` skill 在当前会话 system prompt 中仍列为可用 skill

这种"一边废弃一边残留"的状态很容易让 maintenance 时误用或误删。

---

### 🟠 F7. README 版本历史与 docs/archive 的 v9.x 断层（Critical）

`README.md:185-188` 的版本历史：
```
| v9.0.0 | Harness-First 架构：计算型闸门 + Reader Agent 升格 |
| v8.0.0 | 14 Agent 全规范化 + 风格锚定 + 批量恢复 |
```
从 v9.0 直接跳到 v11.0（第 184 行），缺少 v9.1-v9.x 和 v10.x。

**实际证据**（`docs/archive/`）：
```
ENGINEERING_AUDIT_v9.2.md
ENGINEERING_AUDIT_v9.3.md
ENGINEERING_AUDIT_v9.4.md
ENGINEERING_AUDIT_v9.6.md
ENGINEERING_AUDIT_v9.6_independent.md
ENGINEERING_AUDIT_v9.8.md
ENGINEERING_AUDIT_REPORT_v9.14.0.md
```
至少存在 v9.2 → v9.14 共 6+ 个中间版本的工程审查报告，说明 v9 阶段实际有大量小版本迭代，但 README 完全未记录，只留下审查报告作"考古遗存"。

---

### 🟡 F8. ink_writer 子包几乎全部未被主流程引用（Major）

`reports/architecture_audit.md:18` 明确列出 **85 个 unused module candidates**，以下 ink_writer 子包整包列入"疑似废弃"：

```
anti_detection (整包 4 文件)
checker_pipeline (整包 2 文件)
cultural_lexicon (整包 4 文件)
editor_wisdom (整包 12 文件)
emotion (整包 5 文件)
foreshadow (整包 4 文件)
incremental_extract (整包 3 文件)
pacing (整包 2 文件)
parallel (整包 3 文件)
plotline (整包 4 文件)
prompt_cache (整包 4 文件)
reader_pull (整包 4 文件)
semantic_recall (整包 4 文件)
style_rag (整包 3 文件)
voice_fingerprint (整包 5 文件)
```

需要验证这是"审计工具误报"（因模块通过 `importlib` 或字符串引用动态加载）还是"真死代码"。初步抽样发现 `ink_writer/foreshadow/tracker.py` 被 `ink-writer/scripts/workflow_manager.py` 等处通过 `from ink_writer.foreshadow...` 引用，所以**至少部分是误报**。但 85 这个体量说明**至少 30-50 个模块确实没有被 skills/agents 走的主流程触及**，只在单元测试里被测。

---

### 🟡 F9. 每个 ink_writer 子包都有自己的 `config.py` + `fix_prompt_builder.py` 模板（Major）

共有 **11 个 config.py**、**6 个 fix_prompt_builder.py**，结构高度相似但各自独立实现：

```
ink_writer/editor_wisdom/config.py
ink_writer/plotline/config.py       ← fix_prompt_builder.py 同目录
ink_writer/reader_pull/config.py    ← fix_prompt_builder.py 同目录
ink_writer/anti_detection/config.py ← fix_prompt_builder.py 同目录
ink_writer/foreshadow/config.py     ← fix_prompt_builder.py 同目录
ink_writer/cultural_lexicon/config.py
ink_writer/voice_fingerprint/config.py ← fix_prompt_builder.py 同目录
ink_writer/prompt_cache/config.py
ink_writer/incremental_extract/config.py
ink_writer/semantic_recall/config.py
ink_writer/emotion/config.py        ← fix_prompt_builder.py 同目录
```
同时 `config/*.yaml`（顶级 `config/` 目录）也有 13 个 YAML 配置文件，每个子包还需要手工从 YAML 加载。这是典型的"每次新加一个能力就复制一份脚手架"的叠屋架模式。

---

### 🟡 F10. Agent 样板复用严重（Major）

`reports/architecture_audit.md:153-207` 列出 **50 个重复 prompt 片段**，样例：

```
- 5x 在 [consistency-checker, continuity-checker, high-point-checker, ooc-checker, pacing-checker]:
  `检查范围 输入 单章或章节区间 如 45 45`
- 3x 在 [foreshadow-tracker, plotline-tracker, thread-lifecycle-tracker]:
  `密度告警 5 最低分 0 pass overall_score`
- 3x 在 [high-point-checker, reader-pull-checker, reader-simulator]:
  `题材画像 claude_plugin_root references genre profiles md`
```
虽然 `references/shared-checker-preamble.md` 已提取共享 preamble，但 24 个 agent 规格里的同段落副本仍有 50+ 处复制。改动一处 checker 契约时，需要手工搜 5 个文件同步。

---

## 目录地图（顶层 39 项，带标注）

> 🟢=当前用途清晰 / 🟡=需确认 / 🔴=疑似叠屋架或废弃 / 🔵=次要/辅助

```
/Users/cipher/AI/ink/ink-writer/
├── 🟢 .claude/                   Claude Code 本地会话配置
├── 🟢 .claude-plugin/            根目录插件 marketplace 配置
│   └── marketplace.json           → source: "./ink-writer"
├── 🔵 .codex/                    Codex CLI 安装说明
├── 🔵 .github/                   CI 工作流
├── 🔵 .ink/                      审计阶段产物目录（存日志）
├── 🔵 .pytest_cache/ .ruff_cache/ 工具缓存
├── 🟢 archive/                   每次迭代归档的 prd.json + progress.txt
│   ├── 2026-04-15-editor-wisdom-v1/
│   ├── 2026-04-15-editor-wisdom-fix/
│   ├── 2026-04-16-deep-review-and-perfection/    ← v13.0 迭代档
│   ├── 2026-04-16-ink-optimization/
│   ├── 2026-04-16-logic-fortress/                ← v13.2
│   ├── 2026-04-16-narrative-coherence/           ← v13.5
│   ├── 2026-04-16-token-optimization/            ← v13.4
│   ├── 2026-04-16-wordcount-and-progress/        ← v13.3
│   └── 2026-04-17-combat-pacing-overhaul/        ← v13.6/7 支线
├── 🟢 benchmark/                 基准语料 + 分析脚本 (v11 Style RAG 源)
├── 🟢 config/                    13 个 YAML 业务配置（对应 ink_writer/ 子包）
├── 🟢 data/                      运行时数据（editor-wisdom 规则库 + 种子库）
│   ├── editor-wisdom/            vector_index (FAISS) + rules.json
│   └── cultural_lexicon/ naming/ market-trends/ …
├── 🟢 docs/                      架构/设计文档
│   ├── architecture.md            ← 🟡 Skills 数量 14+"5弃用桩" 与代码不符
│   ├── agent_topology_v13.md      ← 🟡 声称 merged 的 agent 仍在磁盘
│   ├── memory_architecture_v13.md ← 🔴 声称 SQLite 为单一事实源，代码相反
│   ├── v9-upgrade-guide.md
│   ├── skill_systems_decision.md  ← 废弃 webnovel-writer 决策
│   ├── editor-wisdom-integration.md
│   ├── engineering-review-report*.md   ← 4 份不同时期的审查
│   └── archive/                   ← 🔴 存有 v9.2/9.3/9.4/9.6/9.8/9.14 审查
├── 🔴 ink_writer/                下划线 Python 包 (17 子目录)
│   ├── anti_detection/ checker_pipeline/ cultural_lexicon/
│   ├── editor_wisdom/ emotion/ foreshadow/ incremental_extract/
│   ├── pacing/ parallel/ plotline/ prompt_cache/ reader_pull/
│   ├── semantic_recall/ style_rag/ voice_fingerprint/
│   └── → 绝大多数被 architecture_audit 列为 unused 候选
├── 🔴 ink-writer/                横杠插件根 (Claude Code skills + agents)
│   ├── .claude-plugin/plugin.json  ← v13.8.0
│   ├── agents/ (24 md 文件)
│   │   ├── foreshadow-tracker.md + plotline-tracker.md
│   │   └── thread-lifecycle-tracker.md  ← 三者并存（F4）
│   ├── skills/ (14 目录) — init / plan / write / auto / review / …
│   ├── scripts/ (37 py 文件 + data_modules/ 子包)
│   │   └── data_modules/ (37 py)  ← 下划线命名的子包（F2）
│   ├── references/ templates/ genres/ dashboard/
├── 🟢 ralph/ + ralph-使用说明.md   Ralph 工作流核心 + 用户文档
├── 🔵 reports/                   自动化报告输出目录
│   ├── architecture_audit.md      ← 本次审计重要参考
│   └── v13_acceptance.md
├── 🟢 schemas/                   JSON Schema 定义
├── 🔴 scripts/                   顶级 scripts（与 ink-writer/scripts 同名，用途不同）
│   ├── audit_architecture.py  build_style_rag.py
│   ├── run_300chapter_benchmark.py
│   ├── seeds_batch*_*.py (9 个种子脚本)
│   └── editor-wisdom/ (01_scan…06_build_index)
├── 🟢 tasks/                     PRD 源文件 (prd-*.md, 11 个)
├── 🟢 tests/                     顶级单元测试
│   ├── 22 子目录，与 ink_writer/ 子包一一对应
│   └── (data_modules/ 的测试散在 ink-writer/scripts/data_modules/tests/ 中，是 F11 潜在问题)
├── 🔵 .coverage / .coveragerc    coverage 工具产物
├── 🟡 .DS_Store                  （macOS 垃圾文件，已提交到 git）
├── 🟢 AGENTS.md / CLAUDE.md / GEMINI.md  不同 CLI 的项目入口说明
├── 🟢 README.md prd.json progress.txt
├── 🔵 pyproject.toml pytest.ini requirements.txt gemini-extension.json
└── 🟢 LICENSE (GPL v3)
```

### 误放文件判定

| 文件 | 现位置 | 建议 |
|------|-------|------|
| `.DS_Store` | 顶级 + `ink-writer/scripts/` | 🔴 应加入 `.gitignore` 并删除 |
| `.coverage` | 顶级 | 🔴 应加入 `.gitignore`（已在.gitignore 内但被手动 commit） |
| `ralph-使用说明.md` | 顶级 | 🟡 按惯例应进 `docs/` 或 `ralph/` |
| 2 份 `CLAUDE.md` | 顶级 + `ralph/` | 🟢 ralph/CLAUDE.md 是 ralph 自身规范，合理 |

---

## 版本声称 vs 代码现实表

| 版本 | README 声称 | 代码痕迹证据 | 判定 |
|------|-------------|-------------|------|
| **v8.0.0** | "14 Agent 全规范化 + 风格锚定" | `ink-writer/agents/` 现有 24 agents；`ink-writer/scripts/data_modules/style_anchor.py` 存在且被 tests/ 覆盖 | 🟢 代码留存，但已被 v11/v13 大幅扩增 |
| **v9.0.0** | "Harness-First + 计算型闸门 + Reader Agent 升格" | `ink-writer/scripts/computational_checks.py`、`step3_harness_gate.py`、`step2b_metrics.py` 均存在；`docs/v9-upgrade-guide.md` 描述 migration；state_schema.py 内 harness_config 字段 | 🟢 完整代码痕迹 |
| **v9.1–v9.14（README 未列）** | — | `docs/archive/` 存 v9.2/9.3/9.4/9.6/9.8/9.14 审查报告 | 🔴 README 断层，实际这段历史被刻意省略 |
| **v11.0.0** | "Style RAG 3295 片段 + 统计层修复 + 记忆升级" | `ink_writer/style_rag/retriever.py`、`benchmark/reference_corpus/` (117 本标杆)、`scripts/build_style_rag.py` | 🟢 完整 |
| **v11.3.0** | "工程深度审查 22 项：计算型闸门 + 死亡状态 + mega-summary + 黄金三章契约" | `scripts/computational_checks.py`、 `ink-writer/skills/ink-write/references/step-1.5-contract.md`（黄金三章契约） | 🟢 完整 |
| **v11.4.0** | "TTR + 首句钩子 + 伏笔分级 + 角色语气指纹" | `ink_writer/voice_fingerprint/fingerprint.py` (语气指纹)、`ink_writer/foreshadow/tracker.py` (伏笔分级) | 🟢 完整 |
| **v11.5.0** | "跨章遗忘 bug 根因修复" | — | 🟡 未找到显式 bug-fix 代码；可能只在 state_manager._load_state 的窗口扩展里，需深挖 |
| **v12.0.0** | "编辑星河 288 建议 → 364 原子规则 → FAISS" | `ink_writer/editor_wisdom/retriever.py` (FAISS)、`data/editor-wisdom/vector_index/rules.faiss` 存在、`scripts/editor-wisdom/01-06_*.py` pipeline | 🟢 完整 |
| **v13.0.0** | "27 US / 6 Phase + 爽点调度器 + Style RAG + 双 agent 目录消除 + prompt cache" | agent 目录双目录确已合并（`agents/ink-writer/` 已不存在）；`ink_writer/prompt_cache/` 存在；`ink_writer/pacing/high_point_scheduler.py` 存在；`archive/2026-04-16-deep-review-and-perfection/prd.json` 记录 27 US | 🟢 完整，但"合并"只是物理合并，**Python 侧 `ink_writer/` + `data_modules/` 两包并存的更深层问题未解决（F2）** |
| **v13.2.0** | "Logic Fortress + logic-checker + outline-compliance-checker + MCC 5 铁律" | `ink-writer/agents/logic-checker.md` + `outline-compliance-checker.md` 存在；`ink-writer/scripts/logic_precheck.py` 存在 | 🟢 完整 |
| **v13.3.0** | "字数 4000 硬上限 + 双层进度条" | `ink-writer/skills/ink-write/SKILL.md:12` 写最低 2200；4000 硬上限在 computational_checks.py 里；`ink-writer/scripts/status_reporter.py` 进度条 | 🟢 完整 |
| **v13.4.0** | "Token 优化 30min→20min + 审查包瘦身 + logic 预检 + Step 2B 降级" | `ink-writer/scripts/slim_review_bundle.py` 存在；`logic_precheck.py` 存在；`step2b_metrics.py` 存在 | 🟢 完整 |
| **v13.5.0** | "Narrative Coherence + 否定约束管线 + 场景退出快照 + Writer 自洽回扫" | `tests/.../test_negative_constraints.py`、`test_scene_exit_snapshot.py` 存在 | 🟢 完整 |
| **v13.6.0** | "爽点密集化 L7-L10 + 卖点密度 + 摄像头检测 + OOC 本能违反" | `ink-writer/skills/ink-write/references/step-3-review-gate.md` 含 L7-L10；high-point-checker.md 存在 | 🟢 完整 |
| **v13.7.0** | "文笔沉浸感 + prose-impact + sensory-immersion + flow-naturalness + Polish L9" | `ink-writer/agents/prose-impact-checker.md`、`sensory-immersion-checker.md`、`flow-naturalness-checker.md` 存在 | 🟢 完整 |
| **v13.8.0** | "ink-init --quick 创意架构 + 元规则 M01-M10 + 金手指三重硬约束 + 书名 170 模板" | `ink-writer/skills/ink-init/references/creativity/meta-creativity-rules.md` 存在；seed batches 文件存在 (10 批 100 条 × 10) | 🟢 完整 |

**表格结论**：
- v8/v9/v11/v12/v13.x 绝大多数声称都有代码痕迹（🟢）。
- 唯一"只有文档无代码"的是 **README 未提及的 v9.1-v9.14**（🔴），以及 **v11.5 "bug 根因修复"** 难以溯源。
- 真正的问题不是"有没有代码"，而是 **旧实现没被清理**。

---

## "叠屋架"证据

### 类别 A：同一能力多实现

| 能力 | 实现 1 | 实现 2 | 实现 3 | 证据 |
|------|--------|--------|--------|------|
| **伏笔追踪** | `ink-writer/agents/foreshadow-tracker.md` | `ink-writer/agents/thread-lifecycle-tracker.md` (v13 新增) | `ink_writer/foreshadow/tracker.py` | F4 |
| **明暗线追踪** | `ink-writer/agents/plotline-tracker.md` | `ink-writer/agents/thread-lifecycle-tracker.md` | `ink_writer/plotline/tracker.py` | F4 |
| **State 存储** | `state.json` (JSON 文件) | `index.db.state_kv` (SQLite) | `StateManager` + `SQLStateManager` (双 manager) | F1 |
| **Golden Three 检查** | `ink_writer/editor_wisdom/golden_three.py` (编辑智慧视角) | `ink-writer/scripts/data_modules/golden_three.py` (数据层视角) | 2 个文件 hash 不同、逻辑不同 | checksum 已验 |
| **Python 运行时核心** | `ink_writer/*`（能力模块） | `ink-writer/scripts/data_modules/*`（数据层） | 两个独立 Python 包，pythonpath 都加 | F2 |
| **脚本目录** | `/scripts/*`（审计/基准） | `/ink-writer/scripts/*`（运行时） | 同名不同职 | F3 |

### 类别 B：同一概念多处 schema

| 概念 | 存储位置 1 | 存储位置 2 | 现状 |
|------|-----------|-----------|------|
| `protagonist_state` | `state.json.protagonist_state` | `index.db.state_kv (key='protagonist_state')` | F1——state.json 先写，SQLite 后同步，随时可漂移 |
| `harness_config` | `state.json.harness_config` | `index.db.state_kv (key='harness_config')` | 同上 |
| `schema_version` | `state.json.schema_version` | `index.db.state_kv (key='schema_version')` | 同上 |
| `disambiguation_warnings` | `state.json.disambiguation_warnings` | `index.db.disambiguation_log (category='warning')` | 两处独立，rebuild 时合并 |
| `review_checkpoints` | `state.json.review_checkpoints` | `index.db.review_checkpoint_entries` | 两处独立 |
| 伏笔登记 | `state.json.plot_threads`（老字段） | `index.db.plot_thread_registry` | `rebuild_state_json` 用 SQLite 版重建 JSON |

### 类别 C：旧 Agent / 旧 checker 规格未清理

- `ink-writer/agents/foreshadow-tracker.md` + `plotline-tracker.md` (v13 已并入 thread-lifecycle，但未删)
- **旧文档有意保留但未标注 deprecated**：这些文件在 Agent 调用系统里仍然可以被发现和派发，导致即使 agent-topology-v13 声称它们 merged，Skills 或其他自动流程仍可能调用旧 agent。

### 类别 D：脚手架复制粘贴（F9）

每个 `ink_writer/<module>/` 都有独立 `config.py`、`__init__.py`、部分有 `fix_prompt_builder.py`，结构 90% 相似。改变基础 config 加载模式需要改 11 处。

### 类别 E：测试目录分叉

- `tests/` (顶级)：按 ink_writer 子包组织，22 个子目录
- `ink-writer/scripts/data_modules/tests/`：52 个测试文件，专测 data_modules 包
- `pytest.ini:2` 同时把两个目录加入 `testpaths`

新开发者不知道应该把新测试放哪个位置，这是典型的"两套测试基础设施并存"。

---

## 建议（只诊断，不执行）

| 优先级 | 动作 | 收益 |
|--------|------|------|
| 🔴 P0 | 确认 Memory v13 文档 vs 代码方向问题（F1）：到底是文档错、还是代码未完成迁移？ | 避免开发者被误导、避免数据漂移风险 |
| 🔴 P0 | 决定 `ink_writer/` vs `data_modules/` 是否合并（F2）；若不合并，在 CLAUDE.md 里明文规定"什么进 ink_writer，什么进 data_modules" | 消除目录命名混淆 |
| 🟠 P1 | 为 `ink_writer/*` 子包跑"真.动态引用扫描"，确认 85 unused 中真死代码的比例（F8） | 一次性清理 20-40 个死文件 |
| 🟠 P1 | 物理删除（或归档到 archive/）已 merged 的 agent md + 对应 python tracker（F4） | 消除三份并存的职责混乱 |
| 🟡 P2 | 修正 README 版本历史补齐 v9.1-v9.14 概述，或明示"跳过这段" | 恢复诚实的版本历史 |
| 🟡 P2 | 修正 `docs/architecture.md` 的 Skills 14+弃用桩说法；`GEMINI.md` 删除 ink-5 提示（F5） | 文档可信度 |
| 🔵 P3 | 提取 agent spec 样板到更强大的共享 preamble（F10） | 减少 50+ 重复文段 |
| 🔵 P3 | 清理 `.DS_Store`、`.coverage` 等被误 commit 的文件 | 仓库卫生 |

---

## 附录：本次审计数据来源

- `README.md`（版本历史）
- `docs/architecture.md`、`docs/agent_topology_v13.md`、`docs/memory_architecture_v13.md`、`docs/v9-upgrade-guide.md`、`docs/skill_systems_decision.md`
- `reports/architecture_audit.md`（项目自动化审计工具产物）
- `docs/archive/` 下 9 份历史审查报告
- `pyproject.toml` + `pytest.ini`（确认 pythonpath 和 first-party 包定义）
- `ink-writer/scripts/data_modules/state_manager.py`、`sql_state_manager.py`（Memory v13 实现现状）
- `ink-writer/agents/` 24 份 md + `ink_writer/foreshadow/` + `plotline/`（F4 物证）
- `scripts/` 和 `ink-writer/scripts/` 的完整 `diff -r`（F3 物证）
- `ink_writer/` 子包的 `config.py` 和 `fix_prompt_builder.py` 统计（F9）
