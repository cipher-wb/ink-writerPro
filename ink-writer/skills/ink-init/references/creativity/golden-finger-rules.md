---
name: golden-finger-rules
description: 金手指五重硬约束（非战力维度 + 代价池抽取 + 一句话爆点 + 反同源闭环 + 阶梯轴 T1-T4）。Quick Step 1.5 校验标尺，至少 4 项通过方可入选，否则重抽最多 5 次，仍失败则降档。v2.0 引入 cost-pool 强制抽样替代 LLM 自由发挥。
type: reference
version: v2.0
---

# 金手指五重硬约束

五条硬约束串联出「不俗套 + 可玩出戏 + 一句话卖得动 + 不闭环 + 有阶梯」的金手指。每套方案在 Quick Step 1.5 按本文件自检，输出 `gf_checks = {GF1, GF2, GF3, GF4, GF5}` 的 0/1 矩阵，**至少 4 项为 1 方可通过**；否则回到 Quick Step 1 重抽同一槽位（最多 5 次），仍失败触发 Quick Step 1.5 末尾的「降档逻辑」。

> **v2.0 重大变更**：GF-2 由「LLM 自由发挥代价」改为「强制从 `data/golden-finger-cost-pool.json` 抽 1 主代价 + 2 副代价」。新增 GF-4 反同源闭环检测、GF-5 阶梯轴 T1-T4 必填。设计目标：消除『失忆/扣寿/血脉反噬』的中位数趋同。

## GF-1 非战力维度

**定义**：金手指的作用维度不得是「纯力量 / 纯资源」。必须落在以下 8 类之一：

1. 信息（提前/延迟/非对称知情）
2. 时间（回溯/停滞/加速/错位）
3. 情感（读心/情绪操控/共情压制）
4. 社交（关系识别/声望/契约）
5. 认知（逻辑/模型/记忆/学习）
6. 概率（骰子偏置/因果微调）
7. 感知（通感/视觉叠加/第三视角）
8. 规则（局部改写世界规则/契约化 bug）

**禁用维度**：修为暴涨、无限资源、面板属性、纯战斗力倍率。

**校验伪代码**：
```
gf1 = 1 if gf_dimension in {信息,时间,情感,社交,认知,概率,感知,规则} else 0
```

## GF-2 代价池强制抽取（v2.0 重写）

**定义**：金手指的代价**禁止 LLM 自由生成**，必须从 `data/golden-finger-cost-pool.json` 按以下硬规则抽取：

### 抽取规则

| 项 | 数量 | 约束 |
|----|------|------|
| 主代价 `main_cost` | **必须 1 条** | 优先从 `trope_freq ∈ {low, rare}` 抽；`rarity ≥ 3`；不得与该作金手指 `dimension` 同源（详见 GF-4） |
| 副代价 `side_costs` | **必须 2 条** | 至少 1 条跨大类（与 main_cost 不同 category）；`trope_freq=high` 整体配额上限 1/3（即 3 条总代价里最多 1 条 high） |
| 反趋同冷却 | — | 同一作品内最近 30 章不得复用同一 `cost_id`；`trope_freq=high` 子类最近 50 章不得复用 |

### 高频代价（`trope_freq=high`）冷却闸门

下列代价属于「中位数趋同区」，单作品内严格限额，**不得作为唯一主代价**：

- **C02-MEM-016 记忆/通用**（随机抹除记忆）
- **C01-CON-001 寿命削减**（每次扣阳寿）
- **C04-RES-057 灵石燃烧**
- **C06-CD-076 冷却/长冷**
- **C06-CD-077 冷却/单日单次**

**违规处理**：若 main_cost 命中上述任一 → 立即 GF2=0，重抽。

### 合格示例（v2.0）

```json
{
  "golden_finger": {
    "name": "听亡言",
    "dimension": "感知",
    "main_cost": {
      "cost_id": "C03-FOR-037",
      "tier_target": "T2",
      "value": "用一次，名字从某本户籍册的某一页被墨抹去"
    },
    "side_costs": [
      {"cost_id": "C07-EXP-091", "tier_target": "T1", "value": "尸体周围留下淡淡铁锈味"},
      {"cost_id": "C08-FAU-110", "tier_target": "T1", "value": "用时麻雀停叫 1 小时"}
    ]
  }
}
```

### 不合格示例

```
代价：每次使用扣减 1 年寿命 + 失忆一段记忆 + 修为倒退一阶
```

**问题**：
1. ✗ 三条全部从 trope_freq=high 区抽（寿命+记忆+修为倒退）—— 违反「high 配额上限 1/3」
2. ✗ 全部 C01_Physical 大类 —— 违反「至少 1 条跨大类」
3. ✗ 与典型感知/认知类金手指同源闭环（详见 GF-4）

**校验伪代码**：
```
def gf2(scheme):
    cost = scheme.golden_finger.main_cost
    side = scheme.golden_finger.side_costs
    pool = load_cost_pool()

    # 1) 必须从 pool 抽
    if cost.cost_id not in pool: return 0
    if any(s.cost_id not in pool for s in side): return 0

    # 2) 数量
    if len(side) != 2: return 0

    # 3) 至少 1 条副代价跨大类
    main_cat = pool[cost.cost_id].category
    if not any(pool[s.cost_id].category != main_cat for s in side): return 0

    # 4) high 配额 ≤ 1/3
    high_count = sum(1 for cid in [cost.cost_id, *(s.cost_id for s in side)]
                     if pool[cid].trope_freq == "high")
    if high_count > 1: return 0

    # 5) 主代价不得为 high
    if pool[cost.cost_id].trope_freq == "high": return 0

    # 6) tier_target 必须 ∈ {T1,T2,T3,T4}
    for c in [cost, *side]:
        if c.tier_target not in {"T1","T2","T3","T4"}: return 0

    return 1
```

## GF-3 一句话爆点

**定义**：20 字内能讲清楚，且产生「这也行？」的惊讶感。

合格 vs 不合格对比（10 组）：

| # | 合格（✅） | 不合格（❌） |
|---|-----------|-------------|
| 1 | ✅ 我能听见死人的谎话。 | ❌ 我能与亡灵沟通。 |
| 2 | ✅ 我说的每句话都会成真，除了关于我自己的。 | ❌ 我有言出法随的能力。 |
| 3 | ✅ 我每杀一人就老一岁，但能倒流一分钟。 | ❌ 我可以回溯时间。 |
| 4 | ✅ 我读心，但只读得到最恶毒那条。 | ❌ 我有读心术。 |
| 5 | ✅ 我能偷走别人的运气，但必须当面道歉。 | ❌ 我能掠夺气运。 |
| 6 | ✅ 凡签过我名的人，都会梦见自己死法。 | ❌ 我签约能赋予能力。 |
| 7 | ✅ 我可以提前看到自己所有的葬礼。 | ❌ 我能预知未来。 |
| 8 | ✅ 我能把伤口送人，连仇恨一起。 | ❌ 我能转移伤势。 |
| 9 | ✅ 我一哭，半径十米内所有谎言失效。 | ❌ 我的眼泪能破除幻术。 |
| 10 | ✅ 每次说真话，世界就忘记我一个亲人。 | ❌ 说真话有副作用。 |

**校验伪代码**：
```
gf3 = 1 if (字数 ≤ 20 AND 含具体动作/代价/反直觉 AND "这也行？"测试≥3/5评审) else 0
```

## GF-4 反同源闭环（v2.0 新增）

**定义**：金手指的 `dimension` 与代价池条目的 `dimension_taboo` 不得同源——避免「金手指=认知类 + 代价=失忆」这种「能力被代价直接抵消」的零张力闭环。

### 同源闭环典型反例

| 金手指维度 | 同源代价（禁配） | 闭环问题 |
|-----------|-----------------|----------|
| 认知（记忆/学习） | 失忆类（C02-MEM-016/017/018/019/030） | 能记住又忘记，等于没用 |
| 感知（视觉/听觉/通感） | 五感丧失类（C01-CON-004 / C01-PERM-010 / C02-POL-023 / C02-POL-025 / C05-EXP-074） | 给感知又收感知，戏剧空转 |
| 时间（回溯/加速） | 时间错乱类（C05-TIM-069 / C05-TIM-070 / C08-MED-116） | 操控时间又被时间反操控，逻辑闭环 |
| 情感（读心/共情） | 情感剥离类（C02-EMO-020/021/022 / C03-LOV-042 / C02-INT-029） | 读情感又失情感，立刻自废 |
| 社交（契约/声望） | 社交代价类（C03-FRD-044/045 / C06-TRG-081 / C06-MOR-090 / C07-EXP-093） | 控制社交又被社交反噬，结构对消 |
| 概率（运气偏置） | 气运反噬类（C03-FAT-035 / C04-LUC-050/051 / C06-RND-082/083） | 操纵概率又被概率反操纵 |
| 规则（改写世界规则） | 天劫/排斥类（C01-ACC-013 / C05-CAL-061/062/063 / C05-EXP-064/065 / C05-REJ-067 / C05-KAR-071/073） | 改规则又被规则反清算 |

### 例外：刻意制造闭环张力

少数高级写法可故意走同源闭环（如「读心术者每读一次就听到自己最不愿听的那条」），但必须满足：
- 同源闭环出现在**副代价**而非主代价
- 同源张力必须在前 10 章被剧情正面化为冲突点（让读者感到「正因为这个矛盾才好看」而非「正因为这个矛盾才崩」）

例外触发后 GF-4=1（视为通过），但需在方案输出 `gf4_exception_note` 字段说明剧情兑现路径。

**校验伪代码**：
```
def gf4(scheme):
    main_cost = pool[scheme.golden_finger.main_cost.cost_id]
    dim = scheme.golden_finger.dimension
    if dim in main_cost.dimension_taboo:
        if not scheme.golden_finger.gf4_exception_note:
            return 0
        # 例外审查：剧情兑现路径必须 ≥ 50 字
        if len(scheme.golden_finger.gf4_exception_note) < 50:
            return 0
    return 1
```

## GF-5 阶梯轴 T1-T4 必填（v2.0 新增）

**定义**：每个金手指的代价（主代价 + 副代价）必须显式指定 `tier_target ∈ {T1, T2, T3, T4}`，并在 `escalation_ladder` 中给出三个跃迁节点（首章/中段/后期）的 tier 演化。

### Tier 语义

- **T1 minor 小用**：流鼻血/头疼几天/丢点零钱级，用于日常章节高频出现
- **T2 moderate 中用**：扣寿一年/损耗修为/亲友轻伤级，用于卷与卷之间过渡
- **T3 major 大用**：残废/至亲代偿/灵宝粉碎级，用于卷末高潮
- **T4 extreme 极限**：身死道消/灵魂湮灭级，用于全书最终决战

### 阶梯演化必填字段

```json
{
  "escalation_ladder": {
    "ch1": {
      "main_cost_tier": "T1",
      "side_cost_tiers": ["T1", "T1"],
      "scene_anchor": "首章具体场景描写：他闭眼听见乞儿的话，回家路上想不起母亲爱吃哪种咸鱼了。"
    },
    "ch10": {
      "main_cost_tier": "T2",
      "side_cost_tiers": ["T2", "T1"],
      "scene_anchor": "他听完整整十具尸首，忘了母亲叫什么名字、第三次回不出家门。"
    },
    "late_game": {
      "main_cost_tier": "T3",
      "side_cost_tiers": ["T3", "T2"],
      "scene_anchor": "他听完七十二具尸首，连自己姓什么都忘了，户籍册上他的名字也被墨抹去半行。"
    }
  }
}
```

### 不合格示例

```json
{"escalation_ladder": "逐步加重，循序渐进"}
```

—— 空泛表述、无具体 tier、无场景锚点，GF5=0。

**校验伪代码**：
```
def gf5(scheme):
    lad = scheme.golden_finger.escalation_ladder
    if not all(k in lad for k in ["ch1","ch10","late_game"]): return 0
    for stage in lad.values():
        if stage["main_cost_tier"] not in {"T1","T2","T3","T4"}: return 0
        if not all(t in {"T1","T2","T3","T4"} for t in stage["side_cost_tiers"]): return 0
        if len(stage["scene_anchor"]) < 30: return 0
    # tier 必须递增（不允许 ch10 比 ch1 还轻）
    tiers = [lad[k]["main_cost_tier"] for k in ["ch1","ch10","late_game"]]
    rank = {"T1":1,"T2":2,"T3":3,"T4":4}
    if [rank[t] for t in tiers] != sorted([rank[t] for t in tiers]):
        return 0
    return 1
```

## 金手指禁止词列表（≥20）

命中任意一个直接 GF1=0，重抽：

修为暴涨 / 无限金币 / 系统签到 / 作弊器 / 外挂 / 无限奖励 / 吞噬天赋 / 觉醒面板 / 签到一万年 / 熟练度+1 / 属性+1 / 经验值 / 抽卡 / 抽奖池 / 每日任务奖励 / 老爷爷传功 / 万倍返还 / 充值变强 / 资源无限 / 境界飞升 / 丹药爆仓 / 灵石自动产出。

### v2.0 代价禁忌词（命中即 GF2=0）

下列描述属于「LLM 自由发挥」遗留模糊代价，命中其一立即重抽（必须改用 cost-pool 抽样结果）：

需消耗法力 / 过度使用会疲劳 / 有点难受 / 略感虚弱 / 元气大伤 / 暂时性头晕 / 疲惫 / 略感不适 / 短暂虚弱 / 神识透支（无量化）/ 意识模糊（无后果）。

## 校验算法与降档逻辑（v2.0）

```
for scheme in [方案1, 方案2, 方案3]:
    for attempt in range(1, 6):
        gf1, gf2, gf3, gf4, gf5 = self_check(scheme.golden_finger)
        scheme.gf_checks = [gf1, gf2, gf3, gf4, gf5]
        if sum(scheme.gf_checks) >= 4:  # v2.0: 5 项中至少过 4
            break
        scheme.golden_finger = regenerate(scheme, avoid=last_fail)
    else:
        # 5 次仍未通过
        aggression_level = max(1, aggression_level - 1)  # 激进→平衡，平衡→保守
        scheme.golden_finger = regenerate(scheme, aggression=aggression_level)
        scheme.gf_checks = self_check(scheme.golden_finger)

assert all(sum(s.gf_checks) >= 4 for s in 三套方案)
```

降档记录写入日志：`gf_downgrade_log = [{scheme_id, from_level, to_level, reason}]`，Quick Step 2 输出时在对应方案标注「⚠️ 金手指校验触发降档至 X 档」。

### 单项失败 → 主代价/副代价/dimension 重抽路径

| 失败项 | 重抽动作 |
|--------|----------|
| GF1 | 重选 dimension（8 类轮换） |
| GF2 | 重抽 main_cost 或 side_costs（保持 dimension 不变） |
| GF3 | 改写一句话爆点（保持 dimension + cost 不变） |
| GF4 | 重抽 main_cost（避开同 dimension_taboo） |
| GF5 | 补全 escalation_ladder 三阶段场景锚点 |

每项独立重抽 ≤2 次；2 次仍失败，全套金手指重新生成（dimension + cost + 一句话）。

## 与其它 Layer 的协作

- 与 Layer 1 `meta-creativity-rules.md` 的关系：GF-2 与 M01 代价可视化同源；GF-3 与 M07 欲望悖论 / M03 信息不对称互相加成；GF-5 与 M10 尺度跃迁同源（tier 演化即叙事尺度跃迁）。
- 与 Layer 3 `perturbation-engine.md` 的关系：cost-pool **独立于扰动池**，不进 perturbation_pairs；金手指所在维度可作为扰动对的 seed_a，与 category=神话/物件/职业 的 seed_b 组对时创意度提升。
- 与 US-008 创意指纹「金手指维度」字段直接对齐：输出 `GF-1/GF-2/GF-3/GF-4/GF-5` 五项 0/1 矩阵 + 创意指纹板块新增「代价指纹」字段（main_cost.cost_id + 2×side_cost.cost_id + tier_target × 3）。
- 与 `data/golden-finger-cost-pool.json` 的关系：cost-pool 是本规则文件的**唯一合法代价数据源**；版本不一致时以 cost-pool 的 schema_version 为准。
