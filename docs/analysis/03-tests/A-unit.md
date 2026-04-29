# 阶段 3A：单元测试用例

> 代码位置：`tests/docs/test_phase3_unit_core_modes.py`  
> 测试框架：pytest（依据 `pytest.ini` 的 `testpaths` 与 `pythonpath` 配置）  
> 执行状态：本阶段仅编写测试，未执行测试。

## 选择范围

本批单元测试只覆盖阶段 1 函数清单中输入输出明确、副作用可控的函数，优先选取以下类型：

- 纯函数或近似纯函数：检查点分级、消歧紧急度、草稿字段映射。
- 受控文件 IO：蓝本解析、报告读取、状态读取，全部使用 `tmp_path` 或固定 fixture。
- 不触发外部进程、网络、AI API、真实项目写作流程的函数。

## Mock 策略

- 文件 IO：用 `tmp_path` 和 `tests/fixtures/phase3/` 隔离，不读写用户真实项目。
- 网络调用：本批单元测试不覆盖网络路径，不需要 mock。
- AI API：本批单元测试不调用 AI 编排层，不需要 mock。
- CLI 子进程：放入集成测试文档 `B-integration.md`，单元层不启动子进程。

## 覆盖矩阵

| # | 测试函数 | 输入组合 | 关键断言 | 映射 |
|---:|---|---|---|---|
| A-01 | `test_parse_blueprint_normalizes_headers_comments_and_aliases` | 正常：真实小说蓝本；边界：标题外文本、HTML 注释、字段别名、`第1章钩子`；异常：无 | 章节外文本不污染字段，别名归一，注释被清理，钩子字段可读 | quick-mode.md §C.1 #5；v27-bootstrap-mode.md §C.1 V6 → 覆盖: `ink_writer/core/auto/blueprint_to_quick_draft.py:parse_blueprint:50` |
| A-02 | `test_validate_accepts_complete_blueprint_and_rejects_missing_required` | 正常：完整蓝本；边界：空章节体解析为 `None`；异常：必填字段空值 | 完整输入通过；缺 `核心冲突` 抛 `BlueprintValidationError`；空 section 返回 `None` | quick-mode.md §C.1 #6、§E.1 `--blueprint` 校验失败分支 → 覆盖: `ink_writer/core/auto/blueprint_to_quick_draft.py:validate:106` |
| A-03 | `test_validate_rejects_blacklisted_golden_finger` | 正常：合法金手指；边界：禁词出现在能力句；异常：命中黑名单 | 命中 `系统签到` 时抛错，避免 Quick 蓝本进入下游 | quick-mode.md §C.1 #6；v27-bootstrap-mode.md §E.6 V-R2 → 覆盖: `ink_writer/core/auto/blueprint_to_quick_draft.py:validate:111` |
| A-04 | `test_to_quick_draft_maps_fanqie_defaults_and_missing_optional_fields` | 正常：番茄平台蓝本；边界：选填字段缺失；异常：无 | `platform=fanqie`，章节字数默认 1500，`__missing__` 只记录缺失/待自动填充字段 | quick-mode.md §C.1 #7；v27-bootstrap-mode.md §C.3 `--blueprint` 子流程 → 覆盖: `ink_writer/core/auto/blueprint_to_quick_draft.py:to_quick_draft:119` |
| A-05 | `test_to_quick_draft_falls_back_on_bad_numbers_and_auto_values` | 正常：合法字段；边界：未知平台、`AUTO`；异常：非数字目标章数/字数、非法激进度 `5` | 未知平台回退起点，非法数字回退平台默认，`AUTO` 进入 `__missing__` | quick-mode.md §E.1 platform 兜底；v27-bootstrap-mode.md §E.6 V-R4 → 覆盖: `ink_writer/core/auto/blueprint_to_quick_draft.py:_coerce_aggression:163`, `ink_writer/core/auto/blueprint_to_quick_draft.py:_coerce_int:172` |
| A-06 | `test_find_blueprint_chooses_largest_non_blacklisted_markdown` | 正常：多个合法 md；边界：黑名单和 `.draft.md` 同目录；异常：无 | 只扫描顶层非黑名单 md，并按文件大小选择最大蓝本 | v27-bootstrap-mode.md §C.1 V5、§E.2、§E.3 → 覆盖: `ink_writer/core/auto/blueprint_scanner.py:find_blueprint:31`, `ink_writer/core/auto/blueprint_scanner.py:_is_blacklisted:22` |
| A-07 | `test_find_blueprint_returns_none_for_non_dir_or_only_blacklisted` | 正常：无；边界：目录只有黑名单 md；异常：路径不存在 | 非目录或无可用蓝本时返回 `None`，由上层进入交互 bootstrap | v27-bootstrap-mode.md §A.1 触发 2/3；§C.1 V5 → 覆盖: `ink_writer/core/auto/blueprint_scanner.py:find_blueprint:31` |
| A-08 | `test_detect_project_state_covers_uninit_no_outline_writing_completed_and_bad_json` | 正常：S1/S2/S3；边界：只有 `总纲.md` 不算章纲；异常：坏 JSON | 缺 state 为 S0；无章纲为 S1；存在 `第*章*.md` 为 S2；完成态为 S3；坏 JSON 回 S0 | quick-mode.md §C.4 #78；v27-bootstrap-mode.md §C.1 V9 → 覆盖: `ink_writer/core/auto/state_detector.py:detect_project_state:20` |
| A-09 | `test_checkpoint_level_review_range_and_disambiguation_urgency` | 正常：5/10/20/200 章；边界：第 3 章审查范围；异常：非检查点章节 4 | 检查点 5 档分级、最近 5 章范围、消歧积压紧急度都按阶段 1 分支表输出 | quick-mode.md §C.3 #66-68、#74；quick-mode.md §E.4 → 覆盖: `ink_writer/core/cli/checkpoint_utils.py:determine_checkpoint:30`, `ink_writer/core/cli/checkpoint_utils.py:review_range:73`, `ink_writer/core/cli/checkpoint_utils.py:disambiguation_urgency:158` |
| A-10 | `test_report_issue_scanning_counts_missing_and_encoding_errors` | 正常：含四级 severity 报告；边界：文件不存在；异常：非法编码 | critical/high 关键词触发问题，四级数量正确；缺文件/坏编码 fail-soft 返回无问题 | quick-mode.md §C.3 #69-71；quick-mode.md §E.3 `report_has_issues` 分支 → 覆盖: `ink_writer/core/cli/checkpoint_utils.py:report_has_issues:90`, `ink_writer/core/cli/checkpoint_utils.py:count_issues_by_severity:108` |
| A-11 | `test_get_disambiguation_backlog_handles_valid_missing_and_malformed_state` | 正常：2 条待消歧；边界：缺项目；异常：坏 JSON | 正常计数，缺 state/坏 JSON 回 0，不阻断 checkpoint | quick-mode.md §C.3 #72-74；quick-mode.md §E.4 消歧检查分支 → 覆盖: `ink_writer/core/cli/checkpoint_utils.py:get_disambiguation_backlog:144` |

## 阶段 0/1 报告勘误

无。本文件中的源码行号为按需回查确认，用于测试追溯，不构成对阶段 0/1 结论的修正。
