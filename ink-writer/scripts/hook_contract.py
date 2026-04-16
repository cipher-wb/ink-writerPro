#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钩子契约解析与验证

解析大纲中的 `钩子契约` 字段，验证格式与类型合法性。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

VALID_HOOK_TYPES = frozenset({"crisis", "mystery", "emotion", "choice", "desire"})

_CONTRACT_LINE_RE = re.compile(
    r"[·\-\*]\s*钩子契约\s*[:：]\s*(.+)",
    re.UNICODE,
)

_TYPE_RE = re.compile(r"类型\s*=\s*(\w+)")
_ANCHOR_RE = re.compile(r"兑现锚点\s*=\s*第\s*(\d+)\s*章")
_SUMMARY_RE = re.compile(r"兑现摘要\s*=\s*(.+?)(?:\s*\||$)")


@dataclass
class HookContract:
    hook_type: str
    anchor_chapter: int
    payoff_summary: str


@dataclass
class ValidationError:
    chapter_num: int
    message: str


def parse_hook_contract(line: str) -> Optional[HookContract]:
    """Parse a hook contract value string (the part after '钩子契约:').

    Returns HookContract if all three sub-fields are present, else None.
    """
    type_m = _TYPE_RE.search(line)
    anchor_m = _ANCHOR_RE.search(line)
    summary_m = _SUMMARY_RE.search(line)

    if not (type_m and anchor_m and summary_m):
        return None

    return HookContract(
        hook_type=type_m.group(1).strip().lower(),
        anchor_chapter=int(anchor_m.group(1)),
        payoff_summary=summary_m.group(1).strip(),
    )


def extract_hook_contract_from_outline(outline_text: str) -> Optional[HookContract]:
    """Extract a HookContract from a single chapter outline block."""
    match = _CONTRACT_LINE_RE.search(outline_text)
    if not match:
        return None
    return parse_hook_contract(match.group(1))


def validate_chapter_outline(
    outline_text: str, chapter_num: int
) -> List[ValidationError]:
    """Validate a chapter outline block has a valid hook_contract.

    Returns list of errors (empty = valid).
    """
    errors: List[ValidationError] = []
    contract = extract_hook_contract_from_outline(outline_text)

    if contract is None:
        errors.append(
            ValidationError(chapter_num, "缺少钩子契约字段或格式不完整")
        )
        return errors

    if contract.hook_type not in VALID_HOOK_TYPES:
        errors.append(
            ValidationError(
                chapter_num,
                f"钩子类型 '{contract.hook_type}' 不合法，"
                f"必须是 {sorted(VALID_HOOK_TYPES)} 之一",
            )
        )

    if contract.anchor_chapter < 1:
        errors.append(
            ValidationError(chapter_num, "兑现锚点章号必须 ≥ 1")
        )

    if not contract.payoff_summary:
        errors.append(
            ValidationError(chapter_num, "兑现摘要不能为空")
        )

    return errors


_CHAPTER_HEADER_RE = re.compile(
    r"###\s*第\s*(\d+)\s*章[：:]", re.UNICODE
)


def validate_volume_outline(outline_text: str) -> List[ValidationError]:
    """Validate all chapters in a volume outline file."""
    errors: List[ValidationError] = []

    chapter_blocks = re.split(r"(?=###\s*第\s*\d+\s*章[：:])", outline_text)

    for block in chapter_blocks:
        header = _CHAPTER_HEADER_RE.match(block.strip())
        if not header:
            continue
        chapter_num = int(header.group(1))
        errors.extend(validate_chapter_outline(block, chapter_num))

    return errors
