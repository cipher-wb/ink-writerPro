# PRD: Logic Fortress — ink-writer 逻辑防崩体系

## Introduction

ink-writer 当前拥有完善的文风控制（anti-detection）、情绪曲线（emotion-curve）、追读力（reader-pull）、设定一致性（consistency）、连贯性（continuity）等审查机制，但存在一个**系统性盲区**：**正文对大纲的合规性验证**和**章内微观逻辑自洽性验证**几乎为零。

### 问题实证

以《你能看见我还剩多少秒吗》第一章为例，writer-agent 产出了一篇"文笔通顺、情绪到位"但**逻辑千疮百孔**的章节：

| 缺陷类型 | 具体表现 | 现有checker是否能拦截 |
|----------|---------|---------------------|
| 大纲偏离-新增角色 | 凭空创造"中学生"角色，占全文40%篇幅 | ❌ 无 |
| 大纲偏离-缺少角色 | 大纲要求的"周彦"完全缺席 | ❌ 无 |
| 大纲偏离-核心目标弱化 | "孕妇之死"本应是全章核心，却3行带过 | ❌ 无 |
| 大纲偏离-伏笔未埋 | F-001"数字颜色变化"未出现在正文中 | ❌ 无 |
| 大纲偏离-钩子透支 | 章末悬念钩被提前消费 | ❌ 无 |
| 章内数字矛盾 | 倒计时从1:05直接跳到0:00（65秒凭空消失） | ❌ 无（timeline仅查跨章） |
| 章内动作矛盾 | "拉回车厢"下一句"被推下车" | ❌ 无 |
| 章内设定矛盾 | 前文"程序员"，后文变"仓库工人" | ❌ 无（跨章才查） |
| 章内空间跳跃 | 未来潜在风险：角色无移动就换了位置 | ❌ 无 |
| 章内物品连续性 | 未来潜在风险：手持物凭空消失 | ❌ 无 |

### 根因分析

```
                    ┌──────────────────────────────────┐
                    │         根因：验证缺口           │
                    └──────────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
     ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
     │  入口只查存在性  │  │ writer无硬约束  │  │ 出口无合规验证  │
     │                │  │                │  │                │
     │ Step 0.5 只检查 │  │ 执行包是"参考"  │  │ 11个checker中  │
     │ 大纲文件是否存在 │  │ 而非"合同"      │  │ 无一个验证正文  │
     │ 不检查正文是否  │  │ writer可自由发挥 │  │ 是否匹配大纲   │
     │ 遵守了大纲     │  │ 新增/删除/弱化  │  │ 的关键实体/事件 │
     └────────────────┘  └────────────────┘  └────────────────┘
```

**核心洞察**：ink-writer 的"大纲即法律"铁律是一句口号，不是一个执行机制。就像法律没有法院和警察，只靠公民自觉。

---

## Goals

- **G1**: 消除"正文偏离大纲"类缺陷 — writer-agent 不能新增大纲不存在的角色/事件，不能遗漏大纲要求的关键实体/伏笔/钩子
- **G2**: 消除"章内微观逻辑矛盾"类缺陷 — 数字算术错误、动作序列矛盾、设定前后不一、空间跳跃、物品连续性断裂、感官矛盾、对话归属混乱、因果倒置
- **G3**: 建立两层防线（预防+拦截），将逻辑缺陷的修复成本从"重写整章"降低到"writer自检修正"
- **G4**: 所有新增检查必须为**硬阻断**（不通过则不允许进入下一步），不留"建议修复"的灰色地带
- **G5**: 不影响现有写作流程的创意空间——约束的是"大纲规定的必须项"，不是"大纲未规定的自由发挥区"

---

## User Stories

### US-001: Context-Agent 输出"强制合规清单"（Mandatory Compliance Checklist, MCC）

**Description:** 作为 ink-writer 写作流水线，我需要 context-agent 从大纲中提取一份结构化的强制合规清单，以便 writer-agent 在写作时有明确的"必须做"和"禁止做"清单。

**Acceptance Criteria:**
- [ ] context-agent 在现有 13 板块之外，新增 **板块 14: 强制合规清单（MCC）**
- [ ] MCC 从大纲的以下字段自动提取：
  - `关键实体` → `required_entities[]`（必须出场的角色/物品/地点）
  - `伏笔处置.埋设` → `required_foreshadows[]`（本章必须埋设的伏笔）
  - `钩子` → `required_hook`（章末必须设置的钩子类型和内容）
  - `目标` → `chapter_goal`（本章核心目标，必须充分展开）
  - `爽点` → `required_coolpoint`（本章必须出现的爽点）
  - `黄金三章附加` → `golden_three_extras[]`（ch≤3 时的额外硬性要求）
  - `本章变化` → `required_change`（本章结束时必须发生的状态变化）
  - `章末未闭合问题` → `required_open_question`（必须在章末留下的未解问题）
- [ ] MCC 同时生成 `forbidden_inventions` 字段：
  - `max_new_named_characters: 0`（除非大纲 `关键实体` 中有标注"新角色"）
  - `forbidden_plot_elements[]`（从大纲的"禁止拖沓区"等字段提取）
- [ ] MCC 输出为 JSON 结构，嵌入执行包的独立板块
- [ ] 当大纲缺少某字段时，MCC 对应项标记为 `"not_specified"`（不阻断，但在 Step 3 降级为 warning）

---

### US-002: Writer-Agent 写作前/写作后双重自检机制

**Description:** 作为 writer-agent，我需要在写作前确认 MCC 清单，在写作后逐项验证产出是否满足清单，以便在草稿阶段就消除大纲偏离。

**Acceptance Criteria:**
- [ ] Writer-agent 规格文件新增 **"写作前确认"** 环节：
  - 读取 MCC 并在内部生成"写作合同"（不输出，仅内部确认）
  - 合同格式：逐项列出 required_entities、required_foreshadows、required_hook、chapter_goal
- [ ] Writer-agent 规格文件新增 **"写作后自检"** 环节（Step 2A 末尾，输出正文之前）：
  - 逐项对照 MCC 验证：
    1. ✅/❌ 每个 required_entity 是否在正文中出场（至少有名字或明确指代出现）
    2. ✅/❌ 每个 required_foreshadow 是否在正文中有对应段落
    3. ✅/❌ required_hook 是否在章末最后 300 字内出现
    4. ✅/❌ chapter_goal 核心事件是否在正文中出现，且未被自创内容喧宾夺主
    5. ✅/❌ 正文中是否存在 MCC 未列出的新命名角色（forbidden_inventions 检查，具名群演除外：出场≤2句且无剧情影响）
    6. ✅/❌ required_change 是否在正文中体现
  - 任一项 ❌ → writer-agent 必须自行修正后重新输出，最多重试 2 轮
  - 自检结果以 JSON 格式附在正文文件的同目录下：`.ink/tmp/mcc_selfcheck_ch{NNNN}.json`
- [ ] 自检失败超过 2 轮 → 标记为 `mcc_selfcheck_failed`，流程继续但在 Step 3 强制触发 outline-compliance-checker

---

### US-003: 新增 `logic-checker` 审查器（章内微观逻辑验证）

**Description:** 作为 ink-writer 审查体系，我需要一个专门验证章内微观逻辑自洽性的 checker，以便拦截数字矛盾、动作矛盾、空间跳跃等现有 checker 无法覆盖的逻辑缺陷。

**Acceptance Criteria:**
- [ ] 新增 `agents/logic-checker.md` 规格文件
- [ ] logic-checker 执行以下 8 层检查：

**L1: 数字/算术一致性（Arithmetic Consistency）**
- 章内出现的所有数字序列（倒计时、金额、距离、时间流逝等）必须算术正确
- 倒计时/计时器：相邻两次出现的数值差必须与叙事时间流逝合理匹配（允许省略号跳跃，但跳跃必须有叙事时间支撑）
- 叙事时间估算采用粗粒度规则：一轮对话 ≈ 5-10秒、一段动作描写 ≈ 3-5秒、一段心理活动 ≈ 时间暂停（不消耗故事内时间）、一段环境描写 ≈ 1-3秒
- 两次数字出现之间的叙事时间估算值，与数字差值的偏差不得超过 ±30%
- severity: critical（数字跳跃无叙事支撑，如65秒凭空消失）、high（偏差>50%）、medium（偏差30-50%）

**L2: 动作序列一致性（Action Sequence Consistency）**
- 连续动作必须物理可行且因果连贯
- 检测模式：A动作的结果与紧接着的B动作的前提矛盾（如"拉回来"→"下了车"）
- 检测模式：同一时刻角色不能在两个不同位置执行动作
- severity: critical（动作直接矛盾）、high（物理不可行）

**L3: 章内属性一致性（Intra-Chapter Attribute Consistency）**
- 同一章节内，角色的固定属性（职业、年龄、外貌特征、称谓）不得前后矛盾
- 检测方式：提取章内所有对同一角色的属性描述，交叉验证
- severity: critical（核心属性矛盾，如职业变化）、medium（次要属性不一致）

**L4: 空间连续性（Spatial Continuity）**
- 角色位置变化必须有移动过程描写
- 检测模式：角色在A地 → 无移动描写 → 突然在B地执行动作
- 例外：场景切换有明确分隔符或时间跳跃
- severity: high（无解释的瞬移）、medium（移动过程过于简略）

**L5: 物品连续性（Object Continuity）**
- 角色手持/佩戴/携带的物品在场景内保持连续
- 检测模式：物品被提及 → 未描写放下/消失 → 凭空不见或变成另一物品
- 检测模式：物品未被提及获取 → 突然出现在角色手中
- severity: high（关键道具消失）、medium（次要物品不连续）

**L6: 感官一致性（Sensory Consistency）**
- 环境感官描写与角色行为必须匹配
- 检测模式：描述"漆黑一片"但角色能看到颜色细节
- 检测模式：描述"震耳欲聋"但角色能听清低声对话
- severity: high（直接矛盾）、medium（轻微不协调）

**L7: 对话归属清晰性（Dialogue Attribution）**
- 多人场景（≥3人）中每句对话必须可明确归属到说话人
- 检测方式：连续 3 句以上对话无说话人标记时，检查上下文是否足以推断
- severity: high（无法判断说话人）、medium（需要回读才能判断）

**L8: 因果逻辑（Causal Logic）**
- 结果不得先于原因出现
- 角色的决策/行为必须有合理动机（可以是隐性的，但不能完全无因）
- 检测模式：角色做出某个决定，但前文没有任何信息支撑这个决定的合理性
- severity: critical（因果严重倒置）、high（决策无任何铺垫）、medium（铺垫不足）

**输出与阻断：**
- [ ] 输出格式与现有 checker 一致（JSON issues[] + Markdown 报告）
- [ ] MUST_NOT_PASS 条件：存在任何 critical 或 ≥2 个 high severity issue
- [ ] 在 Step 3 审查路由中注册为**核心审查器**（始终执行），权重 15%
- [ ] 权重来源：从 continuity-checker (20% → 15%) 和 reader-pull-checker (15% → 10%) 各分 5%

**权重调整后：**

| Checker | 原权重 | 新权重 |
|---------|--------|--------|
| consistency-checker | 25% | 25% |
| continuity-checker | 20% | 15% |
| ooc-checker | 20% | 20% |
| **logic-checker（新增）** | - | **15%** |
| reader-pull-checker | 15% | 10% |
| outline-compliance-checker（新增） | - | **15%** |
| high-point-checker | 10% | 条件 |
| pacing-checker | 5% | 条件 |
| proofreading-checker | 5% | 条件 |
| emotion-curve-checker | 5% | 条件 |

---

### US-004: 新增 `outline-compliance-checker` 审查器（大纲合规验证）

**Description:** 作为 ink-writer 审查体系，我需要一个专门验证正文是否严格遵守大纲的 checker，作为"大纲即法律"铁律的执法机关。

**Acceptance Criteria:**
- [ ] 新增 `agents/outline-compliance-checker.md` 规格文件
- [ ] outline-compliance-checker 消费 MCC（US-001 产出）和正文，执行以下 6 层检查：

**O1: 实体出场合规（Entity Compliance）**
- 大纲 `关键实体` 中列出的每个实体必须在正文中出场
- 出场判定：角色名/代称/明确指代至少出现 1 次，且有实质性互动（不只是被提及）
- 大纲 `关键实体` 中标注"（死亡）"的角色，正文必须包含死亡场景描写
- severity: critical（关键角色完全缺席）、high（角色仅被提及无实质戏份）

**O2: 禁止发明检查（Invention Guard）**
- 正文中出现的有名字的新角色，必须在大纲 `关键实体` 中有对应
- 例外：群众演员（无名字的路人、乘客等）不受此限
- 例外：大纲 `关键实体` 中标注为"乘客群"等集合名词时，允许具体化为无名个体
- 例外：**具名群演**——出场 ≤2 句且无后续剧情影响的命名角色（如"卖煎饼的老王"一句话后再无出场）不算违规
- severity: critical（有名字的新角色不在大纲中且占据大量篇幅或推动了剧情）、high（新角色虽篇幅不大但参与了剧情互动）

**O3: 核心目标充分性（Goal Fulfillment）**
- 大纲 `目标` 描述的核心事件必须在正文中出现
- 充分性采用**相对判定**而非固定篇幅阈值：
  - 判定1（存在性）：核心事件是否在正文中有明确的对应场景？（有/无，二值判定）
  - 判定2（主导性）：非大纲自创内容的篇幅是否超过了核心事件的篇幅？（即核心事件必须是全章的"主角"，不能被自创情节"喧宾夺主"）
- severity: critical（核心事件完全未出现）、high（自创内容篇幅超过核心事件篇幅，喧宾夺主）、medium（核心事件存在但展开过于简略，少于3个完整段落）

**O4: 伏笔埋设验证（Foreshadow Embedding）**
- 大纲 `伏笔处置.埋设` 中列出的每个伏笔必须在正文中有对应描写
- 验证方式：伏笔关键词/描述在正文中有可识别的对应段落
- severity: high（伏笔完全未埋设）、medium（埋设模糊，读者可能无法感知）

**O5: 钩子合规（Hook Compliance）**
- 大纲 `钩子` 描述的章末钩子必须在正文最后 500 字内出现
- 钩子不得被提前消费（即钩子描述的悬念不应在本章内就被解答）
- severity: high（钩子缺失或被提前消费）、medium（钩子位置不在章末）

**O6: 黄金三章附加项（Golden Three Extras）**
- 仅 ch ≤ 3 时启用
- 大纲 `黄金三章附加` 中的每项要求逐一验证
- 如"第1章必须有至少2个有名字有态度的配角" → 检查正文中有名字且有对话/行为的配角数量
- severity: high（未满足黄金三章硬性要求）

**输出与阻断：**
- [ ] 输出格式与现有 checker 一致
- [ ] MUST_NOT_PASS 条件：存在任何 critical 或 ≥2 个 high severity issue
- [ ] 在 Step 3 审查路由中注册为**核心审查器**（始终执行），权重 15%
- [ ] 此 checker 独立于 continuity-checker 的"大纲一致性"维度（continuity 侧重叙事流，本 checker 侧重合同执行）

---

### US-005: Step 3 Review Gate 集成与硬阻断规则

**Description:** 作为 ink-writer 审查门禁，我需要将新增的 logic-checker 和 outline-compliance-checker 集成到 Step 3，并建立硬阻断规则。

**Acceptance Criteria:**
- [ ] `step-3-review-gate.md` 新增两个核心审查器的路由规则：
  - `logic-checker`：始终执行，权重 15%
  - `outline-compliance-checker`：始终执行，权重 15%
- [ ] 新增两个硬阻断门禁：

**逻辑门禁（Logic Gate）：**
- Hard Block：`logic-checker` 存在 critical issue 或 ≥2 个 high issue → 禁止进入 Step 4，必须回退 Step 2A 重写
- Soft Warning：仅 medium/low issue → 传递给 polish-agent 修复

**大纲合规门禁（Outline Compliance Gate）：**
- Hard Block：`outline-compliance-checker` 存在 critical issue 或 ≥2 个 high issue → 禁止进入 Step 4，必须回退 Step 2A 重写
- Soft Warning：仅 medium/low issue → 传递给 polish-agent 修复

- [ ] 硬阻断回退 Step 2A 时，将 checker 报告的 **issues[] 精简版**注入为 writer-agent 的额外输入（repair context），仅包含 issue 类型、severity、位置、修复建议，不传完整报告正文（控制 token 膨胀）
- [ ] 硬阻断最多触发 2 次回退，第 3 次失败则暂停流程，输出诊断报告请求人工干预
- [ ] `overall_score` 公式更新为包含新 checker 的权重（权重表见 US-003）
- [ ] 若任一新 checker 存在 critical issue，`overall_score` 上限 cap 到 50（比现有的 60 更严格，因为逻辑错误比文风问题更致命）

---

### US-006: Writer-Agent 硬约束升级

**Description:** 作为 writer-agent 的规格文件，我需要新增针对逻辑自洽的硬性写作规则，以便从写作源头预防逻辑缺陷。

**Acceptance Criteria:**
- [ ] writer-agent.md 新增 **"逻辑自洽铁律"** 章节，与现有"写作铁律"并列：

**铁律 L1: 数字即承诺**
- 章内出现的任何数字（倒计时、金额、距离、人数等）一旦给出具体值，后续引用必须算术正确
- 数字变化必须有叙事时间支撑：如果倒计时从 3:42 变成 2:58，中间必须有至少 44 秒份量的叙事内容
- 禁止"跳跃省略"：如需省略中间过程，必须用省略号或时间跳跃标记（"不知过了多久"、"几分钟后"等显式过渡）

**铁律 L2: 动作即物理**
- 每个物理动作的结果必须成为下一个动作的前提
- 如果A把B拉回来了，B的下一个状态必须是"在A拉回来的位置"，不能凭空跳到其他位置
- 禁止"结果先于原因"：角色不能在还没获得信息的情况下基于该信息做出决策

**铁律 L3: 属性即锁定**
- 角色在本章首次提及的属性（职业、年龄、外貌特征）在本章内不可变更
- 如需变更，必须有叙事理由（如变装、伪装被揭穿等）
- 特别注意：context-agent 执行包中的角色档案是权威来源，正文不得与之矛盾

**铁律 L4: 空间即连续**
- 角色从A地到B地，必须有移动过程（可以简略但不能完全没有）
- 同一时刻角色只能在一个地点
- 场景切换必须有过渡（哪怕只是一句"他走出了地铁站"）

**铁律 L5: 大纲即合同**
- MCC 清单中的 required_entities 必须全部出场
- 未经 MCC 授权，禁止创造有名字的新角色（具名群演除外：出场≤2句且无剧情影响）
- chapter_goal 核心事件必须是正文的主导内容，自创情节篇幅不得超过核心事件篇幅
- required_foreshadows 必须在正文中有可识别的对应段落
- required_hook 必须出现在章末，不得提前消费

- [ ] 将这 5 条铁律加入 writer-agent 现有的"禁止事项"清单
- [ ] 在 writer-agent 的"硬性指标检查"环节新增 MCC 合规检查项

---

### US-007: Polish-Agent 逻辑修复能力增强

**Description:** 作为 polish-agent，我需要能够处理 logic-checker 和 outline-compliance-checker 传递的 medium/low severity 问题，以便在润色阶段修复轻微逻辑缺陷。

**Acceptance Criteria:**
- [ ] polish-agent.md 的修复优先级列表新增两项（插入在现有优先级之前，因为逻辑修复优先于文风修复）：
  - P0: **逻辑修复**（logic_fix_prompt）— 修复 logic-checker 的 medium 问题
  - P0.5: **大纲合规修复**（outline_fix_prompt）— 修复 outline-compliance-checker 的 medium 问题
- [ ] 逻辑修复的约束：
  - 修复数字错误时，只改数字本身，不改周围叙事
  - 修复空间跳跃时，只添加过渡句，不删除原有内容
  - 修复物品连续性时，添加物品状态变化的描写
- [ ] Step 4.5 安全校验新增检查：
  - 验证 polish 的逻辑修复没有引入新的逻辑矛盾（diff 检查）
  - 验证 polish 的大纲合规修复没有改变剧情走向

---

### US-008: Continuity-Checker 大纲偏差检查增强

**Description:** 作为 continuity-checker，我需要将现有的"大纲一致性"维度从"标记偏差"升级为"量化偏差"，以便与 outline-compliance-checker 形成互补。

**Acceptance Criteria:**
- [ ] continuity-checker 的"大纲一致性"维度增强：
  - 新增"篇幅偏差"检测：大纲核心事件的篇幅占比 vs 非大纲自创事件的篇幅占比
  - 若自创事件篇幅 > 核心事件篇幅 → severity: high（喧宾夺主）
  - 若自创事件篇幅 > 30% 全文 → severity: medium（篇幅膨胀）
- [ ] continuity-checker 的 MUST_NOT_PASS 条件新增：
  - 自创事件篇幅超过核心事件篇幅

---

### US-009: Context-Agent 时间约束板块增强

**Description:** 作为 context-agent，我需要在时间约束板块（板块5）中提供更精确的时间预算信息，以便 writer-agent 能正确处理章内时间流逝。

**Acceptance Criteria:**
- [ ] 板块 5 新增 `time_budget` 字段：
  - 从大纲的"章内时间跨度"计算本章可用的叙事时间总量
  - 如果章内有倒计时/计时器场景，标注精确的时间窗口
  - 示例：`"time_budget": {"total_span": "4小时", "precision_scenes": [{"type": "countdown", "start": "3:42", "end": "0:00", "duration": "3分42秒", "note": "孕妇倒计时归零，需在约4分钟叙事内完成"}]}`
- [ ] 当大纲中出现"倒计时"、"计时器"、"限时"等关键词时，context-agent 自动生成 precision_scene 条目
- [ ] precision_scene 条目注入 writer-agent 的执行包，作为 L1 铁律的参考数据

---

### US-010: ink-write SKILL.md 流程更新

**Description:** 作为 ink-write 主流程文档，我需要更新以反映新增的检查点和阻断规则。

**Acceptance Criteria:**
- [ ] Step 1 输出规格新增 MCC 板块描述
- [ ] Step 2A 流程新增"写作前确认 MCC"和"写作后自检 MCC"环节描述
- [ ] Step 3 审查路由表新增 logic-checker 和 outline-compliance-checker
- [ ] Step 3 硬阻断规则新增 Logic Gate 和 Outline Compliance Gate
- [ ] Step 3 → Step 2A 回退路径文档化（repair context 注入机制）
- [ ] Step 4 修复优先级列表更新
- [ ] Step 4.5 安全校验新增逻辑修复验证
- [ ] 权重表更新
- [ ] 流程图更新（包含新的回退箭头）

---

## Functional Requirements

### 预防层（Writer-Agent 侧）

- **FR-01**: Context-Agent 必须从大纲提取 MCC 并作为执行包的板块 14 输出
- **FR-02**: MCC 必须包含 required_entities、required_foreshadows、required_hook、chapter_goal、required_coolpoint、forbidden_inventions、required_change、required_open_question 字段
- **FR-03**: Writer-Agent 在 Step 2A 开始前必须读取并内部确认 MCC
- **FR-04**: Writer-Agent 在 Step 2A 完成后必须逐项自检 MCC，失败则自行修正（最多 2 轮）
- **FR-05**: Writer-Agent 规格文件必须包含 5 条逻辑自洽铁律（数字即承诺、动作即物理、属性即锁定、空间即连续、大纲即合同）
- **FR-06**: MCC 自检结果必须持久化为 JSON 文件，供 Step 3 参考

### 拦截层（Checker 侧）

- **FR-07**: logic-checker 必须执行 8 层检查（L1-L8），覆盖数字算术、动作序列、属性一致、空间连续、物品连续、感官一致、对话归属、因果逻辑
- **FR-08**: outline-compliance-checker 必须执行 6 层检查（O1-O6），覆盖实体出场、禁止发明、目标充分性、伏笔埋设、钩子合规、黄金三章附加
- **FR-09**: 两个新 checker 必须注册为 Step 3 的核心审查器（始终执行）
- **FR-10**: 两个新 checker 存在 critical 或 ≥2 high issue 时必须硬阻断，回退 Step 2A
- **FR-11**: 硬阻断回退时，checker 报告必须作为 repair context 注入 writer-agent
- **FR-12**: 硬阻断最多 2 次，第 3 次暂停请求人工干预
- **FR-13**: 新 checker 的 critical issue 使 overall_score 上限 cap 到 50

### 修复层（Polish-Agent 侧）

- **FR-14**: Polish-Agent 必须能处理 logic-checker 的 medium/low 问题
- **FR-15**: Polish-Agent 必须能处理 outline-compliance-checker 的 medium/low 问题
- **FR-16**: 逻辑修复优先级高于文风修复
- **FR-17**: Step 4.5 安全校验必须验证逻辑修复没有引入新矛盾

### 增强层（现有组件升级）

- **FR-18**: Continuity-checker 的大纲偏差检查升级为量化篇幅偏差
- **FR-19**: Context-agent 板块 5 新增 time_budget 和 precision_scenes
- **FR-20**: ink-write SKILL.md 流程文档全面更新

---

## Non-Goals (Out of Scope)

- **不改变大纲生成流程**（ink-plan）— 本 PRD 假设大纲是正确的，只确保正文忠于大纲
- **不新增跨章逻辑检查** — 现有 consistency-checker 和 continuity-checker 已覆盖跨章一致性
- **不改变现有 checker 的核心逻辑** — 只调整权重和新增维度，不重构
- **不增加 writer-agent 的创意限制** — MCC 只约束大纲明确规定的项，大纲未规定的自由区域仍由 writer 自由发挥
- **不涉及 UI/Dashboard 变更**
- **不涉及 data-agent 或 index.db schema 变更**

---

## Technical Considerations

### 架构决策

1. **MCC 放在 context-agent 而非独立模块**：因为 context-agent 已经在读大纲，在同一步骤中提取 MCC 避免重复读取
2. **logic-checker 独立于 consistency-checker**：虽然有重叠（如时间线），但 consistency 侧重跨章设定，logic 侧重章内微观物理，关注点不同
3. **outline-compliance-checker 独立于 continuity-checker**：continuity 侧重叙事流，outline-compliance 侧重合同执行，是两种不同的验证范式
4. **硬阻断而非软修复**：逻辑错误不像文风问题可以靠 polish "抹平"，一个动作矛盾需要重写整段情节，polish 无法胜任

### 性能影响

- 新增 2 个核心 checker 会增加 Step 3 的并行任务数（从 5 个增加到 7 个）
- MCC 自检增加 writer-agent 的 token 消耗（估计 +500-1000 tokens）
- 硬阻断回退会增加总写作时间（但比发现问题后重写整章更节省）

### 依赖关系

```
US-001 (MCC) ──→ US-002 (Writer自检) ──→ US-006 (Writer铁律)
     │                                         │
     ├──→ US-004 (Outline Checker) ────→ US-005 (Gate集成)
     │                                         │
     └──→ US-009 (时间预算)               US-003 (Logic Checker) ──→ US-005
                                               │
                                          US-007 (Polish增强)
                                               │
                                          US-008 (Continuity增强)
                                               │
                                          US-010 (SKILL.md更新)
```

### 实施建议顺序

Phase 1（核心防线）: US-001 → US-002 → US-004 → US-003 → US-005
Phase 2（配套升级）: US-006 → US-007 → US-008 → US-009
Phase 3（文档收尾）: US-010

---

## Success Metrics

- **M1**: 使用新流程重写《你能看见我还剩多少秒吗》第一章，不再出现本 PRD 开头列出的 10 类缺陷中的任何一类
- **M2**: outline-compliance-checker 能 100% 检出"缺少大纲要求的角色"和"新增大纲不存在的角色"
- **M3**: logic-checker 能 100% 检出"数字算术矛盾"和"动作序列矛盾"
- **M4**: writer-agent 的 MCC 自检通过率 ≥ 80%（即大部分逻辑问题在写作阶段就被预防，不需要等到 Step 3 拦截）
- **M5**: 硬阻断触发后的重写成功率 ≥ 90%（即第一次回退修复后就能通过）

---

## Design Decisions（已确定）

以下问题在 PRD 评审中已确定方案：

1. **核心目标充分性判定** — 不使用固定篇幅百分比，采用**相对判定**：核心事件必须存在，且自创内容篇幅不得超过核心事件篇幅（主导性检查）。已更新到 O3 和 US-002。

2. **新命名角色判定** — 出场 ≤2 句且无后续剧情影响的命名角色视为**"具名群演"**，不算违规。已更新到 O2。

3. **叙事时间量化** — 采用粗粒度估算规则：一轮对话 ≈ 5-10秒、一段动作描写 ≈ 3-5秒、一段心理活动 ≈ 时间暂停（不消耗故事内时间）、一段环境描写 ≈ 1-3秒，允许 ±30% 偏差。已更新到 L1。

4. **回退 context 膨胀控制** — repair context 只传递 checker 报告的 issues[] 精简版（issue 类型、severity、位置、修复建议），不传完整报告正文。已更新到 US-005。

## Open Questions

无。所有设计问题已在评审中确定。
