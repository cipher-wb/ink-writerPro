# 跨平台兼容性审计 Findings 报告（US-001）

扫描根目录: `/Users/cipher/AI/ink/ink-writer`

**总 finding 数**: 86 (Blocker=0 / High=48 / Medium=38 / Low=0)

## 按类别汇总

| 类别 | 数量 | 对应修复 US |
|------|------|-------------|
| C1 | 0 | US-002 |
| C2 | 0 | US-003 |
| C3 | 25 | US-004 |
| C4 | 10 | US-005 |
| C5 | 7 | US-006 |
| C6 | 2 | US-007 |
| C7 | 1 | US-008 |
| C8 | 37 | US-009 |
| C9 | 4 | US-010 |

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
| `tests/audit/test_audit_cross_platform.py:281` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
| `tests/audit/test_audit_cross_platform.py:284` | High | 裸 symlink 调用，Windows 非管理员会抛 OSError | 改走 runtime_compat.safe_symlink(src, dst)，无权限自动 copyfile 降级 |
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

---

_报告由 `scripts/audit_cross_platform.py` 自动生成，请勿手工编辑。_
