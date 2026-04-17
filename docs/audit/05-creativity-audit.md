# US-005 创意生成系统审查（v13.8.0 ink-init --quick）

> **审计日期**：2026-04-17  
> **项目根**：`/Users/cipher/AI/ink/ink-writer`  
> **版本**：v13.8.0（`ink-init --quick` 创意架构级升级 + Phase-Seed-1 10 批种子库 v2.0 收官）  
> **审计范围**：三层创意架构（元规则 M01-M11 / 种子库 v2.0 / 扰动引擎）、金手指三重硬约束、4 档激进度 × 3 档语言风格分档、命名素材库（绰号/书名/陈词黑名单）、双平台榜单 90 天缓存。  
> **模式**：只读，代码证据优先（不接受"文档说有"）。

---

## Executive Summary

v13.8 创意系统是一套 **"prompt-grade 结构化"** 体系：数据层（种子库 v2.0 1000 条、命名素材库、元规则文档、schema）齐整且有 Draft-07 JSON Schema + pytest 静态校验兜底；**但所有"引擎"类组件（扰动对抽取算法、金手指三重校验、V1/V2/V3 档位分配、黑名单比对、90 天缓存清理）没有任何 Python 实现**，全部以 markdown 伪代码形式写在 `SKILL.md` 与 references 里，由 Claude LLM 按文档自执行。

这不是 "硬编码 prompt 糊一下"——因为数据层（schema 校验 + 1000 条有标签种子 + 110 绰号 + 170 书名模板 + 多层黑名单 + 元规则映射表）都是**真结构化**、可独立校验。但也绝不是传统意义的"系统"——**引擎侧零代码**，失败时没有 fail-safe，只能靠 LLM 自觉。

**整体评价**：数据/规范层结构化做到位（A-），执行层零代码（C），双平台 90 天缓存**连一个缓存文件都没落地**（D）。"真结构化系统" 与 "硬编码 prompt" 之间，接近前者偏后 1/3 位置。

---

## 一、各组件状态

### 1.1 Layer 1 元规则库（M01-M10 / M11）

**状态**：✅ 结构化存在（文档层），⚠️ 引擎层零代码。

- **文件**：`ink-writer/skills/ink-init/references/creativity/meta-creativity-rules.md`（248 行，v1.1）
- **规则数**：宣称 M01-M10 十条，实际已扩充到 **M11**（EW-0131 整合后新增「熟悉×陌生耦合」），每条含核心定义 + 正例 + 反例 + 适配题材。文件名字段 `M01-M10` 与实际 `M01-M11` 不一致——`SKILL.md` 第 42 行仍写"10 条元规则 M01-M10"（文档漂移小问题）。
- **硬约束标尺**：§方案校验硬门槛 明确"单套方案≥3 条元规则、3 套方案合计≥7 条、未通过丢弃重抽"——但这些校验**没有 Python 实现**，全靠 LLM 自报 `meta_rules_hit` 字段。
- **EW 桥接**：Appendix 记录 22 条 editor-wisdom 创意条目→M 编号的主映射表，声称由 `editor-wisdom-checker` 消费；未检索到 `editor-wisdom-checker` 代码实体。
- **静态校验**：`tests/ink_init/test_quick_creativity.py::TestMetaCreativityRules::test_m01_to_m10_all_present` 用正则断言 M01-M10 全部出现，通过。

### 1.2 Layer 2 种子库 anti-trope-seeds.json

**状态**：✅ 结构化存在，✅ Schema 校验通过，⚠️ 消费侧零代码。

- **数据文件**：`ink-writer/skills/ink-init/references/creativity/anti-trope-seeds.json`（13109 行）
- **Schema**：`anti-trope-seeds-schema.json` Draft-07，定义 `Seed` 对象的 7 必填字段（seed_id / category / value / rarity / genre_tags / example_pairing / source）+ 可选 `meta_rules_hit`。
- **规模**：`version=v2.0`、`total=1000`、`seeds` 数组 **1012 条**（多出 12 条是 skeleton 期 example 种子，不计入 total）。
- **分类覆盖**：10 类均衡——profession 102 / era 102 / conflict 101 / worldview 101 / emotion 101 / taboo 101 / mythology 101 / taboo_language 101 / body_feature 101 / object 101。
- **稀有度分布**：R1=50 / R2=200 / R3=252 / R4=306 / R5=204；**R4+R5=510=50.4%，R5=20.2%**——均达成 Phase-Seed-1 roadmap 硬约束（R4+R5≥50%、R5≥20%）。
- **来源标注**：`source=human` 202 条 / `source=llm` 810 条，与 commit 描述（20% human / 80% llm）一致。
- **meta_rules_hit 覆盖**：只有 284/1012 条标注（28%）；schema 该字段是可选，但消费侧理论上需要此字段做"契合度匹配"，实际覆盖不足意味着 LLM 大概率走语义匹配而非查表。
- **changelog**：完整记录 v1.1→v2.0 十次增量（delta 各 100），日期 2026-04-17。
- **消费代码**：**不存在**。`grep` 全仓 `anti-trope-seeds`/`anti_trope_seeds` 只命中 10 个入库脚本（`scripts/seeds_batch2..10_*.py`，都是 producer 不是 consumer）+ 1 个测试。**没有任何 Python 函数读取此库做抽取**。

### 1.3 Layer 3 扰动引擎 perturbation-engine.md

**状态**：⚠️ 结构化伪代码存在，❌ 无任何 Python 实现。

- **文件**：`ink-writer/skills/ink-init/references/creativity/perturbation-engine.md`（v1.0，180 行）
- **规格完整度**：定义扰动对（跨 category 对）+ 4 档 N 矩阵（1/2/3/5 对）+ 5 种模式（时代错位/职业反差/尺度错位/规则颠倒/感官替换）+ 抽取算法伪代码 `draw_perturbation_pairs(seeds, genre, draft_index, n, rarity_floor)` + 3 套方案整对去重 + 输出 JSON schema。
- **代码实现**：`grep -r 'draw_perturbation\|perturbation_pairs' ink-writer/ scripts/ ink_writer/` → **0 个函数定义**，仅命中规格 md、测试 fixture、seed builder 脚本（producer 侧）。伪代码中的 `stable_hash` / `pick_pattern` / `draw_perturbation_pairs` 均为文档文字，无代码实体。
- **执行方式**：SKILL.md Quick Step 1 要求 LLM 按此文档"在 think 过程中"生成 `perturbation_pairs` 字段——即 **LLM 自己扮演扰动引擎**。重抽机制"最多 3 次失败后降档" 亦无代码兜底。

### 1.4 `/ink-init --quick` 调用链

**状态**：✅ 模式分支存在，⚠️ 仅 SKILL.md prompt 指令驱动，无代码调度。

- **入口**：`ink-writer/skills/ink-init/SKILL.md` 第 10-24 行 `## 模式分支`，按 `--quick` token 进入 Quick Mode（§28 起），含 Quick Step 0→0.5→1→1.5→1.6→1.7→2→3 共 8 个 step。
- **Quick Step 0**：L1 必读 **12 个文件**（第 37-49 行）——涵盖 5 个 creativity reference + 4 个 naming 数据 + 1 个 genre-tropes + 2 个市场趋势。
- **真正的 Python 调用**：只有 Quick Step 3.2 最后的 `init_project.py`（与 Deep Mode 共用），该脚本 903 行**不含任何 `quick/aggression/perturbation/meta_rule/market_avoid` 关键词**（grep 0 命中）——Python 层对激进度档位、扰动对、元规则、市场规避完全无感知，只做 state/preferences 的 JSON 落盘。
- **结论**：`/ink-init --quick` 的"创意三层体系"调用全部在 LLM 侧按 SKILL.md 伪代码自执行；Python 层只做最终产物落盘（`state.json` / `preferences.json` / `golden_three_plan.json` / `idea_bank.json`），**不校验任何 Quick Step 产出的创意字段**（`meta_rules_hit`/`perturbation_pairs`/`gf_checks`/`style_voice` 等在 Python 数据模型里无对应字段）。

### 1.5 金手指三重硬约束（GF-1/GF-2/GF-3）

**状态**：✅ 规格存在，⚠️ 校验零代码（LLM 自报）。

- **文件**：`ink-writer/skills/ink-init/references/creativity/golden-finger-rules.md`（112 行）
- **GF-1 非战力维度**：明确 8 类白名单（信息/时间/情感/社交/认知/概率/感知/规则）+ **22 条禁止词**列表（修为暴涨/无限金币/系统签到/作弊器/.../灵石自动产出），与 SKILL 声称的"≥20 条"吻合。
- **GF-2 代价可视化**：给出 10 条合格示例 + 3 条不合格反例，校验伪代码 `gf2 = 1 if (可量化 AND 可被反派利用 AND 前10章可见)`——无实现。
- **GF-3 一句话爆点**：10 组正反对比 + "这也行？"≥3/5 评审伪标准——无实现（LLM 自评）。
- **降档逻辑**：`for attempt in range(1,6)` 伪代码写了 5 次重抽+降档，无对应 Python 函数。
- **Quick Step 1.5 输出**：要求每套方案产出 `gf_checks = [GF1,GF2,GF3]` 0/1 矩阵，`sum≥2` 方可入选——LLM 自报，无程序化校验。

### 1.6 4 档激进度 × 3 档语言风格分档

**状态**：✅ 规格齐备，❌ 无分档代码，⚠️ 分配算法全为 LLM prompt。

- **4 档激进度**：
  - `SKILL.md` Quick Step 0.5 §档位矩阵（第 105-115 行）定义 1 保守 / 2 平衡 / 3 激进 / 4 疯批，映射到"元规则命中下限 × 扰动对数量 × 稀有度门槛 × 额外约束"。
  - 解析顺序：位置参数 → 命名参数 → AskUserQuestion 兜底 → 中文词容错。
  - **全部为 SKILL.md 文本指令**，零 Python 实现。
  - 疯批档 B01-B12 12 条商业安全边界（反派视角主角/悲剧结局/主角长期失败/...），要求 `safety_boundary_broken` 数组显式列出——LLM 自报。
- **3 档语言风格 V1/V2/V3**：
  - 文件：`references/creativity/style-voice-levels.md`（v1.0，228 行），V1 文学狂野 / V2 烟火接地气 / V3 江湖野气。
  - 敏感词 L0/L1/L2/L3 四级分类 + 档位 × 密度矩阵（档位 1 = 0% / 档位 2 ≈ 0.2% / 档位 3 = 0.5-0.8% / 档位 4 = 0.8-1.5%）。
  - Quick Step 1.6 分配算法伪代码 `stable_hash(timestamp+genre_tuple)` → 无实现。
  - 落地句式库：每档 8 条骨架句——是"素材"不是"引擎"。

### 1.7 命名素材库

**状态**：✅ 全部结构化存在，规模达标。

| 资产 | 文件 | 规模 | 结构化程度 | 消费路径 |
|---|---|---|---|---|
| 江湖绰号库 | `data/naming/nicknames.json` | **110 条**（SKILL 声称 ≥100） | ✅ 每条含 `nickname`/`rarity(1-5)`/`style_tags` 多选（jianghu/rough/smoky/hei_dao/wu_lin） | SKILL.md Quick Step 1.7 §人名校验，LLM 按 `rarity≥3` + `style_tags` 含 `jianghu` 抽"主角外号"；Python 无实现 |
| 书名模板库 | `data/naming/book-title-patterns.json` | **170 条**（V1=54 / V2=57 / V3=59；SKILL 声称 ≥150） | ✅ 每条含 `pattern`/`rhetoric_tags` 多选（pun/homophone/antithesis/irony/oxymoron/concrete_abstract/anachronism 7 种修辞），测试硬断言每种 ≥10 出现 | SKILL.md Quick Step 1.7 §书名校验；Python 无实现 |
| 陈词黑名单 | `data/naming/blacklist.json` | male 30 / female 30 / suffix_ban 19 / prefix_ban 14 / combo_ban (7 姓 × 8 末字 = 56 对) | ✅ 多层分类（直接名单 + 前/后缀 token + 笛卡儿积组合） | Quick Step 1 §命名规则 + Quick Step 1.7；Python 无实现 |
| 姓氏库 | `data/naming/surnames.json` | 225 条（common 30 / moderate 90 / rare 75 / compound 30），加权概率 20/40/30/10% | ✅ 四层 rarity | 同上 |
| 名字库 | `data/naming/given_names.json` | 8 风格桶（classical/modern/martial/scholarly/cold + rough/smoky/jianghu），每桶 male/female 各 ≥30；v13.8 新增的 3 桶显式声明 `_style_tag` = V1/V2/V3 | ✅ 风格 → 档位映射通过 `_style_tag` 元字段打通 | 同上 |

**静态校验**：`tests/ink_init/test_quick_creativity.py` 6 个 TestClass 共 10 个 test 已覆盖 schema/数量/修辞标签/必备词/rough-smoky-jianghu 桶，**但没有任何 integration/e2e 测试验证 Quick 模式真的消费了这些文件**——消费方是 LLM 不是 Python，无法用 pytest 断言。

### 1.8 起点 + 番茄双平台榜单 90 天缓存

**状态**：❌ **最弱环节**——规范存在，落地零。

- **规范文件**：`data/market-trends/README.md`（v1.0，97 行）、SKILL.md 第 51-83 行 WebSearch 子步骤。
- **硬编码检索语**：4 条（起点 2 + 番茄 2）。
- **缓存路径**：`data/market-trends/cache-YYYYMMDD.md`。
- **实际缓存落盘**：`ls data/market-trends/` → **只有 README.md，零个 cache-*.md 文件**（ctime 2026-04-17 17:33，就是 commit 当天初始化时的 README）。说明 v13.8 发布以来 quick 模式没有真正跑过一次带 WebSearch 的链路，或者跑了但没把结果写入该目录。
- **90 天缓存清理代码**：`grep -r '90.?天\|90 day\|cache-\*\.md\|market-trends' ink-writer/ scripts/ ink_writer/` → 仅命中 3 处规格 md 与 package-lock（无关）。**没有任何 Python 代码执行清理**。
- **Fallback 链**：规范写"7 天内近似 → 7 天外标记 `fetch_status=none`"——同样无代码兜底。
- **结论**：双平台 90 天缓存是 **"全靠 LLM 调用 WebSearch 工具 + 按规范落盘 md + 自行维护 90 天窗口"**，这在 Claude Code skill 语境下实际意味着每次 quick 运行都依赖 LLM 诚实执行，清理过期文件靠"静默清理"的文字要求，**现场零证据证明该机制被执行过**。

---

## 二、证据表

| # | 功能 | 代码/文件证据 | 判定 |
|---|---|---|---|
| 1 | 元规则 M01-M11 | `meta-creativity-rules.md` 248 行，M01-M11 完整定义 + EW 桥接 22 条映射 | 结构化存在（文档层） |
| 2 | 元规则命中校验 | **grep 无 Python 实现** | 未找到代码，LLM 自报 |
| 3 | 种子库 v2.0 1000 条 | `anti-trope-seeds.json` 1012 条 / 10 类 / R4+R5=50.4% / R5=20.2% / 10 changelog / Draft-07 校验通过 | 结构化存在 |
| 4 | Seeds schema 校验 | `anti-trope-seeds-schema.json` + `tests/ink_init/test_quick_creativity.py::TestAntiTropeSeeds` 静态通过 | 存在 |
| 5 | 扰动引擎算法 `draw_perturbation_pairs` | `perturbation-engine.md` 伪代码 **only**；全仓 grep `draw_perturbation` 无定义 | **仅文档，无代码** |
| 6 | 扰动对 5 种模式 A-E | `perturbation-engine.md` §3 各含 3 示例 | 规格存在 |
| 7 | 3 套方案整对去重 | 伪代码规范，无实现 | 仅文档 |
| 8 | `/ink-init --quick` 入口 | `SKILL.md` 第 10-24 行模式分支 | 存在（SKILL 级） |
| 9 | quick 模式 Python 调度 | `init_project.py` 903 行，grep `quick\|aggression\|perturbation\|meta_rule\|market_avoid` 全 0 命中 | **Python 层对创意系统零感知** |
| 10 | GF-1 非战力维度 | `golden-finger-rules.md` 8 类白名单 + 22 条禁止词 | 结构化存在 |
| 11 | GF-2 代价可视化 | 10 正例 + 3 反例 + 伪代码 | 仅文档 |
| 12 | GF-3 一句话爆点 | 10 组对比 + "这也行？" ≥3/5 评审 | 仅文档 |
| 13 | GF 三重校验与 5 次重抽 | 伪代码 `for attempt in range(1,6)` | 仅文档 |
| 14 | 4 档激进度矩阵 | `SKILL.md` Quick Step 0.5 §档位矩阵 | 结构化存在（文档） |
| 15 | 档位解析与中文词容错 | SKILL.md 规范；无 Python parser | 仅 prompt |
| 16 | 疯批档 B01-B12 商业安全边界 | SKILL.md 第 152-168 行 12 条 | 结构化存在 |
| 17 | V1/V2/V3 语言风格 | `style-voice-levels.md` 228 行 + 8 条落地句式/档 | 结构化存在 |
| 18 | L0-L3 敏感词 4 级 | 同上 §二 | 规格存在 |
| 19 | 档位 × 密度矩阵 | 同上 §三 | 规格存在 |
| 20 | 风格档位分配算法 | `stable_hash(timestamp+genre_tuple)` 伪代码 | 仅文档 |
| 21 | 江湖绰号库 110 条 | `data/naming/nicknames.json` 110 条 / `rarity+style_tags` | 结构化存在 |
| 22 | 书名模板 170 条 | `book-title-patterns.json` V1=54 / V2=57 / V3=59；7 修辞标签每种 ≥10 | 结构化存在 |
| 23 | 陈词黑名单 | `blacklist.json` male/female/suffix_ban 19/prefix_ban 14/combo_ban 7×8=56 | 结构化存在 |
| 24 | 黑名单运行时比对 | SKILL.md Quick Step 1.7 §书名/人名校验；无 Python | 仅 prompt |
| 25 | 双平台 4 条硬编码检索语 | SKILL.md 第 56-60 行 + market-trends/README.md | 规范存在 |
| 26 | 90 天缓存落盘 | `data/market-trends/` **只有 README.md，零 cache-*.md** | **未落地** |
| 27 | 90 天超期清理 | 全仓无清理代码 | **未实现** |
| 28 | 7 天 fallback | 文档规范 | 仅 prompt |
| 29 | 创意指纹 5 字段输出 | SKILL.md Quick Step 2 | 规格存在；LLM 自报 |
| 30 | pytest 静态验收 | `tests/ink_init/test_quick_creativity.py` 10 个 test 覆盖数据层 | 存在（仅数据层） |

---

## 三、Top Findings

### F1【最严重】"引擎"只是文档，没有代码

**现象**：扰动引擎 `draw_perturbation_pairs` 伪代码、金手指三重校验 `gf_checks` 矩阵、V1/V2/V3 分档算法 `stable_hash(timestamp+genre_tuple)`、GF 5 次重抽与降档 `for attempt in range(1,6)`——全部以 Python 语法写在 markdown 文档里，**全仓 grep 找不到任何对应的真 Python 函数**。

**证据**：
- `grep -r 'def draw_perturbation\|def pick_pattern\|perturbation_pairs' --include='*.py'` 命中 0（仅 test fixture 和 seed builder）
- `init_project.py` 903 行 0 次出现 `quick/aggression/perturbation/meta_rule/market_avoid`

**影响**：所谓的"硬约束校验""重抽/降档"完全依赖 LLM 逐次运行时自觉执行。同一个 prompt 在不同 session、不同档位下 LLM 打分可能漂移；整对去重这种需要跨方案状态的计算也只能信任 LLM。

### F2【严重】双平台 90 天缓存：规范有，落地零

**现象**：`data/market-trends/` 目录从 v13.8 发布（2026-04-17）到审计当天，**只有一个 README.md，零个 cache-YYYYMMDD.md**。90 天超期清理代码全仓 grep 命中 0 处。Fallback 链（7 天近似 + 7 天外 `fetch_status=none`）仅在规范层。

**证据**：
- `ls -la data/market-trends/` → `README.md` 唯一文件（3008 bytes，ctime 17:33）
- `grep -rn '90.?天\|cache-\*\.md\|market-trends' ink-writer/scripts/ ink_writer/` → 0 命中

**影响**：ink-init --quick 调用时，要么没有真的调用 WebSearch（导致 `market_avoid` 字段无法对齐双平台真实榜单），要么调用了但没落盘复用（导致每次 quick 都要重新联网，累积成本）。"反向规避"在现实中等于 LLM 的直觉判断。

### F3【中等】Python 层对创意字段零感知

**现象**：SKILL.md Quick Step 3 将方案字段"映射到内部数据模型"，但落地脚本 `init_project.py` 的 CLI 参数表（第 787-802 行）与 `state_schema.py` 的数据模型**完全不包含** `meta_rules_hit` / `perturbation_pairs` / `gf_checks` / `style_voice` / `market_avoid` / `title_rhetoric_tags` / `safety_boundary_broken` 等创意指纹字段。

**影响**：
- 创意指纹产物**不会写入项目 state**，后续 `/ink-plan`、`/ink-write`、`/ink-review` 链路无法读取这些约束做一致性校验；
- 用户重跑 `/ink-init --quick` 时"档位/扰动对"信息丢失，只保留了传统初始化参数（title/genre/golden_finger 等）；
- US-008 创意指纹标榜"Quick Step 2 消费" 但消费端只是 markdown 展示给用户看，不是项目内部状态。

---

## 四、健康度一句话

**v13.8 创意系统是一套"精致的 prompt 骨架 + 合格的数据底座"——数据层做到了真结构化（1000 条种子 + 110 绰号 + 170 书名 + Draft-07 schema + 10 个 pytest），但"引擎"层全部是 markdown 伪代码、零 Python 实现，双平台 90 天缓存更是规范有而落地零；所谓三层架构驱动 /ink-init --quick 在现实中等同于 "一份极详细的 system prompt + 一组结构化素材库 + 一个只懂传统字段的 Python 落盘脚本"，称之为"真结构化系统"偏乐观，称之为"硬编码 prompt"偏悲观，实际居于两者之间偏前者。**
