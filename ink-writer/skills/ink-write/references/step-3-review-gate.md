# Step 3 Review Gate

## 调用约束（硬规则）

- 必须使用 `Task` 调用审查 subagent，禁止主流程直接内联“自审结论”。
- Step 3 开始前，必须先生成 `review_bundle_file`，并把该绝对路径传给所有 checker。
- 审查任务不得无上限并发；最大并发数为 2，条件审查器默认顺序执行。
- `overall_score` 必须来自聚合结果，不可主观估分。
- 单章写作场景下，统一传入：`{chapter, chapter_file, project_root, review_bundle_file}`。
- `chapter_file` 与 `review_bundle_file` 必须是绝对路径，禁止把目录路径或相对路径交给 checker。

## 审查包（新增，必做）

先生成结构化审查包，供所有 checker 复用：

```bash
mkdir -p "${PROJECT_ROOT}/.ink/tmp"
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" \
  extract-context --chapter {chapter_num} --format review-pack-json \
  > "${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}.json"
```

审查包职责：
- 内嵌当前章节正文、前序章节摘要、黄金三章契约、写作 guidance、记忆卡、设定快照。
- 提供 `allowed_read_files` 绝对路径白名单。
- 明确禁止读取 `.db` 文件、目录路径和白名单外的相对路径。

## 审查路由模式

`auto` 路由：核心 5 个始终执行 + 条件审查器按命中执行。

核心审查器（始终执行）：
- `consistency-checker`
- `continuity-checker`
- `ooc-checker`
- `anti-detection-checker`
- `reader-pull-checker`

条件审查器（仅 `auto` 命中时执行）：
- `golden-three-checker`
- `high-point-checker`
- `pacing-checker`
- `proofreading-checker`
- `reader-simulator`
- `emotion-curve-checker`

## Auto 路由判定信号

输入信号来源：
1. Step 1.5 合同（是否过渡章、追读力设计、核心冲突）。
2. 本章正文（战斗/反转/高光/章末未闭合问题等信号）。
3. 大纲标签（关键章/高潮章/卷末章/转场章）。
4. 最近章节节奏（连续主线、情感线断档、世界观线断档）。

路由规则：
- `golden-three-checker`：当满足任一条件时启用
  - `chapter <= 3`；
  - 用户显式要求”黄金三章审查”；
  - `.ink/golden_three_plan.json` 明确开启且当前章在 1-3 范围内。
- `reader-pull-checker`：**始终启用**
  - 硬约束 5 条检查始终执行（可读性底线/承诺违背/节奏灾难/冲突真空/开篇空洞）
  - 过渡章仅降级软评分要求（权重减半），不跳过硬约束
  - 确保每章都有 chapter_reading_power 数据写入，保障下章差异化检查的数据连续性
- `high-point-checker`：当满足任一条件时启用
  - 关键章/高潮章/卷末章；
  - 正文出现战斗、反杀、打脸、身份揭露、大反转等高光信号。
- `pacing-checker`：当满足任一条件时启用
  - 章号 >= 10；
  - 最近章节存在明显节奏失衡风险；
  - 用户显式要求”节奏审查”。
- `proofreading-checker`：当满足任一条件时启用
  - `chapter >= 1`（所有章节均可启用文笔检查）；
  - 非过渡章（过渡章文笔要求较低，可跳过）；
  - 题材涉及古代/仙侠/历史背景（文化禁忌检测价值更高）；
  - 用户显式要求”文笔审查”或”校对”。

  > **与 golden-three-checker 的覆盖关系**：前 3 章（ch1-3）golden-three-checker 覆盖**叙事质量**（开篇抓取力、读者承诺兑现、章末驱动力），proofreading-checker 覆盖**文笔质量**（修辞重复、段落结构、代称混乱、文化禁忌）。两者维度不同，不互斥。前 3 章应同时启用两个 checker。style_consistency 风格漂移检测仅在 ch ≥ 10 时激活。
- `reader-simulator`：当满足任一条件时启用
  - 关键章/高潮章/卷末章/卷首章；
  - 用户显式要求”读者体验审查”或”模拟读者”；
  - 最近 3 章审查分数持续下降（连续递减 ≥ 5 分/章）。
- `emotion-curve-checker`：当满足任一条件时启用
  - 章号 >= 5（前期章节情绪数据不足以对比）；
  - 最近 3 章情绪方差持续偏低（data/emotion_curves.jsonl 中 valence_variance < 0.15）；
  - 关键章/高潮章/情感线章节（大纲标签命中）；
  - 用户显式要求”情绪审查”或”情绪曲线检查”。

## Task 调用模板（示意）

```text
selected = [“consistency-checker”, “continuity-checker”, “ooc-checker”]

if mode != “minimal”:
  if chapter <= 3: selected.append(“golden-three-checker”)
  selected.append(“reader-pull-checker”)  # 始终执行，过渡章仅降级软评分权重
  if trigger_high_point: selected.append(“high-point-checker”)
  if trigger_pacing: selected.append(“pacing-checker”)
  if trigger_proofreading: selected.append(“proofreading-checker”)
  if trigger_reader_sim: selected.append(“reader-simulator”)

core_stage = ["consistency-checker", "continuity-checker"]
run Task in parallel(core_stage, max_concurrency=2)
run Task("ooc-checker", {chapter, chapter_file, project_root, review_bundle_file})

for agent in conditional_selected:
  run Task(agent, {chapter, chapter_file, project_root, review_bundle_file})
```

## 输出契约（统一）

每个 checker 返回值必须遵循 `${CLAUDE_PLUGIN_ROOT}/references/checker-output-schema.md`：
- 必含：`agent`、`chapter`、`overall_score`、`pass`、`issues`、`metrics`、`summary`
- 允许扩展字段（如 `hard_violations`、`soft_suggestions`），但不得替代必填字段

## 总分聚合规则（必须按此公式计算，禁止主观估分）

### Checker 权重表

| Checker | 权重 | 对应 dimension_scores 键 | 说明 |
|---------|------|------------------------|------|
| `consistency-checker` | 25% | 设定一致性 | 核心——战力/地点/时间线一致 |
| `continuity-checker` | 20% | 连贯性 | 核心——场景衔接/伏笔/逻辑 |
| `ooc-checker` | 20% | 人物塑造 | 核心——角色行为/对话一致 |
| `reader-pull-checker` | 15% | 追读力 | 始终执行——钩子/微兑现/下章动机 |
| `high-point-checker` | 10% | 爽点密度 | 条件——爽点密度/类型/质量 |
| `pacing-checker` | 5% | 节奏控制 | 条件——Strand 平衡 |
| `proofreading-checker` | 5% | 文笔质量 | 条件——修辞/段落/代称/禁忌 |
| `golden-three-checker` | 特殊 | 黄金三章 | 仅ch1-3，替代 reader-pull 的 15% 权重 |
| `emotion-curve-checker` | 5% | 情绪曲线 | 条件——情绪起伏/平淡段/目标对齐 |
| `reader-simulator` | 特殊 | 阅读体验 | 仅关键章启用，不参与总分计算，独立输出沉浸度/弃读风险 |

### 计算公式

```
overall_score = Σ(checker_score × weight) / Σ(active_weights)
```

- 只对实际启用的 checker 计算，权重自动归一化
- 例：minimal 模式只启用 3 个核心 checker（权重 25+20+20=65），则 `overall_score = (c×25 + t×20 + o×20) / 65 × 100`
- 若任一 checker 存在 `critical` 问题，`overall_score` 上限为 60（无论加权分多高）
- `golden-three-checker` 仅在 ch1-3 启用时替代 `reader-pull-checker` 的 15% 权重

### dimension_scores 计算

`dimension_scores` 的每个键直接取对应 checker 的 `overall_score`，不做二次加权：
```json
{
  "设定一致性": 85,
  "连贯性": 90,
  "人物塑造": 82,
  "追读力": 78,
  "爽点密度": 88,
  "节奏控制": 75,
  "文笔质量": 80
}
```

未启用的 checker 对应维度不写入 `dimension_scores`（不要填 0 或默认值）。

聚合输出最小字段：
- `chapter`（单章）
- `start_chapter`、`end_chapter`（单章时二者都等于 `chapter`）
- `selected_checkers`
- `overall_score`（按上方公式计算）
- `severity_counts`
- `critical_issues`
- `issues`（扁平化聚合）
- `dimension_scores`（按上方规则填充）
- `review_payload_json`（可选；结构化扩展字段，黄金三章指标写这里）

## 汇总输出模板

```text
审查汇总 - 第 {chapter_num} 章
- 已启用审查器: {list}
- 严重问题: {N} 个
- 高优先级问题: {N} 个
- 综合评分: {score}
- 可进入润色: {是/否}
```

## 审查指标落库（必做）

```bash
mkdir -p "${PROJECT_ROOT}/.ink/tmp"
# 生成 review_metrics.json 时，优先使用 Bash heredoc 直接写入文件；
# 不要用 Write 直接创建一个尚未读取过的新文件，避免工具链拒绝创建。
# 例如：
# cat > "${PROJECT_ROOT}/.ink/tmp/review_metrics.json" <<'JSON'
# {...}
# JSON
python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index save-review-metrics --data "@${PROJECT_ROOT}/.ink/tmp/review_metrics.json"
```

review_metrics 文件字段约束（当前工作流约定只传以下字段）：
- `start_chapter`（int）、`end_chapter`（int）：单章时二者相等
- `overall_score`（float）：必填
- `dimension_scores`（Dict[str, float]）：按已启用 checker 计算
- `severity_counts`（Dict[str, int]）：键为 critical / high / medium / low
- `critical_issues`（List[str]）
- `report_file`（str）
- `notes`（str）：保留给人读的摘要；必须是单个字符串
- `review_payload_json`（Dict[str, Any]，可选）：结构化扩展信息统一放这里，例如：
  - `selected_checkers`
  - `timeline_gate`
  - `anti_ai_force_check`
  - `golden_three_metrics`

## 进入 Step 4 前闸门

- `overall_score` 已生成。
- `save-review-metrics` 已成功。
- 审查报告中的 `issues`、`severity_counts` 可被 Step 4 直接消费。
- **时间线闸门**：若存在 `TIMELINE_ISSUE` 且 `severity >= high`，禁止进入 Step 4/5，必须先修复。
- **黄金三章硬拦截**：当 `chapter <= 3` 且 `golden-three-checker` 存在任何 `severity = high` 的 issue 时，**硬拦截**——必须回退 Step 2A 重写开篇（不是 Step 4 润色）。黄金三章质量不足是结构性问题，润色无法修复。
- **反 AI 开头硬拦截**：当 `anti-detection-checker` 报告 opening pattern `critical` 时，该 critical 也纳入总分 cap 逻辑（`overall_score` 上限 60），与其他 critical 同等对待。
- **AI味句式多样性硬门禁**（Step 3.8）：anti-detection-checker 综合分低于阈值时触发 polish 定向修复（最多 1 轮）；零容忍清单（时间标记开头、"与此同时"）匹配即阻断，不重试。详见 Step 3.8。
- **读者体验阻断**：当 `reader-simulator` 输出 `reader_verdict.verdict = "rewrite"`（总分 < 25）时，**硬拦截**——回退 Step 2A 重写。此规则对 chapter 1-3 为硬门控，对 chapter 4+ 为强建议（输出警告但允许继续）。

### 时间线闸门规则

**Hard Block（必须修复才能继续）**：
- `TIMELINE_ISSUE` + `severity = critical`（倒计时算术错误）
- `TIMELINE_ISSUE` + `severity = high`（事件先后矛盾/年龄冲突/时间回跳/大跨度无过渡）

**Soft Warning（建议修复但可继续）**：
- `TIMELINE_ISSUE` + `severity = medium`（时间锚点缺失）
- `TIMELINE_ISSUE` + `severity = low`（轻微时间模糊）

**闸门判定逻辑**：
```text
timeline_issues = filter(issues, type="TIMELINE_ISSUE")
critical_timeline = filter(timeline_issues, severity in ["critical", "high"])

if len(critical_timeline) > 0:
    BLOCK: "存在 {len(critical_timeline)} 个严重时间线问题，必须修复后才能进入润色步骤"
    for issue in critical_timeline:
        print(f"- 第{issue.chapter}章: {issue.description}")
    return BLOCKED
else:
    通过: "时间线检查通过"
```

**修复指引**：
- 倒计时错误 → 修正倒计时推进，确保 D-N → D-(N-1) 连续
- 时间回跳 → 添加闪回标记，或调整时间锚点
- 大跨度无过渡 → 添加时间过渡句/段，或插入过渡章
- 事件先后矛盾 → 调整事件发生顺序或添加时间跳跃说明
