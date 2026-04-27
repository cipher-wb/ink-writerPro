"""US-012: writer-agent Step 2A explosive_retrieval injection helper.

将 ExplosiveRetriever 的 top-k 结果注入 prompt 的 <reference_examples> 块。
索引缺失时 graceful fallback（返回空字符串），不阻断写作流程。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ink_writer.retrieval.explosive_retriever import ExplosiveRetriever

logger = logging.getLogger(__name__)

_DEFAULT_INDEX = Path(__file__).resolve().parents[2] / "data" / "explosive_hit_index.json"


def inject_explosive_examples(
    scene_outline: str,
    *,
    scene_type: str | None = None,
    k: int = 3,
    index_path: str | Path | None = None,
    enabled: bool = True,
) -> str:
    """检索 top-k 爆款示例并格式化为 <reference_examples> XML 块。

    Args:
        scene_outline: 场景大纲文本（用于相似度匹配）
        scene_type: 场景类型过滤（combat/dialogue/emotional/action/setup/climax）
        k: 返回切片数（默认 3）
        index_path: 索引文件路径（默认 data/explosive_hit_index.json）
        enabled: False 时跳过检索直接返回空（开关关闭）

    Returns:
        "<reference_examples>...</reference_examples>" 格式字符串，
        或空字符串（索引缺失/开关关闭/检索无结果时）
    """
    if not enabled:
        logger.debug("explosive_retrieval disabled via enable_explosive_retrieval switch")
        return ""

    try:
        retriever = ExplosiveRetriever(index_path if index_path else _DEFAULT_INDEX)
        results = retriever.retrieve(scene_outline, scene_type=scene_type, k=k)
    except Exception as exc:
        logger.warning("ExplosiveRetriever failed, falling back to no-reference mode: %s", exc)
        return ""

    if not results:
        logger.debug("ExplosiveRetriever returned no results for outline: %s...",
                     scene_outline[:50])
        return ""

    lines = ["<reference_examples>"]
    for r in results:
        lines.append(
            f"<!-- source: {r.get('source_book', 'unknown')} "
            f"ch{r.get('source_chapter', '?')} "
            f"scene_type={r.get('scene_type', 'unknown')} "
            f"score={r.get('score', 0):.2f} -->\n"
            f"{r.get('excerpt', '')}"
        )
    lines.append("</reference_examples>")
    return "\n".join(lines)
