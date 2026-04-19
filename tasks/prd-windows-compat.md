# PRD: Windows 兼容性改造（Claude Code 入口）

## Introduction

Ink Writer Pro v18.0.0 原本面向 macOS 开发，核心入口脚本 `ink-auto.sh` / `env-setup.sh` 是 Bash，并对 Unix 运行时（`python3` 命令、POSIX 路径、LF 行结尾、UTF-8 stdio、符号链接）存在隐式假设。本 PRD 的目标是在**完全不影响 Mac 用户现有体验**的前提下，为 Windows 用户（仅 Claude Code 场景）提供一条与 Mac 等价、开箱即用的使用路径，并使 `pytest` 基线 `2984 passed, 19 skipped` 在 Windows 上同样零回归。

仓库内已具备部分跨平台能力（`ink-writer/scripts/runtime_compat.py`、`filelock`、`run_tests.ps1`），本次改造在此基础上补齐链路。

## Goals

- Windows 10/11 用户在 Claude Code 中安装后，通过等价的一条命令即可触发 `/ink-auto`、`/ink-init`、`/ink-resume` 等工作流，行为与 Mac 一致
- `.sh` 脚本、Mac 安装/运行路径、文档中既有 Mac 示例**字节级不变**
- Windows 与 Mac 共享同一套 Python 源码；所有新增代码以 `if sys.platform == "win32"` 分支形式接入，永不影响 Mac 分支
- `pytest --no-cov` 在 Windows 上输出 `2984 passed, 19 skipped`（或在 `skipif win32` 标注的情况下 skipped 数合理上浮），Mac 保持原数值
- 本次所有改动打包成一个 PR，用户明确批准后才 push 到 upstream

## User Stories

### US-001: 新增 Windows PowerShell 入口脚本
**Description:** 作为 Windows 用户，我希望有与 `ink-auto.sh` / `env-setup.sh` 功能等价的 PowerShell 脚本，这样 Claude Code 调起 `/ink-auto` 时在 Windows 上能直接跑通。

**Acceptance Criteria:**
- [ ] 新增 `ink-writer/scripts/ink-auto.ps1`、`ink-writer/scripts/env-setup.ps1`，逐条对应现有 `.sh` 的行为（参数、退出码、日志输出、checkpoint 调度 5/10/20/50/200）
- [ ] 新增 `scripts/ralph/ralph.ps1` 对应 `ralph.sh`
- [ ] 原 `.sh` 脚本字节不变（`git diff` 对这些文件零输出）
- [ ] PowerShell 脚本在 `pwsh 7+` 和 Windows 内置 `powershell 5.1` 均可执行
- [ ] 脚本顶部 `$ErrorActionPreference = 'Stop'`，失败返回非零退出码

### US-002: 新增 `.cmd` 包装器以支持无 PowerShell 配置的场景
**Description:** 作为不想调 `Set-ExecutionPolicy` 的 Windows 用户，我希望能直接 `ink-auto.cmd 10` 启动，避免 PowerShell 执行策略阻塞。

**Acceptance Criteria:**
- [ ] 新增 `ink-writer/scripts/ink-auto.cmd`，内部调用 `powershell -ExecutionPolicy Bypass -File ink-auto.ps1 %*`
- [ ] 同步新增 `env-setup.cmd`
- [ ] 双击或在 `cmd.exe` 中直接执行均可工作

### US-003: Claude Code Skill / Command 层跨平台分发
**Description:** 作为 Claude Code 用户，我希望 `/ink-auto`、`/ink-init`、`/ink-resume` 等 slash commands 在 Mac 上仍调用 `.sh`，在 Windows 上调用 `.ps1/.cmd`，对用户透明。

**Acceptance Criteria:**
- [ ] 定位 `ink-writer/commands/` 与 `ink-writer/skills/` 下所有引用 `ink-auto.sh` / `env-setup.sh` 的位置
- [ ] 每个位置改为平台探测：Mac/Linux 走原 `.sh`，Windows 走对应 `.ps1` 或 `.cmd`
- [ ] 分发逻辑封装在一个 helper（Python 或 markdown 指令），避免散落
- [ ] Mac 下 `/ink-auto 5` 执行路径与改造前**字节级**一致（通过对比日志首行验证）

### US-004: `python3` 硬编码根除
**Description:** 作为 Windows 用户，我希望不需要为了跑脚本而手动 `mklink python3.exe python.exe`。

**Acceptance Criteria:**
- [ ] 搜索仓库内所有 `python3 ` 调用（shell 脚本、PowerShell 脚本、README、Python `subprocess` 调用、CI workflows）
- [ ] Bash 脚本保持 `python3` 不动（Mac 正常）
- [ ] PowerShell / `.cmd` 新脚本中统一使用 `py -3`（优先）或 `python`，通过 `Get-Command` 探测
- [ ] 任何 Python 代码里 `subprocess.run(["python3", ...])` 改为 `sys.executable`
- [ ] README 的 Windows 章节明确写 `python` 或 `py -3`

### US-005: asyncio 事件循环策略在 Windows 上显式设定
**Description:** 作为维护者，我希望并发写作路径在 Windows 上使用 `WindowsProactorEventLoopPolicy`，避免 subprocess / socket 相关行为差异。

**Acceptance Criteria:**
- [ ] 在 `ink_writer/parallel/pipeline_manager.py` 模块级增加：`if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())`
- [ ] 同样守卫加到其它显式调用 `asyncio.run` 的入口（`scripts/` 下的 runner）
- [ ] Mac 分支逻辑完全不变
- [ ] `tests/parallel/test_concurrent_state_write.py` 中 `asyncio.get_event_loop()` 改为 `asyncio.new_event_loop()` 或使用 `asyncio.run`

### US-006: 所有文本 `open()` 补齐 `encoding="utf-8"`
**Description:** 作为 Windows 中文用户，我希望项目读写 md / json / txt / py 不因 cp936 默认编码而乱码或 `UnicodeDecodeError`。

**Acceptance Criteria:**
- [ ] 静态扫描仓库（`ink_writer/`、`ink-writer/scripts/`、`scripts/`、`benchmark/`、`tests/`）所有 `open(` 调用
- [ ] 文本模式（未指定 `"b"`）且未显式 `encoding=` 的，一律补 `encoding="utf-8"`
- [ ] 二进制模式 `"rb"` / `"wb"` 保持不变
- [ ] `pathlib.Path.read_text()` / `write_text()` 同理补 `encoding="utf-8"`
- [ ] 一次性全量改完，提交前 Windows 与 Mac 各自 `pytest` 全绿
- [ ] 工具脚本（`json.load` / `json.dump` 本身不 open 文件时不涉及）

### US-007: 入口统一调用 `enable_windows_utf8_stdio()`
**Description:** 作为 Windows 用户，我希望日志里的中文、emoji、表情在终端显示正常。

**Acceptance Criteria:**
- [ ] 所有 Python 入口（`ink-writer/scripts/ink.py`、`ink-writer/scripts/update_state.py`、`benchmark/e2e_shadow_300.py`、`scripts/quality_dashboard.py`、`scripts/verify_docs.py` 等）在 `if __name__ == "__main__":` 前调用 `runtime_compat.enable_windows_utf8_stdio()`
- [ ] 该函数在 Mac/Linux 下为 no-op（当前实现已满足），不改变 Mac 行为
- [ ] 新增入口使用统一模板

### US-008: 符号链接的跨平台兜底
**Description:** 作为 Windows 用户，我不希望因为未开启开发者模式导致 `symlink` 报错使流程中断。

**Acceptance Criteria:**
- [ ] `scripts/build_reference_corpus.py:245` 的 `dst.symlink_to(...)`：Windows 下优雅降级为 `shutil.copy2`，Mac 保持 `symlink_to`
- [ ] `tests/data_modules/test_path_guard.py` 中的 `link.symlink_to(...)` 增加 `@pytest.mark.skipif(sys.platform == "win32" and not _has_symlink_privilege(), reason="...")`
- [ ] `_has_symlink_privilege()` 工具函数放入 `ink-writer/scripts/runtime_compat.py`，探测失败就跳过
- [ ] Mac 所有符号链接测试照常执行

### US-009: shell 脚本 LF 行结尾强制
**Description:** 作为 Mac 用户，我不希望某天 Windows 贡献者提交了 CRLF 的 `.sh` 让我执行报错。

**Acceptance Criteria:**
- [ ] 新增 `.gitattributes`：`*.sh text eol=lf`、`*.bash text eol=lf`、`*.ps1 text eol=crlf`（PowerShell 传统上 CRLF）
- [ ] 不批量重写现有 `.sh`（保证 Mac 侧 `git diff` 为空）；仅新文件生效
- [ ] 若本地 checkout 已存在 CRLF，在 README 贡献指南注明 `git add --renormalize .`

### US-010: README 新增「Windows 安装」小节
**Description:** 作为 Windows 新手，我希望 README 里有一段从零开始的 Windows 安装步骤，与 Mac 平级。

**Acceptance Criteria:**
- [ ] README 的「安装 → Claude Code」下新增子小节「Windows」
- [ ] 内容包括：Python 3.12+ 安装（winget 示例）、`pip install -r requirements.txt`、`claude plugin marketplace add` 同命令、`.env` 配置的 `%USERPROFILE%\.claude\ink-writer\.env` 路径
- [ ] 标注「仅支持 Claude Code；Gemini CLI / Codex CLI 的 Windows 路径不在本次范围内」
- [ ] Mac / Linux / Claude Code 原有段落**一字不改**
- [ ] 「如何验证」章节的 `python3` 命令示例新增 Windows 对应版 `py -3`

### US-011: CLAUDE.md / AGENTS.md 轻量提示
**Description:** 作为后续开发者，我希望开发指南里告诉我写新代码时要注意 Windows。

**Acceptance Criteria:**
- [ ] `CLAUDE.md` 追加一条「Top 注意事项」：新增 `open()` 必带 `encoding="utf-8"`；新增 Python 入口必调用 `enable_windows_utf8_stdio()`；新增 CLI 路径必跨平台探测
- [ ] `AGENTS.md` / `GEMINI.md` 不动（不在本次 Claude Code 范围内）

### US-012: CI 矩阵加 windows-latest
**Description:** 作为维护者，我希望 CI 上每次 PR 都在 Windows 跑一遍，避免人肉验证。

**Acceptance Criteria:**
- [ ] `.github/workflows/ci-test.yml` 矩阵 `os` 增加 `windows-latest`
- [ ] Windows 下 install 步骤改用 `pip install -r requirements.txt`（跨平台）
- [ ] 原 Ubuntu / macOS 行为不变
- [ ] CI 允许 Windows job 的 skip 数略高于 Mac（符号链接等合理跳过）
- [ ] 不引入新的 Windows 专用 job 以免拖慢 PR

### US-013: Windows 本地 `pytest` 零回归验证
**Description:** 作为需求方，我要求改完后本地在 Windows 跑一次完整 pytest，证明零回归。

**Acceptance Criteria:**
- [ ] 在本机 `E:/AI/AI小说生成/ink-writerPro` 执行 `py -3 -m pytest --no-cov`
- [ ] 结果：`passed` 数 ≥ 2984 减去（因平台合理 skip 的数量，单独列出清单）
- [ ] `failed` 必须为 0
- [ ] 产出 `reports/windows-compat-pytest.txt`，包含 `platform win32`, `Python version`, `collected`, 最终摘要行
- [ ] 有 LLM 依赖的测试若在 Windows 上因缺 API Key 跳过，与 Mac 跳过集合对齐

### US-014: 改动打包成单个 PR，等待用户批准
**Description:** 作为需求方，我要决定是否把改动 push 回 upstream。

**Acceptance Criteria:**
- [ ] 所有改动留在本地分支 `feat/windows-compat`
- [ ] 生成 `reports/windows-compat-changeset.md`：列出新增/修改的文件分类、Mac 分支零影响证据（相关 `.sh` / `README` Mac 段落 `git diff` 为空截图或命令输出）
- [ ] 在用户显式说「可以 push / 提 PR」之前，**不**执行 `git push` 或 `gh pr create`
- [ ] PR 描述模板已备好，包括风险评估与回滚方式

## Functional Requirements

- FR-1：所有 Windows 特化代码必须置于 `if sys.platform == "win32":` 或 `$IsWindows` 分支，Mac/Linux 分支行为与改造前按字节一致
- FR-2：新增入口文件（`.ps1` / `.cmd`）与现有 `.sh` 同目录、同文件名前缀，便于用户发现
- FR-3：所有 Python 文本 IO 显式 `encoding="utf-8"`
- FR-4：所有 Python CLI 入口在 main 之前调用 `runtime_compat.enable_windows_utf8_stdio()`（Mac no-op）
- FR-5：`python3` 命令仅出现在 `.sh` 脚本与面向 Mac 的文档片段中；Windows 侧走 `py -3` 或 `sys.executable`
- FR-6：`asyncio.run` 之前在 Windows 强制 `WindowsProactorEventLoopPolicy`
- FR-7：符号链接相关代码在 Windows 下降级为复制或跳过，不抛异常
- FR-8：`.gitattributes` 锁定 `.sh` 为 LF，`.ps1` 为 CRLF
- FR-9：README 「安装」章节 Claude Code 小节下新增并列的「Windows」子小节；Mac 既有段落零修改
- FR-10：CI 矩阵包含 `windows-latest`；任一平台失败即 PR 阻断
- FR-11：一次性全量改完，单 PR 提交；未经用户显式批准不得 `git push`

## Non-Goals (Out of Scope)

- 不兼容 Gemini CLI 与 Codex CLI 的 Windows 路径（用户明确仅考虑 Claude Code）
- 不把 `.sh` 脚本改写成跨平台 Python 或 Node 版本（用户要求保留 `.sh` 不动）
- 不引入 WSL 强制依赖；Windows 原生 PowerShell / cmd 必须可用
- 不新增功能、不重构既有算法、不调整 checker 阈值
- 不修改 `AGENTS.md` / `GEMINI.md`（非 Claude Code 文档）
- 不修改 FAISS / sentence-transformers 等依赖以强求 Windows 二进制；若安装失败，文档指引切换到 BM25 fallback
- 不支持 Windows 7 / Server 2016 之前系统；目标为 Windows 10 1809+ / 11

## Technical Considerations

- **已有基础设施**：`ink-writer/scripts/runtime_compat.py` 的 `enable_windows_utf8_stdio` 与 `normalize_windows_path` 可直接复用；`filelock` 已跨平台；`run_tests.ps1` 已存在，说明仓库已部分 Windows 感知
- **路径分隔符**：优先使用 `pathlib.Path`；少量字符串拼接的 `/` 在 Windows 上由 Python 容忍，但输出给用户的路径需 `str(Path(...))`
- **终端宽度**：`ink-auto.ps1` 改用 `$Host.UI.RawUI.WindowSize.Width`，而非 `tput cols`
- **依赖**：sentence-transformers 在 Windows 上可装；FAISS 可用 `faiss-cpu` wheel；若装不上走 BM25 fallback（已有降级逻辑）
- **测试运行时间**：首次 Windows pytest 会下载 ST 模型约 400MB；用户已同意等待
- **PR 作用域**：向上游 `cipher-wb/ink-writerPro` 提 PR 必须在用户批准后执行；在此之前所有工作保留在本地分支

## Success Metrics

- Windows 用户从 `git clone` 到跑通 `/ink-auto 1` 的步骤数 ≤ Mac（不含 Python 安装）
- Mac 分支改造前后，`sha256` 对比 `.sh` 文件、README Mac 小节、所有 agent spec 文件：零变化
- Windows `pytest --no-cov` 0 failed；passed ≥ 2984 − (合理 skip 数，预期 ≤ 5)
- Mac `pytest --no-cov` 输出行与改造前一致：`2984 passed, 19 skipped`
- 一条命令（`ink-auto.cmd 5`）在干净 Windows 11 + Python 3.12 环境可成功触发首章生成（人工抽样验证）

## Open Questions（已确认）

- Q1：`ink-writer/commands/` 下 markdown 中的 `bash ink-auto.sh` 调用改为**条件块**（单文件内 Mac/Linux bash + Windows powershell 分支），不建 Windows 副本 — **已确认**
- Q2：CI `windows-latest` job 在 sentence-transformers 安装超时或失败时，以 `INK_EMBED_BACKEND=bm25` 降级跑 pytest — **已确认**
- Q3：PR 目标分支为 upstream `cipher-wb/ink-writerPro` 的 `master`（经确认上游仅此一条活跃主分支）— **已确认**
- Q4：Windows Python 探测顺序 `py -3` → `python3` → `python` — **已确认**
