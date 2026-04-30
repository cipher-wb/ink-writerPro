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


# ═══════════════════════════════════════════
# task #10（2026-04-30）：Bug A 字数微超 → 轻量裁切（shrink）回归
# 历史现象：第 5 章 2191 字超 fanqie 默认 2000 上限 9% → 旧分支跑完整
# retry_chapter（30+ min）。新分支用 shrink_chapter 只删字（< 3 min）。
# ═══════════════════════════════════════════


def test_ink_auto_sh_shrink_chapter_function_exists():
    """ink-auto.sh 必须定义 shrink_chapter 函数（Bug A 治理产物）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert re.search(r"^shrink_chapter\s*\(\s*\)\s*\{", src, re.MULTILINE), (
        "ink-auto.sh 必须定义 shrink_chapter() 函数（task #10 字数微超轻量裁切）"
    )


def test_ink_auto_sh_shrink_chapter_only_deletes():
    """shrink_chapter 的 LLM prompt 必须含『只能删字、不能加字』硬约束 + 不调
    13 步流程，否则 fallthrough 退化成完整重写就破坏整改意图。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "shrink_chapter")
    # 关键硬约束：只删不加 + 不重跑 13 步
    assert "只能删字" in body, "shrink prompt 必须含『只能删字』硬约束"
    assert "不能加字" in body or "绝对不能加字" in body, (
        "shrink prompt 必须显式禁止扩写"
    )
    assert "13 步" in body or "ink-write" in body, (
        "shrink prompt 必须明确『不需要走 13 步流程』，否则 LLM 可能误触发"
    )
    # Edit 工具：避免 LLM 用 Write 整体覆写丢内容
    assert "Edit" in body, "shrink prompt 必须要求用 Edit 工具（不是 Write 覆写）"


def test_ink_auto_sh_shrink_chapter_verifies_final_count():
    """shrink_chapter 必须用 wc -m 验证最终字数 ≤ target_max（容差 100），
    防止 LLM 没真删够字就返回 INK_SHRINK_DONE。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "shrink_chapter")
    assert "final_count" in body and "wc -m" in body, (
        "shrink_chapter 必须 post-hoc 用 wc -m 校验最终字数"
    )
    # 容差 100 字（避免被 LLM 微小溢出搞 false-fail）
    assert "target_max + 100" in body, (
        "shrink_chapter 必须含 100 字容差（避免 LLM 极接近上限时 false-fail）"
    )


def test_ink_auto_sh_shrink_chapter_uses_short_timeout():
    """shrink 是轻量任务，超时必须明显短于完整 retry_chapter（默认 3600s），
    否则 Bug A 治理失效——超时太长依然要等几十分钟。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "shrink_chapter")
    # 超时必须是 1200s（20min）以下，且明确写在 run_cli_process 第三个参数
    m = re.search(r'run_cli_process\s+"\$prompt"\s+"\$log_file"\s+(\d+)', body)
    assert m, "shrink_chapter 必须用 run_cli_process 启动 LLM 子进程"
    timeout = int(m.group(1))
    assert timeout <= 1200, (
        f"shrink 超时必须 ≤ 1200s（20min，比完整 retry 短一档）；当前 {timeout}s"
    )


def test_ink_auto_sh_main_loop_dispatches_to_shrink_on_overlimit():
    """主循环字数超限分支必须调 shrink_chapter（不是 retry_chapter），
    否则 task #10 整改无效。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 找到 WC_FAIL > MAX_WORDS_HARD 的分支
    m = re.search(
        r"if\s*\(\(\s*WC_FAIL\s*>\s*MAX_WORDS_HARD\s*\)\)\s*;\s*then(?P<branch>.*?)\belse\b",
        src, re.DOTALL,
    )
    assert m, "主循环必须有 WC_FAIL > MAX_WORDS_HARD 分支"
    branch = m.group("branch")
    assert "shrink_chapter" in branch, (
        "字数超限分支必须调 shrink_chapter（不是 retry_chapter）；否则 Bug A 整改失效"
    )
    assert "retry_chapter" not in branch, (
        "字数超限分支不得再调 retry_chapter（会触发完整 13 步重写）"
    )


def test_ink_auto_sh_env_var_overrides_max_words_hard():
    """INK_AUTO_MAX_WORDS_HARD 环境变量必须能覆盖默认 MAX_WORDS_HARD
    （cipher 实测：fanqie 默认 2000 太严，章节 2191 字也算超）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "INK_AUTO_MAX_WORDS_HARD" in src, (
        "ink-auto.sh 必须支持 INK_AUTO_MAX_WORDS_HARD 环境变量覆盖"
    )
    # 数字校验 + 实际赋值
    assert re.search(
        r'INK_AUTO_MAX_WORDS_HARD.*=~\s*\^\[0-9\]\+\$', src
    ), "INK_AUTO_MAX_WORDS_HARD 必须做数字校验"
    assert re.search(
        r'MAX_WORDS_HARD\s*=\s*"\$INK_AUTO_MAX_WORDS_HARD"', src
    ), "INK_AUTO_MAX_WORDS_HARD 必须真正覆盖 MAX_WORDS_HARD"


def test_ink_auto_sh_env_var_overrides_min_words_hard():
    """INK_AUTO_MIN_WORDS_HARD 环境变量也必须支持（对称设计——既然能放宽
    上限，也得能放宽下限以备特殊章节如序章/尾声）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "INK_AUTO_MIN_WORDS_HARD" in src, (
        "ink-auto.sh 必须支持 INK_AUTO_MIN_WORDS_HARD 环境变量覆盖（对称设计）"
    )
    assert re.search(
        r'MIN_WORDS_HARD\s*=\s*"\$INK_AUTO_MIN_WORDS_HARD"', src
    ), "INK_AUTO_MIN_WORDS_HARD 必须真正覆盖 MIN_WORDS_HARD"


def test_ink_auto_sh_shrink_chapter_handles_missing_file():
    """如果章节文件不存在（罕见但可能：归档误删 / 路径异常），shrink_chapter
    必须返回 1 而非崩溃，让外层重试逻辑接管。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "shrink_chapter")
    # 必须有文件存在性 guard
    assert re.search(r'\[\[\s*-z\s+"\$watch_file"\s*\|\|\s*!\s+-f\s+"\$watch_file"', body), (
        "shrink_chapter 必须先 guard 章节文件存在性，缺失时返回 1"
    )


def test_ink_auto_sh_shrink_skips_when_already_compliant():
    """如果章节已经 ≤ target_max（中途被人手动改过 / 验证误判），
    shrink_chapter 必须直接 return 0 而不调 LLM 浪费 token。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "shrink_chapter")
    # 必须有 need_cut <= 0 短路
    assert re.search(r'need_cut\s*<=\s*0', body), (
        "shrink_chapter 必须含 need_cut<=0 短路（避免无谓调 LLM）"
    )


# ═══════════════════════════════════════════
# task #11（2026-04-30）：Bug A 孪生 — 字数不足走 grow_chapter 轻量扩写
# 历史现象：第 6 章 2009 字 < 2200 下限 → 旧分支跑完整 retry_chapter（30+ min
# 重写 13 步）+ 重写又只写出 2009 字 → 中止。新分支用 grow_chapter 只加段落。
# ═══════════════════════════════════════════


def test_ink_auto_sh_grow_chapter_function_exists():
    """ink-auto.sh 必须定义 grow_chapter 函数（task #11 字数不足轻量扩写）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert re.search(r"^grow_chapter\s*\(\s*\)\s*\{", src, re.MULTILINE), (
        "ink-auto.sh 必须定义 grow_chapter() 函数"
    )


def test_ink_auto_sh_grow_chapter_only_adds():
    """grow_chapter 的 LLM prompt 必须含『只能加字、不能删字』+ 不重跑 13 步。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "grow_chapter")
    assert "只能加字" in body, "grow prompt 必须含『只能加字』硬约束"
    assert "不能删字" in body or "绝对不能删字" in body, (
        "grow prompt 必须显式禁止删字"
    )
    # 关键：不能改剧情节拍（防止 LLM 顺手"优化"原文）
    assert "不能改剧情" in body, "grow prompt 必须禁止改剧情"
    assert "13 步" in body or "ink-write" in body, (
        "grow prompt 必须明确『不需要走 13 步流程』"
    )
    # Edit 工具：避免 Write 整体覆写
    assert "Edit" in body, "grow prompt 必须要求用 Edit 工具"


def test_ink_auto_sh_grow_chapter_caps_max():
    """grow_chapter 必须告知 LLM 上限并在 post-hoc 校验时同时检查 max
    （防止扩写过头反而触发 shrink，浪费一次 LLM 调用）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "grow_chapter")
    # prompt 里必须显示上限（拒绝爆上限）
    assert "目标上限" in body and "${target_max}" in body, (
        "grow prompt 必须传 target_max 给 LLM（避免扩过头）"
    )
    # post-hoc 必须同时检查 min/max
    assert "target_min - 100" in body, (
        "grow_chapter 必须含『最终字数 ≥ target_min - 100』容差校验"
    )
    assert "target_max + 100" in body, (
        "grow_chapter 必须含『最终字数 ≤ target_max + 100』防扩过头"
    )


def test_ink_auto_sh_grow_chapter_uses_short_timeout():
    """grow 是轻量任务（与 shrink 对称），超时 ≤ 1200s。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "grow_chapter")
    m = re.search(r'run_cli_process\s+"\$prompt"\s+"\$log_file"\s+(\d+)', body)
    assert m, "grow_chapter 必须用 run_cli_process 启动 LLM 子进程"
    timeout = int(m.group(1))
    assert timeout <= 1200, (
        f"grow 超时必须 ≤ 1200s（与 shrink 对称）；当前 {timeout}s"
    )


def test_ink_auto_sh_grow_max_rounds_is_three():
    """扩写循环 3 轮（与 shrink 对称）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert re.search(r"GROW_MAX_ROUNDS\s*=\s*3", src), "GROW_MAX_ROUNDS 必须为 3"


def test_ink_auto_sh_main_loop_dispatches_to_grow_on_underlimit():
    """主循环字数不足分支必须调 grow_chapter（不再是 retry_chapter）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 不足分支：< MIN_WORDS_HARD 且章节文件存在 → grow
    m = re.search(
        r"elif\s*\(\(\s*WC_FAIL\s*>\s*0\s*\)\)\s*&&\s*\(\(\s*WC_FAIL\s*<\s*MIN_WORDS_HARD\s*\)\)(?P<branch>.*?)\belse\b",
        src, re.DOTALL,
    )
    assert m, "主循环必须有 WC_FAIL > 0 && WC_FAIL < MIN_WORDS_HARD 分支"
    branch = m.group("branch")
    assert "grow_chapter" in branch, "字数不足分支必须调 grow_chapter（不是 retry_chapter）"
    assert "retry_chapter" not in branch, (
        "字数不足分支不得再调 retry_chapter（会触发完整 13 步重写）"
    )
    # 必须传 MIN/MAX 双参（让 grow 知道扩到哪、不能超到哪）
    assert "$MIN_WORDS_HARD" in branch and "$MAX_WORDS_HARD" in branch, (
        "grow 调用必须同时传 MIN（目标）和 MAX（上限）"
    )


def test_ink_auto_sh_grow_handles_missing_file():
    """章节文件不存在时不能走 grow（应该走 retry_chapter 全章重写）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 不足分支必须含『章节文件存在性』gate
    m = re.search(
        r"elif\s*\(\(\s*WC_FAIL\s*>\s*0\s*\)\)\s*&&\s*\(\(\s*WC_FAIL\s*<\s*MIN_WORDS_HARD\s*\)\).*?\bthen\b",
        src, re.DOTALL,
    )
    assert m, "字数不足分支必须有条件守卫"
    # 看条件链是否含 -f 文件存在 check
    cond = m.group(0)
    assert "-f" in cond or "_ch_file" in cond, (
        "字数不足分支必须 gate 章节文件存在性，缺失时走 retry_chapter 全章重写"
    )


def test_ink_auto_sh_grow_skips_when_already_compliant():
    """如果章节已经 ≥ target_min（手动加过），grow_chapter 直接 return 0。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    body = _extract_bash_function(src, "grow_chapter")
    assert re.search(r'need_add\s*<=\s*0', body), (
        "grow_chapter 必须含 need_add<=0 短路（避免无谓调 LLM）"
    )
