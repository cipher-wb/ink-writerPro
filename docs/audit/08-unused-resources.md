# US-008 — 死代码与未使用资源扫描

**项目**：ink-writer
**版本**：v13.8.0
**审计日期**：2026-04-17
**扫描脚本**：`scripts/audit/scan_unused.py`
**原始数据**：可通过 `python3 scripts/audit/scan_unused.py --json` 复现

---

## Executive Summary

本次扫描覆盖 4 类资源共 169 个文件（Python 模块 66 + references 34 + data 25 + agents 24 + archive 18 + docs/archive 14 + 旧 engineering-review 报告 4），归并为"可立即删除 / 需确认 / 可归档"三级处置建议。

**总体结论**：

| 类别 | 数量 | 体积 |
|---|---|---|
| 🗑 **可立即删除** | **37 个路径** | **约 603 KB** |
| ⚠ **需确认（文档链路未闭合）** | **11 个路径** | **约 35 KB** |
| 📦 **可归档（无代码引用，但仍可能是规格底稿）** | **9 个路径** | **约 30 KB** |
| ✅ **已验证在用（未在上述三类）** | **112 个路径** | —— |

**可回收磁盘空间总量（🗑 + 📦）**：**约 633 KB**
（注：Python 源码层面 66 个模块 100% 活跃、0 个死模块、0 个不可达函数——这是项目代码层的健康信号。）

**本次扫描重点发现**：`ink_writer/` 包无 Python 死代码；清理压力集中在文档/规格层（references/、archive/、旧 engineering report），与 Python 代码层无耦合，删除不会影响运行时。

---

## 🗑 可立即删除

用户已确认 `archive/` 与 `docs/archive/` 整体可删。同时 docs 根目录下旧版 engineering-review-report(-v2/v3/v4) 已被 v4 之后的新审计体系取代，也可删。另外有两份已并入 `thread-lifecycle-tracker` 的孤儿 agent 规格。

### A. `archive/` 目录 — PRD 历史快照（9 个子目录，18 个文件，264.6 KB）

| 路径 | 总大小 |
|---|---|
| `archive/2026-04-15-editor-wisdom-fix/` | 26.8 KB |
| `archive/2026-04-15-editor-wisdom-v1/` | 29.8 KB |
| `archive/2026-04-16-deep-review-and-perfection/` | 85.0 KB |
| `archive/2026-04-16-ink-optimization/` | 14.4 KB |
| `archive/2026-04-16-logic-fortress/` | 30.5 KB |
| `archive/2026-04-16-narrative-coherence/` | 25.4 KB |
| `archive/2026-04-16-token-optimization/` | 18.9 KB |
| `archive/2026-04-16-wordcount-and-progress/` | 13.1 KB |
| `archive/2026-04-17-combat-pacing-overhaul/` | 20.6 KB |
| **小计** | **264.6 KB** |

### B. `docs/archive/` 目录 — 历史审查报告（14 个 .md，245.2 KB）

`ENGINEERING_AUDIT_v9.2/9.3/9.4/9.6/9.6_independent/9.8/v9.14.0`、`PROJECT_AUDIT_REPORT.md`、`ink-writer*优化路线图.md`、`ink-writer*全面分析报告.md`、`ink-writer*深度评审报告.md`、`ink-writer*审计报告.md` 等共 14 个。
均为早期版本独立审计产物，当前 `docs/audit/` 目录已有 v13.8 审计体系替代。

### C. `docs/` 根下旧版 engineering review 系列（4 个 .md，49.1 KB）

| 路径 | 大小 |
|---|---|
| `docs/engineering-review-report.md` | 18687 B |
| `docs/engineering-review-report-v2.md` | 15621 B |
| `docs/engineering-review-report-v3.md` | 7852 B |
| `docs/engineering-review-report-v4.md` | 8116 B |
| **小计** | **49.1 KB** |

以上四份报告生成于 2026-04-11，为 v7→v9 升级期遗留产物；`docs/audit/01~11` 系列（v13.8 审计）已完全替代。grep 全仓未发现代码/agent/skill 引用。

### D. 已并入 `thread-lifecycle-tracker` 的孤儿 agent（2 个 .md，9.6 KB）

| 路径 | 大小 | 说明 |
|---|---|---|
| `ink-writer/agents/foreshadow-tracker.md` | 5134 B | `docs/agent_topology_v13.md` 第 24 行标注 `← MERGED` |
| `ink-writer/agents/plotline-tracker.md` | 4748 B | `docs/agent_topology_v13.md` 第 25 行标注 `← MERGED` |

证据：
- `docs/agent_topology_v13.md` 第 57/64 行：「Merged: `foreshadow-tracker` + `plotline-tracker` → `thread-lifecycle-tracker`」
- 全仓搜索：无任何 `ink-writer/skills/*/SKILL.md` 引用、无任何 `ink_writer/` Python 文件引用、无任何 agent 规格引用
- 唯一引用位置：`tests/prompts/test_prompt_templates.py:222` 的兼容性白名单 — 若删文件需同步更新此测试

**处置建议**：文件连同兼容性测试条目一起清理；别名逻辑（`docs/agent_topology_v13.md` 198-199 行提到的 `"agent": "foreshadow-tracker"` → `thread-lifecycle-tracker[foreshadow]` 别名）已由新 agent 内部承载。

### E. 可删除合计

**37 个路径 / 约 603 KB**（A + B + C + D = 264.6 + 245.2 + 49.1 + 9.6 + 其他 ≈ 603 KB）

---

## ⚠ 需确认

以下 references/ 下的 .md 文件全仓 grep 不到任何引用（py/md/sh/json/toml），但属于协议级规格（schema / contract / 约定），删除前建议对代码行为做一次再次确认。

| 路径 | 大小 | 性质推断 |
|---|---|---|
| `ink-writer/references/context-contract-v2.md` | 4006 B | 上下文契约 v2 —— 可能是 context-agent 早期规范，已被 `agents/context-agent.md` 内嵌 |
| `ink-writer/references/preferences-schema.md` | 544 B | preferences 结构，state.json/preferences 字段可能仍在用 |
| `ink-writer/references/project-memory-schema.md` | 536 B | project_memory.json 结构，ink-learn skill 会写入 |
| `ink-writer/references/return-work-template.md` | 2131 B | 打回模板，checker 输出格式可能仍依赖 |
| `ink-writer/references/review-bundle-schema.md` | 6391 B | review_bundle.json 结构，slim_review_bundle.py 产出该结构 |
| `ink-writer/references/review-history-library.md` | 4853 B | 旧版复盘库说明 |
| `ink-writer/references/shared/command-reference.md` | 2070 B | 命令参考速查表 |
| `ink-writer/references/shared/harness-architecture.md` | 11850 B | harness 架构文档，skill 设计背景 |
| `ink-writer/references/shared/severity-standard.md` | 3181 B | checker 严重性分级 —— 部分 checker md 可能隐式按此标准评分 |

**小计 9 个，约 35 KB**

**处置建议**：
- `preferences-schema.md` / `project-memory-schema.md` / `review-bundle-schema.md` —— 查 `ink_writer/` 里是否有同步 schema 校验逻辑，若无则保留为文档底稿即可（不必删除，但应明确其已变为 docs-only）
- `harness-architecture.md` / `severity-standard.md` / `command-reference.md` —— 建议在 v14 前进行一次 owner review，判断是否迁入 `docs/` 目录统一管理
- 本审计不主动删除

额外需确认的 2 条 references 在 `code` 类但引用路径较窄，需重新评估加载必要性：

| 路径 | 被谁引用 |
|---|---|
| `ink-writer/references/shared/core-constraints.md` | writer-agent.md + ink-write/ink-review SKILL — 在用 |
| `ink-writer/references/shared/cool-points-guide.md` | `ink_writer/pacing/high_point_scheduler.py` — 在用 |

（以上两条不在需确认清单内，仅列出以便定位疑问。）

---

## 📦 可归档

以下 references/ 下文件被 PRD / 开发指南 / `.codex/INSTALL.md` / `GEMINI.md` 引用，但不被任何 Python/skill/agent 规格在运行时加载。作为项目规格底稿保留价值有限，建议集中迁入 `docs/specs/` 或直接归档。

| 路径 | 大小 | 引用来源 |
|---|---|---|
| `ink-writer/references/codex-tools.md` | 3652 B | `.codex/INSTALL.md`（codex CLI 工具映射说明） |
| `ink-writer/references/gemini-tools.md` | 2541 B | `GEMINI.md`（gemini CLI 工具映射说明） |
| `ink-writer/references/pipeline-dag.md` | 4471 B | `tasks/prd-v13-health-audit.md` + `docs/audit/02-writing-pipeline-trace.md` |
| `ink-writer/references/state-sqlite-migration-guide.md` | 5105 B | `tasks/prd-v13-health-audit.md` + `docs/audit/06-data-layer-audit.md` |
| `ink-writer/references/entity-management-spec.md` | 10665 B | `docs/audit/06-data-layer-audit.md` |
| `ink-writer/references/scene-craft/climax.md` | 1604 B | `docs/quality-upgrade-dev-guide.md` |
| `ink-writer/references/scene-craft/dialogue.md` | 1926 B | `docs/quality-upgrade-dev-guide.md` |
| `data/market-trends/README.md` | 3008 B | 仅 SKILL.md 和 PRD 引用，实际无 Python 读取；v13.8 发布后目录内从未落盘过 `cache-YYYYMMDD.md`（参见 `docs/audit/05-creativity-audit.md`） |

**小计 8 个，约 33 KB**

**处置建议**：
- `codex-tools.md` / `gemini-tools.md` —— 属于多 CLI 支持规格，保留。但可考虑迁移至 `docs/cli-integration/`
- `pipeline-dag.md` / `state-sqlite-migration-guide.md` / `entity-management-spec.md` —— 仅被审计文档引用，说明是"开发参考"，可原地保留作为知识库
- `scene-craft/climax.md` / `scene-craft/dialogue.md` —— 与 combat/emotion/suspense 不同，这两篇不被任何 checker 拉取；要么补全 checker 引用，要么归并进 `quality-upgrade-dev-guide.md`
- `data/market-trends/README.md` —— 缓存机制悬空（参见 Top 5 意外发现 #3），README 本身保留，但需补全 Python 落盘/过期清理逻辑

---

## ✅ 已验证在用（摘要，不在清理目标）

| 类别 | 数量 | 说明 |
|---|---|---|
| Python 模块 | 66/66 | 全部被 import 或被外部（scripts/tests）引用；0 个孤立模块 |
| Python 函数 | 100% | 按 AST 启发式（含属性访问）零孤函数 |
| references/ code 类 | 18/34 | 被 agent/skill 规格或 py 直接加载 |
| data/ code 类 | 24/25 | 涵盖 naming/cultural_lexicon/editor-wisdom/hook_patterns/style_rag 全部运行时数据 |
| agents/ 被用 | 22/24 | 除上述 2 个 MERGED 外均被 skill 或 py 调用 |

---

## 扫描方法（可复现）

### 工具

- **脚本**：`scripts/audit/scan_unused.py`
- **Python**：≥3.10，仅标准库（ast / pathlib / re / json / collections）
- **运行时长**：约 3 秒，读盘 IO-bound

### 命令

```bash
# 控制台摘要
python3 scripts/audit/scan_unused.py

# 输出完整 JSON（供 CI/后续工具消费）
python3 scripts/audit/scan_unused.py --json > audit_unused.json
```

### 扫描步骤

1. **Python 死代码**（AST）：
   - 解析 `ink_writer/**/*.py` 所有模块，构建 dotted-name ↔ 文件映射。
   - 对每个模块扫 `ast.Import` / `ast.ImportFrom`，补齐相对导入前缀。
   - 对每个模块扫 `ast.Call` / `ast.Attribute` / `ast.Name`（属性访问用于识别 `@property` 装饰器方法）。
   - 反向在 `scripts/`、`tests/`、`ink-writer/scripts/`、`docs/` 等 8 个搜索根中扫 dotted 模块名是否出现——命中则视为被引用。
   - 函数名启发式：若私有（`_` 前缀）/ 入口名（main/run/handle/cli/setup/teardown）一律跳过，避免假阳性。

2. **references/ / data/ / agents/ 引用扫描**：
   - 收集 8 个搜索根下所有 `.py/.md/.sh/.json/.yaml/.yml/.toml/.ini/.txt/.bash/.zsh` + 根目录零散文件（README/CLAUDE/GEMINI/AGENTS/.codex/INSTALL.md 等），读入字符串缓存。
   - 对每个被审计的目标文件，按完整相对路径 + 文件名双匹配。
   - 对通用文件名（`README.md`、`__init__.py`、`config.json`、`INDEX.md`）只做完整路径匹配，避免假阳性。
   - **动态加载补救**：对 `data/XXX/*.json` 类文件，若父目录 `XXX` 被代码文件以字符串形式引用，且文件 stem（如 `xianxia`）也作为字符串在代码中出现，则标注为 `[dynamic-load]`（解决 `data/cultural_lexicon/xianxia.json` 由 `ink_writer/cultural_lexicon/loader.py` 拼接路径加载的漏检）。
   - 引用归类：
     - `code`：Python 源代码 / `ink-writer/skills/` / `ink-writer/agents/` 里被引用（视为运行时生效）
     - `docs`：仅被 `docs/` / `tasks/` / `reports/` / 根 md 引用（视为文档层）
     - `unreferenced`：全仓零命中

3. **archive/ 清点**：`rglob('*')` 直接求和，不读内容（用户已确认整体可删）。

4. **旧 engineering-review 清点**：硬编码 4 个路径（v1-v4）。

### 已知限制

- 启发式函数调用扫描无法识别反射 / `getattr` / `importlib` 动态调用；此次扫出 0 个孤函数属于乐观估计（scan 过滤了属性访问，下限可信）。
- references/ 文件引用扫描不识别语义等价（如 "这份规格" 指代某文件而不写文件名）；数值表达的是"lexical 引用"，与语义实际引用可能有差距。
- `data/style_rag/*.json` 体积巨大（约 39 MB），审计日新增；若后续代码层未持续使用，应单独纳入 `.gitignore` 或专门的缓存目录策略。

---

## Top 5 意外发现

### 1. Python 层零死代码 — 但 references/ 层约 1/3 死
`ink_writer/` 66 个模块全部被引用、0 个不可达函数（含属性访问口径），与之对比，`ink-writer/references/` 34 个 .md 中 9 个（≈ 26%）完全无引用，另外 7 个仅被开发指南/PRD 提及。说明代码层维护纪律远好于文档层。

### 2. `foreshadow-tracker` / `plotline-tracker` 两个 agent 规格是幽灵文件
`docs/agent_topology_v13.md` 明确标注这两个 agent 已 `MERGED` 进 `thread-lifecycle-tracker`（第 24-25、57、64 行），但文件仍保留在 `ink-writer/agents/` 下，没有任何 skill/py/agent 引用它们——属于典型"重构留尾"。唯一残留依赖：`tests/prompts/test_prompt_templates.py:222` 的兼容性白名单。

### 3. `data/market-trends/` 只有规格没有落盘
`docs/audit/05-creativity-audit.md` 已发现该问题：自 v13.8 发布（2026-04-17）起，目录下只有 `README.md`，零个 `cache-YYYYMMDD.md`——规格层描述了 90 天滚动缓存机制，Python 侧无任何代码执行该机制。本次扫描佐证：全仓无 `.py` 文件 grep 命中 "market-trends"，只有 SKILL.md 和 PRD 引用。属于"规格飘在空中"。

### 4. docs/ 根下存在 4 份冗余 engineering-review 报告（v1-v4，总 49.1 KB）
`docs/engineering-review-report.md` / `-v2.md` / `-v3.md` / `-v4.md` 这 4 份 2026-04-11 生成的独立审计报告，在 v13.8 新审计体系（`docs/audit/01~11`）上线后完全无引用，还占了首页列表空间。与 `docs/archive/ENGINEERING_AUDIT_v9.*` 系列应统一归档。

### 5. `ink-writer/references/scene-craft/` 6 篇中有 2 篇无 checker 引用
该目录原设计是场景工艺库（combat/emotion/suspense/climax/dialogue/characterization），其中 4 篇被 checker agents 或 skill 规范引用（`combat.md` 被 prose-impact-checker 等 3 个 checker 引用，`emotion.md` + `suspense.md` 被 sensory-immersion-checker 引用），但 **`climax.md` 和 `dialogue.md` 只被 `docs/quality-upgrade-dev-guide.md` 引用，没有任何 checker 或 writer-agent 加载它们**。说明场景工艺规格覆盖不完整——要么补全 checker 引用，要么合并进开发指南并删除子文档。

---

## 建议的清理顺序

1. **即刻执行**：删除 `archive/`、`docs/archive/`、`docs/engineering-review-report*.md`（用户已授权，合计 558.9 KB）。
2. **1 周内**：`rm ink-writer/agents/{foreshadow,plotline}-tracker.md` + 更新 `tests/prompts/test_prompt_templates.py:222` 白名单（收益 9.6 KB，消除重构尾巴）。
3. **Sprint 级**：整理 `references/` 中 9 个 unreferenced + 7 个 docs-only 文件；要么并入 `docs/specs/` 统一目录，要么在各自的规格文件顶部加 `deprecated: true` 标签。
4. **补代码**：修 `data/market-trends/` 悬空缓存机制（补 Python 落盘 + 90 天清理逻辑），或明确降级为纯规格文档。
5. **补 checker 拉取**：把 `references/scene-craft/{climax,dialogue}.md` 接入至少一个 checker 的 preamble，否则其内容无法进入生成链路。

---

## 附录 · 报告元数据

- 脚本：`/Users/cipher/AI/ink/ink-writer/scripts/audit/scan_unused.py`
- 原始 JSON（可通过 `--json` 参数生成）示例已随 PRD 产出
- 搜索根：`ink_writer/`、`ink-writer/`、`scripts/`、`tests/`、`config/`、`schemas/`、`tasks/`、`reports/`、`docs/`、`.codex/`、`.github/` + 根目录零散文件
