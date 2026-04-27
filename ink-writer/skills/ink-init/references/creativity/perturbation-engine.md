---
name: perturbation-engine
description: Layer 3 扰动引擎。强制方案从种子库抽取 N 对跨 category 稀缺元素混搭注入，避免 LLM 落入语料中位数。v1.1 显式声明 cost-pool 独立于扰动池。
type: reference
version: v1.1
---

# Layer 3 扰动引擎（Perturbation Engine）

## 1. 设计目标

LLM 默认会向训练语料的中位数收敛（修真→宗门、都市→兵王、末世→丧尸）。Layer 1 元规则负责"不许走老路"，Layer 3 扰动引擎负责"强行掰向新路"——通过随机抽取种子库（`anti-trope-seeds.json`）中 2 个**不同 category** 的元素组成"扰动对"，作为方案构思的强制输入注入。

扰动对不是装饰，而是约束：方案必须围绕扰动对展开核心冲突或金手指设计，否则视为未生效，需重抽。

### 扰动池 vs 代价池：独立通道（v1.1 明确）

| 抽样系统 | 数据源 | 角色 | 是否 mandatory |
|----------|--------|------|----------------|
| **扰动池** Perturbation | `references/creativity/anti-trope-seeds.json` | "可选注入"—— 方案可借扰动对建立差异化创意 | 受档位 N 控制（1/2/3/5 对） |
| **代价池** Cost Pool | `data/golden-finger-cost-pool.json` | "必须注入"—— 金手指代价**强制**从此池抽 1 主 + 2 副 | 100% 必须，零例外（详见 `golden-finger-rules.md` §GF-2） |

两套系统不混用：
- 代价池条目**不进** anti-trope-seeds.json（不参与扰动对抽取）
- 扰动池条目**不进** cost-pool.json（不充当金手指代价）
- 唯一交集：扰动对的 `injection_note` 可以引用代价 cost_id（但代价的抽取逻辑独立完成）

---

## 2. 「扰动对」定义

一对扰动 = 从种子库不同 category 各抽 1 条种子。

- **形式**：`(seed_A, seed_B)`，其中 `seed_A.category ≠ seed_B.category`。
- **稀有度门槛**：单对中至少 1 条 `rarity ≥ 3`（档位 3+ 提至 ≥4，档位 4 提至 ≥5）。
- **跨类强制**：禁止同类内部混搭（避免"职业+职业=多职业"这类同质堆叠）。
- **互斥性**：同一方案内多对扰动不得共用同一 seed_id；3 套方案之间扰动对不得整对复用。

### 档位决定的扰动对数量 N

| 档位 | N（扰动对数下限） | 单对稀有度下限 | 备注 |
|------|--------------------|------------------|------|
| 1 保守 | 1 | rarity ≤ 3（轻量） | 仅作味道点缀 |
| 2 平衡 | 2 | ≥1 对 rarity = 4 | 默认档 |
| 3 激进 | 3 | ≥2 对 rarity ≥ 4 | 强冲击 |
| 4 疯批 | 5 | ≥3 对 rarity = 5 | 必含 1 对触发商业边界 |

---

## 3. 5 种扰动模式（Pattern）

每对扰动必须归属下列 5 种模式之一（schema 字段 `pattern`）。模式不是抽取工具而是分类标签——LLM 抽到种子对后，需主动判断该对属于哪种模式，并按该模式推导冲突。

### Pattern A：时代错位（Anachronism）

跨时代的元素强行同框，制造文化错位。

- 示例 1：唐代"司天监夜观星象"配"卫星轨道异常告警"——主角是钦天监正，但夜里看到的星不该在。
- 示例 2：1990 年代"录像厅老板"配"区块链分账协议"——录像带里录的是某条链上的私钥碎片。
- 示例 3：上古"祭司持龟甲"配"压力测试报告"——龟甲烧裂的纹路就是服务器的崩溃曲线。

### Pattern B：职业反差（Role Inversion）

把高门槛行业的内行知识塞给最不该懂的人。

- 示例 1："殡仪馆化妆师"配"国际刑警侧写师"——给死者化妆时根据皮下淤青读出凶手习惯。
- 示例 2："幼儿园保育员"配"私募基金风控"——午睡时盯着孩子心率判断市场情绪。
- 示例 3："修脚师傅"配"地质勘探员"——脚茧厚薄分布直接对应客人常踏的矿脉走向。

### Pattern C：尺度错位（Scale Mismatch）

把巨大尺度的事压进微小载体，或把微小事放大成史诗。

- 示例 1："星系灭亡的最后信号"压进"一颗核桃壳的螺纹"。
- 示例 2："地铁卡余额 3 块 5"扩展为"维系一个城市次元结界的最后能量"。
- 示例 3："蝴蝶振翅的 0.7 秒"被刻成"一整部上古剑诀"。

### Pattern D：规则颠倒（Rule Reversal）

把世界默认规则反向运行——重力、因果、价值、善恶顺序。

- 示例 1："说真话扣寿，说谎涨寿"——主角是国家级谈判专家，每场谈判都是和死神的额度博弈。
- 示例 2："越富的人越快变透明"——首富已经只剩半张脸，主角是给他做"被看见"治疗的心理医生。
- 示例 3："记忆从童年向死亡倒着发生"——主角第一次见到母亲时她正在临终。

### Pattern E：感官替换（Sense Substitution）

把信息从默认感官搬到错误感官。

- 示例 1："听见颜色"——主角是色盲，但能从交响乐里"看"出凶案现场的血迹分布。
- 示例 2："闻到时间"——古董鉴定靠鼻子，每件器物的真伪在年代气味里。
- 示例 3："触摸声音"——聋哑刺客摸枪管震动判断对方是否在说谎。

---

## 4. 抽取算法伪代码

```python
def draw_perturbation_pairs(seeds, genre, draft_index, n, rarity_floor):
    """
    seeds: anti-trope-seeds.json 的 seeds 数组
    genre: 当前方案题材（仙侠/都市/末世/...）
    draft_index: 第几套方案（1/2/3）
    n: 扰动对数下限（来自档位）
    rarity_floor: 单对至少 1 条 rarity ≥ rarity_floor
    返回: List[Tuple[seed_A, seed_B, pattern]]
    """
    # 固定种子：同秒同题材同方案号 → 可复现
    rng_seed = stable_hash(f"{int(time.time())}-{genre}-{draft_index}")
    rng = Random(rng_seed)

    # 题材过滤：seed.genre_tags 含 genre 或 "通用"
    pool = [s for s in seeds if genre in s.genre_tags or "通用" in s.genre_tags]

    pairs = []
    used_ids = set()
    while len(pairs) < n:
        a, b = rng.sample(pool, 2)
        if a.category == b.category:        continue
        if a.seed_id in used_ids or b.seed_id in used_ids: continue
        if max(a.rarity, b.rarity) < rarity_floor:        continue
        pattern = pick_pattern(a, b, rng)   # A-E 中按语义就近匹配
        pairs.append((a, b, pattern))
        used_ids.update([a.seed_id, b.seed_id])
    return pairs
```

**确定性说明**：同一秒、同一题材、同一方案号下重跑结果一致，便于调试和"我刚才那一套再来一次"。跨秒自动重洗。

---

## 5. 3 套方案的全局去重

3 套方案各自独立调用 `draw_perturbation_pairs`，但需在汇总阶段做整对级去重：

- 设三套的扰动对集合分别为 P1、P2、P3。
- 对任意两套 (Pi, Pj)，不得存在一对 `(a, b) ∈ Pi` 同时也在 `Pj`（顺序无关）。
- 若发生冲突，保留方案号小者，方案号大者重抽冲突对（`draft_index` 加 100 改种子）。
- 单种子级允许跨方案复用（同一稀缺职业可在 2 套里都出现），仅"整对"禁止复用。

---

## 6. 输出 schema 字段

每套方案输出 JSON / Markdown 必含：

```json
"perturbation_pairs": [
  {
    "pair_id": 1,
    "pattern": "B",
    "seed_a": {"id": "S-PROF-017", "category": "职业", "value": "殡仪馆化妆师", "rarity": 4},
    "seed_b": {"id": "S-PROF-082", "category": "职业", "value": "国际刑警侧写师", "rarity": 5},
    "injection_note": "化妆师能从尸体淤青还原凶手习惯，反向被刑警体系利用。"
  }
]
```

> 注：示例字段中 seed_a 与 seed_b 的 category 相同仅为字段格式说明，实际抽取必须跨 category。

`injection_note` 是 LLM 必填的"我打算怎么用这对扰动"——这是检查方案是否真的"使用"了扰动对，而非只是装饰列在末尾的关键证据。

---

## 7. 校验门槛（Quick Step 1 调用）

生成方案后调用：

1. 扰动对数量 ≥ 档位 N？
2. 每对 category 是否互异？
3. 单对稀有度门槛是否达标？
4. 3 套方案整对去重？
5. 每对 `injection_note` 是否真的体现在方案的核心冲突 / 金手指 / 主线钩子中（LLM 自检）？

任一未通过则该套方案重新抽取扰动对（最多 3 次）；3 次仍失败则按 `style-voice-levels` 与 `golden-finger-rules` 规定的降档逻辑统一降一档。

---

## 8. 与 Layer 1/2 的协作关系

- **Layer 1（meta-creativity-rules.md）**：扰动对必须能映射到至少 1 条元规则 M01-M10（在 `injection_note` 末尾用 `→Mxx` 标注），否则视为"花活但无骨"。
- **Layer 2（anti-trope-seeds.json）**：本引擎的唯一种子来源。skeleton 期 example 种子可用，但抽不出足够 N 对时降低 N 而非放宽 category 跨类规则——宁愿少不要乱。
- **Layer 3 自身**：模式 A-E 是分类工具不是配方，禁止"按模式 A 反推时代再编故事"，必须先抽种子再归类。

---

## 9. 版本演进

- v1.0：5 种模式 + 4 档 N 矩阵 + 整对去重。
- v1.1（待 Phase-Seed-1 后）：根据 1000 条种子统计调整稀有度门槛。
- v2.0（远期）：引入"模式权重"按题材偏置（仙侠偏 D、悬疑偏 E）。
