# PRD: M5 完整闭环上线 — Dashboard 治理 + Layer 4/5 + user_corpus + 文档

## Introduction

落地 spec §9 M5（详见 `docs/superpowers/specs/2026-04-25-m5-final-design.md`）：5 周 roadmap **最后一个 milestone**，建 Layer 4 复发追踪 + Layer 5 元规则浮现 + dashboard 4 大指标治理面板 + 周报 CLI + A/B 通道 + user_corpus history-travel + ink-learn 改造（auto-case-from-failure + promote）+ 作者/编辑双手册，**整套产线工业化结构闭环**。

本期不做：真实测试书 30 章（M5 之外的真实质量验证）；M2 corpus_chunks 实跑（保持 deferred）；元规则浮现的 cron 自动化；dashboard 写权限。

详细 plan：`docs/superpowers/plans/2026-04-25-m5-final.md`（3338 行 / 13-task TDD）。

## Goals

- case schema 加 3 字段（recurrence_history / meta_rule_id / sovereign）+ 现有 410 个 case 完全向后兼容
- Layer 4 `regression_tracker` 模块：扫 evidence_chain 检测 resolved → regressed + 升级 severity
- Layer 5 `meta_rule_emergence` 模块：N=5 + LLM 相似度 > 0.80 → 提议合并到 `data/case_library/meta_rules/MR-NNNN.yaml`（pending）
- `ink meta-rule {list,approve,reject}` CLI 用户审批门禁
- dashboard "M5 Case 治理" 标签页：4 大指标（病例复发率 / 修复速度 / 编辑评分趋势 / checker 准确率）+ M3/M4 dry-run counter + 切换推荐 + pending 元规则列表
- `ink dashboard report --week N` 周报 CLI 生成 markdown 到 `reports/weekly/<year>-W<NN>.md`
- A/B 通道 `config/ab_channels.yaml` + `--channel A|B` flag + evidence_chain 加 `channel` 字段（向后兼容）
- user_corpus history-travel 样例（`明朝那些事儿_节选`）+ `_meta.yaml` + `user_genres.yaml`
- ink-learn `--auto-case-from-failure`（每周限 5 个）+ `--promote`（短期记忆 → 长期 case）
- `docs/USER_MANUAL.md` 5 节（作者）+ `docs/EDITOR_FEEDBACK_GUIDE.md` 3 节（编辑）
- 复用 M1-M4 全部资产（case_library / evidence_chain / planning_writer / LLMClient / ink-dashboard / ink-learn），全部不重建

## User Stories

### US-001: case schema 扩展（recurrence_history / meta_rule_id / sovereign）
**Description:** 作为开发者，我需要给 `Case` dataclass 加 3 个 optional 字段（recurrence_history list / meta_rule_id str|None / sovereign bool），让现有 410 个 case yaml 不强制 backfill 也能加载。

**Acceptance Criteria:**
- [ ] 修改 `ink_writer/case_library/models.py`：`Case` 加 `recurrence_history: list[dict] = field(default_factory=list)` + `meta_rule_id: str | None = None` + `sovereign: bool = False`；`to_dict()` 输出新字段；`from_dict()` 容错读取（缺字段 fallback 默认值）
- [ ] 修改 `schemas/case_schema.json` 加 3 个 optional 字段（不破坏 required；现有 active cases 校验仍过）
- [ ] 新增 `tests/case_library/test_schema_extension.py` 含 5 用例：`test_case_defaults_to_empty_recurrence_and_no_meta_rule_and_not_sovereign` / `test_to_dict_includes_m5_fields` / `test_from_dict_backward_compatible_missing_m5_fields` / `test_existing_410_cases_still_load`（扫 data/case_library/cases/*.yaml round-trip）/ `test_sovereign_explicit_true`
- [ ] `pytest.ini` testpaths 行尾追加 `tests/regression_tracker tests/meta_rule_emergence tests/dashboard tests/learn`（保持单行不重复 M3/M4 已添加的）
- [ ] `pytest tests/case_library/test_schema_extension.py -v --no-cov` 输出 5 passed
- [ ] `pytest tests/case_library/ -v --no-cov` 全绿（M3/M4 已有用例向后兼容）
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 1

### US-002: Layer 4 regression_tracker 模块
**Description:** 作为产线复发追踪机制，我需要 `ink_writer/regression_tracker/` 模块扫所有 evidence_chain（chapter + planning），检测 status=resolved 的 case 是否再次被命中（cases_violated/cases_hit 含其 id），如有则给 case 加一条 `recurrence_history` 记录 + 升级 severity（hard 已顶则 recurrence_count++）+ status 改 regressed。**只检查同 book 内复发**（Q3 默认）。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/regression_tracker/{__init__,models,tracker,__main__}.py`
- [ ] `RecurrenceRecord` dataclass 字段：case_id / book / chapter (None=planning) / evidence_chain_path / resolved_at / regressed_at / severity_before / severity_after + `to_dict()`
- [ ] `scan_evidence_chains(*, base_dir, case_store, since=None) -> list[RecurrenceRecord]`：扫所有 evidence_chain → 同 book 同 case 仅记一次 → 跳过非 resolved case
- [ ] `apply_recurrence(*, record, case_store) -> Case`：调 case_store.record_recurrence 持久化 history + 升级 severity + 改 status=regressed
- [ ] 修改 `ink_writer/case_library/store.py` 加 `iter_resolved()` + `record_recurrence(case_id, record)`：severity P3→P2→P1→P0 升级；P0 已顶则 recurrence_count++（实际由 history list 长度体现）
- [ ] 修改 store.py 加 `iter_all() -> Iterator[Case]`（M5 dashboard 用）
- [ ] `__main__.py` CLI: `python -m ink_writer.regression_tracker [--since YYYY-MM-DD] [--apply]` 默认 dry-run 不写盘；带 `enable_windows_utf8_stdio()`
- [ ] 新增 `tests/regression_tracker/{__init__,test_tracker}.py` 含 5 用例：`test_scan_detects_resolved_case_recurrence` / `test_scan_skips_pending_cases` / `test_scan_dedup_per_book` / `test_scan_handles_planning_evidence` / `test_apply_upgrades_severity_and_status`
- [ ] `pytest tests/regression_tracker/ -v --no-cov` 输出 5 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 2

### US-003: Layer 5 meta_rule_emergence 模块
**Description:** 作为元规则归纳机制，我需要 `ink_writer/meta_rule_emergence/` 模块扫所有 active cases（不含 sovereign + 不含已 meta_rule_id），按 tag 重叠粗分组 → LLM 主观判断（glm-4.6） → N=5 + similarity > 0.80 时产 `MetaRuleProposal` → 写 `data/case_library/meta_rules/MR-NNNN.yaml`（status=pending）。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/meta_rule_emergence/{__init__,models,emerger,__main__}.py` + `prompts/emerge.txt`
- [ ] `MetaRuleProposal` 字段：proposal_id (MR-NNNN) / similarity / merged_rule (一句话元规则) / covered_cases (case_id list) / reason；`to_dict()` 输出加 `status: "pending"`
- [ ] prompt 模板含 `{cases_json}` 占位符；要求 JSON 输出 `{similar, similarity, merged_rule, covered_cases, reason}`
- [ ] `find_similar_clusters(*, cases, llm_client, min_cluster_size=5, similarity_threshold=0.80, model='glm-4.6') -> list[MetaRuleProposal]`：先 `_candidate_clusters_by_tags` 粗筛 + 跳过 sovereign + 跳过已 meta_rule_id；调 LLM；返回 covered_cases 至少 N 个 + similarity 达标的 proposal
- [ ] `_next_proposal_id` 扫 meta_rules/ 取最大 MR-NNNN 编号 + 1（缺目录 → MR-0001）
- [ ] `write_meta_rule_proposal(*, proposal, base_dir) -> Path`：用 yaml.safe_dump 写入 base_dir/MR-NNNN.yaml，`allow_unicode=True`
- [ ] `__main__.py` CLI: `python -m ink_writer.meta_rule_emergence [--propose] [--min-cluster N] [--similarity F]`
- [ ] 新增 `tests/meta_rule_emergence/{__init__,test_emerger}.py` 含 6 用例：`test_finds_cluster_with_5_similar` / `test_skips_below_min_cluster` / `test_skips_sovereign` / `test_skips_already_meta_rule_id` / `test_low_similarity_returns_empty` / `test_write_meta_rule_proposal`
- [ ] `pytest tests/meta_rule_emergence/ -v --no-cov` 输出 6 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 3

### US-004: ink meta-rule {list,approve,reject} CLI
**Description:** 作为用户审批门禁，我需要 `ink meta-rule {list,approve,reject}` 子命令：list 按 status 列出 / approve 给覆盖 cases 写 meta_rule_id 字段 + 改 proposal status=approved / reject 改 status=rejected。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/case_library/meta_rule_cli.py` 暴露 `cmd_list / cmd_approve / cmd_reject` + `register_subparsers(subparsers)` + `main()`
- [ ] `cmd_list` 支持 `--status pending|approved|rejected` 过滤；输出每行格式 `MR-NNNN status=X sim=0.XX cases=N :: <merged_rule>`
- [ ] `cmd_approve <proposal_id>`：读 proposal yaml；status != pending 时返回 1；给 covered_cases 各 case 写 `meta_rule_id`；proposal 改 status=approved + 加 approved_at；用 `case_store._save_case` 持久化
- [ ] `cmd_reject <proposal_id>`：读 proposal yaml；改 status=rejected + 加 rejected_at
- [ ] 修改 `ink_writer/case_library/cli.py` 注册 `meta-rule` 子命令到 main parser
- [ ] CLI 入口带 `enable_windows_utf8_stdio()`
- [ ] 新增 `tests/case_library/test_meta_rule_cli.py` 含 4 用例：`test_list_pending` / `test_approve_writes_meta_rule_id_to_cases` / `test_approve_idempotent`（已处理过的 proposal 返回 1）/ `test_reject`
- [ ] `pytest tests/case_library/test_meta_rule_cli.py -v --no-cov` 输出 4 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 4

### US-005: dashboard "M5 Case 治理" 标签页 + 4 大指标 aggregator
**Description:** 作为产线可视化，我需要 dashboard 加"M5 Case 治理"标签页：4 大指标（recurrence_rate / repair_speed_days / editor_score_trend / checker_accuracy）+ M3/M4 dry-run counter + 通过率 + 切换推荐（continue/investigate/switch）+ pending meta_rules 列表 + 复发 case 列表。后端路由 `/api/m5-overview` 返回完整 JSON。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/dashboard/{__init__,aggregator,m5_overview}.py`
- [ ] `aggregator.compute_recurrence_rate(*, case_store_iter)` 返回 (recurrent count) / (resolved+regressed total)；空集 → 0.0
- [ ] `aggregator.compute_repair_speed(*, case_store_iter)` 返回平均天数（M5 占位 7.0；真实数据需 case 加 resolved_at 字段后续 enhance；注释明示）
- [ ] `aggregator.compute_editor_score_trend(*, base_dir=Path('data/editor_reviews'))` 扫 yaml → list[{date, score, book}]
- [ ] `aggregator.compute_checker_accuracy(*, sample_dir=Path('data/checker_accuracy_samples'))` 缺目录 → 0.0（占位）
- [ ] `aggregator.recommend_dry_run_switch(*, counter, pass_rate, threshold_runs=5, threshold_pass_rate=0.60)` 返回 'switch'|'continue'|'investigate'：counter < 5 → continue；pass_rate < 0.60 → investigate；否则 switch
- [ ] `aggregator.compute_m3_dry_run_pass_rate(*, base_dir)` 返回 (counter, pass_rate)：读 `.dry_run_counter` + 扫 chapter evidence_chain `overall_passed`
- [ ] `aggregator.compute_m4_dry_run_pass_rate(*, base_dir)` 同上读 `.planning_dry_run_counter` + 扫 planning_evidence_chain stages `overall_passed`
- [ ] `m5_overview.get_m5_overview(*, base_dir, case_store=None) -> dict`：返回 `{metrics, dry_run, pending_meta_rules, recurrent_cases}` 完整结构
- [ ] 修改 `ink-writer/skills/ink-dashboard/SKILL.md` 末尾追加 `## M5 Case 治理（M5 P3 必跑）` 章节，含 macOS/Linux 命令 + Windows PowerShell sibling + `ink dashboard --m5` + `curl /api/m5-overview` + 周报命令
- [ ] 新增 `tests/dashboard/{__init__,conftest}.py`（fixtures）
- [ ] 新增 `tests/dashboard/test_aggregator.py` 含 6 用例：`test_recurrence_rate_zero_when_no_resolved` / `test_recurrence_rate_basic` / `test_recommend_switch_below_threshold` / `test_recommend_switch_low_pass_rate` / `test_recommend_switch_ready` / `test_m3_dry_run_pass_rate` / `test_m4_dry_run_pass_rate`
- [ ] 新增 `tests/dashboard/test_m5_overview.py` 含 3 用例：`test_overview_structure` / `test_overview_finds_pending_meta` / `test_overview_recommends_correctly`
- [ ] `pytest tests/dashboard/test_aggregator.py tests/dashboard/test_m5_overview.py -v --no-cov` 输出 9 passed (6+3) — 注：aggregator 实际 7 用例
- [ ] `grep -c 'M5 Case 治理' ink-writer/skills/ink-dashboard/SKILL.md` ≥ 1
- [ ] `grep -c 'PowerShell' ink-writer/skills/ink-dashboard/SKILL.md` ≥ 1
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 5

### US-006: ink dashboard report --week N 周报 CLI
**Description:** 作为产线运营周报机制，我需要 `ink dashboard report --week N` CLI 调 `get_m5_overview()` 拼 markdown 周报到 `reports/weekly/<year>-W<NN>.md`，含 4 大指标 + Layer 4 复发列表 + Layer 5 pending 元规则 + dry-run 状态 + 行动项。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/dashboard/weekly_report.py` 暴露 `_week_range(week_num, year)` + `generate_weekly_report(*, week_num, year=2026, book=None, base_dir=Path('data'), out_path=None) -> Path` + `main()` CLI
- [ ] `_week_range`：用 ISO week 算 (Monday, Sunday) 字符串；W17/2026 = ('2026-04-20', '2026-04-26')
- [ ] markdown 模板含 5 个 H2 段：`## 4 大指标` / `## Layer 4 复发追踪` / `## Layer 5 元规则浮现` / `## Dry-run 状态` / `## 行动项`
- [ ] 行动项条件触发：pending 元规则 ≥ 1 → 加"审批 N 条 pending 元规则"；m3/m4 推荐 switch → 加"评估 dry-run 切真"
- [ ] CLI: `ink dashboard report --week N [--year Y] [--book B] [--out PATH]` 默认输出 `reports/weekly/<Y>-W<NN>.md`；带 `enable_windows_utf8_stdio()`
- [ ] 修改 `ink_writer/dashboard/__init__.py` 加 `cli_main()` 注册 `report` 子命令路由到 `weekly_report.generate_weekly_report`
- [ ] 新增 `tests/dashboard/test_weekly_report.py` 含 3 用例：`test_week_range_w17` / `test_generate_creates_report_file` / `test_report_includes_action_items`（dry-run counter=10 + pass_rate=100% → "评估 M3 dry-run 切真"）
- [ ] `pytest tests/dashboard/test_weekly_report.py -v --no-cov` 输出 3 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 6

### US-007: A/B 通道 config + --channel flag + evidence_chain channel 字段
**Description:** 作为防过拟合护栏（spec §7.4），我需要 `config/ab_channels.yaml` 配置（默认 enabled=false）+ `EvidenceChain.channel: str | None` 字段 + planning_writer 透传 + ink-write SKILL.md 加 `--channel` 参数说明。

**Acceptance Criteria:**
- [ ] 新增 `config/ab_channels.yaml`：`enabled: false` + `channels.A.{description,overrides}` + `channels.B.{description,overrides}`；A 跳过 meta_rule，B 启用 meta_rule
- [ ] 修改 `ink_writer/evidence_chain/models.py` `EvidenceChain` 加 `channel: str | None = None`；`to_dict()` 输出 `channel`
- [ ] 修改 `ink_writer/evidence_chain/planning_writer.py` 让合并/新建 stages 时透传 `channel` 字段到 stage dict
- [ ] 修改 `ink-writer/skills/ink-write/SKILL.md` Step 1.5 附近加 `### M5 A/B 通道（可选）` 段，含 `--channel A|B` 命令示例 + evidence_chain 字段说明
- [ ] 新增 `tests/evidence_chain/test_channel_field.py` 含 4 用例：`test_channel_default_none` / `test_channel_a` / `test_channel_b` / `test_planning_evidence_writes_channel`（写入后 stages[0]['channel'] == 'A'）
- [ ] `pytest tests/evidence_chain/test_channel_field.py -v --no-cov` 输出 4 passed
- [ ] M3/M4 已有 evidence_chain 测试全绿（向后兼容；channel 默认 None）
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 7

### US-008: user_corpus history-travel 样例 + ingest 链路
**Description:** 作为用户扩展接口验证（spec §3 P3），我需要 `data/case_library/user_corpus/history-travel/` 含 2 个公开节选 + `_meta.yaml` + `user_genres.yaml` 索引；M2 corpus_chunks 仍 deferred 不真跑切片。

**Acceptance Criteria:**
- [ ] 新增 `data/case_library/user_corpus/history-travel/_meta.yaml`：`{genre: history-travel, license: fair_use_excerpt, files: [{path, source, note}], created_at}`
- [ ] 新增 `data/case_library/user_corpus/history-travel/明朝那些事儿_节选_第一章.txt`：≤ 2000 字 / ≥ 100 字（fair use 边界；可用 LLM 仿写历史叙事文体片段标 synthetic_excerpt 避免版权风险）
- [ ] 新增 `data/case_library/user_corpus/history-travel/明朝那些事儿_节选_第二章.txt`：同上
- [ ] 新增 `data/case_library/user_corpus/user_genres.yaml`：`{genres: {history-travel: {path, chunks_count: 0, last_ingested_at: null}}, created_at}`
- [ ] 新增 `tests/case_library/test_user_corpus_meta.py` 含 3 用例：`test_meta_yaml_schema_history_travel`（必须有 genre/license/files；files 至少 1 项含 path+source）/ `test_corpus_files_exist_and_under_size_limit`（每个 .txt 字数 100-2000）/ `test_user_genres_yaml_index`（含 history-travel）
- [ ] `pytest tests/case_library/test_user_corpus_meta.py -v --no-cov` 输出 3 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 8

### US-009: ink-learn --auto-case-from-failure
**Description:** 作为短期记忆 → 长期 case 自动通道，我需要 `ink_writer/learn/auto_case.py` 暴露 `propose_cases_from_failures()`：扫 7 天内 blocked 章节 evidence_chain，识别同一 cases_violated 组合出现 ≥ 2 次的"新模式"，自动 propose pending case 到 `data/case_library/cases/CASE-LEARN-NNNN.yaml`，每周限 5 个。

**Acceptance Criteria:**
- [ ] 新增 `config/ink_learn_throttle.yaml`：`auto_case_from_failure: {max_per_week: 5, min_pattern_occurrences: 2, pattern_window_days: 7}`
- [ ] 新增 `ink_writer/learn/{__init__,auto_case}.py`
- [ ] `propose_cases_from_failures(*, case_store, base_dir, cases_dir, throttle_path=None, now=None) -> list[Case]`：调 `_load_throttle` + `_scan_blocked_evidence(since=now-window_days)` + `Counter` 统计 cases_violated tuple → 跳过模式中所有 case 已存在 → 创建 pending Case 写盘
- [ ] 新建 case yaml 字段：`id=CASE-LEARN-NNNN, status=pending, severity=P2, category=auto_learned, tags=[m5_auto_learn, ...pattern_case_ids[:3]], failure_pattern.{description, observable=list(pattern), examples=[]}, countermeasure.guideline, source.{type=ink_learn_auto, notes}, created_at`
- [ ] `_next_learn_id(cases_dir)` 扫现有 CASE-LEARN-NNNN 取最大编号 + 1（缺则 0001）
- [ ] 修改 `ink-writer/skills/ink-learn/SKILL.md` 末尾追加 `## M5 自动 case 提案（M5 P3）` 段，含 macOS/Linux 命令 + Windows PowerShell sibling
- [ ] 新增 `tests/learn/{__init__,test_auto_case}.py` 含 4 用例：`test_proposes_when_pattern_repeats`（同 cases_violated 出现 2 次 → 1 个 pending case 写盘）/ `test_skips_below_min_occurrences`（仅 1 次 → 空）/ `test_throttled_at_max_per_week`（6 个 pattern × 2 次 → 限 5）/ `test_skips_passed_chapters`（overall_passed=True 不参与）
- [ ] `pytest tests/learn/test_auto_case.py -v --no-cov` 输出 4 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 9

### US-010: ink-learn --promote
**Description:** 作为短期记忆桥接，我需要 `ink_writer/learn/promote.py` 暴露 `promote_short_term_to_long_term()`：读 `.ink/<book>/project_memory.json`，把"重复 ≥ 3 次"的 success/failure pattern 回灌 `data/case_library/cases/CASE-PROMOTE-NNNN.yaml`（pending）。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/learn/promote.py`
- [ ] `promote_short_term_to_long_term(*, project_memory_path, case_store, cases_dir=Path('data/case_library/cases'), min_occurrences=3) -> list[Case]`：读 `{patterns: [{text, kind, count}, ...]}` → 跳过 count < min → 创建 Case 写盘
- [ ] 新建 case yaml 字段：`id=CASE-PROMOTE-NNNN, status=pending, severity=P2 (failure) | P3 (success), category=auto_promoted, tags=[m5_promote, kind], failure_pattern.description=text, source.{type=ink_learn_promote, notes}`
- [ ] 缺 project_memory.json 时返回空 list 不抛错
- [ ] 修改 `ink-writer/skills/ink-learn/SKILL.md` 末尾追加 `### --promote` 段
- [ ] 新增 `tests/learn/test_promote.py` 含 4 用例：`test_promotes_high_frequency_pattern`（count=5 → 1 个 case）/ `test_skips_below_min_occurrences`（count=2 < 3 → 空）/ `test_handles_missing_project_memory`（缺文件 → []）/ `test_success_kind_assigns_p3`（kind=success → severity=P3）
- [ ] `pytest tests/learn/test_promote.py -v --no-cov` 输出 4 passed
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 10

### US-011: docs/USER_MANUAL.md（作者使用手册 5 节）
**Description:** 作为作者上手指南，我需要 `docs/USER_MANUAL.md` 5 节：开新书 / 写章 / 看 dashboard / 录编辑反馈 / 应急绕过。

**Acceptance Criteria:**
- [ ] 新增 `docs/USER_MANUAL.md` 含 5 个 H2 段：`## 1. 开新书（ink-init）` / `## 2. 写章（ink-write）` / `## 3. 看 dashboard` / `## 4. 录编辑反馈` / `## 5. 应急绕过`
- [ ] 第 1 节包含 quick / detailed 两个模式 + Step 99 策划期审查（M4）说明 + skip-planning-review flag
- [ ] 第 2 节包含 Step 1.5 写完合规循环（M3）+ A/B 通道（M5）+ 紧急绕过（skip-compliance）
- [ ] 第 3 节包含 4 大指标解读 + 切换推荐 + 周报命令
- [ ] 第 4 节包含 ink case ingest + 评分录入 yaml schema + ink case approve
- [ ] 第 5 节包含 5 项应急绕过 + Rollback（git checkout tag）
- [ ] 文件存在校验：`test -f docs/USER_MANUAL.md`
- [ ] 行数 ≥ 130 + H2 段 ≥ 5：`grep -cE '^## ' docs/USER_MANUAL.md` 输出 ≥ 5
- [ ] 所有 `open()` 带 `encoding='utf-8'`（如有 Python 代码）
- [ ] Typecheck passes
**Priority:** 11

### US-012: docs/EDITOR_FEEDBACK_GUIDE.md（编辑反馈手册 3 节）
**Description:** 作为编辑/产品录入指南，我需要 `docs/EDITOR_FEEDBACK_GUIDE.md` 3 节：评分录入 / case 提案审批 / 复发申诉。

**Acceptance Criteria:**
- [ ] 新增 `docs/EDITOR_FEEDBACK_GUIDE.md` 含 3 个 H2 段：`## 1. 评分如何录入` / `## 2. case 提案审批` / `## 3. 复发申诉`
- [ ] 第 1 节包含 `data/editor_reviews/<book>.yaml` schema + 录入流程
- [ ] 第 2 节包含 ink case list/approve/reject + 自动学习 case (CASE-LEARN-/CASE-PROMOTE-)
- [ ] 第 3 节包含 sovereign 字段标记 + ink case mark-resolved + ink meta-rule list/approve/reject
- [ ] 文件存在校验：`test -f docs/EDITOR_FEEDBACK_GUIDE.md`
- [ ] 行数 ≥ 70 + H2 段 ≥ 3：`grep -cE '^## ' docs/EDITOR_FEEDBACK_GUIDE.md` 输出 ≥ 3
- [ ] Typecheck passes
**Priority:** 12

### US-013: M5 e2e + tag m5-final + ROADMAP/handoff "5 周完成"标记
**Description:** 作为 M5 验收 + 5 周 roadmap 收官，我需要 `tests/integration/test_m5_e2e.py` 6 用例覆盖 spec §13 验收清单 + 全量 pytest 全绿 + tag `m5-final` push 到 origin + 更新 docs/superpowers/M-ROADMAP.md（M5 ⚪→✅ + Status "5 周 100% 完成"）+ 更新 docs/superpowers/M-SESSION-HANDOFF.md（§2 80%→100% + §3 重写 M5 实际产出 + §7 改"真实质量验证"段）。

**Acceptance Criteria:**
- [ ] 新增 `tests/integration/test_m5_e2e.py` 含 6 用例：`test_layer4_recurrence_full_cycle`（resolved → regressed + severity 升级）/ `test_layer5_meta_rule_proposal_and_write`（5 cases → propose → 写 yaml status=pending）/ `test_dashboard_m5_overview_aggregates`（base_dir + counter → 完整 overview）/ `test_weekly_report_generation`（生成 reports/<year>-W<NN>.md 含 "Weekly Report" + "2026-W17"）/ `test_ab_channel_in_planning_evidence`（channel='A' 写到 stages[0]['channel']）/ `test_auto_case_proposes_pattern`（同 pattern 2 次 → CASE-LEARN-NNNN 写盘）
- [ ] `pytest tests/integration/test_m5_e2e.py -v --no-cov` 输出 6 passed
- [ ] 全量 pytest 全绿：`pytest -q --no-cov` ≥ 3700 + 50 passed / 0 failed / coverage ≥ 82%
- [ ] M5 全模块导入冒烟：`python3 -c "from ink_writer.regression_tracker import scan_evidence_chains, apply_recurrence; from ink_writer.meta_rule_emergence import find_similar_clusters, write_meta_rule_proposal; from ink_writer.dashboard.aggregator import compute_recurrence_rate; from ink_writer.dashboard.weekly_report import generate_weekly_report; from ink_writer.dashboard.m5_overview import get_m5_overview; from ink_writer.learn.auto_case import propose_cases_from_failures; from ink_writer.learn.promote import promote_short_term_to_long_term; print('M5 OK')"`
- [ ] regression_tracker CLI dry-run 跑通：`python3 -m ink_writer.regression_tracker` 退出 0 + 输出 JSON 含 `detected: N`
- [ ] meta_rule_emergence CLI 跑通：`python3 -m ink_writer.meta_rule_emergence` 退出 0 + 输出"提议数: N"
- [ ] 周报生成跑通：`python3 -c "from ink_writer.dashboard.weekly_report import generate_weekly_report; from pathlib import Path; out = generate_weekly_report(week_num=17, year=2026, out_path=Path('reports/weekly/2026-W17.md')); print(out)"` + `ls reports/weekly/2026-W17.md`
- [ ] 更新 `docs/superpowers/M-ROADMAP.md`：M5 行 ⚪→✅ + 加 PRD/plan/branch/日期；顶部 Status 行加 "M5 ✅ 完成 2026-04-25 — 5 周 100% 完成；下一步真实质量验证"
- [ ] 更新 `docs/superpowers/M-SESSION-HANDOFF.md`：§1 最后更新 "M5 完成后；5 周 roadmap 100% 完成"；§2 进度快照 M5 行 ⚪→✅ + 完成日期 + branch m5-final + commit count 13 US；"80% 进度" → "100% 进度（5/5 milestone 完成 + 1 partial）"；§3 重写为 M5 实际产出（13 US 实际 commit hash + 关键产物）；§7 改为 "下一步：真实质量验证（5 周 roadmap 之外）" 段，含 7 步流程（开新书 → 出大纲 → 写 30 章 → 投编辑评 → 看 dashboard → 回填 editor_reviews → 周报跟踪）
- [ ] tag + push：`git tag m5-final && git push origin master --tags`；校验 `git ls-remote --tags origin | grep m5-final`
- [ ] 所有 `open()` 带 `encoding='utf-8'`
- [ ] Typecheck passes
**Priority:** 13

## Functional Requirements

- FR-1: M5 必须不破坏 M3/M4 已交付的 5 章节 + 7 策划 checker / writer-self-check / rewrite_loop / chapter+planning evidence_chain（向后兼容）
- FR-2: case schema 加 3 字段必须使现有 410 个 case yaml 不强制 backfill 也能加载（缺字段 fallback 默认值）
- FR-3: Layer 4 仅同 book 内复发触发（spec §4 Q3 默认）
- FR-4: Layer 5 跳过 sovereign=True 的 case + 跳过已 meta_rule_id 的 case
- FR-5: meta_rule 升级路径必经用户审批（不自动升 P0）
- FR-6: dashboard 仅只读展示（不在面板编辑 case yaml；编辑走 ink case CLI）
- FR-7: A/B 通道默认关闭（enabled=false）；用户显式 `--channel A|B` 才生效；evidence_chain channel 字段缺为 None（向后兼容）
- FR-8: ink-learn `--auto-case-from-failure` 每周限 5 个 + 跳过 overall_passed=True 章节 + 跳过模式中所有 case 已存在的组合
- FR-9: ink-learn `--promote` 仅回灌 count ≥ min_occurrences 的 pattern；缺 project_memory.json 不抛错
- FR-10: 全部新增 Python 入口（main 函数 / `__main__`）调 `enable_windows_utf8_stdio()`
- FR-11: 全部 SKILL.md 新增段必须含 `<!-- windows-ps1-sibling -->` PowerShell 块（Windows 兼容守则）
- FR-12: 全部 LLM 调用走 `scripts/corpus_chunking/llm_client.LLMClient` wrapper（与 M3/M4 一致；model='glm-4.6'）

## Non-Goals

- 不补 M2 corpus_chunks（保持 deferred；M5 之外可选）
- 不动 M3 5 章节级 checker / M4 7 策划期 checker（M5 只读它们的 evidence_chain）
- 不打包"自动周报 cron"（用户自接 launchd / systemd）
- 不做"在 dashboard 直接编辑 case yaml"（只读展示）
- 不做"实时 LLM 元规则推断"（Layer 5 是手工/CLI 触发）
- 不做"A/B 通道随机分流"（配置驱动；用户显式选 channel）
- 不做"切换 dry-run 真阻断"按钮（仅推荐；用户手工改 yaml）
- 不做"复发申诉工作流"（编辑反馈手册简单说怎么标即可）
- 不做"跨 book 复发追踪"（M5 之外可选）
- 不做"更多 user_corpus 题材"（仅 history-travel 1 题材；用户自塞）
- 不做"真实测试书 30 章 + 投编辑评"（M5 之外的真实质量验证）

## Technical Considerations

- 复用 M1-M4 evidence_chain schema + thresholds_loader.py + LLMClient + case_library + dashboard 框架（不重建）
- `phase` 字段 + `channel` 字段默认值保证向后兼容现有 evidence_chain 文件
- planning_evidence_chain.json 多次写入合并 stages（先 ink-init 后 ink-plan）已是 M4 行为；M5 加 channel 透传到 stages
- LLM model 默认 glm-4.6（与 M3/M4 一致），调用量小不撞 RPM
- meta_rules 目录默认 `data/case_library/meta_rules/`（与 cases/ 平行）
- weekly_report 输出 `reports/weekly/<year>-W<NN>.md` ISO week 编号

## Success Metrics

- 每次 ink dashboard report --week N 必产 markdown 周报含 4 大指标 + 行动项
- M5 ✅ 后 5 周 roadmap **100% 完成**（5/5 milestone + 1 partial）
- 全量 pytest 3700+ → 3750+ 全绿，coverage ≥ 82%（与 M3/M4 baseline 持平或微升）
- 13 US 全部 commit + tag m5-final push 到 GitHub
- 真实质量验证（M5 之外）：编辑评分 30 → 60+（6 个月内验证；M5 ✅ 是结构闭环，验证靠跑测试书）

## Open Questions

- M2 corpus_chunks 实跑何时做？默认 5 周 roadmap 之外，等 M5 ✅ 后再决定
- meta_rule_emergence 的 cron 自动化是否需要？默认 M5 不做，看真实使用频率再加
- 真实测试书选哪个题材开第一本？默认 fantasy 或 sci-fi（M4 测试书已是仙侠）；用户决定
- 32 个 char_overused 字根模式是否够？M4 dry-run 跑过几次后回填扩充
