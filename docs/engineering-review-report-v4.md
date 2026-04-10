# ink-writer v11.3.1 第三轮工程审查报告

**审查日期**: 2026-04-11
**审查轮次**: 第三轮（验证性审查 + 写作质量评估）
**审查方法**: 2 个专项 Agent（全链路端到端验证 / 写作质量产出能力评估）

---

## 一、工程闭合性验证

### 结论：32 项修复全部闭合，无新断裂

| 检查项 | 结果 | 说明 |
|--------|------|------|
| mega-summary 完整链路 | **PASS** | auto-compress → save-mega → vol{N}_mega.md → _load_volume_summaries，路径完全一致 |
| step3_harness_gate 接入 | **PASS** | SKILL.md Step 3.5 存在，exit code 语义匹配，无报告时安全降级 |
| _get_conn(immediate) 一致性 | **PASS** | 3 个核心 mixin 的 18 个写方法已迁移，无双重 commit |
| chapters_per_volume 配置化 | **PASS** | 全部从环境变量/config 读取，无硬编码 50 遗留 |
| computational_checks SQL | **PASS** | 6 处 SQL 查询与真实 Schema 逐列比对，完全一致 |
| 数据流闭环 | **PASS** | data-agent 标准枚举 → 检测匹配值 → 伏笔 schema 对齐，全部闭合 |
| 测试覆盖 | **PASS** | 1083 passed, 0 failed, 82.77% coverage |

### 唯一遗留项（LOW）

`index_manager.py` 本体、`index_observability_mixin.py`、`index_debt_mixin.py`、`sql_state_manager.py` 中的写方法仍使用 `_get_conn()` 无 immediate。单线程 CLI 场景无实际风险，建议下一版本批量修正。

---

## 二、写作质量产出能力评估

### 总体评分：78/100

v11.3.1 在工程基建层面已达到网文量产的**合格线以上**。核心瓶颈已从工程问题转移到 LLM 本身的创造力上限。

| 维度 | 评分 | 核心优势 | 核心不足 |
|------|------|---------|---------|
| 黄金三章 | ★★★★☆ | 10 秒扫读测试 + ch1-3 专项审查 + Harness 硬拦截 | ch1 第一句缺计算型锚点；缺简介质检 |
| 反 AI 味 | ★★★★☆ | 8 层检测 + 标杆数据校准 + 阈值反转修正 | 缺词汇多样性(TTR)检测；计算型闸门阈值过松 |
| 长篇记忆 | ★★★☆☆ | 卷级 mega-summary + 伏笔闭环 + 角色冲突检测 | 摘要窗口仅 3 章，200 章时信息损失严重；缺关键对话索引 |
| 追读力/节奏 | ★★★★☆ | Override 债务系统 + Strand Weave + 冲突去重 | 过渡章豁免可能被滥用（连续 2 章零爽点） |
| 风格锚定 | ★★★☆☆ | scene-craft-index 可执行技法 + Style RAG 3295 片段 | 风格采纳缺验证闭环；角色声音长篇收敛 |

---

## 三、按优先级排列的改进项

### P1 — 直接影响写作质量

#### 1. 记忆摘要窗口过窄（3 章），200 章时信息损失严重

**文件**: `ink-writer/scripts/data_modules/context_manager.py`

`_load_recent_summaries` 默认 `window=3`，第 200 章只看第 197-199 章摘要。卷级 mega-summary 覆盖远距离，但中距离（10-50 章前）存在记忆空白。一个次要角色在第 180 章的关键台词到第 200 章时已不在上下文中。

**建议**: 将 `context_recent_summaries_window` 从 3 扩大到 5-8，或引入"滑动窗口+关键章摘要"混合策略——近 5 章全文摘要 + 历史高分章/关键转折章的摘要常驻。

#### 2. 缺少词汇多样性（TTR）检测

**文件**: `ink-writer/scripts/computational_checks.py`

AI 文本的 type-token ratio 显著低于人类文本，这是朱雀等检测工具的核心特征之一。当前 8 层反 AI 检测完全没覆盖词汇多样性维度。

**建议**: 新增 `check_vocabulary_diversity(chapter_text)` 函数，计算去停用词后的 TTR，低于阈值（标杆约 0.45-0.55）时报 soft warning。

#### 3. 计算型闸门情感标点阈值与 checker 不对齐

**文件**: `ink-writer/scripts/computational_checks.py:476-497`

`check_emotion_punctuation` 的报警阈值是感叹号 < 0.5/千字，但 `anti-detection-checker` 的 high 阈值是 < 1.5/千字。计算型闸门设置过松，无法有效前置拦截。

**建议**: 将感叹号阈值从 0.5 提到 1.0，问号从 0.5 提到 1.0，使计算型闸门能拦截明显偏低的情况。

### P2 — 提升写作质感

#### 4. 角色语言指纹缺失，长篇声音收敛

当前系统缺少角色级别的语言特征锁定。100 章后，不同角色的对话风格会逐渐趋同。

**建议**: 在 data-agent 的 `character_evolution_ledger` 中增加 `voice_fingerprint` 字段（口头禅、句式偏好、用词特征），context-agent 构建执行包时注入对应角色的语言指纹。

#### 5. 伏笔逾期检测阈值过宽（20 章）

**文件**: `ink-writer/scripts/computational_checks.py`

`check_foreshadowing_consistency` 中逾期阈值为 `delay > 20` 章才报 soft warning。一个预期第 50 章回收的伏笔到第 69 章还不会被标记。

**建议**: 分级告警——逾期 10 章 info，逾期 20 章 soft warning，逾期 30 章 hard warning。

#### 6. 过渡章豁免可能被滥用

`reader-pull-checker` 的 `TRANSITIONAL_SETUP` 理由能覆盖 4 项软约束，连续 2 章过渡章理论上可以零爽点零钩子。

**建议**: 增加"连续过渡章上限"硬约束——不允许连续 2 章以上使用 `TRANSITIONAL_SETUP` Override。

### P3 — 锦上添花

#### 7. 缺少简介质检

起点编辑第一眼看的是简介而非正文，但 golden-three-checker 不检查简介质量。

**建议**: 在 `golden_three_plan.json` 中增加 `synopsis` 字段，golden-three-checker 对简介做 10 秒扫读测试。

#### 8. ch1 第一句缺计算型锚点

ch1 前 300 字的"强触发"完全依赖 LLM 主观判断。第一句是否包含认知缺口/反常识/危机信号，可以用正则初筛。

**建议**: 在 `computational_checks.py` 中新增 `check_first_sentence_hook`，检测第一句是否以对话/行动/感官/冲突开头（vs 说明性/描写性开头）。

#### 9. 风格采纳度缺验证闭环

Style RAG 检索了标杆片段注入执行包，但没有机制验证 writer-agent 是否真的吸收了风格。

**建议**: 在 anti-detection-checker 或 Step 2C 中增加"风格契约对比"——对比执行包注入的风格参数（句长、对话比、情感密度）与实际产出的偏差度。

---

## 四、差距-可弥补性矩阵

| 差距维度 | 当前覆盖度 | 可弥补性 | 优先手段 |
|---------|-----------|---------|---------|
| 黄金三章结构 | 90% | 工程可补 | 简介质检 + 第一句检测 |
| 反 AI 味（统计层） | 85% | 工程可补 | TTR 检测 + 对齐闸门阈值 |
| 反 AI 味（风格层） | 60% | 部分可补 | 风格采纳度反馈闭环 |
| 长篇记忆精度 | 65% | 工程可补 | 扩大摘要窗口 + 关键对话索引 |
| 追读力/节奏 | 85% | 已接近上限 | 收紧过渡章豁免 |
| 微观意外感 | 30% | **LLM 上限** | 需外部创意注入（人类参与大纲） |
| 角色声音区分度 | 50% | 部分可补 | 角色语言指纹 + 对话风格锁定 |
| 闲笔/文学质感 | 55% | 部分可补 | scene-craft-index 持续扩充 |

---

## 五、总结

### 三轮审查修复历程

| 版本 | 发现 | 修复 | 核心突破 |
|------|------|------|---------|
| v11.2.0 → v11.3.0 | 22 项（3 CRITICAL） | SQL 全面对齐 + 记忆补全 + 闸门强化 | 计算型闸门从"全失效"到"真正工作" |
| v11.3.0 → v11.3.1 | 10 项（1 P0） | save-mega 接入 + harness 激活 + 写事务统一 | 链路闭合 + 死代码清除 |
| v11.3.1 验证 | 0 断裂 + 9 改进 | — | **工程层面已无阻断性问题** |

### 最终评价

**工程完备性：92/100** — 32 项修复全部闭合验证通过，1083 测试全绿，闸门层层嵌套，"写出明显烂文"的概率很低。

**写作质量产出：78/100** — 黄金三章和追读力达到量产合格线以上，反 AI 味能力在同类工具中领先。核心瓶颈已从工程问题转移到 LLM 创造力上限（微观意外感 30%、角色声音长篇收敛 50%）。

**下一步建议**：优先投入 P1 的 3 项改进（记忆窗口 + TTR 检测 + 闸门阈值对齐），预计 4 小时可完成，能将写作质量评分从 78 提升到 82-85。
