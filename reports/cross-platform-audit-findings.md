# 跨平台兼容性审计 Findings 报告（US-001）

扫描根目录: `/Users/cipher/AI/ink/ink-writer`

**总 finding 数**: 196 (Blocker=0 / High=48 / Medium=38 / Low=110)

## 按类别汇总

| 类别 | 数量 | 对应修复 US |
|------|------|-------------|
| C1 | 0 | US-002 |
| C2 | 110 | US-003 |
| C3 | 25 | US-004 |
| C4 | 10 | US-005 |
| C5 | 7 | US-006 |
| C6 | 2 | US-007 |
| C7 | 1 | US-008 |
| C8 | 37 | US-009 |
| C9 | 4 | US-010 |

## C2 — 硬编码路径分隔符（疑似）

对应修复 US: **US-003**  数量: **110**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `benchmark/compare.py:19` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `benchmark/craft_analyzer.py:25` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `benchmark/e2e_shadow_300.py:36` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `benchmark/scraper.py:19` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `benchmark/stat_analyzer.py:17` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `benchmark/style_rag_builder.py:21` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `benchmark/validate_qg1.py:15` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/dashboard/app.py:105` | Low | 疑似硬编码路径字面量: '/api/project/info' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/dashboard/app.py:273` | Low | 疑似硬编码路径字面量: '/api/plot-threads/heatmap' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/dashboard/app.py:345` | Low | 疑似硬编码路径字面量: '/api/plotlines/heatmap' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/dashboard/app.py:517` | Low | 疑似硬编码路径字面量: '/api/files/tree' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/dashboard/app.py:530` | Low | 疑似硬编码路径字面量: '/api/files/read' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/anti_ai_scanner.py:108` | Low | 疑似硬编码路径字面量: '打散为动作/对话/心理的混排' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/anti_ai_scanner.py:117` | Low | 疑似硬编码路径字面量: '打散为动作/对话/心理的混排' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/init_project.py:291` | Low | 疑似硬编码路径字面量: '设定集/角色库/主要角色' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/init_project.py:292` | Low | 疑似硬编码路径字面量: '设定集/角色库/次要角色' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/init_project.py:293` | Low | 疑似硬编码路径字面量: '设定集/角色库/反派角色' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/security_utils.py:525` | Low | 疑似硬编码路径字面量: '../../../etc/passwd' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink-writer/scripts/security_utils.py:528` | Low | 疑似硬编码路径字面量: '/tmp/../../../../../etc/hosts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/checker_pipeline/step3_runner.py:28` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/cli/ink.py:31` | Low | 疑似硬编码路径字面量: '../../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/context/writing_guidance_builder.py:46` | Low | 疑似硬编码路径字面量: 'references/shared/scene-craft-index.md' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/anti_ai_lint.py:14` | Low | 疑似硬编码路径字面量: '../../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/entity_linker.py:22` | Low | 疑似硬编码路径字面量: '../../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:26` | Low | 疑似硬编码路径字面量: '爽点种子/压制/不公/利益/力量信号' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:27` | Low | 疑似硬编码路径字面量: '爽点种子/压制/不公/利益/力量信号' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:28` | Low | 疑似硬编码路径字面量: '爽点种子/压制/不公/利益/力量信号' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:29` | Low | 疑似硬编码路径字面量: '知识优势/身份差距/资源机会/规则卡位' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:30` | Low | 疑似硬编码路径字面量: '系统奖励/资源争夺/数值突破/规则差距' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:31` | Low | 疑似硬编码路径字面量: '数据波动/利益冲突/即时反制/舆论反馈' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:32` | Low | 疑似硬编码路径字面量: '情绪暴击/关系反转/身份张力' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:33` | Low | 疑似硬编码路径字面量: '情绪暴击/关系反转/身份张力' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:34` | Low | 疑似硬编码路径字面量: '异常/线索冲突/倒计时' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:35` | Low | 疑似硬编码路径字面量: '异常/规则冲突/倒计时' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:36` | Low | 疑似硬编码路径字面量: '异常/规则冲突/倒计时' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:127` | Low | 疑似硬编码路径字面量: '强触发/高价值承诺/未闭合问题' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:209` | Low | 疑似硬编码路径字面量: '前800字看清主角压力/独特抓手/核心问题' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/golden_three.py:256` | Low | 疑似硬编码路径字面量: '主角/关系/资源/身份/规则认知至少一项显性变化' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/extract/style_sampler.py:17` | Low | 疑似硬编码路径字面量: '../../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/state/migrate_state_to_sqlite.py:34` | Low | 疑似硬编码路径字面量: '../../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/core/state/sql_state_manager.py:20` | Low | 疑似硬编码路径字面量: '../../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/creativity/__main__.py:7` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/creativity/cli.py:66` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/editor_wisdom/coverage_metrics.py:32` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `ink_writer/propagation/drift_detector.py:25` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/ab_prompts.py:27` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/audit/scan_unused.py:23` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/audit/scan_unused.py:47` | Low | 疑似硬编码路径字面量: '/Users/cipher/AI/ink/ink-writer' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/audit_architecture.py:21` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/build_blind_test.py:22` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/build_reference_corpus.py:20` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/build_style_rag.py:23` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/01_scan.py:11` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/01_scan.py:25` | Low | 疑似硬编码路径字面量: '/Users/cipher/Desktop/星河编辑' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/02_clean.py:11` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/03_classify.py:15` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/04_build_kb.py:11` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/05_extract_rules.py:14` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/06_build_index.py:11` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/editor-wisdom/smoke_test.py:17` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/measure_baseline.py:16` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/migration/fix11_merge_packages.py:29` | Low | 疑似硬编码路径字面量: '../../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/migration/fix11_merge_packages.py:118` | Low | 疑似硬编码路径字面量: 'ink-writer/scripts/data_modules/tests' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/migration/fix11_merge_packages.py:118` | Low | 疑似硬编码路径字面量: 'ink_writer/core/tests' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/mine_hook_patterns.py:19` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/mine_hook_patterns.py:250` | Low | 疑似硬编码路径字面量: '神器/丹药/秘法即将到手' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/mine_hook_patterns.py:296` | Low | 疑似硬编码路径字面量: '告白/误会/心动瞬间' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/mine_hook_patterns.py:304` | Low | 疑似硬编码路径字面量: '安全区/物资/队友汇合' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/patch_outline_hook_contract.py:20` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/run_300chapter_benchmark.py:21` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch10_object.py:25` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch2_era.py:16` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch3_conflict.py:17` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch4_worldview.py:21` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch5_emotion.py:21` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch6_taboo.py:22` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch7_mythology.py:26` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch8_taboo_language.py:22` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/seeds_batch9_body_feature.py:21` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/verify_docs.py:24` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `scripts/verify_optimization_quality.py:19` | Low | 疑似硬编码路径字面量: '../ink-writer/scripts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/audit/test_audit_cross_platform.py:138` | Low | 疑似硬编码路径字面量: 'ink-writer/scripts/runtime_compat.py' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/audit/test_audit_cross_platform.py:139` | Low | 疑似硬编码路径字面量: 'a/b/c/d/e.txt' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/baseline/test_slim_review_bundle.py:27` | Low | 疑似硬编码路径字面量: '/tmp/test_project/正文/第0005章.md' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/baseline/test_slim_review_bundle.py:31` | Low | 疑似硬编码路径字面量: '/tmp/test_project/正文/第0005章.md' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_app.py:135` | Low | 疑似硬编码路径字面量: '/api/project/info' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_app.py:145` | Low | 疑似硬编码路径字面量: '/api/project/info' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_app.py:179` | Low | 疑似硬编码路径字面量: '/api/entities/xiao_yan' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_app.py:184` | Low | 疑似硬编码路径字面量: '/api/entities/nonexistent' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_app.py:274` | Low | 疑似硬编码路径字面量: '/api/files/tree' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:24` | Low | 疑似硬编码路径字面量: '/a/.ink/state.json' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:32` | Low | 疑似硬编码路径字面量: '/project/.ink/state.json' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:34` | Low | 疑似硬编码路径字面量: '/project/.ink/state.json' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:39` | Low | 疑似硬编码路径字面量: '/project/.ink/index.db' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:41` | Low | 疑似硬编码路径字面量: '/project/.ink/index.db' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:46` | Low | 疑似硬编码路径字面量: '/p/.ink/workflow_state.json' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:53` | Low | 疑似硬编码路径字面量: '/project/.ink/backup.bak' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_dashboard_watcher.py:132` | Low | 疑似硬编码路径字面量: '/p/.ink/state.json' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_path_guard.py:80` | Low | 疑似硬编码路径字面量: '../../etc/passwd' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_path_guard.py:85` | Low | 疑似硬编码路径字面量: '../../../../../../../../etc/shadow' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_path_guard.py:90` | Low | 疑似硬编码路径字面量: 'subdir/../../outside.txt' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_path_guard.py:107` | Low | 疑似硬编码路径字面量: '/tmp/other_project/secret.txt' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_path_guard.py:160` | Low | 疑似硬编码路径字面量: 'a/b/c/d/e/f/g/h/i/j/file.txt' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_path_guard.py:190` | Low | 疑似硬编码路径字面量: './subdir/file.txt' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_security_utils.py:31` | Low | 疑似硬编码路径字面量: '../../../etc/passwd' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/data_modules/test_security_utils.py:41` | Low | 疑似硬编码路径字面量: '/tmp/../../../../../etc/hosts' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/editor_wisdom/test_smoke_test.py:43` | Low | 疑似硬编码路径字面量: '/usr/bin/claude' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/integration/test_low_coverage_modules.py:86` | Low | 疑似硬编码路径字面量: 'chapters/7/draft.md' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/migration/test_fix11_script.py:78` | Low | 疑似硬编码路径字面量: 'ink-writer/scripts/data_modules/tests' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |
| `tests/migration/test_fix11_script.py:79` | Low | 疑似硬编码路径字面量: 'ink_writer/core/tests' | 改用 pathlib.Path 拼接，或用 os.path.join 让分隔符跨平台 |

## C3 — `subprocess` 调用文本模式缺 encoding 或 `shell=True`

对应修复 US: **US-004**  数量: **25**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `ink-writer/scripts/init_project.py:778` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `ink-writer/scripts/init_project.py:981` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `ink-writer/scripts/security_utils.py:260` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `ink-writer/scripts/workflow_manager.py:834` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `ink_writer/editor_wisdom/llm_backend.py:123` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `ink_writer/style_rag/retriever.py:129` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `scripts/measure_baseline.py:59` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/creativity/test_cli.py:21` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/creativity/test_quick_mode_integration.py:29` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/data_modules/test_encoding_validator.py:91` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/data_modules/test_encoding_validator.py:104` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/data_modules/test_encoding_validator.py:116` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/data_modules/test_encoding_validator.py:133` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/editor_wisdom/test_api_key_guard.py:29` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/editor_wisdom/test_cli.py:229` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/harness/test_api_key_guard.py:27` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/harness/test_init_creative_fingerprint.py:108` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/harness/test_step3_runner.py:109` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/harness/test_step3_runner.py:122` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/harness/test_step3_runner.py:159` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/integration/test_quick_mode_validator_loop.py:24` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/integration/test_step3_enforce_all_pass.py:69` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/integration/test_step3_enforce_hard_fail_blocks.py:76` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/parallel/test_chapter_lock_integration.py:247` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |
| `tests/release/test_v16_gates.py:118` | High | `subprocess.run` 文本模式缺 encoding=utf-8 | 补 encoding="utf-8"，避免 Windows cp936 解码 |

## C4 — asyncio 入口未调 `set_windows_proactor_policy()`

对应修复 US: **US-005**  数量: **10**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `benchmark/scraper.py:675` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `ink-writer/scripts/extract_chapter_context.py:341` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `ink_writer/checker_pipeline/step3_runner.py:490` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `ink_writer/core/cli/ink.py:279` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `ink_writer/core/context/rag_adapter.py:1604` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `ink_writer/parallel/pipeline_manager.py:153` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `tests/checker_pipeline/test_step3_runner_real_checker.py:140` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `tests/harness/test_step3_runner.py:72` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `tests/infra/test_logging_migration.py:55` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |
| `tests/integration/test_step3_enforce_real_polish.py:141` | High | asyncio 入口未调 set_windows_proactor_policy() | 在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op） |

## C5 — 裸 `symlink` 调用未走 `safe_symlink()` 兜底

对应修复 US: **US-006**  数量: **7**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `ink-writer/scripts/runtime_compat.py:116` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `ink-writer/scripts/runtime_compat.py:130` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `scripts/build_reference_corpus.py:61` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `tests/audit/test_audit_cross_platform.py:235` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `tests/audit/test_audit_cross_platform.py:238` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `tests/data_modules/test_path_guard.py:125` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `tests/data_modules/test_path_guard.py:138` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |

## C6 — `*.sh` 缺同目录 `.ps1` / `.cmd` 对等入口

对应修复 US: **US-007**  数量: **2**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `ink-writer/scripts/migrate_webnovel_to_ink.sh:1` | High | .sh 缺对等入口: .ps1, .cmd | .ps1 必须 UTF-8 BOM；.cmd 双击包装。参考 ink-auto.ps1 / ink-auto.cmd（如已有） |
| `ralph/ralph.sh:1` | High | .sh 缺对等入口: .ps1, .cmd | .ps1 必须 UTF-8 BOM；.cmd 双击包装。参考 ink-auto.ps1 / ink-auto.cmd（如已有） |

## C7 — `SKILL.md` 引用 `.sh` 缺 Windows PowerShell sibling 块

对应修复 US: **US-008**  数量: **1**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `ralph/skills/ralph/SKILL.md:244` | High | SKILL.md 引用 .sh 但缺 <!-- windows-ps1-sibling --> 标记 | 在 .sh 代码块下方追加 sibling 标记 + PowerShell 等价块（参考 ink-auto/SKILL.md:51） |

## C8 — 脚本硬编码 `python3` / `py -3`（未走 `find_python_launcher`）

对应修复 US: **US-009**  数量: **37**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `ink-writer/scripts/env-setup.ps1:70` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/env-setup.ps1:78` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/env-setup.sh:63` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/env-setup.sh:67` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.ps1:108` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:248` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:282` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:292` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:294` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:310` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:334` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:364` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:385` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:410` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:424` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:728` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:756` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:777` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:896` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:900` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:901` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:924` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:928` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:937` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:938` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:939` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:940` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:941` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1078` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1104` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1162` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1179` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1183` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1186` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1188` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1189` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |
| `ink-writer/scripts/ink-auto.sh:1227` | Medium | 硬编码 python3 / py -3 启动器 | 改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用） |

## C9 — Python CLI 入口未调 `enable_windows_utf8_stdio()`

对应修复 US: **US-010**  数量: **4**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `ink-writer/dashboard/server.py:70` | High | CLI 入口（__main__）未调 enable_windows_utf8_stdio() | 文件顶部 import runtime_compat 后，在 main 开头 enable_windows_utf8_stdio()（Mac no-op） |
| `ink-writer/scripts/sync_plugin_version.py:348` | High | CLI 入口（__main__）未调 enable_windows_utf8_stdio() | 文件顶部 import runtime_compat 后，在 main 开头 enable_windows_utf8_stdio()（Mac no-op） |
| `scripts/build_chapter_index.py:71` | High | CLI 入口（__main__）未调 enable_windows_utf8_stdio() | 文件顶部 import runtime_compat 后，在 main 开头 enable_windows_utf8_stdio()（Mac no-op） |
| `tests/data_modules/test_data_modules.py:1428` | Medium | CLI 入口（__main__）未调 enable_windows_utf8_stdio() | 文件顶部 import runtime_compat 后，在 main 开头 enable_windows_utf8_stdio()（Mac no-op） |

## Seed US List（按严重级别排序）

供下一轮 PRD 迭代直接消费。已与本 PRD 既有 US-002~US-010 对齐，
数字列表为各类风险对应 US 的优先级再排序参考：

1. **US-004**（C3, 25 处）— `subprocess` 调用文本模式缺 encoding 或 `shell=True`
2. **US-005**（C4, 10 处）— asyncio 入口未调 `set_windows_proactor_policy()`
3. **US-006**（C5, 7 处）— 裸 `symlink` 调用未走 `safe_symlink()` 兜底
4. **US-007**（C6, 2 处）— `*.sh` 缺同目录 `.ps1` / `.cmd` 对等入口
5. **US-008**（C7, 1 处）— `SKILL.md` 引用 `.sh` 缺 Windows PowerShell sibling 块
6. **US-010**（C9, 4 处）— Python CLI 入口未调 `enable_windows_utf8_stdio()`
7. **US-009**（C8, 37 处）— 脚本硬编码 `python3` / `py -3`（未走 `find_python_launcher`）
8. **US-003**（C2, 110 处）— 硬编码路径分隔符（疑似）

---

_报告由 `scripts/audit_cross_platform.py` 自动生成，请勿手工编辑。_
