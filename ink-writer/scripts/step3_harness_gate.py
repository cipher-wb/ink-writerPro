#!/usr/bin/env python3
"""Step 3 Harness Gate: 读取审查结果，硬拦截质量不合格的章节。

Exit codes:
  0 = 通过，可进入 Step 4
  1 = 硬拦截，必须回退 Step 2A 重写
  2 = 脚本错误（静默跳过）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def check_review_gate(project_root: Path, chapter_num: int) -> dict:
    """检查审查结果是否通过闸门。"""
    result = {"pass": True, "reason": "", "action": "continue"}

    # 从最近的审查报告中读取
    reports_dir = project_root / ".ink" / "reports"
    if not reports_dir.exists():
        return result  # 无报告，默认通过

    # 查找匹配当前章节的审查报告
    report_file = None
    for f in sorted(reports_dir.glob("review_ch*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            start = data.get("start_chapter", 0)
            end = data.get("end_chapter", 0)
            if start <= chapter_num <= end:
                report_file = f
                break
        except (json.JSONDecodeError, OSError):
            continue

    if not report_file:
        return result

    data = json.loads(report_file.read_text(encoding="utf-8"))
    overall_score = data.get("overall_score", 100)
    severity_counts = data.get("severity_counts", {})
    critical_count = severity_counts.get("critical", 0)
    checker_results = data.get("checker_results", {})

    # 规则1: 黄金三章硬拦截
    if chapter_num <= 3:
        golden = checker_results.get("golden-three-checker", {})
        golden_issues = golden.get("issues", [])
        high_issues = [i for i in golden_issues if i.get("severity") == "high"]
        if high_issues:
            result["pass"] = False
            result["reason"] = f"黄金三章(ch{chapter_num})存在 {len(high_issues)} 个 high 级问题"
            result["action"] = "rewrite_step2a"
            return result

    # 规则2: 读者体验阻断
    reader_sim = checker_results.get("reader-simulator", {})
    verdict = reader_sim.get("reader_verdict", {}).get("verdict", "")
    if verdict == "rewrite":
        if chapter_num <= 3:
            result["pass"] = False
            result["reason"] = f"reader-simulator 判定 rewrite (ch{chapter_num})"
            result["action"] = "rewrite_step2a"
            return result
        # ch4+ 仅为强警告
        print(f"⚠️  reader-simulator 判定 rewrite，强烈建议重写", file=sys.stderr)

    # 规则3: overall_score 过低
    if overall_score < 40:
        result["pass"] = False
        result["reason"] = f"overall_score={overall_score} < 40"
        result["action"] = "rewrite_step2a"
        return result

    # 规则4: critical 过多
    if critical_count >= 3:
        result["pass"] = False
        result["reason"] = f"critical issues={critical_count} >= 3"
        result["action"] = "rewrite_step2a"

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 3 Harness Gate")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    try:
        result = check_review_gate(args.project_root, args.chapter)
    except Exception as e:
        print(f"Gate error: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["pass"]:
            print(f"✅ Step 3 Gate PASS (ch{args.chapter})")
        else:
            print(f"❌ Step 3 Gate FAIL: {result['reason']}")
            print(f"   Action: {result['action']}")

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
