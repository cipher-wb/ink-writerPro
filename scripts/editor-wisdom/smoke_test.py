#!/usr/bin/env python3
"""End-to-end smoke test: prove the hard gate actually blocks a bad chapter.

Usage:
    python scripts/editor-wisdom/smoke_test.py [--project-root PATH]

If ANTHROPIC_API_KEY is absent, exits 0 with status 'skipped'.
Produces reports/editor-wisdom-smoke-report.md.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _check_api_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    import shutil
    return shutil.which("claude") is not None


def _ensure_index(report_lines: list[str]) -> bool:
    """Rebuild index if vector_index is missing. Returns True if index is ready."""
    index_dir = PROJECT_ROOT / "data" / "editor-wisdom" / "vector_index"
    if index_dir.exists() and (index_dir / "rules.faiss").exists():
        report_lines.append("- Index already exists, skipping rebuild")
        return True

    report_lines.append("- Vector index missing, running rebuild...")
    from ink_writer.editor_wisdom.cli import cmd_rebuild

    t0 = time.time()
    rc = cmd_rebuild()
    elapsed = time.time() - t0
    report_lines.append(f"- Rebuild finished in {elapsed:.1f}s (exit={rc})")
    return rc == 0


BAD_CHAPTER = """第一章 重生

我睁开了眼睛。我重生了。我拥有了无敌的力量。

"哈哈哈！"我笑了起来。我太强了。没有人是我的对手。

然后我看到了一个人。那个人很弱。我一拳就把他打飞了。

"太弱了。"我说。

然后又来了一个人。我又一拳打飞了他。

"还是太弱了。"

我走在大街上，所有人都在看我。我无敌了。我很开心。

然后我回家了。睡觉了。第一天结束了。

---

这就是我重生后的第一天。一切都很好。明天会更好。

然后我想：我的目标是什么？嗯，大概是变得更强吧。

于是我决定去修炼。修炼很简单，因为我有金手指。

金手指很厉害。我一天就突破了三个境界。

"太简单了。"我说。

周围的人都惊呆了。"这怎么可能？"他们说。

"因为我有金手指啊。"我心里想，但是没有说出来。

然后我又突破了一个境界。现在我是全城最强的人了。

大家都很佩服我。城主也来了，说要把女儿嫁给我。

"好的。"我说。

就这样，我成为了城主的女婿。生活真是太美好了。
"""


def _run_gate(report_lines: list[str]) -> tuple[bool, int, str | None]:
    """Run the real review gate on the bad chapter.

    Returns (blocked, attempts, blocked_path).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        chapter_dir = tmp_root / "chapters" / "1"
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "draft.md").write_text(BAD_CHAPTER, encoding="utf-8")

        from ink_writer.editor_wisdom.checker import check_chapter
        from ink_writer.editor_wisdom.config import load_config
        from ink_writer.editor_wisdom.retriever import Retriever
        from ink_writer.editor_wisdom.review_gate import run_review_gate

        config = load_config()
        retriever = Retriever()

        polish_call_count = 0

        def checker_fn(text: str, ch_no: int) -> dict:
            rules = retriever.retrieve(text)
            return check_chapter(text, ch_no, rules, config=config)

        def polish_fn(text: str, violations: list[dict], ch_no: int) -> str:
            nonlocal polish_call_count
            polish_call_count += 1
            report_lines.append(
                f"  - Polish attempt {polish_call_count}: "
                f"{len(violations)} violations received"
            )
            return text

        t0 = time.time()
        result = run_review_gate(
            chapter_text=BAD_CHAPTER,
            chapter_no=1,
            project_root=str(tmp_root),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=config,
            max_retries=3,
        )
        elapsed = time.time() - t0

        report_lines.append(f"- Gate finished in {elapsed:.1f}s")
        report_lines.append(f"- Final score: {result.final_score}")
        report_lines.append(f"- Threshold: {result.threshold}")
        report_lines.append(f"- Attempts: {len(result.attempts)}")
        report_lines.append(f"- Passed: {result.passed}")
        report_lines.append(f"- Polish calls: {polish_call_count}")

        blocked_path = None
        if result.blocked_path:
            blocked_path = result.blocked_path
            report_lines.append(f"- blocked.md written: {blocked_path}")

        return not result.passed, len(result.attempts), blocked_path


def _write_report(lines: list[str], status: str) -> Path:
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / "editor-wisdom-smoke-report.md"

    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = [
        "# Editor-Wisdom End-to-End Smoke Test Report",
        "",
        f"**Date**: {now}",
        f"**Status**: {status}",
        "",
        "## Steps",
        "",
    ]
    content.extend(lines)
    content.append("")

    report_path.write_text("\n".join(content), encoding="utf-8")
    return report_path


def main() -> int:
    report_lines: list[str] = []

    if not _check_api_key():
        report_lines.append(
            "- ANTHROPIC_API_KEY not set. Smoke test skipped."
        )
        report_lines.append(
            "- Set the key and re-run to execute the full end-to-end test."
        )
        report_path = _write_report(report_lines, "skipped")
        print(f"Smoke test SKIPPED (no API key). Report: {report_path}")
        return 0

    report_lines.append("### Step 1: Check / rebuild index")
    if not _ensure_index(report_lines):
        report_lines.append("- FAILED: could not build index")
        report_path = _write_report(report_lines, "FAIL")
        print(f"Smoke test FAILED (index build). Report: {report_path}")
        return 1

    report_lines.append("")
    report_lines.append("### Step 2: Run hard gate on intentionally bad chapter")
    try:
        blocked, attempts, blocked_path = _run_gate(report_lines)
    except Exception as e:
        report_lines.append(f"- EXCEPTION: {type(e).__name__}: {e}")
        report_path = _write_report(report_lines, "FAIL")
        print(f"Smoke test FAILED (exception). Report: {report_path}")
        return 1

    report_lines.append("")
    report_lines.append("### Step 3: Assertions")

    all_pass = True
    if blocked:
        report_lines.append("- [PASS] Chapter was blocked")
    else:
        report_lines.append("- [FAIL] Chapter was NOT blocked (expected block)")
        all_pass = False

    if attempts == 3:
        report_lines.append(f"- [PASS] 3 check attempts made")
    else:
        report_lines.append(
            f"- [FAIL] Expected 3 attempts, got {attempts}"
        )
        all_pass = False

    if blocked_path:
        report_lines.append(f"- [PASS] blocked.md exists at {blocked_path}")
    else:
        report_lines.append("- [FAIL] blocked.md was not created")
        all_pass = False

    status = "PASS" if all_pass else "FAIL"
    report_path = _write_report(report_lines, status)
    print(f"Smoke test {status}. Report: {report_path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
