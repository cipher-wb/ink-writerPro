# ink-writer v11.2 工程深度审查报告

**审查日期**: 2026-04-11
**审查方法**: 5 个专项 Agent 并行审查（记忆系统 / 计算型闸门 / 写作流水线 / 测试覆盖 / 数据流Schema）
**核心问题**: 能否稳定产出"黄金三章抓人、长篇记忆不错乱、快速吸引读者"的小说？
**结论**: **不能**。存在 3 个 CRITICAL 级别的数据流断裂，导致角色冲突检测、伏笔逾期检测、战力检测三大计算型闸门全部形同虚设。

---

## 一、总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 工程架构 | ★★★★☆ | 14 Agent 流水线 + 9 步分层解耦，设计成熟 |
| 测试覆盖 | ★★★★☆ | 1050 测试全通过，覆盖率 82.59%，但关键路径有致命盲区 |
| 计算型闸门 | ★☆☆☆☆ | **SQL 列名/表名/值全部对不上**，三大检测项静默返回"通过" |
| 记忆系统 | ★★☆☆☆ | mega-summary 从未被自动生成，50+ 章后远距离记忆是黑洞 |
| 黄金三章 | ★★★★☆ | 硬拦截机制设计正确，但依赖 golden_three_plan.json 才能精准 |
| 长篇稳定性 | ★★☆☆☆ | 伏笔数据源割裂 + 死代码 + 无端到端测试，300+ 章场景最薄弱 |
| 风格一致性 | ★★★☆☆ | Style RAG 架构完整，但新项目冷启动阶段无动态风格锚定 |

---

## 二、按优先级排列的修改项

### P0 — CRITICAL：数据流断裂，闸门全部失效

#### 1. computational_checks.py 的 SQL 查询与实际 Schema 完全不匹配

**严重程度**: 这是当前系统最致命的 bug。三个计算型检测函数的 SQL 全部查错了列名/表名/值，异常被 `except OperationalError: pass` 静默吞掉，导致检测永远返回"通过"。

| 检测函数 | 代码写的 | 实际 Schema | 后果 |
|----------|---------|-------------|------|
| `check_character_conflicts` | `SELECT name FROM entities WHERE type = 'character'` | 列名是 `canonical_name`，type 值是 `'角色'`（中文） | 已死角色复活无法检测 |
| `check_character_conflicts` | `SELECT alias FROM aliases` | 列名是 `alias_name` | 别名匹配全部跳过 |
| `check_foreshadowing_consistency` | `FROM plot_threads WHERE status = 'active' AND expected_payoff_chapter < ?` | 表名是 `plot_thread_registry`，列名是 `target_payoff_chapter` | 伏笔逾期检测全部跳过 |
| `check_power_level` | `WHERE field IN ('ability_lost', 'sealed_ability', 'disabled_skill')` | data-agent 写入的 field 名无规范约束 | 能力冲突检测形同虚设 |

**文件**: `ink-writer/scripts/computational_checks.py:130-298`

**根因**: computational_checks.py 是基于"预想的 Schema"编写的，从未与 index_manager.py 的实际建表语句对齐。所有 SQL 错误被 try/except 静默吞掉，测试中使用的是手工构建的临时 DB（字段名与测试匹配但与生产不匹配），所以测试全绿但生产全部失效。

**修复方案**:
```python
# 修复列名
"SELECT canonical_name FROM entities WHERE type = '角色'"
# 修复别名
"SELECT alias_name FROM aliases"
# 修复伏笔表
"FROM plot_thread_registry WHERE status = 'active' AND target_payoff_chapter < ?"
```
同时修复测试，使用与 index_manager._ensure_tables() 一致的建表语句。

---

#### 2. `disabled_abilities` / `lost_items` 无写入来源，战力检测永远为空

**文件**: `computational_checks.py:265-298`、`update_state.py`、`agents/data-agent.md`

`check_power_level` 从 state.json 读取 `protagonist.power.disabled_abilities` 和 `protagonist.power.lost_items`，但：
- `update_state.py` 没有写这两个字段的方法
- `data-agent.md` 没有定义如何提取这两个字段
- 没有任何代码路径会填充它们

**后果**: 即使主角在第 50 章失去一个技能，第 51 章用了也不会被拦截。

**修复方案**: 在 data-agent 的 StateChange 输出规范中增加能力丧失/封印的标准化写入约定，并在 update_state.py 中增加对应 setter；或改为从 state_changes 表用 LIKE 匹配反推。

---

### P1 — HIGH：长篇记忆黑洞 + 闸门绕过

#### 3. mega-summary 永远不会被自动生成

**文件**: `ink-auto.sh:833-847`、`ink.py:566-585`、ink-write SKILL.md

ink-auto.sh 中的 `memory auto-compress` 只输出检测结果并打印提示"将由 ink-write Step 0 自动执行"，但 **ink-write SKILL.md 中不存在任何 mega-summary 生成步骤**。`_load_volume_summaries` 找不到 `vol{N}_mega.md` 时返回空列表。

**后果**: 200 章长篇中，第 1-50 章的剧情信息在第 100 章后完全丢失。角色"被遗忘"、伏笔永远回收不了、前后设定矛盾。这是长篇写作的致命伤。

**修复方案**: 在 ink-write Step 0 中增加 mega-summary 自动生成步骤：检测 `needed=True` 时调用 LLM 生成摘要并执行 `save_mega_summary()`。或在 ink-auto.sh 中直接执行而非仅提示。

---

#### 4. 伏笔检测依赖 index.db 但写入在 state.json，数据源割裂

**文件**: `update_state.py:278`（写入 state.json）、`computational_checks.py:221-225`（读取 index.db）

`update_state.py` 的 `add_foreshadowing()` 将伏笔写入 state.json 的 `plot_threads.foreshadowing`（字段：`planted_chapter/target_chapter/content`），但检测函数查的是 index.db 的 `plot_thread_registry` 表（字段：`thread_id/planted_chapter/target_payoff_chapter`）。两者 Schema 完全不同且无同步机制。

**后果**: 通过 update_state.py 添加的伏笔永远不会被检测到逾期。

**修复方案**: 在 `add_foreshadowing()` 中同步写入 index.db，或检测函数同时查 state.json 作为 fallback。

---

#### 5. `_write_transaction` 是死代码，所有 index.db 写操作无事务保护

**文件**: `index_manager.py:939-968`

新增的 `_write_transaction()` 提供了 BEGIN IMMEDIATE + retry-on-busy 的安全写入包装，但 **没有任何 mixin 调用它**。所有写操作（`add_chapter`、`upsert_entity`、`record_state_change` 等）直接使用 `_get_conn()` + `conn.commit()`。

**后果**: 无 BEGIN IMMEDIATE 保护，并发写入可能冲突；无 retry 机制，busy 时直接失败。

**修复方案**: 将核心 mixin 写操作迁移到 `_write_transaction()`，或在 `_get_conn` 中默认启用 BEGIN IMMEDIATE。

---

#### 6. 角色死亡/离场状态的 field/value 无标准化约束

**文件**: `computational_checks.py:152-158`、`agents/data-agent.md`、`schemas.py:31-38`

检测端硬编码 `new_value IN ('dead', '死亡', '已死', '阵亡')`，但 data-agent 写入的是自由文本，StateChange schema 中 field 和 new_value 都无 enum 约束。如果 LLM 写 `"战死"` / `"牺牲"` / `"身亡"`，检测就漏掉了。

**修复方案**: (a) 在 data-agent.md 中明确约束死亡状态必须写 `field='status', new_value='dead'`；(b) 检测侧用 LIKE/正则扩大匹配范围；(c) 在 schemas.py 增加 enum 校验。

---

#### 7. Step 3 审查闸门全靠 prompt 指令，无 harness 硬拦截

**文件**: `step-3-review-gate.md:207-209`、SKILL.md

黄金三章硬拦截、反 AI 开头 cap 60、读者体验阻断等闸门规则定义在 markdown 中，由 LLM 执行。Step 2C 有 `exit code 1` 的 harness 硬拦截，但 Step 3 → Step 4 的闸门判定完全依赖 LLM 遵守 prompt 规则。

**后果**: LLM 可能忽略 golden-three-checker 的 high 判定继续润色，结构性问题未修复就发布。

**修复方案**: 新增 Step 3.5 harness 级闸门脚本：读取 review_metrics.json，检查 overall_score / critical issues / golden-three 判定，返回 exit code 作为硬拦截。

---

#### 8. 新项目前 10 章无风格样本 fallback

**文件**: SKILL.md Step 2B、`rag_adapter.py`

Style RAG 的风格样本来自本项目已有高分章节，但新项目前几章 RAG 库为空，writer-agent 第 11 板块"风格参考样本"不存在，完全依赖静态写作铁律。

**修复方案**: 新项目前 10 章提供 `benchmark_style_sample` fallback——从 `scene-craft-index.md` 范例或 `style_rag.db` 标杆库中按 genre+scene_type 检索注入。

---

#### 9. golden_three_plan.json 缺失时 ch1-3 审查泛化

**文件**: `agents/golden-three-checker.md`、SKILL.md Step 0

如果项目没有通过 `/ink-init` 生成 `golden_three_plan.json`，golden-three-checker 仍可运行但缺少项目特定契约（金手指是什么、核心卖点是什么），审查变成通用标准。

**修复方案**: Step 0 预检增加 ch<=3 时 `golden_three_plan.json` 存在性检查，缺失时 warn 提示用户补充。

---

#### 10. `memory_compressor.py` 测试覆盖率 0%

**文件**: `ink-writer/scripts/data_modules/memory_compressor.py`（63 行，0 测试）

ink.py 的 `memory auto-compress` 子命令依赖此模块，压缩逻辑若出错会丢失记忆上下文。

**修复方案**: 补充 roundtrip 测试 + 压缩阈值边界 + 异常处理测试。

---

### P2 — MEDIUM：质量波动与工程债务

#### 11. 对话占比正则只匹配 `""` 不匹配 `「」`

**文件**: `computational_checks.py:368`

正则 `\u201c[^\u201d]*\u201d` 只匹配中文双引号，完全不匹配日式引号 `「」`。使用 `「」` 的章节对话占比计为 0%，触发 hard failure 误报。

**修复**: 正则改为 `[\u201c\u300c][^\u201d\u300d]*[\u201d\u300d]`。

---

#### 12. 元数据泄漏检测只查末尾 500 字符

**文件**: `computational_checks.py:427-444`

`METADATA_PATTERNS` 缺少常见泄漏模式（`（作者按）`、`【注】`、`## Summary`），且只扫描末尾。

**修复**: 全文扫描 + 扩充 patterns。

---

#### 13. Token 预算裁剪后无通知 writer-agent

**文件**: `context_manager.py:210-234`

裁剪后 section 标记了 `budget_trimmed=True`，但 SKILL.md 中无任何检测和提醒逻辑。writer-agent 不知道上下文被截断。

**修复**: Step 1 执行包构建时检测标记，注入显式提醒。

---

#### 14. `chapters_per_volume` 全项目硬编码为 50

**文件**: `context_manager.py`、`init_project.py`、`chapter_paths.py`、`memory_compressor.py`

4+ 处硬编码，非标卷长项目无法正确切分卷边界。

**修复**: 在 config 中增加配置项，所有硬编码处改为读取 config。

---

#### 15. Step 2C 脚本异常时静默跳过

**文件**: `step-2c-comp-gate.md:60-67`

脚本不存在/超时/异常(exit 2)时直接 fallthrough 进 Step 3，字数不足的草稿可进入昂贵的 LLM Review。

**修复**: 区分"未安装"和"运行时异常"，后者记录 warning 而非静默跳过。

---

#### 16. 句长均值 / 情感标点密度无计算型前置验证

**文件**: `writer-agent.md`、`step-2c-comp-gate.md`

writer-agent 的情感深度自检和句式节奏检查完全依赖 LLM 自觉。Step 2C 只检查字数和命名，不检查句长均值或标点密度。

**修复**: Step 2C 增加句长均值和情感标点密度的 soft warning 检查。

---

#### 17. 检查点修复失败被静默吞掉

**文件**: `ink-auto.sh` run_auto_fix()

修复失败后 `|| true` 静默继续，critical 数据错误可能在修复失败后累积。

**修复**: audit critical 修复失败增加阻断选项。

---

#### 18. reader-pull-checker 过渡章不启用

**文件**: `step-3-review-gate.md`

过渡章不执行追读力审查，导致 `chapter_reading_power` 无记录，下一章差异化检查数据断档。

**修复**: 始终执行硬约束 5 条检查，过渡章仅降级软评分要求。

---

#### 19. update_state.py 不同步 index.db

**文件**: `update_state.py` 全文

仅操作 state.json，不触碰 index.db。虽有金丝雀检查兜底，但手动更新后必须等下次写作才能发现不一致。

**修复**: `save()` 后增加可选的 `--sync-index` 钩子。

---

#### 20. context_manager.py 关键路径未测试

**文件**: `ink-writer/scripts/data_modules/tests/`

`_load_volume_summaries`、Token 预算裁剪（L1156-1284）、`_resolve_context_stage` 均无测试。

**修复**: 补充单测，特别是裁剪边界和卷级摘要加载。

---

#### 21. 无端到端集成测试

现有测试全部是模块级单测，没有模拟"写一章 → 审查 → 修复 → 数据回写"的完整流程。模块间契约可能断裂。

**修复**: 增加 smoke test：`extract_context → computational_checks → index_manager.process_chapter_data → update_state` 完整链路。

---

### P3 — LOW：可优化项

#### 22. polish-agent diff 校验为纯 LLM 判断

Step 4.5 的 diff 校验（剧情事实变更、设定违规）完全由 LLM 判断，存在"自己审自己"的盲区。

**建议**: 数字变更 + 字数变更增加计算型辅助（正则检测 + wc 对比）。

---

#### 23. filelock 为可选依赖，并发降级静默

**文件**: `rag_adapter.py:38-41`

`_HAS_FILELOCK=False` 时直接跳过加锁，单进程无影响但多进程可能丢 chunk。

**建议**: 将 filelock 加入 requirements.txt 为必需依赖。

---

## 三、修复优先级路线图

### 第一阶段：紧急修复（预计 4h）— 让闸门真正工作

| 序号 | 任务 | 预计时间 |
|------|------|----------|
| #1 | 修复 computational_checks.py 全部 SQL（列名/表名/值对齐） | 1h |
| #1 | 同步修复 test_computational_checks.py（用真实 Schema 建表） | 1h |
| #2 | 为 disabled_abilities/lost_items 建立写入通道 | 1h |
| #6 | 在 data-agent.md 中标准化死亡/离场状态的 field/value 枚举 | 0.5h |
| #11 | 修复对话正则支持「」 | 0.5h |

### 第二阶段：记忆系统补全（预计 6h）— 让长篇不失忆

| 序号 | 任务 | 预计时间 |
|------|------|----------|
| #3 | 在 ink-write Step 0 实装 mega-summary 自动生成 | 2h |
| #4 | 统一伏笔数据源（state.json → index.db 同步） | 2h |
| #5 | 将 _write_transaction 接入所有 mixin 写操作 | 1h |
| #10 | 补充 memory_compressor.py 测试 | 1h |

### 第三阶段：闸门 Harness 化（预计 4h）— 让 LLM 无法绕过规则

| 序号 | 任务 | 预计时间 |
|------|------|----------|
| #7 | 新增 Step 3.5 harness 级闸门脚本（exit code 拦截） | 2h |
| #9 | Step 0 增加 golden_three_plan.json 存在性检查 | 0.5h |
| #8 | 新项目冷启动风格样本 fallback | 1.5h |

### 第四阶段：工程加固（预计 6h）— 提升长期稳定性

| 序号 | 任务 | 预计时间 |
|------|------|----------|
| #12-18 | P2 级修复（元数据检测/Token裁剪通知/句长检查/检查点阻断等） | 4h |
| #20-21 | 关键路径测试补充 + 端到端 smoke test | 2h |

---

## 四、核心结论

**当前系统的架构设计是成熟的**——14 Agent 流水线、9 步分层、计算型闸门 + LLM 审查的混合检测、Override 债务系统、Strand Weave 节奏追踪，这些在同类工具中属于上乘设计。

**但执行层存在严重的"假阳性通过"问题**：计算型闸门的 SQL 全部对不上真实 Schema，所有检测静默返回"通过"，相当于安检机器通电了但传送带断了。mega-summary 只有检测逻辑没有生成逻辑，长篇记忆系统有框架但无内容。

**修复这些问题后**，系统具备产出高质量长篇网文的能力：
- 黄金三章有专项 checker + 硬拦截，机制正确
- 10 个 Checker 覆盖了从设定一致性到追读力的全维度
- Style RAG + 场景技法索引提供了真实的写作质量锚定
- 智能检查点确保长篇写作过程中持续自检自修

**一句话总结**: 设计 90 分，实现 60 分。第一阶段 4 小时的紧急修复可以让评分跳到 80 分。
