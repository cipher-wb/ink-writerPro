# Windows 故障排查手册

面向 Windows 10/11 原生运行 Ink Writer Pro 的用户。每条故障按"症状 / 原因 / 修复 / 验证"四段组织，先定位再动手。

> Mac/Linux 用户通常不会触发本手册的任何一条——所有 Windows 特化行为都走 `if sys.platform == "win32":` 分支（见 `CLAUDE.md > Windows 兼容守则`）。

---

## 目录（按出现频率排序）

1. [UnicodeDecodeError: 'gbk' codec 或 'charmap' codec](#1-unicodedecodeerror-gbk-codec-或-charmap-codec)
2. [PowerShell 执行策略拒绝运行 .ps1](#2-powershell-执行策略拒绝运行-ps1)
3. [PATH 里找不到 python / py](#3-path-里找不到-python--py)
4. [含中文或空格的项目路径打开失败](#4-含中文或空格的项目路径打开失败)
5. [OSError: symbolic link privilege not held](#5-oserror-symbolic-link-privilege-not-held)
6. [sqlite3.OperationalError: database is locked（index.db）](#6-sqlite3operationalerror-database-is-locked-indexdb)
7. [asyncio NotImplementedError: subprocess_exec](#7-asyncio-notimplementederror-subprocess_exec)
8. [ink-auto 崩溃后无法直接续写](#8-ink-auto-崩溃后无法直接续写)
9. [PYTHONIOENCODING 未生效 / 终端中文乱码](#9-pythonioencoding-未生效--终端中文乱码)
10. [.ps1 中文脚本在 PowerShell 5.1 运行时乱码](#10-ps1-中文脚本在-powershell-51-运行时乱码)
11. [Git Bash / WSL 路径（`/d/...`、`/mnt/d/...`）Python 读不到](#11-git-bash--wsl-路径d-mntd-python-读不到)
12. [.cmd 双击窗口秒闪退](#12-cmd-双击窗口秒闪退)

---

## 1. UnicodeDecodeError: 'gbk' codec 或 'charmap' codec

**症状**

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xe4 in position 12: illegal multibyte sequence
UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 1234: character maps to <undefined>
```

常见触发：读取 `outline.md` / `state.json` / chapter 正文文件。

**原因**

Windows 下 `open()` 默认编码是当前代码页（中文版 Windows 是 `cp936` / `gbk`），Python 没加 `encoding="utf-8"` 就按 gbk 去解码 UTF-8 字节序列必炸。本仓库所有 `open()` / `Path.read_text()` / `Path.write_text()` 都已在 US-002 修齐 `encoding="utf-8"`；若仍遇到此错，大概率是**第三方插件** 或 **用户自写脚本**缺参数。

**修复**

所有文本文件读写显式声明 UTF-8：

```python
# 错误：默认编码随平台漂移
open(path, "r")
Path(path).read_text()

# 正确：跨平台字节级一致
open(path, "r", encoding="utf-8")
Path(path).read_text(encoding="utf-8")
```

二进制模式（`"rb"` / `"wb"`）不受影响。

**验证**

```powershell
# 跑一遍仓库红线，任何缺 encoding 的 open() 会被扫出
py -3 scripts/audit_cross_platform.py --root . --only C1
```

---

## 2. PowerShell 执行策略拒绝运行 .ps1

**症状**

```
ink-auto.ps1 : 无法加载文件 ink-auto.ps1，因为在此系统上禁止运行脚本。
有关详细信息，请参阅 https:/go.microsoft.com/fwlink/?LinkID=135170 中的 about_Execution_Policies。
```

**原因**

PowerShell 默认执行策略 `Restricted`，不允许本地 `.ps1` 运行。

**修复**

本仓库的所有 `.cmd` 双击包装已经带 `-ExecutionPolicy Bypass`（见 `ink-writer/scripts/ink-auto.cmd:3`），双击走这条路径。如果你需要直接在 PowerShell 里跑 `.ps1`，三选一：

```powershell
# 选项 A（推荐，单次执行）：命令行显式 bypass
powershell -NoProfile -ExecutionPolicy Bypass -File .\ink-writer\scripts\ink-auto.ps1 10

# 选项 B：当前用户一次性放开
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 选项 C：当前会话放开（关窗口失效）
Set-ExecutionPolicy -Scope Process Bypass
```

不要开 `Unrestricted` 全局——RemoteSigned 就够。

**验证**

```powershell
Get-ExecutionPolicy -List
powershell -NoProfile -ExecutionPolicy Bypass -File .\ink-writer\scripts\env-setup.ps1
```

---

## 3. PATH 里找不到 python / py

**症状**

```
'python' 不是内部或外部命令、可运行的程序或批处理文件。
找不到名为 'py' 的命令
```

或 `.sh`/`.ps1` 脚本退出码 127。

**原因**

安装 Python 时没勾选 "Add python.exe to PATH"，或安装的是 Microsoft Store 别名（跳转到应用商店的假 python.exe）。

**修复**

本仓库的 launcher 探测逻辑（`runtime_compat.find_python_launcher()` + bash `find_python_launcher_bash` + PS `Find-PythonLauncher`）会按 `py -3` → `python3` → `python` 顺序探测。任何一个能跑就行：

```powershell
# 推荐：装官方 Python Launcher（py）
winget install Python.Python.3.12

# 验证
py -3 --version        # 最优先
python3 --version      # 次选
python --version       # 兜底
```

若装了但 `py` 还是找不到：把 `C:\Windows\py.exe` 或 `%LocalAppData%\Programs\Python\Launcher\` 加到 PATH。禁用 Microsoft Store 的 python 别名：**设置 → 应用 → 高级应用设置 → 应用执行别名** → 关闭 `python.exe` / `python3.exe`。

**验证**

```powershell
py -3 -c "import ink_writer; print('OK')"
Get-Command py, python3, python | Format-Table Name,Source
```

---

## 4. 含中文或空格的项目路径打开失败

**症状**

- `FileNotFoundError: [WinError 2] 系统找不到指定的文件: 'C:\Users\张三\我的小说\state.json'`
- subprocess 启动时 `OSError` 或参数被拆成多段

**原因**

两类：① 中文字符被错误编码后变乱码路径；② 含空格路径传给 subprocess 时未 quote，shell 按空格拆词。

**修复**

- **不要**用 `shell=True`；用 args 列表（`subprocess.run([py, "-c", code])`）。仓库已全面禁用 `shell=True`，`tests/core/test_subprocess_cross_platform.py:test_repo_has_no_subprocess_shell_true` 是红线。
- 路径变量一律 `Path(...)` 或 `Path(str).expanduser().resolve()`，不用 `os.path.join` 拼字符串再裸传（尤其别在 bash 手写拼接）。
- 项目根目录建议放英文路径（如 `C:\ink-projects\xiuxian`），中文路径虽然能用，但在遇到第三方工具（git / pip / 某些编辑器）时仍偶有兼容性小坑。

**验证**

```powershell
# 把当前项目路径过一遍 locator（含中文不炸即 OK）
py -3 -c "from project_locator import find_project_root; print(find_project_root())"
```

---

## 5. OSError: symbolic link privilege not held

**症状**

```
OSError: [WinError 1314] 客户端没有所需的特权: 'src' -> 'link'
```

多在 migrate / quality-upgrade 等需要建符号链接的步骤出现。

**原因**

Windows 创建 symlink 需要 ① Administrator 权限，或 ② 开"开发人员模式"（Windows 10 1703+）。普通用户默认两者都没有。

**修复**

仓库内所有符号链接都走 `runtime_compat.safe_symlink(src, dst)`——无特权时**自动降级为 `shutil.copyfile` / `copytree`** 并打 WARNING（见 `ink-writer/scripts/runtime_compat.py:163`）。如果你看到 WARNING 但程序继续跑，这是**预期降级**，不是错误。

若想恢复真 symlink（节省磁盘），二选一：

```
方案 A（推荐）：打开开发人员模式
  设置 → 系统 → 开发者选项 → 开发人员模式 → 打开
  重启后无需管理员即可创建 symlink

方案 B：以管理员身份运行 PowerShell
  右键开始菜单 → Windows Terminal（管理员） → 跑脚本
```

**验证**

```powershell
py -3 -c "from runtime_compat import _has_symlink_privilege; print(_has_symlink_privilege())"
# True = 有特权，symlink 真建；False = 自动走 copy 降级
```

---

## 6. sqlite3.OperationalError: database is locked（index.db）

**症状**

```
sqlite3.OperationalError: database is locked
```

多发生在 `/ink-auto` 并发写章、或上一次 Ink 进程异常退出后再启动时。

**原因**

- 上一次进程崩溃后 SQLite WAL 锁未释放（`index.db-shm` / `index.db-wal` 残留）；
- 并发进程数超过 `ChapterLockManager` 的 filelock + asyncio.Lock 容量（推荐 `parallel <= 4`）；
- Windows 反病毒软件/云同步（OneDrive/Dropbox）扫描 `.db` 造成瞬时锁。

**修复**

1. 确认无其他 Ink 进程：`Get-Process | Where-Object { $_.Name -match 'python|claude' }`，有残留就 `Stop-Process` 掉；
2. 删除两个临时文件（**不要**删 `index.db` 本体）：
   ```powershell
   Remove-Item .\<project>\index.db-shm, .\<project>\index.db-wal -ErrorAction SilentlyContinue
   ```
3. 项目目录加入反病毒白名单 / 移出 OneDrive 同步目录；
4. 并发跑时 `--parallel` 不超过 4。

**验证**

```powershell
py -3 -c "import sqlite3; c=sqlite3.connect(r'.\<project>\index.db', timeout=5); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); print('OK')"
```

---

## 7. asyncio NotImplementedError: subprocess_exec

**症状**

```
NotImplementedError
  File "asyncio\events.py", line ..., in _run
  File "...\cli.py", line ..., in main
    await run_cli_process(...)
```

常见于"调用 agent 子进程"或 "ink-auto 并发 writer-agent" 场景。

**原因**

Windows 上 asyncio 默认事件循环策略是 `WindowsSelectorEventLoopPolicy`，不支持 subprocess API。必须切到 `WindowsProactorEventLoopPolicy`。

**修复**

所有生产入口已通过 `runtime_compat.set_windows_proactor_policy()` 统一声明（US-005）。`tests/conftest.py` 也在 module 加载时调一次。如果你**自写脚本**或**第三方插件**遇到此错，在 `main()` 最开头加：

```python
from runtime_compat import set_windows_proactor_policy
set_windows_proactor_policy()  # Mac no-op; Windows 首次设策略，幂等
```

**禁止**手写 `if sys.platform == "win32": asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())`——仓库红线测试 `tests/core/test_asyncio_proactor_policy.py` 会挂 CI。

**验证**

```powershell
py -3 -c "import asyncio; from runtime_compat import set_windows_proactor_policy; set_windows_proactor_policy(); print(type(asyncio.get_event_loop_policy()).__name__)"
# 期望输出: WindowsProactorEventLoopPolicy
```

---

## 8. ink-auto 崩溃后无法直接续写

**症状**

- `/ink-auto 10` 跑到第 5 章 PowerShell 窗口消失；
- 再跑 `/ink-auto` 报 "already has draft at chapter N" 或状态不一致。

**原因**

上一次运行中断（LLM 超时 / 网络断 / 手动 Ctrl+C）。`ink-auto.ps1:364` 已经在失败时向 stderr 打一行诊断日志：

```
[ink-auto] llm_exit=<code> tool=<platform> log=<path>
```

这行就是定位中断章节和根因的首选。

**修复**

```powershell
# 1. 先看诊断日志（ink-auto 失败时打到 stderr）
Get-Content .\<project>\.ink\logs\ink-auto-*.log -Tail 50

# 2. 用 /ink-resume 自动识别断点
#    在 Claude Code 里：
/ink-resume

# 3. 如果 resume 也报错，查 project_memory.json 的 workflow_state
py -3 -c "import json; print(json.dumps(json.load(open(r'.\<project>\project_memory.json',encoding='utf-8')).get('workflow_state',{}), ensure_ascii=False, indent=2))"
```

`ink-resume` 内建断点决策树（见 `ink-writer/skills/ink-resume/SKILL.md`），无需手删任何文件。

**验证**

```powershell
Select-String -Path .\<project>\.ink\logs\ink-auto-*.log -Pattern 'llm_exit=' | Select-Object -Last 5
```

---

## 9. PYTHONIOENCODING 未生效 / 终端中文乱码

**症状**

`print("你好")` 在 cmd / PowerShell 打印成 `???` 或 `浣犲ソ`。

**原因**

Windows 控制台默认代码页 cp936，Python stdout/stderr 没强制 UTF-8 就按 gbk 输出。仓库所有 CLI 入口已在文件开头调 `enable_windows_utf8_stdio()`（US-010 红线），正常路径不会炸——若仍乱码，多半是**非 CLI 入口**脚本（用户自写、第三方工具）。

**修复**

两档并行，任一生效即可：

```powershell
# 档 1（推荐，永久）：启用 Windows 系统级 UTF-8
# 设置 → 时间和语言 → 语言 → 管理语言设置 → 更改系统区域设置
#   → 勾选 "Beta: 使用 Unicode UTF-8 提供全球语言支持"
# （部分老软件不兼容；如遇兼容性问题关掉即可）

# 档 2（临时，当前 shell 生效）：env 变量
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"          # Python 3.7+ 全局 UTF-8 模式
chcp 65001                      # 控制台代码页切 UTF-8

# 持久化（写入 PowerShell profile）
Add-Content $PROFILE '$env:PYTHONIOENCODING = "utf-8"'
Add-Content $PROFILE '$env:PYTHONUTF8 = "1"'
```

新写的 CLI 入口必须在 `main()` 开头调 `enable_windows_utf8_stdio()`（见 `CLAUDE.md > Windows 兼容守则第 2 条`）。

**验证**

```powershell
py -3 -c "import sys; print(sys.stdout.encoding); print('你好')"
# 期望: utf-8 + 正常中文
```

---

## 10. .ps1 中文脚本在 PowerShell 5.1 运行时乱码

**症状**

`ink-auto.ps1` 里的中文提示（如 `"开始写第 N 章..."`）打出来是问号或方块。

**原因**

PowerShell 5.1（Windows 10 预装版本）读取 `.ps1` 时按**系统 ANSI 代码页**解码——没有 UTF-8 BOM 就认不出 UTF-8，中文字节按 gbk 解码后乱码。PowerShell 7 默认 UTF-8 无此问题。

**修复**

仓库所有 `.ps1` 文件**已经**带 UTF-8 BOM（三字节 `EF BB BF`，由 US-007 强制），`tests/scripts/test_script_entries_parity.py:test_every_ps1_sibling_has_utf8_bom` 是红线——PR 里新增 `.ps1` 缺 BOM 会直接挂 CI。

若你看到乱码，多半是**自己复制粘贴**时 IDE 去掉了 BOM。用下面方式重建：

```powershell
# 方法 A：用 Python 加 BOM
py -3 -c "import pathlib; p=pathlib.Path('your-script.ps1'); p.write_bytes(b'\xef\xbb\xbf' + p.read_bytes())"

# 方法 B：升级到 PowerShell 7（彻底绕过）
winget install Microsoft.PowerShell
pwsh -NoProfile -File .\your-script.ps1
```

**验证**

```powershell
# 头三字节应为 EF BB BF
Format-Hex .\ink-writer\scripts\ink-auto.ps1 -Count 3
```

---

## 11. Git Bash / WSL 路径（`/d/...`、`/mnt/d/...`）Python 读不到

**症状**

从 Git Bash 复制 `/d/projects/novel` 贴到 `/ink-init --project` 后，Python 报 `FileNotFoundError`。

**原因**

- Git Bash / MSYS 把 `D:\` 渲染成 `/d/...`；
- WSL 把 `D:\` 渲染成 `/mnt/d/...`。

这两种都不是 Windows 原生路径，Python `Path("/d/projects/novel")` 会按 POSIX 解析，在 Windows 上找不到。

**修复**

仓库内用 `runtime_compat.normalize_windows_path(value)` 统一归一化（见 `runtime_compat.py:59`）：

```python
from runtime_compat import normalize_windows_path

p = normalize_windows_path("/d/projects/我的小说")
# Mac/Linux: 透传 Path('/d/projects/我的小说')
# Windows:   Path('D:/projects/我的小说')
```

`/ink-init`、`/ink-write` 等入口已内建此归一化。若你自己写脚本接收用户路径，**必调一次** `normalize_windows_path`。

**验证**

```powershell
py -3 -c "from runtime_compat import normalize_windows_path; print(normalize_windows_path('/d/projects/test'))"
# Windows 期望: D:\projects\test
```

---

## 12. .cmd 双击窗口秒闪退

**症状**

双击 `ink-auto.cmd` 或 `env-setup.cmd`，窗口弹一瞬间就消失，看不到任何错误。

**原因**

`.cmd` 遇到非零退出就关窗。真实错误写到了 stderr，但窗口已经关了你来不及看。

**修复**

**不要**双击 `.cmd`——直接在 PowerShell 里显式调用，看完整输出：

```powershell
# 推荐：开 PowerShell，进入仓库目录
cd path\to\ink-writer
powershell -NoProfile -ExecutionPolicy Bypass -File .\ink-writer\scripts\ink-auto.ps1 10

# 或临时改 cmd 让它跑完 pause（仅调试用，不要提交）
cmd /k .\ink-writer\scripts\ink-auto.cmd 10
```

日常用法仍推荐 Claude Code 里的 `/ink-auto 10` 斜杠命令，由插件接管，避免 shell 窗口问题。

**验证**

```powershell
# 直接看脚本最近一次运行留下的 llm_exit 诊断行
Get-Content .\<project>\.ink\logs\ink-auto-*.log -Tail 20
```

---

## 还是没搞定？

1. 先跑跨平台审计，把所有 C1~C9 类风险重新扫一遍：
   ```powershell
   py -3 scripts/audit_cross_platform.py --root . --output reports/cross-platform-audit-findings.md
   ```
2. 翻 `progress.txt` 里的 `## Codebase Patterns` 段——每条都是上一轮踩过的坑和解决方案；
3. 翻 `CLAUDE.md > Windows 兼容守则`——三条硬约束（`encoding="utf-8"` / `enable_windows_utf8_stdio` / `.sh` 对等 `.ps1`+`.cmd`）覆盖了 90% 的新问题。

如果你发现一条本手册没覆盖的 Windows 特有故障，欢迎提 PR 补进来——按现有四段式模板（症状 / 原因 / 修复 / 验证）即可。
