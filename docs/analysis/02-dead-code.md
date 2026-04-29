# Ink Writer Pro - 阶段 2 死代码与冗余文件清单

> 基于 `docs/analysis/00-codemap.md` 与 `docs/analysis/01-modes/*.md`。  
> 本阶段只产出清单，不删除文件、不修改源码、不执行测试。

## 审计口径

- `00-codemap.md` 的 importer 表与 `01-modes/*.md` 的 IO 表作为事实底座。
- 对 Tier 1 候选实跑 `rg` 验证，避免误删。
- 生产引用判断默认排除 `docs/analysis/**`、`archive/**`、`tests/**`、`benchmark/**`、`ralph/**`；文档/任务引用单独记录为“可能仍有手工用途”。
- `__init__.py`、配置文件、README/LICENSE/package 元文件不进入 Tier 1。

## 🔴 Tier 1: 确定无引用（可直接删除）

| 文件 | 行数 | 最后修改时间 | 证据(grep/rg 命令 + 输出) |
|---|---:|---|---|
| `ink_writer/chapter_paths_types.py` | 70 | 2026-04-19 04:33:21 | `$ rg -n "^(from ink_writer\\.chapter_paths_types import\|import ink_writer\\.chapter_paths_types)" --glob '*.py' --glob '!docs/analysis/**' --glob '!archive/**' --glob '!tests/**' --glob '!benchmark/**' --glob '!ralph/**' .` → 无输出；`$ rg -n "chapter_paths_types" ink-writer/skills ink-writer/scripts --glob '*.md' --glob '*.sh' --glob '*.py'` → 仅命中 `ink-writer/scripts/chapter_paths.py:23/31`、`ink-writer/scripts/chapter_outline_loader.py:11/13` 等对 `chapter_paths_types` / `scripts.chapter_paths_types` 的导入，不经过 `ink_writer.chapter_paths_types`。[源码核实: `ink-writer/scripts/chapter_paths.py:23`, `ink-writer/scripts/chapter_outline_loader.py:11`] |

判定说明：

- `00-codemap.md:132` 标记该文件直接 importer 为 `0 | (none)`，且 `00-codemap.md:399-400` 将它列为唯一实质死代码候选。
- 它不是任何 CLI 命令入口，没有 `argparse` / `__main__`。
- `01-modes/*.md` 的 IO 表没有任何模式读取该文件。
- 同名实际使用路径是 `ink-writer/scripts/chapter_paths_types.py`，生产导入方走的是脚本树模块。

## 🟡 Tier 2: 静态无引用但可能被运行时动态加载

| 条目 | 为什么静态分析显示无引用 | 怀疑的动态加载机制 | 需要你决策的问题 |
|---|---|---|---|
| `ink_writer/pacing/high_point_scheduler.py` + `config/high-point-scheduler.yaml` | `00-codemap.md:299` 显示生产 importer 为 0，仅 `tests/pacing/test_high_point_scheduler.py` 引用；`rg -n "high_point_scheduler\|ink_writer\\.pacing"` 排除 tests 后只命中文档/skill 文案与模块自身。 | `ink-writer/skills/ink-plan/SKILL.md:486-487` 明确要求调用 `ink_writer.pacing.high_point_scheduler.schedule_high_point()`；模块自身在 `ink_writer/pacing/high_point_scheduler.py:31-32` 读取 `config/high-point-scheduler.yaml`。[源码核实: `ink-writer/skills/ink-plan/SKILL.md:486`, `ink_writer/pacing/high_point_scheduler.py:31`] | `/ink-plan` 执行时是否真的让 LLM 运行这段 Python，还是只是 prompt 约束？若没有真实调用，应归档或补接线。 |
| `ink_writer/foreshadow/fix_prompt_builder.py` | `00-codemap.md:279` 显示只被 `tests/foreshadow/test_foreshadow_fix_prompt.py` 引用；`rg -n "ink_writer\\.foreshadow\\.fix_prompt_builder"` 排除 tests 后无输出。 | 同包 `tracker.py` 已被 `/ink-plan` 生命周期调度使用；fix prompt 可能原计划由 polish/fix 阶段按扫描结果动态拼接，但阶段 1 的模式文档未列到该调用。 | 伏笔生命周期违规是否需要自动生成修复提示词？如果需要，应接入 polish/fix；如果不需要，可删除该模块及测试。 |
| `ink_writer/plotline/fix_prompt_builder.py` | `00-codemap.md:312` 显示只被 `tests/plotline/test_plotline_fix_prompt.py` 引用；`rg -n "ink_writer\\.plotline\\.fix_prompt_builder"` 排除 tests 后无输出。 | `ink-writer/skills/ink-write/SKILL.md:1766` 写明 critical 明暗线断更应触发 `plotline_fix_prompt`，但 `ink-writer/skills/ink-write/SKILL.md:1773` 只列出 `ink_writer.plotline.tracker.scan_plotlines()`，没有导入 fix builder。[源码核实: `ink-writer/skills/ink-write/SKILL.md:1766`] | 这里是缺接线还是废弃设计？若保留 Step 3.10 阻断，建议接入；否则删去 fix builder 并修正文档。 |
| `config/ab_channels.yaml` | `00-codemap.md:757` 标记为“仅测试和 spec 引用，生产代码未加载”；排除 tests 后主要命中 README、设计文档、`ink-writer/skills/ink-write/SKILL.md:1007/1024/1039`。 | `ink-write` skill 以 LLM 编排方式读取/解释 A/B 通道，`EvidenceChain.channel` 已可持久化，但没有 Python loader 强制读取配置。 | A/B 通道是否仍是未来真实质量验证开关？若是，应补 loader；若否，可归档配置与 skill 文案。 |
| `config/ink_learn_throttle.yaml` | `00-codemap.md:766` 标记“仅 spec 引用，代码未加载”；排除 tests 后实际命中 `ink-writer/skills/ink-learn/SKILL.md:179/195/203`。 | `/ink-learn` 的 inline Python 把 `throttle_path=Path('config/ink_learn_throttle.yaml')` 传给 `propose_cases_from_failures()`。[源码核实: `ink-writer/skills/ink-learn/SKILL.md:179`] | 这是 skill 动态配置，不应直接删；但 codemap 的“仅 spec 引用”应修正。 |
| `config/incremental-extract.yaml` | `00-codemap.md:764` 标记“仅测试引用，生产代码未直接加载”；当前仓库已无 `ink_writer/incremental_extract/` 目录，`rg -n "incremental-extract\|incremental_extract"` 排除 tests 后只命中文档/历史审计。 | 可能是已删除 `incremental_extract` 模块留下的孤儿配置。 | 若增量抽取不计划恢复，可归档/删除；若要恢复，需要先恢复模块与数据流接线。 |
| 顶层手工维护脚本：`scripts/ab_prompts.py`, `scripts/build_blind_test.py`, `scripts/build_chapter_index.py`, `scripts/build_reference_corpus.py`, `scripts/calibrate_anti_ai_thresholds.py`, `scripts/e2e_anti_ai_overhaul_eval.py`, `scripts/mine_hook_patterns.py`, `scripts/regen_directness_thresholds_explosive.py`, `scripts/run_300chapter_benchmark.py`, `scripts/run_m4_test_book.py` | 均有 `argparse`/手工 CLI 用法，但不在 17 个 slash command 或阶段 1 运行模式 IO 表中；`rg` 排除 tests 后多为脚本自带 usage、PRD、历史审计引用。 | 这些更像审计、校准、benchmark、一次性数据构建工具。`scripts/build_style_rag.py` 不列入本项，因为 `ink_writer/style_rag/retriever.py:32/121` 与 `ink-writer/scripts/init_project.py:994` 会真实调用它。 | 是否保留为开发者工具？建议若保留，统一放入 `scripts/devtools/` 或文档化“非主流程”。 |
| `scripts/migration/fix11_merge_packages.py` | `00-codemap.md:525` 只说明它是 FIX-11 迁移脚本；排除 tests 后只有自身 usage 与历史任务引用。 | 一次性迁移工具，可能只在历史升级时手动执行。 | FIX-11 是否已彻底完成？若完成，可移到 `archive/`；若还要支持旧项目迁移，应保留并写入迁移手册。 |
| `ink-writer/scripts/sync_plugin_version.py` | `rg -n "sync_plugin_version\|sync-plugin-version"` 排除 tests/docs/analysis 后无输出；它有独立 CLI，但不在任何模式或发布脚本中出现。 | 可能是手工发布前同步 `plugin.json` / manifest 版本的工具。 | 是否存在外部发布流程调用它？若没有，应接入 `scripts/maintenance/check_plugin_version_consistency.py` 或归档。 |

## 🟢 Tier 3: 被引用但疑似 dead code

| 条目 | 调用链 / 不可达原因 | 建议 |
|---|---|---|
| `ink_writer/debug/alerter.py:Alerter.chapter_summary` 与 `Alerter.batch_report` | `debug-mode.md:297-299` 标记仅 tests 调用；`rg -n "Alerter\|batch_report"` 排除 tests 后只命中类定义、shim 与配置字段。预期链应为 `ink-auto.sh run_checkpoint/批次结束 → Alerter.batch_report`，但 `quick-mode.md:675` 与 `debug-mode.md:436` 均确认 `ink-auto.sh` 中 0 处实际调用。 | 这是文档承诺的 Debug per-chapter/per-batch 告警层。要么接到 `ink-write` 章末和 `ink-auto` 批次末，要么降级为未启用实验功能。 |
| `ink_writer/debug/checker_router.py:route` | `debug-mode.md:300` 标记仅 tests 调用；源码 `ink_writer/rewrite_loop/orchestrator.py:255-257` 只有 TODO，未把 checker report 转为 `layer_b_checker` Incident。实际链停在 `rewrite_loop.orchestrator.run → checkers_fn → TODO checker_router`。 | 若保留 Layer B，需要把 checker 输出 schema 规整后调用 `route()`；否则 Debug Mode 的 layer_b 开关是空开关。 |
| `ink_writer/debug/invariants/auto_step_skipped.py:check` | `debug-mode.md:301/434` 标记未接线；`config/debug.yaml:38-47` 有 `expected_steps`，`ink-writer/skills/ink-auto/SKILL.md:262-289` 有 LLM 文案示例，但真实执行器 `ink-auto.sh` 未调用。调用链应为 `ink-auto.sh 每章收尾 → auto_step_skipped.check`，当前不存在。 | 如果要检查 `/ink-auto` 漏步，必须由 shell 收集实际 step 序列并调用该 invariant；否则删除 skill 文案，避免误导。 |

## 📦 临时 / 备份 / 系统文件

| 类型 | 文件 | 状态 | 建议 |
|---|---|---|---|
| `.DS_Store` | 19 个：`.DS_Store`, `benchmark/.DS_Store`, `data/.DS_Store`, `docs/.DS_Store`, `ink-writer/.DS_Store`, `reports/.DS_Store` 等 | `git check-ignore -v` 显示 `.gitignore:23:.DS_Store` 已忽略；未被 `git status` 列出 | 可本地清理，不影响仓库。 |
| `.log` | `reports/e2e-smoke-mac.log` 28 行、`scripts/live-review/m3_batch.log` 302 行 | `git ls-files` 显示已跟踪 | 这两份是历史运行日志，若不需要复现证据，可从仓库移除并保留在 `reports/` 生成产物策略里。 |
| `.log` | `scripts/ralph/ralph.run.log` 198 行 | `.gitignore:77` 已忽略，未跟踪 | 可本地删除。 |
| `*.bak`, `*~`, `Thumbs.db` | 未发现 | - | 无动作。 |

## 阶段 0/1 报告勘误

1. `00-codemap.md:888-890` 仍把 `/ink-debug-{toggle,status,report}` 的 `${SCRIPTS_DIR}/debug/*.sh` 标为“未扫到”。实际文件存在：`scripts/debug/ink-debug-{report,status,toggle}.{sh,ps1,cmd}` 与 `ink-writer/scripts/debug/ink-debug-{report,status,toggle}.{sh,ps1,cmd}`。建议修正 codemap 的待确认项。
2. `00-codemap.md:854` 对 Codex 入口写成“使用同一 ink-writer/”。`external-environments-mode.md` 已补充更准确描述：Codex 通过 symlink 暴露 `ink-writer/skills/`，并依赖 `CLAUDE_PLUGIN_ROOT`。建议把 codemap 同步为 symlink 机制。
3. `00-codemap.md:856-858` 把 ink-auto 自动化只视为内部检查点；`v27-bootstrap-mode.md` 证明空目录 `/ink-auto N` 从用户视角是独立主模式。建议 codemap 增补 `6-A.4 v27 bootstrap mode`。

> Tier 1: 1 个文件 70 行 | Tier 2: 9 个待确认 | Tier 3: 3 个建议重构 | 临时文件: 22 个
