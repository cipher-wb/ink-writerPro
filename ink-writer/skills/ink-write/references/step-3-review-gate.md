# Step 3 Review Gate

## 调用约束（硬规则）

- 必须使用 `Task` 调用审查 subagent，禁止主流程直接内联“自审结论”。
- Step 3 开始前，必须先生成 `review_bundle_file`，并把该绝对路径传给所有 checker。
- 审查任务全量并发（US-503），首个硬门禁失败立即 cancel 其余并触发 polish。
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

`auto` 路由：核心 7 个始终执行 + 条件审查器按命中执行。

核心审查器（始终执行）：
- `consistency-checker`
- `continuity-checker`
- `ooc-checker`
- `logic-checker`
- `outline-compliance-checker`
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

## Checker 输入 Profile 映射表（审查包瘦身）

每个 checker 只需消费审查包的部分字段。生成瘦身包时，按下表提取对应字段子集。
**meta 字段始终保留**：`chapter`、`project_root`、`chapter_file`、`chapter_file_name`、`chapter_char_count`、`absolute_paths`、`allowed_read_files`、`review_policy`。

### 核心 Checker Profile

| Checker | 需要的字段（除 meta 外） | 说明 |
|---------|------------------------|------|
| `anti-detection-checker` | `chapter_text` | 最轻量——仅需正文做 AI 味检测 |
| `logic-checker` | `chapter_text`、`scene_context`、`setting_snapshots`、`core_context` | 需要角色属性+设定做 L1-L8 验证 |
| `outline-compliance-checker` | `chapter_text`、`outline`、`scene_context`、`core_context` | 需要大纲+MCC 做合规验证 |
| `continuity-checker` | `chapter_text`、`previous_chapters`、`memory_context`、`outline`、`narrative_commitments`、`plot_structure_fingerprints` | 需要前序+记忆做连贯验证 |
| `consistency-checker` | `chapter_text`、`setting_snapshots`、`scene_context`、`previous_chapters`、`memory_context`、`narrative_commitments`、`plot_structure_fingerprints` | 最重量——跨章设定一致性 |
| `ooc-checker` | `chapter_text`、`scene_context`、`previous_chapters`、`setting_snapshots` | 角色行为/对话一致验证 |
| `reader-pull-checker` | `chapter_text`、`reader_signal`、`memory_context`、`outline`、`golden_three_contract` | 追读力评估 |

### 条件 Checker Profile 复用规则

条件 checker 复用最近核心 checker 的 profile：

| 条件 Checker | 复用 Profile | 理由 |
|-------------|-------------|------|
| `golden-three-checker` | `reader-pull-checker` | 同属读者体验维度 |
| `high-point-checker` | `reader-pull-checker` | 同属读者体验维度 |
| `pacing-checker` | `continuity-checker` | Strand 平衡需要前序+记忆 |
| `proofreading-checker` | `anti-detection-checker` | 同属文本表层检查 |
| `reader-simulator` | `reader-pull-checker` | 同属读者体验维度 |
| `emotion-curve-checker` | `reader-pull-checker` | 情绪曲线需要读者信号 |

### 瘦身包生成规则

1. 先生成完整审查包（`review_bundle_ch${chapter_padded}.json`）。
2. 为每个选中的 checker 生成瘦身包：从完整包中提取 meta 字段 + profile 指定字段。
3. **降级兜底**：若瘦身包生成失败（脚本异常/字段缺失），退回完整包，不影响审查流程。
4. 瘦身包路径：`${PROJECT_ROOT}/.ink/tmp/review_bundle_ch${chapter_padded}_${checker_name}.json`。
5. Task 传参时 `review_bundle_file` 指向对应瘦身包路径。

## Task 调用模板（示意）

**并发策略（US-503）**：所有独立 checker 同时并行发射，首个硬门禁失败立即 cancel 其余。

```text
selected = [“consistency-checker”, “continuity-checker”, “ooc-checker”,
            “logic-checker”, “outline-compliance-checker”,
            “anti-detection-checker”, “reader-pull-checker”]

if mode != “minimal”:
  if chapter <= 3: selected.append(“golden-three-checker”)
  if trigger_high_point: selected.append(“high-point-checker”)
  if trigger_pacing: selected.append(“pacing-checker”)
  if trigger_proofreading: selected.append(“proofreading-checker”)
  if trigger_reader_sim: selected.append(“reader-simulator”)
  if trigger_emotion: selected.append(“emotion-curve-checker”)

# 全量并发：所有 checker 同时启动（max_concurrency 由 Claude Code Task 调度器控制）
run Task in parallel(selected, max_concurrency=len(selected))

# 首个硬门禁失败 → 立即触发 polish，无需等其他 checker 完成
# 硬门禁: consistency, continuity, ooc, logic-checker, outline-compliance-checker
# （核心权重 90%，任一 score<40 即 hard fail）
# 逻辑/大纲合规硬阻断: critical 或 ≥2 high → 回退 Step 2A（见下方门禁规则）
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
| `continuity-checker` | 15% | 连贯性 | 核心——场景衔接/伏笔/逻辑 |
| `ooc-checker` | 20% | 人物塑造 | 核心——角色行为/对话一致 |
| `logic-checker` | 15% | 逻辑自洽 | 核心——章内数字/动作/属性/空间/物品/感官/对话/因果 |
| `outline-compliance-checker` | 15% | 大纲合规 | 核心——实体出场/禁止发明/目标充分/伏笔/钩子/黄金三章 |
| `reader-pull-checker` | 10% | 追读力 | 始终执行——钩子/微兑现/下章动机 |
| `high-point-checker` | 10% | 爽点密度 | 条件——爽点密度/类型/质量 |
| `pacing-checker` | 5% | 节奏控制 | 条件——Strand 平衡 |
| `proofreading-checker` | 5% | 文笔质量 | 条件——修辞/段落/代称/禁忌 |
| `golden-three-checker` | 特殊 | 黄金三章 | 仅ch1-3，替代 reader-pull 的 10% 权重 |
| `emotion-curve-checker` | 5% | 情绪曲线 | 条件——情绪起伏/平淡段/目标对齐 |
| `reader-simulator` | 特殊 | 阅读体验 | 仅关键章启用，不参与总分计算，独立输出沉浸度/弃读风险 |

### 计算公式

```
overall_score = Σ(checker_score × weight) / Σ(active_weights)
```

- 只对实际启用的 checker 计算，权重自动归一化
- 例：minimal 模式只启用核心 checker 子集（如 consistency+continuity+ooc，权重 25+15+20=60），则 `overall_score = (c×25 + t×15 + o×20) / 60 × 100`
- 若任一 checker 存在 `critical` 问题，`overall_score` 上限为 60（无论加权分多高）
- **逻辑/大纲合规 critical 更严格**：若 `logic-checker` 或 `outline-compliance-checker` 存在 `critical` 问题，`overall_score` 上限为 **50**（逻辑错误比文风问题更致命）
- `golden-three-checker` 仅在 ch1-3 启用时替代 `reader-pull-checker` 的 10% 权重

### dimension_scores 计算

`dimension_scores` 的每个键直接取对应 checker 的 `overall_score`，不做二次加权：
```json
{
  "设定一致性": 85,
  "连贯性": 90,
  "人物塑造": 82,
  "逻辑自洽": 88,
  "大纲合规": 92,
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
- **逻辑门禁**：若 `logic-checker` 存在 critical 或 ≥2 个 high issue，禁止进入 Step 4，必须回退 Step 2A 重写（详见下方逻辑门禁规则）。
- **大纲合规门禁**：若 `outline-compliance-checker` 存在 critical 或 ≥2 个 high issue，禁止进入 Step 4，必须回退 Step 2A 重写（详见下方大纲合规门禁规则）。
- **卖点密度门禁**：若 `high-point-checker` 报告 `SELLING_POINT_DEFICIT` severity=critical（大卖点缺失或小卖点<2），禁止进入 Step 4，必须回退 Step 2A 重写（详见下方卖点密度门禁规则）。卖点缺失是结构性问题，润色无法补救。
- **时间线闸门**：若存在 `TIMELINE_ISSUE` 且 `severity >= high`，禁止进入 Step 4/5，必须先修复。
- **黄金三章硬拦截**：当 `chapter <= 3` 且 `golden-three-checker` 存在任何 `severity = high` 的 issue 时，**硬拦截**——必须回退 Step 2A 重写开篇（不是 Step 4 润色）。黄金三章质量不足是结构性问题，润色无法修复。
- **反 AI 开头硬拦截**：当 `anti-detection-checker` 报告 opening pattern `critical` 时，该 critical 也纳入总分 cap 逻辑（`overall_score` 上限 60），与其他 critical 同等对待。
- **AI味句式多样性硬门禁**（Step 3.8）：anti-detection-checker 综合分低于阈值时触发 polish 定向修复（最多 1 轮）；零容忍清单（时间标记开头、"与此同时"）匹配即阻断，不重试。详见 Step 3.8。
- **读者体验阻断**：当 `reader-simulator` 输出 `reader_verdict.verdict = "rewrite"`（总分 < 25）时，**硬拦截**——回退 Step 2A 重写。此规则对 chapter 1-3 为硬门控，对 chapter 4+ 为强建议（输出警告但允许继续）。

### 逻辑门禁（Logic Gate）

**Hard Block（回退 Step 2A 重写）**：
- `logic-checker` 存在任何 `critical` issue
- `logic-checker` 存在 ≥2 个 `high` issue

**Soft Warning（传递给 polish-agent 修复）**：
- 仅 `medium` / `low` issue → 作为 `logic_fix_prompt` 传递给 Step 4 polish-agent

**闸门判定逻辑**：
```text
logic_issues = logic-checker.issues
logic_critical = filter(logic_issues, severity="critical")
logic_high = filter(logic_issues, severity="high")

if len(logic_critical) > 0 or len(logic_high) >= 2:
    BLOCK: "逻辑门禁触发：{len(logic_critical)} 个 critical + {len(logic_high)} 个 high 逻辑问题"
    # 生成 repair context（精简版）传递给 Step 2A writer-agent
    repair_context = [{
        "issue_type": issue.type,
        "severity": issue.severity,
        "location": issue.location,    # 段落/行号定位
        "fix_suggestion": issue.suggestion
    } for issue in logic_critical + logic_high]
    return BLOCKED, repair_context
else:
    通过: "逻辑检查通过（{len(logic_medium)} 个 medium 问题转 polish 修复）"
```

### 大纲合规门禁（Outline Compliance Gate）

**Hard Block（回退 Step 2A 重写）**：
- `outline-compliance-checker` 存在任何 `critical` issue
- `outline-compliance-checker` 存在 ≥2 个 `high` issue

**Soft Warning（传递给 polish-agent 修复）**：
- 仅 `medium` / `low` issue → 作为 `outline_fix_prompt` 传递给 Step 4 polish-agent

**闸门判定逻辑**：
```text
occ_issues = outline-compliance-checker.issues
occ_critical = filter(occ_issues, severity="critical")
occ_high = filter(occ_issues, severity="high")

if len(occ_critical) > 0 or len(occ_high) >= 2:
    BLOCK: "大纲合规门禁触发：{len(occ_critical)} 个 critical + {len(occ_high)} 个 high 合规问题"
    repair_context = [{
        "issue_type": issue.type,
        "severity": issue.severity,
        "location": issue.location,
        "fix_suggestion": issue.suggestion
    } for issue in occ_critical + occ_high]
    return BLOCKED, repair_context
else:
    通过: "大纲合规检查通过（{len(occ_medium)} 个 medium 问题转 polish 修复）"
```

### 卖点密度门禁（Selling Point Gate）

> US-007 新增。确保审查层拦截卖点缺失的章节。

**Hard Block（回退 Step 2A 重写）**：
- `high-point-checker` 报告 `SELLING_POINT_DEFICIT` 且 severity = `critical`（大卖点缺失或小卖点 < 2）
- 连续2章大卖点缺失（rolling window critical）

**Soft Warning（传递给 polish-agent 修复）**：
- `SELLING_POINT_DEFICIT` severity = `high`（大卖点无反应段）→ 进入 Step 4 润色修复
- `SELLING_POINT_DEFICIT` severity = `medium`（小卖点无情绪触发）→ 建议修复
- `SELLING_POINT_FRONT_LOADING` severity = `high`（前1/3无小卖点）→ 进入 Step 4 润色修复

**闸门判定逻辑**：
```text
sp_issues = high-point-checker.issues.filter(rule startswith "SELLING_POINT")
sp_critical = filter(sp_issues, severity="critical")

if len(sp_critical) > 0:
    BLOCK: "卖点密度门禁触发：{details}"
    # 卖点缺失是结构性问题，必须回退 Step 2A 重写，不能仅靠 Step 4 润色
    repair_context = [{
        "issue_type": issue.rule + "." + issue.sub_rule,
        "severity": issue.severity,
        "location": "全章",
        "fix_suggestion": issue.detail
    } for issue in sp_critical]
    return BLOCKED, repair_context
else:
    sp_high = filter(sp_issues, severity="high")
    if len(sp_high) > 0:
        通过（带修复建议）: "卖点检查有 {len(sp_high)} 个 high 问题，转 polish 修复"
    else:
        通过: "卖点密度检查通过"
```

### 逻辑/合规门禁回退机制

**回退 Step 2A 重写流程**：
1. 硬阻断触发时，将 `repair_context`（issues[] 精简版：issue_type / severity / location / fix_suggestion）注入 writer-agent 作为额外输入
2. Writer-agent 基于 repair context 定向修复问题区域，重新输出正文
3. 重新进入 Step 3 审查（仅重跑触发阻断的 checker + 核心 checker）

**回退次数限制**：
- 逻辑门禁和大纲合规门禁各自独立计数回退次数
- 每个门禁最多触发 **2 次**回退
- 第 3 次同一门禁失败 → **暂停流程**，输出诊断报告请求人工干预：
  ```text
  ⚠️ 流程暂停：{gate_name} 已连续失败 3 次
  - 失败章节：第 {chapter} 章
  - 累计未解决 issues：{issues_summary}
  - 建议：人工检查大纲与正文的适配性，或调整大纲要求
  ```

**repair_context 膨胀控制**：
- 只传递 `critical` 和 `high` 级别的 issue 精简信息
- 每条 issue 仅包含 4 个字段（type / severity / location / suggestion），不传完整报告正文
- 总 token 预算：repair_context 不超过 500 tokens

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
