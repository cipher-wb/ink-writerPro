---
name: ink-plan
description: Builds volume and chapter outlines from the total outline, inherits creative constraints, and prepares writing-ready chapter plans. Use when the user asks for outlining or runs /ink-plan.
allowed-tools: Read Bash AskUserQuestion
---

# Outline Planning

Purpose: refine 总纲 into volume + chapter outlines. Do not redesign the global story.
Setting policy: 先基于 init 产出的总纲+世界观补齐设定集基线；再在卷纲完成后，直接对现有设定集做增量补充。

## Project Root Guard
- Claude Code 的“工作区根目录”不一定等于“书项目根目录”。常见结构：工作区为 `D:\wk\xiaoshuo`，书项目为 `D:\wk\xiaoshuo\凡人资本论`。
- 必须先解析 `PROJECT_ROOT` 为真实书项目根（必须包含 `.ink/state.json`），后续所有读写路径都以该目录为准。

环境设置（bash 命令执行前）：
```bash
export INK_SKILL_NAME="ink-plan"
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
```


## References（按步骤导航）

- Step 3（必读，节拍表模板）：[大纲-卷节拍表.md](../../templates/output/大纲-卷节拍表.md)
- Step 4.5（必读，时间线模板）：[大纲-卷时间线.md](../../templates/output/大纲-卷时间线.md)
- Step 4（必读，题材配置）：[genre-profiles.md](../../references/genre-profiles.md)
- Step 4（必读，Strand 节奏）：[strand-weave-pattern.md](../../references/shared/strand-weave-pattern.md)
- Step 4（可选，爽点结构需要细化）：[cool-points-guide.md](../../references/shared/cool-points-guide.md)
- Step 5/6（可选，冲突强度分层）：[conflict-design.md](references/outlining/conflict-design.md)
- Step 5（可选，需要钩子/节奏细分）：[reading-power-taxonomy.md](../../references/reading-power-taxonomy.md)
- Step 6（可选，章节微结构细化）：[chapter-planning.md](references/outlining/chapter-planning.md)
- Step 4/5（可选，电竞/直播文/克苏鲁）：[genre-volume-pacing.md](references/outlining/genre-volume-pacing.md)
- Step 6（必读，主角行动动词表）：[protagonist-action-verbs.md](../../references/shared/protagonist-action-verbs.md)
- 归档（不进主流程）：`references/outlining/outline-structure.md`、`references/outlining/plot-frameworks.md`

## Reference Loading Levels (strict, lazy)

Use progressive disclosure and load only what current step requires:
- L0: No references before scope/volume is confirmed.
- L1: Before each step, load only the "必读" items in **References（按步骤导航）**.
- L2: Load optional items only when the trigger condition applies.

## Workflow
1. Load project data.
1.5. **Load propagation debts（FIX-17 P4d，hard constraint）**。
2. Build setting baseline from 总纲 + 世界观 (in-place incremental).
3. Select volume and confirm scope.
4. Generate volume beat sheet (节拍表).
4.5. Generate volume timeline (时间线表).
5. Generate volume skeleton.
6. Generate chapter outlines in batches.
7. Enrich existing setting files from volume outline (in-place incremental).
8. Validate + save + update state（落盘后标记被消化的 debts 为 resolved）。

## 1) Load project data
```bash
cat "$PROJECT_ROOT/.ink/state.json"
cat "$PROJECT_ROOT/大纲/总纲.md"
```

Optional (only if they exist):
- `设定集/主角组.md`
- `设定集/女主卡.md`
- `设定集/反派设计.md`
- `设定集/世界观.md`
- `设定集/力量体系.md`
- `设定集/主角卡.md`
- `.ink/idea_bank.json` (inherit constraints)
- `.ink/golden_three_plan.json`（**必须**，若 `progress.current_volume == 1` 且 `chapters["1"].ch1_cool_point_spec` 为空 → hard fail，要求先运行 `/ink-init` 补齐）

If 总纲.md lacks volume ranges / core conflict / climax, ask the user to fill those before proceeding.

### 已写正文回顾（当 `progress.current_chapter > 0` 时必须执行）

> 当项目已有已写正文时，大纲规划必须参考实际写作成果，避免新卷大纲与已写内容脱节。

**触发条件**：`state.json` 中 `progress.current_chapter > 0`（即至少写过1章正文）。第1卷首次规划时跳过此步。

**必须加载的已写成果**：

1. **章节摘要**（了解已发生的所有事件）：
   ```bash
   # 读取最近 10 章摘要（或全部摘要，取较少者）
   ls "$PROJECT_ROOT/.ink/summaries/" | tail -10 | while read f; do cat "$PROJECT_ROOT/.ink/summaries/$f"; echo "---"; done
   ```

2. **角色当前状态**（了解角色在正文中的实际发展）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" index query-entities --type character --limit 20
   ```

3. **未闭合伏笔与钩子**（了解哪些线索必须在后续卷中回收）：
   ```bash
   python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${PROJECT_ROOT}" state get-open-threads
   ```

4. **上一卷末章摘要**（了解衔接点）：
   ```bash
   # 读取上一卷最后一章的摘要
   cat "$PROJECT_ROOT/.ink/summaries/ch$(printf '%04d' ${last_volume_end_chapter}).md"
   ```

**以上数据的使用规则**：
- 新卷大纲必须**承接**已写正文中的角色状态、关系变化、未闭合伏笔，不得与之矛盾。
- 若总纲中对本卷的设想与已写正文发展出现冲突，以**已写正文为准**——列出冲突项并提示用户，建议更新总纲后再继续。
- 未闭合伏笔中标记为 P0（紧迫）的线索，必须在新卷大纲中安排回收章节。
- 角色状态查询结果中的能力/关系/认知，作为新卷角色行为的**起点约束**。

## 1.5) Load propagation debts（FIX-17 P4d）

> 反向传播债务（propagation debts）由 `ink-macro-review` 的 canon-drift-detector 在每
> 50 章触发时写入 `.ink/propagation_debt.json`。本步把 **status ∈ {"open", "in_progress"}**
> （即 `ACTIVE_STATUSES`）的 debts 作为本轮规划的**硬约束**注入。

**触发条件**：`.ink/propagation_debt.json` 存在且含 active 条目。若文件不存在或全部已
`resolved` / `wont_fix`，直接跳过本步。

**加载方式（示例 Python 片段）**：
```python
from ink_writer.propagation import (
    filter_debts_for_range,
    load_active_debts,
    mark_debts_resolved,
    render_debts_for_plan,
)

active_debts = load_active_debts(PROJECT_ROOT)
# 新卷规划：把 target_chapter 落在本卷章节区间内的 debts 作为必须消化项
consumable = filter_debts_for_range(active_debts, volume_start_ch, volume_end_ch)
print(render_debts_for_plan(consumable))  # 注入 planner 提示
```

**规划硬约束**：
- `consumable` 中每条 debt 的 `target_chapter` 必须在本次生成/修订的章纲里得到显式处
  理：或加伏笔、或补前情、或调整节拍，不得忽略。
- 章纲（chapter plan）顶部必须列出 `consumed_debt_ids: [DEBT-xxx, ...]`，覆盖所有本轮
  被消化的 debt_id。
- 无法在本卷消化的 debts（target_chapter 超出本卷范围）保留 active，留给未来 plan 迭代
  处理；本步**不得**把它们提前翻转为 resolved。

**Step 8（Validate + save）里必须做的收尾**：
```python
mark_debts_resolved(PROJECT_ROOT, consumed_debt_ids)
```
仅在章纲落盘成功后调用，确保只有真正被消化的 debts 状态从 `open` / `in_progress`
翻转为 `resolved`。状态翻转幂等，重复调用安全。

## 2) Build setting baseline from 总纲 + 世界观
目标：在不推翻现有内容的前提下，让设定集从“骨架模板”进入“可规划可写作”的基线状态。

输入来源：
- `大纲/总纲.md`
- `设定集/世界观.md`
- `设定集/力量体系.md`
- `设定集/主角卡.md`
- `设定集/反派设计.md`

执行规则（必须）：
- 只做增量补齐，不清空、不重写整文件。
- 优先补齐“可执行字段”：角色定位、势力关系、能力边界、代价规则、反派层级映射。
- 若总纲与现有设定冲突，先列冲突并阻断，等待用户裁决后再改。

基线补齐最小要求：
- `设定集/世界观.md`：世界规则边界、社会结构、关键地点用途。
- `设定集/力量体系.md`：境界链/能力限制/代价与冷却。
- `设定集/主角卡.md`：欲望、缺陷、初始资源与限制。
- `设定集/反派设计.md`：小/中/大反派层级与主角镜像关系。

## 3) Select volume
- Offer choices from 总纲.md (卷名 + 章节范围).
- Confirm any special requirement (tone, POV emphasis, romance, etc.).
If 总纲缺少卷名/章节范围/核心冲突/卷末高潮，先补问并更新总纲，再继续。

### 结局卷检测
读取 `state.json` → `project_info.volumes`，判断当前选择的卷是否标记为 `is_final: true`。

**如果是结局卷**，后续规划必须额外满足：
1. **收线章**（至少 1 章）：回收本书所有主要伏笔和角色弧光
2. **决战/高潮章**（至少 1-2 章）：主线核心冲突的终极对决
3. **尾声章**（最后 1 章）：角色归宿、世界状态、情感收束
4. 最后一章的章纲额外标记 `- is_finale: true`
5. 最后一章不设悬念钩子（仅设开放式余韵或情感收束钩）
6. 节拍表第 6 段"新钩子"改为"全书收束"（不引入下一卷承诺）

## 4) Generate volume beat sheet (节拍表)
目标：先把本卷“承诺→危机递增→中段反转→最低谷→大兑现+新钩子”钉死，避免卷中段漂移。

Load template:
```bash
cat "${SKILL_ROOT}/../../templates/output/大纲-卷节拍表.md"
```

Must satisfy (hard requirements):
- **中段反转（必填）**：不得留空；若无，写 `无（理由：...）`
- **危机链**：至少 3 次递增（表格 1-3 行不得空）
- **卷末新钩子**：必须能落到”最后一章的章末未闭合问题”
- **已写成果承接**（当有已写正文时）：节拍表的起始状态必须与上一卷末章摘要中的角色状态、场景位置、未闭合问题一致；P0 伏笔必须在节拍表中标注回收位置
- **爽点链规划**：第 7 段至少填写 2 个爽点链（PC-1, PC-2），每个需完整填写铺垫章→压迫章→爆发章路径、信息差设计、预期读者情绪
- **爽点前置原则**（hard requirements）：
  - **PC-1 爆发章锁定第 1 章**：第 1 卷的 PC-1 必须在第 1 章完成首次爽点交付（即本卷第 1 章的压扬标记=扬，且爆发章号=1），不允许延后到第 2/3 章；后续卷 PC-1 爆发章仍不得晚于该卷第 3 章（US-004 收紧）
  - 前 3 章每章必须规划至少 1 个大卖点 + 2 个小卖点（与章纲卖点字段对齐）
  - 前 3 章的 `压扬标记` 不能全部为"压"，至少有 1 章为"扬"（保证读者在前3章内获得至少一次爽感释放）
  - 违反以上任一规则 → hard fail，阻断进入 Step 5

Write output:
```bash
cat > "$PROJECT_ROOT/大纲/第${volume_id}卷-节拍表.md" <<'EOF'
{beat_sheet_content}
EOF
```

Completion criteria:
- `大纲/第{volume_id}卷-节拍表.md` 存在且非空
- Step 4/5 能直接引用 Catalyst / 中段反转 / 最低谷 / 大兑现 / 新钩子来锚定节奏

## 4.5) Generate volume timeline (时间线表)

目标：为本卷建立时间轴基准，确保章节间时间推进逻辑自洽，避免"第一章灾变第二章火拼"的时间跳跃问题。

Load template:
```bash
cat "${SKILL_ROOT}/../../templates/output/大纲-卷时间线.md"
```

Must satisfy (hard requirements):
- **时间基准（必填）**：明确本卷使用的时间体系（末世第X天/仙历年月/现代日期）
- **本卷时间跨度（必填）**：本卷覆盖的时间范围
- **关键倒计时事件**：若有时限性事件（物资耗尽/大比开始/截止日期），必须列出并标注 D-N

Write output:
```bash
cat > "$PROJECT_ROOT/大纲/第${volume_id}卷-时间线.md" <<'EOF'
{timeline_content}
EOF
```

Completion criteria:
- `大纲/第{volume_id}卷-时间线.md` 存在且非空
- 时间基准和本卷跨度已明确
- 若存在倒计时事件，已在表中列出

## 5) Generate volume skeleton
Load genre profile and apply standards:
```bash
cat "${SKILL_ROOT}/../../references/genre-profiles.md"
cat "${SKILL_ROOT}/../../references/shared/strand-weave-pattern.md"
```

Optional (only if爽点结构需要细化):
```bash
cat "${SKILL_ROOT}/../../references/shared/cool-points-guide.md"
```

Optional (only if需要补强卷级冲突链与强度分层):
```bash
cat "${SKILL_ROOT}/references/outlining/conflict-design.md"
```

Load beat sheet (must exist):
```bash
cat "$PROJECT_ROOT/大纲/第{volume_id}卷-节拍表.md"
```

Extract for current genre:
- Strand 比例（Quest/Fire/Constellation）
- 爽点密度标准（每章最低/推荐）
- 钩子类型偏好

### Strand Weave 规划策略
Based on genre profile, distribute chapters:
- **Quest Strand** (主线推进): 55-65% 章节
  - 目标明确、进展可见、有阶段性成果
  - 例：突破境界、完成任务、获得宝物
- **Fire Strand** (情感/关系): 20-30% 章节
  - 人物关系变化、情感冲突、团队动态
  - 例：与女主互动、师徒矛盾、兄弟背叛
- **Constellation Strand** (世界/谜团): 10-20% 章节
  - 世界观揭示、伏笔埋设、谜团推进
  - 例：发现古老秘密、揭示反派阴谋、世界真相

**Weaving pattern** (recommended):
- 每 3-5 章切换主导 Strand
- 高潮章节可多 Strand 交织
- 卷末 3-5 章集中 Quest Strand

For 电竞/直播文/克苏鲁, apply dedicated volume pacing template:
```bash
cat "${SKILL_ROOT}/references/outlining/genre-volume-pacing.md"
```

### Strand 阈值自动校验

> 在生成卷级 Strand 规划表时，必须根据题材 Profile 自动校验阈值，不允许用户在不知情的情况下偏离题材推荐值。

**执行流程**：
1. 从 `state.json.project_info.genre` 读取当前题材
2. 从 `genre-profiles.md` 查出对应题材的 pacing_config：
   - `quest_max_consecutive`：Quest 最大连续章数
   - `fire_max_gap`：Fire 最大断档章数
   - `constellation_max_gap`：Constellation 最大断档章数
3. 在规划表中，对每个卷的 Strand 分布进行检查：
   - 若 Quest 连续章数 > `quest_max_consecutive` → 输出警告：`"⚠️ 第{X}-{Y}章连续 Quest {N} 章，超过题材建议的 {max} 章"`
   - 若 Fire 断档 > `fire_max_gap` → 输出警告：`"⚠️ 第{X}章后 Fire 断档 {N} 章，超过题材建议的 {max} 章"`
   - 若 Constellation 断档 > `constellation_max_gap` → 同上
4. 若存在警告，使用 AskUserQuestion 确认：`"以上 Strand 分布偏离题材推荐值，是否确认？(Y/调整)"`
5. 若用户确认，记录为 Override（带理由）；若用户选择调整，重新规划对应章节

**各题材参考阈值**：

| 题材 | Quest最大连续 | Fire最大断档 | Constellation最大断档 |
|------|-------------|-------------|---------------------|
| 爽文 | 5章 | 8章 | 12章 |
| 修仙 | 6章 | 12章 | 15章 |
| 言情 | 4章 | 5章 | 15章 |
| 悬疑 | 5章 | 10章 | 10章 |
| 都市 | 4章 | 6章 | 10章 |
| 规则怪谈 | 5章 | 10章 | 8章 |
| 知乎短篇 | 3章 | 3章 | 5章 |

### 长篇专用 Strand 占比（计划总章数 > 100 章时启用）

| 阶段 | Quest | Fire | Constellation | 说明 |
|------|-------|------|---------------|------|
| 前 30 章 | 60-70% | 20-25% | 10-15% | 快速建立主线，密集推进 |
| 31-100 章 | 50-60% | 20-30% | 15-25% | 逐步展开副线，深化世界观 |
| 101-200 章 | 45-55% | 20-30% | 20-30% | 三线均衡，防止主线单调 |
| 200 章+ | 50-60% | 15-25% | 20-30% | 收束副线，聚焦主线收尾 |

与标准占比的区别：中期 Constellation 提升到 20-30% 避免世界观展开不足；后期 Fire 略降聚焦收尾。

### 卷级黄金三章规则（多卷长篇，第 2 卷起生效）

| 章节位置 | 要求 | 检查项 |
|---------|------|--------|
| 卷首第 1 章 | 强触发 + 承接上卷 | 前 300 字必须有引发好奇的事件；必须回应上卷末尾钩子 |
| 卷首第 2 章 | 新卷目标明确化 | 本卷核心冲突/目标必须在前 500 字内清晰呈现 |
| 卷首第 3 章 | 首个小闭环 | 必须完成一个小事件的闭环，证明"新卷值得追读" |

执行方式：ink-write Step 1 加载 Context 时，若检测到当前章节为某卷的前 3 章，自动标注"卷级黄金三章模式"，Step 3 审查时 golden-three-checker 的精简版规则生效。

### 长篇检查点（每 25 章自动触发）

> 适用于 50 章以上的长篇项目。

**检查点章节**：第 25、50、75、100、125... 章

| 检查项 | 执行方式 | 失败处理 |
|--------|---------|---------|
| Strand 平衡审计 | 统计过去 25 章的 Quest/Fire/Constellation 占比 | 偏差 >15% → high 警告 |
| 伏笔回收进度 | 列出所有 planted 状态伏笔，标注预期回收章节 | 逾期伏笔 → high 警告 |
| 债务清算 | 列出所有 active/overdue 的 Override Contract | overdue 债务 → 强制处理 |
| 角色出场审计 | 统计所有"重要角色"的最近出场章节 | >30 章未出场 → medium 警告 |
| 主线进度 | 对照卷纲，评估主线推进是否达标 | 进度偏差 >20% → high 警告 |

---

### 卖点密度规划策略
每章硬约束：1 个大卖点 + 2 个小卖点（全部必填）

Based on genre profile:
- **常规章节**: 大卖点强度=minor + 2 个小卖点
- **关键章节**: 大卖点强度=combo + 2 个小卖点
- **高潮章节**: 大卖点强度=milestone + 2-3 个小卖点

**大卖点类型合法列表**：装逼打脸/扮猪吃虎/越级反杀/打脸权威/反派翻车/甜蜜超预期/迪化误解/身份掉马/能力升级/关键情报获取/危机逆转
**小卖点类型合法列表**：微兑现(信息/关系/能力/资源/认可/情绪/线索)/角色魅力展示/世界观趣味细节/关系推进/小悬念设置/能力小应用
**去重规则**：大卖点类型不得与前 3 章重复同一类型

**Distribution rule**:
- 每 5-8 章至少 1 个关键章节（强度=combo）
- 每卷至少 1 个高潮章节（强度=milestone，通常在卷末）

### 约束触发规划策略
If idea_bank.json exists:
```bash
cat "$PROJECT_ROOT/.ink/idea_bank.json"
```

Calculate trigger frequency:
- **反套路规则**: 每 N 章触发 1 次
  - N = max(5, 总章数 / 10)
  - 例：50 章卷 → 每 5 章触发
  - 例：100 章卷 → 每 10 章触发
- **硬约束**: 贯穿全卷，在章节目标/爽点设计中体现
- **主角缺陷**: 每卷至少 2 次成为冲突来源
- **反派镜像**: 反派出场章节必须体现镜像对比

Use this template and fill from 总纲 + idea_bank:

```markdown
# 第 {volume_id} 卷：{卷名}

> 章节范围: 第 {start} - {end} 章
> 核心冲突: {conflict}
> 卷末高潮: {climax}

## 卷摘要
{2-3 段落概述}

## 关键人物与反派
- 主要登场角色：
- 反派层级：

## Strand Weave 规划
| 章节范围 | 主导 Strand | 内容概要 |
|---------|------------|---------|

## 卖点密度规划
| 章节 | 大卖点类型 | 大卖点描述(≤80字) | 小卖点1 | 小卖点2 | 强度 |
|------|-----------|-------------------|---------|---------|------|

## 爽点链与章节压扬标记

基于节拍表第 7 段的爽点链规划，为每章分配压扬标记：
- **压**：铺垫/压迫阶段，积蓄读者期待，主角受挫/被轻视/面临困境
- **平**：日常/过渡，但需维持微兑现（信息/关系/能力的小进展）
- **扬**：爆发/释放阶段，集中兑现爽点，逆袭打脸/越级反杀/身份揭露

**验证规则**：
- 连续 3 章标记为"压"后，第 4 章必须为"扬"或包含微释放
- 里程碑爽点（强度=里程碑）必须有 ≥2 章铺垫
- 每个爽点链的信息差字段不得留空（可填"无信息差"但需说明理由）
- 爽点链的爆发章必须与对应章纲的压扬标记=扬一致
- **爽点前置**：前 3 章压扬标记不能全为"压"，至少 1 章为"扬"；PC-1 爆发章 ≤ 第 3 章

## 伏笔规划
| 章节 | 操作 | 伏笔内容 |
|------|------|---------|

## 约束触发规划（如有）
- 反套路规则：每 N 章触发一次
- 硬约束：贯穿全卷
```

## 6) Generate chapter outlines (batched)
Batching rule:
- ≤20 章：1 批
- 21–40 章：2 批
- 41–60 章：3 批
- >60 章：4+ 批

Optional (only if需要钩子/节奏细分):
```bash
cat "${SKILL_ROOT}/../../references/reading-power-taxonomy.md"
```

Optional (only if需要章节微结构/标题策略细化):
```bash
cat "${SKILL_ROOT}/references/outlining/chapter-planning.md"
```

### Chapter generation strategy
For each chapter, determine:

**1. Strand assignment** (follow volume skeleton distribution)
- Quest: 主线任务推进、目标达成、能力提升
- Fire: 人物关系、情感冲突、团队动态
- Constellation: 世界揭示、伏笔埋设、谜团推进

**2. 爽点设计** (based on Strand and position)
- Quest Strand → 成就爽点（打脸、逆袭、突破）
- Fire Strand → 情感爽点（认可、保护、告白）
- Constellation Strand → 认知爽点（真相、预言、身份）

**2.4 伏笔生命周期调度** (hard constraint from thread-lifecycle-tracker[foreshadow])
- 调用 `ink_writer.foreshadow.tracker.scan_foreshadows()` 获取逾期/沉默伏笔
- 调用 `ink_writer.foreshadow.tracker.build_plan_injection()` 获取强制兑现列表
- 输入：index.db 路径, 当前章号
- 输出：{forced_payoffs, mode, alerts, total_active, total_overdue, total_silent}
- **硬约束**：`mode == "force"` 时，`forced_payoffs` 中的伏笔**必须**在本批大纲中安排兑现章节
- 每章最多安排 2 条强制兑现（`max_forced_payoffs_per_chapter`）
- 将 `alerts` 列表注入到章纲注释中，便于 writer-agent 理解伏笔紧迫度

**2.5 爽点节奏调度** (hard constraint from high_point_scheduler)
- 调用 `ink_writer.pacing.high_point_scheduler.schedule_high_point()` 获取本章大卖点配方
- 输入：chapter_no, volume_position (0.0-1.0), last_5_chapter_high_points
- 输出：{high_point_type, intensity, payoff_window, require_high_point, rationale}
- **硬约束**：require_high_point=true 的章节**必须**包含对应 intensity 级别的爽点
- intensity 映射：minor=小爽点(单一模式), combo=组合爽点(2模式叠加), milestone=里程碑爽点(改变主角地位)
- high_point_type（大卖点类型）映射：装逼打脸/扮猪吃虎/越级反杀/打脸权威/反派翻车/甜蜜超预期/迪化误解/身份掉马/能力升级/关键情报获取/危机逆转
- 将调度器输出的 rationale 附加到大纲注释中，便于 writer-agent 理解意图

**2.7 明暗线生命周期调度** (hard constraint from thread-lifecycle-tracker[plotline])
- 调用 `ink_writer.plotline.tracker.scan_plotlines()` 获取断更线程
- 调用 `ink_writer.plotline.tracker.build_plan_injection()` 获取强制推进列表
- 输入：index.db 路径, 当前章号
- 输出：{forced_advances, mode, alerts, total_active, total_inactive}
- **硬约束**：`mode == "force"` 时，`forced_advances` 中的线程**必须**在本批大纲中安排推进章节
- 每章最多安排 2 条强制推进（`max_forced_advances_per_chapter`）
- 将 `alerts` 列表注入到章纲注释中，便于 writer-agent 理解线程紧迫度
- 线型阈值：main=3章断更, sub=8章, dark=15章

**2.6 爽点执行剧本** (based on 节拍表爽点链规划 + 调度器配方)
- 检查本章所属的爽点链（PC-X），确定本章角色（铺垫/压迫/爆发）
- 填写**压扬标记**：压/平/扬
- 填写**爽点执行**字段：
  - 铺垫来源：引用哪章埋的铺垫，或本章新起
  - 信息差：读者知道什么但角色不知道什么（无则注明理由）
  - 预期读者情绪：解气/震撼/热血/紧张/优越感等
- **爆发章（压扬标记=扬）**：大卖点描述必须写明"谁→做什么→对象反应→围观反应"（≤80字）
- **压迫章（压扬标记=压）**：大卖点描述聚焦"对手/困境如何压迫主角"
- **过渡章（压扬标记=平）**：大卖点描述聚焦"微兑现类型"
- **所有章节**：必须填写2个小卖点（各≤40字），类型从小卖点类型列表中选取

**3. 钩子设计** (based on next chapter's Strand)
- 悬念钩子：提出问题、制造危机
- 承诺钩子：预告奖励、暗示转折
- 情感钩子：关系变化、角色危机

**4. 反派层级** (based on volume skeleton)
- 无：日常章节、修炼章节、关系章节
- 小：小冲突、小反派、局部对抗
- 中：中反派出场、重要冲突、阶段性对抗
- 大：大反派出场、核心冲突、卷级高潮

**5. 关键实体** (new or important)
- 新角色：姓名 + 一句话定位
- 新地点：名称 + 一句话描述
- 新物品：名称 + 功能
- 新势力：名称 + 立场

**6. 约束检查** (if idea_bank exists)
- 是否触发反套路规则？
- 是否体现硬约束？
- 是否展现主角缺陷？
- 是否体现反派镜像？

**7. 主角行动验证** (hard constraint)
- 每章 `主角行动` 字段必须填写（≤30字），以动词开头
- **被动描述黑名单**：`主角行动` 不能以下列动词/动词前缀开头 → hard fail：被/发现/意识到/感受到/想到/回忆/观察/注意到/看到/听到
- **推荐动词白名单**（参考 `references/shared/protagonist-action-verbs.md`）：决定/冲向/使用/对抗/说服/欺骗/逃离/交换/挑战/保护/破坏/窃取/调查/伪装/拒绝/选择/牺牲/激活/召唤/反击 等（白名单不穷举，非黑名单的主动动词均可）
- **连续重复警告**：连续 2 章 `主角行动` 的动词类型相同（如都是"调查"类）→ medium warning，建议调整

**8. 标题去重**：生成本批章节标题后，与本卷已有标题 + 前卷所有标题做精确匹配检查，发现重复则重命名（保留核心语义但添加差异化元素）。

Chapter format (include 反派层级 for context-agent):

```markdown
### 第 {N} 章：{标题}
- 目标: {20字以内}
- 阻力: {20字以内}
- 代价: {20字以内}
- 时间锚点: {末世第X天 时段/仙历X年X月X日/具体日期+时段}
- 章内时间跨度: {如 3小时/半天/1天}
- 与上章时间差: {如 紧接/6小时/1天/跨夜}
- 倒计时状态: {事件A D-3 -> D-2 / 无}
- 大卖点类型: {装逼打脸|扮猪吃虎|越级反杀|打脸权威|反派翻车|甜蜜超预期|迪化误解|身份掉马|能力升级|关键情报获取|危机逆转} | 强度={minor|combo|milestone} | 兑现窗口={1-3章}
- 大卖点描述: {≤80字，格式：谁→做什么→对象反应→围观反应}
- 小卖点: 1.{类型}-{≤40字} 2.{类型}-{≤40字}
  - 小卖点类型: {微兑现(信息/关系/能力/资源/认可/情绪/线索)|角色魅力展示|世界观趣味细节|关系推进|小悬念设置|能力小应用}
- 爽点执行: 铺垫来源:{哪章/本章} | 信息差:{读者知X但角色不知Y/无(理由)} | 预期读者情绪:{解气/震撼/热血/优越感}
- 压扬标记: {压/平/扬}
- Strand: {Quest|Fire|Constellation}
- 反派层级: {无/小/中/大}
- 视角/主角: {主角A/主角B/女主/群像}
- 关键实体: {新增或重要出场}
- 主角行动: {≤30字，动词开头的主动行为描述}
- 本章变化: {30字以内，优先可量化变化}
- 章末未闭合问题: {30字以内}
- 钩子: {类型} - {30字以内}
- 钩子契约: 类型={crisis|mystery|emotion|choice|desire} | 兑现锚点=第{M}章 | 兑现摘要={20字以内}
- 伏笔处置: {无 | 埋设:[thread_id]描述 | 推进:[thread_id]描述 | 兑现:[thread_id]描述}
- 明暗线推进: {[plotline_id]:推进描述, ... | 无}
- info_budget:
  - max_new_concepts: {整数，默认 3；第 1-3 章上限 2}
  - max_named_characters: {整数，默认 3；第 1 章上限 2}
  - setting_reveal_queue: [{priority}: {设定条目简述}, ...]  # 按优先级降序，仅本章需要揭示的设定
  - natural_delivery_hints: [{融入方式}: {一句话提示}, ...]  # 融入方式枚举：行动展示 | 对话揭示 | 后果倒推 | 误读制造 | 环境映射
```

**info_budget 字段说明（US-005）**：解决信息过载导致的"塞信息感"，强制每章信息释放按配额进行。

- **max_new_concepts**：本章最多引入的新概念/新设定数（包括功法名/组织名/地名/规则等首次出现项）。默认 3；第 1-3 章上限 2；超出则必须推迟到后续章节。
- **max_named_characters**：本章最多新出场的有名有姓角色数（不含龙套/无名群众）。默认 3；第 1 章上限 2；超出则硬阻断。
- **setting_reveal_queue**：本章计划揭示的设定条目列表，按 `priority`（1=最高）排序；超出 `max_new_concepts` 的条目必须排到后续章节的 `setting_reveal_queue`。
- **natural_delivery_hints**：每条新概念/设定的融入方式提示，要求从 5 种方式中选择：
  1. **行动展示**：通过主角/配角动作揭示（如"主角触碰石碑触发光阵"）
  2. **对话揭示**：通过角色对白自然带出（禁用"讲师式独白"）
  3. **后果倒推**：通过事件后果让读者反推机制（如"被弹开才知墙体有禁制"）
  4. **误读制造**：先给错误认知，后续反转揭示真相
  5. **环境映射**：通过环境细节暗示（如"墙上的剑痕数=历代挑战者失败次数"）
  - 禁用"纯叙述性设定解释"（连续 >50 字的第三人称说明文）

**第 1 章严格执行**（hard fail）：
- `max_new_concepts` ≤ 2，且其中 1 个槽位必须留给**金手指核心机制**
- `max_named_characters` ≤ 2（不含主角）
- `setting_reveal_queue` 首项必须是金手指相关设定，其他世界观/力量体系/反派背景等**推迟到后续章节**
- `natural_delivery_hints` 中禁止出现"纯叙述/讲解/介绍"字样，必须命中 5 种融入方式之一

黄金三章附加规则（第 1-3 章必须额外写出）：
- 本章职责：立触发 / 接钩升级 / 小闭环（按章号选择）
- 读者承诺：本章要让读者清楚感知的价值（**第 1 章必须额外包含金手指解决问题的具体承诺句 · US-004**）
- 兑现项：本章必须兑现的 1-3 个项目
- 禁止拖沓区：本章开头不能出现的慢区
- 第 1 章不允许只写”铺垫”；第 2 章不允许”重新起头”；第 3 章不允许”只铺不收”
- **第 1 章必须出现至少 2 个有名字、有态度的配角**（独角戏无法建立世界信任感）
- **第 1 章章纲必须新增字段**（US-004）：
  - `爽点闭环`: `ability_demo={事件+感官标注} → crisis_trigger={与金手指直接相关的危机} → concrete_payoff={允许列表中的具体收益}`
  - `cool_point_preview`: ≤300 字，覆盖三节拍连接点的画面蓝本

**第 1 章爽点闭环（硬约束 · US-004 强化）**：
第 1 章大纲必须额外包含以下必填节拍组 `爽点闭环` 与配套字段（数据来源：`.ink/golden_three_plan.json` → `chapters["1"].ch1_cool_point_spec`；若未生成则阻断）：

- **爽点闭环**（3 个强制节拍，缺一 → hard fail）：
  1. **ability_demo（能力展示）**：主角金手指/核心能力首次被读者看到的事件
     - **感官描写要求（必填）**：必须在章纲字段内标注至少 2 种感官通道（视觉/听觉/触觉/嗅觉/味觉）——如 `感官={视觉:金光, 听觉:轰鸣, 触觉:灼热}`；仅内心感知 / 纯视觉描写 → hard fail
     - 必须对齐 `ch1_cool_point_spec.scene_description` 中的激活场景
  2. **crisis_trigger（危机触发）**：**必须与金手指直接相关**（能力暴露 / 能力失控 / 能力被觊觎 / 能力差额引来针对 / 能力不足以解决当下困境）
     - 与金手指无直接因果的外部巧合危机（如"恰好遇到劫匪""恰好碰到陨石"而与主角能力无关）→ hard fail
  3. **concrete_payoff（具体收益）**：金手指使用后必须产出**可量化、可感知**的具体收益
     - **硬性排除词表（命中任一即 hard fail）**：理解 / 领悟 / 感悟 / 知道了 / 发现了 / 明白了 / 意识到 / 成长了 / 坚强了 / 看透了 / 释怀了 / 有了新认知
     - **允许列表（五选一必须命中 `ch1_cool_point_spec.payoff_form`）**：资源获取 / 敌人击退 / 他人认可 / 地位提升 / 信息解锁 / 危机解除
     - 与 `ch1_cool_point_spec.payoff_form` 枚举不一致 → hard fail

- **cool_point_preview**（第 1 章大纲必填，≤300 字）：以读者视角预演第 1 章爽点高潮段落的画面、对白、收益落地瞬间；必须覆盖 ability_demo → crisis_trigger → concrete_payoff 三个节拍的连接点，可直接被 writer-agent 作为画面蓝本
- **读者承诺**（第 1 章必填项升级）：除通用价值承诺外，**必须显式包含一句金手指解决问题的具体承诺**（模板："{金手指名称/代称}将帮助主角{可感知动词}{可感知对象}"，禁止"主角获得认知/成长"之类抽象句）

**Gate（阻断进入 Step 8 的保存与 Validation）**：
- `爽点闭环` 3 个节拍任一为空或不满足上述要求 → hard fail，必须重新生成第 1 章大纲
- `cool_point_preview` 缺失 / 未覆盖三节拍 / 出现硬性排除词 → hard fail
- `读者承诺` 未包含金手指具体承诺句 → hard fail
- 第 1 章的 `章末未闭合问题` 必须指向主线大冲突（不能停留在"主角在想这个能力是什么"这种探索层级）→ hard fail

（保留旧字段作为兼容映射：`爽点闭环.ability_demo` 对齐旧 `第1章闭环.能力展示`；`爽点闭环.crisis_trigger` 对齐旧 `危机`；`爽点闭环.concrete_payoff` 对齐旧 `能力收益`。旧字段仍可出现但不得与新节拍矛盾。）

**前3万字里程碑约束**（默认启用，所有项目生效）：

起点编辑在3万字（~12章）时做正式评估。前12章大纲**必须**满足以下里程碑：
- ch1: 能力展示 + 首次危机 + **能力产生具体收益（完整小闭环）**+ 至少2个有温度的配角
- ch2: 第一个小胜利 + 重要配角出场 + **主线冲突方向明确**
- ch3: 第一个完整小高潮 + **读者已知道”这本书要讲什么”**
- ch4-5: 世界观通过行动展开（非讲述）
- ch6-10: 第一个完整对决 + 长线冲突确立
若里程碑缺失，标记 `high` 并建议调整大纲。

**audit_mode 配置**（读取自 `state.json` 的 `audit_mode` 字段）：
- `”normal”`（默认）：启用上述全部里程碑约束（= 原”审核优化模式”的 strict 级别）
- `”strict”`：在 normal 基础上，里程碑缺失从 `high` 升级为 `critical`（hard block）
- `”relaxed”`：降级回旧标准（ch1-2 合并、ch10-12 合并、不强制闭环），仅标记 `medium` 建议
若 `state.json` 中未设置 `audit_mode`，默认为 `”normal”`。

参考：`references/shared/golden-opening-patterns.md`、`references/shared/commercial-packaging.md`

**时间字段说明**：
- **时间锚点**：本章发生的具体时间点，必须与时间线表一致
- **章内时间跨度**：本章内容覆盖的时间长度
- **与上章时间差**：与上一章结束时间的间隔
  - 紧接：无时间间隔，直接承接
  - 跨夜：过夜但不超过 12 小时
  - 具体时长：如 6小时、1天、3天
- **倒计时状态**：若存在倒计时事件，标注推进情况（D-N → D-(N-1)）

**字段说明**：
- **章末未闭合问题**：本章结尾必须保留的“未闭合决策/问题”，用于驱动读者点下一章。
  - 规则：必须与 **钩子** 的类型/强度一致；不得出现“钩子很强但问题很虚”的错配。
- **钩子**：本章应设置的章末钩子（规划用）
  - 例：悬念钩 - 神秘人身份即将揭晓
  - 意思是：本章结尾要设置这个悬念钩子
  - 下章 context-agent 会读取 chapter_meta[N].hook（实际实现的钩子），生成"接住上章"指导
  - 钩子类型参考：悬念钩 | 危机钩 | 承诺钩 | 情绪钩 | 选择钩 | 渴望钩
- **钩子契约**：可验证的钩子承诺（硬约束）。
  - `类型`：必须是 crisis/mystery/emotion/choice/desire 之一（对齐 `data/hook_patterns.json` 分类）
  - `兑现锚点`：该钩子预期在哪一章兑现（可以是本章或后续章号）
  - `兑现摘要`：20 字以内描述兑现内容
  - 用于前置约束 + 后置校验闭环：reader-pull-checker 会验证兑现是否达成

Save after each batch:
```bash
cat >> "$PROJECT_ROOT/大纲/第${volume_id}卷-详细大纲.md" <<'EOF'
{batch_content}
EOF
```

### 批次间衔接校验（每批保存后必做）

> 防止分批生成时出现"上批末章钩子 → 下批首章回应"的断裂。

**校验时机**：第 2 批及之后的每批生成前，必须先校验与上一批的衔接。

**校验项目**：

| 校验项 | 规则 | 失败处理 |
|--------|------|---------|
| 钩子承接 | 上批末章的 `章末未闭合问题` 和 `钩子` 必须在下批首章的 `目标` 或专项字段中有明确回应 | 修改下批首章章纲，补充回应 |
| 时间连续 | 上批末章的 `时间锚点` + `章内时间跨度` 与下批首章的 `与上章时间差` + `时间锚点` 必须算术一致 | 修正时间字段 |
| Strand 延续 | 若上批末章为 Quest 且连续 Quest 已达 3+章，下批首章建议切换 Strand | 输出警告，由用户决定 |
| 反派层级衔接 | 上批末章若引入中/大反派且未闭合，下批首章不得跳过该反派线 | 修改下批首章关键实体 |
| 角色状态一致 | 上批末章的 `本章变化` 造成的角色状态变更，必须反映在下批首章的角色前提中 | 补充角色状态说明 |
| 标题唯一性 | 本批所有章节标题不得与已有（本卷+前卷）章节标题重复 | 重命名重复标题，保留核心语义但添加差异化元素 |

**执行方式**：
1. 读取上批最后一章的章纲（末章的全部字段）
2. 读取下批第一章的章纲（首章的全部字段）
3. 逐项对照上表执行校验
4. 若存在 `钩子承接` 或 `时间连续` 失败 → 必须修正后才能继续生成下一批
5. 其他项失败 → 输出警告，可由用户决定是否修正

## 7) Enrich existing setting files from volume outline
目标：卷纲写完后，把本卷新增事实写回“现有设定集文件”，确保后续写作可直接读取。

输入来源：
- `大纲/第{volume_id}卷-节拍表.md`
- `大纲/第{volume_id}卷-详细大纲.md`
- 现有设定集文件（世界观/力量体系/主角卡/主角组/女主卡/反派设计）

写回策略（必须）：
- 仅增量补充相关段落，不覆盖整文件。
- 新增角色：写入对应角色卡或角色组条目（含首次出场章、关系、红线）。
- 新增势力/地点/规则：写入世界观或力量体系对应章节。
- 新增反派层级信息：写入反派设计并保持小/中/大层级一致。

冲突处理（硬规则）：
- 若卷纲新增信息与总纲或已确认设定冲突，标记 `BLOCKER` 并停止 state 更新。
- 只有冲突裁决完成后，才允许继续更新设定并进入保存步骤。

## 8) Validate + save
### Validation checks (must pass all)

**1. 卖点密度检查**
- 每章必须有 1 个大卖点（`大卖点类型` 非空 + `大卖点描述` ≤80字且非空） → 缺失则 hard fail
- 每章必须有 ≥2 个小卖点（`小卖点` 字段包含 2 条） → 数量<2 则 hard fail
- 大卖点类型不得与前 3 章重复同一类型 → 重复则 hard fail
- 每 5-8 章至少 1 个关键章节（强度=combo 或 milestone）
- 每卷至少 1 个高潮章节（强度=milestone）

**1.5 爽点链完整性检查**
- 节拍表中每个爽点链的爆发章，在章纲中必须有对应（压扬标记=扬）
- 连续 3 章压扬标记为"压"后，第 4 章必须为"扬"或包含微释放
- 里程碑爽点链的铺垫章数 ≥ 2
- 每个爽点链的信息差字段不得留空
- 章纲中"爽点执行"的铺垫来源引用的章号必须在本卷范围内或为已写章节
- 爽点链的爆发章号必须与对应章纲的压扬标记=扬一致（交叉校验，不一致则 hard fail）

**1.6 爽点前置检查**（节拍表→章纲交叉校验）
- 节拍表 PC-1 爆发章不得晚于本卷第 3 章 → 违反则 hard fail
- 前 3 章每章必须有 1 个大卖点 + 2 个小卖点（章纲字段非空） → 缺失则 hard fail
- 前 3 章压扬标记不能全部为"压"，至少 1 章为"扬" → 违反则 hard fail

**1.7 第1章爽点闭环检查（US-004 强化）**
- 第 1 章大纲必须包含 `爽点闭环` 节拍组 → 缺失则 hard fail
- `爽点闭环` 的三个节拍（ability_demo / crisis_trigger / concrete_payoff）任一为空 → hard fail
- `ability_demo` 未标注 ≥2 种感官通道（视觉/听觉/触觉/嗅觉/味觉）→ hard fail
- `crisis_trigger` 与金手指无直接因果关系（外部巧合/与能力无关的突发事件）→ hard fail
- `concrete_payoff` 命中硬性排除词（理解/领悟/感悟/知道了/发现了/明白了/意识到/成长了/坚强了/看透了/释怀了/有了新认知）→ hard fail
- `concrete_payoff` 未命中允许列表（资源获取/敌人击退/他人认可/地位提升/信息解锁/危机解除），或与 `ch1_cool_point_spec.payoff_form` 不一致 → hard fail
- 第 1 章必填字段 `cool_point_preview` 缺失 / 字符数 >300 / 未覆盖三节拍 → hard fail
- 第 1 章 `读者承诺` 未显式包含金手指解决问题的具体承诺句（形如"{金手指}将帮助主角{动词}{对象}"）→ hard fail
- 第 1 章 `章末未闭合问题` 必须指向主线大冲突，不能是"主角在探索能力""主角在思考"等探索层级 → hard fail
- 兼容项：若大纲仍带旧 `第1章闭环` 字段，其三子字段必须与新 `爽点闭环` 节拍内容一致，不一致则 hard fail

**1.75 信息释放配额检查（US-005 info_budget）**
- 每章必须包含 `info_budget` 区块 → 缺失则 hard fail
- `info_budget.max_new_concepts` 必须为正整数；第 1-3 章 >2 → hard fail；其他章节 >5 → medium warning
- `info_budget.max_named_characters` 必须为正整数；第 1 章 >2 → hard fail；其他章节 >5 → medium warning
- `setting_reveal_queue` 长度 > `max_new_concepts` → hard fail（配额超支）
- `natural_delivery_hints` 中任一条未命中 5 种融入方式枚举（行动展示/对话揭示/后果倒推/误读制造/环境映射）→ hard fail
- 第 1 章 `setting_reveal_queue` 首项不包含金手指相关关键词 → hard fail
- 第 1 章 `natural_delivery_hints` 出现"纯叙述/讲解/介绍/设定解释"等裸叙述标记词 → hard fail
- 交叉一致性：`关键实体` 中新角色数量 > `max_named_characters` → hard fail

**1.8 主角行动检查**
- 每章 `主角行动` 字段必须非空且 ≤30 字 → 缺失或超长则 hard fail
- `主角行动` 必须以主动动词开头，不得以被动描述黑名单动词开头（被/发现/意识到/感受到/想到/回忆/观察/注意到/看到/听到）→ 违反则 hard fail
- 连续 2 章 `主角行动` 的动词类型相同 → medium warning（标记但不阻断）

**2. Strand 比例检查**
Count chapters by Strand and compare with genre profile:
- Quest: 应占 55-65%
- Fire: 应占 20-30%
- Constellation: 应占 10-20%

If deviation > 15%, adjust chapter assignments.

**3. 总纲一致性检查**
- 卷核心冲突是否贯穿章节？
- 卷末高潮是否在最后 3-5 章体现？
- 关键人物是否按计划登场？

**4. 约束触发频率检查** (if idea_bank exists)
- 反套路规则触发次数 ≥ 总章数 / N（N = max(5, 总章数/10)）
- 硬约束在至少 50% 章节中体现
- 主角缺陷至少 2 次成为冲突来源
- 反派镜像在反派出场章节中体现

**5. 完整性检查**
Every chapter must have:
- 目标（20 字以内）
- 阻力（20 字以内）
- 代价（20 字以内）
- 时间锚点（必填）
- 章内时间跨度（必填）
- 与上章时间差（必填）
- 倒计时状态（若有倒计时事件则必填）
- 大卖点类型 + 大卖点描述（≤80字，谁→做什么→对象反应→围观反应）
- 小卖点（2个，各≤40字，含类型标签）
- 爽点执行（铺垫来源 + 信息差 + 预期读者情绪）
- 压扬标记（压/平/扬）
- Strand（Quest/Fire/Constellation）
- 反派层级（无/小/中/大）
- 视角/主角
- 关键实体（至少 1 个）
- 主角行动（≤30字，主动动词开头，非被动描述黑名单）
- 本章变化（30 字以内）
- 章末未闭合问题（30 字以内）
- 钩子（类型 + 30 字描述）
- 第 1-3 章额外必须有：本章职责 / 读者承诺 / 兑现项 / 禁止拖沓区
- 第 1 章额外必须有：`爽点闭环`（ability_demo + 感官×≥2 / crisis_trigger 与金手指直接相关 / concrete_payoff 命中允许列表）、`cool_point_preview`（≤300 字覆盖三节拍）、读者承诺含金手指具体承诺句（US-004）

**6. 时间线一致性检查（新增）**
- 时间线表文件存在：`大纲/第{volume_id}卷-时间线.md`
- 所有章节时间锚点已填写
- 时间单调递增（不得回跳，除非明确标注为闪回）
- 倒计时推进正确（D-5 → D-4 → D-3，不得跳跃）
- 大跨度时间跳跃（>3天）必须有过渡章说明或明确标注

**7. 设定补全检查**
- 本卷涉及的新角色/势力/规则已回写到现有设定集文件
- 所有新增条目可回溯到本卷章纲章节
- `BLOCKER` 数量为 0；若 >0，必须先裁决，不得进入 state 更新

Update state (include chapters range):
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" update-state -- \
  --volume-planned {volume_id} \
  --chapters-range "{start}-{end}"
```

Final check:
- 节拍表文件已写入：`大纲/第{volume_id}卷-节拍表.md`
- 时间线表文件已写入：`大纲/第{volume_id}卷-时间线.md`
- 章纲文件已写入：`大纲/第{volume_id}卷-详细大纲.md`
- 设定集已完成基线补齐与本卷增量补充（原文件内可见）
- 每章包含：目标/阻力/代价/时间锚点/章内时间跨度/与上章时间差/大卖点类型/大卖点描述/小卖点(×2)/爽点执行/压扬标记/Strand/反派层级/视角/关键实体/主角行动/本章变化/章末未闭合问题/钩子/钩子契约/伏笔处置/明暗线推进/info_budget
- **伏笔强制兑现校验**：thread-lifecycle-tracker 的 `forced_payoffs` 中每条伏笔必须在本卷章纲中至少有一章标注 `伏笔处置: 兑现:[thread_id]`；缺失则 hard fail
- **明暗线强制推进校验**：thread-lifecycle-tracker 的 `forced_advances` 中每条线程必须在本卷章纲中至少有一章标注 `明暗线推进: [plotline_id]:推进描述`；缺失则 hard fail
- 时间线单调递增，倒计时推进正确
- 与总纲冲突/高潮一致，约束触发频率合理（如有 idea_bank）

### Hard fail conditions (must stop)
- 节拍表文件不存在或为空
- 节拍表中段反转缺失（未按“必填/无（理由）”规则填写）
- **时间线表文件不存在或为空**
- 章纲文件不存在或为空
- 任一章节缺少：目标/阻力/代价/时间锚点/章内时间跨度/与上章时间差/大卖点类型/大卖点描述/小卖点(×2)/爽点执行/压扬标记/Strand/反派层级/视角/关键实体/主角行动/本章变化/章末未闭合问题/钩子/钩子契约/伏笔处置/明暗线推进/info_budget
- **大卖点描述缺失或超过80字** → hard fail
- **小卖点数量<2** → hard fail
- **大卖点类型与前3章重复同一类型** → hard fail
- **大卖点类型不在合法列表内**（合法：装逼打脸/扮猪吃虎/越级反杀/打脸权威/反派翻车/甜蜜超预期/迪化误解/身份掉马/能力升级/关键情报获取/危机逆转） → hard fail
- **主角行动缺失或超长**：`主角行动` 字段为空或超过30字 → hard fail
- **主角行动为被动描述**：`主角行动` 以被动描述黑名单动词开头（被/发现/意识到/感受到/想到/回忆/观察/注意到/看到/听到）→ hard fail
- **钩子契约缺失或格式错误**：每章必须有 `钩子契约: 类型=X | 兑现锚点=第M章 | 兑现摘要=Y`，类型必须在 {crisis, mystery, emotion, choice, desire} 内
- 爽点链的爆发章号与对应章纲的压扬标记不一致（交叉校验失败）
- **节拍表 PC-1 爆发章晚于本卷第 3 章**（爽点前置原则违反）
- **前 3 章中任一章缺少大卖点或小卖点 < 2**（爽点前置原则违反）
- **前 3 章压扬标记全部为"压"（无"扬"章）**（爽点前置原则违反）
- 第 1-3 章缺少：本章职责/读者承诺/兑现项/禁止拖沓区
- **第 1 章缺少 `爽点闭环` 节拍组**（US-004 爽点闭环违反）
- **第 1 章 `爽点闭环` 三节拍（ability_demo/crisis_trigger/concrete_payoff）任一为空**（US-004 爽点闭环违反）
- **第 1 章 `ability_demo` 感官通道 <2 种**（US-004 感官要求违反）
- **第 1 章 `crisis_trigger` 与金手指无直接因果关系**（US-004 爽点闭环违反）
- **第 1 章 `concrete_payoff` 命中硬性排除词**（理解/领悟/感悟/知道了/发现了/明白了/意识到/成长了/坚强了/看透了/释怀了/有了新认知）
- **第 1 章 `concrete_payoff` 未命中允许列表**（资源获取/敌人击退/他人认可/地位提升/信息解锁/危机解除）或与 `ch1_cool_point_spec.payoff_form` 不一致
- **第 1 章缺少 `cool_point_preview` 或字符数 >300 或未覆盖三节拍**（US-004 违反）
- **第 1 章 `读者承诺` 未显式包含金手指具体承诺句**（US-004 违反）
- **第 1 章 `章末未闭合问题` 停留在探索层级而非指向主线大冲突**（爽点闭环违反）
- **`.ink/golden_three_plan.json` 缺少 `chapters["1"].ch1_cool_point_spec`**（依赖 US-003，无法执行 US-004 校验）
- **任一章节缺少 `info_budget` 区块**（US-005 违反）
- **任一章节 `info_budget.max_new_concepts` 非正整数**，或第 1-3 章 >2（US-005 违反）
- **任一章节 `info_budget.max_named_characters` 非正整数**，或第 1 章 >2（US-005 违反）
- **`setting_reveal_queue` 长度超过 `max_new_concepts`**（US-005 配额超支）
- **`natural_delivery_hints` 未命中 5 种融入方式枚举**（行动展示/对话揭示/后果倒推/误读制造/环境映射）（US-005 违反）
- **第 1 章 `setting_reveal_queue` 首项不是金手指相关设定**（US-005 第 1 章严格执行）
- **第 1 章 `natural_delivery_hints` 出现"纯叙述/讲解/介绍/设定解释"裸叙述标记**（US-005 第 1 章严格执行）
- **任一章节时间字段（时间锚点/章内时间跨度/与上章时间差）缺失**
- **时间回跳且未标注为闪回**
- **倒计时算术冲突（如 D-5 直接跳到 D-2）**
- **重大事件发生时间与前章间隔不足且无合理解释（如末世第1天建帮派）**
- 与总纲核心冲突或卷末高潮明显冲突
- 设定集基线未补齐，或本卷增量未回写到现有设定集
- 存在 `BLOCKER` 未裁决
- **伏笔强制兑现未安排**：thread-lifecycle-tracker 返回 `forced_payoffs` 且 `mode == "force"`，但本卷章纲中无对应 `伏笔处置: 兑现:[thread_id]` 标注
- 约束触发频率不足（当 idea_bank 启用时）

### Rollback / recovery
If any hard fail triggers:
1. Stop and list the failing items.
2. Re-generate only the failed batch (do not overwrite the whole file).
3. If the last batch is invalid, remove that batch and rewrite it.
4. Only update state after Final check passes.

Next steps:
- 继续规划下一卷 → /ink-plan
- 开始写作 → /ink-write
