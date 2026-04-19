# PRD: v15 审计完结 → v16.0.0

> **来源**：[`reports/audit-v15-findings.md`](../reports/audit-v15-findings.md)（21 条 F-XXX）+ 用户澄清补充（X1 文档矛盾、X2 AI 审读员）
> **生成日期**：2026-04-18
> **用户选项**：1C（Ralph 按 priority 自治）/ 2C（shadow 先→真 LLM 后）/ 3A（零回归门禁保留）/ 4C（分两版 v15.9→v16.0）/ 5C（creativity 完整版）
> **硬约束**：每个 US 完成后必须 `pytest --no-cov` 全量对比 baseline 2420 passed 零新增失败

---

## 1. Introduction / Overview

本 PRD 收口 ink-writerPro v15.0.0 审计发现的全部问题，分三个 Milestone 推进到 v16.0.0：
- **Milestone A（止血）**：3 个 P0 + 2 个 P1，消除 step3_runner stub / ChapterLockManager 虚假声明 / FIX-11 残留 / 文档自相矛盾
- **Milestone B（补能力）**：创意 validator 子系统（对标 editor_wisdom）+ 反 AI 味升级 + 300 章压测（shadow→真 LLM）+ AI 审读员
- **Milestone C（工程卫生）**：Skill/SDK/NovelCrafter 对标差距 + 日志/循环依赖/孤儿清理

完成后项目从"规格漂亮但有断层"进入"规格-代码一致 + 实证指标齐全"。**明确声明：本 PRD 不保证"完美无缺陷"**——仅闭环 v5+v15 两轮审计发现，压测过程会产生新 Finding，留给下一轮迭代。

---

## 2. Goals

- **G1**：step3_runner 的 5 个 Python gate 从 stub 升级到生产真阻断（F-001）
- **G2**：文档-代码一致率 100%（verify_docs.py CI 守卫）
- **G3**：`/ink-auto --parallel 4` 真并发且数据安全（ChapterLockManager 接入）
- **G4**：反俗套从"词库齐、发力没"升级到"Python validator 硬拦截"
- **G5**：300 章端到端性能+质量指标实证（Q1-Q8 + AI 审读员 + 3 个关键章节人工抽读）
- **G6**：每 5/10/20/50/200 章分层检查点文档与实装对齐
- **G7**：Claude Code Skill 规范评分 27/30 → 30/30
- **G8**：v15.9.0（Milestone A+B）可发布，v16.0.0（含 C）为正式大版本

---

## 3. User Stories

每个 US 的 acceptance criteria 末尾都含：
- [ ] `typecheck/lint` 通过（ruff + mypy 若配置）
- [ ] **零回归**：`pytest --no-cov` 全量通过（baseline ≥2420 passed，新增失败 = 0）

---

### Milestone A：止血（US-001 ~ US-008，v15.9.0 预发布候选）

---

### US-001: SKILL.md ChapterLockManager 虚假声明清除 + verify_docs.py 守卫

**Description**：As a 业主，I want `skills/ink-auto/SKILL.md:40` 的虚假"保护"声明与代码真实状态一致 so that 其它 AI/用户读 SKILL.md 不会误判安全。

**映射**：F-002（P0，D5+D7）
**预估**：0.3d
**依赖**：无

**Acceptance Criteria**：
- [ ] 修改 `ink-writer/skills/ink-auto/SKILL.md:40`，删除/替换为"⚠️ 当前仅 parallel=1 安全，parallel>1 未接 ChapterLockManager 会触发 RuntimeWarning"
- [ ] 全仓 `grep "ChapterLockManager 保护"` 无假声明命中（除 pipeline_manager.py 的"尚未接入"声明外）
- [ ] `scripts/verify_docs.py` 新增一条 rule：任何 SKILL.md 出现"ChapterLockManager 保护|parallel>1 安全"必须在 pipeline_manager.py:10-17 诚实降级段同步存在，不一致 CI fail
- [ ] `tests/docs/test_verify_docs_chapterlock.py` 构造 SKILL.md 含错误声明，expect verify_docs.py exit != 0
- [ ] 典型的 typecheck/零回归

---

### US-002: ChapterLockManager 接入 PipelineManager（并发根治）

**Description**：As a 业主，I want `/ink-auto --parallel 4` 真并发且 state.json/index.db 不损坏 so that 批量写作能加速 2-3x。

**映射**：F-003（P0，D5）
**预估**：2d
**依赖**：US-001

**Acceptance Criteria**：
- [ ] `ink_writer/parallel/pipeline_manager.py.__init__` 实例化 `ChapterLockManager(state_dir, ttl=300)`
- [ ] 章节任务启动前 `async with lock.chapter_lock(chapter_id)` 独占
- [ ] Step 5 data-agent 写 SQL 前 `async with lock.state_update_lock()` 包裹
- [ ] `ink_writer/parallel/chapter_lock.py:49-54` 从 `threading.local()` 改为 `asyncio.Lock`（保留 file-lock 兜底）
- [ ] 删除 `pipeline_manager.py:149-159` 的 RuntimeWarning，改写为"parallel>1 已接入锁，仍建议 ≤4"
- [ ] 删除 `pipeline_manager.py:10-17` 的"尚未接入"docstring
- [ ] `README.md:166` FAQ 改写
- [ ] 新增 `tests/parallel/test_concurrent_state_write.py`：4 个 asyncio task 并发写同一 state.json + index.db，验证数据完整无 lost update
- [ ] 基准测试：串行 10 章 wall_time vs parallel=4 10 章 wall_time，记录到 `reports/perf-parallel-v15.md`
- [ ] 典型的 typecheck/零回归

---

### US-003: step3_runner 5 个 Gate checker_fn 接真 LLM（Phase B 主干）

**Description**：As a 业主，I want step3_runner 的 5 个 Python gate（reader_pull/emotion/anti_detection/voice/plotline）真正检查章节而非恒返回 score=1.0 so that "硬门禁"不是空壳。

**映射**：F-001 主体（P0，D1+D6）
**预估**：3d
**依赖**：US-001

**Acceptance Criteria**：
- [ ] 新建 `ink_writer/checker_pipeline/llm_checker_factory.py`：构造 `make_llm_checker(gate_name, system_prompt_path) -> callable`，内部调用 `ink_writer.core.infra.api_client.call_claude(model="claude-haiku-4-5")`
- [ ] 改写 `step3_runner.py:104-215` 的 5 个 `_stub_checker`，替换为 `make_llm_checker("hook", ".../prompts/hook_checker.md")` 等真调用
- [ ] 5 个 gate 的 system prompt 从对应 agent spec（`ink-writer/agents/reader-pull-checker.md` 等）抽取精简版（约 500 字），放入 `ink_writer/checker_pipeline/prompts/`
- [ ] 每个 checker 返回 `{"score": float, "violations": [...], "passed": bool}` 严格 schema
- [ ] 新增 `tests/checker_pipeline/test_llm_checker_factory.py`：mock API 返回多种 score，验证 schema 解析
- [ ] 新增 `tests/checker_pipeline/test_step3_runner_real_checker.py`：构造违规章节文本（含时间标记开头 / OOC 明显），verify 5 个 gate 至少 2 个返回 passed=False
- [ ] 典型的 typecheck/零回归

---

### US-004: step3_runner polish_fn 接真 polish-agent

**Description**：As a 业主，I want 违规时真调 polish agent 修复而非返回原文 so that retry 循环有意义。

**映射**：F-001 延伸（P0，D1）
**预估**：1.5d
**依赖**：US-003

**Acceptance Criteria**：
- [ ] 新建 `ink_writer/checker_pipeline/polish_llm_fn.py`：构造 `make_llm_polish(gate_name) -> callable`，用 claude-sonnet-4-6 模型（品质优先）+ polish-agent.md 的 system prompt
- [ ] 替换 `step3_runner.py` 中 5 个 `_stub_polish`
- [ ] 支持超时控制（默认 120s）+ 降级（超时返回原文 + 记日志）
- [ ] 每次 polish 写入 `.ink/reports/polish_ch{N}_gate_{name}.md` 审计日志
- [ ] 新增 `tests/checker_pipeline/test_polish_llm_fn.py`：mock API，验证超时降级、schema
- [ ] 新增 `tests/integration/test_step3_enforce_real_polish.py`：enforce 模式 + 违规章节 → 预期触发 polish → 重查通过
- [ ] 典型的 typecheck/零回归

---

### US-005: step3_runner enforce 模式 E2E 真阻断集成测试 + 默认切换

**Description**：As a 业主，I want `INK_STEP3_RUNNER_MODE` 默认 enforce 且真能阻断劣质章节 so that shadow 模式统计期结束后就进入生产防线。

**映射**：F-001 收尾（P0，D1）
**预估**：1d
**依赖**：US-004

**Acceptance Criteria**：
- [ ] `step3_runner.py` 默认 `DEFAULT_MODE = MODE_ENFORCE`（替换原 shadow）
- [ ] `skills/ink-write/SKILL.md` Step 3.45 文案更新：不再写"shadow 默认"
- [ ] 新增 `tests/integration/test_step3_enforce_hard_fail_blocks.py`：构造 anti-detection 零容忍章节（"次日清晨，天刚蒙蒙亮……"开头），enforce 模式预期 exit code=1
- [ ] 新增 `tests/integration/test_step3_enforce_all_pass.py`：构造合规章节，enforce 预期 exit=0
- [ ] 删除 `step3_runner.py` 中所有"Phase A MVP"注释，改为"Phase B production"
- [ ] README "8 层反 AI 检测"声明与实际层数对齐
- [ ] 典型的 typecheck/零回归

---

### US-006: FIX-11 残留清理 + CI 门禁

**Description**：As 新开发者, I want 全仓零 `from data_modules` 与零意义的 `sys.path.insert` so that 双包合并真闭环。

**映射**：F-005（P1，D5）
**预估**：1.5d
**依赖**：无

**Acceptance Criteria**：
- [ ] `ink-writer/scripts/ink-auto.sh:750` 的 `from data_modules.checkpoint_utils` 改为 `from ink_writer.core.cli.checkpoint_utils`
- [ ] 删除 `ink-auto.sh:1099-1100` 两条 `sys.path.insert`，改用 `PYTHONPATH=$REPO_ROOT:$PYTHONPATH` env var
- [ ] 修复 `skills/ink-resolve/SKILL.md:84-85` 注释与代码的自我矛盾（保留注释，删 85 行的 sys.path.insert）
- [ ] `ink_writer/core/cli/ink.py:573` 的 sys.path hack 改为 relative import 或删除
- [ ] 扫描并修复 `ink-writer/scripts/{ink.py,migrate.py,extract_chapter_context.py,patch_outline_hook_contract.py,measure_baseline.py}` 中的 sys.path.insert
- [ ] 合并 `ink_writer/core/tests_data_modules/` 到主 `tests/` 目录（保留 git 历史）
- [ ] `.pre-commit-config.yaml` 新增 `rg "from data_modules|import data_modules"` fail 门禁（允许白名单：archive/, benchmark/, tests/migration/）
- [ ] `scripts/verify_docs.py` 新增 rule：设计稿 §6.2 零裸路径 §6.3 零 data_modules 校验
- [ ] 典型的 typecheck/零回归

---

### US-007: LLM 调用显式 timeout

**Description**：As a 业主，I want 所有 LLM API 调用有显式 timeout 避免会话卡死 so that 批量写作不会因单次 LLM 挂住而永久阻塞。

**映射**：F-019（P2，D8，提前到 Milestone A）
**预估**：0.5d
**依赖**：无

**Acceptance Criteria**：
- [ ] `ink_writer/editor_wisdom/llm_backend.py` 的 `client.messages.create()` 显式传 `timeout=120`
- [ ] `ink_writer/core/infra/api_client.py` 所有 LLM 调用传 `timeout=120`
- [ ] 新建 config `config/llm_timeouts.yaml`：分 task 类别（writer=300s / polish=180s / checker=90s / classify=60s）
- [ ] 新增 `tests/infra/test_llm_timeout.py`：mock 超时，expect 异常被捕获 + 返回降级结果
- [ ] 典型的 typecheck/零回归

---

### US-008: ink-auto 分层检查点文档对齐（5/10/20/50/200 正式化）

**Description**：As 业主，I want `/ink-auto` 的 5/10/20/50/200 章分层检查点在所有文档中描述一致 so that 预期与实装无漂移。

**映射**：X1（新增，D5+D7）
**预估**：1d
**依赖**：无

**Acceptance Criteria**：
- [ ] `ink-writer/scripts/ink-auto.sh:4` 注释与 `:64-66` 表格对齐，统一为**5 档层级**：每 5 章 ink-review Core+修复 / 每 10 章 ink-audit quick+修复 / 每 20 章 ink-audit standard + Tier2+修复 / 每 50 章 Tier2+drift_detector / 每 200 章 Tier3
- [ ] `skills/ink-macro-review/SKILL.md:55` 与 `:266` 自相矛盾解决：明确"Tier2 默认每 50 章外部触发，但 ink-auto 已在每 20 章内部触发一次 Tier2 浅版"
- [ ] `skills/ink-auto/SKILL.md` 顶部 badge 展示完整 5 档层级
- [ ] `README.md` FAQ 数字对齐（当前说"每 5 章 + 每 20 章"，补齐为"5/10/20/50/200"）
- [ ] 新增 `tests/docs/test_ink_auto_tier_consistency.py`：grep 解析 5 档表格，验证三个文档源同值
- [ ] 更新 `reports/audit-v15-workflow.md` 鸟瞰图（把原"每 50 章"改为 "5/10/20/50/200 多层"）
- [ ] 典型的 typecheck/零回归

---

### Milestone B：补能力（US-009 ~ US-021，v15.9.0 正式发布）

---

### US-009: creativity/name_validator.py（陈词 + 书名黑名单）

**Description**：As 业主, I want 书名和主角名生成时被 Python 硬拦截 so that "神帝/战神/龙傲天"后缀、"我的/全球/无敌"前缀和禁用 combo 不再出现。

**映射**：F-007a（P1，D4）
**预估**：2d
**依赖**：无

**Acceptance Criteria**：
- [ ] 新建 `ink_writer/creativity/__init__.py` + `ink_writer/creativity/name_validator.py`
- [ ] `validate_book_title(title: str) -> ValidationResult`：读 `data/naming/blacklist.json` 的 suffix_ban / prefix_ban / combo_ban，返回 `(passed, violations, suggestion)`
- [ ] `validate_character_name(name: str, role: str = "main") -> ValidationResult`：检查 male/female 通俗人名
- [ ] 支持 `severity=hard/soft`，hard 必须重抽，soft 警告
- [ ] 新增 `tests/creativity/test_name_validator.py`（20+ case：含"林战神"、"我的斗罗大陆"、合法书名）
- [ ] 典型的 typecheck/零回归

---

### US-010: creativity/gf_validator.py（金手指三重约束）

**Description**：As 业主, I want 金手指方案生成时被 Python 硬校验 GF-1/GF-2/GF-3 so that 不再出现"修为暴涨 / 无限金币"类废设定。

**映射**：F-007b（P1，D4）
**预估**：1.5d
**依赖**：US-009（共享 ValidationResult）

**Acceptance Criteria**：
- [ ] `ink_writer/creativity/gf_validator.py`
- [ ] `validate_golden_finger(gf_spec: dict) -> ValidationResult`：
  - GF-1：`dimension` 必须 ∈ {信息/时间/情感/社交/认知/概率/感知/规则} 8 类；含 20+ 禁用词（修为暴涨/无限金币/…）→ hard fail
  - GF-2：`cost` 字段必须有"明确 + 可量化 + 前 10 章可见"描述，用正则/关键词匹配
  - GF-3：`one_liner` ≤20 字 + 含动作/代价 + 有"反直觉"信号
- [ ] 读 `ink-writer/skills/ink-init/references/creativity/golden-finger-rules.md` 的禁用词列表
- [ ] 新增 `tests/creativity/test_gf_validator.py`（15+ case）
- [ ] 典型的 typecheck/零回归

---

### US-011: creativity/sensitive_lexicon_validator.py（L0-L3 密度）

**Description**：As 业主, I want 章节正文中的 L0-L3 敏感词密度被 Python 统计 so that V3/激进档位不会因 L2/L3 超限而被起点退回。

**映射**：F-007c（P1，D4）
**预估**：1.5d
**依赖**：US-009

**Acceptance Criteria**：
- [ ] `ink_writer/creativity/sensitive_lexicon_validator.py`
- [ ] 解析 `style-voice-levels.md` 生成 L0-L3 词库 JSON（约 200-300 词）
- [ ] `validate_density(text: str, voice: str, aggression: int) -> ValidationResult`：按 style-voice-levels.md 密度矩阵（档位 1=0%、档位 2≈0.2%、档位 3=0.5-0.8%、档位 4=0.8-1.5%）判决
- [ ] L3 命中 → hard fail + 返回触发词
- [ ] 新增 `tests/creativity/test_sensitive_lexicon_validator.py`（各档位 case）
- [ ] 典型的 typecheck/零回归

---

### US-012: creativity 扰动引擎 + 5 次重抽降档循环 Python 实装

**Description**：As 业主, I want 扰动引擎和降档循环是真 Python 代码而非 markdown 伪代码 so that 不同 session 结果可复现。

**映射**：F-007d（P1，D4）
**预估**：3d
**依赖**：US-009/US-010/US-011

**Acceptance Criteria**：
- [ ] `ink_writer/creativity/perturbation_engine.py`：
  - `draw_perturbation_pairs(seeds: list, n_pairs: int, rng_seed: int) -> list[tuple]`：从 anti-trope-seeds.json 随机抽 n 对，含 rarity 加权
  - `stable_hash(timestamp, genre) -> int`：确定性 seed 生成
- [ ] `ink_writer/creativity/retry_loop.py`：`run_quick_mode_with_retry(config) -> QuickModeResult`
  - 最多 5 次重抽；每次调 3 个 validator；任一 fail 即下次重抽
  - 连续 5 次失败 → 档位降档（aggression 4→3→2→1）
  - 降档到 1 仍失败 → raise CreativityExhaustedError
- [ ] 新增 `tests/creativity/test_perturbation_engine.py` + `tests/creativity/test_retry_loop.py`（含同 seed 可复现测试）
- [ ] 典型的 typecheck/零回归

---

### US-013: creativity Quick Mode SKILL.md 集成

**Description**：As 业主, I want `/ink-init --quick` 真调用 creativity validator 而非靠 LLM 自律 so that Quick Mode 输出稳定。

**映射**：F-007e（P1，D4）
**预估**：1d
**依赖**：US-012

**Acceptance Criteria**：
- [ ] `ink-writer/skills/ink-init/SKILL.md` Quick Step 1.6/1.7 改为 bash 调用：`python -m ink_writer.creativity.validate --input /tmp/quick_draft.json --output /tmp/validation.json`
- [ ] 脚本入口 `ink_writer/creativity/cli.py` 支持 `validate` 子命令
- [ ] 验证失败时 SKILL.md 明确告诉 LLM 按 validation.json 的 suggestion 重抽
- [ ] 新增 `tests/creativity/test_cli.py`（CLI 入口烟囱测试）
- [ ] 新增 `tests/integration/test_quick_mode_validator_loop.py`：mock Quick Mode 的 3 套方案，验证 validator 能拦下已知俗套样本
- [ ] 典型的 typecheck/零回归

---

### US-014: anti_detection ZT 正则扩展 + 连接词密度

**Description**：As 业主, I want ZT 零容忍项和连接词密度检测覆盖起点常见 AI 味句式 so that 过审拦截率提升到 85%+。

**映射**：F-008（P2，提前到 B）
**预估**：2d
**依赖**：US-003

**Acceptance Criteria**：
- [ ] `config/anti-detection.yaml` 新增 ZT 规则 6-8 条（"不仅……而且"、"尽管如此"、"与此同时"的不同句式变体、"毫无疑问"等）
- [ ] `ink_writer/anti_detection/sentence_diversity.py` 新增 `conjunction_density(text) -> float`
- [ ] 新增配置 `conjunction_density_max: 2.5`（每千字连接词数上限）
- [ ] 用用户的 117 本起点标杆跑 baseline，调试阈值到假阳性 <5%
- [ ] 新增 `tests/anti_detection/test_zt_expansion.py`（新规则命中测试）
- [ ] 新增 `tests/anti_detection/test_conjunction_density.py`
- [ ] 典型的 typecheck/零回归

---

### US-015: 黄金三章阈值软化 + 整章重写逃生门

**Description**：As 业主, I want 前 3 章不会因 editor_wisdom 命中几条 soft 规则就被反复 blocked so that /ink-init 流畅度提升。

**映射**：F-009（P2）
**预估**：1.5d
**依赖**：无

**Acceptance Criteria**：
- [ ] `config/editor-wisdom.yaml` 拆分 `golden_three_hard_threshold: 0.75` + `golden_three_soft_threshold: 0.92`
- [ ] `ink_writer/editor_wisdom/review_gate.py` 实装双阈值逻辑
- [ ] `editor_wisdom/checker.py:62-70` 扣分模型改为指数：`score = 1.0 * (0.7 ** hard_count) * (0.9 ** soft_count)`
- [ ] retry 达 2 次仍失败时触发"整章重写"逃生门（返回 Step 2A，不走 polish 局部修）
- [ ] 新增 `tests/editor_wisdom/test_gradient_threshold.py`
- [ ] 典型的 typecheck/零回归

---

### US-016: 文笔维度 merged_fix_suggestion

**Description**：As 业主, I want polish-agent 收到的镜头/感官/句式节奏修复建议去重合并 so that token 不膨胀、修复方向不冲突。

**映射**：F-011（P2）
**预估**：2.5d
**依赖**：无

**Acceptance Criteria**：
- [ ] 新建 `ink-writer/references/checker-merge-matrix.md`：按维度（镜头/感官/句式节奏/voice/对话）列出主 checker + 从 checker
- [ ] `ink_writer/checker_pipeline/merge_fix_suggestion.py`：读多个 checker report，按 matrix 去重，产出 `merged_fix_suggestion.json`
- [ ] polish-agent.md 改为消费 merged_fix_suggestion.json（而非 3-5 份重叠 report）
- [ ] 新增 `tests/checker_pipeline/test_merge_fix_suggestion.py`
- [ ] 典型的 typecheck/零回归

---

### US-017: 300 章 Shadow 压测（G1-G5 性能指标）

**Description**：As 业主, I want shadow 模式跑 300 章收集 G1-G5 性能指标 so that "300 万字不崩"的推断获得首轮实证（零 LLM 费用）。

**映射**：F-010a（P1，D7）
**预估**：3d
**依赖**：US-002/US-005（确保真阻断和并发安全）

**Acceptance Criteria**：
- [ ] 新建 `benchmark/e2e_shadow_300.py`：
  - 预生成 300 章 mock 章节（每章 1-2KB，模拟正常节奏）
  - 循环跑 Step 0-6 流水线，writer-agent 用 mock 读文件替代 LLM
  - 记录 G1 = wall_time_per_chapter
  - G2 = state.json size at {50, 100, 150, 200, 250, 300}
  - G3 = index.db size at same milestones
  - G4 = context-agent pack size (chars + tokens estimate)
  - G5 = SemanticChapterRetriever.retrieve() p50/p95 latency
- [ ] 产出 `reports/perf-300ch-shadow-v15.md`（含 mermaid 趋势图）
- [ ] 修正 `README.md` FAQ 的"100 章 7 小时"为实测数字或删除
- [ ] 新增 `tests/benchmark/test_shadow_runner_smoke.py`（5 章 smoke 测试，避免 CI 真跑 300 章）
- [ ] 典型的 typecheck/零回归

---

### US-018: Q1-Q8 质量指标仪表盘

**Description**：As 业主, I want 压测结束后一张表看到 8 个客观质量指标 so that 不用读章节也能判断逻辑健康度。

**映射**：X2a（新增，D7）
**预估**：2d
**依赖**：US-017

**Acceptance Criteria**：
- [ ] 新建 `ink_writer/quality_metrics/` 模块
- [ ] `collect_quality_metrics(project_root, chapter_range) -> QualityReport`：
  - Q1 progression cross-chapter conflicts（ooc Layer K 报 CROSS_CHAPTER_OOC 数）
  - Q2 foreshadow 埋设/回收比（plot_thread_registry 统计）
  - Q3 propagation_debt 累积数（drift_detector 写入条数）
  - Q4 review_metrics.passed 比例
  - Q5 consistency-checker critical 累积
  - Q6 continuity-checker critical 累积
  - Q7 candidate_facts 未消歧堆积数
  - Q8 state_kv vs index.db 漂移次数（ink-audit 输出）
- [ ] 整合进 `benchmark/e2e_shadow_300.py`，每 50 章记录一次
- [ ] dashboard 新增 `/quality` 页面展示趋势
- [ ] 产出 `reports/quality-300ch-v15.md`
- [ ] 新增 `tests/quality_metrics/test_collectors.py`
- [ ] 典型的 typecheck/零回归

---

### US-019: AI 审读员（Haiku 4.5 随机抽章评分）

**Description**：As 业主, I want 一个 AI 审读员 每 50 章随机抽 5 章读全文评 4 维度分 so that 我不用读 300 章就能接近"真读过"的判断。

**映射**：X2b（新增，D7）
**预估**：2.5d
**依赖**：US-017

**Acceptance Criteria**：
- [ ] 新建 `ink_writer/ai_reviewer/random_sampler.py`
- [ ] `sample_chapters(project_root, window, n=5) -> list[int]`：每 50 章窗口内随机抽 5 章
- [ ] `ink_writer/ai_reviewer/reader_agent.py`：
  - 用 claude-haiku-4-5（成本优先）
  - 输入：目标章全文 + 前 10 章摘要 + 角色演进 summary
  - 输出 JSON：{角色连贯性 0-100, 时间线 0-100, 设定自洽 0-100, 伏笔兑现感 0-100, 综合 0-100, 问题列表}
- [ ] 阈值 <70 自动 flag 到 `reports/ai-reader-flagged-ch{N}.md`
- [ ] 整合进压测：每 50 章 auto 触发
- [ ] 预算控制：max 60 次 API 调用（$10-30 token）
- [ ] 新增 `tests/ai_reviewer/test_reader_agent.py`（mock API）+ `test_random_sampler.py`
- [ ] 典型的 typecheck/零回归

---

### US-020: 真 LLM 压测（条件触发）

**Description**：As 业主, I want shadow 压测发现性能/质量疑点后，才启动真 LLM 300 章压测 so that 在 $50-200 预算内拿到一轮真实数据。

**映射**：F-010b（P1，D7，2C 策略）
**预估**：4d + token 费
**依赖**：US-017/US-018/US-019

**Acceptance Criteria**：
- [ ] 触发条件（三选一满足即启动）：
  - (a) G2 state.json >30MB at ch200
  - (b) G4 context pack >15K tokens at ch150
  - (c) 任一 Q 指标趋势异常（比如 Q1 跨章 OOC 累积 >50）
- [ ] 若全部正常 → 本 US 自动 skip（notes 标明 "shadow 数据显示健康，真 LLM 压测延后"）
- [ ] 若触发：`benchmark/e2e_real_300.py` 用 claude-sonnet-4-6 真写 50 章（不必 300 章，够暴露问题即可），预算上限 `INK_BENCHMARK_BUDGET_USD=200`
- [ ] 产出 `reports/perf-300ch-real-v15.md`
- [ ] 任何新暴露的 finding 追加到 `reports/audit-v16-emerging.md`（不在本 PRD 修，留下一轮）
- [ ] 典型的零回归（不影响现有测试）

---

### US-021: v15.9.0 发布

**Description**：As 业主, I want Milestone A+B 完成就发 v15.9.0 享受即时收益 so that 不用等 Milestone C 再用 6 周。

**映射**：Milestone 收口（4C 策略）
**预估**：0.5d
**依赖**：US-001 ~ US-020

**Acceptance Criteria**：
- [ ] `ink-writer/.claude-plugin/plugin.json` version 15.0.0 → 15.9.0
- [ ] `pyproject.toml` version 同步
- [ ] `README.md` 版本历史新增 v15.9.0 条目，汇总 step3_runner Phase B + ChapterLockManager 接入 + creativity 子系统 + 300 章压测 + AI 审读员
- [ ] README shield 版本号更新
- [ ] 3 个关键章节人工抽读指引：在 README "如何验证"段落写明"压测后读 100/200/300 三章各 10 分钟"
- [ ] `scripts/verify_docs.py` 通过
- [ ] 典型的零回归

---

### Milestone C：工程卫生（US-022 ~ US-029，v16.0.0 目标）

---

### US-022: Skill 规范修复（ink-plan allowed-tools + CI agent frontmatter 审计）

**Description**：As 业主, I want Skill 规范评分 30/30 so that 项目达 Claude Code 官方完整合规。

**映射**：F-013（P2，D6）
**预估**：1.5d

**Acceptance Criteria**：
- [ ] `skills/ink-plan/SKILL.md` frontmatter 补 `allowed-tools: Read Bash AskUserQuestion`
- [ ] `scripts/verify_docs.py` 新增 rule：所有 SKILL.md 必须含 name/description/allowed-tools；所有 agent .md 必须含 name/description/tools
- [ ] 若新增 agent 默认 allowed-tools 超 Read → CI warn
- [ ] 新增 `tests/docs/test_frontmatter_completeness.py`
- [ ] 典型的零回归

---

### US-023: Agent SDK 优化（prompt_cache 观测 + 模型选型 + batch API）

**Description**：As 业主, I want 充分利用 Anthropic 2026 Q1 SDK 能力 so that 成本与性能双优化。

**映射**：F-014（P2，D6）
**预估**：3d

**Acceptance Criteria**：
- [ ] `ink_writer/core/infra/api_client.py` 每次 response 采集 `usage.cache_creation_input_tokens` / `cache_read_input_tokens`，写入 `cache_metrics.db`
- [ ] 新建 `config/model_selection.yaml`：writer/polish = Opus 4.7, context/data = Sonnet 4.6, checker/classify/extract = Haiku 4.5
- [ ] `api_client.call_claude(task_type)` 按 task_type 自动选型
- [ ] `ink-review` 批量 >10 章时启用 Anthropic Messages Batch API（带 fallback）
- [ ] dashboard `/cache` 页面展示命中率
- [ ] 新增 `tests/infra/test_model_selection.py` + `test_cache_metrics.py`
- [ ] 典型的零回归

---

### US-024: 长记忆范式升级（BM25 + 2 层压缩 + reflection agent）

**Description**：As 业主, I want 对标 NovelCrafter/MemGPT/Generative Agents 补三项长记忆能力 so that 长程一致性更强。

**映射**：F-015（P2，D6）
**预估**：4d

**Acceptance Criteria**：
- [ ] `ink_writer/semantic_recall/retriever.py` 新增 BM25 分支 + FAISS 做 reciprocal rank fusion
- [ ] `ink_writer/core/context/memory_compressor.py` 加章级 L1 压缩（8→3 bullet）
- [ ] `ink_writer/reflection/` 新模块：macro-review 每 50 章读最近摘要+progressions，产出"涌现现象" 3-5 条到 `.ink/reflections.json`
- [ ] context-agent 消费 reflections
- [ ] 新增 `tests/semantic_recall/test_hybrid_retrieval.py` + `tests/reflection/test_reflection_agent.py`
- [ ] 典型的零回归

---

### US-025: architecture_audit 扫描扩展 + 孤儿清理

**Description**：As 业主, I want `scripts/audit_architecture.py` 真实识别 SKILL.md 里的 embedded python 避免误报 so that "unused 123"降到 <20。

**映射**：F-016（P2，D7）
**预估**：1.5d

**Acceptance Criteria**：
- [ ] 扩 `scripts/audit_architecture.py` 扫 `*.md` 里的 `python3 -c "from ink_writer..."` / `python -m ink_writer...`
- [ ] 归档 `ink_writer/incremental_extract/differ.py`（真孤儿）到 `archive/orphans/` 或删除
- [ ] 合并 `ink_writer/core/tests_data_modules/` 到主 `tests/`
- [ ] 跑 audit 后 unused module candidates <20
- [ ] 新增 `tests/audit/test_skill_md_scanner.py`
- [ ] 典型的零回归

---

### US-026: 日志规范化 + JSON/DB 源头统一

**Description**：As 业主, I want print 污染消除 + 所有审查数据有单一事实源 so that 观测一致、可靠。

**映射**：F-017 + F-018（P2，D7+D8）
**预估**：2d

**Acceptance Criteria**：
- [ ] `ink_writer/core/infra/api_client.py` 8 处 retry print 换 `logger.warning`
- [ ] scripts/ 下 non-CLI print → logging（保留用户面向的交互 print）
- [ ] `.ink/reports/review_*.json` 文件顶部加字段 `generated_from: index.db.review_metrics`
- [ ] JSON 文件与 DB 不一致时以 DB 为源自动重生成
- [ ] 新增 `tests/infra/test_logging_migration.py` + `tests/review/test_json_db_consistency.py`
- [ ] 典型的零回归

---

### US-027: import cycle 解构 + foreshadow/plotline tracker Python 合并

**Description**：As 业主, I want Python 层唯一 import cycle 消除 + 冗余 tracker 合并 so that 架构干净。

**映射**：F-012 + F-004（P2，D5）
**预估**：1.5d

**Acceptance Criteria**：
- [ ] 新建 `ink_writer/chapter_paths_types.py` 只含类型定义，拆解 chapter_paths ↔ chapter_outline_loader 循环
- [ ] `scripts/audit_architecture.py` 报告 Import cycles = 0
- [ ] 新建 `ink_writer/thread_lifecycle/tracker.py` 统一入口，内部 delegate 到 foreshadow + plotline
- [ ] 保留 `foreshadow/tracker.py` + `plotline/tracker.py` 2 个 session 作为 transitional shim
- [ ] 新增 `tests/thread_lifecycle/test_unified_tracker.py`
- [ ] 典型的零回归

---

### US-028: 前 3 章 checker 冲突仲裁 + 细节收尾

**Description**：As 业主, I want 前 3 章所有 checker 冲突有明确仲裁表 + 收尾杂项 so that v16.0.0 无未结悬项。

**映射**：F-006 + F-020 + F-021（D3+D8+D7）
**预估**：2d
**依赖**：US-016（merged_fix_suggestion）

**Acceptance Criteria**：
- [ ] 新建 `ink-writer/references/golden-three-arbitration.md`：章 1-3 被 golden-three-checker + 4 项爽点硬阻断 + editor_wisdom 同时检测时的优先级表
- [ ] polish-agent 消费仲裁结果，不再收到自相矛盾 fix_prompt
- [ ] `scripts/editor-wisdom/03_classify.py` + `05_extract_rules.py` 入口补 `ANTHROPIC_API_KEY` 校验 + 连续失败 abort + 测试
- [ ] `CLAUDE.md` Top 3 注意事项精简（删 FIX-11 警告，因 US-006 已解）
- [ ] 新增 `tests/editor_wisdom/test_api_key_guard.py`
- [ ] 新增 `tests/integration/test_chapter1_arbitration.py`
- [ ] 典型的零回归

---

### US-029: v16.0.0 发布

**Description**：As 业主, I want Milestone C 完成打包为 v16.0.0 正式发布 so that 本轮审计全面闭环。

**映射**：Milestone 收口
**预估**：0.5d
**依赖**：US-022 ~ US-028

**Acceptance Criteria**：
- [ ] `plugin.json` + `pyproject.toml` version → 16.0.0
- [ ] `README.md` 版本历史新增 v16.0.0：汇总 Skill 规范 30/30 + Agent SDK 优化 + 长记忆升级（BM25/2 层压缩/reflection）+ import cycle 消除 + 日志规范化
- [ ] 产出 `reports/v16-release-audit.md` 总结本 PRD 29 US 完成情况 + 未解的"新暴露 finding"（从 US-020 而来）
- [ ] 运行 `scripts/verify_docs.py` 全通过
- [ ] 新增集成测试 `tests/release/test_v16_gates.py`（版本号一致性 + 全维度 sanity）
- [ ] 典型的零回归

---

## 4. Functional Requirements

- **FR-1**：step3_runner 的 5 个 Python gate 必须调用真 LLM checker，不得使用 stub
- **FR-2**：PipelineManager parallel>1 模式必须通过 ChapterLockManager 保护 state.json / index.db 写入
- **FR-3**：全仓 `from data_modules` 引用数 = 0（白名单除外）
- **FR-4**：ink_writer/creativity/ 必须提供 3 个 validator + 扰动引擎 + 5 次重抽降档循环，对标 editor_wisdom 架构
- **FR-5**：5/10/20/50/200 章分层检查点在 ink-auto.sh + SKILL.md + README 三处描述一致
- **FR-6**：300 章 shadow 压测必须收集 G1-G5 性能指标 + Q1-Q8 质量指标 + AI 审读员评分
- **FR-7**：所有 LLM API 调用有显式 timeout（按 task 类别配置）
- **FR-8**：所有 SKILL.md 含 name/description/allowed-tools frontmatter；所有 agent .md 含 name/description/tools
- **FR-9**：Anthropic Messages Batch API 用于 ink-review 批量 >10 章场景（带 fallback）
- **FR-10**：每个 US 完成后 `pytest --no-cov` 全量无新增失败（baseline ≥2420）

---

## 5. Non-Goals（明确不做）

- **不保证"完美无缺陷"**：本 PRD 闭环 v5+v15 两轮审计发现，压测会产生新 finding（US-020 输出到 `audit-v16-emerging.md`），留下一轮
- **不做项目重写**：保留 ink_writer/core 目录结构与 v15 架构
- **不做跨书知识继承**（Sudowrite Series Folder 范式）——推迟到 v17+
- **不做方言/地域风格**
- **不做图文混排 / 视频生成**
- **不做移动端或桌面原生客户端**
- **不做自动告警**（Q 指标超阈值发邮件/钉钉）——v17+
- **不修改数据库 schema**（除 US-012 扰动引擎可能需 `creativity_fingerprint_entries` 表外不动）
- **不引入新外部服务依赖**（保留 Anthropic SDK 为唯一 LLM 提供方 + 可选 ModelScope/OpenAI embedding）

---

## 6. Design Considerations

### 6.1 依赖图
```
US-001 → US-002 (ChapterLockManager)
US-001 → US-003 → US-004 → US-005 (step3_runner Phase B)
US-009 → US-010 / US-011 → US-012 → US-013 (creativity)
US-017 → US-018 / US-019 → US-020 (压测链)
US-016 → US-028 (仲裁)
US-001 ~ US-020 → US-021 (v15.9.0)
US-022 ~ US-028 → US-029 (v16.0.0)
```

### 6.2 Ralph 执行策略（1C）
- Ralph 每轮按 `priority asc` 找第一条 `passes:false` 的 US 执行
- 完成后 commit + `jq` 改 `passes:true`
- 不提问、不暂停——纯自治
- 零回归失败即 `git reset --hard` + 标 `passes:false` 下轮再试

### 6.3 新增目录
- `ink_writer/creativity/`（US-009~US-013）
- `ink_writer/quality_metrics/`（US-018）
- `ink_writer/ai_reviewer/`（US-019）
- `ink_writer/reflection/`（US-024）
- `ink_writer/thread_lifecycle/`（US-027）
- `ink_writer/chapter_paths_types.py`（US-027）

---

## 7. Technical Considerations

- **性能预算**：step3_runner Phase B 会每章加 5-10 秒（5 个 gate × LLM 调用）。Milestone A 完成后 wall time 预计 +10%
- **Token 预算**：US-020 真压测上限 $200；US-019 AI 审读员上限 $30
- **SQLite schema 影响**：US-012 可能需要 `creativity_fingerprint_entries` 新表（由该 US 自己 migrate）
- **BatchAPI tier**：US-023 需 Anthropic tier 3+ 账户（留 Open Question）
- **整章重写逃生门**（US-015）依赖 writer-agent 的 re-entry，需验证不会无限循环（最多 1 次）

---

## 8. Success Metrics

| 指标 | 当前 v15.0.0 | v15.9.0 目标 | v16.0.0 目标 |
|------|:---:|:---:|:---:|
| step3_runner 真阻断能力 | 0/5（全 stub） | 5/5（真 LLM） | 5/5 |
| SKILL.md ↔ 代码一致率 | 85% | 100% | 100% |
| parallel=4 数据安全 | 🔴 裸奔 | 🟢 ChapterLockManager | 🟢 |
| Quick Mode 书名黑名单触碰率 | 未知 | <1% | <0.5% |
| 300 章 Q1-Q8 全指标健康 | 无数据 | 至少 shadow 有数据 | shadow+真 LLM 双数据 |
| AI 审读员平均评分 | N/A | ≥75/100 | ≥82/100 |
| AI 味过审拦截率 | ~65% | ~82% | ~85% |
| Skill 规范评分 | 27/30 | 27/30 | 30/30 |
| 测试数 | 2420 | ≥2600 | ≥2800 |
| Import cycles | 1 | 1 | 0 |
| unused module candidates | 123 | 123 | <20 |

---

## 9. Open Questions

1. **Anthropic 账户 tier** 是否支持 Messages Batch API（US-023 需 tier 3+）？若不支持则 US-023 的 batch 部分降级为普通并发
2. **US-020 真压测预算** $200 是否可调？若 US-017 shadow 发现严重性能问题，是否允许扩预算到 $500？
3. **US-019 AI 审读员模型选型**：Haiku 4.5 性价比高但准确度有限，是否允许关键章节（100/200/300）升级 Sonnet 4.6？
4. **v15.9.0 发布**：是否同步更新 GitHub release notes + marketplace？还是纯本地 version bump？
5. **US-024 Reflection agent** 的"涌现现象"如何评估质量？是否需要单独的 reflection-checker agent 做二级审查？
6. 用户 Memory `project_quality_optimization.md` 提到"情感紧凑度"，是否要单独抽一条 US？当前归在 F-011 merged_fix_suggestion 的 sensory-immersion 维度里顺带做

---

## 10. Ralph 执行清单（供 /ralph 转 prd.json 参考）

- **总 US 数**：29
- **branchName 建议**：`ralph/v16-audit-completion`
- **排除范围**：无（上轮排除的 FIX-16 已通过 US-020 重新纳入）
- **零回归基线**：pytest 2420 passed（v15.0.0 HEAD=910add7）
- **人工决策点**：无（用户已 pre-approve 所有方向，1C 策略纯自治）
- **Session 分片建议**：
  - Session A：US-001 ~ US-008（Milestone A，约 1-1.5 周）
  - Session B：US-009 ~ US-016（creativity + 反 AI 味 + 文笔，约 2 周）
  - Session C：US-017 ~ US-021（压测 + v15.9.0，约 1.5 周）
  - Session D：US-022 ~ US-029（Milestone C + v16.0.0，约 2 周）

---

**PRD 结束。** 总 29 个 US，预计 6-8 周（单 session/agent 按 priority 自治推进）。建议下一步：`/ralph @tasks/prd-v16-audit-completion.md` 生成 `prd.json`，再 `ralph.sh` 跑起来。
