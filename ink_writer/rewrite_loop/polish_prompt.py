"""case_id 驱动的 polish prompt 构造（M3 P1 / spec §5.3 + Q12）。

polish-agent 在 rewrite_loop 中接收单条阻断 case，按照 case 的
failure_description / observable 与（可选）相关 chunks 重写最小必要段落。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

_CHUNK_TEXT_PREVIEW = 120  # 单 chunk 截断字数，避免 prompt 过长


def _format_observable(observable: Sequence[str]) -> str:
    if not observable:
        return "（病例未给出 observable 列表，按 failure_description 整体修复）"
    return "\n".join(f"- {item}" for item in observable)


def _format_chunks(related_chunks: Sequence[dict[str, Any]] | None) -> str:
    if not related_chunks:
        return (
            "（无相关范文 / no related chunks available — "
            "M3 期 chunk_borrowing deferred，仅按 case 病例修复）"
        )
    lines: list[str] = []
    for chunk in related_chunks:
        chunk_id = chunk.get("chunk_id", "<unknown>")
        text = str(chunk.get("text", ""))
        preview = text[:_CHUNK_TEXT_PREVIEW]
        if len(text) > _CHUNK_TEXT_PREVIEW:
            preview += "…"
        lines.append(f"- [{chunk_id}] {preview}")
    return "\n".join(lines)


def build_polish_prompt(
    *,
    chapter_text: str,
    case_id: str,
    case_failure_description: str,
    case_observable: Sequence[str],
    related_chunks: Sequence[dict[str, Any]] | None,
) -> str:
    """构造 case_id 驱动的重写 prompt。

    Args:
        chapter_text: 当前章节正文（可能是上一轮 polish 后的版本）。
        case_id: 阻断病例 id（写入 prompt 顶部，便于审计）。
        case_failure_description: 病例失败模式描述。
        case_observable: 病例可观察特征列表，告诉 LLM 如何识别违规。
        related_chunks: 相关范文段落（M3 期通常为 None；M4+ 可能注入）。

    Returns:
        完整 prompt 字符串，交给 polish-agent 调 LLM。
    """
    observable_block = _format_observable(case_observable)
    chunks_block = _format_chunks(related_chunks)

    return (
        "你是 polish-agent。请按以下病例对当前章节做最小化重写：\n"
        "\n"
        f"## 阻断病例\n"
        f"- case_id: {case_id}\n"
        f"- failure_description: {case_failure_description}\n"
        f"\n## observable（识别要点）\n"
        f"{observable_block}\n"
        f"\n## 相关范文\n"
        f"{chunks_block}\n"
        f"\n## 当前章节正文\n"
        f"{chapter_text}\n"
        "\n## 输出要求\n"
        "- 只重写最小必要段落，未受影响的段落原样保留。\n"
        "- 不输出 diff，直接给出重写后的完整章节正文。\n"
        "- 末尾附 1 行修改说明（以 `修改说明：` 开头），简述改了哪段、为什么。\n"
        "- 不包裹 markdown 代码块（不要 ```），章节正文直接以正文首段开始。\n"
        "- 不得改变剧情事实、人物身份、设定物理边界。\n"
    )
