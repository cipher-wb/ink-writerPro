---
name: ink-init
description: 深度初始化网文项目。通过分阶段交互收集完整创作信息，生成可直接进入规划与写作的项目骨架与约束文件。支持 --quick 快速随机模式。
allowed-tools: Read Write Edit Grep Bash Task AskUserQuestion WebSearch WebFetch
---

# Project Initialization

## 模式分支（流程最前端）

解析用户输入参数：

- **带 `--quick`**：进入 Quick 模式（见下方 §Quick Mode）。
- **不带 `--quick`**：进入 Deep 模式（原有苏格拉底式提问流程，见 §Deep Mode）。

---

# Quick Mode（快速随机方案生成）

## 目标

一条命令生成 3 套完整小说方案，用户选一个（或混搭/重随）即可进入初始化，跳过 10+ 轮问答。

## Quick Step 0：加载命名素材与参考

必须 Read 以下文件：

1. `${CLAUDE_PLUGIN_ROOT}/../../data/naming/blacklist.json` — 黑名单，生成的所有角色名不得命中此列表中的任何条目。
2. `${CLAUDE_PLUGIN_ROOT}/../../data/naming/surnames.json` — 姓氏库（按 common/moderate/rare/compound 四层），随机抽取时按稀有度加权：common 20%、moderate 40%、rare 30%、compound 10%。
3. `${CLAUDE_PLUGIN_ROOT}/../../data/naming/given_names.json` — 名字素材库（按 classical/modern/martial/scholarly/cold 五风格 × male/female），根据方案风格从匹配风格池中随机取 1-2 字组合。
4. `references/genre-tropes.md`（L1 必读）。
5. `references/creativity/meta-creativity-rules.md`（L1 必读）—— 10 条元规则 M01-M10，作为 Quick Step 1 方案校验的硬约束标尺。
6. `references/creativity/anti-trope-seeds.json`（L1 必读）—— Layer 2 种子库骨架，扰动引擎抽取稀缺元素来源；skeleton 期 example 种子即可，1000 条正式种子由 Phase-Seed-1 交互会话补全，详见 `anti-trope-seeds-roadmap.md`。
7. `references/creativity/perturbation-engine.md`（L1 必读）—— Layer 3 扰动引擎规格；定义扰动对抽取算法、5 种模式、档位 N 矩阵、3 套方案整对去重，Quick Step 1 必须按本规格生成 `perturbation_pairs` 字段。
8. `references/creativity/golden-finger-rules.md`（L1 必读）—— 金手指三重硬约束（GF-1 非战力维度 / GF-2 代价可视化 / GF-3 一句话爆点）+ 禁止词列表 ≥20 + 校验算法 + 降档逻辑，Quick Step 1.5 校验标尺。
9. `references/creativity/style-voice-levels.md`（L1 必读）—— 语言风格三档分级（V1 文学狂野 / V2 烟火接地气 / V3 江湖野气）+ 敏感词 L0-L3 四级分类 + 档位×密度矩阵，Quick Step 1.6 分配标尺。
10. `${CLAUDE_PLUGIN_ROOT}/../../data/naming/nicknames.json`（L1 必读）—— 江湖绰号库 ≥100 条，每条含 `rarity(1-5)` 与 `style_tags`；V3 档主力素材，V1 档冷峻配角可借用 `rough` 标签子集。
11. `${CLAUDE_PLUGIN_ROOT}/../../data/naming/book-title-patterns.json`（L1 必读）—— V1/V2/V3 三档各 50+ 条书名模板，每条含 `rhetoric_tags`（7 种修辞：pun/homophone/antithesis/irony/oxymoron/concrete_abstract/anachronism），Quick Step 1.7 书名生成与修辞标签标注的抽取池。
12. 根据随机题材方向加载对应 `references/creativity/anti-trope-*.md`（L2 按需）。

### WebSearch 子步骤：双平台榜单反向建模

固定 2 个检索源（不可配置）：**起点中文网月票榜** + **番茄小说热门新书**。

**硬编码检索语**（4 条，两两分平台并行执行）：

1. `起点中文网 月票榜 2026 热门 题材`
2. `起点 分类 月榜`
3. `番茄小说 爆款 套路 2026`
4. `番茄免费小说 热门 新书`

**缓存路径与命名**：

- 基准目录 `${CLAUDE_PLUGIN_ROOT}/../../data/market-trends/`（见该目录 `README.md`）。
- 缓存文件 `cache-YYYYMMDD.md`（`YYYYMMDD` 为 UTC+8 当日日期）。

**执行流程**：

1. Read `${CLAUDE_PLUGIN_ROOT}/../../data/market-trends/cache-$(date +%Y%m%d).md`。
   - 若存在 → 当日已缓存，直接复用，**跳过 WebSearch**。
2. 若不存在 → 两平台并行 WebSearch（起点 2 条 + 番茄 2 条）；总延迟上限 **15s**。
3. 聚合结果写入 `cache-YYYYMMDD.md`，格式见 `data/market-trends/README.md`（两平台 Top 10 + 各 5-8 热门套路关键词 + **两平台共通套路 Top 5** 列表）。
4. 保留最近 **90 天** 缓存，超期文件启动时静默清理。

**Fallback**：

- WebSearch 失败 / 超时 → 回溯最近 **7 天** 内任一 `cache-*.md` 作为近似当日数据；命中则在 Quick Step 2 输出显式提示 `⚠️ 使用 N 天前榜单数据`。
- 7 天内无缓存 → `fetch_status: none`，Quick Step 1 **跳过** 反向规避，创意指纹「反向规避」字段填 `无当日数据`。

**消费（Quick Step 1）**：

- 方案生成时 **必须规避两平台共通 Top 5 热门套路关键词**；单平台榜单不强制规避。
- 被规避的关键词记入每套方案字段 `market_avoid`（数组），Quick Step 2 创意指纹消费。

## Quick Step 1：生成 3 套差异化方案

### 差异化约束

3 套方案必须在以下维度两两不同：
- **题材方向**：从题材集合（见 Deep Mode Step 1 的题材集合）中选 3 个不同大类。
- **角色设定**：主角性格/背景不重复（如成长型 vs 复仇型 vs 天才型）。
- **冲突模式**：核心冲突不雷同（如弱变强 vs 阴谋揭露 vs 守护底线）。
- **金手指类型**：避免 3 套都是系统流（如系统 vs 传承 vs 天赋 vs 重生记忆）。

### 命名规则

对每套方案中的角色名（主角、女主/核心配角）：

1. 从 `surnames.json` 按加权概率随机取姓氏。
2. 从 `given_names.json` 按方案风格匹配风格池，随机取 1-2 字组合为名。
3. 将完整姓名与 `blacklist.json` 的 male/female 列表做全匹配校验。
4. 若命中黑名单，丢弃并重新生成（最多重试 3 次，仍命中则换姓重试）。
5. 3 套方案之间的角色姓名不得重复。

### 每套方案必须包含

| 字段 | 说明 |
|------|------|
| 书名 | 吸引力优先，可带副标题 |
| 题材方向 | 从题材集合中选择（可复合 A+B） |
| 核心卖点 | 一句话，读者为什么要追 |
| 主角姓名 + 设定 | 姓名（命名系统生成）+ 2-3 句人设（含欲望、缺陷） |
| 女主/核心配角姓名 + 设定 | 姓名（命名系统生成）+ 1-2 句人设 |
| 核心冲突 | 全书主线冲突一句话 |
| 金手指概要 | 类型 + 能力 + 代价，或"无金手指" |
| 第一章爽点预览 | **必填 ≥50 字**（US-001）：描述金手指在第一章的具体收益场景（资源/击退/认可/地位/信息/危机解除），含视觉/感官特征。禁止仅写抽象收益。 |
| 前三章钩子概念 | 第 1/2/3 章各一句话钩子描述 |

### 输出格式

以编号列表展示，每套方案清晰标注 **方案 1 / 方案 2 / 方案 3**，内部按上述字段分项排列。示例结构：

```markdown
### 方案 1：《书名》

- **题材方向**：XX
- **核心卖点**：XX
- **主角**：姓名 — XX（欲望/缺陷）
- **女主/核心配角**：姓名 — XX
- **核心冲突**：XX
- **金手指**：XX（代价：XX）
- **第一章爽点预览**：XX（≥50 字，具体收益场景 + 视觉/感官特征）
- **前三章钩子**：
  1. 第1章：XX
  2. 第2章：XX
  3. 第3章：XX

#### 🧬 创意指纹
- **命中元规则**：M03 信息不对称（主角知未来小新闻） / M07 欲望悖论（越靠近越失去）
- **使用扰动对**：「民国租界」×「量子物理」 ；「丧葬师」×「直播带货」
- **金手指维度**：GF-1=1 / GF-2=1 / GF-3=0（信息类，代价可量化）
- **语言档位**：V1 文学狂野 —— 「江雾压城，像一口咽不下的铁」
- **反向规避**：修真升级流、赘婿打脸、系统签到（两平台共通 Top 5）
```

> 创意指纹总字数 ≤200 字；3 套方案的指纹必须在 `命中元规则` / `使用扰动对` / `语言档位` 三项中至少三项全不同。

展示完毕后，提示用户：

> 请选择：
> - 输入 **1/2/3** 选择对应方案
> - 输入混搭指令（如「1的书名 + 2的主角 + 3的冲突」）
> - 输入 **0** 重新随机生成 3 套全新方案

## Quick Step 1.5：金手指三重校验

参照 `references/creativity/golden-finger-rules.md`，对 Quick Step 1 生成的 3 套方案逐套自检金手指，输出 `gf_checks = [GF1, GF2, GF3]` 的 0/1 矩阵：

- **GF-1 非战力维度**：金手指作用维度必须落在 {信息 / 时间 / 情感 / 社交 / 认知 / 概率 / 感知 / 规则} 8 类之一；命中禁止词列表（修为暴涨/无限金币/系统签到/作弊器/外挂 等 ≥20 条）直接 GF1=0。
- **GF-2 代价可视化**：代价必须明确 / 可量化 / 可被反派利用，且前 10 章可见。模糊代价（如「消耗法力」「会疲劳」）判 GF2=0。
- **GF-3 一句话爆点**：20 字内讲清楚且触发「这也行？」惊讶感；含具体动作/代价/反直觉维度。

### 通过条件

每套方案 `sum(gf_checks) >= 2` 方可入选（三项通过二项即可）。

### 重抽与降档

- 未通过时回到 Quick Step 1 同一槽位重抽金手指，最多 5 次。
- 5 次仍未通过 → 触发档位降档（激进→平衡，平衡→保守；保守档不再降），用更保守参数重生成；降档事件写入 `gf_downgrade_log`，Quick Step 2 方案标题旁标注「⚠️ 金手指校验触发降档至 X 档」。
- 3 套方案各自独立降档，互不影响。

### 输出产物

- `gf_checks` 字段（每套方案一组 3 元 0/1 数组）—— Quick Step 2 创意指纹板块消费。
- `gf_downgrade_log` 数组（如空则省略）—— Quick Step 2 末尾汇总。

## Quick Step 1.6：语言风格三档分配

参照 `references/creativity/style-voice-levels.md`，对通过金手指校验的 3 套方案强制分配 V1 / V2 / V3 三档，禁止两套同档。

### 分配算法

1. 按种子 `stable_hash(timestamp + genre_tuple)` 固定 `[V1, V2, V3]` 洗牌顺序，依次赋值给方案 1/2/3。
2. 档位 1 保守：若分配到 V3 → 回退到 V1（`style_fallback: "V3→V1 (level=1)"` 写入日志），保持差异化。
3. 档位 4 疯批：三套方案中必须至少一套 V3，否则重新分配。
4. 题材适配度（见 style-voice-levels.md §八）仅作优先级参考，硬约束优先。

### 敏感词/粗口控制

- 每套方案产出 `vocabulary_allowlist`（L0 / L1 / L2 子集）。
- 档位 × 档位密度矩阵：
  - 档位 1 保守 = 0%（零 L1+）
  - 档位 2 平衡 ≈ 0.2%（L0 主力，L1 ≤0.05%）
  - 档位 3 激进 = 0.5%-0.8%（L2 仅 V3）
  - 档位 4 疯批 = 0.8%-1.5%（L2 仅 V3）
- L3 红线全档禁止，命中 → 方案整体重写。

### 输出字段（每套方案）

```
style_voice: "V1|V2|V3"
style_voice_name: "文学狂野|烟火接地气|江湖野气"
density_target: "0.2%"            # 字符串带百分号，便于日志打印
sample_line: "<5-15 字 voice 示例句>"
vocabulary_allowlist: ["L0", "L1"?, "L2"?]
```

以上字段由 Quick Step 2 创意指纹板块「语言档位」直接消费。

## Quick Step 1.7：书名与人名校验

对 Quick Step 1/1.5/1.6 产出的 3 套方案逐套做书名与人名的黑名单校验与修辞标签标注。

### 书名校验

1. 从 `book-title-patterns.json` 对应 V1/V2/V3 档位的桶里抽取模板作为候选（档位 4 疯批允许混抽高稀缺 V3 + V1）。
2. 候选书名对照 `blacklist.json.book_title_suffix_ban.tokens` 与 `book_title_prefix_ban.tokens` 做子串检测；命中任一立即丢弃重抽（最多 5 次）。
3. 最终书名输出 `title_rhetoric_tags`（多选自 7 种修辞），取自该模板 `rhetoric_tags`；若模板标签数 <1 需自行推断至少 1 个合法标签。
4. 3 套方案的 `title_rhetoric_tags` 两两不得完全相同（至少 1 个差异 tag）。

### 人名校验

1. 主角/核心配角名继续走 Quick Step 1 的 `surnames.json + given_names.json`（`given_names.json` 新增 `rough/smoky/jianghu` 桶，与 V1/V2/V3 档位映射：V1→rough、V2→smoky、V3→jianghu，默认从对应桶抽字）。
2. 若方案为 V3 档，核心绰号从 `nicknames.json` 挑选 `rarity ≥3` 且 `style_tags` 含 `jianghu` 的条目作为「主角外号」。
3. 全名命中 `blacklist.json.male/female` 列表 → 丢弃重抽。
4. 全名拆成「姓」与「名末字」，分别对照 `blacklist.json.name_combo_ban.surname_tokens × given_suffix_tokens` 笛卡儿积；命中任一组合直接丢弃重抽（即便不在 male/female 列表中）。
5. 3 套方案之间的角色姓名不得重复。

### 输出字段（每套方案）

```
title_rhetoric_tags: ["irony", "oxymoron"]          # 数组，≥1 且 ∈ rhetoric_enum
nickname?: "刀疤阿九"                                 # 仅 V3 档必填
name_checks:
  combo_ban_hit: false
  blacklist_hit: false
  retry_count: 0-5
```

未通过时同步写入 `name_retry_log`，由 Quick Step 2 末尾汇总。

## Quick Step 2：用户选择与方案确定

### 🧬 创意指纹板块规格（每套方案末尾必出）

对每套方案，在输出末尾追加固定结构的「🧬 创意指纹」板块，总字数 ≤200 字，Markdown 列表形式，5 个字段顺序固定：

| 字段 | 来源 | 说明 |
|------|------|------|
| **命中元规则** | `meta_rules_hit`（Quick Step 1 产出） | 列出 M01-M10 中命中的具体编号 + 一句话说明，≥1 条（档位 1）/ ≥2（档位 2）/ ≥3（档位 3）/ ≥5（档位 4），多条用 ` / ` 分隔。 |
| **使用扰动对** | `perturbation_pairs`（Quick Step 1） | 至少 2 对（档位 1 可为 1 对）；格式「`seed_a × seed_b`」，多对用 `；` 分隔。 |
| **金手指维度** | `gf_checks`（Quick Step 1.5） | `GF-1=<0/1> / GF-2=<0/1> / GF-3=<0/1>`；附一句话解释通过的维度（如「信息类，代价可量化」）。 |
| **语言档位** | `style_voice + sample_line`（Quick Step 1.6） | 格式「`V1/V2/V3 <风格名> —— 「<sample_line>」`」。 |
| **反向规避** | `market_avoid`（Quick Step 0 WebSearch） | 列出本方案显式规避的两平台共通 Top 5 套路关键词；`fetch_status=none` 时填「无当日数据」。 |

**硬约束：3 套方案的创意指纹必须体现差异性** —— 在以下三项中至少三项全不同：
- `命中元规则` 的编号集合两两无交集，或交集 ≤1（档位 ≥3 要求严格两两不同）。
- `使用扰动对` 的 seed 条目两两完全不重叠（Quick Step 1 已由 perturbation-engine.md 硬去重）。
- `语言档位` 两两不同（Quick Step 1.6 已硬约束 V1/V2/V3 各占一套）。

违反任一项 → 退回 Quick Step 1 重抽失败维度。

### 选择模式

根据用户输入，进入对应分支：

**A) 直接选择（输入 1/2/3）**
- 将对应编号的方案作为最终方案，直接进入 Quick Step 3。

**B) 混搭（如「1的书名 + 2的主角 + 3的冲突」）**
- 解析用户混搭指令，从指定方案中提取对应字段。
- 未指定的字段从用户选中最多的方案中继承。
- 合并后展示最终方案摘要，请求用户确认：
  > 混搭方案如下：[展示合并结果]
  > 确认？（输入 Y 确认，或继续修改）
- 用户确认后进入 Quick Step 3。

**C) 重新随机（输入 0 或「重新随机」）**
- 回到 Quick Step 1，重新生成 3 套全新方案。
- 不限重随次数。
- 新方案必须与上一轮方案在题材方向上不同（尽量避免重复）。

### 补充采集（可选）

方案确认后，检查以下字段是否已足够详细，不足则快速追问（每个字段最多 1 轮）：
- 目标规模（总字数/章数）— 若未指定，建议默认值并确认
- 主角欲望/缺陷 — 方案中已包含简要描述，确认是否需要细化
- 世界规模 — 从方案题材自动推断默认值，确认即可

## Quick Step 3：自动填充与初始化

方案确定后，自动执行以下操作：

### 1) 映射到内部数据模型

将最终方案字段映射到 Deep Mode 的内部数据模型（见 §内部数据模型）：

| 方案字段 | 映射目标 |
|----------|----------|
| 书名 | `project.title` |
| 题材方向 | `project.genre` |
| 核心卖点 | `constraints.core_selling_points[0]` |
| 主角姓名 | `protagonist.name` |
| 主角设定（欲望） | `protagonist.desire` |
| 主角设定（缺陷） | `protagonist.flaw` |
| 女主/核心配角姓名 | `relationship.heroine_names[0]` 或 `relationship.co_protagonists[0]` |
| 核心冲突 | `project.core_conflict` |
| 金手指概要 | `golden_finger.type` + `golden_finger.name` |
| 第一章爽点预览 | `golden_finger.first_payoff`（若未达 80 字，自动扩写或追问补齐以通过充分性闸门 5a）；同时派生 `golden_finger.visual_signature`（从预览中抽取视觉/感官描写，不足 50 字则追问） |
| 前三章钩子 | `constraints.opening_hook` |

未覆盖的字段（如 `world.scale`、`world.power_system_type`）从题材自动推断合理默认值。

**US-001 Quick 模式补充填充**（充分性闸门 5a 所需）：
- `golden_finger.first_payoff`：由「第一章爽点预览」扩写至 ≥80 字（追问用户或自动展开具体收益形式）。
- `golden_finger.visual_signature`：从预览中抽取视觉/感官片段，若 <50 字则由系统补齐并请用户确认。
- `golden_finger.escalation_ladder`：基于金手指类型自动生成三阶段默认梯度（ch1 / ch10 / late_game），各写一句话，展示给用户确认（Y/N）。
- `golden_finger.payoff_self_check`：Quick 模式下自动填入「已通过预览字段校验」，若用户修改预览则重置该字段要求用户重新回答。

**US-003 Quick 模式第一章爽点规格自动填充**（充分性闸门 5b 所需）：
- 在 `golden_finger.first_payoff` / `visual_signature` 已补齐后，自动合并派生 `ch1_cool_point_spec` 四字段（规则同 Deep Mode Step 3+++）。
- `involved_characters` 默认取 `protagonist.name` + `relationship.heroine_names[0]`（或首个核心配角），若存在对抗型爽点则额外追加临时对手代号。
- `payoff_form` 基于 `first_payoff` 关键词匹配（含「钱/资源/宝物」→资源获取；「击退/震慑/重创」→敌人击退；「刮目相看/认可/赞叹」→他人认可；「上位/晋升/拜入」→地位提升；「揭穿/窥见/看懂」→信息解锁）；匹配失败时默认「敌人击退」并提示用户校正。
- `reader_emotion_target` 由 `payoff_self_check` 衍生，若缺失则使用模板「第一章末读者因 <主角><payoff_form> 的具体画面，产生<爽快/惊艳/期待>的情绪」。
- 生成后以紧凑表格一次性展示，请求 Y/N 确认；回答 N 则进入逐字段微调（最多 3 轮）；标记 `ch1_cool_point_spec.auto_generated=true` 与 `user_confirmed` 的最终取值。

**US-002 Quick 模式角色语言档案自动填充**（充分性闸门 3a 所需）：
- 基于方案中的「主角设定（含性格/背景）」与「女主/核心配角设定」，按 Deep Mode 的「自动推荐规则」生成 `protagonist.voice_profile` 与 `relationship.voice_profiles[<core_partner_name>]` 两份完整档案。
- 自动填充时，标记 `voice_profile.auto_generated=true`。
- 生成后以紧凑表格展示给用户，请求一次性 Y/N 确认；用户回答 N 则进入逐字段微调（最多 5 轮），完成后再继续 Quick Step 3 的剩余流程。

### 2) 填充 `.ink/state.json` 和 `.ink/preferences.json`

执行与 Deep Mode 相同的 `init_project.py` 脚本（见 §执行生成），传入映射后的参数。

### 3) 对接后续流程

初始化完成后，进入与 Deep Mode 相同的后续流程：
- 写入 `idea_bank.json`
- Patch 总纲
- 验证与交付
- RAG 配置引导

即：从 §执行生成 的"1) 运行初始化脚本"开始，与 Deep Mode 共用同一套生成、验证、失败处理逻辑。

---

# Deep Mode（苏格拉底式深度采集）

## 目标

- 通过结构化交互收集足够信息，避免“先生成再返工”。
- 产出可落地项目骨架：`.ink/state.json`、`.ink/preferences.json`、`.ink/golden_three_plan.json`、`设定集/*`、`大纲/总纲.md`、`.ink/idea_bank.json`。
- 保证后续 `/ink-plan` 与 `/ink-write` 可直接运行。

## 执行原则

1. 先收集，再生成；未过充分性闸门，不执行 `init_project.py`。
2. 分波次提问，每轮只问“当前缺失且会阻塞下一步”的信息。
3. 允许调用 `Read/Grep/Bash/Task/AskUserQuestion/WebSearch/WebFetch` 辅助收集。
4. 用户已明确的信息不重复问；冲突信息优先让用户裁决。
5. Deep 模式优先完整性，允许慢一点，但禁止漏关键字段。

## 引用加载等级（strict, lazy）

采用分级加载，避免一次性灌入全部资料：

- L0：未确认任务前，不预加载参考。
- L1：每个阶段仅加载该阶段“必读”文件。
- L2：仅在题材、金手指、创意约束触发条件满足时加载扩展参考。
- L3：市场趋势类、时效类资料仅在用户明确要求时加载。

路径约定：
- `references/...` 相对当前 skill 目录（`${CLAUDE_PLUGIN_ROOT}/skills/ink-init/references/...`）。
- `templates/...` 相对插件根目录（`${CLAUDE_PLUGIN_ROOT}/templates/...`）。

默认加载清单：
- L1（启动前）：`references/genre-tropes.md`
- L2（按需）：
  - 题材模板：`templates/genres/{genre}.md`
  - 金手指：`../../templates/golden-finger-templates.md`
  - 世界观：`references/worldbuilding/faction-systems.md`
  - 创意约束：按下方“逐文件引用清单”触发加载
- L3（显式请求）：
  - `references/creativity/market-trends-2026.md`

## References（逐文件引用清单）

### 根目录

- `references/genre-tropes.md`
  - 用途：Step 1 题材归一化、题材特征提示。
  - 触发：所有项目必读。
- `references/system-data-flow.md`
  - 用途：初始化产物与后续 `/plan`、`/write` 的数据流一致性检查。
  - 触发：Step 0 预检必读。

### worldbuilding

- `references/worldbuilding/character-design.md`
  - 用途：Step 2 角色维度补问（目标、缺陷、动机、反差）。
  - 触发：用户人物信息抽象或扁平时加载。
- `references/worldbuilding/faction-systems.md`
  - 用途：Step 4 势力格局与组织层级设计。
  - 触发：Step 4 默认加载。
- `references/worldbuilding/power-systems.md`
  - 用途：Step 4 力量体系类型与边界定义。
  - 触发：涉及修仙/玄幻/高武/异能时加载。
- `references/worldbuilding/setting-consistency.md`
  - 用途：Step 6 一致性复述前做设定冲突检查。
  - 触发：Step 6 默认加载。
- `references/worldbuilding/world-rules.md`
  - 用途：Step 4 世界规则与禁忌项收束。
  - 触发：Step 4 默认加载。

### creativity

- `references/creativity/creativity-constraints.md`
  - 用途：Step 5 创意约束包主 schema。
  - 触发：Step 5 必读。
- `references/creativity/category-constraint-packs.md`
  - 用途：Step 5 按平台/题材选择约束包模板。
  - 触发：Step 5 必读。
- `references/creativity/creative-combination.md`
  - 用途：复合题材（A+B）融合规则。
  - 触发：用户选择复合题材时加载。
- `references/creativity/inspiration-collection.md`
  - 用途：用户卡住时提供卖点/钩子候选。
  - 触发：Step 1 或 Step 5 卡顿时加载。
- `references/creativity/selling-points.md`
  - 用途：Step 5 卖点生成与筛选。
  - 触发：Step 5 必读。
- `references/creativity/market-positioning.md`
  - 用途：目标读者/平台定位与商业化语义统一。
  - 触发：Step 1 用户提及平台或商业目标时加载。
- `references/creativity/market-trends-2026.md`
  - 用途：时间敏感市场趋势参考。
  - 触发：仅用户明确要求“参考当下趋势”时加载。
- `references/creativity/anti-trope-xianxia.md`
  - 用途：反套路库（修仙/玄幻/高武/西幻/无限流）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-urban.md`
  - 用途：反套路库（都市异能/都市日常/都市脑洞/电竞/直播文）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-game.md`
  - 用途：反套路库（游戏体育/科幻/系统流）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-rules-mystery.md`
  - 用途：反套路库（规则怪谈/克苏鲁）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-romance.md`
  - 用途：反套路库（言情/婚恋/霸总/替身/豪门/宫斗言情/青春甜宠/民国言情/多子多福/种田/狗血言情）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-history.md`
  - 用途：反套路库（历史古代/历史脑洞/抗战谍战/年代/历史穿越）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-apocalypse.md`
  - 用途：反套路库（末世/废土/灾变）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-suspense.md`
  - 用途：反套路库（悬疑脑洞/悬疑灵异/女频悬疑）。
  - 触发：题材命中对应映射时加载。
- `references/creativity/anti-trope-realistic.md`
  - 用途：反套路库（现实题材/黑暗题材/职场婚恋）。
  - 触发：题材命中对应映射时加载。

## 工具策略（按需）

- `Read/Grep`：读取项目上下文与参考文件（`README.md`、`CLAUDE.md`、`templates/genres/*`、`references/*`）。
- `Bash`：执行 `init_project.py`、文件存在性检查、最小验证命令。
- `Task`：拆分并行子任务（如题材映射、约束包候选生成、文件验证）。
- `AskUserQuestion`：用于关键分歧裁决、候选方案选择、最终确认。
- `WebSearch`：用于检索最新市场趋势、平台风向、题材数据（可带域名过滤）。
- `WebFetch`：用于抓取已确定来源页面内容并做事实核验。
- 外部检索触发条件：
  - 用户明确要求参考市场趋势或平台风向；
  - 创意约束需要“时间敏感依据”；
  - 对题材信息存在明显不确定。

## 交互流程（Deep Mode）

### Step 0：预检与上下文加载

环境设置（bash 命令执行前）：
```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```

必须做：
- 确认当前目录可写。
- 解析脚本目录并确认入口存在（仅支持插件目录）：
  - 固定路径：`${CLAUDE_PLUGIN_ROOT}/scripts`
  - 入口脚本：`${SCRIPTS_DIR}/ink.py`
- 建议先打印解析结果，避免写到错误目录：
  - `python3 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where`
- 加载最小参考：
  - `references/system-data-flow.md`（用于校对 init 产物与 plan/write 输入链路）
  - `references/genre-tropes.md`
  - `templates/genres/`（仅在用户选定题材后按需读取）

输出：
- 进入 Deep 采集前的“已知信息清单”和“待收集清单”。

### Step 1：故事核与商业定位

收集项（必收）：
- 书名（可先给工作名）
- 题材（支持 A+B 复合题材）
- 目标规模（总字数或总章数）
- 一句话故事
- 核心冲突
- 开篇钩子（尤其第 1 章前 300 字的触发点）
- 目标读者/平台

题材集合（用于归一化与映射）：
- 玄幻修仙类：修仙 | 系统流 | 高武 | 西幻 | 无限流 | 末世 | 科幻
- 都市现代类：都市异能 | 都市日常 | 都市脑洞 | 现实题材 | 黑暗题材 | 电竞 | 直播文
- 言情类：古言 | 宫斗宅斗 | 青春甜宠 | 豪门总裁 | 职场婚恋 | 民国言情 | 幻想言情 | 现言脑洞 | 女频悬疑 | 狗血言情 | 替身文 | 多子多福 | 种田 | 年代
- 特殊题材：规则怪谈 | 悬疑脑洞 | 悬疑灵异 | 历史古代 | 历史脑洞 | 游戏体育 | 抗战谍战 | 知乎短篇 | 克苏鲁

交互方式：
- 优先让用户自由描述，再二次结构化确认。
- 若用户卡住，给 2-4 个候选方向供选。

### Step 2：角色骨架与关系冲突

收集项（必收）：
- 主角姓名
- 主角欲望（想要什么）
- 主角缺陷（会害他付代价的缺陷）
- 主角结构（单主角/多主角）
- 感情线配置（无/单女主/多女主）
- 反派分层（小/中/大）与镜像对抗一句话

收集项（可选）：
- 主角原型标签（成长型/复仇型/天才流等）
- 多主角分工

#### Step 2+ 角色语言特征档案（必收，US-002）

为「主角 + 核心配角（女主/男主搭档/核心反派一名）」的每位角色，建立 `voice_profile` 子字段组，必须全部填写：

1. **`speech_vocabulary_level`**：词汇层级，从下列枚举中选一项 — `口语化` / `标准` / `文雅` / `古风` / `混合`。
2. **`preferred_sentence_length`**：偏好句长，从下列枚举中选一项 — `短促` / `中等` / `冗长` / `跳跃（短长交错）`。
3. **`verbal_tics`**：口头禅清单（**最多 3 个**，可为空数组）。每条不超过 8 字，要求是该角色高频复用且能让读者一眼认出来的语气词/连接词/自我标签。
4. **`emotional_tell`**：情绪外显规则（一句话）— 描述当此角色处于愤怒/羞愧/紧张等高情绪场景时，其语言会发生的具体变化（变短/变长/破句/失语/突然引经据典/方言冒头/称谓切换 等）。
5. **`taboo_topics`**：禁言话题列表 — 此角色绝不会主动提起或在对话中尽量回避的话题（家人/某段过往/某位故人/某种身份），用于对话审查时识别角色破功。

**采集策略**：
- 优先让用户自己描述各角色「最像 ta 自己的一句话」，再据此结构化抽取。
- 若用户表示「不知道 / 想不出来」，**系统必须基于已收集的 `性格 + 年龄 + 职业 + 背景 + 出身阶层` 自动生成推荐档案**，并以 `Y/N` 模式请求确认（用户回答 N 则进入逐字段微调）。
- 自动推荐规则参考（最小集）：
  - `性格外向 + 年轻` → 句长「中等」、口语化、口头禅 1-2 个
  - `性格内向 / 谨慎` → 句长「短促」、词汇「标准」、口头禅 0-1 个
  - `古风背景 / 修仙长者` → 词汇「古风」或「文雅」、句长「中等」或「冗长」、emotional_tell 多为「失语 / 称谓切换」
  - `市井 / 江湖` → 词汇「口语化」、口头禅可含俚语
  - `学者 / 科研 / 谋士` → 词汇「文雅」、句长「冗长」、情绪激动时反向「破句」
- 至少为「主角 + 1 名核心配角」完整填写；其余次要配角可在后续 plan 阶段按需补齐。

收集后，所有 `voice_profile` 必须随主角卡一起在 `Step 6 一致性复述` 阶段展示给用户最终确认。

### Step 3：金手指与兑现机制

收集项（必收）：
- 金手指类型（可为“无金手指”）
- 名称/系统名（无则留空）
- 风格（硬核/诙谐/黑暗/克制等）
- 可见度（谁知道）
- 不可逆代价（必须有代价或明确“无+理由”）
- 成长节奏（慢热/中速/快节奏）

收集项（条件必收）：
- 若为系统流：系统性格、升级节奏
- 若为重生：重生时间点、记忆完整度
- 若为传承/器灵：辅助边界与出手限制

#### Step 3+ 爽点前置收益场景（必收，US-001）

在完成上述金手指基础信息后，追加三项爽点前置字段，必须全部填写：

1. **`golden_finger_first_payoff`**（≥80 字）
   - 描述金手指在**第一章**为主角带来的具体收益场景：什么能力被触发、触发后主角获得了什么具体有形的好处（资源/敌人击退/他人认可/地位提升/信息解锁/危机解除等）。
   - 禁止使用抽象词汇作为收益（理解/领悟/感悟/知道了/发现了/明白了/意识到/成长了/坚强了）。
   - 若用户给出的描述不足 80 字或仅提及抽象收益，继续追问直至满足。
2. **`golden_finger_visual_signature`**（≥50 字）
   - 描述金手指激活时的视觉/感官特征：画面是什么、有无光效/声响/触感/气味等感官锚点。此字段将在 write 阶段用于感官描写注入。
3. **`golden_finger_escalation_ladder`**
   - 能力阶梯三段描述，必须显式给出：
     - 第 1 章：此时能做什么、有什么边界。
     - 第 10 章前后：升级后能做什么。
     - 后期（主线中后段）：最终形态能做什么。
   - 禁止仅写“逐步提升”“循序渐进”之类空泛表述。

#### Step 3++ 读者爽感自检（必问）

上述三项收集完毕后，再追加以下强制追问（用户必须回答，不能跳过）：

> 「如果读者看完第一章，仍然不知道金手指究竟能怎么爽（不知道它能解决什么问题、不知道它带来什么具体好处），你会怎么改？」

- 将用户的回答作为 `golden_finger_payoff_self_check` 字段写入内部数据模型。
- 若用户表示“不知道如何改”或给出空洞回答，系统根据已收集的 `golden_finger_first_payoff` 生成 2-3 条强化建议供用户选择。
- 用户给出有效答复后方可进入 Step 4。

#### Step 3+++ 第一章爽点规格派生（US-003）

完成 Step 3+ / Step 3++ 后，系统基于已收集字段自动派生**第一章爽点规格** `ch1_cool_point_spec`，该对象将被写入 `.ink/golden_three_plan.json` 的 `chapters["1"].ch1_cool_point_spec`，供 `/ink-plan` 与 `/ink-write` 阶段消费。

派生规则（由系统生成草案，再交由用户 Y/N 确认）：

- `scene_description`（≥100 字，必填）：
  - 将 `golden_finger.first_payoff` 与 `golden_finger.visual_signature` 合并为一段完整的第一章爽点场景描述：交代触发位置、触发动作、能力画面/感官锚点、具体收益结果。
  - 若合并后 <100 字，系统自动补齐缺失要素（环境/对手/观众反应）再提交确认；仍不足则追问用户。
  - 禁止使用纯抽象收益词（理解/领悟/感悟/知道了/发现了/明白了/意识到/成长了/坚强了）。
- `involved_characters`（字符串数组，必填）：
  - 默认从 `protagonist.name` + `relationship.heroine_names[0]` + `relationship.co_protagonists[0]` 中抽取非空项。
  - 至少 1 项；若爽点为对抗型则必须补充反派/对手名（可为临时代号）。
- `payoff_form`（枚举，必填）：
  - 候选值：`资源获取` / `敌人击退` / `他人认可` / `地位提升` / `信息解锁`。
  - 系统基于 `golden_finger.first_payoff` 的关键词自动匹配；匹配不确定时展示候选列表供用户选择。
- `reader_emotion_target`（≥30 字，必填）：
  - 描述第一章末读者应产生的情绪反应（例：爽快/惊艳/期待/共情）及其触发点。
  - 系统依据 `golden_finger.payoff_self_check` 的回答生成初稿。

**用户确认（Y/N 必走）**：

1. 系统以紧凑格式展示 `ch1_cool_point_spec` 草案的 4 个字段。
2. 用户回答 `Y` → 写入 `golden_three_plan.json`，进入 Step 4。
3. 用户回答 `N` → 进入逐字段修改（最多 3 轮）；任一字段修改后必须重新校验长度与枚举约束，通过后再次请求确认。
4. 未经用户确认前，禁止执行生成阶段的 `golden_three_plan.json` 写入。

### Step 4：世界观与力量规则

收集项（必收）：
- 世界规模（单城/多域/大陆/多界）
- 力量体系类型
- 势力格局
- 社会阶层与资源分配

收集项（题材相关）：
- 货币体系与兑换规则
- 宗门/组织层级
- 境界链与小境界

### Step 5：创意约束包（差异化核心）

流程：
1. 基于题材映射加载反套路库（最多 2 个主相关库）。
2. 生成 2-3 套创意包，每套包含：
   - 一句话卖点
   - 反套路规则 1 条
   - 硬约束 2-3 条
   - 主角缺陷驱动一句话
   - 反派镜像一句话
   - 开篇钩子
3. **核心主题提炼**（新增）：
   - 询问用户："用1-3个关键词描述这本书的核心主题（如'力量的代价'、'救赎'、'家的意义'）"
   - 这些主题将贯穿全书，系统会自动追踪主题在各章的呈现情况，防止主题漂移
   - 写入 `state.json.project_info.themes` 数组
   - 若用户跳过，默认为空（主题追踪功能不启用）
4. 三问筛选：
   - 为什么这题材必须这么写？
   - 换成常规主角会不会塌？
   - 卖点能否一句话讲清且不撞模板？
4. 展示五维评分（详见 `references/creativity/creativity-constraints.md` 的 `8.1 五维评分`），辅助用户决策。
5. 用户选择最终方案，或拒绝并给出原因。

备注：
- 若用户要求“贴近当下市场”，可触发外部检索并标注时间戳。

### Step 6：一致性复述与最终确认

必须输出“初始化摘要草案”并让用户确认：
- 故事核（题材/一句话故事/核心冲突）
- 主角核（欲望/缺陷）
- 金手指核（能力与代价）
- 世界核（规模/力量/势力）
- 创意约束核（反套路 + 硬约束）

确认规则：
- 用户未明确确认，不执行生成。
- 若用户仅改局部，回到对应 Step 最小重采集。

### RAG 配置引导（v10.6 新增）

项目初始化成功后，提示用户配置 Embedding API 以启用向量检索增强：

**提示文案**：
> 推荐配置向量检索（RAG）：ink-writer 内置了完整的语义检索系统，可以在写作时自动召回相关章节片段，大幅提升长篇小说的记忆一致性。
>
> 配置方式（选一个）：
> 1. **ModelScope（免费）**：
>    ```
>    echo "EMBED_API_KEY=你的ModelScope密钥" >> ~/.claude/ink-writer/.env
>    ```
>    获取密钥：https://modelscope.cn/my/myaccesstoken
>
> 2. **OpenAI**：
>    ```
>    echo "EMBED_BASE_URL=https://api.openai.com/v1" >> ~/.claude/ink-writer/.env
>    echo "EMBED_MODEL=text-embedding-3-small" >> ~/.claude/ink-writer/.env
>    echo "EMBED_API_KEY=你的OpenAI密钥" >> ~/.claude/ink-writer/.env
>    ```
>
> 3. **跳过**：不影响写作，系统自动使用BM25关键词检索（精度略低但完全可用）。
>
> 配置后运行 `python ink.py rag stats` 验证。

**执行规则**：
- 仅在项目初始化成功后显示此提示
- 不阻断任何流程（纯建议性质）
- 用户选择跳过时不再提醒

## 内部数据模型（初始化收集对象）

```json
{
  "project": {
    "title": "",
    "genre": "",
    "target_words": 0,
    "target_chapters": 0,
    "one_liner": "",
    "core_conflict": "",
    "target_reader": "",
    "platform": "",
    "themes": []
  },
  "protagonist": {
    "name": "",
    "desire": "",
    "flaw": "",
    "archetype": "",
    "structure": "单主角",
    "voice_profile": {
      "speech_vocabulary_level": "",
      "preferred_sentence_length": "",
      "verbal_tics": [],
      "emotional_tell": "",
      "taboo_topics": []
    }
  },
  "relationship": {
    "heroine_config": "",
    "heroine_names": [],
    "heroine_role": "",
    "co_protagonists": [],
    "co_protagonist_roles": [],
    "antagonist_tiers": {},
    "antagonist_level": "",
    "antagonist_mirror": "",
    "voice_profiles": {}
  },
  "golden_finger": {
    "type": "",
    "name": "",
    "style": "",
    "visibility": "",
    "irreversible_cost": "",
    "growth_rhythm": "",
    "first_payoff": "",
    "visual_signature": "",
    "escalation_ladder": {
      "ch1": "",
      "ch10": "",
      "late_game": ""
    },
    "payoff_self_check": ""
  },
  "ch1_cool_point_spec": {
    "scene_description": "",
    "involved_characters": [],
    "payoff_form": "",
    "reader_emotion_target": "",
    "user_confirmed": false
  },
  "world": {
    "scale": "",
    "factions": "",
    "power_system_type": "",
    "social_class": "",
    "resource_distribution": "",
    "currency_system": "",
    "currency_exchange": "",
    "sect_hierarchy": "",
    "cultivation_chain": "",
    "cultivation_subtiers": ""
  },
  "constraints": {
    "anti_trope": "",
    "hard_constraints": [],
    "core_selling_points": [],
    "opening_hook": ""
  }
}
```

## 充分性闸门（必须通过）

未满足以下条件前，禁止执行 `init_project.py`：

1. 书名、题材（可复合）已确定。
2. 目标规模可计算（字数或章数至少一个）。
3. 主角姓名 + 欲望 + 缺陷完整。
3a. **角色语言特征档案齐备**（US-002 硬阻断）：
   - `protagonist.voice_profile` 中 `speech_vocabulary_level`、`preferred_sentence_length`、`emotional_tell` 三个字段非空；`verbal_tics` 与 `taboo_topics` 允许为空数组但必须显式存在。
   - 至少 1 名核心配角（`relationship.heroine_names[0]` 或 `relationship.co_protagonists[0]`）在 `relationship.voice_profiles` 中存在同结构条目，且上述三项关键字段非空。
   - 用户拒绝填写时，必须有自动推荐档案 + 用户 Y 确认记录（写入 `voice_profile.auto_generated=true`）。
   - 未通过此闸门 → 阻断进入 `/ink-plan` 阶段。
4. 世界规模 + 力量体系类型完整。
5. 金手指类型已确定（允许“无金手指”）。
5a. **金手指爽点前置字段齐备**（US-001 硬阻断）：
   - `golden_finger.first_payoff` 非空且 ≥ 80 字，且不含纯抽象收益词（理解/领悟/感悟/知道了/发现了/明白了/意识到/成长了/坚强了）。
   - `golden_finger.visual_signature` 非空且 ≥ 50 字。
   - `golden_finger.escalation_ladder.ch1` / `ch10` / `late_game` 三项均非空。
   - `golden_finger.payoff_self_check` 非空（读者爽感自检已回答）。
   - 若 `golden_finger.type` 为「无金手指」，允许上述字段留空，但必须显式标记 `type="无金手指"` 且在总纲中补充“无金手指兑现路径”说明。
   - 未通过此闸门 → 阻断进入 `/ink-plan` 阶段。
5b. **第一章爽点规格 `ch1_cool_point_spec` 已确认**（US-003 硬阻断）：
   - `scene_description` 非空且 ≥100 字，不含抽象收益词黑名单；
   - `involved_characters` 至少 1 项；
   - `payoff_form` ∈ {资源获取, 敌人击退, 他人认可, 地位提升, 信息解锁}；
   - `reader_emotion_target` 非空且 ≥30 字；
   - `user_confirmed=true`（必须经过 Step 3+++ 的 Y/N 确认步骤）。
   - 若 `golden_finger.type="无金手指"`，本闸门跳过但必须写入占位说明 `scene_description="[无金手指方案] 以 <具体手段> 交付第一章兑现"`。
   - 未通过此闸门 → 阻断写入 `.ink/golden_three_plan.json`。
6. 创意约束已确定：
   - 反套路规则 1 条
   - 硬约束至少 2 条
   - 或用户明确拒绝并记录原因。

## 项目目录安全规则（必须）

- `project_root` 必须由书名安全化生成（去非法字符，空格转 `-`）。
- 若安全化结果为空或以 `.` 开头，自动前缀 `proj-`。
- 禁止在插件目录下生成项目文件（`${CLAUDE_PLUGIN_ROOT}`）。

## 执行生成

### 1) 运行初始化脚本

```bash
python3 "${SCRIPTS_DIR}/ink.py" init \
  "{project_root}" \
  "{title}" \
  "{genre}" \
  --protagonist-name "{protagonist_name}" \
  --target-words {target_words} \
  --target-chapters {target_chapters} \
  --golden-finger-name "{gf_name}" \
  --golden-finger-type "{gf_type}" \
  --golden-finger-style "{gf_style}" \
  --core-selling-points "{core_points}" \
  --protagonist-structure "{protagonist_structure}" \
  --heroine-config "{heroine_config}" \
  --heroine-names "{heroine_names}" \
  --heroine-role "{heroine_role}" \
  --co-protagonists "{co_protagonists}" \
  --co-protagonist-roles "{co_protagonist_roles}" \
  --antagonist-tiers "{antagonist_tiers}" \
  --world-scale "{world_scale}" \
  --factions "{factions}" \
  --power-system-type "{power_system_type}" \
  --social-class "{social_class}" \
  --resource-distribution "{resource_distribution}" \
  --gf-visibility "{gf_visibility}" \
  --gf-irreversible-cost "{gf_irreversible_cost}" \
  --currency-system "{currency_system}" \
  --currency-exchange "{currency_exchange}" \
  --sect-hierarchy "{sect_hierarchy}" \
  --cultivation-chain "{cultivation_chain}" \
  --cultivation-subtiers "{cultivation_subtiers}" \
  --protagonist-desire "{protagonist_desire}" \
  --protagonist-flaw "{protagonist_flaw}" \
  --protagonist-archetype "{protagonist_archetype}" \
  --antagonist-level "{antagonist_level}" \
  --target-reader "{target_reader}" \
  --platform "{platform}" \
  --opening-hook "{opening_hook}"
```

### 2) 写入 `idea_bank.json`

写入 `.ink/idea_bank.json`：

```json
{
  "selected_idea": {
    "title": "",
    "one_liner": "",
    "anti_trope": "",
    "hard_constraints": []
  },
  "constraints_inherited": {
    "anti_trope": "",
    "hard_constraints": [],
    "protagonist_flaw": "",
    "antagonist_mirror": "",
    "opening_hook": ""
  }
}
```

### 3) Patch `golden_three_plan.json`（US-003）

`init_project.py` 生成 `.ink/golden_three_plan.json` 之后，将 §内部数据模型 中的 `ch1_cool_point_spec` 写入 `chapters["1"].ch1_cool_point_spec`：

```json
{
  "chapters": {
    "1": {
      "ch1_cool_point_spec": {
        "scene_description": "",
        "involved_characters": [],
        "payoff_form": "",
        "reader_emotion_target": "",
        "user_confirmed": true,
        "auto_generated": false,
        "derived_from": ["golden_finger.first_payoff", "golden_finger.visual_signature"]
      }
    }
  }
}
```

约束：
- 仅在充分性闸门 5b 通过后写入；未通过则以原子失败回退并提示用户回到 Step 3+++。
- 再次运行 `/ink-init` 时，若用户未显式修改爽点字段，保持现有 `ch1_cool_point_spec` 不变（幂等）；若 `first_payoff` 或 `visual_signature` 变更，重置 `user_confirmed=false` 并重走 Step 3+++ 确认。

### 4) Patch 总纲

必须补齐：
- 故事一句话
- 核心主线 / 核心暗线
- 创意约束（反套路、硬约束、主角缺陷、反派镜像）
- 反派分层
- 关键爽点里程碑（2-3 条）

## 验证与交付

执行检查：

```bash
test -f "{project_root}/.ink/state.json"
test -f "{project_root}/.ink/preferences.json"
test -f "{project_root}/.ink/golden_three_plan.json"
find "{project_root}/设定集" -maxdepth 1 -type f -name "*.md"
test -f "{project_root}/大纲/总纲.md"
test -f "{project_root}/.ink/idea_bank.json"
```

成功标准：
- `state.json` 存在且关键字段不为空（title/genre/target_words/target_chapters）。
- `preferences.json` 已开启 `opening_strategy.golden_three_enabled=true`。
- `golden_three_plan.json` 已生成第 1-3 章承诺卡，且 `chapters["1"].ch1_cool_point_spec` 四字段齐备、`user_confirmed=true`（US-003）。
- 设定集核心文件存在：`世界观.md`、`力量体系.md`、`主角卡.md`、`金手指设计.md`。
- `总纲.md` 已填核心主线与约束字段。
- `idea_bank.json` 已写入且与最终选定方案一致。

## 失败处理（最小回滚）

触发条件：
- 关键文件缺失；
- 总纲关键字段缺失；
- 约束启用但 `idea_bank.json` 缺失或内容不一致。

恢复流程：
1. 仅补缺失字段，不全量重问。
2. 仅重跑最小步骤：
   - 文件缺失 -> 重跑 `init_project.py`；
   - 总纲缺字段 -> 只 patch 总纲；
   - idea_bank 不一致 -> 只重写该文件。
3. 重新验证，全部通过后结束。
