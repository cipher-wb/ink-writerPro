---
name: ink-write
description: Writes ink chapters (default 2000-2500 words). Use when the user asks to write a chapter or runs /ink-write. Runs context, drafting, review, polish, and data extraction.
allowed-tools: Read Write Edit Grep Bash Task
---

# Chapter Writing (Structured Workflow)

## 目标

- 以稳定流程产出可发布章节：优先使用 `正文/第{NNNN}章-{title_safe}.md`，无标题时回退 `正文/第{NNNN}章.md`。
- 默认章节字数目标：2000-2500（用户或大纲明确覆盖时从其约定）。
- 保证审查、润色、数据回写完整闭环，避免“写完即丢上下文”。
- 输出直接可被后续章节消费的结构化数据：`review_metrics`、`summaries`、`chapter_meta`。

## 执行原则

1. 先校验输入完整性，再进入写作流程；缺关键输入时立即阻断。
2. 审查与数据回写是硬步骤，`--fast`/`--minimal` 只允许降级可选环节。
3. 参考资料严格按步骤按需加载，不一次性灌入全部文档。
4. Step 2B 与 Step 4 职责分离：2B 只做风格转译，4 只做问题修复与质控。
5. 任一步失败优先做最小回滚，不重跑全流程。

## 模式定义

- `/ink-write`：Step 1 → 2A → 2B → 3 → 4 → 5 → 6
- `/ink-write --fast`：Step 1 → 2A → 3 → 4 → 5 → 6（跳过 2B）
- `/ink-write --minimal`：Step 1 → 2A → 3（仅3个基础审查）→ 4 → 5 → 6

最小产物（所有模式）：
- `正文/第{NNNN}章-{title_safe}.md` 或 `正文/第{NNNN}章.md`
- `index.db.review_metrics` 新纪录（含 `overall_score`）
- `.ink/summaries/ch{NNNN}.md`
- `.ink/state.json` 的进度与 `chapter_meta` 更新

### 流程硬约束（禁止事项）

- **禁止并步**：不得将两个 Step 合并为一个动作执行（如同时做 2A 和 3）。
- **禁止跳步**：不得跳过未被模式定义标记为可跳过的 Step。
- **禁止临时改名**：不得将 Step 的输出产物改写为非标准文件名或格式。
- **禁止自创模式**：`--fast` / `--minimal` 只允许按上方定义裁剪步骤，不允许自创混合模式、"半步"或"简化版"。
- **禁止自审替代**：Step 3 审查必须由 Task 子代理执行，主流程不得内联伪造审查结论。
- **禁止源码探测**：脚本调用方式以本文档与 data-agent 文档中的命令示例为准，命令失败时查日志定位问题，不去翻源码学习调用方式。

## 引用加载等级（strict, lazy）

- L0：未进入对应步骤前，不加载任何参考文件。
- L1：每步仅加载该步“必读”文件。
- L2：仅在触发条件满足时加载“条件必读/可选”文件。

路径约定：
- `references/...` 相对当前 skill 目录。
- `../../references/...` 指向全局共享参考。

## References（逐文件引用清单）

### 根目录

- `references/step-3-review-gate.md`
  - 用途：Step 3 审查调用模板、汇总格式、落库 JSON 规范。
  - 触发：Step 3 必读。
- `references/step-5-debt-switch.md`
  - 用途：Step 5 债务利息开关规则（默认关闭）。
  - 触发：Step 5 必读。
- `../../references/shared/core-constraints.md`
  - 用途：Step 2A 写作硬约束（大纲即法律 / 设定即物理 / 发明需识别）。
  - 触发：Step 2A 必读。
- `references/polish-guide.md`
  - 用途：Step 4 问题修复、Anti-AI 与 No-Poison 规则。
  - 触发：Step 4 必读。
- `references/writing/typesetting.md`
  - 用途：Step 4 移动端阅读排版与发布前速查。
  - 触发：Step 4 必读。
- `references/style-adapter.md`
  - 用途：Step 2B 风格转译规则，不改剧情事实。
  - 触发：Step 2B 执行时必读（`--fast`/`--minimal` 跳过）。
- `references/style-variants.md`
  - 用途：Step 1（内置 Contract）开头/钩子/节奏变体与重复风险控制。
  - 触发：Step 1 当需要做差异化设计时加载。
- `../../references/reading-power-taxonomy.md`
  - 用途：Step 1（内置 Contract）钩子、爽点、微兑现 taxonomy。
  - 触发：Step 1 当需要追读力设计时加载。
- `../../references/genre-profiles.md`
  - 用途：Step 1（内置 Contract）按题材配置节奏阈值与钩子偏好。
  - 触发：Step 1 当 `state.project.genre` 已知时加载。
- `references/writing/genre-hook-payoff-library.md`
  - 用途：电竞/直播文/克苏鲁的钩子与微兑现快速库。
  - 触发：Step 1 题材命中 `esports/livestream/cosmic-horror` 时必读。

### writing（问题定向加读）

- `references/writing/combat-scenes.md`
  - 触发：战斗章或审查命中“战斗可读性/镜头混乱”。
- `references/writing/dialogue-writing.md`
  - 触发：审查命中 OOC、对话说明书化、对白辨识差。
- `references/writing/emotion-psychology.md`
  - 触发：情绪转折生硬、动机断层、共情弱。
- `references/writing/scene-description.md`
  - 触发：场景空泛、空间方位不清、切场突兀。
- `references/writing/desire-description.md`
  - 触发：主角目标弱、欲望驱动力不足。

## 工具策略（按需）

- `Read/Grep`：读取 `state.json`、大纲、章节正文与参考文件。
- `Bash`：运行 `extract_chapter_context.py`、`index_manager`、`workflow_manager`。
- `Task`：调用审查 subagent、`data-agent`；`context-agent` 仅在 Step 1 脚本构建失败时兜底。

## 交互流程

### Step 0：预检与上下文最小加载

必须做：
- 解析真实书项目根（book project_root）：必须包含 `.ink/state.json`。
- 校验核心输入：`大纲/总纲.md`、`${CLAUDE_PLUGIN_ROOT}/scripts/extract_chapter_context.py` 存在。
- 规范化变量：
  - `WORKSPACE_ROOT`：Claude Code 打开的工作区根目录（可能是书项目的父目录，例如 `D:\wk\xiaoshuo`）
  - `PROJECT_ROOT`：真实书项目根目录（必须包含 `.ink/state.json`，例如 `D:\wk\xiaoshuo\凡人资本论`）
  - `SKILL_ROOT`：skill 所在目录（固定 `${CLAUDE_PLUGIN_ROOT}/skills/ink-write`）
  - `SCRIPTS_DIR`：脚本目录（固定 `${CLAUDE_PLUGIN_ROOT}/scripts`）
  - `chapter_num`：当前章号（整数）
  - `chapter_padded`：四位章号（如 `0007`）

环境设置（bash 命令执行前）：
```bash
export WORKSPACE_ROOT="${INK_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  if [ -d "$PWD/scripts" ] && [ -d "$PWD/skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$PWD"
  elif [ -d "$PWD/../scripts" ] && [ -d "$PWD/../skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$(cd "$PWD/.." && pwd)"
  else
    echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT，且无法从当前目录推断插件根目录" >&2
    exit 1
  fi
fi

export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is required}/skills/ink-write"

python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where)"
```

**硬门槛**：`preflight` 必须成功。它统一校验 `CLAUDE_PLUGIN_ROOT` 派生出的 `SKILL_ROOT` / `SCRIPTS_DIR`、`ink.py`、`extract_chapter_context.py` 和解析出的 `PROJECT_ROOT`。任一失败都立即阻断。

输出：
- “已就绪输入”与“缺失输入”清单；缺失则阻断并提示先补齐。

### Step 0.5：工作流断点记录（best-effort，不阻断）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-task --command ink-write --chapter {chapter_num} || true
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-step --step-id "Step 1" --step-name "Context Build" || true
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step --step-id "Step 1" --artifacts '{"ok":true}' || true
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-task --artifacts '{"ok":true}' || true
```

要求：
- `--step-id` 仅允许：`Step 1` / `Step 2A` / `Step 2B` / `Step 3` / `Step 4` / `Step 5` / `Step 6`。
- 任何记录失败只记警告，不阻断写作。
- 每个 Step 执行结束后，同样需要 `complete-step`（失败不阻断）。

### Step 0.6：重入续跑规则（当 `start-task` 提示“任务已在运行”时必须执行）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow detect
```

硬规则：
- 若 `workflow detect` 显示当前运行任务与本次请求的 `command/chapter` 一致，必须从 `current_step` 继续，不得重新从 Step 1 开始。
- 已完成 Step 只允许复用其产物，不得再次 `start-step` 覆盖；活跃 Step 未完成前，禁止启动不同 Step。
- 若 `current_step` 为 `Step 3`，必须先完成审查并落库 `review_metrics`，然后才能进入 Step 4/5。
- 若 `current_step` 为 `Step 5`，只允许重跑 Data Agent；Step 1-4 视为已通过，禁止回滚整个写作链。
- 若 `workflow detect` 显示活跃 Step 与当前文件状态明显冲突，先执行 `workflow fail-task` 或显式改走 `/ink-resume`，不得私自覆盖当前 Step。

按 `current_step.id` 的续跑映射：
- `Step 1`：只完成脚本执行包构建（失败时才走 `context-agent` 兜底），然后进入 `Step 2A`
- `Step 2A`：只继续/重写正文，不得重复 `Step 1`
- `Step 2B`：只继续风格适配，不得跳去 `Step 4/5`
- `Step 3`：只完成审查、汇总、`save-review-metrics`
- `Step 4`：只基于现有审查结论润色，随后进入 `Step 5`
- `Step 5`：只重跑 Data Agent 并校验 `state/index/summary`
- `Step 6`：只处理 Git 备份与收尾验证

### Step 1：脚本执行包构建（默认）/ Context Agent（兜底）

默认路径：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" extract-context --chapter {chapter_num} --format pack
```

兜底路径（仅当默认路径失败、超时、或输出缺关键字段时才允许）：
- 使用 `Task` 调用 `context-agent`
- 参数：
  - `chapter`
  - `project_root`
  - `storage_path=.ink/`
  - `state_file=.ink/state.json`

兜底前置要求：
- 先执行一次：
```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" extract-context --chapter {chapter_num} --format pack-json
```
- `context-agent` 必须优先消费这份 `pack-json`，只补它缺失的字段，禁止重新把 `state.json`、`summaries`、`index`、`extract-context --format json` 全量重复读一遍。

硬要求：
- 若 `state` 或大纲不可用，立即阻断并返回缺失项。
- 当 `chapter <= 3` 时，必须额外读取 `.ink/golden_three_plan.json` 与 `.ink/preferences.json`，进入黄金三章模式。
- 输出必须同时包含：
  - 8 板块任务书（本章核心任务/接住上章/角色/场景与力量约束/时间约束/风格指导/连续性与伏笔/追读力策略）；
  - Context Contract 全字段（目标/阻力/代价/本章变化/未闭合问题/开头类型/情绪节奏/信息密度/过渡章判定/追读力设计）；
  - 若 `chapter <= 3`：额外包含 `golden_three_role / opening_window_chars / reader_promise / must_deliver_this_chapter / end_hook_requirement`；
  - Step 2A 可直接消费的“写作执行包”（章节节拍、不可变事实清单、禁止事项、终检清单）。
- 合同与任务书出现冲突时，以“大纲与设定约束更严格者”为准。
- 默认应直接复用脚本产出的 execution pack，不再起子代理做二次整理。

输出：
- 单一“创作执行包”（任务书 + Context Contract + 直写提示词），供 Step 2A 直接消费，不再拆分独立 Step 1.5。

### Step 2A：正文起草

执行前必须加载：
```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"
```

硬要求：
- 只输出纯正文到章节正文文件；若详细大纲已有章节名，优先使用 `正文/第{chapter_padded}章-{title_safe}.md`，否则回退为 `正文/第{chapter_padded}章.md`。
- 默认按 2000-2500 字执行；若大纲为关键战斗章/高潮章/卷末章或用户明确指定，则按大纲/用户优先。
- 禁止占位符正文（如 `[TODO]`、`[待补充]`）。
- 保留承接关系：若上章有明确钩子，本章必须回应（可部分兑现）。

中文思维写作约束（硬规则）：
- **禁止"先英后中"**：不得先用英文工程化骨架（如 ABCDE 分段、Summary/Conclusion 框架）组织内容，再翻译成中文。
- **中文叙事单元优先**：以"动作、反应、代价、情绪、场景、关系位移"为基本叙事单元，不使用英文结构标签驱动正文生成。
- **禁止英文结论话术**：正文、审查说明、润色说明、变更摘要、最终报告中不得出现 Overall / PASS / FAIL / Summary / Conclusion 等英文结论标题。
- **英文仅限机器标识**：CLI flag（`--fast`）、checker id（`consistency-checker`）、DB 字段名（`anti_ai_force_check`）、JSON 键名等不可改的接口名保持英文，其余一律使用简体中文。

输出：
- 章节草稿（可进入 Step 2B 或 Step 3）。

### Step 2B：风格适配（`--fast` / `--minimal` 跳过）

执行前加载：
```bash
cat "${SKILL_ROOT}/references/style-adapter.md"
```

硬要求：
- 只做表达层转译，不改剧情事实、事件顺序、角色行为结果、设定规则。
- 对“模板腔、说明腔、机械腔”做定向改写，为 Step 4 留出问题修复空间。
- 必须优先读取本地高分 `style_samples`；若 `chapter <= 3`，优先选择更能匹配开头窗口、对白密度、句长节奏的样本。
- 若 Anti-AI 检查未通过，不得把该版正文交给 Step 3。

输出：
- 风格化正文（覆盖原章节文件）。

### Step 3：审查（auto 路由，必须由 Task 子代理执行）

执行前加载：
```bash
cat "${SKILL_ROOT}/references/step-3-review-gate.md"
```

调用约束：
- 必须用 `Task` 调用审查 subagent，禁止主流程伪造审查结论。
- 可并行发起审查，统一汇总 `issues/severity/overall_score`。
- 默认使用 `auto` 路由：根据“本章执行合同 + 正文信号 + 大纲标签”动态选择审查器。

核心审查器（始终执行）：
- `consistency-checker`
- `continuity-checker`
- `ooc-checker`

条件审查器（`auto` 命中时执行）：
- `golden-three-checker`
- `reader-pull-checker`
- `high-point-checker`
- `pacing-checker`

模式说明：
- 标准/`--fast`：核心 3 个 + auto 命中的条件审查器
- `--minimal`：只跑核心 3 个（忽略条件审查器）

审查指标落库（必做）：
```bash
mkdir -p "${PROJECT_ROOT}/.ink/tmp"
# 生成 review_metrics.json 时，优先使用 Bash heredoc 写入；
# 不要用 Write 直接创建一个尚未读取过的新文件，避免工具链拒绝创建。
# 例如：
# cat > "${PROJECT_ROOT}/.ink/tmp/review_metrics.json" <<'JSON'
# {...}
# JSON
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index save-review-metrics --data "@${PROJECT_ROOT}/.ink/tmp/review_metrics.json"
```

review_metrics 字段约束（当前工作流约定只传以下字段）：
```json
{
  "start_chapter": 100,
  "end_chapter": 100,
  "overall_score": 85.0,
  "dimension_scores": {"爽点密度": 8.5, "设定一致性": 8.0, "节奏控制": 7.8, "人物塑造": 8.2, "连贯性": 9.0, "追读力": 8.7},
  "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
  "critical_issues": ["问题描述"],
  "report_file": "审查报告/第100-100章审查报告.md",
  "notes": "单个字符串；摘要给人读",
  "review_payload_json": {
    "selected_checkers": ["consistency-checker", "continuity-checker"],
    "timeline_gate": "pass",
    "anti_ai_force_check": "pass",
    "golden_three_metrics": {}
  }
}
```
- `notes` 在当前执行契约中必须是单个字符串，不得传入对象或数组。
- `review_payload_json` 用于结构化扩展信息；黄金三章指标必须写入 `golden_three_metrics`。

硬要求：
- `--minimal` 也必须产出 `overall_score`。
- 当 `chapter <= 3` 时，`golden-three-checker` 未通过不得放行。
- 未落库 `review_metrics` 不得进入 Step 5。

### Step 4：润色（问题修复优先）

执行前必须加载：
```bash
cat "${SKILL_ROOT}/references/polish-guide.md"
cat "${SKILL_ROOT}/references/writing/typesetting.md"
```

执行顺序：
1. 修复 `critical`（必须）
2. 修复 `high`（不能修复则记录 deviation）
3. 处理 `medium/low`（按收益择优）
4. 执行 Anti-AI 与 No-Poison 全文终检（必须输出 `anti_ai_force_check: pass/fail`）

黄金三章定向修复（当 `chapter <= 3` 时必须执行）：
- 前移触发点，禁止把强事件压到开头窗口之后。
- 压缩背景说明、长回忆、空景描写。
- 强化主角差异点与本章可见回报。
- 增强章末动机句，确保读者必须点下一章。

输出：
- 润色后正文（覆盖章节文件）
- 变更摘要（至少含：修复项、保留项、deviation、`anti_ai_force_check`）

### Step 5：Data Agent（状态与索引回写）

使用 Task 调用 `data-agent`，参数：
- `chapter`
- `chapter_file` 必须传入实际章节文件路径；若详细大纲已有章节名，优先传 `正文/第{chapter_padded}章-{title_safe}.md`，否则传 `正文/第{chapter_padded}章.md`
- `review_score=Step 3 overall_score`
- `project_root`
- `storage_path=.ink/`
- `state_file=.ink/state.json`

Data Agent 默认子步骤（全部执行）：
- A. 加载上下文
- B. AI 实体提取
- C. 实体消歧
- D. 统一走 `state process-chapter` 写入 state/index
- E. 写入章节摘要
- F. AI 场景切片
- G. RAG 向量索引（`rag index-chapter --scenes ...`）
- H. 风格样本评估（`style extract --scenes ...`，仅 `review_score >= 80` 时）
- I. 债务利息（默认跳过）

黄金三章回写要求（当 `chapter <= 3` 时）：
- `reading_power` 必须尽量补全：
  - `golden_three_role`
  - `opening_trigger_type`
  - `opening_trigger_position`
  - `reader_promise`
  - `visible_change`
  - `next_chapter_drive`
  - `golden_three_metrics`
- `chapter_meta.golden_three` 作为兼容镜像同步写入。

`--scenes` 来源优先级（G/H 步骤共用）：
1. 优先从 `index.db` 的 scenes 记录获取（Step F 写入的结果）
2. 其次按 `start_line` / `end_line` 从正文切片构造
3. 最后允许单场景退化（整章作为一个 scene）

Step 5 强约束：
- 禁止用手工整体重写 `.ink/state.json` 代替 `state process-chapter`。
- 必须先生成完整 Data Agent payload，再执行：

```bash
cat > "${PROJECT_ROOT}/.ink/tmp/data_agent_payload_ch${chapter_padded}.json" <<'EOF'
{...完整 JSON...}
EOF

python3 -X utf8 "${SCRIPTS_DIR}/ink.py" \
  --project-root "${PROJECT_ROOT}" \
  state process-chapter \
  --chapter {chapter_num} \
  --data @"${PROJECT_ROOT}/.ink/tmp/data_agent_payload_ch${chapter_padded}.json"
```

- 上述 payload 必须包含并显式落库这些字段：
  - `scenes`
  - `chapter_meta`
  - `chapter_memory_card`
  - `timeline_anchor`
  - `plot_thread_updates`
  - `reading_power`
  - `candidate_facts`
- `chapter <= 3` 时，`reading_power` 必须包含：
  - `golden_three_role`
  - `opening_trigger_type`
  - `opening_trigger_position`
  - `reader_promise`
  - `visible_change`
  - `next_chapter_drive`
- 若缺这些字段，不得宣称 Step 5 完成。

Step 5 失败隔离规则：
- 若 G/H 失败原因是 `--scenes` 缺失、scene 为空、scene JSON 格式错误：只补跑 G/H 子步骤，不回滚或重跑 Step 1-4。
- 若 A-E 失败（state/index/summary 写入失败）：仅重跑 Step 5，不回滚已通过的 Step 1-4。
- 禁止因 RAG/style 子步骤失败而重跑整个写作链。

执行后检查（最小白名单）：
- `.ink/state.json`
- `.ink/index.db`
- `.ink/summaries/ch{chapter_padded}.md`
- `.ink/observability/data_agent_timing.jsonl`（观测日志）
- `chapter_memory_cards.chapter={chapter_num}`
- `chapter_reading_power.chapter={chapter_num}`
- `scenes.chapter={chapter_num}`

Step 5 收尾动作必须按这个顺序执行：
1. 先验证上述文件和结构化表记录全部存在。
2. 验证通过后再执行：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step \
  --step-id "Step 5" \
  --artifacts '{"ok":true,"state_updated":true,"index_updated":true,"summary_created":true}'
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-step \
  --step-id "Step 6" \
  --step-name "Git备份"
```

3. 若结构化表缺失，禁止执行 `workflow complete-step --step-id "Step 5"`，必须继续修复 Step 5。

性能要求：
- 读取 timing 日志最近一条；
- 当 `TOTAL > 30000ms` 时，输出最慢 2-3 个环节与原因说明。

观测日志说明：
- `call_trace.jsonl`：外层流程调用链（agent 启动、排队、环境探测等系统开销）。
- `data_agent_timing.jsonl`：Data Agent 内部各子步骤耗时。
- 当外层总耗时远大于内层 timing 之和时，默认先归因为 agent 启动与环境探测开销，不误判为正文或数据处理慢。

债务利息：
- 默认关闭，仅在用户明确要求或开启追踪时执行（见 `step-5-debt-switch.md`）。

### Step 6：Git 备份（可失败但需说明）

```bash
git add .
git -c i18n.commitEncoding=UTF-8 commit -m "第{chapter_num}章: {title}"
```

规则：
- 提交时机：验证、回写、清理全部完成后最后执行。
- 提交信息默认中文，格式：`第{chapter_num}章: {title}`。
- 若 commit 失败，必须给出失败原因与未提交文件范围。
- Step 6 收尾必须显式执行：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step \
  --step-id "Step 6" \
  --artifacts '{"ok":true,"git_backup":true}'
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-task \
  --artifacts '{"ok":true,"git_backup":true}'
```

- 若 Git 因 `user.name / user.email` 未配置而跳过，也必须显式完成 Step 6 与任务：

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step \
  --step-id "Step 6" \
  --artifacts '{"ok":true,"git_backup":false,"reason":"git_author_identity_unknown"}'
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-task \
  --artifacts '{"ok":true,"git_backup":false,"reason":"git_author_identity_unknown"}'
```

## 充分性闸门（必须通过）

未满足以下条件前，不得结束流程：

1. 章节正文文件存在且非空：`正文/第{chapter_padded}章-{title_safe}.md` 或 `正文/第{chapter_padded}章.md`
2. Step 3 已产出 `overall_score` 且 `review_metrics` 成功落库
3. Step 4 已处理全部 `critical`，`high` 未修项有 deviation 记录
4. Step 4 的 `anti_ai_force_check=pass`（基于全文检查；fail 时不得进入 Step 5）
5. Step 5 已回写 `state.json`、`index.db`、`summaries/ch{chapter_padded}.md`
6. 若开启性能观测，已读取最新 timing 记录并输出结论

## 验证与交付

执行检查：

```bash
test -f "${PROJECT_ROOT}/.ink/state.json"
test -f "${PROJECT_ROOT}/正文/第${chapter_padded}章.md"
test -f "${PROJECT_ROOT}/.ink/summaries/ch${chapter_padded}.md"
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index get-recent-review-metrics --limit 1
tail -n 1 "${PROJECT_ROOT}/.ink/observability/data_agent_timing.jsonl" || true
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "SELECT COUNT(*) FROM chapter_memory_cards WHERE chapter=${chapter_num};"
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "SELECT COUNT(*) FROM chapter_reading_power WHERE chapter=${chapter_num};"
sqlite3 "${PROJECT_ROOT}/.ink/index.db" "SELECT COUNT(*) FROM scenes WHERE chapter=${chapter_num};"
```

成功标准：
- 章节文件、摘要文件、状态文件齐全且内容可读。
- 审查分数可追溯，`overall_score` 与 Step 5 输入一致。
- 润色后未破坏大纲与设定约束。
- `chapter_memory_cards / chapter_reading_power / scenes` 对当前章节均非空。

## 失败处理（最小回滚）

触发条件：
- 章节文件缺失或空文件；
- 审查结果未落库；
- Data Agent 关键产物缺失；
- 润色引入设定冲突。

恢复流程：
1. 仅重跑失败步骤，不回滚已通过步骤。
2. 常见最小修复：
   - 审查缺失：只重跑 Step 3 并落库；
   - 润色失真：恢复 Step 2A 输出并重做 Step 4；
   - 摘要/状态缺失：只重跑 Step 5；
3. 重新执行“验证与交付”全部检查，通过后结束。
