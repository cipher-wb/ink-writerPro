# PRD: M4 P0 上游策划层 — ink-init / ink-plan 阶段强制策划期审查

## Introduction

落地 spec §9 M4（详见 `docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md`）：在 ink-init / ink-plan 阶段强制走 4 + 3 = 7 个策划期 checker + 2 个数据资产（起点 top200 简介库 + LLM 高频起名词典 ≥ 250 条）+ 7 个上游 seed cases，每次开新书产出 `planning_evidence_chain.json`，把 spec §1.3 上游 5/8 扣分点（题材老套 / 金手指模糊 / AI 起名 / 主角动机牵强 / 金手指出场过晚 / 主角骨架级被动 / 章节钩子稀疏）阻断在策划期（**50 → 60+ 分质量拐点**）。

本期不做：M5 内容（dashboard / 自进化 / user_corpus）；不补 M2 chunks；不退役 FAISS；不动 M3 已建的 5 个章节级 checker；不做 P3 自进化。

详细 plan：`docs/superpowers/plans/2026-04-25-m4-p0-planning.md`（3937 行 / 14-task TDD）。

## Goals

- 每次开新书 ink-init / ink-plan 必走"7 个策划期 checker → 写 planning_evidence_chain.json"
- ink-init Step 99 跑 4 个 checker：genre-novelty / golden-finger-spec / naming-style / protagonist-motive
- ink-plan Step 99 跑 3 个 checker：golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density
- 阻断策略与 M3 一致（P0 阻断 / P1 警告需豁免 / P2-P3 提示）
- planning dry-run 5 次护栏（独立 `data/.planning_dry_run_counter`，与 M3 dry-run 不混淆）
- `--skip-planning-review` 紧急绕过（写 evidence_chain.warn 不阻塞用户开新书）
- 7 个上游 seed cases 入活（CASE-2026-M4-0001~0007）
- 复用 M3 evidence_chain schema + thresholds_loader + LLMClient + block_threshold_wrapper，全部不重建
- M3 chapter evidence_chain.json 向后兼容（`phase` 字段 fallback 为 `"writing"`）

## User Stories

### US-001: config/checker-thresholds.yaml 加 7 段 + planning_dry_run
**Description:** 作为开发者，我需要把 M4 7 个 checker 的阈值 + planning_dry_run 段加到 M3 已建的 `config/checker-thresholds.yaml`，让 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()` 在 ink-init / ink-plan Step 99 启动时读到。

**Acceptance Criteria:**
- [ ] `config/checker-thresholds.yaml` 末尾追加 8 段：`genre_novelty` (block 0.40 / warn 0.55 / case_ids [CASE-2026-M4-0001]) / `golden_finger_spec` (0.65/0.75/[0002]) / `naming_style` (0.70/0.85/[0003]) / `protagonist_motive` (0.65/0.75/[0004]) / `golden_finger_timing` (1.0/1.0/[0005] 硬阻断) / `protagonist_agency_skeleton` (0.55/0.70/[0006]) / `chapter_hook_density` (0.70/0.85/[0007]) / `planning_dry_run` (enabled true + observation_runs 5 + switch_to_block_after true + counter_path "data/.planning_dry_run_counter")
- [ ] M3 已有 8 段保持不变（`writer_self_check / reader_pull / sensory_immersion / high_point / conflict_skeleton / protagonist_agency / rewrite_loop / dry_run`）
- [ ] `pytest.ini` testpaths 行尾追加 `tests/checkers/genre_novelty tests/checkers/golden_finger_spec tests/checkers/naming_style tests/checkers/protagonist_motive tests/checkers/golden_finger_timing tests/checkers/protagonist_agency_skeleton tests/checkers/chapter_hook_density tests/planning_review tests/market_intelligence`（保持单行）
- [ ] `tests/checker_pipeline/test_thresholds_loader.py` 追加用例 `test_load_thresholds_includes_m4_sections` 校验 7 段都存在 + 关键值（`genre_novelty.block_threshold == 0.40`, `naming_style.block_threshold == 0.70`, `golden_finger_timing.block_threshold == 1.0`, `planning_dry_run.observation_runs == 5`）
- [ ] `pytest tests/checker_pipeline/test_thresholds_loader.py -v --no-cov` 全绿（M3 原用例 + 新用例）
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes
**Priority:** 1

### US-002: planning_evidence_chain.json schema + writer + 向后兼容
**Description:** 作为产线可观测性的 M4 扩展，我需要 `EvidenceChain` 加 `phase` + `stage` 字段 + 新建 `planning_writer.py` 暴露 `write_planning_evidence_chain` / `require_planning_evidence_chain` / `PlanningEvidenceChainMissingError`；M3 已写出的 chapter `evidence_chain.json` 不强制 backfill（loader 缺 phase 字段时 fallback 为 `"writing"`）。

**Acceptance Criteria:**
- [ ] 修改 `ink_writer/evidence_chain/models.py` 给 `EvidenceChain` 加 `phase: str = "writing"` + `stage: str | None = None`；`to_dict()` 输出新字段
- [ ] 新增 `ink_writer/evidence_chain/planning_writer.py` 暴露 `write_planning_evidence_chain(*, book, evidence, base_dir=None) -> Path` + `require_planning_evidence_chain(*, book, base_dir=None) -> dict` + `PlanningEvidenceChainMissingError`
- [ ] 写盘路径：`<base_dir>/<book>/planning_evidence_chain.json`（与 chapter `<book>/chapters/<chapter>.evidence.json` 不同目录）
- [ ] 文件已存在时合并 stages（先 ink-init 后 ink-plan 时，stages 列表追加新段；overall_passed = all(stages)）
- [ ] 文件不存在时新建：`{schema_version: "1.0", phase: "planning", book, stages: [...], overall_passed}`
- [ ] `evidence.phase != "planning"` 时 raise `ValueError("phase='planning'")`
- [ ] 修改 `ink_writer/evidence_chain/__init__.py` 导出新 API
- [ ] 新增 `tests/planning_review/__init__.py` + `tests/planning_review/conftest.py`（fixtures: `planning_base_dir`, `sample_planning_evidence_init`）+ `tests/planning_review/test_planning_writer.py` 含 4 用例：`test_write_creates_new_file` / `test_write_merges_ink_plan_after_ink_init` / `test_require_raises_when_missing` / `test_write_rejects_non_planning_phase`
- [ ] `pytest tests/planning_review/test_planning_writer.py -v --no-cov` 输出 4 passed
- [ ] `pytest tests/evidence_chain/ -v --no-cov` 全绿（M3 用例向后兼容）
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes
**Priority:** 2

### US-003: genre-novelty-checker
**Description:** 作为 ink-init 策划期 checker，我需要 `check_genre_novelty()` 用 LLM 把当前书的题材标签 + 主线一句话与起点 top200 逐条比对，取 top5 最相似 → score = 1.0 - max(sim)，block_threshold=0.40；空 top200 时 score=1.0 跳过；LLM 失败重试后仍失败 → blocked=True、notes="checker_failed"。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/genre_novelty/{__init__,models,checker}.py` + `prompts/check.txt`
- [ ] `GenreNoveltyReport` dataclass 字段：score / blocked / top5_similar (含 rank+title+similarity+reason) / cases_hit / notes
- [ ] prompt 含 `{genre_tags}` / `{main_plot_one_liner}` / `{top200_json}` 占位符；要求 JSON 数组输出 [{rank, similarity, reason}]
- [ ] `check_genre_novelty(*, genre_tags, main_plot_one_liner, top200, llm_client, block_threshold=0.40, model="glm-4.6", max_retries=2) -> GenreNoveltyReport`
- [ ] empty top200 → `score=1.0, blocked=False, notes="empty_top200_skipped"`，不调 LLM
- [ ] LLM JSON 解析含 markdown ``` 包裹去除；失败重试 max_retries 后仍失败 → `score=0.0, blocked=True, notes="checker_failed: <err>"`
- [ ] 新增 `tests/checkers/genre_novelty/__init__.py` + `test_checker.py` 含 4 用例：`test_high_similarity_blocks` / `test_low_similarity_passes` / `test_empty_top200_skipped` / `test_llm_failure_blocks`
- [ ] `pytest tests/checkers/genre_novelty/ -v --no-cov` 输出 4 passed
- [ ] 新增 `ink-writer/agents/genre-novelty-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 3

### US-004: golden-finger-spec-checker
**Description:** 作为 ink-init 策划期 checker，我需要 `check_golden_finger_spec()` LLM 4 维度评估金手指描述（clarity / falsifiability / boundary / growth_curve），算术平均 → score，block_threshold=0.65；description < 20 字直接 blocked=True、notes="description_too_short"；LLM 失败 fallback。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/golden_finger_spec/{__init__,models,checker}.py` + `prompts/check.txt`
- [ ] `GoldenFingerSpecReport` 字段：score / blocked / dim_scores (4 个 dim 各自 0-1) / cases_hit / notes
- [ ] prompt 含 `{description}` 占位符；要求 JSON 输出 4 个 dim 各 0-1 + notes
- [ ] `check_golden_finger_spec(*, description, llm_client, block_threshold=0.65, model="glm-4.6", max_retries=2) -> GoldenFingerSpecReport`
- [ ] description 缺失或 < 20 字 → blocked=True + notes="description_too_short"，不调 LLM
- [ ] score = mean(4 dim)；blocked = score < block_threshold
- [ ] LLM 失败重试后仍失败 → score=0.0、blocked=True、notes="checker_failed"
- [ ] 新增 `tests/checkers/golden_finger_spec/__init__.py` + `test_checker.py` 含 4 用例：`test_high_score_passes` / `test_low_score_blocks` / `test_short_description_blocks` / `test_llm_failure_blocks`
- [ ] `pytest tests/checkers/golden_finger_spec/ -v --no-cov` 输出 4 passed
- [ ] 新增 `ink-writer/agents/golden-finger-spec-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 4

### US-005: naming-style-checker
**Description:** 作为 ink-init 策划期 checker（**纯规则无 LLM**），我需要 `check_naming_style()` 用 `data/market_intelligence/llm_naming_blacklist.json` 词典对每个角色名打分：exact match → 0.0；双字模式（首字 + 末字都命中）→ 0.4；单字模式 → 0.7；clean → 1.0；多名取均值；block_threshold=0.70。词典缺失时直接 blocked=True、notes="blacklist_missing"。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/naming_style/{__init__,models,checker}.py`（无 prompts/ 目录，纯规则）
- [ ] `NamingStyleReport` 字段：score / blocked / per_name_scores (含 role+name+score+hit_type) / cases_hit / notes
- [ ] `check_naming_style(*, character_names, blacklist_path=None, block_threshold=0.70) -> NamingStyleReport`
- [ ] character_names = `[{role, name}, ...]`；为空 → score=1.0, blocked=False, notes="no_names"
- [ ] 词典 schema：`{exact_blacklist: [], char_patterns: {first_char_overused: [], second_char_overused: []}}`
- [ ] 默认 path = `data/market_intelligence/llm_naming_blacklist.json`；缺失 → blocked=True + notes 含 "blacklist_missing"
- [ ] `_score_one_name`: exact → (0.0, "exact")；双字 → (0.4, "double_char")；单字 → (0.7, "single_char")；clean → (1.0, "clean")
- [ ] score = mean(per_name_scores)；blocked = score < block_threshold
- [ ] 新增 `tests/checkers/naming_style/__init__.py` + `test_checker.py` 含 6 用例：`test_exact_match_zero` / `test_double_char_pattern` / `test_single_char_pattern` / `test_clean_name_passes` / `test_multiple_names_average` / `test_blacklist_missing_blocks`
- [ ] `pytest tests/checkers/naming_style/ -v --no-cov` 输出 6 passed
- [ ] 新增 `ink-writer/agents/naming-style-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 5

### US-006: protagonist-motive-checker
**Description:** 作为 ink-init 策划期 checker，我需要 `check_protagonist_motive()` LLM 3 维度评估主角动机（resonance / specific_goal / inner_conflict），算术平均 → score，block_threshold=0.65；description < 20 字直接 blocked=True；LLM 失败 fallback。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/protagonist_motive/{__init__,models,checker}.py` + `prompts/check.txt`
- [ ] `ProtagonistMotiveReport` 字段：score / blocked / dim_scores (3 个 dim 各 0-1) / cases_hit / notes
- [ ] prompt 含 `{description}` 占位符；要求 JSON 输出 3 个 dim 各 0-1 + notes
- [ ] `check_protagonist_motive(*, description, llm_client, block_threshold=0.65, model="glm-4.6", max_retries=2) -> ProtagonistMotiveReport`
- [ ] description 缺失或 < 20 字 → blocked=True + notes="description_too_short"
- [ ] score = mean(3 dim)；blocked = score < block_threshold
- [ ] LLM 失败重试后 → blocked=True + notes="checker_failed"
- [ ] 新增 `tests/checkers/protagonist_motive/__init__.py` + `test_checker.py` 含 4 用例：`test_high_score_passes` / `test_low_score_blocks` / `test_short_description_blocks` / `test_llm_failure_blocks`
- [ ] `pytest tests/checkers/protagonist_motive/ -v --no-cov` 输出 4 passed
- [ ] 新增 `ink-writer/agents/protagonist-motive-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 6

### US-007: 起点 top200 爬虫 + qidian_top200.jsonl
**Description:** 作为 genre-novelty-checker 的数据后端，我需要 `scripts/market_intelligence/fetch_qidian_top200.py` 爬虫脚本（合规：UA 礼貌 + robots.txt + 1 req/s 限速 + checkpoint 续爬 + max_retries 3），实跑后产出 `data/market_intelligence/qidian_top200.jsonl`（≥ 150 条；如反爬触发或 HTML 结构变只有少量 commit 空 jsonl + 标记需手动）。

**Acceptance Criteria:**
- [ ] 新增 `scripts/market_intelligence/__init__.py`（空）+ `scripts/market_intelligence/fetch_qidian_top200.py`
- [ ] 脚本带 `if __name__ == "__main__":` + `enable_windows_utf8_stdio()` 调用（CLAUDE.md Windows 兼容守则）
- [ ] argparse 支持 `--target N` (default 200)；UA = `"ink-writer/M4 (educational/non-commercial; contact: insectwb@gmail.com)"`
- [ ] `_check_robots_txt()` 起始检查 disallow 时 return 1 退出
- [ ] `_load_progress()` / `_save_progress_one(rank)` 用 `data/market_intelligence/.qidian_top200_progress` 持久化已抓 rank
- [ ] `_fetch_one_book(rank, book_id)` 解析 BeautifulSoup 提取 title/author/genre_tags/intro_one_liner/intro_full + max_retries 3 + 失败 return None
- [ ] `_fetch_rank_page()` 抓 10 页榜单 → [(rank, book_id), ...]；间隔 RATE_LIMIT_SECONDS = 1.0
- [ ] 输出 jsonl 每行 `{rank, title, author, url, genre_tags, intro_one_liner, intro_full, fetched_at}`
- [ ] 新增 `tests/market_intelligence/__init__.py` + `test_fetch_qidian_top200.py` 含 2 用例：`test_fetch_one_book_parses_html` (mock requests.get + 假 HTML) / `test_fetch_one_book_returns_none_after_retries` (mock side_effect RuntimeError)
- [ ] `pytest tests/market_intelligence/test_fetch_qidian_top200.py -v --no-cov` 输出 2 passed
- [ ] 真跑爬虫：`python -m scripts.market_intelligence.fetch_qidian_top200 --target 200`
- [ ] 实跑成功路径：`wc -l data/market_intelligence/qidian_top200.jsonl` ≥ 150；commit jsonl 一起 push
- [ ] 实跑失败路径（HTML 结构变 / 反爬）：commit 爬虫代码 + 空 jsonl + commit message 标 `[manual-fallback-needed]`，US-014 e2e 用 fixture top200 跑（不阻塞）
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes
**Priority:** 7

### US-008: LLM 高频起名词典 ≥ 250 条
**Description:** 作为 naming-style-checker 的数据后端，我需要 `data/market_intelligence/llm_naming_blacklist.json` 含 ≥ 250 条 exact_blacklist + 首字 ≥ 24 + 末字 ≥ 24 字根模式；手工汇总 + LLM 扩充（可选 `scripts/market_intelligence/expand_naming_blacklist.py`）。

**Acceptance Criteria:**
- [ ] 新增 `data/market_intelligence/llm_naming_blacklist.json` schema：`{version, updated_at, exact_blacklist: [...], char_patterns: {first_char_overused: [...], second_char_overused: [...]}, notes}`
- [ ] exact_blacklist 长度 ≥ 250（手工汇总 ≈ 100 条 + LLM 扩充 ≈ 150 条；至少含"叶凡 / 林夜 / 陈青山 / 李逍遥 / 沈墨 / 苏寒 / 顾寒 / 韩立 / 罗峰 / 秦尘 / 楚尘 / 白逸 / 王腾 / 唐三 / 萧炎 / 云澈 / 夜辰 / 风尘 / 凌天 / 墨尘 / 玄武 / 九天 / 易天 / 古辰"等）
- [ ] first_char_overused 长度 ≥ 24（含"叶 林 陈 李 沈 苏 顾 韩 罗 秦 楚 白 王 唐 萧 云 夜 风 凌 墨 玄 九 易 古"）
- [ ] second_char_overused 长度 ≥ 24（含"凡 辰 天 尘 轩 夜 墨 寒 风 炎 渊 宇 杰 豪 翔 腾 霖 瀚 霸 雷 煜 燃 铮 翊"）
- [ ] exact_blacklist 内无重复
- [ ] 全部条目均为中文字符
- [ ] 新增 `tests/market_intelligence/test_naming_blacklist.py` 含 3 用例：`test_blacklist_schema` (≥ 100 + ≥ 20 + ≥ 20) / `test_blacklist_no_duplicates` / `test_blacklist_chinese_only`
- [ ] `pytest tests/market_intelligence/test_naming_blacklist.py -v --no-cov` 输出 3 passed
- [ ] 验证 naming-style-checker 用真词典跑通："叶凡" → score=0.0, blocked=True, hit_type="exact"
- [ ] Typecheck passes
**Priority:** 8

### US-009: golden-finger-timing-checker
**Description:** 作为 ink-plan 策划期 checker，我需要 `check_golden_finger_timing()` 用 regex 主 + LLM 回退判断金手指是否在前 3 章 summary 出现：regex 命中即通过（不调 LLM）；regex miss 时调 LLM 二次判断；硬阻断 block_threshold=1.0（passed→1.0 / failed→0.0）。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/golden_finger_timing/{__init__,models,checker}.py` + `prompts/check.txt`
- [ ] `GoldenFingerTimingReport` 字段：score / blocked / regex_match (bool) / llm_match (bool | None) / matched_chapter (int | None) / cases_hit / notes
- [ ] prompt 含 `{keywords}` / `{summaries_text}` 占位符；要求 JSON 输出 `{matched, matched_chapter, reason}`
- [ ] `check_golden_finger_timing(*, outline_volume_skeleton, golden_finger_keywords, llm_client, block_threshold=1.0, model="glm-4.6", max_retries=2) -> GoldenFingerTimingReport`
- [ ] outline_volume_skeleton = `[{chapter_idx, summary}, ...]`；不足 3 章 → blocked=True + notes="outline_too_short: <n> < 3"
- [ ] keywords 为空 → blocked=True + notes="empty_keywords"
- [ ] regex 用 `re.escape(kw)` 拼 OR 模式扫前 3 章 summary；命中 → 直通 score=1.0, blocked=False, regex_match=True, llm_match=None
- [ ] regex miss → 调 LLM；matched=True → score=1.0, blocked=False, regex_match=False, llm_match=True；matched=False → score=0.0, blocked=True
- [ ] LLM 失败重试后 → score=0.0, blocked=True, notes="checker_failed"
- [ ] 新增 `tests/checkers/golden_finger_timing/__init__.py` + `test_checker.py` 含 5 用例：`test_regex_hit_passes` / `test_regex_miss_llm_hit_passes` / `test_regex_miss_llm_miss_blocks` / `test_outline_too_short_blocks` / `test_empty_keywords_blocks`
- [ ] `pytest tests/checkers/golden_finger_timing/ -v --no-cov` 输出 5 passed
- [ ] 新增 `ink-writer/agents/golden-finger-timing-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 9

### US-010: protagonist-agency-skeleton-checker
**Description:** 作为 ink-plan 策划期 checker（**卷骨架级**，与 M3 章节级 protagonist-agency 不同），我需要 `check_protagonist_agency_skeleton()` LLM 对每章 summary 打 agency_score 0-1，平均 → score，block_threshold=0.55；空 skeleton → blocked=True；LLM 失败 fallback。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/protagonist_agency_skeleton/{__init__,models,checker}.py` + `prompts/check.txt`
- [ ] `ProtagonistAgencySkeletonReport` 字段：score / blocked / per_chapter (含 chapter_idx+agency_score+reason) / cases_hit / notes
- [ ] prompt 含 `{summaries_text}` 占位符；要求 JSON 数组 [{chapter_idx, agency_score, reason}]
- [ ] `check_protagonist_agency_skeleton(*, outline_volume_skeleton, llm_client, block_threshold=0.55, model="glm-4.6", max_retries=2) -> ProtagonistAgencySkeletonReport`
- [ ] empty skeleton → blocked=True + notes="empty_skeleton"，不调 LLM
- [ ] score = mean(per_chapter agency_score)；blocked = score < block_threshold
- [ ] LLM 失败重试后 → blocked=True + notes="checker_failed"
- [ ] 新增 `tests/checkers/protagonist_agency_skeleton/__init__.py` + `test_checker.py` 含 4 用例：`test_high_agency_passes` / `test_low_agency_blocks` / `test_empty_skeleton_blocks` / `test_llm_failure_blocks`
- [ ] `pytest tests/checkers/protagonist_agency_skeleton/ -v --no-cov` 输出 4 passed
- [ ] 新增 `ink-writer/agents/protagonist-agency-skeleton-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 10

### US-011: chapter-hook-density-checker
**Description:** 作为 ink-plan 策划期 checker（卷骨架级），我需要 `check_chapter_hook_density()` LLM 对每章 summary 打 hook_strength 0-1，density = strong_count / total_count（strong threshold = 0.5），block_threshold=0.70；空 skeleton → blocked=True。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/checkers/chapter_hook_density/{__init__,models,checker}.py` + `prompts/check.txt`
- [ ] `ChapterHookDensityReport` 字段：score / blocked / per_chapter (含 chapter_idx+hook_strength+strong+reason) / strong_count / total_count / cases_hit / notes
- [ ] prompt 含 `{summaries_text}` 占位符；要求 JSON 数组 [{chapter_idx, hook_strength, reason}]
- [ ] `check_chapter_hook_density(*, outline_volume_skeleton, llm_client, block_threshold=0.70, model="glm-4.6", max_retries=2) -> ChapterHookDensityReport`
- [ ] strong threshold = 0.5；strong if hook_strength >= 0.5
- [ ] score = strong_count / total_count；blocked = score < block_threshold
- [ ] empty skeleton → blocked=True + notes="empty_skeleton"
- [ ] LLM 失败重试后 → blocked=True + notes="checker_failed"
- [ ] 新增 `tests/checkers/chapter_hook_density/__init__.py` + `test_checker.py` 含 4 用例：`test_high_density_passes` / `test_low_density_blocks` / `test_empty_skeleton_blocks` / `test_llm_failure_blocks`
- [ ] `pytest tests/checkers/chapter_hook_density/ -v --no-cov` 输出 4 passed
- [ ] 新增 `ink-writer/agents/chapter-hook-density-checker.md` agent spec
- [ ] Typecheck passes
**Priority:** 11

### US-012: planning_review 编排层 + ink-init/ink-plan SKILL.md Step 99
**Description:** 作为 M4 集成层，我需要 `ink_writer/planning_review/{ink_init_review, ink_plan_review, dry_run, dry_run_report}.py` 编排 4+3 checker 串行 + 写 evidence_chain + 独立 `data/.planning_dry_run_counter` + `--skip-planning-review` flag；同时 `ink-writer/skills/ink-init/SKILL.md` + `ink-writer/skills/ink-plan/SKILL.md` 末尾追加 Step 99 章节（含 PowerShell sibling 块满足 Windows 兼容守则）。

**Acceptance Criteria:**
- [ ] 新增 `ink_writer/planning_review/__init__.py` 导出主入口
- [ ] 新增 `ink_writer/planning_review/dry_run.py` 暴露 `get_counter / increment_counter / is_dry_run_active`；默认路径 `Path("data/.planning_dry_run_counter")`
- [ ] 新增 `ink_writer/planning_review/ink_init_review.py` 暴露 `run_ink_init_review(*, book, setting, llm_client, base_dir=None, skip=False, dry_run_counter_path=None) -> dict`
- [ ] ink-init 4 checker 串行：genre-novelty (含 `_load_top200()` 读 jsonl，缺则 [])、golden-finger-spec、naming-style、protagonist-motive
- [ ] 阻断逻辑：`effective_blocked = blocked_any and not dry_run`；写 evidence (phase=planning, stage=ink-init)
- [ ] skip=True 路径：写 evidence 含 `skipped=True, skip_reason="--skip-planning-review"` 不调任何 checker
- [ ] cases_hit 注入：blocked 时把 config 里 case_ids 注入到该 checker 报告
- [ ] CLI: `python -m ink_writer.planning_review.ink_init_review --book X --setting path.json [--skip-planning-review]` 退出码 1 if blocked else 0；带 `enable_windows_utf8_stdio()`
- [ ] 新增 `ink_writer/planning_review/ink_plan_review.py` 暴露 `run_ink_plan_review(*, book, outline, llm_client, ...)`；3 checker 串行（golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density）；CLI 同上
- [ ] outline schema：`{volume_skeleton: [{chapter_idx, summary}, ...], golden_finger_keywords: [...]}`
- [ ] 新增 `ink_writer/planning_review/dry_run_report.py` 暴露 `generate_planning_dry_run_report(*, base_dir="data") -> str` 聚合所有 book 的 planning_evidence_chain.json 输出 markdown：每 checker 平均分 + case 触发频次 + per-stage rows；带 `if __name__ == "__main__":`
- [ ] `ink-writer/skills/ink-init/SKILL.md` 末尾追加 `## Step 99：策划期审查（M4 P0 必跑）` 章节，含 macOS/Linux 命令 + Windows PowerShell sibling + dry-run/real 模式说明 + skip flag 说明 + 5 次后聚合报告命令
- [ ] `ink-writer/skills/ink-plan/SKILL.md` 同样追加 Step 99（替换 ink_init_review → ink_plan_review、--setting → --outline、checker 列表）
- [ ] M3 已有 SKILL.md 前段保持不变
- [ ] 新增 `tests/planning_review/test_dry_run.py` 含 3 用例：`test_counter_starts_at_zero` / `test_increment` / `test_dry_run_active_until_threshold`
- [ ] 新增 `tests/planning_review/test_ink_init_review.py` 含 5 用例：`test_skip_flag` / `test_dry_run_blocked_does_not_fail` / `test_real_mode_blocks_on_failure` / `test_all_pass_real_mode` / `test_evidence_chain_written`
- [ ] 新增 `tests/planning_review/test_ink_plan_review.py` 含 4 用例：`test_skip_flag` / `test_evidence_merges_after_init` / `test_low_agency_blocks_in_real_mode` / `test_empty_outline_blocks`
- [ ] `pytest tests/planning_review/ -v --no-cov` 输出 12 passed (3+5+4)
- [ ] `grep -c "Step 99" ink-writer/skills/ink-init/SKILL.md` ≥ 1；同 ink-plan
- [ ] `grep -c "skip-planning-review" ink-writer/skills/ink-init/SKILL.md` ≥ 1
- [ ] `grep -c "PowerShell" ink-writer/skills/ink-init/SKILL.md` ≥ 1
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes
**Priority:** 12

### US-013: 7 个 CASE-2026-M4-* seed cases + batch approve
**Description:** 作为 M4 阻断的真相源，我需要 7 个上游种子 case（CASE-2026-M4-0001~0007 各对应 1 个 checker）+ `ink case approve --batch` 批量入活；schema 与现有 case 对齐（参考 `data/case_library/cases/CASE-2026-0001.yaml`）。

**Acceptance Criteria:**
- [ ] 新增 7 个 yaml `data/case_library/cases/CASE-2026-M4-{0001..0007}.yaml`：
  - 0001 题材老套（tags: genre_novelty, market_intelligence；severity: hard；status: pending）
  - 0002 金手指模糊（tags: golden_finger_spec）
  - 0003 主角名 AI 味重（tags: naming_style）
  - 0004 主角动机牵强（tags: protagonist_motive）
  - 0005 金手指出场过晚（tags: golden_finger_timing, opening_hook）
  - 0006 大纲主角骨架级被动（tags: protagonist_agency_skeleton）
  - 0007 大纲钩子密度低（tags: chapter_hook_density）
- [ ] 每个 yaml 含字段：`id / title / severity (hard) / status (pending) / category / tags / failure_pattern.{description, observable, examples} / countermeasure.guideline / source.{type=editor_review, notes=M4 spec §1.3 引用} / created_at: '2026-04-25'`
- [ ] yaml 通过 `yaml.safe_load` 解析校验：`d['id'] == p.stem` + `d['severity'] in {hard, soft, info}` + `d['status'] == 'pending'`
- [ ] 跑 batch approve：`ink case approve --batch CASE-2026-M4-0001 ... CASE-2026-M4-0007`（或等效 `python3 -m ink_writer.case_library.cli approve --batch ...`）
- [ ] 校验 7 个 case 已 active：`from ink_writer.case_library.store import CaseStore; s = CaseStore(); m4 = [c for c in s.iter_active() if c.id.startswith('CASE-2026-M4')]; assert len(m4) == 7`
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes
**Priority:** 13

### US-014: M4 e2e 测试 + 跑测试书 + tag m4-p0-planning + ROADMAP/handoff 更新
**Description:** 作为 M4 验收，我需要 `tests/integration/test_m4_e2e.py` 7 用例覆盖 spec §10 验收清单 + 跑一本测试书 ink-init + ink-plan 真链路产 planning_evidence_chain.json + 全量 pytest 全绿 + tag `m4-p0-planning` push 到 origin + 更新 docs/superpowers/M-ROADMAP.md M4 行 ✅ + 更新 docs/superpowers/M-SESSION-HANDOFF.md §2/§3。

**Acceptance Criteria:**
- [ ] 新增 `tests/integration/test_m4_e2e.py` 含 7 用例：`test_thresholds_yaml_has_m4_sections` / `test_ink_init_e2e_success` / `test_ink_plan_e2e_success` / `test_ink_init_then_ink_plan_merges` / `test_skip_flag_writes_evidence_with_skipped_true` / `test_dry_run_counter_increments` / `test_seven_seed_cases_active`
- [ ] `pytest tests/integration/test_m4_e2e.py -v --no-cov` 输出 7 passed
- [ ] 全量 pytest 全绿：`pytest -q` ≥ 3700 + 30 passed / 0 failed / coverage ≥ 82%
- [ ] M4 全模块导入冒烟：`python3 -c "from ink_writer.planning_review import ink_init_review, ink_plan_review; from ink_writer.checkers.{genre_novelty,golden_finger_spec,naming_style,protagonist_motive,golden_finger_timing,protagonist_agency_skeleton,chapter_hook_density} import *; print('M4 OK')"`
- [ ] 跑测试书 ink-init：`mkdir -p data/test-book-m4`；写 `data/test-book-m4/setting.json`（顾望安 + 万道归一金手指 + 蓝漪 + 裴惊戎 + 战争遗孤动机 ≥ 200 字）；`python3 -m ink_writer.planning_review.ink_init_review --book test-book-m4 --setting data/test-book-m4/setting.json` 返回 0
- [ ] 跑测试书 ink-plan：写 `data/test-book-m4/outline.json`（5 章 skeleton，前 3 章含"万道归一/融合"关键词，主角主动语态）；`python3 -m ink_writer.planning_review.ink_plan_review --book test-book-m4 --outline data/test-book-m4/outline.json` 返回 0
- [ ] 校验 evidence_chain：`data/test-book-m4/planning_evidence_chain.json` 存在；`phase==planning`；`{s['stage'] for s in stages} == {ink-init, ink-plan}`；total_checkers == 7 (4+3)
- [ ] 数据资产校验：`wc -l data/market_intelligence/qidian_top200.jsonl`（如 US-007 实跑成功 ≥ 150；如 manual-fallback 则该项标 deferred）；`len(blacklist['exact_blacklist']) >= 250`；`ls data/case_library/cases/CASE-2026-M4-*.yaml | wc -l == 7`
- [ ] 7 个 agent.md 全在：`ls ink-writer/agents/{genre-novelty,golden-finger-spec,naming-style,protagonist-motive,golden-finger-timing,protagonist-agency-skeleton,chapter-hook-density}-checker.md`
- [ ] SKILL.md 检查：`grep -c "Step 99" ink-writer/skills/ink-init/SKILL.md` ≥ 1；同 ink-plan；`grep -c "skip-planning-review" ink-writer/skills/ink-init/SKILL.md` ≥ 1；`grep -c "PowerShell" ink-writer/skills/ink-init/SKILL.md` ≥ 1
- [ ] 更新 `docs/superpowers/M-ROADMAP.md`：M4 行 ⚪→✅ + 加 PRD/plan/branch/日期；顶部 Status 行加 "M4 ✅ 完成 2026-04-25 — ink-init/ink-plan 强制策划期审查全链路落档；下一步开 M5"
- [ ] 更新 `docs/superpowers/M-SESSION-HANDOFF.md`：§2 进度快照 M4 行 ⚪→✅ + 完成日期 2026-04-25 + branch m4-p0-planning + commit count 14 US；"60% 进度" → "80% 进度（4/5 milestone 完成 + 1 partial）"；§3 重写为 M4 实际产出（14 US 实际 commit hash + 关键产物列表）；§7 改为 "M5 brainstorm 准备" 段
- [ ] tag + push：`git tag m4-p0-planning && git push origin master --tags`；校验 `git ls-remote --tags origin | grep m4-p0-planning`
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] Typecheck passes
**Priority:** 14

## Functional Requirements

- FR-1: M4 必须不破坏 M3 已交付的 5 个章节级 checker / writer-self-check / rewrite_loop / chapter evidence_chain（向后兼容）
- FR-2: ink-init Step 99 跑 4 个 checker（genre-novelty / golden-finger-spec / naming-style / protagonist-motive），任一阻断需写入 evidence_chain.warn 或终止
- FR-3: ink-plan Step 99 跑 3 个 checker（golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density），同上
- FR-4: planning_dry_run 与 M3 dry_run 完全独立（独立 counter_path / 独立配置段）
- FR-5: `--skip-planning-review` 必须写入 `evidence_chain.skipped=true / skip_reason` 让 review 阶段可见绕过痕迹（不静默放过）
- FR-6: `data/<book>/planning_evidence_chain.json` 多次写入合并 stages（ink-init + ink-plan），不覆盖
- FR-7: M3 chapter `evidence_chain.json` 缺 phase 字段时 loader fallback 为 `"writing"`，不报错
- FR-8: 7 个 checker 阻断时必须把 config 里 case_ids 注入到 cases_hit 字段
- FR-9: 全部 LLM 调用走 `scripts/corpus_chunking/llm_client.LLMClient` wrapper（与 M3 一致）
- FR-10: 全部新增 Python 入口（main 函数 / `__main__`）调 `enable_windows_utf8_stdio()`
- FR-11: 全部新增 `.sh` 必须同时提供 `.ps1`（UTF-8 BOM）+ `.cmd` 双击包装；SKILL.md 引用 `.sh` 必带 PowerShell sibling 块
- FR-12: 起点爬虫遵守 robots.txt + UA 礼貌（含 contact email）+ 1 req/s 限速 + checkpoint 续爬

## Non-Goals

- 不补 M2 corpus_chunks（保持 deferred 状态）
- 不动 M3 5 个章节级 checker
- 不动 ink-write 阶段任何流程
- 不做 P3 自进化 / dashboard / user_corpus → M5
- 不退役 FAISS
- 不打包"M4 一次跑全 7 checker 的 CLI"（直接走 SKILL.md Step 99 调用即可）
- 不建立"上游 cases 持续扩充流水线"（与下游 case 库共享 ingest_case 工具）
- 不做"naming-style-checker 的中文姓名重复率统计"（hash 太慢，依赖 dry-run 阶段调阈值）
- 不做"interactive review 体验优化"（M5 dashboard 配套）

## Technical Considerations

- 复用 M3 evidence_chain schema + thresholds_loader.py + LLMClient + block_threshold_wrapper（不重建）
- 新增 `phase` 字段默认值 `"writing"` 保证 M3 chapter 文件向后兼容
- planning_evidence_chain.json 与 chapter `<chapter>.evidence.json` 不同目录（前者在 `<book>/planning_evidence_chain.json`）
- LLM model 默认 glm-4.6（与 M3 一致），调用量小不撞 RPM
- 起点爬虫如 HTML 结构变化导致解析失败：单条跳过 + 进度持续；总数低于 100 时 commit 空 jsonl + manual-fallback 标记

## Success Metrics

- 每次开新书 ink-init / ink-plan 必产 `planning_evidence_chain.json`
- 7 个上游扣分点（spec §1.3）至少 5 个被 M4 阻断在策划期（dry-run 阶段触发样本验证）
- 编辑评分 50 → 60+（与 M3 30→50 拐点接力，6 个月内验证）
- 全量 pytest 3700+ → 3730+ 全绿，coverage ≥ 82%（与 M3 baseline 持平或微升）

## Open Questions

- 起点 top200 实跑如反爬触发，是否切 plan B（用 reference_corpus 30 本简介代替）？默认 commit 空 jsonl + manual-fallback 让用户后补
- LLM 高频起名词典扩充至 ≥ 250 条不足时是否阻塞 US-014？默认 yaml 校验 ≥ 100 条即放行（ralph 期接受手工补完）
- M5 是否需要把 phase 字段也加到 chapter evidence_chain（强制 backfill 现有文件）？默认 M4 不强制（loader fallback 已兼容）
