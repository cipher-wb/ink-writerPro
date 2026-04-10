# ink-writer v11.3.0 工程验证审查报告

**审查日期**: 2026-04-11
**审查方法**: 4 个专项验证 Agent 并行（闸门 SQL 验证 / 记忆系统验证 / 事务与数据一致性 / 端到端流水线）
**核心问题**: v11.3.0 的 22 项修复是否有效？是否引入新问题？系统能否产出高质量长篇网文？

**结论**: v11.3.0 修复了 v11.2.0 的全部 CRITICAL 级 SQL 断裂，**计算型闸门现在真正工作了**。但验证发现 4 个新问题（1 个 P0 + 2 个 P1 + 若干 P2），需要修复后才能进入稳定状态。

---

## 一、v11.3.0 修复验证结果

| 修复项 | 验证状态 | 说明 |
|--------|---------|------|
| SQL 列名/表名/值对齐 | **PASS** | 6 处 SQL 查询全部与真实 Schema 一致 |
| 死亡/离场状态扩展匹配 | **PASS** | 新增 5+4 个匹配值 |
| 对话「」引号支持 | **PASS** | 正则同时匹配 "" 和「」 |
| 句长/标点检查函数 | **PASS** | 实现合理，边界处理完善，severity=soft |
| 元数据全文扫描 | **PASS** | 从末尾 500 字改为全文，+5 个新 pattern |
| Token 预算裁剪通知 | **PASS** | budget_trim_warning section 正确注入 |
| chapters_per_volume 配置化 | **PARTIAL** | context_manager + memory_compressor 已改，init_project + chapter_paths 遗漏 |
| 伏笔同步 index.db | **PASS** | INSERT OR IGNORE 到 plot_thread_registry |
| _write_transaction 接入 | **PARTIAL** | 9 个核心方法已迁移，9 个次要方法遗漏 |
| Step3 Harness 闸门脚本 | **FAIL** | 脚本已创建但未被任何地方调用（死代码） |
| mega-summary 自动生成 | **FAIL** | SKILL.md 引用的 `save-mega` 子命令不存在 |
| golden_three_plan 检查 | **PASS** | Step 0.2 正确插入 |
| 风格样本 fallback | **PASS** | Step 2B fallback 逻辑完整 |
| data-agent 标准化枚举 | **PASS** | 8 个标准场景清晰约束 |
| reader-pull 始终执行 | **PARTIAL** | 路由规则文字改了，但伪代码模板仍用条件判断 |
| step-2c 错误分级 | **PASS** | WARNING + observability + 升级机制 |
| --sync-index | **PASS** | SQL 正确，busy_timeout 保护 |
| ink-auto 修复失败警告 | **PASS** | critical 持续检查逻辑正确 |
| polish-agent 计算辅助 | **PASS** | 描述完整 |

---

## 二、按优先级排列的新修改项

### P0 — CRITICAL

#### 1. `save-mega` CLI 子命令不存在，mega-summary 保存链路断裂

**文件**: `ink-writer/scripts/data_modules/ink.py`（memory 子命令定义）、`ink-writer/skills/ink-write/SKILL.md`（Step 0.3）

SKILL.md Step 0.3 引导执行：
```bash
python3 ink.py memory save-mega --volume {volume} --content "{mega_summary_text}"
```
但 `ink.py` 的 memory 子命令只注册了 `auto-compress`，没有 `save-mega`。`save_mega_summary()` 函数在 `memory_compressor.py` 中已实现且已被 import，但从未被路由调用。

虽然 SKILL.md 有 fallback（直接写文件），但 LLM 会优先尝试首选方案并在报错后可能困惑。

**修复方案**: 在 `ink.py` 的 `memory_sub` 中注册 `save-mega` 子命令，调用 `save_mega_summary()`。

---

### P1 — HIGH

#### 2. step3_harness_gate.py 是死代码，闸门逻辑无确定性兜底

**文件**: `ink-writer/scripts/step3_harness_gate.py`、`ink-writer/skills/ink-write/SKILL.md`

Grep 全项目搜索 `step3_harness_gate` 零匹配。SKILL.md 未引用它，ink-auto.sh 未调用它。黄金三章硬拦截、reader-simulator rewrite 判定等逻辑目前仅靠 SKILL.md 自然语言描述让 LLM 自行判断，没有确定性脚本兜底。

**修复方案**: 在 SKILL.md Step 3 审查聚合完成后，增加 harness 级复检调用：
```bash
python3 step3_harness_gate.py --project-root "$PROJECT_ROOT" --chapter {N}
# exit 1 → 回退 Step 2A
```

#### 3. `init_project.py` 和 `chapter_paths.py` 仍硬编码 chapters_per_volume=50

**文件**: `ink-writer/scripts/init_project.py:179,208,345`、`ink-writer/scripts/chapter_paths.py:26`

v11.3.0 将 context_manager 和 memory_compressor 的 `chapters_per_volume` 配置化了，但遗漏了这两个文件。如果项目 chapters_per_volume 非 50，初始化生成的大纲框架与运行时会不一致。

**修复方案**: 这两个文件的硬编码默认值改为读取 config 或环境变量 `INK_CHAPTERS_PER_VOLUME`。

#### 4. 9 个已迁移写方法存在双重 commit

**文件**: `ink-writer/scripts/data_modules/index_chapter_mixin.py`、`index_entity_mixin.py`、`index_reading_mixin.py`

`_get_conn(immediate=True)` 退出 try 块时自动 `conn.commit()`，但 9 个已迁移方法内部仍有显式 `conn.commit()` 调用。SQLite 对已提交事务再次 commit 是 no-op，功能不受影响，但属于代码异味。

**修复方案**: 删除 9 个方法内的显式 `conn.commit()`，统一由 `_get_conn` 自动 commit。

---

### P2 — MEDIUM

#### 5. 9 个次要写方法未迁移到 immediate=True

**文件**: `index_entity_mixin.py`（update_entity_current, archive_entity, register_alias, remove_alias, record_relationship_event）、`index_reading_mixin.py`（save_timeline_anchor, save_candidate_fact, save_review_metrics, save_writing_checklist_score）

这些方法仍使用 `_get_conn()` 而非 `_get_conn(immediate=True)`，在并发场景下存在 SQLITE_BUSY 风险。

**修复方案**: 将这 9 个方法的 `_get_conn()` 改为 `_get_conn(immediate=True)`。

#### 6. Step 2C 文档与代码不同步

**文件**: `step-2c-comp-gate.md`、SKILL.md

文档记录 6 项检查，实际代码执行 11 项（新增 sentence_length, emotion_punctuation, opening_pattern, dialogue_ratio, metadata_leakage）。LLM 在解读 soft_warnings 时缺乏上下文。

**修复方案**: 更新 step-2c-comp-gate.md 的检查项表格为 11 项。

#### 7. reader-pull-checker 伪代码模板仍用条件判断

**文件**: `step-3-review-gate.md:89`

路由规则文字写"始终启用"，但 Task 调用伪代码模板仍为 `if trigger_reader_pull: selected.append(...)`。权重表注释也写"条件"。LLM 执行时可能产生歧义。

**修复方案**: 伪代码模板改为无条件 append，权重表注释更新为"始终执行"。

#### 8. `_write_transaction` 方法应删除

**文件**: `index_manager.py:950-980`

`_write_transaction()` 与 `_get_conn(immediate=True)` 功能完全重叠，且无任何调用者。保留会导致维护混淆。

**修复方案**: 删除 `_write_transaction` 方法。

---

### P3 — LOW

#### 9. 测试 fixture `priority` 列类型不一致

**文件**: `test_computational_checks.py:63`

测试中 `plot_thread_registry.priority` 定义为 `TEXT`，真实 Schema 为 `INTEGER DEFAULT 50`。不影响功能但 fixture 注释声称匹配真实 Schema。

#### 10. SKILL.md Step 0.3 硬编码 `chapter > 50`

SKILL.md 写死"当 chapter > 50 时"触发压缩检查，应引用 config 的 `chapters_per_volume`。

---

## 三、总体评估更新

| 维度 | v11.2.0 | v11.3.0 | 变化 |
|------|---------|---------|------|
| 计算型闸门 | ★☆☆☆☆ | ★★★★☆ | SQL 全部对齐，11 项检查真正工作 |
| 记忆系统 | ★★☆☆☆ | ★★★☆☆ | 伏笔统一、config 化，但 mega-summary 保存链路断 |
| 黄金三章 | ★★★★☆ | ★★★★☆ | 契约检查加入，但 harness 闸门是死代码 |
| 长篇稳定性 | ★★☆☆☆ | ★★★☆☆ | 写事务保护 + 并发改善，但双重 commit + 遗漏方法 |
| 测试覆盖 | ★★★★☆ | ★★★★☆ | 1083 测试全通过，+29 新测试 |
| 风格一致性 | ★★★☆☆ | ★★★★☆ | 风格 fallback + 句长/标点检查填补了冷启动空白 |

**一句话**: v11.3.0 让闸门从"全部失效"变为"真正工作"，是巨大进步。剩余 10 项修改预计 3 小时可完成，完成后系统可进入生产就绪状态。
