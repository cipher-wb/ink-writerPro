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

- `/ink-write`：Step 1 → 2A → 2A.1 → 2A.5 → 2B → 2C → 3 → 4 → 4.5 → 5 → 5.5 → 6

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

## 进度输出规范

本章节定义 ink-write 工作流的 [INK-PROGRESS] 事件输出规则，用于终端进度条渲染。

### 13 步 step_id 与名称映射表

| 序号 | step_id    | 名称                | 说明                              |
|------|------------|---------------------|-----------------------------------|
| 1    | Step 0     | 预检                | 预检 + 上下文加载 + 断点记录       |
| 2    | Step 0.7   | 金丝雀扫描          | 金丝雀健康扫描                     |
| 3    | Step 0.8   | 设定校验            | 设定权限校验（防幻觉）             |
| 4    | Step 1     | 上下文构建          | 脚本执行包构建 / Context Agent     |
| 5    | Step 2A    | 正文起草            | 正文起草（2200-3000 字）           |
| 6    | Step 2A.1  | 自洽回扫            | 章内自洽回扫（4 项语义检查）       |
| 7    | Step 2A.5  | 字数校验            | 编码校验 + 字数校验                |
| 8    | Step 2B    | 风格适配            | 风格适配                           |
| 9    | Step 2C    | 计算型闸门          | 计算型闸门校验                     |
| 10   | Step 3     | 审查                | 审查（Task 子代理执行）            |
| 11   | Step 4     | 润色                | 润色 + 改写安全校验（含 Step 4.5） |
| 12   | Step 5     | 数据回写            | Data Agent + 前序章修复（含 Step 5.5） |
| 13   | Step 6     | Git 备份            | Git 备份                           |

### 事件输出规则

1. **Step 开始**：每个 Step 启动前必须调用 `workflow start-step --step-id {step_id}`，自动输出：
   ```
   [INK-PROGRESS] step_started {step_id}
   ```

2. **Step 完成**：每个 Step 完成后调用 `workflow complete-step --step {step_id}`，自动输出：
   ```
   [INK-PROGRESS] step_completed {step_id} {elapsed_seconds}
   ```

3. **跳过的步骤**：被跳过的步骤（如 Step 5.5 无需修复、Step 2C 无需校验）也必须调用 `workflow complete-step --step {step_id}` 并在前一行输出：
   ```
   [INK-PROGRESS] step_skipped {step_id}
   ```

4. **回退重写**：审查不通过触发回退时，输出：
   ```
   [INK-PROGRESS] step_retry {from_step} {to_step}
   ```
   例如：`[INK-PROGRESS] step_retry Step 3 Step 2A` 表示审查不通过，回退到正文起草。

5. **章节完成**：`workflow complete-task` 自动输出（US-003 已实现）：
   ```
   [INK-PROGRESS] chapter_completed {chapter_num} {word_count} {overall_score} {total_seconds}
   ```

### 终端进度条渲染格式

外层工具（ink-auto.sh）解析 [INK-PROGRESS] 事件后，按以下格式渲染终端进度条：

**内层步骤进度条**（单章内 13 步）：

```
📝 第{N}章 [{█████████░░░░}] 9/13 步 (69%) — ⏳ Step 3 审查
```

- 使用 Unicode 块字符 `█`（已完成）和 `░`（未完成），宽度 13 字符（对应 13 步）
- 百分比 = 已完成步骤数 / 13 × 100%
- 右侧显示当前执行中的步骤名称

**步骤状态列表**（详细模式）：

```
  ✅ Step 0 预检  ✅ Step 0.7 金丝雀扫描  ✅ Step 0.8 设定校验
  ✅ Step 1 上下文构建  ✅ Step 2A 正文起草  ✅ Step 2A.1 自洽回扫
  ✅ Step 2A.5 字数校验  ✅ Step 2B 风格适配  ⏳ Step 2C 计算型闸门
  ☐ Step 3 审查  ☐ Step 4 润色  ☐ Step 5 数据回写  ☐ Step 6 Git 备份
```

状态图标：`✅` 已完成 / `⏳` 执行中 / `☐` 待执行 / `⏭` 已跳过 / `🔄` 重试中

### 完成汇总行格式

章节完成后输出单行汇总：

```
✅ 第{N}章完成 | {字数}字 | 总耗时 {time} | 审查分 {score}
```

- `{time}` 格式：`{分}m{秒}s`（如 `12m34s`），不足 1 分钟则显示 `{秒}s`
- `{score}` 为审查综合评分（来自 chapter_completed 事件的 overall_score）

## 引用加载等级（strict, lazy）

- L0：未进入对应步骤前，不加载任何参考文件。
- L1：每步仅加载该步“必读”文件。
- L2：仅在触发条件满足时加载“条件必读/可选”文件。

路径约定：
- `references/...` 相对当前 skill 目录。
- `../../references/...` 指向全局共享参考。

## References（逐文件引用清单）

> **加载顺序设计**：按 cache 亲和度分三批排列——静态文件（跨章不变）前置、半静态文件（跨卷不变）居中、动态文件（每章变化）后置。Claude Code CLI 内置 prompt cache（5 分钟 TTL），同一会话内多 Step 共享的静态内容放在前面可最大化 cache 命中率。各 Step 加载参考文件时，应按此顺序读取。

### 第一批：静态（跨章不变，cache 命中率最高）

- `../../references/shared/core-constraints.md`
  - 用途：Step 2A 写作硬约束（大纲即法律 / 设定即物理 / 发明需识别）。
  - 触发：Step 2A 必读。
- `references/step-3-review-gate.md`
  - 用途：Step 3 审查调用模板、汇总格式、落库 JSON 规范。
  - 触发：Step 3 必读。
- `references/polish-guide.md`
  - 用途：Step 4 问题修复、Anti-AI 与 No-Poison 规则。
  - 触发：Step 4 必读。
- `references/writing/typesetting.md`
  - 用途：Step 4 移动端阅读排版与发布前速查。
  - 触发：Step 4 必读。
- `references/step-5-debt-switch.md`
  - 用途：Step 5 债务利息开关规则（默认关闭）。
  - 触发：Step 5 必读。

### 第二批：半静态（跨卷不变，同卷内 cache 可复用）

- `references/style-adapter.md`
  - 用途：Step 2B 风格转译规则，不改剧情事实。
  - 触发：Step 2B 执行时必读。
- `references/anti-detection-writing.md`
  - 用途：Step 2A 防AI检测源头写作指南（句长突发度/信息密度波动/逻辑跳跃/对话人类化/词汇意外性/段落碎片化/视角限制）。
  - 触发：Step 2A 必读。
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

### 第三批：动态（每章变化，cache 无法复用）

> 以下内容在运行时按需加载，不列入静态引用清单：执行包（Step 1 产出）、审查包（Step 3 输入）、章节正文、前序摘要。

### writing（问题定向加读，半静态）

- `references/writing/combat-scenes.md`
  - 触发：战斗章或审查命中”战斗可读性/镜头混乱”。
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
export INK_SKILL_NAME="ink-write"
export INK_PREFLIGHT=1
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```

**硬门槛**：`preflight` 必须成功。它统一校验 `CLAUDE_PLUGIN_ROOT` 派生出的 `SKILL_ROOT` / `SCRIPTS_DIR`、`ink.py`、`extract_chapter_context.py`、解析出的 `PROJECT_ROOT`、以及 **RAG Embedding API 连通性**（v10.6.1 新增，必填项）。任一失败都立即阻断。

**RAG 硬门控**（v10.6.1）：`preflight` 会实际调用 Embedding API 发送测试文本。若 `EMBED_API_KEY` 未配置或 API 不可达，`preflight` 直接失败，**阻断写作流程**。配置方法参见 `references/shared/rag-guide.md`。

**大纲覆盖硬检查**（preflight 通过后、进入 Step 0.5 之前必须执行）：

```bash
python3 -X utf8 “${SCRIPTS_DIR}/ink.py” --project-root “${PROJECT_ROOT}” check-outline --chapter {chapter_num}
```

> **⚠️ 关键**：必须使用 `check-outline` 子命令，**禁止使用 `extract-context --format pack`** 检查大纲（pack 格式会吞掉 ⚠️ 标记，导致漏检）。

若 `check-outline` 退出码非零，说明第 `{chapter_num}` 章没有详细大纲覆盖。

**处理规则**：
- 若检查失败 → **立即阻断**，输出：
  ```
  ❌ 第{chapter_num}章没有详细大纲，禁止写作。
  请先执行 /ink-plan 生成对应卷的详细大纲，再重新执行 /ink-write。
  ```
- 禁止在无大纲时自行编造章节内容，禁止用总纲替代详细大纲。
- 此检查不可跳过、不可兜底、不可降级。

输出：
- “已就绪输入”与”缺失输入”清单；缺失则阻断并提示先补齐。

#### Step 0.2: 黄金三章契约检查（ch <= 3 时）

当 chapter <= 3 时，检查 `$PROJECT_ROOT/.ink/golden_three_plan.json` 是否存在：
- **存在**：加载到执行包中供 golden-three-checker 使用
- **不存在**：输出 WARNING：
  ```
  ⚠️  golden_three_plan.json 不存在。黄金三章审查将使用通用标准而非项目特定契约。
  建议运行 /ink-init 补充黄金三章计划（金手指定义、核心卖点、前三章节拍表）。
  ```
  **不阻断写作**，但在 Step 3 审查时 golden-three-checker 的精度会降低。

#### Step 0.3: 跨卷记忆压缩检查

当 chapter > chapters_per_volume（默认 50，可通过环境变量 INK_CHAPTERS_PER_VOLUME 配置）时自动检查是否需要卷级记忆压缩：

```bash
COMPRESS_RESULT=$(python3 -X utf8 “$SCRIPTS_DIR/ink.py” --project-root “$PROJECT_ROOT” memory auto-compress --chapter {chapter_num} --format json)
```

**若 `needed=true`**：
1. 从 COMPRESS_RESULT 中提取 `prompt` 字段
2. 调用 LLM 生成 mega-summary（提示词已在 prompt 中，直接发送即可）
3. 将 LLM 生成的摘要保存：
   ```bash
   python3 -X utf8 “$SCRIPTS_DIR/ink.py” --project-root “$PROJECT_ROOT” memory save-mega --volume {volume} --content “{mega_summary_text}”
   ```
   若 `save-mega` 子命令不存在，直接写文件：
   ```bash
   echo “{mega_summary_text}” > “$PROJECT_ROOT/.ink/summaries/vol{volume}_mega.md”
   ```
4. 记录日志：`📦 已生成第{volume}卷 mega-summary`

**若 `needed=false`**：跳过，无操作。

**重要**：此步骤是自动化的，不需要用户确认。压缩仅在新卷首章触发（如 ch51, ch101 等）。

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
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path('${SCRIPTS_DIR}').resolve().parent.parent))
from ink_writer.foreshadow.tracker import scan_foreshadows, build_plan_injection
from ink_writer.foreshadow.config import load_config
project_root = '${PROJECT_ROOT}'
state = json.loads(Path(f'{project_root}/.ink/state.json').read_text())
current = state.get('progress', {}).get('current_chapter', 0)
db_path = f'{project_root}/.ink/index.db'
try:
    config = load_config()
    scan = scan_foreshadows(db_path, current, config)
    injection = build_plan_injection(scan, config)
    if scan.alerts:
        for alert in scan.alerts:
            print(alert)
        print(f'📊 活跃伏笔: {scan.total_active} | 逾期: {len(scan.overdue)} | 沉默: {len(scan.silent)}')
        if scan.forced_payoffs:
            print(f'🔴 强制兑现: {len(scan.forced_payoffs)}条 — 本章必须处理')
            for fp in scan.forced_payoffs:
                print(f'  → [{fp.record.thread_id}] {fp.record.title} (severity={fp.severity})')
    else:
        print('✅ 无逾期伏笔')
    print(json.dumps(injection, ensure_ascii=False))
except Exception as e:
    print(f'⚠️ 伏笔检查跳过（数据库不可用）: {e}')
“
```

**处理规则**：
- thread-lifecycle-tracker[foreshadow] 按优先级分级检测逾期（P0 宽限5章, P1 宽限10章, P2 宽限20章）和沉默（超30章未推进）
- `forced_payoffs` 非空时：Context Agent Board 7 强制置顶，writer-agent 必须在本章处理
- 此检查为**警告模式**（不强制阻断写作），但 forced_payoffs 中的伏笔会注入到 Context Agent Board 7 中作为本章写作硬约束
- 若存在逾期伏笔，建议在本章解决，或通过 /ink-plan 显式延期目标章节

### Step 0.7：金丝雀健康扫描（Canary Health Scan）

> **设计目的**：将 ink-macro-review 和 ink-audit 的核心检查能力前移到每章写作前执行，做到"写一章就保证一章正确"。所有检查为轻量 SQL 查询 + JSON 比对，零额外子代理开销。
>
> **兼容性保证**：所有查询均包裹 `try...except`，表不存在或数据为空时返回空结果（检查通过）。第 1 章写作时所有表为空，所有检查自动通过。任何金丝雀脚本执行异常只输出 `⚠️ canary_skipped`，不阻断写作。

**执行时机**：逾期伏笔检查通过后、进入 Step 0.5 之前。

**增量模式（可选）**：
- 标志：`--canary-mode incremental`
- 启用时跳过 A.2（角色发展停滞检测）和 A.3（冲突模式重复检测），仅执行 A.1、A.4、A.5、A.6
- **适用场景**：快速批量写作（如 ink-auto）中，连续章之间 A.2/A.3 的30-40章窗口查询结果几乎不变，可安全跳过
- **不跳过 A.1 的原因**：A.1 是唯一带自动修复的检查（主角状态同步），跳过可能导致后续章节在错误状态上继续
- **默认行为**：不传此标志时执行全部 A.1-A.6（行为不变）

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

**ink-fix 约束消费**（v10.3.0 新增）：若 `.ink/pending_constraints.md` 存在且非空，读取全部约束条目，追加到 `canary_injections` 列表中（与金丝雀约束同等优先级）。消费后清空该文件：
```bash
if [[ -s "${PROJECT_ROOT}/.ink/pending_constraints.md" ]]; then
    echo "📋 发现 ink-fix 待消费约束："
    cat "${PROJECT_ROOT}/.ink/pending_constraints.md"
    # 约束内容追加到 canary_injections 列表
    # 消费后清空文件
    : > "${PROJECT_ROOT}/.ink/pending_constraints.md"
fi
```

**保留金丝雀结果供 Step 1 消费**：将所有 WARNING 级结果的注入文本（含 ink-fix 约束）收集为 `canary_injections` 列表，在 Step 1 追加到创作执行包中。

### Step 0.5：工作流断点记录（best-effort，不阻断）

```bash
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-task --command ink-write --chapter {chapter_num} || true
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-step --step-id "Step 1" --step-name "Context Build" || true
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step --step-id "Step 1" --artifacts '{"ok":true}' || true
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-task --artifacts '{"ok":true}' || true
```

要求：
- `--step-id` 仅允许：`Step 1` / `Step 2A` / `Step 2B` / `Step 2C` / `Step 3` / `Step 4` / `Step 5` / `Step 6`。
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
  - **板块 14: 强制合规清单（MCC）**——从大纲自动提取 required_entities、required_foreshadows、required_hook、chapter_goal、required_coolpoint、forbidden_inventions、required_change、required_open_question，供 Step 2A 写作合同和 Step 3 outline-compliance-checker 消费；
  - Context Contract 全字段（目标/阻力/代价/本章变化/未闭合问题/开头类型/情绪节奏/信息密度/过渡章判定/追读力设计）；
  - 若 `chapter <= 3`：额外包含 `golden_three_role / opening_window_chars / reader_promise / must_deliver_this_chapter / end_hook_requirement`；
  - Step 2A 可直接消费的”写作执行包”（章节节拍、不可变事实清单、禁止事项、终检清单）。
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

执行前必须加载（静态优先，最大化 cache 命中）：
```bash
# 第一批：静态（跨章不变）
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"
# 第二批：半静态（跨卷不变）
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

**MCC 写作前确认**（执行包含板块14时必做）：
- 读取板块 14 MCC，内部生成"写作合同"（不输出，仅内部确认）
- 逐项列出 required_entities、required_foreshadows、required_hook、chapter_goal、required_coolpoint、required_change、required_open_question、forbidden_inventions
- MCC 中标记为 `not_specified` 的项跳过

防检测自检（交出草稿前必须完成）：
- 检查是否存在连续 4+ 句长度在 15-25 字的"平坦区"，若有则插入碎句或长流句打破。
- 检查是否有连续 500 字全部在推进情节，若有则插入无功能感官细节。
- 检查对话是否所有角色风格和长度趋同，若有则差异化处理。
- 检查单句段占比是否 ≥ 25%，不足则拆分或增加碎片段。
- 以上自检发现问题时直接修复，不另起步骤。

**MCC 写作后自检**（输出正文之前必做）：
- 逐项验证 6 项：
  1. ✅/❌ 每个 required_entity 是否在正文中出场（至少有名字或明确指代出现）
  2. ✅/❌ 每个 required_foreshadow 是否在正文中有对应段落
  3. ✅/❌ required_hook 是否在章末 300 字内出现
  4. ✅/❌ chapter_goal 核心事件是否存在且未被自创内容喧宾夺主
  5. ✅/❌ 正文中无 MCC 未列出的新命名角色（具名群演除外：出场≤2句且无剧情影响）
  6. ✅/❌ required_change 是否在正文中体现
- 任一项 ❌ → 自行修正后重新输出，最多重试 2 轮
- 自检结果持久化：`.ink/tmp/mcc_selfcheck_ch{NNNN}.json`
- 自检失败超 2 轮 → 标记 `mcc_selfcheck_failed`，Step 3 强制触发 outline-compliance-checker

输出：
- 章节草稿（可进入 Step 2A.1 自洽回扫）。

### Step 2A.1：自洽回扫（Self-Consistency Scan）

> Step 2A 产出正文后、Step 2A.5 字数校验前，writer-agent 对自己的产出做一次结构化自洽回扫，捕获章内前后矛盾。此步骤不阻断流程（即使发现无法修复的问题也继续），但回扫结果会注入 Step 3 审查包，供 checker 重点关注。

输入：
- Step 2A 产出的章节正文（已写入文件）
- 执行包中的板块 15 否定约束清单

执行（writer-agent 自洽回扫，参见 writer-agent.md「自洽回扫」章节）：

4 项检查：
1. **SC-1 观察-统计完整性**：正文中角色做出的每次观察/发现，是否在后续的总结/统计/回忆中都被纳入？
2. **SC-2 信息引用合法性**：正文中角色引用的每个事实/关系/联系方式，在本章正文中或执行包的否定约束之外是否有合法来源？
3. **SC-3 角色存在完整性**：本章开头出场的所有角色，在结尾前是否都有交代？
4. **SC-4 因果链闭合**：正文中的每个行为动机是否有前因，每个开始的动作是否有结果？

修正规则：
- 发现问题时 writer 自行修正（最多 2 轮），修正后重新回扫
- 回扫结果持久化：`.ink/tmp/selfcheck_scan_ch{NNNN}.json`
- 超 2 轮仍有问题 → 标记为 `scan_unresolved`，**不阻断流程**，继续进入 Step 2A.5

Step 3 联动：
- 回扫结果（无论通过或未解决）注入 Step 3 审查包
- `scan_unresolved` 标记的章节，Step 3 审查器会对相关问题区域做重点检查
- 回扫结果文件路径：`.ink/tmp/selfcheck_scan_ch{NNNN}.json`，Step 3 生成审查包时自动包含

输出：
- 修正后的章节正文（或标记 `scan_unresolved` 的原始正文）
- `.ink/tmp/selfcheck_scan_ch{NNNN}.json` 回扫报告

### Step 2A.5：编码校验 + 字数校验（必做，不可跳过）

> 正文写入章节文件后，先执行编码校验（检测 U+FFFD 乱码），再执行字数校验。

#### 2A.5.1 编码校验（乱码检测与自动修复）

LLM 流式输出时，多字节 UTF-8 字符偶尔在 chunk 边界被截断，导致文件中出现 U+FFFD 替换字符（显示为 `���`）。此步骤检测并自动修复。

**检测**：
```bash
cd "${PROJECT_ROOT}" && python "${SCRIPTS_DIR}/encoding_validator.py" \
  --file "${PROJECT_ROOT}/正文/第${chapter_padded}章${title_suffix}.md"
```

**修复流程**（退出码 = 1 时执行）：
1. 读取 JSON 输出中每处乱码的 `context_before`、`context_after` 和 `line` 信息
2. 根据前后文语义推断被损坏的正确字符（通常是 1 个常用中文字符）
3. 使用 Edit 工具将 `U+FFFD` 序列替换为推断出的正确字符
4. 再次运行 `encoding_validator.py` 确认修复成功
5. 最多执行 **2 轮**修复，避免无限循环；2 轮后仍有乱码则阻断并报告

**退出码说明**：`0` = 无乱码，直接进入字数检测；`1` = 有乱码，执行修复流程；`2` = 参数/文件错误，阻断。

#### 2A.5.2 字数检测

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
| 3501-4000 字 | 偏长 | **建议精简**：输出提示"当前 {WORD_COUNT} 字，建议压缩至 3500 字以内"。若大纲标注为关键战斗章/高潮章/卷末章，可放行 |
| > 4000 字 | 严重超标 | **必须精简**：回到 Step 2A 对现有正文做减法，压缩至 ≤ 4000 字。精简时只允许：删除冗余描写、合并重复信息、压缩过渡段落。禁止删除大纲要求的关键剧情点 |

**豁免条件**（仅适用于偏长/超标，不适用于不合格）：
- 大纲或用户明确指定了更高字数目标（如"本章 5000 字"）
- 大纲标注为特殊章型（关键战斗章/高潮章/卷末章允许上浮 33%，不超过 4000）
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

#### Step 2B 前置指标计算（必做，决定执行模式）

```bash
STEP2B_METRICS=$(python3 -X utf8 “${SCRIPTS_DIR}/step2b_metrics.py” \
  --chapter-file “${CHAPTER_FILE}” 2>/dev/null) || true
```

判定逻辑：
- **脚本不存在或执行失败** → 退回全量模式（向后兼容）。
- **`targeted_mode: true`**（句长均值 > 20字 且 对话占比 > 10%）→ 进入**定向检查模式**。
- **`targeted_mode: false`** → 执行原有的**全量风格适配**。

输出 `STEP2B_METRICS` 中的 `mode` 字段到日志，便于追溯。

#### 模式 A：全量风格适配（`mode == “full”`）

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

##### 风格样本 Fallback（新项目前 10 章）

当本地 `style_samples` 表为空或匹配结果不足 2 条时（新项目常见情况）：
1. 从 `scene-craft-index.md` 的对应场景类型范例中提取 2-3 个参考片段
2. 若项目配置了 `genre`，从 benchmark `style_rag.db`（如果存在）按 genre + scene_type 检索 3 个标杆片段
3. 将这些 fallback 样本注入执行包第 11 板块，标记为 `source: “benchmark_fallback”`
4. 从第 11 章起，本地高分章节应已积累足够样本，不再触发 fallback

#### 模式 B：定向检查模式（`mode == “targeted”`）

> 当 writer-agent (Step 2A) 产出已内化风格（句长、对话占比达标），Step 2B 降级为定向红线检查，
> 只处理 3 项残留职责，跳过全文改写。省约 80% Step 2B token。

执行前加载：
```bash
cat “${SKILL_ROOT}/references/style-adapter.md”  # 仅需读取”定向检查模式”章节
```

定向检查仅做 3 件事（参考 `STEP2B_METRICS` 中的检测结果辅助定位）：

1. **拆分超长句**（>55 字的非对话句）
   - `STEP2B_METRICS.long_sentences` 已预标记位置，逐一拆分
   - 35-55 字长句保留不动（正常节奏纵深）
2. **删除总结式旁白**（”由此可见”、”换句话说”、”总而言之”等 AI 痕迹短语）
   - `STEP2B_METRICS.summary_phrases` 已预标记位置和上下文
   - 替换为直接结论动作，不做元叙述
3. **清除模板腔**（检查 `ai-word-blacklist.md` 中的黑名单词）
   - 当单章使用密度超过标杆均值 2 倍时替换

硬约束（与全量模式相同）：
- 不改剧情事实、事件顺序、角色行为结果、设定规则。
- **定向检查完成后必须自检**：确认所有人名、地名、数字、行为结果、因果关系零偏差。

输出：
- 风格化正文（覆盖原章节文件）。

### Step 2C：计算型闸门 (Computational Gate)

> **目的**：在昂贵的 LLM checker (Step 3) 之前，用确定性规则快速拦截明显问题。

执行前加载：
```bash
cat "${SKILL_ROOT}/references/step-2c-comp-gate.md"
```

调用：
```bash
COMP_GATE_RESULT=$(python3 "${SCRIPTS_DIR}/computational_checks.py" \
  --project-root "${PROJECT_ROOT}" \
  --chapter ${CHAPTER_NUM} \
  --chapter-file "${CHAPTER_FILE}" \
  --format json 2>/dev/null) || true
```

判定逻辑：
- **脚本不存在** → 跳过，直接进入 Step 3。
- **exit 2**（内部错误）→ 输出 WARNING 日志，在 review_bundle 中附加 `comp_gate_skipped: true`，进入 Step 3（详见 `step-2c-comp-gate.md`）。
- **exit 1**（硬失败）→ 读取 `hard_failures` 列表，退回 Step 2A 重写。不进入 Step 3。
- **exit 0 + 有 soft_warnings** → 将 `soft_warnings` 记录到日志，附加到 review_bundle 的 `computational_warnings` 字段，进入 Step 3。
- **exit 0 + 全部通过** → 正常进入 Step 3。

检查项（6 项确定性检查）：
- 章节字数区间 [2200, 5000]
- 章节文件命名规范
- 角色名基础冲突
- 伏笔生命周期一致性
- 主角能力等级基础检查
- 前章契约字段完整性

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

生成按 checker 瘦身包（必做，紧随完整包之后）：
```bash
# selected_checkers 为本次选中的 checker 列表（逗号分隔）
# --precheck: 自动运行 logic_precheck.py 并将结果注入 logic-checker 的瘦身包
python3 -X utf8 "${SCRIPTS_DIR}/slim_review_bundle.py" \
  --bundle "${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}.json" \
  --checkers "${selected_checkers}" \
  --outdir "${PROJECT_ROOT}/.ink/tmp" \
  --precheck \
  > "${PROJECT_ROOT}/.ink/tmp/slim_bundle_map.json"
# 输出 JSON 映射：checker_name → 瘦身包路径
# 若某 checker 瘦身失败，自动退回完整包路径（向后兼容）
# --precheck 运行 L1/L3 计算型预检，结果注入 logic-checker 包的 precheck_results 字段
# 若预检失败，静默跳过（不阻断流程）
```

Task 传参硬约束：
- 必须传 `review_bundle_file`：优先使用瘦身包路径（从 `slim_bundle_map.json` 读取），若瘦身包不存在则退回完整包 `"${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}.json"`
- 必须传绝对路径 `chapter_file`
- checker 不得自行扫描 `正文/`、`设定集/`、`.ink/` 目录，不得读取 `.db`

核心审查器（始终执行）：
- `consistency-checker`（权重 25%）
- `continuity-checker`（权重 15%）
- `ooc-checker`（权重 20%）
- `logic-checker`（权重 15%）——章内微观逻辑验证（L1-L9：数字算术/动作序列/属性一致/空间连续/物品连续/感官一致/对话归属/因果逻辑/枚举完整性）
- `outline-compliance-checker`（权重 15%）——大纲合规验证（O1-O7：实体出场/禁止发明/目标充分性/伏笔埋设/钩子合规/黄金三章附加/否定约束合规），消费 MCC（板块14）+ 否定约束（板块15）
- `anti-detection-checker`（权重 10%）
- `reader-simulator`（**快速模式**，v9.0 升格为核心裁判。输出 `reader_verdict` 7 维评分，驱动 Step 4 自动返修）

条件审查器（`auto` 命中时执行）：
- `golden-three-checker`
- `reader-pull-checker`
- `high-point-checker`
- `pacing-checker`
- `proofreading-checker`

审查范围：核心 7 个 + auto 命中的条件审查器（始终全量执行）。

**reader_verdict 联动逻辑**（Step 3 完成后判定）：
- `reader_verdict.verdict == "pass"` → 正常进入 Step 4
- `reader_verdict.verdict == "enhance"` → 进入 Step 4，但追加"追读力增强"修复指令
- `reader_verdict.verdict == "rewrite"` → **退回 Step 2A 重写**（附带 reader-simulator 的 issues 列表作为修改指引，最多重写 1 次）

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
2. `ooc-checker` + `logic-checker` 并发（最多 2 个）
3. `outline-compliance-checker` + `anti-detection-checker` 并发（最多 2 个）
4. `reader-simulator`（快速模式，核心裁判）
5. 条件审查器按命中顺序串行：`golden-three-checker` → `reader-pull-checker` → `high-point-checker` → `pacing-checker` → `proofreading-checker`

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
  "dimension_scores": {"爽点密度": 8.5, "设定一致性": 8.0, "节奏控制": 7.8, "人物塑造": 8.2, "连贯性": 9.0, "章内逻辑": 8.8, "大纲合规": 9.0, "追读力": 8.7, "AI味检测": 7.2},
  "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
  "critical_issues": ["问题描述"],
  "report_file": "审查报告/第100-100章审查报告.md",
  "notes": "单个字符串；摘要给人读",
  "review_payload_json": {
    "selected_checkers": ["consistency-checker", "continuity-checker", "reader-simulator"],
    "timeline_gate": "pass",
    "anti_ai_force_check": "pass",
    "anti_detection_score": 72,
    "golden_three_metrics": {},
    "reader_verdict": {"hook_strength": 8, "curiosity_continuation": 7, "emotional_reward": 9, "protagonist_pull": 8, "cliffhanger_drive": 9, "filler_risk": 2, "repetition_risk": 1, "total": 48, "verdict": "pass"}
  }
}
```
- `notes` 在当前执行契约中必须是单个字符串，不得传入对象或数组。
- `review_payload_json` 用于结构化扩展信息；黄金三章指标必须写入 `golden_three_metrics`。

reader_verdict 落库（必做，紧随 review_metrics 之后）：
```bash
# 将 reader-simulator 的 reader_verdict 写入 harness_evaluations 表（v9.0）
# reader_verdict JSON 从 review_payload_json.reader_verdict 中提取
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  index save-harness-evaluation --data '{"chapter": ${CHAPTER_NUM}, "reader_verdict": ${READER_VERDICT_JSON}, "review_depth": "core"}'
```

硬要求：
- 当 `chapter <= 3` 时，`golden-three-checker` 未通过不得放行。
- 未落库 `review_metrics` 不得进入 Step 5。

#### Step 3.5: Harness 级闸门复检

审查聚合完成后，执行确定性闸门脚本作为最终兜底：

```bash
python3 -X utf8 "$SCRIPTS_DIR/step3_harness_gate.py" \
    --project-root "$PROJECT_ROOT" --chapter {chapter_num} --format json
```

- **exit 0**：通过，继续 Step 4
- **exit 1**：硬拦截。读取 JSON 输出的 `action` 字段：
  - `rewrite_step2a`：回退 Step 2A 重写（黄金三章/读者体验/质量过低）
  - 输出拦截原因供参考
- **exit 2**：脚本异常，输出 WARNING 并继续 Step 4（不阻断）

此步骤是确定性检查，不依赖 LLM 判断。即使 Step 3 的 LLM 审查遗漏了某条闸门规则，此脚本也会兜底拦截。

#### Step 3.51: 逻辑门禁（Logic Gate）

> 基于 logic-checker 结果判定章内微观逻辑是否通过。

**Hard Block 条件**：logic-checker 存在 critical issue 或 ≥2 个 high severity issue。

```text
logic_result = Step 3 中 logic-checker 的输出

if logic_result has critical OR count(high) >= 2:
    生成 repair_context（精简版 issues[]，每条仅含 type/severity/location/suggestion，≤500 tokens）
    退回 Step 2A 重写，注入 repair_context 作为 writer-agent 的修复指引
    逻辑门禁回退计数 += 1
    if 逻辑门禁回退计数 >= 3:
        暂停流程，输出诊断报告请求人工干预
else:
    logic_result 中的 medium/low issues 传递给 Step 4 polish-agent（logic_fix_prompt）
```

**overall_score cap**：logic-checker 存在 critical issue 时，overall_score 上限 cap 到 50。

#### Step 3.52: 大纲合规门禁（Outline Compliance Gate）

> 基于 outline-compliance-checker 结果判定正文是否忠于大纲。

**Hard Block 条件**：outline-compliance-checker 存在 critical issue 或 ≥2 个 high severity issue。

```text
occ_result = Step 3 中 outline-compliance-checker 的输出

if occ_result has critical OR count(high) >= 2:
    生成 repair_context（精简版 issues[]，每条仅含 type/severity/location/suggestion，≤500 tokens）
    退回 Step 2A 重写，注入 repair_context 作为 writer-agent 的修复指引
    大纲合规门禁回退计数 += 1
    if 大纲合规门禁回退计数 >= 3:
        暂停流程，输出诊断报告请求人工干预
else:
    occ_result 中的 medium/low issues 传递给 Step 4 polish-agent（outline_fix_prompt）
```

**overall_score cap**：outline-compliance-checker 存在 critical issue 时，overall_score 上限 cap 到 50。

**Step 3.51/3.52 → Step 2A 回退路径**：
- 回退时 writer-agent 接收 `repair_context`：checker 报告的 issues[] 精简版（type/severity/location/suggestion），不传完整报告
- 每个门禁独立计数回退次数，最多 2 次回退
- 第 3 次失败 → 暂停请求人工干预，不再自动重试

#### Step 3.6: 追读力门禁（hook retry gate）

> v13.0 新增。从 reader-pull-checker 结果中提取 {score, violations, fix_prompt}，得分低于阈值时自动触发 polish-agent 定向修复，最多重试 2 次。

**执行条件**：reader-pull-checker 在 Step 3 中被调度执行（条件审查器命中时）。

**流程**：

```text
reader_pull_result = Step 3 中 reader-pull-checker 的输出
config = config/reader-pull.yaml
threshold = config.score_threshold（章节 ≤ 3 时用 golden_three_threshold）

if reader_pull_result.overall_score < threshold:
    for retry in 1..2:
        调用 polish-agent，传入:
          chapter_file = 当前章节路径
          hook_fix_prompt = reader_pull_result.fix_prompt
          issues = reader_pull_result.hard_violations + soft_suggestions
        重新执行 reader-pull-checker
        if new_score >= threshold: break
    else:
        写入 chapters/{n}/hook_blocked.md（得分、违规列表、fix_prompt）
        章节标记为失败，不进入 Step 4
```

**hook_blocked.md 格式**：包含最终得分、阈值、所有未解决违规及修复提示。

**与 Step 4 的关系**：
- 若追读力门禁通过（含重试后通过），正常进入 Step 4 执行其他修复
- 若门禁阻断，Step 4/5/6 均跳过
- 追读力门禁的 polish 调用独立于 Step 4 的常规润色

**Python 模块**：`ink_writer.reader_pull.hook_retry_gate.run_hook_gate()`

#### Step 3.7: 情绪曲线门禁（emotion curve gate）

> v13.0 新增。从 emotion-curve-checker 结果中提取 {score, violations, fix_prompt}，情绪曲线过平时自动触发 polish-agent 定向修复，最多重试 2 次。

**执行条件**：emotion-curve-checker 在 Step 3 中被调度执行（条件审查器命中时）。

**流程**：

```text
emotion_result = Step 3 中 emotion-curve-checker 的输出
config = config/emotion-curve.yaml
threshold = config.score_threshold

if emotion_result.overall_score < threshold:
    for retry in 1..2:
        调用 polish-agent，传入:
          chapter_file = 当前章节路径
          emotion_fix_prompt = emotion_result.fix_prompt
          issues = emotion_result.hard_violations + soft_suggestions
        重新执行 emotion-curve-checker
        if new_score >= threshold: break
    else:
        写入 chapters/{n}/emotion_blocked.md（得分、违规列表、fix_prompt）
        章节标记为失败，不进入 Step 4
```

**emotion_blocked.md 格式**：包含最终得分、阈值、平淡段位置及修复提示。

**与 Step 3.6 的关系**：
- 追读力门禁（Step 3.6）先执行；若已阻断则跳过情绪门禁
- 情绪门禁通过后正常进入 Step 4
- 情绪门禁的 polish 调用独立于 Step 4 的常规润色

**Python 模块**：`ink_writer.emotion.emotion_gate.run_emotion_gate()`

#### Step 3.8: AI味硬门禁（anti-detection sentence diversity gate）

> v13.0 新增。从 anti-detection-checker 结果中提取统计特征（句长变异系数、短句占比、对话占比、情感标点密度等），不达标时自动触发 polish-agent 定向修复。零容忍项（如时间标记开头）立即阻断，不触发重试。

**执行条件**：anti-detection-checker 在 Step 3 中被调度执行（核心审查器，始终运行）。

**流程**：

```text
# 1. 零容忍检查（在 checker 调用之前）
config = config/anti-detection.yaml
zero_tolerance_hit = check_zero_tolerance(chapter_text, config)
if zero_tolerance_hit:
    写入 chapters/{n}/anti_detection_blocked.md（零容忍阻断）
    章节标记为失败，不进入 Step 4

# 2. 综合评分检查 + 重试
anti_detection_result = Step 3 中 anti-detection-checker 的输出
threshold = config.score_threshold（章节 ≤ 3 时用 golden_three_threshold）

if anti_detection_result.overall_score < threshold:
    for retry in 1..1:
        调用 polish-agent，传入:
          chapter_file = 当前章节路径
          anti_detection_fix_prompt = anti_detection_result.fix_prompt
          issues = anti_detection_result.fix_priority
        重新执行 anti-detection-checker
        if new_score >= threshold: break
    else:
        写入 chapters/{n}/anti_detection_blocked.md（得分、违规列表、fix_prompt）
        章节标记为失败，不进入 Step 4
```

**零容忍清单**（匹配即阻断，不重试）：
- `ZT_TIME_OPENING`：章节以时间标记开头（第xx日/次日/N天后等）
- `ZT_MEANWHILE`：使用"与此同时"全知视角转场

**与 Step 3.6/3.7 的关系**：
- 追读力门禁（Step 3.6）和情绪门禁（Step 3.7）先执行；若已阻断则跳过 AI味门禁
- AI味门禁通过后正常进入 Step 4
- AI味门禁的 polish 调用独立于 Step 4 的常规润色

**Python 模块**：`ink_writer.anti_detection.anti_detection_gate.run_anti_detection_gate()`

#### Step 3.9: 语气指纹门禁（voice fingerprint gate）

**触发条件**：前序门禁（Step 3.6/3.7/3.8）均未阻断。

**流程**：
1. 从 `character_evolution_ledger` 加载出场角色的 `voice_fingerprint_json`
2. 提取章节中各角色对话，逐项校验：
   - 禁忌表达命中 → `critical`（必须修复）
   - 口头禅缺席 ≥ N 章 → `medium`
   - 用词层次偏离 → `medium`
   - 角色间对话辨识度不足 → `medium`
3. 综合评分低于阈值（默认60） → 触发 polish-agent（Step 1.8 voice_fix_prompt）
4. 最多重试2次；仍不通过 → 写 `voice_blocked.md` + 阻断

**与 Step 3.6/3.7/3.8 的关系**：
- 前序门禁先执行；若已阻断则跳过语气指纹门禁
- 语气指纹门禁的 polish 调用独立于 Step 4 的常规润色

**Python 模块**：`ink_writer.voice_fingerprint.ooc_gate.run_voice_gate()`

#### Step 3.10: 明暗线推进门禁（plotline gate）

**触发条件**：前序门禁（Step 3.6/3.7/3.8/3.9）均未阻断。

**流程**：
1. 从 `plot_thread_registry`（`thread_type='plotline'`）加载所有活跃线程
2. 调用 `ink_writer.plotline.tracker.scan_plotlines()` 检测断更线程
3. 检查本章大纲 `明暗线推进` 字段中声明的线程是否在正文中有实际推进：
   - 主线断更 > 3章 → `critical`（必须推进）
   - 支线断更 > 8章 → `high`
   - 暗线断更 > 15章 → `medium`
4. 存在 critical 断更且本章未推进 → 触发 polish-agent（Step 1.9 plotline_fix_prompt）
5. 最多重试2次；仍不通过 → 写 `plotline_blocked.md` + 阻断

**与 Step 3.6-3.9 的关系**：
- 前序门禁先执行；若已阻断则跳过明暗线门禁
- 明暗线门禁的 polish 调用独立于 Step 4 的常规润色

**Python 模块**：`ink_writer.plotline.tracker.scan_plotlines()`

### Step 4：润色（问题修复优先）

执行前必须加载（静态优先，最大化 cache 命中）：
```bash
# 第一批：静态（跨章不变）
cat "${SKILL_ROOT}/references/polish-guide.md"
cat "${SKILL_ROOT}/references/writing/typesetting.md"
```

执行顺序：
1. **P0: 逻辑修复**（logic_fix_prompt，来自 logic-checker 的 medium/low）——数字只改数字、空间只加过渡句、物品加状态描写，最小化改动
2. **P0.5: 大纲合规修复**（outline_fix_prompt，来自 outline-compliance-checker 的 medium/low）——补充展开/强化可识别度/调整位置，不改剧情走向
3. 修复 `critical`（必须）
4. 修复 `high`（不能修复则记录 deviation）
5. 处理 `medium/low`（按收益择优）
6. **Style RAG 人写参考检索**（当 `fix_priority` 非空时）：
   - 调用 `ink_writer.style_rag.build_polish_style_pack(fix_priorities, chapter_text, chapter_no, retriever, genre)` 检索人写标杆片段
   - 将返回的 `PolishStylePack.format_full_prompt()` 注入改写上下文
   - 参考人写片段的句式节奏和表达手法，**不可照搬内容或剧情**
7. **AI味定向修复**（根据 `anti-detection-checker` 的 `fix_priority` 列表，结合人写参考逐项修复）：
   - 句长平坦区：在指定位置插入碎句（≤8字）或合并为长流句（≥35字）
   - 信息密度无波动：在指定位置插入无功能感官句（环境/声音/温度/气味细节）
   - 因果链过密：删除指定位置的中间因果环节，让读者自行推断
   - 对话同质：按指定角色差异化对话长度和风格（加入省略/打断/反问/语气词）
   - 段落过于工整：拆分指定长段为碎片段，增加单句段
   - 视角泄露：改写为POV角色的有限感知（猜测/推断/不确定）
8. 执行 Anti-AI 与 No-Poison 全文终检（必须输出 `anti_ai_force_check: pass/fail`）

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
   | 逻辑修复引入新矛盾 | P0 逻辑修复的 diff 是否引入了新的数字错误、动作矛盾或空间跳跃 | `critical`：恢复原文该段，记录 deviation |
   | 大纲合规修复偏离剧情 | P0.5 大纲合规修复的 diff 是否改变了剧情走向、角色决策或因果关系 | `critical`：恢复原文该段，记录 deviation |
   | 剧情事实变更 | 角色行为结果、因果关系、数字/数量是否改变 | `critical`：必须恢复原文该段 |
   | 设定违规引入 | 变更后出现原文没有的能力/地点/角色名 | `critical`：必须恢复原文该段 |
   | OOC 引入 | 角色语气/决策风格与角色档案明显偏离 | `high`：恢复或重新改写该段 |
   | 大纲偏离 | 变更后偏离大纲要求的事件/结果 | `critical`：必须恢复原文该段 |
   | 过度删减 | 单次润色删除超过原文 20% 内容 | `high`：检查是否误删关键信息 |

3. **违规处理**：
   - 若发现 `critical` 违规：从 `pre_polish` 快照恢复对应段落，仅保留非违规的改写
   - 若发现 `high` 违规但无 `critical`：记录到变更摘要的 deviation 中
   - 最多执行 1 轮修正，避免无限循环

4. **编码校验（乱码检测与自动修复）**（v10.1.0 新增）：
   ```bash
   cd "${PROJECT_ROOT}" && python "${SCRIPTS_DIR}/encoding_validator.py" \
     --file "${PROJECT_ROOT}/正文/第${chapter_padded}章${title_suffix}.md"
   ```
   - 若退出码 = 1（检测到 U+FFFD 乱码）：读取 JSON 输出，根据 `context_before` / `context_after` 推断正确字符，用 Edit 替换，再次检测确认。最多 2 轮。
   - 此检查为 `critical` 级：润色引入的乱码必须修复后才能进入 Step 5。

5. **情感扁平化差分检测**（v7.0.5 新增，轻量级）：
   - 对比润色前快照与润色后正文的情感密度：
     - 统计润色前后的感叹句数量、感官描写句数量、短句（≤8字）占比
     - 若润色后感叹句减少 ≥ 50% 或感官描写句减少 ≥ 40% → 输出 `⚠️ 润色后情感密度下降，建议检查是否过度修改情感段落`
   - 此检查为 WARNING 级，不阻断流程，仅提示
   - 若 Data Agent 在 Step B.10 产出了 `subtext_markers`，额外检查：润色是否删除或弱化了标记的潜台词段落

6. **清理快照**（Step 5 开始前）：
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

##### C.4 审查分数趋势检查（WARNING，非阻断）

> 来源：桌面评审"25章 Quick Audit 间隔是最大叙事质量盲区"。通过查询最近5章的 review_metrics 分数趋势，在每章级别捕获质量下滑。

```bash
python3 -X utf8 -c "
import sqlite3, sys
db_path = '${PROJECT_ROOT}/.ink/index.db'
chapter = ${chapter_num}
try:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        'SELECT end_chapter, overall_score FROM review_metrics WHERE end_chapter <= ? ORDER BY end_chapter DESC LIMIT 5',
        (chapter,)
    ).fetchall()
    conn.close()
    if len(rows) < 3:
        print('✅ Mini-Audit C.4 跳过（历史数据不足3章）')
        sys.exit(0)
    scores = [r[1] for r in reversed(rows)]
    declining = all(scores[i] > scores[i+1] for i in range(len(scores)-1))
    if declining and len(scores) >= 3:
        trend = ' → '.join(f'{s:.0f}' for s in scores)
        print(f'⚠️ Mini-Audit C.4 WARNING: 最近{len(scores)}章审查分数持续下降: {trend}')
        print(f'   建议关注质量趋势，考虑运行 /ink-review 进行详细审查')
    else:
        avg = sum(scores) / len(scores)
        print(f'✅ Mini-Audit C.4 PASS: 最近{len(scores)}章平均分 {avg:.1f}，趋势正常')
except Exception as e:
    print(f'⚠️ mini_audit_skipped: {e}')
"
```

**处理规则**：WARNING 级，记录但不阻断。连续3章以上分数持续下降时输出趋势警告，提醒关注质量。

##### Mini-Audit 汇总输出

```
=== Step 5 Mini-Audit 结果 ===
C.1 主角状态同步: PASS / FAIL / SKIPPED
C.2 实体提取数量: PASS / WARNING / SKIPPED
C.3 时间线锚点: PASS / WARNING / SKIPPED
C.4 审查分数趋势: PASS / WARNING / SKIPPED
阻断: 是/否
```

仅当 C.1 为 FAIL（重试后仍失败）时阻断 Step 5 完成。其余 WARNING 记录到审查报告但不阻断。

### Step 5.5：前序章数据即时修复（Cascading Data Fix）

> **原理**：Step 3 审查可能发现前序章的数据层问题（如时间线锚点错误、角色状态不一致）。这类问题会通过 context-agent 传播到后续章节——如果不立即修复，每一章都会继承错误数据，形成雪崩式传播。正文层问题（如某段描写不够充分）不会传播，可以等 5 章检查点批量修复。

**触发条件**（必须同时满足）：
1. Step 3 审查报告中存在涉及**前序章**的 `TIMELINE_ISSUE`（severity ≥ high）或数据一致性问题
2. Mini-Audit C.1 或 C.3 报告了 FAIL 或 WARNING

**不触发的情况**：
- 问题仅涉及当前章正文（已由 Step 4 polish 处理）
- 问题仅涉及前序章正文（等 5 章检查点由 ink-fix 批量处理）
- Mini-Audit 全部 PASS

**执行逻辑**：

```
if (C.1 == FAIL 且已自动修复) or (C.3 == WARNING):
    # 1. 识别受影响的前序章数据
    affected = 从 Mini-Audit 报告中提取受影响的章节号和字段
    
    # 2. 仅修复数据层（state.json / index.db），不改正文
    for chapter_id in affected:
        修复 state.json 中 chapter_meta[chapter_id] 的错误字段
        修复 index.db 中对应记录（时间锚点、角色状态等）
    
    # 3. 验证修复
    重跑 Mini-Audit C.1 和 C.3 验证数据一致性
    
    # 4. 记录修复日志
    输出: "Step 5.5: 已修复前序章数据 [ch{N}] — {修复内容摘要}"
```

**约束**：
- **只修数据，不改正文**：正文修复需要全局视野，交给 5 章检查点的 ink-fix
- **耗时预算**：≤ 30 秒（仅 JSON/SQLite 操作，无 LLM 调用）
- **最多修复 3 章**：超过 3 章受影响说明问题系统性，暂停并输出诊断报告
- **修复失败不阻断**：记录 WARNING 继续进入 Step 6，留给检查点处理

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
3. **大纲覆盖批量验证**（必做）：一次性检查范围内所有章节的大纲覆盖：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
     check-outline --chapter {batch_start} --batch-end {batch_end}
   ```
   > **⚠️ 关键**：必须使用 `check-outline` 子命令，禁止使用 `extract-context --format pack`（pack 格式会吞掉 ⚠️ 标记）。

   若 `check-outline` 退出码非零，立即阻断并输出：
   ```
   ❌ 大纲覆盖验证失败，批量写作中止。
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
