"""US-011 Mac 端 `ralph.sh` 专项回归：端到端 smoke + COMPLETE 信号检测收紧。

针对 PRD `cross-platform-audit` US-011 的验收准则：
  - 定位 Mac 上 ralph.sh 的具体异常点（候选：COMPLETE grep 误命中 / iteration 退出码吞没 / stderr 吞吐）
  - pytest + subprocess 模拟一轮 iteration + `<promise>COMPLETE</promise>`，验证脚本 exit 0 且归档路径正确
  - Mac 实跑一轮 mock fake claude（不调真 API），端到端绿

测试策略：
  - 构造临时目录，拷入真实 `scripts/ralph/ralph.sh` + 精简 `prd.json` / `CLAUDE.md`
  - 通过 PATH prepend 注入一个 fake `claude` shell 脚本（子场景决定输出内容 + 退出码）
  - 子场景：
      A. sentinel 独占一行 → exit 0
      B. prose 里提到 sentinel 字面量（防误命中）→ 继续跑完 max_iterations, exit 1
      C. 无 sentinel → 跑完 max_iterations, exit 1
      D. fake claude 非零退出 → ralph.sh 不因 `set -e` / pipefail 崩溃（`|| LLM_EXIT=$?` 兜底）
      E. LLM_EXIT 日志可见（defensive 日志固化）

注：ralph.sh 依赖 `jq` 解析 prd.json + `tee /dev/stderr` + `sleep`——纯 Unix 命令，Windows 上不跑。
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RALPH_SH = REPO_ROOT / "scripts" / "ralph" / "ralph.sh"


pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="ralph.sh 是 Unix 入口，Windows 走 ralph.ps1"),
    pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash 可执行"),
    pytest.mark.skipif(shutil.which("jq") is None, reason="ralph.sh 依赖 jq 解析 prd.json"),
]


def _write_fake_claude(dir_: Path, *, stdout: str, exit_code: int = 0) -> Path:
    """写一个 fake claude shell 脚本（忽略所有参数 / stdin，只按固定输出+退出码返回）。"""
    fake = dir_ / "claude"
    # 用 printf 以保持多行字面量——heredoc 避免字符串字面量里转义踩坑
    script = (
        "#!/bin/bash\n"
        "# fake claude for ralph.sh smoke test\n"
        "# 吞掉 stdin（ralph.sh 用 `< CLAUDE.md` 喂进来）防止 SIGPIPE\n"
        "cat > /dev/null || true\n"
        f"cat <<'FAKE_CLAUDE_EOF'\n{stdout}\nFAKE_CLAUDE_EOF\n"
        f"exit {int(exit_code)}\n"
    )
    fake.write_text(script, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return fake


def _setup_ralph_workdir(tmp_path: Path, *, branch_name: str = "ralph/smoke-test") -> Path:
    """复制 ralph.sh + 造最小 prd.json / CLAUDE.md 到独立工作目录。"""
    workdir = tmp_path / "ralph_workdir"
    workdir.mkdir()
    # 拷真实 ralph.sh（不 symlink——跨平台 parity 更稳）
    dst_sh = workdir / "ralph.sh"
    dst_sh.write_text(RALPH_SH.read_text(encoding="utf-8"), encoding="utf-8")
    dst_sh.chmod(dst_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # 最小 prd.json（仅 ralph.sh 归档/branch-track 路径需要）
    (workdir / "prd.json").write_text(
        '{"project":"smoke","branchName":"%s","userStories":[]}' % branch_name,
        encoding="utf-8",
    )
    # 最小 CLAUDE.md（内容任意，ralph.sh 会 cat 它喂给 claude stdin）
    (workdir / "CLAUDE.md").write_text(
        "# Smoke CLAUDE.md\n\nDo the thing.\n<promise>COMPLETE</promise>  <-- 这是 prompt 里的提示，"
        "不是响应信号；COMPLETE 检测必须能把它和响应末尾的独立行区分开。\n",
        encoding="utf-8",
    )
    return workdir


def _run_ralph(
    workdir: Path,
    fake_claude_dir: Path,
    *,
    max_iterations: int = 1,
    extra_timeout: float = 30.0,
) -> subprocess.CompletedProcess:
    """运行 ralph.sh 并捕获 stdout+stderr。"""
    env = os.environ.copy()
    # 把 fake claude 前置到 PATH 最前面
    env["PATH"] = f"{fake_claude_dir}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        [
            "bash",
            str(workdir / "ralph.sh"),
            "--tool",
            "claude",
            str(max_iterations),
        ],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=max(15.0, extra_timeout + max_iterations * 5.0),
        check=False,
    )


# ----- 场景 A: sentinel 独占一行 → exit 0 -----


def test_completes_when_sentinel_is_on_its_own_line(tmp_path):
    """fake claude 输出里含独立行 `<promise>COMPLETE</promise>` → ralph.sh 应 exit 0 并在 iter 1 退出。"""
    workdir = _setup_ralph_workdir(tmp_path)
    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    _write_fake_claude(
        fake_dir,
        stdout="I implemented story US-XXX.\nAll good.\n<promise>COMPLETE</promise>\n",
        exit_code=0,
    )

    result = _run_ralph(workdir, fake_dir, max_iterations=3)

    assert result.returncode == 0, (
        f"ralph.sh 应识别 COMPLETE 信号并 exit 0。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # 合并流（stdout/stderr 都可）里应提到 completed
    combined = result.stdout + result.stderr
    assert "Ralph completed all tasks!" in combined
    # iteration 退出日志应为 1（早退）而非 3
    assert "Completed at iteration 1 of 3" in combined


# ----- 场景 B: prose 里提及 sentinel 字面量 → 不应误命中 -----


def test_does_not_false_positive_on_inline_sentinel_mention(tmp_path):
    """fake claude 把 sentinel 写在散文/代码块注释里（非独立行）→ 绝不视为完成信号。

    ralph.sh 收紧后应：继续跑完 max_iterations=2 并 exit 1，而不是错在 iter 1 误报完成。
    """
    workdir = _setup_ralph_workdir(tmp_path)
    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    inline = (
        "I will emit the <promise>COMPLETE</promise> sentinel once all US are done.\n"
        "For now I'm still working.\n"
        "Mentioning <promise>COMPLETE</promise> inline does not count as a real signal.\n"
    )
    _write_fake_claude(fake_dir, stdout=inline, exit_code=0)

    result = _run_ralph(workdir, fake_dir, max_iterations=2)

    assert result.returncode == 1, (
        "prose 里提到 sentinel 字面量不应触发完成——ralph.sh 应跑满 max_iterations 后 exit 1。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "reached max iterations" in combined
    assert "Ralph completed all tasks!" not in combined


# ----- 场景 C: 纯无信号输出 → 跑满 max_iterations, exit 1 -----


def test_runs_full_iterations_without_sentinel(tmp_path):
    workdir = _setup_ralph_workdir(tmp_path)
    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    _write_fake_claude(fake_dir, stdout="doing work...\nstill going.\n", exit_code=0)

    result = _run_ralph(workdir, fake_dir, max_iterations=2)

    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "reached max iterations (2)" in combined
    # defensive 日志：每轮都应打 iter / llm_exit
    assert "[ralph] iteration 1 tool=claude llm_exit=0" in combined
    assert "[ralph] iteration 2 tool=claude llm_exit=0" in combined


# ----- 场景 D: fake claude 非零退出 → ralph.sh 不 crash -----


def test_nonzero_llm_exit_does_not_abort_ralph_loop(tmp_path):
    """fake claude 故意 exit 17——ralph.sh 的 `|| LLM_EXIT=$?` 应兜住，继续 loop 直到 max_iterations。

    这条测试同时守护 `set -e` + `set -o pipefail` 的联合行为：
      - pipefail 让 `claude | tee` 继承 claude 的退出码
      - `|| LLM_EXIT=$?` 显式捕获后脚本继续
    """
    workdir = _setup_ralph_workdir(tmp_path)
    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    _write_fake_claude(fake_dir, stdout="claude crashed, exit 17\n", exit_code=17)

    result = _run_ralph(workdir, fake_dir, max_iterations=2)

    assert result.returncode == 1, (
        "ralph.sh 应兜住 claude 非零退出并跑满 max_iterations。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    # 退出码日志应显式记录
    assert "[ralph] iteration 1 tool=claude llm_exit=17" in combined
    assert "[ralph] iteration 2 tool=claude llm_exit=17" in combined
    # 最终仍按 max_iterations 路径收尾
    assert "reached max iterations (2)" in combined


# ----- 场景 E: 归档路径计算（branch 变更）-----


def test_archive_path_strips_ralph_prefix(tmp_path):
    """当 .last-branch 和 prd.json branchName 不一致时，archive/<date>-<name> 目录应被创建，
    name 部分必须是去掉 `ralph/` 前缀的。这里验证路径计算逻辑（US-011 候选异常点之一）。
    """
    workdir = _setup_ralph_workdir(tmp_path, branch_name="ralph/new-run")
    # 伪造 .last-branch 指向旧分支（有 ralph/ 前缀）
    (workdir / ".last-branch").write_text("ralph/old-run\n", encoding="utf-8")
    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    _write_fake_claude(fake_dir, stdout="<promise>COMPLETE</promise>\n", exit_code=0)

    result = _run_ralph(workdir, fake_dir, max_iterations=1)

    assert result.returncode == 0, (
        f"ralph.sh 应成功归档并识别 COMPLETE。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    archive_dir = workdir / "archive"
    assert archive_dir.is_dir(), "archive/ 目录应已创建"
    # 找到形如 `<YYYY-MM-DD>-old-run` 的子目录（name 必须去 ralph/ 前缀）
    subdirs = [p for p in archive_dir.iterdir() if p.is_dir()]
    assert subdirs, f"archive/ 下应有归档子目录，实际：{list(archive_dir.iterdir())}"
    names = [p.name for p in subdirs]
    assert any(n.endswith("-old-run") for n in names), (
        f"归档目录名必须以 '-old-run' 结尾（证明 ralph/ 前缀已剥离），实际：{names}"
    )
    # 同时验证 .last-branch 已被更新为新分支
    assert (workdir / ".last-branch").read_text(encoding="utf-8").strip() == "ralph/new-run"


# ----- 场景 F: 源码级红线——sentinel 检测必须带行锚定 -----


def test_ralph_sh_sentinel_check_is_line_anchored():
    """源码级守护：COMPLETE 检测行必须包含行锚定（`^...$`），否则任何散文提及都会误命中。

    若未来有人把 grep 改回裸字面量 `grep -q "<promise>COMPLETE</promise>"`，此测试挂 CI。
    """
    text = RALPH_SH.read_text(encoding="utf-8")
    assert "<promise>COMPLETE</promise>" in text
    # 必须出现带 `^` 或 `\$` 的锚定形式
    assert "'^" in text and "COMPLETE</promise>" in text, (
        "ralph.sh 的 COMPLETE 检测必须带行锚定 `^...$`，否则 prose 提及会误命中。"
    )


def test_ralph_ps1_sentinel_check_is_multiline_anchored():
    ps1 = (REPO_ROOT / "scripts" / "ralph" / "ralph.ps1").read_text(encoding="utf-8")
    # PowerShell 多行锚定标志
    assert "(?m)" in ps1 and "<promise>COMPLETE</promise>" in ps1, (
        "ralph.ps1 的 COMPLETE 检测必须带 `(?m)` 多行模式 + 行锚定，保持与 ralph.sh 语义一致。"
    )
