"""US-004 ink-auto 字数硬上限对称阻断 + 精简循环回归。

覆盖 ink-auto.sh / ink-auto.ps1 在 `> MAX_WORDS_HARD` 场景下必须对称阻断：
  - verify_chapter 返回 1 ←→ 触发重试分流
  - MAX_WORDS_HARD 从 `.ink/preferences.json` 的 `pacing.chapter_words + 500` 推导
  - 默认值 5000（preferences.json 缺失 / JSON 损坏 / 字段缺失均回落）
  - 硬下限 2200 字节级保留（零回归）

测试分两层：
  - 黑盒：抠 verify_chapter 函数体 + 构造 `正文/第XXXX章.md` fixture，注入各种字数
    并观察 bash 子 shell 返回码，类似 test_ink_auto_smoke 的 harness 模式
  - 源码级守护：grep 断言上限分支、SHRINK_MAX_ROUNDS、.ps1 对等与 UTF-8 BOM 不被
    悄悄改回
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"
INK_AUTO_PS1 = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.ps1"

pytestmark = [
    pytest.mark.mac,
    pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash 可执行"),
]


def _extract_bash_function(source: str, fn_name: str) -> str:
    pattern = re.compile(
        r"^" + re.escape(fn_name) + r"\s*\(\s*\)\s*\{\s*\n(?P<body>.*?)\n\}\s*\n",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        raise AssertionError(f"未能从 ink-auto.sh 抠到 {fn_name} 函数体")
    return f"{fn_name}() {{\n{m.group('body')}\n}}\n"


def _write_chapter(project_root: Path, chapter: int, char_count: int) -> Path:
    """在 project_root/正文 下生成指定字数的章节文件。

    `wc -m` 按字符计数；纯 ASCII 文件里每个字符 1 字节，文件末尾的换行也算 1。
    为了让 `wc -m` 恰好返回 ``char_count``，我们写入 ``char_count - 1`` 个字符 + 末尾 `\n`。
    """
    padded = f"{chapter:04d}"
    dest = project_root / "正文"
    dest.mkdir(parents=True, exist_ok=True)
    chapter_file = dest / f"第{padded}章-测试.md"
    # char_count 包含 trailing newline
    body_len = max(0, char_count - 1)
    chapter_file.write_text("a" * body_len + "\n", encoding="utf-8")
    # 摘要文件：verify_chapter 最后一层 gate
    summary_dir = project_root / ".ink" / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / f"ch{padded}.md").write_text("summary\n", encoding="utf-8")
    return chapter_file


def _run_verify(
    tmp_path: Path,
    char_count: int,
    *,
    max_words_hard: int = 5000,
    chapter: int = 1,
    current_chapter: int = 1,
) -> int:
    """构造最小子 shell 执行 verify_chapter，返回 bash 退出码。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    verify_body = _extract_bash_function(src, "verify_chapter")

    project_root = tmp_path / "proj"
    project_root.mkdir()
    _write_chapter(project_root, chapter, char_count)

    # 提前生成 wc -m 实测值，方便调试（编码显式 utf-8 满足 subprocess 跨平台红线）
    chapter_file = next(iter((project_root / "正文").glob(f"第{chapter:04d}章*.md")))
    with open(chapter_file, "rb") as fh:
        actual_wc = subprocess.run(
            ["wc", "-m"], stdin=fh,
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout.strip().split()[0]

    script = (
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        f"PROJECT_ROOT={str(project_root)!r}\n"
        f"MAX_WORDS_HARD={max_words_hard}\n"
        # stub get_current_chapter
        f"get_current_chapter() {{ echo {current_chapter}; }}\n"
        f"{verify_body}\n"
        f'verify_chapter {chapter}; echo "[rc=$?][wc={actual_wc}]"\n'
    )
    script_file = tmp_path / "harness.sh"
    script_file.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(script_file)],
        capture_output=True, text=True, encoding="utf-8",
        timeout=15, check=False,
    )
    # 解析 rc=N
    match = re.search(r"\[rc=(\d+)\]", result.stdout)
    assert match, f"未解析到 rc，output:\n{result.stdout}\nstderr:\n{result.stderr}"
    return int(match.group(1))


# ═══════════════════════════════════════════
# 黑盒：verify_chapter 分支矩阵
# ═══════════════════════════════════════════


def test_verify_chapter_passes_within_limits(tmp_path):
    """2200 ≤ wc ≤ MAX_WORDS_HARD → rc=0（合格放行）。"""
    rc = _run_verify(tmp_path, char_count=3000, max_words_hard=5000)
    assert rc == 0


def test_verify_chapter_fails_on_lower_floor(tmp_path):
    """wc < 2200 → rc=1（US-004 零回归：硬下限保留）。"""
    rc = _run_verify(tmp_path, char_count=1500, max_words_hard=5000)
    assert rc == 1


def test_verify_chapter_fails_on_upper_limit(tmp_path):
    """wc > MAX_WORDS_HARD → rc=1（US-004 核心：上限对称阻断）。"""
    rc = _run_verify(tmp_path, char_count=6000, max_words_hard=5000)
    assert rc == 1


def test_verify_chapter_fails_on_upper_limit_custom(tmp_path):
    """自定义 MAX_WORDS_HARD=3500（preferences.json chapter_words=3000 场景）：
    3800 字应阻断。
    """
    rc = _run_verify(tmp_path, char_count=3800, max_words_hard=3500)
    assert rc == 1


def test_verify_chapter_passes_at_upper_boundary(tmp_path):
    """wc == MAX_WORDS_HARD → rc=0（边界：使用 `>` 而非 `>=`，边界是合格区）。"""
    rc = _run_verify(tmp_path, char_count=5000, max_words_hard=5000)
    assert rc == 0


# ═══════════════════════════════════════════
# 源码级守护（防止未来 PR 悄悄回退）
# ═══════════════════════════════════════════


def test_ink_auto_sh_verify_chapter_has_upper_bound():
    """ink-auto.sh:verify_chapter 必须对称检查 `char_count > MAX_WORDS_HARD`。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "verify_chapter")
    assert "char_count < 2200" in body, "硬下限 2200 分支不得弱化（零回归红线）"
    assert "char_count > MAX_WORDS_HARD" in body, (
        "verify_chapter 必须含 `char_count > MAX_WORDS_HARD` 对称上限分支"
    )


def test_ink_auto_sh_max_words_hard_derivation_exists():
    """ink-auto.sh 顶部必须从 preferences.json 推导 MAX_WORDS_HARD，含默认 5000 兜底。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "MAX_WORDS_HARD=" in src, "必须定义 MAX_WORDS_HARD 变量"
    assert "preferences.json" in src, "MAX_WORDS_HARD 必须读 preferences.json"
    assert "pacing" in src and "chapter_words" in src, (
        "MAX_WORDS_HARD 派生必须基于 pacing.chapter_words（US-002 schema）"
    )


def test_ink_auto_sh_shrink_max_rounds_is_three():
    """精简循环最多 3 轮（与 SKILL.md 2A.5 对齐）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert re.search(r"SHRINK_MAX_ROUNDS\s*=\s*3", src), (
        "SHRINK_MAX_ROUNDS 必须为 3"
    )


def test_ink_auto_sh_retry_loop_uses_shrink_bound():
    """主重试流程必须按 MAX_WORDS_HARD 分流：over-limit 用 SHRINK_MAX_ROUNDS，
    下限/其它失败保持 1 轮（零回归）。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "WC_FAIL" in src and "MAX_WORDS_HARD" in src, (
        "重试流程必须含基于 MAX_WORDS_HARD 的失败原因分流"
    )
    assert "MAX_RETRIES=$SHRINK_MAX_ROUNDS" in src, (
        "over-limit 分支必须使用 SHRINK_MAX_ROUNDS"
    )
    assert re.search(r"MAX_RETRIES=1\b", src), (
        "其它失败分支必须保持 1 轮重试（补写循环零回归）"
    )


# ═══════════════════════════════════════════
# .ps1 对等守护
# ═══════════════════════════════════════════


def test_ink_auto_ps1_test_chapter_has_upper_bound():
    ps1 = INK_AUTO_PS1.read_text(encoding="utf-8")
    assert "$chars -lt 2200" in ps1, "硬下限 2200 分支不得弱化"
    assert "$chars -gt $MaxWordsHard" in ps1, (
        "Test-Chapter 必须含 `$chars -gt $MaxWordsHard` 对称上限分支"
    )


def test_ink_auto_ps1_max_words_hard_derivation_exists():
    ps1 = INK_AUTO_PS1.read_text(encoding="utf-8")
    assert "$MaxWordsHard" in ps1, "必须定义 MaxWordsHard 变量"
    assert "preferences.json" in ps1, "MaxWordsHard 必须读 preferences.json"
    assert "pacing" in ps1 and "chapter_words" in ps1, (
        "MaxWordsHard 派生必须基于 pacing.chapter_words"
    )
    assert re.search(r"\$MaxWordsHard\s*=\s*5000", ps1), (
        ".ps1 默认 MaxWordsHard = 5000（与 .sh 对等）"
    )


def test_ink_auto_ps1_shrink_max_rounds_is_three():
    ps1 = INK_AUTO_PS1.read_text(encoding="utf-8")
    assert re.search(r"\$ShrinkMaxRounds\s*=\s*3", ps1), (
        "ShrinkMaxRounds 必须为 3"
    )


def test_ink_auto_ps1_retry_loop_uses_shrink_bound():
    ps1 = INK_AUTO_PS1.read_text(encoding="utf-8")
    assert "$MaxWordsHard" in ps1 and "$wcFail" in ps1, (
        ".ps1 重试流程必须含基于 $MaxWordsHard 的失败原因分流"
    )
    assert "$maxRetries = $ShrinkMaxRounds" in ps1, (
        "over-limit 分支必须使用 $ShrinkMaxRounds"
    )
    assert re.search(r"\$maxRetries\s*=\s*1\b", ps1), (
        "其它失败分支必须保持 1 轮重试（补写循环零回归）"
    )


def test_ink_auto_ps1_preserves_utf8_bom():
    """US-004 改动后 PS 5.1 UTF-8 BOM 必须保留（跨 US 的仓库红线）。"""
    head = INK_AUTO_PS1.read_bytes()[:3]
    assert head == b"\xef\xbb\xbf", (
        f"ink-auto.ps1 必须以 UTF-8 BOM 开头，实际前 3 字节：{head!r}"
    )
