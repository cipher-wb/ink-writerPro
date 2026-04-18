#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checkpoint_utils — ink-auto 检查点判断与报告解析工具

从 ink-auto.sh 的 Bash 逻辑中提取为可测试的 Python 函数。
Bash 端通过调用 ink.py checkpoint 子命令使用这些函数。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple


# ───────────────────────────────────────
# 检查点级别判断
# ───────────────────────────────────────

class CheckpointLevel(NamedTuple):
    """检查点级别及需要执行的动作。"""
    review: bool        # 审查最近 5 章
    audit: str | None   # None / "quick" / "standard" / "deep"
    macro: str | None   # None / "Tier2" / "Tier3"
    disambig: bool      # 是否检查消歧积压


def determine_checkpoint(chapter: int) -> CheckpointLevel:
    """根据章节号决定需要执行的检查点级别（v16 US-008 起 5 档分层）。

    规则（高级别包含低级别）:
    - 每 5 章: ink-review Core + ink-fix
    - 每 10 章: + ink-audit quick + ink-fix 修复数据问题
    - 每 20 章: + ink-audit standard + Tier2（浅版）+ 消歧检查
    - 每 50 章: + Tier2（完整版）+ propagation drift_detector
    - 每 200 章: + Tier3 跨卷分析

    实现细节：
      - 200 章优先级最高（同时是 100/50/20/10/5 的倍数），返回 Tier3。
      - 50 章返回 Tier2 完整 + drift_detector（overrides Tier2 浅版）。
      - 20 章返回 Tier2 浅版 + standard audit。
      - 10 章返回 quick audit。
      - 5 章仅 review。
    """
    if chapter % 5 != 0:
        return CheckpointLevel(review=False, audit=None, macro=None, disambig=False)

    if chapter % 200 == 0:
        return CheckpointLevel(
            review=True, audit="standard", macro="Tier3", disambig=True,
        )
    if chapter % 50 == 0:
        # Tier2 完整版 + drift_detector。macro 字段仍记 "Tier2"，具体"完整/浅"
        # 由 ink-auto 按 chapter % 50 判定是否叠加 propagation。
        return CheckpointLevel(
            review=True, audit="standard", macro="Tier2", disambig=True,
        )
    if chapter % 20 == 0:
        return CheckpointLevel(
            review=True, audit="standard", macro="Tier2", disambig=True,
        )
    if chapter % 10 == 0:
        return CheckpointLevel(
            review=True, audit="quick", macro=None, disambig=False,
        )
    return CheckpointLevel(
        review=True, audit=None, macro=None, disambig=False,
    )


def review_range(chapter: int) -> tuple[int, int]:
    """返回审查范围 (start, end)，覆盖最近 5 章。"""
    start = max(1, chapter - 4)
    return (start, chapter)


# ───────────────────────────────────────
# 报告问题检测
# ───────────────────────────────────────

# 匹配 critical/high 级别问题的关键词（中英文）
_ISSUE_PATTERN = re.compile(
    r"critical|high|严重|错误|不一致|漂移|失衡|逾期",
    re.IGNORECASE,
)


def report_has_issues(report_path: str | Path) -> bool:
    """检查审查/审计报告中是否存在需要修复的问题。

    扫描报告文本中的 critical/high 等关键词。
    比 Bash 中 `grep -qiE` 更可靠：忽略空文件、编码错误。
    """
    path = Path(report_path)
    if not path.is_file():
        return False

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    return bool(_ISSUE_PATTERN.search(text))


def count_issues_by_severity(report_path: str | Path) -> dict[str, int]:
    """统计报告中各严重级别的问题数量。

    返回格式: {"critical": N, "high": N, "medium": N, "low": N}
    """
    path = Path(report_path)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    if not path.is_file():
        return counts

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return counts

    # 匹配 markdown 中常见的严重级别标记模式:
    # - **严重级别**: critical / 🔴 critical / [critical]
    for line in text.splitlines():
        line_lower = line.lower()
        if re.search(r"\bcritical\b|🔴|严重", line_lower):
            counts["critical"] += 1
        elif re.search(r"\bhigh\b|🟠|较高", line_lower):
            counts["high"] += 1
        elif re.search(r"\bmedium\b|🟡|中等", line_lower):
            counts["medium"] += 1
        elif re.search(r"\blow\b|🔵|较低", line_lower):
            counts["low"] += 1

    return counts


# ───────────────────────────────────────
# 消歧积压检查
# ───────────────────────────────────────

def get_disambiguation_backlog(project_root: str | Path) -> int:
    """读取 state.json 中的消歧积压数量。"""
    state_file = Path(project_root) / ".ink" / "state.json"
    if not state_file.is_file():
        return 0

    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
        return len(state.get("disambiguation_pending", []))
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def disambiguation_urgency(count: int) -> str:
    """根据消歧积压数量返回紧急程度。

    返回: "critical" (>100) / "warning" (>20) / "normal"
    """
    if count > 100:
        return "critical"
    elif count > 20:
        return "warning"
    return "normal"


# ───────────────────────────────────────
# CLI 入口（供 ink.py checkpoint 子命令调用）
# ───────────────────────────────────────

def cli_checkpoint_level(args) -> None:
    """输出指定章节的检查点级别（JSON 格式）。"""
    level = determine_checkpoint(args.chapter)
    result = {
        "chapter": args.chapter,
        "review": level.review,
        "review_range": list(review_range(args.chapter)) if level.review else None,
        "audit": level.audit,
        "macro": level.macro,
        "disambig": level.disambig,
    }
    print(json.dumps(result, ensure_ascii=False))


def cli_report_check(args) -> None:
    """检查报告文件是否包含需要修复的问题。"""
    has = report_has_issues(args.report)
    if args.count:
        counts = count_issues_by_severity(args.report)
        counts["has_issues"] = has
        print(json.dumps(counts, ensure_ascii=False))
    else:
        print(json.dumps({"has_issues": has}, ensure_ascii=False))


def cli_disambig_check(args) -> None:
    """检查消歧积压数量和紧急程度。"""
    count = get_disambiguation_backlog(args.project_root)
    urgency = disambiguation_urgency(count)
    print(json.dumps({
        "count": count,
        "urgency": urgency,
    }, ensure_ascii=False))
