---
name: ink-write
description: Writes ink chapters (minimum 2200 words). Use when the user asks to write a chapter or runs /ink-write. Runs context, drafting, review, polish, and data extraction.
allowed-tools: Read Write Edit Grep Bash Task
---

# Chapter Writing (Structured Workflow)

## 目标

- 以稳定流程产出可发布章节：优先使用 `正文/第{NNNN}章-{title_safe}.md`，无标题时回退 `正文/第{NNNN}章.md`。
- 默认章节字数目标：2200-3000（硬下限 2200 字，不可突破；用户或大纲明确覆盖时从其约定，但不得低于 2200）。
- 保证审查、润色、数据回写完整闭环，避免“写完即丢上下文”。
- 输出直接可被后续章节消费的结构化数据：`review_metrics`、`summaries`、`chapter_meta`。

## 执行原则

1. 先校验输入完整性，再进入写作流程；缺关键输入时立即阻断。
2. 审查与数据回写是硬步骤，不可跳过或降级。
3. 参考资料严格按步骤按需加载，不一次性灌入全部文档。
4. Step 2B 与 Step 4 职责分离：2B 只做风格转译，4 只做问题修复与质控。
5. 任一步失败优先做最小回滚，不重跑全流程。

## 模式定义

- `/ink-write`：Step 1 → 2A → 2A.5 → 2B → 3 → 4 → 4.5 → 5 → 6

### Agent 调用成本控制策略

> 长篇写作的 Agent 调用量线性增长（每章 5-9 个子 Agent），需要系统性控制成本。

#### 单章成本预算

每章预估 Agent 调用数：7-10 个（context + writer + 2B 风格适配 + 全量 checker + data）

#### 成本观测（每章结束后输出）

在 Step 6 收尾时，统计并输出本章 Agent 调用摘要：

```text
本章 Agent 调用统计：
- 总调用数: {N} 个
- 实际启用 checker: {list}
- 审查模式: standard
- 耗时最长环节: {step} ({ms}ms)
```

数据来源：`.ink/observability/call_trace.jsonl` + `data_agent_timing.jsonl`

#### 批量写作说明（`--batch N`）

`--batch N` 的每章流程与单章 `/ink-write` 完全一致：
- 每章独立执行完整的 Step 0 → Step 6，不复用上一章的 context、checker 缓存或 Data Agent 结果
- 详细编排逻辑见文件末尾"批量模式编排"区域

#### 项目级成本仪表盘

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" status -- --focus cost
```

输出：
```text
项目成本概览：
- 总章节: {N} 章
- 总 Agent 调用: {total} 次
- 平均每章调用: {avg} 次
- 最高成本章节: 第 {ch} 章（{count} 次调用，原因：{reason}）
```

批量模式：
- `/ink-write --batch N`：连续写 N 章，每章完整执行标准流程
- 未指定 N 时默认 5 章
- `--batch` 不改变任何单章内部流程，仅在 Step 6 完成后自动开始下一章的 Step 0

最小产物（所有模式）：
- `正文/第{NNNN}章-{title_safe}.md` 或 `正文/第{NNNN}章.md`
- `index.db.review_metrics` 新纪录（含 `overall_score`）
- `.ink/summaries/ch{NNNN}.md`
- `.ink/state.json` 的进度与 `chapter_meta` 更新

### 流程硬约束（禁止事项）

- **禁止并步**：不得将两个 Step 合并为一个动作执行（如同时做 2A 和 3）。
- **禁止跳步**：不得跳过任何 Step。
- **禁止临时改名**：不得将 Step 的输出产物改写为非标准文件名或格式。
- **禁止自创模式**：不允许自创"简化版"、"快速版"或跳过任何标准流程步骤。
- **禁止自审替代**：Step 3 审查必须由 Task 子代理执行，主流程不得内联伪造审查结论。
- **禁止源码探测**：脚本调用方式以本文档与 data-agent 文档中的命令示例为准，命令失败时查日志定位问题，不去翻源码学习调用方式。
- **禁止直写 state.json**：所有对 `.ink/state.json` 的写入必须通过 `ink.py` CLI 命令（`state process-chapter`、`update-state`、`workflow *`），禁止用 `Write`/`Edit` 工具直接修改。Step 5 Data Agent 执行期间，主流程不得调用任何写入 state.json 的命令。
- **禁止批量偷懒**：`--batch` 模式下，每一章必须完整执行 Step 0 → Step 6 的全部步骤，不得因"已是第 N 章"而简化、合并或跳过任何环节。第 5 章的流程严格程度必须与第 1 章完全一致。
- **禁止批量并行**：多章必须严格串行执行。第 i 章的充分性闸门和验证全部通过后，才能开始第 i+1 章的 Step 0。
- **禁止批量中途询问**：`--batch` 模式下，禁止在章节之间停下来询问用户"是否继续"、"要不要写下一章"、"需要确认吗"等。用户指定了 `--batch N` 就是明确授权连续写 N 章，必须自动执行到全部完成或遇到失败为止。唯一允许暂停的情况是：章节写作失败且重试后仍失败、章号与预期不一致、大纲缺失。

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
  - 触发：Step 2B 执行时必读。
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
- `references/anti-detection-writing.md`
  - 用途：Step 2A 防AI检测源头写作指南（句长突发度/信息密度波动/逻辑跳跃/对话人类化/词汇意外性/段落碎片化/视角限制）。
  - 触发：Step 2A 必读。

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

**大纲覆盖硬检查**（preflight 通过后、进入 Step 0.5 之前必须执行）：

```bash
python3 -X utf8 “${SCRIPTS_DIR}/ink.py” --project-root “${PROJECT_ROOT}” extract-context --chapter {chapter_num} --format pack 2>&1 | head -5
```

检查输出前5行是否包含 `⚠️` 或 `未找到` 或 `不存在`。若包含，说明第 `{chapter_num}` 章没有详细大纲覆盖。

**处理规则**：
- 若输出包含”大纲文件不存在”或”未找到第X章的大纲” → **立即阻断**，输出：
  ```
  ❌ 第{chapter_num}章没有详细大纲，禁止写作。
  请先执行 /ink-plan 生成对应卷的详细大纲，再重新执行 /ink-write。
  ```
- 禁止在无大纲时自行编造章节内容，禁止用总纲替代详细大纲。
- 此检查不可跳过、不可兜底、不可降级。

输出：
- “已就绪输入”与”缺失输入”清单；缺失则阻断并提示先补齐。

**写作前里程碑强制审查**（大纲检查通过后、逾期伏笔检查之前执行）：

读取 `progress.current_chapter`，计算 `next_chapter = current_chapter + 1`。按以下优先级检测（**只触发最高级别的一条**，执行完审查后自动继续写作）：

1. 若 `next_chapter % 200 == 0`（200章里程碑）：
   输出：
   ```
   🏆 第{next_chapter}章触发 200 章里程碑强制审查，写作暂停，开始执行审查...
   ```
   **强制执行以下审查，全部完成后再继续写作**：
   - 执行 `/ink-audit deep`（全量数据对账）。等待审查完成并输出报告。
   - 执行 `/ink-macro-review Tier3`（跨卷叙事审查）。等待审查完成并输出报告。
   - 两项审查全部完成后，输出：
     ```
     ✅ 200章里程碑审查完成，继续写作第{next_chapter}章...
     ```
   - 然后自动继续后续步骤（逾期伏笔检查 → Step 0.5 → ...）。

2. 否则，若 `next_chapter % 50 == 0`（50章检查点）：
   输出：
   ```
   📋 第{next_chapter}章触发 50 章检查点强制审查，写作暂停，开始执行审查...
   ```
   **强制执行以下审查，全部完成后再继续写作**：
   - 执行 `/ink-audit standard`（标准数据对账）。等待审查完成并输出报告。
   - 执行 `/ink-macro-review Tier2`（宏观叙事审查）。等待审查完成并输出报告。
   - 两项审查全部完成后，输出：
     ```
     ✅ 50章检查点审查完成，继续写作第{next_chapter}章...
     ```
   - 然后自动继续后续步骤。

3. 否则，若 `next_chapter % 25 == 0`（25章快检点）：
   输出：
   ```
   🔍 第{next_chapter}章触发 25 章快检点强制审查，写作暂停，开始执行审查...
   ```
   **强制执行**：
   - 执行 `/ink-audit quick`（快速数据健康检查）。等待审查完成并输出报告。
   - 审查完成后，输出：
     ```
     ✅ 25章快检完成，继续写作第{next_chapter}章...
     ```
   - 然后自动继续后续步骤。

4. 否则 → 无审查，直接继续。

**此检查为强制执行，不可跳过、不可降级。** 审查发现的问题记录在审查报告中，不阻断本次写作（但会注入到 Context Agent 的 alerts 板块中影响本章写作）。

**逾期伏笔检查**（大纲检查通过后、进入 Step 0.5 之前执行）：

```bash
python3 -X utf8 -c “
import json, sqlite3
from pathlib import Path
project_root = '${PROJECT_ROOT}'
state = json.loads(Path(f'{project_root}/.ink/state.json').read_text())
current = state.get('progress', {}).get('current_chapter', 0)
grace = 10
db_path = f'{project_root}/.ink/index.db'
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        'SELECT thread_id, title, content, target_payoff_chapter FROM plot_thread_registry '
        'WHERE status = ? AND target_payoff_chapter IS NOT NULL AND target_payoff_chapter < ?',
        ('active', current - grace)
    ).fetchall()
    conn.close()
    if rows:
        print(f'⚠️ 发现 {len(rows)} 条逾期伏笔（超过目标章节{grace}章以上仍未解决）：')
        for r in rows:
            overdue = current - r[3]
            print(f'  - [{r[0]}] {r[1]}: 目标ch{r[3]}, 已逾期{overdue}章')
    else:
        print('✅ 无逾期伏笔')
except Exception as e:
    print(f'⚠️ 伏笔检查跳过（数据库不可用）: {e}')
“
```

**处理规则**：
- 若存在逾期超过10章的活跃伏笔 → 输出警告列表：
  ```
  ⚠️ 发现 {N} 条逾期伏笔（超过目标章节10章以上仍未解决）：
  - [{thread_id}] {title}: 目标ch{target}, 当前已逾期{overdue}章
  建议：在本章解决，或通过 /ink-plan 显式延期目标章节。
  ```
- 此检查为**警告模式**（不强制阻断），但会在 Context Agent Board 7 中强制置顶逾期伏笔。

### Step 0.7：金丝雀健康扫描（Canary Health Scan）

> **设计目的**：将 ink-macro-review 和 ink-audit 的核心检查能力前移到每章写作前执行，做到"写一章就保证一章正确"。所有检查为轻量 SQL 查询 + JSON 比对，零额外子代理开销。
>
> **兼容性保证**：所有查询均包裹 `try...except`，表不存在或数据为空时返回空结果（检查通过）。第 1 章写作时所有表为空，所有检查自动通过。任何金丝雀脚本执行异常只输出 `⚠️ canary_skipped`，不阻断写作。

**执行时机**：逾期伏笔检查通过后、进入 Step 0.5 之前。

#### A.1 主角状态同步检查（CRITICAL + 自动修复 + 复检闸门）

> 来源：ink-audit Quick #1。以 index.db 为权威数据源（因为它是 `state process-chapter` 写入的结果），检测 state.json 是否与之一致。

```bash
python3 -X utf8 -c "
import json, sqlite3, sys
from pathlib import Path
project_root = '${PROJECT_ROOT}'
state_path = Path(f'{project_root}/.ink/state.json')
db_path = f'{project_root}/.ink/index.db'

state = json.loads(state_path.read_text())
protag = state.get('protagonist_state', {})

try:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        'SELECT canonical_name, current_json FROM entities WHERE is_protagonist = 1 LIMIT 1'
    ).fetchone()
    conn.close()
except Exception as e:
    print(f'⚠️ canary_skipped: 主角状态检查跳过（数据库不可用）: {e}')
    sys.exit(0)

if not row:
    print('✅ 主角状态检查跳过（index.db 无主角记录，可能是新项目）')
    sys.exit(0)

current = json.loads(row[1] or '{}')
s_realm = protag.get('power', {}).get('realm', '')
d_realm = current.get('realm', '')
s_loc = protag.get('location', {}).get('current', '')
d_loc = current.get('location', '')

issues = []
if s_realm and d_realm and s_realm != d_realm:
    issues.append(('realm', s_realm, d_realm))
if s_loc and d_loc and s_loc != d_loc:
    issues.append(('location', s_loc, d_loc))

if issues:
    details = '; '.join(f'{k}: state.json={sv} vs index.db={dv}' for k, sv, dv in issues)
    print(f'⚠️ 主角状态不一致: {details}')
    print('CANARY_PROTAGONIST_SYNC=fail')
    for k, sv, dv in issues:
        print(f'CANARY_FIX_{k.upper()}={dv}')
else:
    print('✅ 主角状态同步')
    print('CANARY_PROTAGONIST_SYNC=pass')
"
```

**自动修复流程**（当输出 `CANARY_PROTAGONIST_SYNC=fail` 时执行）：

1. 以 index.db 为准同步 state.json：
```bash
# 若 realm 不一致：
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  update-state --protagonist-power "${CANARY_FIX_REALM}" \
  "$(python3 -c "import json; s=json.loads(open('${PROJECT_ROOT}/.ink/state.json').read()); print(s.get('protagonist_state',{}).get('power',{}).get('layer','1'))")" \
  "$(python3 -c "import json; s=json.loads(open('${PROJECT_ROOT}/.ink/state.json').read()); print(s.get('protagonist_state',{}).get('power',{}).get('bottleneck','无'))")"

# 若 location 不一致：
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  update-state --protagonist-location "${CANARY_FIX_LOCATION}" "${chapter_num}"
```

2. **复检**：修复后重新执行上方 A.1 检测脚本。
3. **闸门**：复检输出 `CANARY_PROTAGONIST_SYNC=pass` → 继续；仍为 `fail` → 输出 `❌ 主角状态同步失败（自动修复后仍不一致），请手动检查 .ink/state.json 和 .ink/index.db`，**阻断写作**。
4. **最多重试 1 次**，不无限循环。

#### A.2 角色发展停滞检测（WARNING → 注入执行包）

> 来源：ink-macro-review 2.2。检测核心/重要角色是否长期无演变记录。

```bash
python3 -X utf8 -c "
import sqlite3, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute('''
        SELECT e.canonical_name, e.tier,
               (SELECT MAX(chapter) FROM chapters) - COALESCE(MAX(cel.chapter), 0) as stagnant_chapters
        FROM entities e
        LEFT JOIN character_evolution_ledger cel ON e.id = cel.entity_id
        WHERE e.type = '角色' AND e.tier IN ('核心', '重要') AND e.is_archived = 0
        GROUP BY e.id
        HAVING stagnant_chapters > 40
        ORDER BY stagnant_chapters DESC LIMIT 5
    ''').fetchall()
    conn.close()
    if rows:
        print('⚠️ 角色发展停滞警告：')
        for name, tier, stagnant in rows:
            print(f'  CANARY_STAGNANT: {name}（{tier}）已 {stagnant} 章无角色发展记录')
    else:
        print('✅ 无角色发展停滞')
except Exception as e:
    print(f'⚠️ canary_skipped: 角色停滞检查跳过: {e}')
"
```

**处理规则**：
- 非阻断，输出结果保存为 `canary_stagnant_characters` 列表，在 Step 1 注入到创作执行包。
- 注入文本格式：`"角色 {name}（{tier}）已 {N} 章无角色发展记录，本章若出场必须展现变化（行为/态度/能力/关系至少一项）"`

#### A.3 冲突模式重复检测（WARNING → 注入执行包）

> 来源：ink-macro-review 2.3。检测最近 30 章内是否有重复 3+ 次的冲突模式。

```bash
python3 -X utf8 -c "
import sqlite3, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute('''
        SELECT conflict_type, resolution_mechanism, COUNT(*) as count,
               GROUP_CONCAT(chapter) as chapters
        FROM plot_structure_fingerprints
        WHERE chapter >= (SELECT MAX(chapter) FROM chapters) - 30
        GROUP BY conflict_type, resolution_mechanism
        HAVING COUNT(*) >= 3
        ORDER BY count DESC
    ''').fetchall()
    conn.close()
    if rows:
        print('⚠️ 冲突模式重复警告：')
        for ctype, rmech, count, chs in rows:
            print(f'  CANARY_CONFLICT_REPEAT: {ctype}+{rmech} 在最近30章出现{count}次 (ch{chs})')
    else:
        print('✅ 无冲突模式重复')
except Exception as e:
    print(f'⚠️ canary_skipped: 冲突模式检查跳过: {e}')
"
```

**处理规则**：
- 非阻断，输出结果保存为 `canary_conflict_repetitions` 列表，在 Step 1 注入到创作执行包。
- 注入文本格式：`"本章禁止使用 {conflict_type}+{resolution_mechanism} 冲突模式（最近30章已用{count}次）"`

#### A.4 消歧积压警告（ADVISORY）

> 来源：ink-audit Quick #4。

```bash
python3 -X utf8 -c "
import json
from pathlib import Path
state = json.loads(Path('${PROJECT_ROOT}/.ink/state.json').read_text())
pending = state.get('disambiguation_pending', [])
count = len(pending)
if count > 50:
    print(f'⚠️ 消歧积压严重: {count}条，强烈建议运行 /ink-resolve')
elif count > 30:
    print(f'⚠️ 消歧积压: {count}条，建议运行 /ink-resolve')
else:
    print(f'✅ 消歧积压正常（{count}条）')
"
```

**处理规则**：仅提醒，不阻断，不注入执行包。

#### A.5 时间线链条验证（WARNING → 注入执行包）

> 来源：ink-audit Standard #7。检查最近 10 章时间线锚点的逻辑一致性。

```bash
python3 -X utf8 -c "
import sqlite3, json, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute('''
        SELECT chapter, anchor_time, countdown, relative_to_previous
        FROM timeline_anchors
        WHERE chapter >= (SELECT MAX(chapter) FROM chapters) - 10
        ORDER BY chapter ASC
    ''').fetchall()
    conn.close()
    if not rows:
        print('✅ 时间线检查跳过（无锚点数据）')
        sys.exit(0)
    issues = []
    prev_time = None
    prev_chapter = None
    for chapter, anchor_time, countdown, rel in rows:
        if prev_time and anchor_time and rel:
            # 检查是否存在无闪回标记的时间倒退
            if '倒退' in str(rel) or '之前' in str(rel):
                issues.append(f'ch{prev_chapter}→ch{chapter}: 时间倒退（{rel}），请确认是否为闪回')
        prev_time = anchor_time
        prev_chapter = chapter
    if issues:
        print('⚠️ 时间线一致性警告：')
        for issue in issues:
            print(f'  CANARY_TIMELINE: {issue}')
    else:
        print('✅ 时间线链条一致')
except Exception as e:
    print(f'⚠️ canary_skipped: 时间线检查跳过: {e}')
"
```

**处理规则**：
- 非阻断，输出结果在 Step 1 注入执行包的时间约束板块。

#### A.6 遗忘伏笔补充检测（WARNING → 注入执行包）

> 来源：ink-macro-review 2.4。与 Step 0 的逾期伏笔检查互补——逾期检查看 `target_payoff_chapter`（有明确目标的伏笔），本检查看 `last_touched_chapter`（所有活跃但已沉默 30+ 章的伏笔）。

```bash
python3 -X utf8 -c "
import sqlite3, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute('''
        SELECT thread_id, title, content, last_touched_chapter,
               (SELECT MAX(chapter) FROM chapters) - last_touched_chapter as silent_chapters
        FROM plot_thread_registry
        WHERE status = 'active'
          AND last_touched_chapter < (SELECT MAX(chapter) FROM chapters) - 30
        ORDER BY silent_chapters DESC LIMIT 5
    ''').fetchall()
    conn.close()
    if rows:
        print('⚠️ 遗忘伏笔提醒（沉默30+章）：')
        for tid, title, content, last_ch, silent in rows:
            print(f'  CANARY_FORGOTTEN: [{tid}] {title}: 最后触及ch{last_ch}, 已沉默{silent}章')
    else:
        print('✅ 无遗忘伏笔')
except Exception as e:
    print(f'⚠️ canary_skipped: 遗忘伏笔检查跳过: {e}')
"
```

**处理规则**：
- 非阻断，输出结果在 Step 1 注入到执行包的伏笔推进建议板块。
- 注入文本格式：`"伏笔 [{thread_id}] {title} 已沉默 {N} 章，本章建议推进或提及"`

#### Step 0.7 输出汇总

金丝雀扫描完成后，必须输出汇总：

```
=== 金丝雀健康扫描结果 ===
主角状态同步: pass / fixed / fail
角色停滞: {N}个角色停滞
冲突模式重复: {N}个模式重复
消歧积压: {N}条
时间线问题: {N}个
遗忘伏笔: {N}条
阻断: 是/否
注入约束数: {N}条
```

**保留金丝雀结果供 Step 1 消费**：将所有 WARNING 级结果的注入文本收集为 `canary_injections` 列表，在 Step 1 追加到创作执行包中。

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

### Step 前置验证协议（每个 Step 启动前强制执行）

> **本协议为铁律，不可跳过、不可裁剪、不可合并到其他 Step。**

每个 Step（1/2A/2B/3/4/5/6）启动前，必须执行以下验证：

1. **前置 Step 完成检查**：
   - 调用 `workflow detect` 读取 `.ink/workflow_state.json`
   - 验证 `current_step` 是否为本 Step 的前一步且状态为 `completed`
   - 若前置 Step 未完成 → **阻断**，输出错误：`"❌ 前置 Step {N} 未完成，禁止进入 Step {N+1}"`
   - **唯一例外**：Step 1 的前置检查为 Step 0 完成（环境验证通过）

2. **Step 开始标记**：
   - 调用 `workflow start-step --step {当前Step号}`
   - 写入 `workflow_state.json`：`{"current_step": "Step {N}", "status": "in_progress", "started_at": "{ISO时间}"}`

3. **Step 完成标记**（在每个 Step 末尾执行）：
   - 调用 `workflow complete-step --step {当前Step号}`
   - 写入 `workflow_state.json`：`{"current_step": "Step {N}", "status": "completed", "completed_at": "{ISO时间}"}`

4. **并步检测**：
   - 若 `workflow_state.json` 中存在 `status: "in_progress"` 的 Step 且不是当前 Step → **阻断**
   - 输出错误：`"❌ 检测到 Step {X} 仍在执行中，禁止并行启动 Step {Y}"`

**违规处理**：若 Agent 跳过本协议直接执行 Step 内容，该 Step 的所有产出视为无效，必须回退重做。

### Step 0.8: 设定权限校验（防幻觉前置执行）

> 本步骤强制执行，不可跳过，不可兜底。

**执行流程**：

1. **读取 index.db 实体快照**：查询当前章节相关的所有实体状态
   ```bash
   cd "$PROJECT_ROOT" && python -c "
   from scripts.data_modules.index_manager import IndexManager
   im = IndexManager('index.db')
   # 获取主角当前状态
   print(im.get_entity_current_state('protagonist'))
   # 获取所有活跃实体的能力上限
   print(im.list_entities_by_type('能力', limit=50))
   "
   ```

2. **生成权限边界清单**：
   - 主角当前境界/等级及可用技能上限
   - 已解锁的地点列表（不可出现未解锁地点）
   - 已建立的关系网络（不可出现未引入角色的深度互动）
   - 已确立的世界规则（不可违反已设定的物理/魔法法则）

3. **输出"写作权限卡"**：
   ```
   === 第 N 章写作权限卡 ===
   【可用能力】: [从 index.db 读取]
   【禁止能力】: [高于当前境界的所有技能]
   【可达地点】: [已解锁地点列表]
   【禁止地点】: [未解锁地点]
   【活跃角色】: [最近 5 章出场 + 本章大纲提及的角色]
   【世界规则红线】: [不可违反的已确立设定]
   ```

4. **Step 2A Writer 必须在写作权限卡范围内创作**。任何超出权限卡的内容，在 Step 3 审查中将被判定为 `critical`。

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
- 单一”创作执行包”（任务书 + Context Contract + 直写提示词），供 Step 2A 直接消费，不再拆分独立 Step 1.5。

**金丝雀写作约束注入**（Step 0.7 产出非空时必须执行）：

若 Step 0.7 的金丝雀扫描产出了 WARNING 级结果（`canary_injections` 非空），**必须**将金丝雀注入文本追加到创作执行包末尾，作为独立板块”金丝雀写作约束”。此板块中的每条约束具有与”不可变事实清单”**同等优先级**——Step 2A Writer 必须遵守，Step 3 Checker 会验证。

注入板块格式（追加到执行包末尾）：

```markdown
## 金丝雀写作约束（自动注入，优先级等同不可变事实）

### 角色发展要求（来自 A.2）
- 角色 “{name}”（{tier}）已 {N} 章无演变，本章若出场**必须**展现变化（行为/态度/能力/关系至少一项）

### 禁用冲突模式（来自 A.3）
- 本章**禁止**使用 “{conflict_type}+{resolution_mechanism}” 冲突模式（最近30章已用{count}次）

### 伏笔推进建议（来自 A.6）
- 伏笔 [{thread_id}] “{title}” 已沉默 {N} 章，本章**建议**推进或提及

### 时间线约束（来自 A.5）
- {时间线警告内容}
```

注入规则：
- 若 Step 0.7 某项检查返回空结果，对应子板块不生成（不输出空板块）。
- 若所有检查均为空，则不追加”金丝雀写作约束”板块（执行包保持原样）。
- 注入完成后，执行包的最终版本即为 Step 2A 消费的输入。

### Step 2A：正文起草

执行前必须加载：
```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"
cat "${SKILL_ROOT}/references/anti-detection-writing.md"
```

硬要求：
- 只输出纯正文到章节正文文件；若详细大纲已有章节名，优先使用 `正文/第{chapter_padded}章-{title_safe}.md`，否则回退为 `正文/第{chapter_padded}章.md`。
- **章节标题约束**：`title_safe` 必须至少包含 2 个汉字。若大纲中的章节标题为空、纯数字、纯标点或少于 2 个汉字，必须根据本章核心事件自行生成一个 2-8 个汉字的标题，禁止使用单字标题或无意义标题。
- **章节标题唯一性**：整本书禁止出现相同的章节标题。生成标题前，必须检查 `正文/` 目录下已有章节的文件名，若新标题与任一已有标题重复，必须修改新标题直到唯一。检查命令：`ls "${PROJECT_ROOT}/正文/" | grep -o '章-.*\.md' | sed 's/章-//;s/\.md//'`
- 默认按 2200-3000 字执行（硬下限 2200，任何情况不得低于此值）；若大纲为关键战斗章/高潮章/卷末章或用户明确指定更高字数，则按大纲/用户优先。
- 禁止占位符正文（如 `[TODO]`、`[待补充]`）。
- 保留承接关系：若上章有明确钩子，本章必须回应（可部分兑现）。

中文思维写作约束（硬规则）：
- **禁止"先英后中"**：不得先用英文工程化骨架（如 ABCDE 分段、Summary/Conclusion 框架）组织内容，再翻译成中文。
- **中文叙事单元优先**：以"动作、反应、代价、情绪、场景、关系位移"为基本叙事单元，不使用英文结构标签驱动正文生成。
- **禁止英文结论话术**：正文、审查说明、润色说明、变更摘要、最终报告中不得出现 Overall / PASS / FAIL / Summary / Conclusion 等英文结论标题。
- **英文仅限机器标识**：CLI flag（`--batch`）、checker id（`consistency-checker`）、DB 字段名（`anti_ai_force_check`）、JSON 键名等不可改的接口名保持英文，其余一律使用简体中文。

防检测自检（交出草稿前必须完成）：
- 检查是否存在连续 4+ 句长度在 15-25 字的"平坦区"，若有则插入碎句或长流句打破。
- 检查是否有连续 500 字全部在推进情节，若有则插入无功能感官细节。
- 检查对话是否所有角色风格和长度趋同，若有则差异化处理。
- 检查单句段占比是否 ≥ 25%，不足则拆分或增加碎片段。
- 以上自检发现问题时直接修复，不另起步骤。

输出：
- 章节草稿（可进入 Step 2A.5 字数校验）。

### Step 2A.5：字数校验（必做，不可跳过）

> 正文写入章节文件后，立即执行字数校验，确保章节字数在可控范围内。

**字数检测**：
```bash
WORD_COUNT=$(wc -m < "${PROJECT_ROOT}/正文/第${chapter_padded}章${title_suffix}.md" 2>/dev/null || echo 0)
echo "当前章节字数: ${WORD_COUNT}"
```

**判定规则**：

| 字数范围 | 判定 | 处理方式 |
|---------|------|---------|
| < 2200 字 | **不合格** | **必须补写**：回到 Step 2A 在现有正文基础上扩写至 ≥ 2200 字。补写时只允许：展开已有场景细节、补充角色互动/反应、增加感官描写、插入无功能感官句。禁止新增大纲之外的剧情事件。**无豁免条件，任何情况不得放行低于 2200 字的章节。** |
| 2200-3500 字 | 合格 | 直接进入下一步 |
| 3501-4500 字 | 偏长 | **建议精简**：输出提示"当前 {WORD_COUNT} 字，建议压缩至 3500 字以内"。若大纲标注为关键战斗章/高潮章/卷末章，可放行 |
| > 4500 字 | 严重超标 | **必须精简**：回到 Step 2A 对现有正文做减法，压缩至 ≤ 4000 字。精简时只允许：删除冗余描写、合并重复信息、压缩过渡段落。禁止删除大纲要求的关键剧情点 |

**豁免条件**（仅适用于偏长/超标，不适用于不合格）：
- 大纲或用户明确指定了更高字数目标（如"本章 5000 字"）
- 大纲标注为特殊章型（关键战斗章/高潮章/卷末章允许上浮 50%）
- **2200 字硬下限无豁免，过渡章也不例外**

**补写/精简后必须再次检测字数**，确认进入合格范围后才可继续。最多执行 2 轮补写，避免无限循环；2 轮后仍不足 2200 字则阻断并报告。

输出：
- 字数合格的章节草稿（可进入 Step 2B 或 Step 3）。

### Step 2A / 2B / 4 职责边界（铁律，三步不可互相越权）

> 三个步骤各有严格的职责范围，任何步骤不得侵入其他步骤的领域。

| 维度 | Step 2A（内容层） | Step 2B（表达层） | Step 4（质量层） |
|------|-----------------|-----------------|----------------|
| **核心职责** | 生成符合大纲的剧情内容 | 将粗稿转为网文风格 | 修复审查问题 + Anti-AI |
| **可改范围** | 剧情事件、角色行为、因果关系、信息传递 | 句式/词序/修辞/感官细节/对话标签 | 审查报告指出的具体问题段落 |
| **禁止范围** | 风格转换、Anti-AI 改写 | 剧情事实、角色行为结果、因果、数字 | 改动未被审查标记的正常段落 |
| **输入** | 创作执行包（Step 1 产出） | Step 2A 的纯内容正文 | Step 3 审查报告 + Step 2B 正文 |
| **输出** | 内容完整但可能有AI味的草稿 | 风格化正文（内容与2A完全一致） | 问题修复后的终稿 |

**交叉校验规则**：
- Step 2B 完成后，剧情事实必须与 Step 2A 输出完全一致（人名、地名、数字、行为结果、因果、时间线零偏差）
- Step 4 的修改范围必须限定在审查报告 `issues` 列表涉及的段落，加上 Anti-AI 终检标记的段落
- 任何步骤发现前序步骤的输出有大纲/设定违规，必须回报而非自行修复

### Step 2B：风格适配

执行前加载：
```bash
cat “${SKILL_ROOT}/references/style-adapter.md”
```

硬要求：
- 只做表达层转译，不改剧情事实、事件顺序、角色行为结果、设定规则。
- 对”模板腔、说明腔、机械腔”做定向改写，为 Step 4 留出问题修复空间。
- 必须优先读取本地高分 `style_samples`；若 `chapter <= 3`，优先选择更能匹配开头窗口、对白密度、句长节奏的样本。
- 若 Anti-AI 检查未通过，不得把该版正文交给 Step 3。
- **Step 2B 完成后必须自检**：对比 2A 输出与 2B 输出，确认所有人名、地名、数字、行为结果、因果关系零偏差。若发现偏差，恢复对应段落为 2A 版本并仅做表达层调整。

输出：
- 风格化正文（覆盖原章节文件）。

### Step 3：审查（auto 路由，必须由 Task 子代理执行）

执行前加载：
```bash
cat "${SKILL_ROOT}/references/step-3-review-gate.md"
```

调用约束：
- 必须用 `Task` 调用审查 subagent，禁止主流程伪造审查结论。
- Step 3 开始前必须先生成 `review_bundle_file`，所有 checker 统一消费这份审查包。
- 最大并发数为 2；核心 checker 可两两并发，条件 checker 顺序执行，统一汇总 `issues/severity/overall_score`。
- 默认使用 `auto` 路由：根据“本章执行合同 + 正文信号 + 大纲标签”动态选择审查器。

先生成审查包（必做）：
```bash
mkdir -p "${PROJECT_ROOT}/.ink/tmp"
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  extract-context --chapter {chapter_num} --format review-pack-json \
  > "${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}.json"
```

Task 传参硬约束：
- 必须传 `review_bundle_file="${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}.json"`
- 必须传绝对路径 `chapter_file`
- checker 不得自行扫描 `正文/`、`设定集/`、`.ink/` 目录，不得读取 `.db`

核心审查器（始终执行）：
- `consistency-checker`
- `continuity-checker`
- `ooc-checker`
- `anti-detection-checker`

条件审查器（`auto` 命中时执行）：
- `golden-three-checker`
- `reader-pull-checker`
- `high-point-checker`
- `pacing-checker`
- `proofreading-checker`
- `reader-simulator`

审查范围：核心 3 个 + auto 命中的条件审查器（始终全量执行）。

**金丝雀约束传递**（若 Step 0.7 产出了金丝雀写作约束）：

生成 review_bundle 后，若创作执行包中包含"金丝雀写作约束"板块，必须将约束信息传递给对应 checker：

| 金丝雀约束类型 | 传递给 Checker | 检查维度 | 未遵守严重度 |
|--------------|---------------|---------|------------|
| 角色发展要求 | `ooc-checker` | 本章出场的停滞角色是否展现了变化（行为/态度/能力/关系） | `medium` |
| 禁用冲突模式 | `pacing-checker` | 本章冲突模式是否命中禁用列表 | `high` |
| 时间线约束 | `continuity-checker` | 本章时间线是否满足约束（不倒退/不矛盾） | `critical` |
| 伏笔推进建议 | `continuity-checker` | 建议性——不强制检查，但 checker 可在报告中标注是否推进了遗忘伏笔 | — |

传递方式：在 Task 调用每个 checker 时，将金丝雀约束作为额外 prompt 内容传入。格式：
```
[金丝雀约束 - 请额外检查以下项目]
- 角色发展: {约束内容}
- 禁用冲突: {约束内容}
- 时间线: {约束内容}
```

审查汇总时，金丝雀约束违规的 issue 标记来源为 `canary_constraint`，与常规审查 issue 合并计入 `severity_counts`。

推荐调度顺序：
1. `consistency-checker` + `continuity-checker` 并发（最多 2 个）
2. `ooc-checker` + `anti-detection-checker` 并发（最多 2 个）
3. 条件审查器按命中顺序串行：`golden-three-checker` → `reader-pull-checker` → `high-point-checker` → `pacing-checker` → `proofreading-checker` → `reader-simulator`

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
  "dimension_scores": {"爽点密度": 8.5, "设定一致性": 8.0, "节奏控制": 7.8, "人物塑造": 8.2, "连贯性": 9.0, "追读力": 8.7, "AI味检测": 7.2},
  "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
  "critical_issues": ["问题描述"],
  "report_file": "审查报告/第100-100章审查报告.md",
  "notes": "单个字符串；摘要给人读",
  "review_payload_json": {
    "selected_checkers": ["consistency-checker", "continuity-checker"],
    "timeline_gate": "pass",
    "anti_ai_force_check": "pass",
    "anti_detection_score": 72,
    "golden_three_metrics": {}
  }
}
```
- `notes` 在当前执行契约中必须是单个字符串，不得传入对象或数组。
- `review_payload_json` 用于结构化扩展信息；黄金三章指标必须写入 `golden_three_metrics`。

硬要求：
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
4. **AI味定向修复**（根据 `anti-detection-checker` 的 `fix_priority` 列表逐项修复）：
   - 句长平坦区：在指定位置插入碎句（≤8字）或合并为长流句（≥35字）
   - 信息密度无波动：在指定位置插入无功能感官句（环境/声音/温度/气味细节）
   - 因果链过密：删除指定位置的中间因果环节，让读者自行推断
   - 对话同质：按指定角色差异化对话长度和风格（加入省略/打断/反问/语气词）
   - 段落过于工整：拆分指定长段为碎片段，增加单句段
   - 视角泄露：改写为POV角色的有限感知（猜测/推断/不确定）
5. 执行 Anti-AI 与 No-Poison 全文终检（必须输出 `anti_ai_force_check: pass/fail`）

黄金三章定向修复（当 `chapter <= 3` 时必须执行）：
- 前移触发点，禁止把强事件压到开头窗口之后。
- 压缩背景说明、长回忆、空景描写。
- 强化主角差异点与本章可见回报。
- 增强章末动机句，确保读者必须点下一章。

### Step 4.5：改写安全校验（润色后必做，不可跳过）

> 防止润色过程中"修A破B"——修复 Anti-AI 问题时意外引入设定违规、OOC 或大纲偏离。

**执行流程**：

1. **保存润色前快照**（在 Step 4 开始前执行）：
   ```bash
   cp "${PROJECT_ROOT}/正文/第${chapter_padded}章${title_suffix}.md" \
      "${PROJECT_ROOT}/.ink/tmp/pre_polish_ch${chapter_padded}.md"
   ```

2. **润色完成后，执行 diff 校验**：
   - 对比润色前后正文，提取所有变更段落
   - 对每个变更段落执行以下检查：

   | 检查项 | 判定规则 | 违规处理 |
   |--------|---------|---------|
   | 剧情事实变更 | 角色行为结果、因果关系、数字/数量是否改变 | `critical`：必须恢复原文该段 |
   | 设定违规引入 | 变更后出现原文没有的能力/地点/角色名 | `critical`：必须恢复原文该段 |
   | OOC 引入 | 角色语气/决策风格与角色档案明显偏离 | `high`：恢复或重新改写该段 |
   | 大纲偏离 | 变更后偏离大纲要求的事件/结果 | `critical`：必须恢复原文该段 |
   | 过度删减 | 单次润色删除超过原文 20% 内容 | `high`：检查是否误删关键信息 |

3. **违规处理**：
   - 若发现 `critical` 违规：从 `pre_polish` 快照恢复对应段落，仅保留非违规的改写
   - 若发现 `high` 违规但无 `critical`：记录到变更摘要的 deviation 中
   - 最多执行 1 轮修正，避免无限循环

4. **清理快照**（Step 5 开始前）：
   ```bash
   rm -f "${PROJECT_ROOT}/.ink/tmp/pre_polish_ch${chapter_padded}.md"
   ```

输出：
- 安全校验后的润色正文（覆盖章节文件）
- 变更摘要（至少含：修复项、保留项、deviation、`anti_ai_force_check`、diff 校验结果）

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

#### Step 5 数据回写验证（Mini-Audit）

> **设计目的**：在 Step 5 回写完成后立即验证数据一致性，防止回写引入新问题。所有检查为轻量 SQL 查询，零额外子代理。
>
> **执行时机**：Step 5 收尾动作（`workflow complete-step --step-id "Step 5"`）执行**之前**。Mini-Audit 全部通过后才允许 complete-step。

##### C.1 回写后主角状态同步（CRITICAL + 自动重试）

> 复用 Step 0.7 A.1 的比对逻辑，验证 `state process-chapter` 执行后 state.json 与 index.db 的主角状态是否一致。

```bash
python3 -X utf8 -c "
import json, sqlite3, sys
from pathlib import Path
project_root = '${PROJECT_ROOT}'
state = json.loads(Path(f'{project_root}/.ink/state.json').read_text())
protag = state.get('protagonist_state', {})
try:
    conn = sqlite3.connect(f'{project_root}/.ink/index.db')
    row = conn.execute(
        'SELECT canonical_name, current_json FROM entities WHERE is_protagonist = 1 LIMIT 1'
    ).fetchone()
    conn.close()
except Exception as e:
    print(f'⚠️ mini_audit_skipped: {e}')
    sys.exit(0)

if not row:
    print('✅ Mini-Audit C.1 跳过（无主角记录）')
    sys.exit(0)

current = json.loads(row[1] or '{}')
s_realm = protag.get('power', {}).get('realm', '')
d_realm = current.get('realm', '')
s_loc = protag.get('location', {}).get('current', '')
d_loc = current.get('location', '')

issues = []
if s_realm and d_realm and s_realm != d_realm:
    issues.append(f'realm: state.json={s_realm} vs index.db={d_realm}')
if s_loc and d_loc and s_loc != d_loc:
    issues.append(f'location: state.json={s_loc} vs index.db={d_loc}')

if issues:
    print(f'⚠️ Mini-Audit C.1 FAIL: 回写后主角状态不一致: {\"; \".join(issues)}')
    print('MINI_AUDIT_C1=fail')
else:
    print('✅ Mini-Audit C.1 PASS: 回写后主角状态一致')
    print('MINI_AUDIT_C1=pass')
"
```

**处理规则**：
- 若 `MINI_AUDIT_C1=fail`：
  1. 重跑一次 `state process-chapter`（使用与 Step 5 相同的 payload）
  2. 重新执行 C.1 检测
  3. 复检通过 → 继续；仍不通过 → 输出 `❌ Step 5 回写后主角状态不一致（重试后仍失败），请手动检查`，**阻断 Step 5 完成**（不影响已保存的正文文件）
- 最多重试 **1 次**，不无限循环

##### C.2 实体提取数量验证（WARNING）

```bash
python3 -X utf8 -c "
import sqlite3, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
chapter = ${chapter_num}
try:
    conn = sqlite3.connect(db_path)
    count = conn.execute('SELECT COUNT(*) FROM appearances WHERE chapter = ?', (chapter,)).fetchone()[0]
    conn.close()
    if count == 0:
        print(f'⚠️ Mini-Audit C.2 WARNING: 第{chapter}章 appearances 表记录为0，可能实体提取失败')
    else:
        print(f'✅ Mini-Audit C.2 PASS: 第{chapter}章 appearances 记录 {count} 条')
except Exception as e:
    print(f'⚠️ mini_audit_skipped: {e}')
"
```

**处理规则**：WARNING 级，记录但不阻断。0 条记录在有角色互动的章节中为异常，建议检查 Data Agent 提取日志。

##### C.3 时间线锚点验证（WARNING）

```bash
python3 -X utf8 -c "
import sqlite3, json, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
chapter = ${chapter_num}
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        'SELECT chapter, anchor_time, countdown FROM timeline_anchors WHERE chapter IN (?, ?) ORDER BY chapter',
        (chapter - 1, chapter)
    ).fetchall()
    conn.close()
    if len(rows) < 2:
        print('✅ Mini-Audit C.3 跳过（锚点数据不足）')
        sys.exit(0)
    prev_time = rows[0][1]
    curr_time = rows[1][1]
    if prev_time and curr_time and prev_time > curr_time:
        print(f'⚠️ Mini-Audit C.3 WARNING: 时间可能倒退 ch{chapter-1}={prev_time} → ch{chapter}={curr_time}')
    else:
        print(f'✅ Mini-Audit C.3 PASS: 时间锚点一致')
except Exception as e:
    print(f'⚠️ mini_audit_skipped: {e}')
"
```

**处理规则**：WARNING 级，记录但不阻断。时间倒退可能是闪回章节的正常行为。

##### Mini-Audit 汇总

```
=== Step 5 Mini-Audit 结果 ===
C.1 主角状态同步: PASS / FAIL / SKIPPED
C.2 实体提取数量: PASS / WARNING / SKIPPED
C.3 时间线锚点: PASS / WARNING / SKIPPED
阻断: 是/否
```

仅当 C.1 为 FAIL（重试后仍失败）时阻断 Step 5 完成。其余 WARNING 记录到审查报告但不阻断。

### Step 6：Git 备份（可失败但需说明）

```bash
git add \
  "${PROJECT_ROOT}/正文/第${chapter_padded}章"*.md \
  "${PROJECT_ROOT}/.ink/state.json" \
  "${PROJECT_ROOT}/.ink/index.db" \
  "${PROJECT_ROOT}/.ink/summaries/ch${chapter_padded}.md" \
  "${PROJECT_ROOT}/.ink/observability/" \
  "${PROJECT_ROOT}/审查报告/" 2>/dev/null
git -c i18n.commitEncoding=UTF-8 commit -m "第${chapter_num}章: ${title}"
```

规则：
- **精确指定文件**：只添加章节正文、state.json、index.db、摘要、观测日志、审查报告。禁止使用 `git add .` 或 `git add -A`，避免将 `.ink/tmp/` 下的临时文件（review_bundle、payload、pre_polish 快照等）加入版本库。
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
4b. Step 4 已处理 `anti-detection-checker` 的全部 `high` 问题（AI味评分 ≥ 60 后方可放行）
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
3. 重新执行”验证与交付”全部检查，通过后结束。

---

> ⛔ **以下区域仅在 `--batch N` 模式下生效。单章模式（无 `--batch` 参数）执行到上方”失败处理”即结束，必须完全忽略以下全部内容。**

## 批量模式编排（仅 `--batch N` 时生效）

当用户指定 `--batch N` 时，进入批量编排模式。核心原则：**每章完整走一遍 Step 0 到 Step 6，与手动执行 `/ink-write` 完全一致，没有任何区别**。

### 批量预检（在第一章 Step 0 之前执行）

1. 完成环境设置（与 Step 0 相同的 env setup 块），解析 `PROJECT_ROOT`、`SCRIPTS_DIR`、`SKILL_ROOT`。
2. 读取 `state.json` 获取 `progress.current_chapter`，计算：
   - `batch_start = current_chapter + 1`
   - `batch_end = batch_start + N - 1`
3. **大纲覆盖批量验证**（必做）：对范围内每一章执行大纲覆盖检查：
   ```bash
   for ch in $(seq {batch_start} {batch_end}); do
     python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" extract-context --chapter $ch --format pack 2>&1 | head -3
   done
   ```
   若任一章输出包含 `⚠️` 或 `未找到` 或 `不存在`，立即阻断并输出：
   ```
   ❌ 第{ch}章没有详细大纲，批量写作中止。
   当前大纲覆盖范围不足以支持第{batch_start}-{batch_end}章。
   请先执行 /ink-plan 生成缺失卷的详细大纲。
   ```
4. 向用户输出批次计划：
   ```
   📋 批量写作计划：第{batch_start}章 → 第{batch_end}章（共{N}章）
   ✅ 大纲覆盖验证通过
   ```

### 章节循环

```
FOR i = 1 TO N:

    ─── 批量进度 [{i}/{N}] 开始第{chapter_num}章 ───

    # ⚠️ 批量模式关键规则重申（每章开头强制输出，防止上下文压缩后遗忘）
    # ═══════════════════════════════════════════════════════════
    # 1. 本次为 --batch {N}，用户已授权连续写 {N} 章，写完立即继续，禁止询问
    # 2. 每章正文必须 ≥ 2200 字（硬下限，无豁免，不足必须补写）
    # 3. 每章必须完整执行 Step 0→1→2A→2A.5→2B→3→4→4.5→5→6，禁止跳步
    # 4. Step 2A 必须加载 core-constraints.md 和 anti-detection-writing.md
    # 5. Step 3 审查必须由 Task 子代理执行，禁止伪造审查结论
    # 6. Step 2A.5 字数校验：< 2200 字必须补写，最多 2 轮，仍不足则阻断
    # 7. 章节标题 ≥ 2 个汉字且全书唯一
    # ═══════════════════════════════════════════════════════════

    # 章号确定（每次循环必做）
    从 state.json 重新读取 progress.current_chapter
    chapter_num = current_chapter + 1
    chapter_padded = 四位补零(chapter_num)
    若 chapter_num 与预期值(batch_start + i - 1)不一致 → 暂停并报告差异，等待用户指示

    # 清理上一章残留 workflow 状态（第一章跳过此步）
    若 i > 1:
        执行 workflow detect
        执行 workflow fail-task --reason “batch_inter_chapter_cleanup” || true

    # ====== 以下为标准单章流程，与手动 /ink-write 完全一致 ======
    执行 Step 0（预检与上下文最小加载）
    执行 Step 0.5（工作流断点记录）
    执行 Step 0.6（重入续跑规则 — 若无残留任务则自动跳过）
    执行 Step 1（脚本执行包构建）
    执行 Step 2A（正文起草 — 目标 2200-3000 字）
    执行 Step 2A.5（字数校验 — 用 bash wc -m 命令验证 ≥ 2200，不足则补写）
    执行 Step 2B（风格适配）
    执行 Step 3（审查 — 必须由 Task 子代理执行）
    执行 Step 4（润色）
    执行 Step 4.5（改写安全校验）
    执行 Step 5（Data Agent）
    执行 Step 6（Git 备份）
    通过 充分性闸门（上方”充分性闸门”章节的全部条件）
    通过 验证与交付（上方”验证与交付”章节的全部检查命令）
    # ====== 标准单章流程结束 ======

    # ⚠️ 批量字数强制验证（bash 命令，非 AI 自评）
    # 此检查在充分性闸门之后、进度输出之前执行，作为最终防线
    FINAL_WC=$(wc -m < “${PROJECT_ROOT}/正文/第${chapter_padded}章”*.md 2>/dev/null | tail -1)
    若 FINAL_WC < 2200 → 输出”❌ 第{chapter_num}章仅{FINAL_WC}字，未达2200字硬下限”
                          → 回到 Step 2A 补写，不得跳过

    # 章节完成确认（仅输出一行进度，然后立即继续）
    输出：✅ [{i}/{N}] 第{chapter_num}章完成 · {字数}字 · 评分{overall_score}

    # 若验证失败：按上方”失败处理”做最小回滚和重跑
    # 重跑后仍失败：输出 ❌ 第{chapter_num}章失败，暂停批量并询问用户是否跳过继续
    # （这是唯一允许暂停的情况）

    # ⚠️ 强制继续指令：输出上方进度行后，不等待用户回复，不询问任何问题，
    # 立即回到 FOR 循环顶部执行下一章的”章号确定”步骤。
    # 用户已通过 --batch {N} 授权全部 {N} 章的连续写作，无需二次确认。

END FOR
```

### 章间衔接（每章 Step 6 完成后、下一章 Step 0 开始前）

在进入下一章之前，必须逐项确认：

1. `workflow_state.json` 中当前任务状态为 `completed`（非 `running`/`failed`）
   - 若为 `running`/`failed`：执行 `workflow fail-task --reason “batch_inter_chapter_cleanup”` 清理
2. `state.json` 的 `progress.current_chapter` 已更新为刚完成的章号
   - 若未更新：说明 Step 5 未正确执行，尝试重跑 Step 5
3. 上一章的充分性闸门全部通过

任一项修复后仍不满足 → 暂停批量并询问用户。

### 批量完成报告

全部章节完成后（或因失败中止后），输出汇总：

```
═══════════════════════════════════════
批量写作完成报告
═══════════════════════════════════════
范围：第{batch_start}章 → 第{实际最后完成章}章
完成：{done}/{N}章
总字数：约{total_words}字
平均评分：{avg_score}
───────────────────────────────────────
各章概览：
  ✅ 第X章 · {标题} — {字数}字 · 评分{score}
  ...
═══════════════════════════════════════
```
