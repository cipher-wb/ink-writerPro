"""Step 3 审查并发化（优化 A）回归

背景（cipher 实测 2026-04-29）：
  Step 3 单章 13 分钟，触发 rewrite 翻倍到 26 分钟。原因：
  - 核心 8 个 checker 分 3 阶段 + 2 单跑（max=2 并发）→ 5min
  - 条件 7 个 checker **完全串行** → 7min
  - 任一 critical → 整个 Step 3 重跑

优化 A 决策：
  - 核心 8 个一波并发
  - 条件 checker max=K 并发（K=INK_AUTO_REVIEW_CONCURRENCY，默认 8）
  - 每个 checker 独立无数据依赖，并发不影响审查质量
  - 只改 SKILL.md + ink-auto.sh prompt 透传，不改代码

本测试守护：
  1. SKILL.md 不再含旧的"两两并发""按命中顺序串行"提法
  2. SKILL.md 含新的"全并发"指引 + 并发上限通过 INK_AUTO_REVIEW_CONCURRENCY 控制
  3. ink-auto.sh run_chapter prompt 透传 INK_AUTO_REVIEW_CONCURRENCY
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"
INK_WRITE_SKILL = REPO_ROOT / "ink-writer" / "skills" / "ink-write" / "SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_skill_md_documents_full_concurrency():
    """SKILL.md 必须文档化全并发策略。"""
    src = _read(INK_WRITE_SKILL)
    assert "INK_AUTO_REVIEW_CONCURRENCY" in src, (
        "SKILL.md 必须引用 INK_AUTO_REVIEW_CONCURRENCY 环境变量"
    )
    assert "全并发" in src or "一次性 Task" in src or "一波" in src, (
        "SKILL.md 必须明确说核心 8 个 checker 一波并发（不分阶段）"
    )


def test_skill_md_removes_legacy_serial_scheduling():
    """SKILL.md 不能再保留旧的'两两并发''按命中顺序串行'调度文字。

    保留旧文字 LLM 会按旧调度执行，并发优化失效。
    """
    src = _read(INK_WRITE_SKILL)
    # 找到 Step 3 章节
    step3_section_match = re.search(
        r"### Step 3.*?(?=### Step \d|\Z)",
        src, re.DOTALL,
    )
    assert step3_section_match, "应能定位 Step 3 章节"
    step3 = step3_section_match.group(0)

    # 旧"两两并发"必须被新文字取代
    legacy_phrases = [
        "consistency-checker` + `continuity-checker` 并发（最多 2 个）",
        "条件审查器按命中顺序串行",
    ]
    for phrase in legacy_phrases:
        assert phrase not in step3, (
            f"Step 3 章节不能再含旧调度文字 {phrase!r}（会让 LLM 按旧串行调度）"
        )


def test_skill_md_lists_all_8_core_checkers():
    """全并发列表必须含 8 个核心 checker（一个不能少）。"""
    src = _read(INK_WRITE_SKILL)
    core_checkers = [
        "consistency-checker",
        "continuity-checker",
        "ooc-checker",
        "logic-checker",
        "outline-compliance-checker",
        "anti-detection-checker",
        "reader-simulator",
        "flow-naturalness-checker",
    ]
    for checker in core_checkers:
        assert checker in src, f"SKILL.md 必须列出核心 checker {checker}"


def test_skill_md_documents_rate_limit_fallback():
    """SKILL.md 必须说明 rate-limit 时的降级策略。

    不然遇 429 报错就 fail，而不是降并发重试。
    """
    src = _read(INK_WRITE_SKILL)
    assert "rate-limit" in src.lower() or "429" in src, (
        "SKILL.md 必须文档化 API rate-limit 时的降级策略"
    )


def test_ink_auto_sh_passes_concurrency_to_prompt():
    """ink-auto.sh run_chapter 的 prompt 必须透传 INK_AUTO_REVIEW_CONCURRENCY。"""
    src = _read(INK_AUTO_SH)
    m = re.search(
        r"^run_chapter\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m, "应能抠出 run_chapter 函数体"
    body = m.group(1)
    assert "INK_AUTO_REVIEW_CONCURRENCY" in body, (
        "run_chapter 必须在 prompt 里告知 LLM 当前并发上限"
    )
    assert re.search(r'INK_AUTO_REVIEW_CONCURRENCY:-\d+', body), (
        "INK_AUTO_REVIEW_CONCURRENCY 必须有默认值（推荐 8）"
    )


def test_ink_auto_sh_default_concurrency_is_8():
    """默认并发 8（核心 8 个 checker 一波吃完）。"""
    src = _read(INK_AUTO_SH)
    m = re.search(r"INK_AUTO_REVIEW_CONCURRENCY:-(\d+)", src)
    assert m, "INK_AUTO_REVIEW_CONCURRENCY 必须有默认值"
    default = int(m.group(1))
    assert default == 8, (
        f"默认并发应为 8（一波吃完核心 checker）。当前 {default}"
    )


def test_bash_syntax_check():
    """ink-auto.sh 必须通过 bash -n。"""
    import shutil
    import subprocess
    if shutil.which("bash") is None:
        import pytest
        pytest.skip("需要 bash")
    result = subprocess.run(
        ["bash", "-n", str(INK_AUTO_SH)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, f"语法失败:\n{result.stderr}"
