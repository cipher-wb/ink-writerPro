# PRD: 文笔反 AI 味 + 爆款白话化深层重构（Prose Anti-AI Overhaul）

> 决策档位：**1A + 2A + 3A + 4C**
> 标杆 = 起点/番茄爆款（猪三样、辰东式，人物开口就是冲突）
> 修复策略 = 全量硬阻断（违规即 polish 重写，重写失败 → 整章 block）
> 覆盖范围 = 全章节、所有场景
> 重构深度 = 深层（重构 writer-agent 范式 + 爆款示例库 RAG）

---

## 1. Introduction / Overview

当前 ink-writer 产出的章节存在三类显性 AI 味，编辑/读者一眼可识别：

1. **AI 化标点**：高频使用 `——`（双破折号）、英式连字符、智能引号 `“”`、过密顿号
2. **句式绕、阅读成本高**：嵌套从句 + 长修饰语链 + 抽象主语，需要"理解一遍"才能往下读
3. **装逼文笔**：成语堆叠、四字格排比、抽象名词链（"宿命的虚无"、"灵魂的颤栗"），冲淡冲突与情节

根因（已通过代码审阅锁定）：

| 根因 | 位置 | 现状 |
|------|------|------|
| 零容忍清单无标点指纹类 | `config/anti-detection.yaml:62-100` | 只有时间开头/与此同时/不仅而且，没有 ——/连字符/智能引号 |
| 反 AI 写作指南反向引导 | `references/anti-detection-writing.md:32` | "长句绵延，有省略号和破折号"——鼓励用破折号 |
| 直白度只覆盖 1/4 场景 | `directness-checker.md:19-24` | 普通章节、过渡章、铺垫章无人查 |
| 缺白话度硬门禁 | 全项目 | 没有成语/四字格/抽象名词链密度上限 |
| writer-agent 范式偏文学 | `writer-agent.md:99-220` | "先穿上视角→铁律自检→写"，鼓励感官铺陈 |
| 无爆款示例库 retrieval | benchmark/reference_corpus 已有 50+ 本但未接入 writer | writer 凭模型先验生成，无 few-shot 锚 |

本 PRD 通过**七层改造**根治：标点零容忍清单 → 白话度新检查器 → 直白度全场景化 → 爆款黑名单扩展 → writer-agent 范式重构 → 爆款示例库 RAG → 全量硬阻断闭环。

## 2. Goals

- **G1（标点）**：上线后产出章节中 `——` 出现频率 ≤ 0.2/千字（基线：当前约 3-5/千字），智能引号/英式连字符 = 0
- **G2（绕度）**：全章节嵌套从句深度均值 ≤ 1.5（基线：当前约 2.3），单句最长修饰语链 ≤ 3 个修饰词
- **G3（白话度）**：成语密度 ≤ 3/千字（基线：当前约 8-12/千字），四字格密度 ≤ 6/千字，抽象名词链（A 的 B 的 C）= 0
- **G4（爆款贴合度）**：在 5 本爆款书 + 5 章新产出上做盲测，人工评分"像爆款"占比 ≥ 70%（基线：当前 < 20%）
- **G5（不退化）**：reader-pull / hook-density / conflict-skeleton 等钩子类指标分数不下降（容差 ±5%）
- **G6（成本可控）**：全量硬阻断后，章均 polish 重试次数 ≤ 1.5 次，章均 LLM token 增长 ≤ 40%

## 3. User Stories

### US-001：标点 AI 指纹零容忍清单（标点硬门禁）
**Description:** As a writer-agent，I want 在 `config/anti-detection.yaml` 里加入完整的标点 AI 指纹清单 so that 任何 `——`、英式连字符、智能引号、定时顿号都被即时拦截。

**Acceptance Criteria:**
- [ ] `config/anti-detection.yaml` `zero_tolerance` 段新增 `ZT_EM_DASH`（中文 `——` 任意出现 ≥ 1 处即阻断；含豁免名单：电报体、字幕、引号内"角色被打断"对话场景）
- [ ] 新增 `ZT_AI_QUOTES`（智能引号 `"" ''`、法式引号 `«»` 任意出现即阻断）
- [ ] 新增 `ZT_HYPHEN_AS_DASH`（英式 `-` 用作中文破折号场景：例如 `他笑了-然后转身`）
- [ ] 新增 `ZT_DENSE_DUNHAO`（顿号密度 > 3/千字 → 阻断，意图打散"AB、CD、EF、GH"式列举堆砌）
- [ ] 新增 `ZT_ELLIPSIS_OVERUSE`（省略号 `……` > 8/千字 → 阻断；标杆 2.8/千字，上限 3 倍）
- [ ] 每条规则有豁免标注（whitelist patterns 字段，对话内"被打断"等场景不阻断）
- [ ] anti-detection-checker.md 同步更新第 0 层文档，加入"标点指纹"小节
- [ ] 单测：5 个 fixture 章节（4 违规 / 1 合规）全部命中预期
- [ ] Typecheck/lint 通过

### US-002：新增 colloquial-checker（白话度硬检查器）
**Description:** As a review pipeline，I want 一个全场景激活的"白话度检查器" so that 成语堆叠、四字格排比、抽象名词链在普通章节也能被拦截。

**Acceptance Criteria:**
- [ ] 新建 `ink-writer/agents/colloquial-checker.md` agent 规格
- [ ] 新建 `ink_writer/prose/colloquial_checker.py` 实现，5 维度评分：
  - C1：成语密度（≤ 3/千字 = green，3-5 = yellow，> 5 = red）
  - C2：四字格密度（≤ 6/千字 = green，6-10 = yellow，> 10 = red）—— 含"X然X之"、"X而不X"等仿四字格
  - C3：抽象名词链长度（"A 的 B 的 C" 出现 ≥ 1 处 = red，例：宿命的虚无的颤栗）
  - C4：修饰语链长度（单个名词前修饰词 ≥ 4 个 = red，例：那道幽深的、阴冷的、裹挟着千年怨气的影子）
  - C5：抽象主语率（一段中"命运/时光/记忆/思绪"等抽象名词作主语占比 > 30% = red）
- [ ] 阈值常量集中在 `config/colloquial.yaml`，遵循 `config/anti-detection.yaml` 同款 schema
- [ ] 全章节、所有 scene_mode 激活（**no skip**）
- [ ] severity = red 时 `pass=false`，触发 polish 重写
- [ ] 输出格式遵循 `checker-output-schema.md`
- [ ] 注册到 `config/checker-thresholds.yaml` 与 review pipeline
- [ ] 单测：3 章对照样本（爆款 / AI 装逼 / 严肃文）打分符合预期方向
- [ ] Typecheck/lint 通过

### US-003：directness-checker 激活范围扩展 + 爆款档阈值
**Description:** As a review pipeline，I want directness-checker 在所有章节都激活，并区分"爆款档"和"标准档"两套阈值 so that 普通章节也被绕度门禁覆盖。

**Acceptance Criteria:**
- [ ] 修改 `ink-writer/agents/directness-checker.md` 激活条件：删除"仅黄金三章+战斗/高潮/爽点"硬门禁，改为全场景激活
- [ ] 新增 D6 维度：**句子嵌套深度**（按"，"切分子句，平均嵌套层数 ≤ 1.5 = green，> 2.0 = red）
- [ ] 新增 D7 维度：**修饰语链平均长**（每名词前修饰词数均值 ≤ 1.5 = green，> 2.5 = red）
- [ ] 在 `reports/seed_thresholds.yaml` 增加 `tier: explosive_hit` 桶（爆款档），更激进阈值；保留现有 `golden_three`/`combat`/默认桶
- [ ] 写一个迁移脚本 `scripts/regen_directness_thresholds_explosive.py`，从 5 本爆款书（猪三样、辰东任选两本、番茄 top3）量化生成 explosive_hit 阈值
- [ ] 项目级配置 `config/anti-detection.yaml` 增加 `directness_tier: explosive_hit | standard`，默认 `explosive_hit`
- [ ] D1-D7 任一 red → 触发 polish；polish 后仍 red → 整章 block
- [ ] 抒情章 / slow_build 场景可在 outline 中显式声明 `directness_override: standard` 降档
- [ ] 单测：旧 1/4 场景激活的回归测试改为全场景激活，旧 fixture 行为不变
- [ ] Typecheck/lint 通过

### US-004：扩展 prose-blacklist.yaml 爆款风专用黑名单
**Description:** As a writer-agent / polish-agent，I want prose-blacklist.yaml 增加"装逼词黑名单"和"爆款替换映射" so that 写作和润色阶段都能机械替换。

**Acceptance Criteria:**
- [ ] `ink-writer/assets/prose-blacklist.yaml` 新增 `pretentious_verbs` 域：凝视/伫立/驻足/凝望/审视/睥睨/睨视/俯瞰/仰望/瞥见/扫视…（≥ 30 词）
- [ ] 新增 `pretentious_nouns` 域：宿命/虚无/苍茫/沧桑/孤寂/静谧/缱绻/缥缈/旖旎/迷离…（≥ 30 词）
- [ ] 新增 `pretentious_adverbs` 域：缓缓/徐徐/悄然/淡然/默然/怅然/惘然/兀自/兀然…（≥ 30 词）
- [ ] 新增 `replacement_map` 段：每个装逼词给出 1-3 个爆款替换（例：`凝视: [盯着, 看着, 死盯]`）
- [ ] `polish-agent` 的 simplification pass 自动应用 replacement_map
- [ ] 词表来源标注：注释中标明每个词的取证文件（取自 benchmark/reference_corpus/per_book_stats 的"高 AI 比"词）
- [ ] 单测：simplification_pass.py 跑替换前/后对照
- [ ] Typecheck/lint 通过

### US-005：writer-agent 范式重构（对话+动作优先 L11）
**Description:** As a writer-agent，I want 新增 L11 铁律"对话+动作驱动" so that 起草阶段就贴爆款范式，而不是事后靠 checker 修。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/writer-agent.md` 新增 **铁律 L11：对话+动作驱动律**，全章节强制（不分场景）
  - L11a：每 200 字至少 1 句对话或 1 个具体动作（不含心理描写、环境描写、感官描写）
  - L11b：禁止段首抽象名词或抽象副词（如"宿命般地"、"缓缓地"作段首）
  - L11c：每段开头优先级：对话 > 动作 > 感官 > 心理 > 环境（环境段首每章 ≤ 2 处）
  - L11d：每个场景必须有"明确冲突"（角色 vs 角色 / 角色 vs 环境 / 角色 vs 自我），无冲突段视为废段
- [ ] 修改 L10b/L10e 暂挂条款：从"仅在 directness mode 暂挂"改为"在 colloquial-checker red 时整体暂挂"
- [ ] 修改 L10c 加入"禁止四字格排比"和"禁止抽象名词链"
- [ ] 修改 `references/anti-detection-writing.md`：删除第 32 行"长句绵延，有省略号和破折号"鼓励语；改为"严禁双破折号 ——，被打断对话用 `他正要说话，对方抢过去：`"
- [ ] 修改 `references/anti-detection-writing.md` 原则一表格：删除"破折号"列，删除"模糊的感官记忆"等装逼示例
- [ ] 单测：跑 1 章已知违 L11 的旧章，writer-self-check 命中
- [ ] Typecheck/lint 通过

### US-006：构建爆款示例库 RAG（writer 起草前 retrieve）
**Description:** As a writer-agent，I want 在起草每个场景前 retrieve 3 个语义最相似的爆款段落作为 few-shot so that 模型从"平均范式"漂移到"爆款范式"。

**Acceptance Criteria:**
- [ ] 新建 `scripts/build_explosive_hit_index.py`：从 `benchmark/reference_corpus/` 选 5 本爆款（猪三样《我有一座超神基地》、辰东《圣墟》、番茄《吞噬星空》、起点 top3 任选两本）切片
- [ ] 每个切片携带 metadata：`scene_type`（对话/动作/冲突/铺垫/高潮）、`pov`（一/三人称）、`pace`（快/慢）
- [ ] 索引存于 `data/explosive_hit_index/`，使用 sentence-transformers（已在用）embedding
- [ ] 新建 `ink_writer/retrieval/explosive_retriever.py`：输入"本场景大纲文本+ scene_type"，返回 top-3 段落（< 200 字/段）
- [ ] writer-agent 起草流程修改：Step 2A drafting 前先调用 retriever，把 3 段插入 prompt 的 `<reference_examples>` 块
- [ ] 在 `config/parallel-pipeline.yaml` 加 `enable_explosive_retrieval: true` 开关，便于 A/B
- [ ] 索引构建 < 10 分钟，retrieve 单次 < 500ms（用现有 retriever 模式）
- [ ] 单测：retrieve 一个"战斗场景"大纲，top-1 段落必须包含动词比 ≥ 0.4 的实战描写
- [ ] Typecheck/lint 通过

### US-007：polish-agent 强化（全量硬阻断闭环）
**Description:** As a review pipeline，I want polish-agent 在标点/白话/直白任一硬阻断时执行"全章重写"而非"句级修改" so that 修复彻底，不留漏网。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/polish-agent.md` 新增 `## Hard Block Rewrite Mode` 章节
- [ ] 触发条件：`anti-detection-checker.zero_tolerance` 命中 OR `colloquial-checker.severity=red` OR `directness-checker.severity=red`
- [ ] Rewrite mode 行为：
  - 不做句级 patch，而是把整章作为 reference + 违规清单 + 爆款 retrieval 段落，全章重写
  - 重写后必须再过一次三个 checker
  - 第二次仍 red → 标记 `chapter_status: hard_blocked`，不进入归档，写 `reports/blocked/chapter_NNN.md`
- [ ] 新增 `config/anti-detection.yaml` 的 `max_hard_block_retries: 1`（默认重写一次）
- [ ] ink-write 流程在 hard_blocked 时退出 code 2，给 ink-auto 检查点接管
- [ ] 单测：构造一个"打死也修不好"的违规章（全是 ——），验证走完两次重写后被 block
- [ ] Typecheck/lint 通过

### US-008：阈值校准 + 5+5 对照基线
**Description:** As a maintainer，I want 在上线前用 5 本爆款 + 5 本严肃文学 跑 baseline，确认门禁不会一刀切误伤严肃风 so that explosive_hit 档不会污染 standard 档。

**Acceptance Criteria:**
- [ ] 新建 `scripts/calibrate_anti_ai_thresholds.py`：跑 anti-detection / colloquial / directness 三个 checker on 10 本书 × 30 章
- [ ] 输出 `reports/calibration/anti_ai_baseline_2026-04.md`：
  - 5 本爆款的 P50/P75 指标（用作 explosive_hit 档阈值）
  - 5 本严肃文学的 P50/P75 指标（用作 standard 档阈值，且确保不被 explosive 档误判）
  - 两档阈值的 gap 表
- [ ] 校准结果写回 `reports/seed_thresholds.yaml` 的 `tier` 段
- [ ] 不阻断单测；用作发布前 manual gate
- [ ] Typecheck 通过

### US-009：E2E 验收 + 人工 + LLM 双盲评分
**Description:** As a maintainer，I want 一次 E2E 验收：用同一份大纲跑 旧 pipeline / 新 pipeline 各 5 章，盲测对比 so that 验证 G1-G5 全部命中。

**Acceptance Criteria:**
- [ ] 新建 `scripts/e2e_anti_ai_overhaul_eval.py`：
  - 选定 1 个测试项目（已有 outline）
  - 旧 pipeline（master 当前 commit）跑 5 章
  - 新 pipeline（本 PRD 完成 commit）跑 5 章
  - 输出 10 章对照
- [ ] 跑 4 个量化指标对比：—— 密度、成语密度、嵌套深度、对话占比
- [ ] LLM 盲评：用 Claude opus 4.7 同时读 10 章（去掉 commit 标识），让模型给"哪 5 章更像爆款"打分
- [ ] 人工 spot-check：抽 3 对（旧/新）由用户读，记录主观感受到 `reports/eval/user_blind_review.md`
- [ ] 通过门：4 个量化指标全部达 G1-G3 目标 + LLM 盲评新版命中率 ≥ 70%
- [ ] 报告写入 `reports/eval/anti_ai_overhaul_2026-04.md`

### US-010：文档与回滚预案
**Description:** As a future maintainer，I want 整套改造有完整文档和一键回滚开关 so that 出问题能快速降级。

**Acceptance Criteria:**
- [ ] 新建 `docs/prose-anti-ai-overhaul.md`：架构图（七层）、阈值表、A/B 开关、回滚步骤
- [ ] `CLAUDE.md` 新增 "Prose Anti-AI Module" 段，与 "编辑智慧模块"、"Live-Review 模块" 平级
- [ ] 全套门禁有总开关：`config/anti-detection.yaml` `prose_overhaul_enabled: true`，false 时回到旧行为
- [ ] colloquial-checker 单独开关：`config/colloquial.yaml` `enabled: true`
- [ ] explosive_hit retrieval 单独开关：`config/parallel-pipeline.yaml` `enable_explosive_retrieval: true`
- [ ] 回滚步骤验证：手动改三个开关为 false，跑 1 章，行为与改造前一致

## 4. Functional Requirements

- FR-1：`config/anti-detection.yaml` `zero_tolerance` 必须新增 5 条标点指纹规则（ZT_EM_DASH / ZT_AI_QUOTES / ZT_HYPHEN_AS_DASH / ZT_DENSE_DUNHAO / ZT_ELLIPSIS_OVERUSE），每条带 patterns + whitelist + description
- FR-2：必须新建 `ink-writer/agents/colloquial-checker.md` + `ink_writer/prose/colloquial_checker.py`，全章节激活，5 维度评分（C1-C5）
- FR-3：`directness-checker` 激活条件必须改为全场景激活；新增 D6（嵌套深度）/ D7（修饰链长）；新增 explosive_hit 阈值档
- FR-4：`prose-blacklist.yaml` 必须新增 pretentious_verbs / pretentious_nouns / pretentious_adverbs（每域 ≥ 30 词）+ replacement_map
- FR-5：`writer-agent.md` 必须新增铁律 L11（对话+动作驱动），含 L11a-L11d；同步删除 references/anti-detection-writing.md 中鼓励破折号/装逼示例的内容
- FR-6：必须新建爆款示例 RAG 索引（5 本书）+ explosive_retriever，writer-agent Step 2A 前 retrieve top-3 注入 prompt
- FR-7：`polish-agent.md` 必须新增 Hard Block Rewrite Mode，三个 checker 任一硬阻断 → 全章重写，第二次仍 red → 标 hard_blocked + 退出 code 2
- FR-8：必须有 `prose_overhaul_enabled` / `colloquial.enabled` / `enable_explosive_retrieval` 三个独立开关，可独立回滚
- FR-9：必须跑 calibration 在 5+5 基线书上，把阈值写回 seed_thresholds.yaml
- FR-10：必须跑 E2E 旧/新 pipeline 各 5 章对比，4 量化指标 + LLM 盲评 + 人工 spot-check 三关全过

## 5. Non-Goals (Out of Scope)

- ❌ **不**改变章节字数下限（保持 2200 字）
- ❌ **不**重构 outline / planning 阶段（本 PRD 只涉及 write/review/polish 三段）
- ❌ **不**新增风格分支（如严肃文学专用 writer-agent），只做"爆款档 / 标准档"两档阈值切换
- ❌ **不**重写 anti-detection 的 6 层框架，只在零容忍清单加规则
- ❌ **不**接入新的外部 LLM 或 embedding 模型（仍用现有 sentence-transformers + Anthropic SDK）
- ❌ **不**修改 ink-init / ink-plan / ink-audit 等其他子命令
- ❌ **不**做实时学习（live-review 已有规则候选闸，本 PRD 不动）

## 6. Design Considerations

### 与现有模块的边界

| 模块 | 关系 | 改动点 |
|------|------|--------|
| editor-wisdom-checker | 并列 | simplicity 域可暂时不动；后续按 calibration 结果增量 |
| live-review-checker | 并列 | 不动，独立链路 |
| anti-detection-checker | 扩展 | 加 5 条零容忍 + 文档同步，不改 6 层算分框架 |
| directness-checker | 扩展 + 行为变更 | 全场景激活 + 加 D6/D7 + 加 explosive 档 |
| sensory-immersion-checker | 联动 | colloquial-checker red 时整体 skipped（避免与 L10b 暂挂条件冲突） |
| writer-agent | 扩展 | 加 L11 + 接 retrieval；不改 L1-L9 |
| polish-agent | 扩展 | 加 Hard Block Rewrite Mode；保留旧 simplification pass |

### 七层改造架构图

```
┌─────────────────────────────────────────────────────────────┐
│ Step 2A: writer-agent 起草                                  │
│   ↓ 接入 explosive_retriever（US-006）                       │
│   ↓ 应用 L11 铁律（US-005）                                  │
│   ↓ 应用扩展 prose-blacklist（US-004）                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: review pipeline 三层硬门禁                          │
│   ┌──────────────────────────────────────────────────┐      │
│   │ anti-detection-checker（含 5 条新零容忍）（US-001）│      │
│   ├──────────────────────────────────────────────────┤      │
│   │ colloquial-checker（新增，全场景）（US-002）       │      │
│   ├──────────────────────────────────────────────────┤      │
│   │ directness-checker（全场景 + D6/D7 + 爆款档）(US-003)│    │
│   └──────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                          ↓ 任一 red
┌─────────────────────────────────────────────────────────────┐
│ Step 4: polish-agent Hard Block Rewrite（US-007）            │
│   ↓ 全章重写 + 二次过 checker                                │
│   ↓ 仍 red → hard_blocked, exit 2                           │
└─────────────────────────────────────────────────────────────┘
                          ↓ 通过
                       归档 / 写入
```

### 阈值分档原则

- **explosive_hit**（默认）：基于 5 本爆款 P75 量化，激进
- **standard**：基于 5 本严肃文学 P75 量化，宽松
- **章节级 override**：outline 在 `chapter_meta` 加 `directness_tier: standard` 即可降档
- **绝不**让 standard 档松到能让 —— 通过；标点零容忍是**两档共用**的

## 7. Technical Considerations

- **依赖**：sentence-transformers（已在用）、anthropic SDK（已在用）、pyyaml（已在用）；无需新增外部依赖
- **首次索引构建**：US-006 的 explosive_hit 索引建设需要 ~10 分钟（5 本书 × ~3000 切片）；CI 不跑，本地一次性
- **Token 成本**：US-006 retrieval 每章新增 ~600 token（3 段 × 200 字）+ US-007 hard block 重写约新增 1 次完整章（~3000 token），章均 token 增长约 30-40%
- **Windows 兼容**：所有新文件遵循 CLAUDE.md "Windows 兼容守则"——`open()` 带 `encoding="utf-8"`，新增 CLI 配 .ps1/.cmd
- **回滚**：三个独立开关 + 旧 fixture 回归测试保证回滚后字节级一致
- **零容忍冲突**：标点零容忍优先级 > directness/colloquial（标点错就是错，不分档）
- **抒情章兼容**：outline 可在 `chapter_meta.directness_tier: standard` 降档；不能降的是标点

## 8. Success Metrics

| 指标 | 基线 | 目标 | 测量方式 |
|------|------|------|---------|
| —— 出现密度 | ~3-5/千字 | ≤ 0.2/千字 | E2E 5 章统计 |
| 智能引号/英式连字符 | 偶发 | 0 | E2E 5 章 grep |
| 嵌套从句深度均值 | ~2.3 | ≤ 1.5 | colloquial-checker D6 |
| 成语密度 | ~8-12/千字 | ≤ 3/千字 | colloquial-checker C1 |
| 四字格密度 | ~12+/千字 | ≤ 6/千字 | colloquial-checker C2 |
| LLM 盲评"像爆款"率 | < 20% | ≥ 70% | US-009 LLM 盲评 |
| 人工主观评分 | 偏 AI | ≥ 4/5 分 | US-009 人工 spot-check |
| reader-pull / hook-density 退化 | — | 容差 ±5% | 现有 checker 对比 |
| 章均 polish 重试 | ~0.8 | ≤ 1.5 | ink-write 日志 |
| 章均 token 增长 | — | ≤ 40% | ink-write 日志 |

## 9. Open Questions

1. **抒情章如何标记**：当前 outline schema 有 `scene_mode` 但没有 `directness_tier` 字段；US-003 的"显式 override"需要 ink-plan 同步 schema 改动——是否纳入本 PRD 还是单独提？
   - **建议**：纳入本 PRD US-003 作为子任务（ink-plan schema 加一个可选字段，向后兼容）

2. **explosive_hit 5 本书选哪 5 本**：当前 benchmark/reference_corpus 已有 50+ 本但未做"爆款标签"。US-006 需要先人工选 5 本——用户是否亲自指定？
   - **建议**：用户列 5 本书名 → 自动从 corpus 找，找不到的现场抓取

3. **L10b/L10e 暂挂条件变更的回归风险**：原来"仅 directness mode 暂挂"改为"colloquial red 时暂挂"，可能影响过去 1-3 章的回归基线
   - **建议**：US-005 落地后跑一次现有 regression suite，差异列入 calibration 报告

4. **standard 档阈值会不会松到无意义**：如果 5 本严肃文学 P75 的 —— 密度本身就很高，零容忍会冲突
   - **决策**：标点零容忍**两档共用**（FR-7 已明示），严肃文学也不能用 ——；只有句长/嵌套/成语等量化维度分档

5. **是否引入"装逼度"语义 LLM 检查器**（4D 选项）
   - **当前回答**：1A/2A/3A/4C 已选 C 不选 D；本 PRD 不含 LLM 语义评分，全部走规则 + 量化指标。如果 G4（LLM 盲评 ≥ 70%）未达成，再单开 PRD 加 4D

---

## Implementation Sequencing（建议执行顺序）

1. **Phase 1（1-2 天）**：US-001（标点零容忍） + US-004（黑名单扩展）—— 立竿见影，痛点 1 直接消失
2. **Phase 2（2-3 天）**：US-002（colloquial-checker） + US-003（directness 全场景）—— 痛点 2/3 上检查器
3. **Phase 3（2-3 天）**：US-005（writer L11 + 删反向引导） + US-007（Hard Block Rewrite）—— 写作端范式重构 + 修复闭环
4. **Phase 4（3-4 天）**：US-006（爆款 RAG 索引 + retrieval 接入）—— 最重的一块
5. **Phase 5（1-2 天）**：US-008（阈值 calibration） + US-009（E2E 双盲）—— 验收
6. **Phase 6（0.5 天）**：US-010（文档 + 回滚开关）—— 收尾

总工时估计：**10-15 天**（与档位 4C 深层重构匹配）

---

## Checklist（PRD 写完前自检）

- [x] 与用户确认决策档位（1A/2A/3A/4C）
- [x] 基于代码扫描定位三大根因（行号级证据）
- [x] 10 个 US 全部可验证、可单测
- [x] 7 层架构图完整
- [x] 阈值分档不违反"标点零容忍两档共用"原则
- [x] 不退化条款写入 G5 + Success Metrics
- [x] 三个独立回滚开关 + 总开关
- [x] Open Questions 给出建议方向，未拍板
- [x] 路径全部用绝对路径或仓库相对路径，不含猜测的 placeholder
