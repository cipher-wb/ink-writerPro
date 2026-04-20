# 跨平台兼容性审计 Findings 报告（US-001）

扫描根目录: `/Users/cipher/AI/ink/ink-writer`

**总 finding 数**: 44 (Blocker=0 / High=3 / Medium=38 / Low=3)

## 按类别汇总

| 类别 | 数量 | 对应修复 US |
|------|------|-------------|
| C1 | 0 | US-002 |
| C2 | 3 | US-003 |
| C3 | 0 | US-004 |
| C4 | 0 | US-005 |
| C5 | 0 | US-006 |
| C6 | 0 | US-007 |
| C7 | 0 | US-008 |
| C8 | 37 | US-009 |
| C9 | 4 | US-010 |

## C2 — 硬编码路径分隔符（疑似）

对应修复 US: **US-003**  数量: **3**

| 文件:行 | 严重级别 | 现象 | 修复建议 |
|---------|----------|------|----------|
| `tests/core/test_path_cross_platform.py:141` | Low | 疑似硬编码路径字面量: '/Users/cipher/AI/ink/ink-writer' | 改用 pathlib.Path 拼接，让分隔符在 Windows 上自动归一化 |
| `tests/core/test_path_cross_platform.py:144` | Low | 疑似硬编码路径字面量: '/d/desktop/foo' | 改用 pathlib.Path 拼接，让分隔符在 Windows 上自动归一化 |
| `tests/core/test_path_cross_platform.py:146` | Low | 疑似硬编码路径字面量: '/mnt/d/desktop/foo' | 改用 pathlib.Path 拼接，让分隔符在 Windows 上自动归一化 |

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

1. **US-010**（C9, 4 处）— Python CLI 入口未调 `enable_windows_utf8_stdio()`
2. **US-009**（C8, 37 处）— 脚本硬编码 `python3` / `py -3`（未走 `find_python_launcher`）
3. **US-003**（C2, 3 处）— 硬编码路径分隔符（疑似）

---

_报告由 `scripts/audit_cross_platform.py` 自动生成，请勿手工编辑。_
