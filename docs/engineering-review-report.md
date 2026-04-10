# ink-writer 工程深度审查报告

**审查日期**: 2026-04-11
**审查范围**: 全项目工程架构、逻辑完备性、TDD覆盖、Harness可靠性
**核心问题**: 能否稳定产出"黄金三章抓人、长篇记忆不错乱、快速吸引读者"的小说？

---

## 一、总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 工程架构 | ★★★★☆ | 14 Agent 流水线设计成熟，分步解耦清晰 |
| 测试覆盖 | ★★★★☆ | 1034 测试全通过，覆盖率 83%，但关键路径有盲区 |
| 记忆系统 | ★★★☆☆ | SQLite+RAG+mega-summary 三层架构完整，但存在逻辑漏洞 |
| 黄金三章 | ★★★★☆ | 有专项 checker + golden_three.py + genre-adaptive 契约，但缺端到端验证 |
| 质量闸门 | ★★★☆☆ | 计算型闸门 + 10 checker + 自动修复，但"假阳性通过"风险高 |
| 长篇稳定性 | ★★☆☆☆ | 300+ 章场景最薄弱，多个组件存在退化隐患 |

---

## 二、按优先级排列的修改项

### P0 — 阻断性逻辑漏洞（必须立即修复）

#### 1. 记忆系统：远距离摘要窗口固定，长篇必然遗忘

**文件**: `context_manager.py:1100-1106`

```python
def _load_recent_summaries(self, chapter: int, window: int = 3) -> List[Dict[str, Any]]:
    for ch in range(max(1, chapter - window), chapter):
        summary = self._load_summary_text(ch)
```

**问题**: `window=3` 硬编码，第 200 章只看第 197-199 章摘要。mega-summary 虽然存在，但 `_load_recent_summaries` **完全不引用它**。第 1-50 章发生的事情在第 100 章后就成了黑洞。

**影响**: 角色"被遗忘"、伏笔永远回收不了、前后设定矛盾。这是长篇写作的致命伤。

**修复方案**:
- `_load_recent_summaries` 应在 recent window 之外叠加 mega-summary 层
- 引入"远距离摘要注入"逻辑：当 chapter > 50 时，自动加载相关卷的 mega-summary
- 结合 RAG 检索相关历史片段，补充到 core.relevant_history

#### 2. 计算型闸门：角色冲突检查形同虚设

**文件**: `computational_checks.py:117-153`

```python
def check_character_conflicts(chapter_text: str, project_root: Path) -> CheckResult:
    # ... 获取所有已知实体名称和别名 ...
    # 简单检测：检查已知角色是否在正文中出现了错误的名字变体
    # 这里只做基础检查，复杂的交给 consistency-checker
    return CheckResult("character_conflicts", True, "soft", f"已知实体 {len(known_names)} 个，基础检查通过")
```

**问题**: 这个函数**永远返回 True**。它获取了实体名称列表，但没有做任何实际的冲突检测，直接返回"通过"。这是一个占位函数伪装成了真实检查。

**影响**: 计算型闸门（Step 2C）声称检查了角色冲突，但实际上什么都没做。角色名字混用、死去角色复活等明显错误无法在低成本阶段拦截。

**修复方案**:
- 实现真实的检查逻辑：已死亡角色出现在正文、角色名拼写错误、已离场角色突然出现
- 至少检测 `entities WHERE status='dead'` 的角色名是否出现在正文中
- 检测角色 `last_seen_location` 与当前场景的地理一致性

#### 3. 战力等级检查形同虚设

**文件**: `computational_checks.py:194-215`

```python
def check_power_level(chapter_text: str, project_root: Path) -> CheckResult:
    realm = power.get("realm", "")
    if not realm:
        return CheckResult("power_level", True, "soft", "主角境界未设置，跳过能力检查")
    return CheckResult("power_level", True, "soft", f"主角当前境界: {realm}")
```

**问题**: 同上，只读取了境界信息但**没有做任何校验**，直接返回通过。越级使用技能、突然降级等问题完全不检测。

**修复方案**:
- 比对 `power.abilities` 列表与正文中出现的技能/招式名
- 检测"不应出现的高级词汇"（如主角还在筑基期但正文出现"渡劫"相关能力描写）

#### 4. SQLite 并发写入无事务保护

**文件**: `index_manager.py`, `sql_state_manager.py`, `context_manager.py` 等

**问题**: Step 3 启动最多 10 个并行 checker Agent，Step 5 Data Agent 并行写入 index.db。虽然使用了 WAL 模式（允许并发读），但没有看到**写入事务**的隔离保护。多个 Data Agent 写同一张表时可能：
- 同一实体被重复插入（upsert 无 row-level lock）
- 关系事件写入丢失（两个 Agent 同时 INSERT）
- 审查指标覆盖而非追加

**影响**: 偶发的数据不一致，难以复现和定位。

**修复方案**:
- Data Agent 写入使用 `BEGIN IMMEDIATE` 事务
- 为高频写入操作（upsert_entity, record_state_change）加 retry-on-busy 逻辑
- 添加集成测试：并发写入场景

---

### P1 — 严重质量风险（影响产出质量）

#### 5. 黄金三章：有检测无强制闭环

**文件**: `golden_three.py`, `step-3-review-gate.md`

**问题**: golden-three-checker 作为**条件审查器**，只在 `chapter <= 3` 时启用，且审查结果是 soft warning。如果 `analyze_golden_three_opening` 检测到"前300字无强触发"，它只产出一个 `severity: high` 的 issue，但 Step 3 汇总时没有对黄金三章实施**硬拦截**。

也就是说：第 1 章开头写了 500 字景物描写，checker 报了 high，但流水线仍然可以继续到 Step 4 润色、Step 5 回写、Step 6 git commit。这等于黄金三章失效。

**修复方案**:
- 对 chapter 1-3 的 golden-three-checker，`high` 级别 issue 应升级为硬失败
- Step 3 聚合逻辑增加判断：若 `chapter <= 3 && golden_three_issues.any(severity='high')` → 强制回退 Step 2A 重写
- 添加 TDD 测试：模拟前 3 章各种开头模式，验证黄金三章门控行为

#### 6. 对话占比检查阈值过低

**文件**: `computational_checks.py:259-276`

```python
if ratio < 0.05:  # 5%
    return CheckResult("dialogue_ratio", False, "soft", ...)
```

**问题**: 标杆值 34.5%，但只在 < 5% 时才报 soft warning。5%-15% 这个"明显偏低"区间完全不告警。而且 severity 是 "soft"，不阻断流程。

**修复方案**:
- 增加分层告警：< 5% = hard, 5-15% = soft warning, 15-25% = info
- 对非独处/修炼章，调高阈值
- 修炼/独处章豁免应通过大纲标签判定，不能让 LLM 自行决定

#### 7. 元数据泄漏检查是假阳性

**文件**: `computational_checks.py:326-336`

```python
def check_metadata_leakage(chapter_text: str) -> CheckResult:
    hits = [p for p in METADATA_PATTERNS if re.search(p, tail)]
    if hits:
        return CheckResult("metadata_leakage", True, "soft", ...)  # passed=True!
```

**问题**: 检测到元数据泄漏后，`passed` 仍然是 `True`！这意味着泄漏了也当作通过。应该是 `False`。

**修复方案**: `passed=True` → `passed=False`

#### 8. context_manager：Token 预算无硬上限

**文件**: `context_manager.py`

**问题**: Token Budget v3 定义了各板块权重和优先级，但没有看到**总 token 数的硬上限**。当项目积累了数百个实体、数十条伏笔、大量关系时，context pack 可能膨胀到超出模型上下文窗口，导致重要信息被截断。

**修复方案**:
- 为 `_build_pack` 添加总 token 估算（中文≈1.5 char/token）
- 当 pack 超出预算时，按优先级裁剪低价值信息
- 记录裁剪日志，供后续诊断

#### 9. ink-auto.sh 完结时直接写 state.json

**文件**: `ink-auto.sh:857-863`

```bash
python3 -X utf8 -c "
import json
with open('${PROJECT_ROOT}/.ink/state.json', 'r') as f:
    state = json.load(f)
state.setdefault('progress', {})['is_completed'] = True
with open('${PROJECT_ROOT}/.ink/state.json', 'w') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
" 2>/dev/null || true
```

**问题**: SKILL.md 明确禁止"直接写 state.json"（必须通过 ink.py CLI），但 ink-auto.sh 在完结检测时直接用 Python 内联修改 state.json。这违反了自身定义的约束，且绕过了 `atomic_write_json` 的安全写入机制。

**修复方案**: 通过 `ink.py state update-field` 或类似 CLI 命令来修改完结标记。

---

#### 10. reader-simulator "rewrite" 判定不阻断流水线

**文件**: `agents/reader-simulator.md`, `step-3-review-gate.md`

**问题**: reader-simulator 产出 `reader_verdict.verdict = "rewrite"`（总分 < 25）时，语义上要求"重写"，但 Step 3 聚合逻辑**没有将其路由回 Step 2A**。reader-simulator 的评分独立于 `overall_score`，不参与加权计算，也不触发硬拦截。

**影响**: 一个设定一致、逻辑通顺但**读者体验极差**的章节可以顺利通过 Step 3 → Step 4 → 发布。

**修复方案**: 当 `reader_verdict.verdict == "rewrite"` 时，强制回退 Step 2A 重写（至少对前 3 章启用）。

#### 11. anti-detection opening pattern critical 不影响总分

**文件**: `agents/anti-detection-checker.md`

**问题**: 开头时间标记模式检测结果为 `critical`，但文档明确说"不计入综合评分"。这意味着即使第 1 章以"第一天清晨"开头（典型 AI 味），overall_score 仍可能达到 70+，不触发总分 cap 60 的硬拦截。

**影响**: 最明显的 AI 味信号（时间标记开头）无法通过评分体系拦截。

**修复方案**: 将 opening pattern critical 纳入总分 cap 逻辑。

#### 12. mega-summary 压缩未自动触发

**文件**: `data_modules/memory_compressor.py`

**问题**: `memory_compressor.py` 文档注释说"由 ink-write Step 0 在新卷第 1 章时自动触发"，但代码中**没有实际的自动调用**。需要手动执行 `ink.py memory compress-volume`。

**影响**: 长篇写作（50+ 章）时，远距离记忆压缩完全依赖用户手动操作。如果用户使用 `/ink-auto 100`，100 章写完也不会自动压缩。

**修复方案**: 在 Step 0 或 `ink-auto.sh` 主循环中添加自动压缩触发。

---

### P2 — 测试/覆盖盲区（影响可维护性和回归安全）

#### 13. 关键路径测试缺失

| 模块 | 覆盖率 | 缺失场景 |
|------|--------|---------|
| `computational_checks.py` | 14% | 大部分函数只有路径覆盖，无边界条件 |
| `context_manager.py` | 11% | 几乎无测试，核心 `_build_pack` 未覆盖 |
| `memory_compressor.py` | 0% | **零测试** — 跨卷记忆压缩完全未测试 |
| `writing_guidance_builder.py` | 0% | **零测试** — 写作指导生成完全未测试 |
| `anti_ai_scanner.py` | 7% | 反 AI 检测引擎近乎裸奔 |
| `anti_ai_lint.py` | 17% | AI 味检测逻辑未充分测试 |
| `archive_manager.py` | 10% | 备份恢复逻辑未测试 |
| `backup_manager.py` | 11% | 同上 |

**核心风险**: `context_manager.py` 是整个系统最核心的模块（上下文构建），11% 覆盖率意味着任何重构都可能引入回归 bug。`memory_compressor.py` 和 `writing_guidance_builder.py` 是 0% 覆盖率 — 完全没有测试。`computational_checks.py` 是唯一的确定性门控，14% 覆盖率无法保证闸门逻辑正确。

**修复方案**:
- **紧急**: 为 `memory_compressor.py` 补充基础测试（压缩触发条件、摘要生成、幂等性）
- **紧急**: 为 `writing_guidance_builder.py` 补充基础测试（craft lesson 加载、checklist 生成）
- 优先补全 `context_manager.py` 的 `_build_pack` 集成测试
- 补全 `computational_checks.py` 的边界条件测试（空文件、极短文本、极长文本、特殊字符）
- 为 `anti_ai_scanner.py` 补充对标杆文本和典型 AI 文本的检测测试

#### 14. 无端到端集成测试

**问题**: 1034 个测试全是单元/模块级测试。没有一个测试模拟完整的 Step 0 → Step 6 流水线。无法验证：
- 各步骤之间的数据流转是否正确
- Step 2C 闸门失败时是否真的回退到 Step 2A
- Step 3 审查结果是否正确传递给 Step 4

**修复方案**:
- 编写 1-2 个 fixture-based 端到端测试
- 使用 mock LLM 响应，测试流水线的编排逻辑
- 重点覆盖：正常通过、闸门拦截、审查修复循环

#### 15. ink-auto.sh 无自动化测试

**问题**: 500+ 行 bash 脚本，包含复杂的循环/条件/子进程管理逻辑，完全没有测试。检查点编排器、验证函数、信号处理等关键逻辑全靠人肉验证。

**修复方案**:
- 将核心逻辑（检查点判定、章节验证、报告生成）抽取为可测试的 Python 模块
- `checkpoint_utils.py` 已经存在且有测试——将更多 bash 逻辑迁移到 Python
- 对 bash 脚本编写 bats 测试或 pytest + subprocess 测试

---

### P3 — 优化建议（提升产出质量上限）

#### 16. Style RAG 检索与写作执行缺乏反馈闭环

**问题**: Style RAG 检索了标杆片段注入执行包，但没有机制验证 writer-agent 是否真的**吸收并应用**了这些风格。anti-detection-checker 检查的是统计指标（句长、对话比），不检查风格采纳度。

**建议**:
- 在 Step 4 润色后，做一次"风格锚定度"检查（对比注入片段的风格特征 vs 产出文本特征）
- 将风格采纳度记入 review_metrics，追踪趋势

#### 17. 开头模式检测覆盖不完整

**文件**: `computational_checks.py:283-293`

**问题**: `_OPENING_TIME_PATTERNS` 只覆盖了中文时间表达的一部分，缺少：
- "过了几天"、"一晃三年"
- "当XXX的时候"（条件时间）
- 数字+时间单位：如"半个时辰后"

**建议**: 补充更多模式，或改为基于规则+关键词混合检测。

#### 18. 伏笔逾期检测阈值单一

**文件**: `computational_checks.py:156-191`

**问题**: 只检查 `> 20 章逾期` 的伏笔，但 10-20 章的"中度逾期"不告警。对于节奏快的题材（如都市/电竞），5-10 章逾期就应该告警。

**建议**: 按题材配置逾期阈值，从 genre_profile 读取。

#### 19. 审查路由"条件触发"可能漏检

**文件**: `step-3-review-gate.md:48-80`

**问题**: reader-pull-checker、high-point-checker 等条件审查器依赖 Step 1.5 合同和正文信号来判定是否启用。但"信号判定"本身依赖 LLM 的判断，可能因 LLM 漏判而跳过审查。

**建议**:
- 每 N 章强制启用全量审查器（当前每 5 章通过检查点审查，但检查点审查深度为 Core = 只有 4 个必选 checker）
- 定期（如每 10 章）做一次 Full 模式审查，覆盖全部 10 个 checker

#### 20. 角色声音样本机制不够鲁棒

**文件**: `context_manager.py:1156-1160`

**问题**: 角色语音样本只取最近一条 (`recent_voice_sample`)，不做多样性采样。如果最近一条恰好是该角色的非典型台词（如受伤时的虚弱语气），writer-agent 可能以此为锚写出 OOC 对话。

**建议**: 取 2-3 条不同类型的台词样本，标注情绪标签，让 writer-agent 知道这是角色的正常范围。

---

## 三、架构级观察

### 优点

1. **Skill 即规范**: 用 SKILL.md 定义完整流程，LLM 作为执行器而非设计者，降低了随机性
2. **计算型闸门（Step 2C）**: 在昂贵的 LLM 审查前做确定性检查，理念正确
3. **观测性**: call_trace.jsonl + 质量趋势报告 + 运行报告，可追溯可诊断
4. **ink-auto 跨会话隔离**: 每章新进程，避免上下文污染，是解决长篇写作的正确思路
5. **Override Contract + 债务系统**: 允许有理由地违背约束，同时追踪偿还，设计精巧
6. **标杆分析系统**: 117 本标杆 + 3295 片段，数据驱动而非拍脑袋

### 风险点

1. **LLM-as-judge 的脆弱性**: 10 个 checker 全依赖 LLM 判断，LLM 模型升级/换代可能导致审查标准漂移
2. **单点故障**: state.json 是全局状态文件，损坏则整个项目不可恢复（虽有 backup_manager，但恢复流程未测试）
3. **隐性耦合**: SKILL.md 中的流程指令（自然语言）与 Python 脚本（代码）之间通过 CLI 调用耦合，版本不同步时会静默失败

---

## 四、修复优先级总表

| 优先级 | 编号 | 问题 | 影响范围 | 估计工作量 |
|--------|------|------|---------|-----------|
| **P0** | #1 | 远距离摘要不注入，长篇必遗忘 | 全部 50+ 章项目 | 中 |
| **P0** | #2 | 角色冲突检查永远返回 True | 所有章节 | 小 |
| **P0** | #3 | 战力等级检查永远返回 True | 仙侠/玄幻类 | 小 |
| **P0** | #4 | SQLite 并发写入无事务保护 | 偶发数据丢失 | 中 |
| **P1** | #5 | 黄金三章无硬拦截 | 前 3 章质量 | 小 |
| **P1** | #6 | 对话占比阈值过低 | 章节对话质量 | 小 |
| **P1** | #7 | 元数据泄漏 passed=True bug | 泄漏不拦截 | 极小 |
| **P1** | #8 | Token 预算无硬上限 | 大型项目上下文溢出 | 中 |
| **P1** | #9 | ink-auto.sh 直写 state.json | 违反自身约束 | 小 |
| **P1** | #10 | reader-simulator rewrite 不阻断 | 读者体验差的章放行 | 小 |
| **P1** | #11 | anti-detection opening critical 不影响总分 | AI 味开头放行 | 小 |
| **P1** | #12 | mega-summary 压缩未自动触发 | 长篇记忆退化 | 中 |
| **P2** | #13 | 关键模块 0% 覆盖率 | 回归风险 | 大 |
| **P2** | #14 | 无端到端集成测试 | 流水线正确性 | 大 |
| **P2** | #15 | ink-auto.sh 无测试 | bash 逻辑回归 | 中 |
| **P3** | #16-20 | 风格闭环/开头/伏笔/审查/声音 | 质量上限 | 各小 |

---

## 五、结论

**能写出合格的小说吗？** 可以，工程架构设计水平很高，14 Agent 流水线的思路正确。

**能写出"超凡脱俗、黄金三章抓人"的小说吗？** 目前有 3 个 P0 级逻辑漏洞阻碍：

1. **长篇记忆**: 50 章后远距离信息丢失，角色和伏笔会被遗忘
2. **闸门空转**: 计算型闸门（角色冲突 + 战力等级）永远返回通过，等于没有门控
3. **黄金三章软着陆**: checker 报了 high 但不阻断，第一印象无保障

修复 P0 后，系统的可靠性会有质的提升。P1 项目修复后，产出质量可以接近"稳定过起点审核"的水平。P2/P3 是长期投资，提升系统可维护性和质量上限。

**建议的修复顺序**:
1. **一行修复**: #7(元数据bug) → #11(opening critical纳入总分)
2. **填充占位**: #2/#3(角色冲突+战力检查实现真实逻辑)
3. **记忆修复**: #1(远距离摘要注入) → #12(mega-summary自动触发)
4. **门控升级**: #5(黄金三章硬拦截) → #6(对话阈值) → #10(reader-simulator路由)
5. **并发保护**: #4(SQLite事务) → #9(state.json约束)
6. **Token安全**: #8(预算硬上限)
7. **测试补全**: #13(0%覆盖模块) → #14(端到端) → #15(bash测试)
