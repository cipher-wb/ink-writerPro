# 测试基线报告

日期：2026-04-29（Asia/Shanghai）

## 结论

当前工程测试基线已建立，最终全量测试通过：

```text
4341 passed, 23 skipped, 62 warnings in 648.15s (0:10:48)
Total coverage: 80.07%
Required test coverage of 70% reached.
```

这份基线是在修复全量失败项、同步直白模式全场景设计、补齐 Phase 3 测试资料后重新跑出的最终结果。

## 已执行校验

| 类型 | 命令 | 结果 |
| --- | --- | --- |
| 全量测试 | `pytest` | 4341 passed / 23 skipped / 0 failed，coverage 80.07% |
| 直白模式闭环回归 | `pytest tests/checker_pipeline/test_directness_checker.py tests/editor_wisdom/test_simplicity_theme.py tests/prose/test_writer_agent_directness_mode.py tests/prose/test_simplification_pass.py tests/prose/test_sensory_immersion_directness_gate.py tests/prose/test_directness_threshold_gates.py --no-cov -q` | 通过 |
| 直白模式/场景分类回归 | `pytest tests/prose/test_writer_agent_directness_mode.py tests/prose/test_sensory_immersion_directness_gate.py tests/prose/test_directness_threshold_gates.py tests/core/context/test_scene_classifier.py --no-cov -q` | 通过 |
| Dashboard 导入冲突回归 | `pytest tests/data_modules/test_dashboard_app.py tests/data_modules/test_dashboard_server.py tests/data_modules/test_dashboard_watcher.py --no-cov -q`、`pytest tests/dashboard --no-cov -q` | 通过 |
| Phase 3 新增测试 | `tests/docs/test_phase3_unit_core_modes.py`、`tests/integration/test_phase3_mode_cli_contracts.py` | 通过，纳入全量 |
| Python 编译 | `git diff --name-only --diff-filter=ACMR -- '*.py' \| tr '\n' '\0' \| xargs -0 python3 -m py_compile` | 通过 |
| Shell 语法 | `git diff --name-only -- '*.sh' \| tr '\n' '\0' \| xargs -0 bash -n` | 通过 |
| diff 空白检查 | `git diff --check` | 通过，仅有 Git 对 `.cmd/.ps1` 的 CRLF 提示 |

## 修复归类

1. Dashboard 导入冲突：删除空的 `tests/dashboard/__init__.py`，避免 pytest 将 `import dashboard` 解析到测试包而非真实 dashboard 包。
2. 跨平台守卫：补齐 C8 Python launcher 检测、C9 Windows UTF-8 stdio 初始化、C3 subprocess `encoding="utf-8"` 契约。
3. 直白模式设计收敛：US-006 全场景激活已同步到 `directness-checker`、`sensory-immersion-checker`、`prose-impact-checker`、`flow-naturalness-checker`、`polish-agent`、`writer-agent`、Step 3 gate、writer-injection、schema 与测试。
4. writer-injection 前置约束：`directness_recall` 默认覆盖 7 值 `scene_mode`，缺失 `scene_mode` 按 `other` 兜底，避免写作端漏注入 simplicity 规则、审查端事后才拦。
5. 当前数据基线：更新 M2 真实规则数量、severity split、agent 数量、版本门禁等已经漂移的测试断言。
6. 脚本与文档一致性：调试 wrapper、maintenance wrapper、Agent 说明、架构文档与 editor-wisdom 文档已对齐当前流程。

## 剩余警告

这些警告当前不阻断测试，但建议后续单独治理：

- `ResourceWarning: unclosed database`：来自 `tests/core/test_safe_symlink.py` 扫描导入期间触发的 sqlite 连接未关闭提示。
- `jieba/pkg_resources` deprecation：第三方依赖在 Python 3.14 + 新 setuptools 下的弃用提示。
- local Qdrant payload indexes：本地 Qdrant 模式下 payload index 无效果的提示。
- Qdrant remote version warning：preflight 测试中无法获取 server version 的兼容性提示。
- Git CRLF 提示：`.cmd/.ps1` 文件在当前 Git 配置下提示下次 touch 会转 CRLF；`git diff --check` 未发现空白错误。

## 当前基线含义

- 测试层面：当前工作区在 macOS + Python 3.14 环境下全量通过。
- 覆盖率层面：项目总覆盖率为 80.07%，高于当前 70% 门槛。
- 设计层面：直白模式已按“全场景默认激活，仅 `directness_skip=true` 跳过”的目标收敛，writer / checker / polish / arbitration / schema / docs 语义一致。
