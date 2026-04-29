# 阶段 3B：集成测试用例

> 代码位置：`tests/integration/test_phase3_mode_cli_contracts.py`  
> Fixture 位置：`tests/fixtures/phase3/`  
> 执行状态：本阶段仅编写测试，未执行测试。

## Fixture 设计

`tests/fixtures/phase3/` 下的 fixture 内容贴近真实写作场景，避免 lorem ipsum：

- `quick_blueprint.md`：都市悬疑+轻异能蓝本，包含平台、激进度、核心冲突、主角、金手指、前三章钩子。
- `chapter_outline.md`：第 1 章章纲片段，用于后续扩展写作流程测试。
- `debug.yaml`：Debug Mode 全局配置，打开 master 与 layer A/B/C。
- `plugin.json` / `marketplace.json`：外部环境版本一致性检查 fixture。

## 执行约束

- 集成测试以 CLI 合同为边界，使用 `subprocess.run(..., timeout=30)`。
- 不调用 Claude/Gemini/Codex 子进程，不触发真实 AI 写作。
- 所有项目副作用写入 `tmp_path`，不污染用户真实项目。
- 断言四类结果：退出码、stdout/stderr 关键内容、产出文件存在性、产出文件内容片段。

## 覆盖矩阵

| # | 模式 | 测试函数 | CLI 命令 | 关键断言 | Fixture | 映射 |
|---:|---|---|---|---|---|---|
| B-01 | Quick / `--blueprint` | `test_quick_mode_blueprint_cli_writes_draft_json` | `python ink-writer/scripts/blueprint_to_quick_draft.py --input quick_blueprint.md --output quick-draft.json` | exit 0；stdout 含 `BLUEPRINT_OK`；stderr 空；输出 JSON 存在且含 `题材方向=都市悬疑+轻异能`、`platform=fanqie` | `quick_blueprint.md` | quick-mode.md §C.1 #5-8；v27-bootstrap-mode.md §C.1 V6-V7 → 覆盖: `ink_writer/core/auto/blueprint_to_quick_draft.py:_main:181` |
| B-02 | Deep / init 等价出口 | `test_deep_mode_init_cli_creates_project_skeleton` | `python ink-writer/scripts/ink.py init <tmp/深潮秘档> 深潮秘档 都市悬疑 ...` | exit 0；stdout 含 `Project initialized at:`；`.ink/state.json` 与 `设定集/主角卡.md` 存在；主角卡含 `闻照` | 无，参数直接模拟 Deep 收集后的结构化输入 | deep-mode.md §C.1 D15；quick-mode.md §C.1 #15 → 覆盖: `ink-writer/scripts/init_project.py:main:871`, `ink-writer/scripts/init_project.py:init_project:243` |
| B-03 | Daily Workflow / 中断恢复 | `test_daily_workflow_clear_cli_writes_workflow_state_and_trace` | `python ink-writer/scripts/ink.py --project-root <project> workflow clear` | exit 0；stdout 含 `中断任务已清除`；`workflow_state.json.current_task` 变为 `None`；`.ink/observability/call_trace.jsonl` 存在 | 临时 `.ink/workflow_state.json` | daily-workflow.md `workflow clear` 分支；quick-mode.md §B.3 清残留状态 → 覆盖: `ink-writer/scripts/workflow_manager.py:clear_current_task:854` |
| B-04 | Auto Checkpoint Internals | `test_auto_checkpoint_cli_reports_level_json` | `python ink-writer/scripts/ink.py --project-root <project> checkpoint-level --chapter 20` | exit 0；stdout 为 JSON；第 20 章输出 review、standard audit、Tier2、disambig、review_range `[16,20]` | 临时 `.ink/state.json` | quick-mode.md §C.3 #66-68；auto-checkpoint-internals.md 检查点分支 → 覆盖: `ink_writer/core/cli/checkpoint_utils.py:cli_checkpoint_level:174` |
| B-05 | Debug / toggle | `test_debug_mode_toggle_cli_writes_local_config` | `python -m ink_writer.debug.cli --project-root <project> --global-yaml debug.yaml toggle layer_c off` | exit 0；stdout 含 `已写入`；`.ink-debug/config.local.yaml` 存在；内容含 `layer_c_invariants: false` | `debug.yaml` | debug-mode.md §C.1 #34/#37；debug-mode.md §E.7 → 覆盖: `ink_writer/debug/cli.py:cmd_toggle:73`, `ink_writer/debug/cli.py:main:99` |
| B-06 | Debug / report | `test_debug_mode_report_cli_indexes_jsonl_and_writes_report` | `python -m ink_writer.debug.cli --project-root <project> --global-yaml debug.yaml report --since 1d --run-id phase3-run --severity warn` | exit 0；stdout 含 `报告已生成`；`reports/manual-*.md` 存在；报告含 `writer.short_word_count` | `debug.yaml` + 临时 `events.jsonl` | debug-mode.md §C.1 #28/#32/#36；debug-mode.md §B.3 → 覆盖: `ink_writer/debug/cli.py:cmd_report:59`, `ink_writer/debug/reporter.py:Reporter.render:33` |
| B-07 | Cross-Platform / 路径 | `test_cross_platform_where_cli_accepts_chinese_and_space_path` | `python ink-writer/scripts/ink.py --project-root "<tmp>/雾港 问心录" where` | exit 0；stdout 等于 resolve 后路径；中文和空格路径不破坏入口 | 临时项目路径 | cross-platform-mode.md §C、§E.3；quick-mode.md §A.3 `ink.py` 入口 → 覆盖: `ink-writer/scripts/ink.py:main:24` |
| B-08 | External Environments / manifest | `test_external_environment_manifest_cli_passes_version_consistency` | `python scripts/maintenance/check_plugin_version_consistency.py --plugin-json plugin.json --marketplace-json marketplace.json` | exit 0；stdout 含 `PASS  ink-writer version aligned`；manifest 文件保持存在 | `plugin.json`, `marketplace.json` | external-environments-mode.md 插件发布一致性；阶段 2 Tier 2 动态发布入口核实 → 覆盖: `scripts/maintenance/check_plugin_version_consistency.py:main:77`, `scripts/maintenance/check_plugin_version_consistency.py:check:51` |
| B-09 | v27 Bootstrap / 扫描与 7 题兜底 | `test_v27_bootstrap_scanner_and_interactive_bootstrap_cli` | `python ink-writer/scripts/blueprint_scanner.py --cwd <dir>`；`bash ink-writer/scripts/interactive_bootstrap.sh <out>` | scanner exit 0 且输出最大合法蓝本路径；bootstrap exit 0；stderr 含 `蓝本已落盘`；输出 md 含 `### 核心冲突` | `quick_blueprint.md` + 交互输入 | v27-bootstrap-mode.md §C.1 V5/V8；§E.2-§E.4 → 覆盖: `ink-writer/scripts/blueprint_scanner.py:find_blueprint:33`, `ink-writer/scripts/interactive_bootstrap.sh:prompt_required:20`, `ink-writer/scripts/interactive_bootstrap.sh:prompt_with_default:33`, `ink-writer/scripts/interactive_bootstrap.sh:57` |

## 未覆盖说明

- `/ink-auto N` 的完整写章主循环需要真实 Claude/Gemini/Codex 子进程与章节生成链，本阶段只定义低风险 CLI 合同测试，不执行真实写作。
- Quick/Deep 的 LLM 苏格拉底式询问由 Skill prompt 编排，当前测试覆盖其结构化落地出口：蓝本转换与 `ink.py init`。

## 阶段 0/1 报告勘误

无。本文件中的源码行号为按需回查确认，用于测试追溯，不构成对阶段 0/1 结论的修正。
