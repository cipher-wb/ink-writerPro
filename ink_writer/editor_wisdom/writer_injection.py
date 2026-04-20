"""Inject editor-wisdom rules as hard constraints into the writer-agent prompt."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config
from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError
from ink_writer.editor_wisdom.golden_three import (
    GOLDEN_THREE_CATEGORIES,
    GOLDEN_THREE_FLOOR_CATEGORIES,
    GOLDEN_THREE_FLOOR_PER_CATEGORY,
)
from ink_writer.editor_wisdom.retriever import Retriever, Rule, get_retriever

# v18 US-002：分类别召回下限常量迁移到 golden_three.py，
# 此处 re-export 便于既有调用方（含测试）继续通过 writer_injection 访问。
__all__ = [
    "WriterConstraintsSection",
    "build_writer_constraints",
    "GOLDEN_THREE_FLOOR_CATEGORIES",
    "GOLDEN_THREE_FLOOR_PER_CATEGORY",
    "DIRECTNESS_SCENE_MODES",
]

# v22 US-004：directness 模式 scene_mode 取值。golden_three（chapter ∈ [1,3]）在
# build_writer_constraints 里按 chapter_no 直接判；这里仅列明显式的 scene_mode 值。
DIRECTNESS_SCENE_MODES: frozenset[str] = frozenset({"combat", "climax", "high_point"})


@dataclass
class WriterConstraintsSection:
    rules: list[Rule] = field(default_factory=list)
    chapter_no: int = 1

    @property
    def empty(self) -> bool:
        return len(self.rules) == 0

    def to_markdown(self) -> str:
        if self.empty:
            return ""
        hard = [r for r in self.rules if r.severity == "hard"]
        soft = [r for r in self.rules if r.severity == "soft"]
        if not hard and not soft:
            return ""
        lines: list[str] = ["### 编辑智慧硬约束（Editor Wisdom Constraints）", ""]
        if hard:
            lines.append("**【硬约束 — 必须遵守，违反将触发返工】**：")
            for r in hard:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        if soft:
            lines.append("**【软约束 — 建议遵守】**：")
            for r in soft:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        return "\n".join(lines)


def build_writer_constraints(
    chapter_outline: str,
    chapter_no: int = 1,
    *,
    config: EditorWisdomConfig | None = None,
    retriever: Retriever | None = None,
    project_root: Path | str | None = None,
    scene_mode: str | None = None,
) -> WriterConstraintsSection:
    """Build the 硬约束 section for writer-agent prompt injection.

    Groups rules by severity (hard first, soft next, info omitted).
    When chapter_no <= 3, additionally injects rules whose applies_to includes 'golden_three'
    AND enforces a per-category floor (opening/taboo/hook each ≥3 rules) — v18 US-002.

    v22 US-004: when chapter_no ∈ [1,3] OR scene_mode ∈ {combat, climax, high_point},
    additionally enforce a per-category floor for simplicity rules (default ≥5) so the
    writer-agent prompt always carries directness-mode constraints for those scenes.
    Non-directness scenes are unaffected — 零退化硬约束保留 sensory-immersion 流程。
    """
    if config is None:
        config = load_config()

    if not config.enabled or not config.inject_into.writer:
        return WriterConstraintsSection(chapter_no=chapter_no)

    if retriever is None:
        try:
            retriever = get_retriever()  # v13 US-006：单例复用，避免每章重加载 BAAI 模型
        except EditorWisdomIndexMissingError:
            if config.enabled:
                raise
            return WriterConstraintsSection(chapter_no=chapter_no)
        except Exception:
            if config.enabled:
                raise
            return WriterConstraintsSection(chapter_no=chapter_no)

    k = config.retrieval_top_k
    rules = retriever.retrieve(query=chapter_outline, k=k)

    # v22 US-004：directness 激活判定——黄金三章 chapter∈[1,3] 或显式 scene_mode 命中
    directness_scene_modes = frozenset(config.directness_recall.scene_modes)
    directness_active = (chapter_no <= 3) or (
        scene_mode is not None and scene_mode in directness_scene_modes
    )

    if chapter_no <= 3:
        golden_rules = [
            r for r in retriever.retrieve(query=chapter_outline, k=k * 2)
            if r.category in GOLDEN_THREE_CATEGORIES
        ]
        seen_ids = {r.id for r in rules}
        for r in golden_rules:
            if r.id not in seen_ids:
                rules.append(r)
                seen_ids.add(r.id)

        # v18 US-002：分类别下限。openig/taboo/hook 每类 ≥ GOLDEN_THREE_FLOOR_PER_CATEGORY 条。
        rules = _enforce_category_floor(
            rules=rules,
            retriever=retriever,
            query=chapter_outline,
            floor=GOLDEN_THREE_FLOOR_PER_CATEGORY,
            categories=GOLDEN_THREE_FLOOR_CATEGORIES,
        )

    if directness_active:
        # v22 US-004：simplicity 类分类别下限（默认 ≥5），独立于 golden-three 的 opening/taboo/hook 下限。
        # 非 directness 场景（scene_mode in {slow_build, emotional, other}, chapter>3）完全不进入。
        rules = _enforce_category_floor(
            rules=rules,
            retriever=retriever,
            query=chapter_outline,
            floor=config.directness_recall.floor_per_category,
            categories=tuple(config.directness_recall.floor_categories),
        )

    filtered = [r for r in rules if r.severity in ("hard", "soft")]

    # v18 US-002：覆盖率埋点。只在传入 project_root 时写出（生产链路传入；单元测试不传）。
    if project_root is not None:
        try:
            from ink_writer.editor_wisdom.coverage_metrics import (
                record_chapter_coverage,
            )

            record_chapter_coverage(
                project_root=Path(project_root),
                chapter_no=chapter_no,
                rules=filtered,
            )
        except Exception:
            # 覆盖率记录失败不阻断正文生产
            pass

    if not filtered:
        return WriterConstraintsSection(chapter_no=chapter_no)

    return WriterConstraintsSection(rules=filtered, chapter_no=chapter_no)


def _enforce_category_floor(
    *,
    rules: list[Rule],
    retriever: Retriever,
    query: str,
    floor: int,
    categories: tuple[str, ...],
) -> list[Rule]:
    """Top up each target category to at least `floor` rules via category-filtered retrieval.

    Additions are appended after the existing rules (preserving ranking of the head),
    deduplicated by rule id.
    """
    seen_ids: set[str] = {r.id for r in rules}
    by_category: dict[str, int] = {}
    for r in rules:
        by_category[r.category] = by_category.get(r.category, 0) + 1

    for cat in categories:
        have = by_category.get(cat, 0)
        if have >= floor:
            continue
        need = floor - have
        # 取 floor + 已有数的两倍作为过采样上限，避免频繁补召回
        over_k = max(floor * 2, have + need + floor)
        extras = retriever.retrieve(query=query, k=over_k, category=cat)
        added = 0
        for r in extras:
            if r.id in seen_ids:
                continue
            # 仅补 hard/soft；info 补了也会在 filter 阶段被去掉，浪费 prompt
            if r.severity not in ("hard", "soft"):
                continue
            rules.append(r)
            seen_ids.add(r.id)
            added += 1
            if added >= need:
                break

    return rules
