# PRD: v18 Audit Fix — 收口 v17 审查 9 条 Red

> **基线版本**：v16.0.0（2026-04-18 发布，HEAD `e3b0c82`）
> **审查来源**：`reports/audit-v17-findings.md`（总分 71.1/100，Red 9 / Yellow 12 / Green 8）
> **本 PRD 作用域**：**仅修复 9 条 Red**，Yellow 归入 Open Questions 留 v19 讨论，Green 作为"不倒退"约束
> **工作量估算**：14 US / 16 sessions（13 US 修复 + 1 US 集成回归 + 2 session 缓冲）
> **目标升分**：71 → ≥80（合格线），过审概率区间 [75%, 85%] → ≥ [85%, 95%]

---

## 1. Introduction

v17 审查通过 22 个对比维度 + 7 因子过审概率公式，给 ink-writerPro v16.0.0 打了 71.1 分（不合格但无偏科）。9 条 Red 集中在 4 个主题：

1. **编辑规则召回覆盖率硬瓶颈**（R001、R006）—— 每章只激活 388 条 KB 的 3.9%
2. **800 章长记忆性能**（R002、R004）—— O(n) DB 扫描 + Python 侧切片
3. **并发写一致性 & Validator 真调用**（R003、R005、R007）—— v15 遗留未收口
4. **checker 仲裁 & AI 味检测扩展**（R008、R009）

本 PRD 把 9 条 Red 拆为 14 个 User Stories，严格遵守业主已有的 `PRD → /ralph → ralph.sh` 三段式工作流，零回归硬约束（参照 `memory/feedback_no_regression.md` 和 v15→v16 零回归实践）。

---

## 2. Goals

- G1：把总分从 **71.1 提升到 ≥80**，通过补齐 D2（业务目标）和 D1（工程架构）两大短板
- G2：把起点过审概率区间从 **[75%, 85%] 提升到 ≥ [85%, 95%]**（业主期望 ≥90%）
- G3：让 `parallel>1` 真正可用，解锁业主日产 3-5 万字能力（当前 1-2 万字天花板）
- G4：确保 800-1000 章场景下 `drift_detector` + `progression/context_injection` 响应时间 <3s（当前 15-30s）
- G5：**零回归**——8 条 Green 亮点全部作为"不倒退"硬约束保留，任一 US 提交前必须 typecheck + pytest 对比 baseline 2420 无新增失败
- G6：v15 遗留的 3 条 F-00x（F-003 ChapterLockManager / F-007 Validator 调用 / F-008 ZT 扩展）在 v18 彻底收口

---

## 3. User Stories

### US-001: 提升 editor-wisdom retrieval_top_k 到 15-20
**Description**: As 业主，I want 每章编辑规则注入数量从 15 条提到 45-60 条，so that 过审概率从 [75%, 85%] 突破到 ≥ [85%, 95%]。

**Acceptance Criteria**:
- [ ] `config/editor-wisdom.yaml:3` `retrieval_top_k` 从 `5` 改为 `15`（或 20，评估 prompt 膨胀后定）
- [ ] 对比 A/B：top_k=5 vs 15 在 20 章样本上 writer-prompt token 膨胀 ≤30%
- [ ] 过审概率 f₂ 因子从 4 分提升到 ≥7 分（按 v17 提示词 §8.3 公式自验）
- [ ] 不破坏 prompt cache 命中率（测试 `ink_writer/prompt_cache/metrics.py`）
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-002: editor-wisdom 分类别召回（黄金三章 opening/taboo/hook 各 ≥3 条）
**Description**: As 业主，I want 黄金三章时每个关键类别（opening/taboo/hook）强制至少注入 3 条规则，so that 前 3 章过审概率独立达 ≥90%。

**Acceptance Criteria**:
- [ ] `ink_writer/editor_wisdom/writer_injection.py:76-85` 新增分类别召回逻辑
- [ ] 章 1-3 时 opening 类 ≥3 条、taboo 类 ≥3 条、hook 类 ≥3 条
- [ ] 新增 `ink_writer/editor_wisdom/coverage_metrics.py` 每章统计覆盖率写 `.ink/editor-wisdom-coverage.json`
- [ ] 测试 `tests/editor_wisdom/test_coverage_floor.py` 覆盖率 <10%/章 即 fail
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-003: drift_detector 改用单条 IN 查询 + GROUP BY
**Description**: As 业主，I want `drift_detector.py` 把 800 次 SQL 合并为单条查询，so that 第 1000 章跨卷审计 15-30s → <3s。

**Acceptance Criteria**:
- [ ] `ink_writer/propagation/drift_detector.py:172-194` 改用 `WHERE start_chapter <= ? AND end_chapter >= ?` 的 IN 查询 + GROUP BY
- [ ] 加 `max_chapters_per_scan` 参数（默认 50），超过则分批
- [ ] `_drifts_from_data` 对 `critical_issues` 加 `limit=20` 早停
- [ ] 测试 `tests/propagation/test_detect_drifts_scale.py` 1000 章 fixture 执行 <3s
- [ ] 旧 O(n) 路径保留作为 `legacy=True` 参数，默认关闭但不删（零回归）
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-004: drift_detector 增量 debt 持久化（.ink/drift_debts.db）
**Description**: As 业主，I want drift_detector 把 debt 增量持久化到 SQLite，so that 第 2 次扫描不用重跑第 1 次扫过的章节。

**Acceptance Criteria**:
- [ ] 新建 `.ink/drift_debts.db` schema：`CREATE TABLE drift_debts (chapter_id TEXT, debt_type TEXT, payload JSON, last_seen INTEGER, PRIMARY KEY(chapter_id, debt_type))`
- [ ] `drift_detector.py` 增量扫描：只扫 `chapter_id > last_seen_max` 的章节
- [ ] 手动 invalidate 命令：`python -m ink_writer.propagation.drift_detector --reset`
- [ ] 测试：800 章全扫一次 + 增量扫第 801 章，总时间 <5s
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-005: PipelineManager 接入 ChapterLockManager（v15 F-003 真收口）
**Description**: As 业主，I want `parallel>1` 下写 index.db / state.json 不丢数据，so that 并发写 3-5 章/轮解锁日产 3-5 万字。

**Acceptance Criteria**:
- [ ] `ink_writer/parallel/pipeline_manager.__init__` 实例化 `ChapterLockManager(state_dir, ttl=300)`
- [ ] Step 5 data-agent 写 SQL 前 `with lock.state_update_lock()` 包裹
- [ ] 章节级任务启动前 `lock.chapter_lock(chapter_id)` 独占
- [ ] `ink-writer/skills/ink-auto/SKILL.md:40` 的"⚠️ 当前仅 parallel=1 安全"声明改为"parallel≤4 已接 ChapterLockManager 验证安全"
- [ ] 测试 `tests/parallel/test_chapter_lock_integration.py`：4 并发 subprocess 写 index.db 验证无 lost update
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-006: chapter_lock.py threading.local() 改 asyncio.Lock
**Description**: As 业主，I want `chapter_lock.py` 支持 asyncio 场景，so that 未来异步 writer-agent 接入不用二次改造。

**Acceptance Criteria**:
- [ ] `ink_writer/parallel/chapter_lock.py:49-54` `threading.local()` 改 `asyncio.Lock`（或 hybrid：同步路径保留，异步路径新增）
- [ ] 兼容现有同步调用路径（US-005 的集成测试必须仍 passing）
- [ ] 新增 async 测试 `tests/parallel/test_chapter_lock_async.py`：10 个 asyncio task 并发持锁
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-007: progression/context_injection SQL LIMIT 下推
**Description**: As 业主，I want `progression/context_injection.py` 从 8 万行全量加载改为 SQL LIMIT 下推，so that 500+ 章 Python 侧 O(n²) 切片消失。

**Acceptance Criteria**:
- [ ] `ink_writer/progression/context_injection.py:58-65` 切片改为 SQL 下推：`WHERE char_id=? AND chapter_no<? ORDER BY chapter_no DESC LIMIT ?`
- [ ] 建索引 `CREATE INDEX idx_char_chapter ON character_evolution_ledger(char_id, chapter_no)`
- [ ] `_ProgressionSource` protocol 加 `get_recent_progressions_for_character(char_id, before, limit)` 方法
- [ ] 测试：mock 1 万 progression 下 `build_progression_summary` <100ms
- [ ] 保留 `max_rows_per_char=5` 默认值（Green G006 不倒退约束）
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-008: reflection agent 消费链路显式 wire
**Description**: As 业主，I want reflection agent 50 章一次的 CPU 成本真的被 writer-agent 消费，so that 长程语义涌现不丢。

**Acceptance Criteria**:
- [ ] `ink_writer/core/context/context_manager.py:590` `_build_pack` 显式调 `_load_reflections(project_root)`
- [ ] `context_weights.py` 给 `reflections` 最小权重 `0.05`
- [ ] 测试 `tests/reflection/test_reflection_consumption.py` 端到端验证 writer-agent prompt 含 reflection bullets
- [ ] 测试：若 `.ink/reflections.json` 为空，prompt 装配不 crash
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-009: editor-wisdom checker 解除 5000 字硬截断
**Description**: As 业主，I want `editor-wisdom-checker` 看到 4000+ 字章节的完整结尾（含章末钩子），so that 钩子违规能被检出。

**Acceptance Criteria**:
- [ ] `ink_writer/editor_wisdom/checker.py:28` `_build_user_prompt` 加参数 `max_chars=7500`
- [ ] `ink_writer/editor_wisdom/checker.py:39` 超限时分段：头部 3500 字 + 尾部 3500 字（保留章末钩子）
- [ ] 测试：4500 字章节断言 checker 看到尾段钩子（构造含"欲知后事"的结尾）
- [ ] 测试：8000 字章节断言分段不丢头尾关键信息
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-010: creativity validator 真接入 ink-init Quick Mode（v15 F-007 真收口）
**Description**: As 业主，I want ink-init Quick Mode 每次重抽书名/设定后调用 creativity validator，so that 反俗套承诺从 LLM 自律升级为 Python 硬校验。

**Acceptance Criteria**:
- [ ] `ink-writer/skills/ink-init/SKILL.md` Quick Mode 每次重抽后加 bash 调用：`python -m ink_writer.creativity.cli validate --book-title "..." --strict`
- [ ] validator exit code ≠ 0 → 触发降档重抽（2 次重抽失败后让用户手动选）
- [ ] 测试 `tests/creativity/test_quick_mode_integration.py` 模拟黑名单命中 → validator 真 fail
- [ ] Green G004 不倒退：`creativity/{name_validator,gf_validator,sensitive_lexicon_validator}.py` 三文件保留
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-011: arbitration 扩展到章 ≥4 的 generic 仲裁路径
**Description**: As 业主，I want 第 4 章起 prose-impact/sensory-immersion/flow-naturalness 三重叠 checker 冲突能被合并，so that polish-agent prompt 不膨胀 15-25%、300 章以上 API 成本不被炸。

**Acceptance Criteria**:
- [ ] `ink_writer/editor_wisdom/arbitration.py` 新增 `arbitrate_generic(chapter_id, issues)` 路径
- [ ] 章 ≥4 时按 `symptom_key`（正则/关键词规范化）去重合并
- [ ] `references/checker-merge-matrix.md` 加重叠 checker 合并规则条目
- [ ] `ink_writer/parallel/pipeline_manager.py` review step 调 `arbitrate_generic`
- [ ] 测试：章 50 同时 3 个重叠 checker 产出 issues → 合并为单 `fix_prompt`
- [ ] 黄金三章原路径（`arbitrate` P0-P4）保留不动（Green G003 不倒退约束）
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-012: arbitration 合并矩阵配置化 + 集成 pipeline
**Description**: As 业主，I want 合并规则从硬编码改为配置化，so that 新增 checker 只需加 matrix 条目不用改代码。

**Acceptance Criteria**:
- [ ] `config/arbitration.yaml` 新建，定义 `symptom_key_groups`（e.g. `flow_issue: [prose-impact, flow-naturalness, sensory-immersion]`）
- [ ] `arbitrate_generic` 读取 yaml，避免硬编码 checker 列表
- [ ] `tests/editor_wisdom/test_arbitration_matrix.py`：加新 checker 条目后无需改 Python 代码即可合并
- [ ] Green G003（不合并/删减 16 checker）约束写入 arbitration.yaml 顶部注释
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-013: anti_detection ZT 规则扩展到 8-10 条（v15 F-008 真收口）
**Description**: As 业主，I want 零容忍（ZT）AI 味规则从 2 条扩到 8-10 条，so that 起点编辑打回的"尽管如此/不仅……而且/与此同时"等连接词密集现象被拦截。

**Acceptance Criteria**:
- [ ] `ink_writer/anti_detection/config.py` 扩 ZT 正则到 8-10 条（包含连接词密集、长句滥用、转折堆叠等模式）
- [ ] `ink_writer/anti_detection/sentence_diversity.py` 加 `conjunction_density_max` 指标
- [ ] 用 117 本起点标杆（参照 `memory/project_quality_upgrade.md`）做 baseline 校准阈值
- [ ] 测试 `tests/anti_detection/test_zt_extended.py` 每条 ZT 给 positive（应拦截）+ negative（误伤样本）共 20+ case
- [ ] 参照 `memory/feedback_writing_quality.md`：禁止"第 xx 日"时间标记开头已实装，本 US 不影响（零回归）
- [ ] Typecheck passes / pytest --no-cov 零回归

### US-014: v18 集成回归 + v18.0.0 发版
**Description**: As 业主，I want v18 9 条 Red 修完后做一轮完整回归测试，so that 确认 Green 8 条亮点零倒退、baseline 2420 无新增失败、总分 ≥80。

**Acceptance Criteria**:
- [ ] 跑 `pytest --no-cov` 全量，通过数 ≥ 2420 + US-001~013 新增测试（估 20-30 个新 test）
- [ ] 手动跑 `ink-auto 10` 写 10 章，对比 v16 baseline 无新增 checker fail
- [ ] 按 v17 提示词 §8.3 重新计算过审概率 S 值，f₂ ≥7 分、f₅ ≥8 分、其他因子不倒退
- [ ] 按 v17 提示词 §5 重新打四维分，总分 ≥80 且所有维度 ≥5
- [ ] 生成 `reports/audit-v18-pass-report.md` 或 `reports/audit-v18-findings.md`（若仍不合格则追加 v19 PRD）
- [ ] 更新 `ink-writer/.claude-plugin/plugin.json` version → `18.0.0`
- [ ] 合并 `ralph/v18-audit-fix` → `master`，git tag `v18.0.0`
- [ ] 更新 `README.md` version badge + 主要改动摘要
- [ ] 归档 `archive/2026-XX-XX-v18-audit-fix/` 保留本轮 `prd.json` + `progress.txt`

---

## 4. Functional Requirements

- **FR-1**：`config/editor-wisdom.yaml` `retrieval_top_k` 默认值 ≥15；A/B 验证 token 膨胀 ≤30%
- **FR-2**：editor-wisdom 黄金三章（章 1-3）对 opening/taboo/hook 三类别强制分类别召回，各 ≥3 条
- **FR-3**：新增 `coverage_metrics` 模块每章写 `.ink/editor-wisdom-coverage.json`
- **FR-4**：`drift_detector` 单条 IN 查询 + GROUP BY；默认 `max_chapters_per_scan=50`；`legacy=True` 参数保留旧路径作为降级开关
- **FR-5**：`drift_detector` 增量持久化到 `.ink/drift_debts.db`，支持 `--reset` 清理
- **FR-6**：`PipelineManager` 所有写 index.db/state.json 操作由 `ChapterLockManager` 包裹，`parallel≤4` 安全
- **FR-7**：`chapter_lock.py` 支持 sync + async 双路径，默认 sync 路径行为不变
- **FR-8**：`progression/context_injection` 必须用 SQL 下推，保留 `max_rows_per_char=5` 默认值
- **FR-9**：`context_manager._build_pack` 必须调 `_load_reflections`；`reflections` 在 context_weights 中权重 ≥0.05
- **FR-10**：`editor_wisdom/checker.py` 长章节分段（头 3500 + 尾 3500），绝不丢章末
- **FR-11**：`ink-init` Quick Mode 每次生成书名/金手指/设定后 bash 调用 `creativity.cli validate --strict`
- **FR-12**：`arbitration.py` 提供 `arbitrate_generic`（章 ≥4）+ `arbitrate`（章 1-3）双路径；合并矩阵由 `config/arbitration.yaml` 驱动
- **FR-13**：`anti_detection/config.py` ZT 规则数 ≥8；`sentence_diversity.py` 新增 `conjunction_density_max`
- **FR-14**：v18 发版前必须跑全量回归，baseline 2420 无新增失败；四维分 ≥80；过审概率区间 ≥ [85%, 95%]
- **FR-15**：全程遵守 `memory/feedback_no_regression.md` 零回归原则 —— 任何 US 提交不得删除或降级已有功能

---

## 5. Non-Goals（零倒退硬约束，对应 8 条 Green 亮点）

> 以下 8 条是 v16 审查验证的"已达成"能力，v18 期间**禁止退化**。每条由审查报告 §6 的 Green 条目直接转化为硬约束。

- **NG-1（对应 G001）**：**CLAUDE.md 不得超过 50 行**，超过需 ADR 论证（当前 13 行极简典范）
- **NG-2（对应 G002）**：**不得退化为单层检索**；`semantic_recall/{retriever,bm25,chapter_index}.py` + RRF fusion 必须保留且在主路径被调用
- **NG-3（对应 G003）**：**不得合并或删减 16 checker**（`ink-writer/agents/*.md` 中的 checker 规格文件）；US-011/012 的 arbitrate_generic 只是**合并运行时输出**，不是**合并 checker 本身**
- **NG-4（对应 G004）**：**`creativity/` 下 3 个 validator 不得删除**；US-010 修复必须保证 validator 真被 SKILL.md 调用
- **NG-5（对应 G005）**：**review_gate 不得回退到单阈值 + 3-retry-hard-block 老路径**；dual-threshold + escape_hatch 保留
- **NG-6（对应 G006）**：**`progression/context_injection` `max_rows_per_char=5` 默认值不动或加大到 >10**（US-007 必须保留此参数）
- **NG-7（对应 G007）**：**snapshot 写入不得绕过 FileLock**；US-005 的 ChapterLockManager 与现有 FileLock 共存，不替换
- **NG-8（对应 G008）**：**继续按 `PRD → /ralph → ralph.sh` 三段式工作流**；不得越权自动改 `ralph/prd.json` 或跳过 PRD 直接写代码

**其他 Non-Goals**：
- 不做 dashboard / UI 可视化（留给 v19，对应 Y001）
- 不做 model 分层选型（留给 v19，对应 Y002）
- 不做 batch API 接入（100 章以内收益小，对应 Y003）
- 不涉及 LLM 路径的 reflection agent 改造（对应 Y011）
- 不做第三方依赖安全性审查（独立 `/security-review` 流程）

---

## 6. Design Considerations

- **US 依赖顺序**：US-001 → US-002 → US-003 → US-004 → US-005 → US-006 → US-007 → US-008 → US-009 → US-010 → US-011 → US-012 → US-013 → US-014
  - US-005 在 US-006 前：先让同步路径可用再改异步
  - US-011 在 US-012 前：先让逻辑跑通再抽配置
  - US-014 必须最后：做全量回归和发版
- **分支策略**：`ralph/v18-audit-fix`（对应 `ralph/prd.json` 的 `branchName`）
- **评分自验证**：每个 US 提交后，审查者（人或 AI）可跑 `python -m ink_writer.editor_wisdom.coverage_metrics` 查看 f₂ 因子升降；US-014 做完整 v17 提示词 §5 四维重评

---

## 7. Technical Considerations

- **零回归门禁**：每 US 提交前跑 `pytest --no-cov`，passed 数对比 v16 baseline 2420，`new_failures=0`
- **对接 Ralph**：生成 PRD 后 `/ralph tasks/prd-v18-audit-fix.md` → `ralph/prd.json`；`ralph.sh` 自治 14 iteration
- **HEAD sha 锚定**：Ralph 第一次 iteration 必须从 `master`（基线 v16.0.0）切出 `ralph/v18-audit-fix`
- **Green 约束强制化**：`NG-1`~`NG-8` 写入 `ralph/CLAUDE.md` 头部，Ralph 每轮开始前 Read 一次，避免无意倒退
- **测试覆盖**：每条 Red 必须有新增测试（`tests/editor_wisdom/`、`tests/propagation/`、`tests/parallel/`、`tests/progression/`、`tests/reflection/`、`tests/creativity/`、`tests/anti_detection/` 7 个子目录），估 20-30 个新 test
- **Python 3.12+ 兼容**：US-006 的 asyncio.Lock 需验证 3.12 API 稳定性
- **token 预算**：US-001 top_k 提升后 writer-agent prompt 膨胀 ≤30%，`prompt_cache/metrics.py` 命中率不得降 ≥10%

---

## 8. Success Metrics

- **SM-1**：v17 提示词 §5 四维重评，总分 ≥80（当前 71.1，升 ≥9 分）
- **SM-2**：D2 业务目标均分 ≥7.5（当前 6.83，升 ≥0.67）
- **SM-3**：v17 提示词 §8.3 过审概率 S 值 ≥8.5（当前 8.05），区间 P_low ≥ 85%
- **SM-4**：800 章 fixture 下 `drift_detector` 扫描 <3s（当前 15-30s）
- **SM-5**：1 万 progression fixture 下 `build_progression_summary` <100ms
- **SM-6**：`parallel=4` 4 并发 subprocess 写 index.db 零 lost update（当前 `parallel>1` silent corruption）
- **SM-7**：`editor-wisdom-coverage` 平均 ≥20%/章（当前 3.9%/章）
- **SM-8**：pytest 全量 passed ≥ 2440（baseline 2420 + 新 test），new_failure=0
- **SM-9**：8 条 Green NG-1~8 零倒退（v18.0.0 发版前最终核验）
- **SM-10**：日产字数从 1-2 万字（parallel=1 天花板）提升到 3-5 万字（parallel=4 解锁后）

---

## 9. Open Questions（从 v17 Yellow 12 条转化，留 v19 讨论）

> 这些是 v17 审查判定为"暗礁"但非必修的 Yellow 项，放在 Open Questions 等 v18 完成后根据业主实际使用感受再决定是否 v19 处理。

- **OQ-1（Y001）prompt cache 命中率无 dashboard 暴露**：业主看不到每章 cache 命中率，token 成本可能高 30-50%。依赖：`ink_writer/prompt_cache/metrics.py` + `ink-dashboard`。优先级低于核心修复，可推迟到 v19。
- **OQ-2（Y002）model 选型未做 task→model 分层**：writer/polish 应 Opus、classify/extract 应 Haiku。需配合 API 用量统计，先做 OQ-1 再评估。
- **OQ-3（Y003）batch API 未用于 ≥10 章的并发 review**：错失 50% 折扣 + 24h SLA。30 章以内意义小，业主 100 章后再评估。
- **OQ-4（Y004）ooc-checker Layer-5 依赖 review_bundle 外部投喂**：context-agent 漏注 `knowledge_gaps` 时规则失效。与 US-010（R007）ink-init 改造绑定评估。
- **OQ-5（Y005）memory_compressor L2 手工 CLI 而非自动**：业主忘触发时第 2 卷开头爆 token 预算。SKILL.md 自动化可与 US-010 合并。
- **OQ-6（Y006）snapshot version mismatch 无迁移层**：v16→v17 未发生，暂不影响；v17 版本 bump 前再评估。
- **OQ-7（Y007）BM25 Python 原生实现 800+ 章 build 慢**：首次加载 2-3s。收益在 500+ 章显著，400 章前可不做。
- **OQ-8（Y008）snapshot_manager try/except 路径兜底 security_utils**：pip install -e 方式装包时 import 失败。可与 US-005（R003）的工程迁移合并，若未合并则 v19 处理。
- **OQ-9（Y009）query_router 无 fallback 路径**：retriever 失败时无降级回退。低频失败场景，优先级低。
- **OQ-10（Y010）rule_sources 新增 md 未进入 retriever 索引**：24 条 prose_craft 规则可能未被检索命中。与 US-001（R001）的 top_k 提升合并：若 US-001 的测试验证 prose_craft 召回命中，OQ-10 自动消除。
- **OQ-11（Y011）reflection_agent 仅启发式，LLM 路径未 wire**：启发式 reflection 不如 LLM 能看出涌现现象。涉及 LLM API 成本，业主决策。
- **OQ-12（Y012）pytest tests/editor_wisdom 未实跑核实**：f5 打分按"假设已修"给 10 分，未经真实核实。v18 CI 必须强制 `pytest tests/editor_wisdom --tb=line`，建议并入 US-014 验收清单。

---

## Appendix A：v17 审查 Red/Yellow/Green ↔ 本 PRD 映射

| v17 ID | 主题 | 本 PRD US | estimated_us |
|---|---|---|---|
| AUDIT-V17-R001 | top_k=5 覆盖率硬瓶颈 | US-001, US-002 | 2 |
| AUDIT-V17-R002 | drift_detector 800 章扫描 O(n) | US-003, US-004 | 2 |
| AUDIT-V17-R003 | PipelineManager 未接 ChapterLockManager | US-005, US-006 | 2 |
| AUDIT-V17-R004 | progression/context_injection 无 SQL LIMIT | US-007 | 1 |
| AUDIT-V17-R005 | reflection agent 消费链路依赖外部 path | US-008 | 1 |
| AUDIT-V17-R006 | checker.py 5000 字硬截断 | US-009 | 1 |
| AUDIT-V17-R007 | creativity validator 未在 ink-init 被调用 | US-010 | 1 |
| AUDIT-V17-R008 | arbitration 只覆盖章 1-3 | US-011, US-012 | 2 |
| AUDIT-V17-R009 | anti_detection ZT 仅 2 条 | US-013 | 1 |
| — | v18 集成回归 + 发版 | US-014 | 1 |
| **合计** | — | **14 US** | **14** |

| v17 Green ID | 标题 | 本 PRD Non-Goal |
|---|---|---|
| AUDIT-V17-G001 | CLAUDE.md 13 行极简典范 | NG-1 |
| AUDIT-V17-G002 | semantic_recall hybrid RRF fusion | NG-2 |
| AUDIT-V17-G003 | 22 agent writer-review-polish-arbitrate 循环 | NG-3 |
| AUDIT-V17-G004 | creativity 三 validator 真修复 | NG-4 |
| AUDIT-V17-G005 | review_gate dual-threshold + escape_hatch | NG-5 |
| AUDIT-V17-G006 | progression/context_injection 5 行/角色窗口 | NG-6 |
| AUDIT-V17-G007 | snapshot FileLock 并发安全 | NG-7 |
| AUDIT-V17-G008 | v15→v16 零回归（27 US 全过） | NG-8 |

---

**Checklist（本 PRD 自查）**：
- [x] 9 条 Red 100% 覆盖（US-001~013 逐条对应）
- [x] 14 US 粒度（每 US 1 session，US-001/003/005/011 稍重但仍 ≤4h）
- [x] 12 Yellow 全部进入 Open Questions（OQ-1~12 一一对应）
- [x] 8 Green 全部转化为 Non-Goals 硬约束（NG-1~8 一一对应）
- [x] 零回归原则显式写入（FR-15 + 每 US AC 末尾）
- [x] 对接 `PRD → /ralph → ralph.sh` 工作流（Design Considerations 分支名 + Technical Considerations Green 约束注入 CLAUDE.md）
- [x] 保存路径：`tasks/prd-v18-audit-fix.md`
