---
name: ink-review
description: Reviews chapter quality with checker agents and generates reports. Use when the user asks for a chapter review or runs /ink-review.
allowed-tools: Read Grep Write Edit Bash Task AskUserQuestion
---

# Quality Review Skill

## Project Root Guard（必须先确认）

- Claude Code 的“工作区根目录”不一定等于“书项目根目录”。常见结构：工作区为 `D:\wk\xiaoshuo`，书项目为 `D:\wk\xiaoshuo\凡人资本论`。
- 必须先解析真实书项目根（必须包含 `.ink/state.json`），后续所有读写路径都以该目录为准。

环境设置（bash 命令执行前）：
```bash
export INK_SKILL_NAME="ink-review"
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
```


## Step 0: 充分性闸门（Sufficiency Gate）

> 本步骤强制执行。未通过闸门的审查请求直接终止并报告原因。

**检查清单**：

1. **章节文件存在性**：确认待审查章节文件存在且字数 > 500
2. **写作完成标记**：确认 workflow_state.json 中 current_step ≥ "Step 2A completed"（若 workflow_state 不存在，仅检查章节文件是否存在且完整）
3. **大纲可用性**：确认对应章节的章纲文件存在（卷纲目录下的对应章节条目）
4. **index.db 可用性**：确认 index.db 存在且可读

```bash
# 充分性检查
CHAPTER_FILE=$(find "${PROJECT_ROOT}" -name "*${CHAPTER_NUM}*" -path "*/chapters/*" 2>/dev/null | head -1)
if [ -z "$CHAPTER_FILE" ] || [ ! -s "$CHAPTER_FILE" ]; then
  echo "GATE FAIL: 章节文件不存在或为空" >&2; exit 1
fi
WORD_COUNT=$(wc -m < "$CHAPTER_FILE" 2>/dev/null || echo 0)
if [ "$WORD_COUNT" -lt 500 ]; then
  echo "GATE FAIL: 章节字数 ${WORD_COUNT} < 500，可能未完成写作" >&2; exit 1
fi
if [ ! -f "${PROJECT_ROOT}/.ink/index.db" ]; then
  echo "GATE FAIL: index.db 不存在" >&2; exit 1
fi
```

**失败处理**：
- 任一检查未通过 → 输出具体失败原因 → 建议用户先完成对应步骤 → 终止审查流程
- 不尝试降级执行，不跳过检查

---

## 0.5 工作流断点（best-effort，不得阻断主流程）

> 目标：让 `/ink-resume` 能基于真实断点恢复。即使 workflow_manager 出错，也**只记录警告**，审查继续。

推荐（bash）：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-task --command ink-review --chapter {end} || true
```

Step 映射（必须与 `workflow_manager.py get_pending_steps("ink-review")` 对齐）：
- Step 1：加载参考
- Step 2：加载项目状态
- Step 3：并行调用检查员
- Step 4：生成审查报告
- Step 5：保存审查指标到 index.db
- Step 6：写回审查记录到 state.json
- Step 7：处理关键问题（AskUserQuestion）
- Step 8：收尾（完成任务）

Step 记录模板（bash，失败不阻断）：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-step --step-id "Step 1" --step-name "加载参考" || true
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step --step-id "Step 1" --artifacts '{"ok":true}' || true
```

## Review depth

- **Core (default)**: consistency / continuity / ooc / reader-pull / **reader-simulator（快速模式）** / **flow-naturalness-checker（US-014 新增，核心文笔层）**
- **Full (关键章/用户要求)**: core + high-point + pacing + proofreading + golden-three(前3章) + **prose-impact-checker（US-014）** + **sensory-immersion-checker（US-014）**
- **Full+ (卷首章/卷末章/用户要求)**: full + **reader-simulator（完整模式，替换快速模式）** + anti-detection-checker（US-014：prose-impact-checker 与 sensory-immersion-checker 使用完整分析模式）
- **黄金三章强制项（US-014）**：当 `chapter <= 3` 时，无论选择 Core / Full / Full+，均强制追加 `prose-impact-checker` 与 `sensory-immersion-checker`

> **v9.0 变更**: reader-simulator 从 Full+ 升格为 Core 级别（快速模式）。每章必跑，输出 `reader_verdict` 7 维评分驱动自动返修。Full+ 级别运行完整模式（含情绪曲线和读者独白）。

## Step 1: 加载参考（按需）

## References（按步骤导航）

- Step 1（必读，硬约束）：[core-constraints.md](../../references/shared/core-constraints.md)
- Step 1（可选，Full 或节奏/爽点相关问题）：[cool-points-guide.md](../../references/shared/cool-points-guide.md)
- Step 1（可选，Full 或节奏/爽点相关问题）：[strand-weave-pattern.md](../../references/shared/strand-weave-pattern.md)
- Step 1（可选，仅在返工建议需要时）：[common-mistakes.md](references/common-mistakes.md)
- Step 1（可选，仅在返工建议需要时）：[pacing-control.md](references/pacing-control.md)

## Reference Loading Levels (strict, lazy)

- L0: 先确定审查深度（Core / Full），再加载参考。
- L1: 只加载 References 区的“必读”条目。
- L2: 仅在问题定位需要时加载 References 区的“可选”条目。

**必读**:
```bash
cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"
```

**建议（Full 或需要时）**:
```bash
cat "${SKILL_ROOT}/../../references/shared/cool-points-guide.md"
cat "${SKILL_ROOT}/../../references/shared/strand-weave-pattern.md"
```

**可选**:
```bash
cat "${SKILL_ROOT}/references/common-mistakes.md"
cat "${SKILL_ROOT}/references/pacing-control.md"
```

## Step 2: 加载项目状态（若存在）

```bash
cat "$PROJECT_ROOT/.ink/state.json"
```

## Step 3: 调用检查员（Task）

**调用约束**:
- 必须通过 `Task` 工具调用审查 subagent，禁止主流程直接内联审查结论。
- 先生成 `review_bundle_file`，再把这份绝对路径传给所有 checker。
- 最大并发数为 2；核心 checker 可两两并发，条件 checker 默认顺序执行。
- 各 subagent 结果全部返回后再生成总评与优先级。

```bash
mkdir -p "${PROJECT_ROOT}/.ink/tmp"
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  extract-context --chapter {start} --format review-pack-json \
  > "${PROJECT_ROOT}/.ink/tmp/review_bundle_ch$(printf '%04d' {start}).json"
```

硬规则：
- 必须把 `review_bundle_file` 和 `chapter_file` 的绝对路径传给 checker
- checker 不得自行读取 `.db` 文件或项目目录

**Core**:
- `consistency-checker`
- `continuity-checker`
- `ooc-checker`
- `reader-pull-checker`
- `reader-simulator`（快速模式：仅 7 维评分 + 弃读风险热点，跳过逐段模拟和读者独白）
- `flow-naturalness-checker`（US-014：核心文笔层——信息节奏/融入方式/过渡/对话辨识/黄金比例/语气/voice 七维）

**Full 追加**:
- `golden-three-checker`（仅第 1-3 章强制）
- `high-point-checker`
- `pacing-checker`
- `proofreading-checker`（文笔质量：修辞重复/段落结构/代称混乱/文化禁忌）
- `prose-impact-checker`（US-014：文笔冲击力——镜头多样性/感官丰富度/句式节奏/动词锐度/环境-情绪共振/特写缺失）
- `sensory-immersion-checker`（US-014：感官沉浸——主导感官轮换/深度/通感/感官-情绪匹配/抽象替代）

**Full+ 追加**:
- `reader-simulator`（完整模式：替换 Core 的快速模式，含情绪曲线+读者独白）
- `anti-detection-checker`
- `prose-impact-checker` 与 `sensory-immersion-checker` 切换为**完整分析模式**（逐场景深度统计 + 跨章感官主导轮换校验）

**黄金三章强制项（US-014）**：当 `chapter <= 3` 时，无论选择 Core / Full / Full+，均强制追加 `prose-impact-checker` 与 `sensory-immersion-checker`，保障开篇文笔与感官沉浸双重把关。

## Step 3.5: 编辑智慧硬门禁（Editor Wisdom Hard Gate）

> 在所有 checker 完成后、生成审查报告前，运行编辑智慧门禁检查。

**前置条件**：Step 3 所有 checker 结果已返回。

**执行逻辑**：

1. 加载 `config/editor-wisdom.yaml`，检查 `enabled` 标志
2. 调用 `editor-wisdom-checker` 对章节评分
3. 比较得分与阈值：
   - 章节 1-3：使用 `golden_three_threshold`（默认 0.90）
   - 其他章节：使用 `hard_gate_threshold`（默认 0.75）
4. **若得分 ≥ 阈值**：通过，继续 Step 4
5. **若得分 < 阈值**：
   - 调用 `polish-agent` 传入 violations 列表进行精准修复
   - 重新运行 `editor-wisdom-checker`
   - 最多重试 3 次（1 次初始检查 + 2 次润色后重检）
6. **3 次重试均未通过**：
   - 写入 `chapters/{n}/blocked.md` 描述剩余违规
   - **不输出最终章节文件**（阻断发布）
   - 在审查报告中标注为"编辑智慧门禁阻断"

**日志**：每次检查尝试记录到 `logs/editor-wisdom/chapter_{n}.log`

**编排模块**：`ink_writer/editor_wisdom/review_gate.py` — `run_review_gate()`

```python
from ink_writer.editor_wisdom.review_gate import run_review_gate

gate_result = run_review_gate(
    chapter_text=chapter_text,
    chapter_no=chapter_no,
    project_root=project_root,
    checker_fn=checker_fn,
    polish_fn=polish_fn,
)

if not gate_result.passed:
    # blocked.md already written; halt chapter emission
    pass
```

## Step 3.6: live-review 硬门禁（与 Step 3.5 OR 并列）

> 在 Step 3.5 之后、Step 4 之前运行。Step 3.5（editor-wisdom）与 Step 3.6（live-review）OR 并列：**两 checker 都不通过才阻断；任一通过即放行**。

**前置条件**：
- Step 3.5 已运行并产出 `editor_wisdom_gate_result`（含 `passed` 字段）。
- live-review 向量索引存在（首次需跑 `python3 scripts/live-review/build_vector_index.py`）。

**执行逻辑**：

1. 加载 `config/live-review.yaml`，检查 `enabled` 与 `inject_into.review`。
2. 调 `ink_writer.live_review.review_injection.check_review` 对章节评分：
   - 检索 Top-K=5 相似病例（FAISS + bge-small-zh-v1.5）；
   - LLM 比对正文 → 输出 `score / dimensions / violations / cases_hit`；
   - 由 `chapter_no` 自动选阈值：`chapter_no <= 3` → `golden_three_threshold` 0.75，否则 `hard_gate_threshold` 0.65。
3. **若 `score >= threshold`**：本路通行（`live_review_passed = True`）。
4. **若 `score < threshold`**：
   - 把 `result["violations"]` extend 进 `evidence_chain.violations`（供后续审查报告引用）；
   - 调 `polish_fn` 触发修复（与 Step 3.5 共享同一 polish-agent 实例）；
   - 重检最多 2 次；连续失败则本路 `live_review_passed = False`。
5. **OR 合并**：`final_passed = editor_wisdom_passed OR live_review_passed`。
   - `final_passed = True` → 进入 Step 4；
   - `final_passed = False` → 写 `chapters/{n}/blocked.md`（合并两路 violations），不输出最终章节。

**编排模块**：`ink_writer/live_review/review_injection.py` — `check_review()`

```python
from ink_writer.live_review.review_injection import check_review

live_review_result = check_review(
    chapter_text=chapter_text,
    chapter_no=chapter_no,
    genre_tags=genre_tags,            # 来自 state.json / .ink/state.json:project.genre_tags
    polish_fn=polish_fn,              # 与 Step 3.5 共享 polish-agent 调用器
    config_path=None,                 # 默认 config/live-review.yaml
)

# OR 合并两路硬门禁
final_passed = editor_wisdom_passed or live_review_result["passed"]

if not final_passed:
    # 合并 violations 后写 blocked.md，halt chapter emission
    evidence_chain["violations"].extend(live_review_result["violations"])
```

<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 Python 等价；通过 ink-auto.ps1 包装运行）：

```powershell
python -X utf8 -c @'
from ink_writer.live_review.review_injection import check_review
result = check_review(chapter_text=$chapter_text, chapter_no=$chapter_no, genre_tags=$genre_tags, polish_fn=$polish_fn)
'@
```

**关闭开关**：
- `config/live-review.yaml:inject_into.review: false` → 本步骤短路（`disabled=True` + `passed=True`，不调用 checker / polish）。
- `config/live-review.yaml:enabled: false` → master switch，整个 live-review 模块短路。

**日志**：失败的检查写入 `logs/live-review/chapter_{n}.log`（参考 editor-wisdom 同款）。

## Step 4: 生成审查报告

保存到：`审查报告/第{start}-{end}章审查报告.md`

**报告结构（精简版）**:
```markdown
# 第 {start}-{end} 章质量审查报告

## 综合评分
- 爽点密度 / 设定一致性 / 节奏控制 / 人物塑造 / 连贯性 / 追读力
- **文笔冲击力** / **感官沉浸** / **自然流畅度**（US-014：启用对应 checker 时填入）
- 总评与等级

## 修改优先级
- 🔴 高优先级（必须修改）
- 🟠 中优先级（建议修改）
- 🟡 低优先级（可选优化）

## 改进建议
- 可执行的修复建议
```

**审查指标 JSON（用于趋势统计）**:
```json
{
  "start_chapter": {start},
  "end_chapter": {end},
  "overall_score": 48,
  "dimension_scores": {
    "爽点密度": 8,
    "设定一致性": 7,
    "节奏控制": 7,
    "人物塑造": 8,
    "连贯性": 9,
    "追读力": 9,
    "文笔冲击力": 8,
    "感官沉浸": 7,
    "自然流畅度": 8
  },
  "severity_counts": {"critical": 1, "high": 2, "medium": 3, "low": 1},
  "critical_issues": ["设定自相矛盾"],
  "report_file": "审查报告/第{start}-{end}章审查报告.md",
  "notes": "",
  "review_payload_json": {
    "selected_checkers": [],
    "golden_three_metrics": {}
  }
}
```

注意：此处只生成审查指标 JSON；落库见 Step 5。

## Step 5: 保存审查指标到 index.db（必做）

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index save-review-metrics --data '@review_metrics.json'
```

## Step 6: 写回审查记录到 state.json（必做）

将审查报告记录写回 `state.json.review_checkpoints`，用于后续追踪与回溯（依赖 `update_state.py --add-review`）：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" update-state -- --add-review "{start}-{end}" "审查报告/第{start}-{end}章审查报告.md"
```

## Step 7: 处理关键问题

如发现 critical 问题（`severity_counts.critical > 0` 或 `critical_issues` 非空），**必须使用 AskUserQuestion** 询问用户：
- A) 立即修复（推荐）
- B) 仅保存报告，稍后处理

若用户选择 A：
- 输出“返工清单”（逐条 critical 问题 → 定位 → 最小修复动作 → 注意事项）
- 如用户明确授权可直接修改正文文件，则用 `Edit` 对对应章节文件做最小修复，并建议重新运行一次 `/ink-review` 验证

若用户选择 B：
- 不做正文修改，仅保留审查报告与指标记录，结束本次审查

#### Step 7A：自动重审验证（仅在用户选择"立即修复"后触发）

> **本步骤在 Step 7 修复完成后自动执行，不需要用户额外操作。**

1. **触发条件**：用户选择了选项 A（立即修复），且 Agent 已完成正文修改
2. **执行内容**：
   - 仅调用核心 3 个 checker（consistency-checker、continuity-checker、ooc-checker）
   - 使用与 Step 3 相同的 review_bundle 生成流程
   - 最大并发数 = 2
3. **结果判定**：
   - 若 `critical_count == 0`：输出 `"✅ 重审通过，所有 critical 问题已消除"` → 进入 Step 8
   - 若 `critical_count > 0`：输出 `"⚠️ 仍有 {N} 个 critical 问题未消除"`，列出剩余问题 → 交由用户决定是否继续修复
4. **循环限制**：自动重审**最多执行 1 轮**，防止无限循环。第 2 轮起必须由用户手动触发 `/ink-review`
5. **指标更新**：重审结果覆盖 Step 5 的 review_metrics（保留原始审查记录作为 `review_v1`，重审记录为 `review_v2`）

## Step 8: 收尾（完成任务）

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow start-step --step-id "Step 8" --step-name "收尾" || true
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-step --step-id "Step 8" --artifacts '{"ok":true}' || true
python3 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" workflow complete-task --artifacts '{"ok":true}' || true
```
