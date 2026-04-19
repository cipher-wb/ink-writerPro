"""Build character-progression summary for context-agent / Context Contract.

Consumer: context-agent Step 4.5 (FIX-18 P5c) —— 在组装任务书第 N 章前的
"本章之前摘要"时，把各角色 dimension 演进切片注入 Context Contract 的
`character_progression_summary` 字段，供 writer-agent 感知配角多维度状态漂移。

Design notes:
- 轻量纯函数，不依赖具体 IndexManager 类型。任何带
  `get_progressions_for_character(char_id, before_chapter=N)` 签名的对象都能注入，
  方便 harness 测试 mock。
- `max_rows_per_char` 默认 5，对应 PRD 验收"最多 5 行/角色"；排序按章节升序，
  超出时保留"最近 N 条"（离本章最近的演进最有信息量）。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Protocol

DEFAULT_MAX_ROWS_PER_CHAR = 5


class _ProgressionSource(Protocol):
    def get_progressions_for_character(
        self, char_id: str, before_chapter: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        ...

    # US-007: SQL LIMIT 下推路径（可选）。实现了此方法的 source 会绕过 Python 侧切片，
    # 将 "最近 N 条" 约束下推到 SQLite（WHERE ... ORDER BY chapter_no DESC LIMIT ?）。
    # Protocol 允许缺省：build_progression_summary 用 hasattr 动态探测，未实现则 fallback。
    def get_recent_progressions_for_character(  # pragma: no cover - Protocol only
        self, char_id: str, before_chapter: int, limit: int
    ) -> List[Dict[str, Any]]:
        ...


def _compact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """抽取注入所需字段，忽略 recorded_at 等低信号字段。"""
    return {
        "chapter_no": row.get("chapter_no"),
        "dimension": row.get("dimension"),
        "from_value": row.get("from_value"),
        "to_value": row.get("to_value"),
        "cause": row.get("cause"),
    }


def build_progression_summary(
    source: _ProgressionSource,
    char_ids: Iterable[str],
    before_chapter: int,
    max_rows_per_char: int = DEFAULT_MAX_ROWS_PER_CHAR,
) -> Dict[str, List[Dict[str, Any]]]:
    """返回 {char_id: [ {chapter_no, dimension, from_value, to_value, cause}, ... ]}。

    - 过滤规则：chapter_no < before_chapter
    - 每个角色最多 `max_rows_per_char` 行；超出则保留最近的（章节升序末尾）
    - 入参 char_ids 为空或全无记录时返回 {}
    """
    if before_chapter is None or int(before_chapter) <= 0:
        raise ValueError("before_chapter must be a positive int")
    if max_rows_per_char <= 0:
        raise ValueError("max_rows_per_char must be > 0")

    # US-007: 优先走 SQL LIMIT 下推路径。source 实现了 get_recent_progressions_for_character
    # 时，直接在 SQLite 侧返回"最近 N 条"，避免 500+ 章 8 万行场景下的 Python 侧 O(n²) 切片。
    use_limit_pushdown = hasattr(source, "get_recent_progressions_for_character")

    out: Dict[str, List[Dict[str, Any]]] = {}
    for char_id in char_ids:
        if use_limit_pushdown:
            rows = source.get_recent_progressions_for_character(  # type: ignore[attr-defined]
                char_id,
                before_chapter=int(before_chapter),
                limit=int(max_rows_per_char),
            ) or []
            trimmed = rows  # SQL 已限量，保序返回
        else:
            rows = source.get_progressions_for_character(
                char_id, before_chapter=int(before_chapter)
            ) or []
            if not rows:
                continue
            # 章节升序下取最近 N 条 = 尾部 N
            trimmed = rows[-max_rows_per_char:] if len(rows) > max_rows_per_char else rows
        if not trimmed:
            continue
        out[char_id] = [_compact_row(r) for r in trimmed]
    return out


def render_progression_summary_md(
    summary: Dict[str, List[Dict[str, Any]]],
    *,
    header: str = "## 本章之前 · 角色演进摘要",
    empty_placeholder: str = "[本章之前无角色演进记录]",
) -> str:
    """将 summary 渲染为 Markdown table，供任务书"本章之前摘要"板块直接嵌入。"""
    if not summary:
        return f"{header}\n\n{empty_placeholder}\n"

    lines: List[str] = [header, ""]
    for char_id, rows in summary.items():
        lines.append(f"### {char_id}")
        lines.append("| 章节 | 维度 | 从 | 到 | 原因 |")
        lines.append("|------|------|----|----|------|")
        for r in rows:
            lines.append(
                "| {ch} | {dim} | {fv} | {tv} | {cause} |".format(
                    ch=r.get("chapter_no", ""),
                    dim=r.get("dimension", ""),
                    fv=r.get("from_value") or "—",
                    tv=r.get("to_value") or "—",
                    cause=r.get("cause") or "—",
                )
            )
        lines.append("")
    return "\n".join(lines)
