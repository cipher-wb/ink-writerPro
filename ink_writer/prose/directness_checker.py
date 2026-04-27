"""US-005: Directness checker 程序化打分核心。

提供 5 维度（D1-D5）直白度评分：
  - D1 rhetoric_density  —— 比喻 + 排比 / 总句数
  - D2 adj_verb_ratio    —— 形容词 / 动词
  - D3 abstract_per_100_chars —— 抽象词命中 / 每 100 字
  - D4 sent_len_median   —— 句长中位数（mid_is_better）
  - D5 empty_paragraphs  —— 空描写段数

评级：任一维度 <6 → RED；均 ≥8 → GREEN；否则 YELLOW。

激活条件（由调用方决定）：scene_mode ∈ {golden_three, combat, climax, high_point}
或 chapter_no ∈ [1,3]（等同 golden_three）。其他场景应跳过。

阈值来源：``reports/seed_thresholds.yaml``（US-002 产出），按 scene 选 bucket；
YAML 不可用时 fallback 到 ``_DEFAULT_THRESHOLDS``（golden_three 固化副本）。
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ACTIVATION_SCENE_MODES = frozenset(
    {"golden_three", "combat", "climax", "high_point"}
)

SKIPPED_SCENE_MODES = frozenset({"slow_build", "emotional", "other"})

DIMENSION_KEYS: tuple[str, ...] = (
    "D1_rhetoric_density",
    "D2_adj_verb_ratio",
    "D3_abstract_per_100_chars",
    "D4_sent_len_median",
    "D5_empty_paragraphs",
    "D6_nesting_depth",
    "D7_modifier_chain_length",
)

_DIMENSION_LABELS: dict[str, str] = {
    "D1_rhetoric_density": "修辞密度",
    "D2_adj_verb_ratio": "形容词-动词比",
    "D3_abstract_per_100_chars": "抽象词密度",
    "D4_sent_len_median": "句长适中",
    "D5_empty_paragraphs": "空描写段",
    "D6_nesting_depth": "嵌套深度",
    "D7_modifier_chain_length": "修饰链长",
}

GREEN_SCORE: float = 8.0
RED_SCORE: float = 6.0

_DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "D1_rhetoric_density": {
        "direction": "lower_is_better",
        "green_max": 0.0247,
        "yellow_max": 0.0399,
    },
    "D2_adj_verb_ratio": {
        "direction": "lower_is_better",
        "green_max": 0.1595,
        "yellow_max": 0.1872,
    },
    "D3_abstract_per_100_chars": {
        "direction": "lower_is_better",
        "green_max": 0.0776,
        "yellow_max": 0.1434,
    },
    "D4_sent_len_median": {
        "direction": "mid_is_better",
        "green_low": 13.0,
        "green_high": 17.625,
        "yellow_low": 8.375,
        "yellow_high": 22.25,
    },
    "D5_empty_paragraphs": {
        "direction": "lower_is_better",
        "green_max": 50.5,
        "yellow_max": 68.25,
    },
    "D6_nesting_depth": {
        "direction": "lower_is_better",
        "green_max": 1.5,
        "yellow_max": 2.0,
    },
    "D7_modifier_chain_length": {
        "direction": "lower_is_better",
        "green_max": 1.5,
        "yellow_max": 2.5,
    },
}

_DEFAULT_THRESHOLDS_PATH = (
    Path(__file__).resolve().parents[2] / "reports" / "seed_thresholds.yaml"
)

_SCENE_TO_BUCKET: dict[str, str] = {
    "golden_three": "golden_three",
    "combat": "combat",
    "climax": "combat",
    "high_point": "combat",
}

# US-007: D6/D7 regex patterns
_D6_SENT_SPLIT_RE = re.compile(r"[。！？!?；;…]+")
_D6_CLAUSE_SPLIT_RE = re.compile(r"[，、,;；]")
_D7_MODIFIER_RE = re.compile(r"(?:[一-龥]+的)+[一-龥]+")


@dataclass(frozen=True)
class DimensionScore:
    key: str
    value: float
    score: float
    rating: str
    direction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": round(self.value, 4),
            "score": round(self.score, 2),
            "rating": self.rating,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class DirectnessIssue:
    id: str
    dimension: str
    severity: str
    description: str
    suggest_rewrite: str
    line_range: tuple[int, int]
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "severity": self.severity,
            "description": self.description,
            "suggest_rewrite": self.suggest_rewrite,
            "line_range": list(self.line_range),
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class DirectnessReport:
    skipped: bool
    reason: str
    scene_mode: str | None
    chapter_no: int
    overall_score: float
    passed: bool
    severity: str
    dimensions: tuple[DimensionScore, ...]
    issues: tuple[DirectnessIssue, ...]
    metrics_raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skipped": self.skipped,
            "reason": self.reason,
            "scene_mode": self.scene_mode,
            "chapter_no": self.chapter_no,
            "overall_score": round(self.overall_score, 2),
            "passed": self.passed,
            "severity": self.severity,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "issues": [i.to_dict() for i in self.issues],
            "metrics_raw": self.metrics_raw,
        }


def _rating_from_score(score: float) -> str:
    if score >= GREEN_SCORE:
        return "green"
    if score >= RED_SCORE:
        return "yellow"
    return "red"


def _score_lower_is_better(value: float, green_max: float, yellow_max: float) -> float:
    """lower-is-better 维度 → 0-10 分。

    green: value ≤ green_max → 10
    yellow: green_max < value ≤ yellow_max → 10..6 线性
    red: value > yellow_max → 6..0 线性（越界越惨）
    """
    if value <= green_max:
        return 10.0
    if value <= yellow_max:
        span = max(yellow_max - green_max, 1e-9)
        return max(0.0, 10.0 - 4.0 * ((value - green_max) / span))
    span = max(yellow_max, 1e-9)
    over = value - yellow_max
    return max(0.0, 6.0 - 6.0 * min(over / span, 1.0))


def _score_mid_is_better(
    value: float,
    *,
    green_low: float,
    green_high: float,
    yellow_low: float,
    yellow_high: float,
) -> float:
    """mid-is-better（D4 句长中位数）→ 0-10 分。

    green: green_low ≤ value ≤ green_high → 10
    yellow: [yellow_low, green_low) 或 (green_high, yellow_high] → 6..10 线性
    red: 超出 yellow → 6..0 线性
    """
    if green_low <= value <= green_high:
        return 10.0
    if yellow_low <= value < green_low:
        span = max(green_low - yellow_low, 1e-9)
        return max(6.0, 6.0 + 4.0 * ((value - yellow_low) / span))
    if green_high < value <= yellow_high:
        span = max(yellow_high - green_high, 1e-9)
        return max(6.0, 10.0 - 4.0 * ((value - green_high) / span))
    if value < yellow_low:
        dist = yellow_low - value
        span = max(yellow_low, 1e-9)
        return max(0.0, 6.0 - 6.0 * min(dist / span, 1.0))
    dist = value - yellow_high
    span = max(yellow_high, 1e-9)
    return max(0.0, 6.0 - 6.0 * min(dist / span, 1.0))


def score_dimension(metric_key: str, value: float, thresholds: dict[str, Any]) -> DimensionScore:
    """单维度打分。未识别 metric → 回退 10 分（中性）。"""
    dim = thresholds.get(metric_key) or _DEFAULT_THRESHOLDS[metric_key]
    direction = dim.get("direction", "lower_is_better")
    if direction == "lower_is_better":
        score = _score_lower_is_better(
            float(value),
            green_max=float(dim["green_max"]),
            yellow_max=float(dim["yellow_max"]),
        )
    elif direction == "mid_is_better":
        score = _score_mid_is_better(
            float(value),
            green_low=float(dim["green_low"]),
            green_high=float(dim["green_high"]),
            yellow_low=float(dim["yellow_low"]),
            yellow_high=float(dim["yellow_high"]),
        )
    else:
        logger.warning(
            "unknown threshold direction %r for %s, default to 10", direction, metric_key
        )
        score = 10.0
    return DimensionScore(
        key=metric_key,
        value=float(value),
        score=round(float(score), 2),
        rating=_rating_from_score(score),
        direction=direction,
    )


_THRESHOLDS_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


def clear_cache() -> None:
    """测试钩子：清空阈值 YAML 缓存。"""
    _THRESHOLDS_CACHE.clear()


def _resolve_scene_bucket(
    scene_mode: str | None,
    chapter_no: int,
    buckets: dict[str, Any],
    *,
    directness_tier: str | None = None,
    tiers: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """根据 scene_mode/chapter_no + directness_tier 选 YAML bucket 的 thresholds。

    US-006 起支持 directness_tier（阈值桶选择）：
      - "explosive_hit" → YAML tiers.explosive_hit 或回退 golden_three（最严）
      - "standard" → YAML tiers.standard 或回退 scenes.other
      - None → 沿用原 scene bucket 逻辑（向后兼容）

    YAML 里 combat bucket 若 n=0 带 inherits_from 时，自动跟 golden_three。
    """
    # tier 优先（US-006）：查独立的 tiers 参数（root level）
    if directness_tier and isinstance(tiers, dict):
        tier_bucket = tiers.get(directness_tier)
        if isinstance(tier_bucket, dict) and "thresholds" in tier_bucket:
            return (f"tier:{directness_tier}", tier_bucket["thresholds"])
        # tier 桶未定义 → 按 tier 语义回退
        if directness_tier == "explosive_hit":
            gt_bucket = buckets.get("golden_three")
            if isinstance(gt_bucket, dict) and "thresholds" in gt_bucket:
                return ("tier:explosive_hit→golden_three", gt_bucket["thresholds"])
        elif directness_tier == "standard":
            other_bucket = buckets.get("other")
            if isinstance(other_bucket, dict) and "thresholds" in other_bucket:
                return ("tier:standard→other", other_bucket["thresholds"])
        # 通用回退
        return ("default", _DEFAULT_THRESHOLDS)

    # 原逻辑：scene_mode → bucket
    resolved_scene: str | None = scene_mode
    if resolved_scene is None and 1 <= chapter_no <= 3:
        resolved_scene = "golden_three"
    if resolved_scene is None:
        return ("default", _DEFAULT_THRESHOLDS)

    bucket_key = _SCENE_TO_BUCKET.get(resolved_scene)
    if bucket_key is None:
        return ("default", _DEFAULT_THRESHOLDS)

    bucket = buckets.get(bucket_key)
    if bucket is None:
        return ("default", _DEFAULT_THRESHOLDS)

    if isinstance(bucket, dict) and "thresholds" in bucket:
        return (bucket_key, bucket["thresholds"])

    inherits = bucket.get("inherits_from") if isinstance(bucket, dict) else None
    if inherits and isinstance(buckets.get(inherits), dict):
        inherit_thresh = buckets[inherits].get("thresholds")
        if inherit_thresh:
            return (f"{bucket_key}→{inherits}", inherit_thresh)

    return ("default", _DEFAULT_THRESHOLDS)


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    """读取 seed_thresholds.yaml；带 (resolved, mtime_ns) 缓存。

    文件缺失或 YAML 解析失败 → fallback 到 ``{"scenes": {"golden_three":
    {"thresholds": _DEFAULT_THRESHOLDS}}}``（保证调用方至少能拿到默认阈值）。
    """
    target = (path or _DEFAULT_THRESHOLDS_PATH).resolve()
    try:
        mtime_ns = target.stat().st_mtime_ns if target.exists() else 0
    except OSError:
        mtime_ns = 0
    cache_key = (str(target), mtime_ns)
    cached = _THRESHOLDS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    fallback = {"scenes": {"golden_three": {"thresholds": dict(_DEFAULT_THRESHOLDS)}}}

    if not target.exists() or not target.is_file():
        _THRESHOLDS_CACHE[cache_key] = fallback
        return fallback

    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        logger.warning("PyYAML unavailable; directness_checker falls back to defaults")
        _THRESHOLDS_CACHE[cache_key] = fallback
        return fallback

    try:
        with target.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("directness_checker threshold YAML parse failed: %s", exc)
        _THRESHOLDS_CACHE[cache_key] = fallback
        return fallback

    if not isinstance(data, dict) or "scenes" not in data:
        _THRESHOLDS_CACHE[cache_key] = fallback
        return fallback

    _THRESHOLDS_CACHE[cache_key] = data
    return data


def is_activated(
    scene_mode: str | None = None,
    chapter_no: int = 0,
    *,
    directness_skip: bool = False,
) -> bool:
    """US-006 全场景激活：所有章节均进入直白模式。

    仅当 directness_skip=True 时返回 False（向后兼容老 outline 显式跳过）。
    scene_mode/chapter_no 不再参与激活判定（保留参数签名以兼容旧调用方）。
    """
    if directness_skip:
        return False
    return True


def _compute_metrics(text: str, abstract_words: Sequence[str] | None = None) -> dict[str, Any]:
    """薄封装：复用 scripts/analyze_prose_directness.py 的 compute_metrics。"""
    import sys as _sys  # noqa: PLC0415

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in _sys.path:
        _sys.path.insert(0, str(scripts_dir))
    from analyze_prose_directness import (  # type: ignore[import-not-found]  # noqa: PLC0415
        _ABSTRACT_SEED,
        compute_metrics,
    )

    words = abstract_words if abstract_words is not None else _ABSTRACT_SEED
    return compute_metrics(text, abstract_words=words)


def _calc_d6_nesting_depth(text: str) -> float:
    """D6: avg clauses per sentence (逗号分隔子句数/句数)。"""
    sentences = [s.strip() for s in _D6_SENT_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return 0.0
    total_clauses = 0
    for sent in sentences:
        clauses = [c.strip() for c in _D6_CLAUSE_SPLIT_RE.split(sent) if c.strip()]
        total_clauses += len(clauses)
    return total_clauses / len(sentences)


def _calc_d7_modifier_chain_length(text: str) -> tuple[float, int]:
    """D7: 修饰语链均长 + 最长链。

    Returns (mean_chain_length, max_chain_length).
    修饰链 = 连续多个 "的" 修饰结构，如 "古老的破旧的褪色的木门" → chain=3。
    """
    chains = [m.group() for m in _D7_MODIFIER_RE.finditer(text)]
    if not chains:
        return (0.0, 0)
    lengths = [c.count("的") for c in chains]
    return (sum(lengths) / len(chains), max(lengths))


def _d6_nesting_predicate(paragraph: str) -> int:
    """段级 D6 嵌套深度 predicate（用于 top paragraph 定位）。"""
    sents = [s.strip() for s in _D6_SENT_SPLIT_RE.split(paragraph) if s.strip()]
    if not sents:
        return 0
    total = 0
    for s in sents:
        clauses = [c.strip() for c in _D6_CLAUSE_SPLIT_RE.split(s) if c.strip()]
        total += len(clauses)
    return total // max(len(sents), 1)


def _d7_modifier_predicate(paragraph: str) -> int:
    """段级 D7 修饰链长 predicate（用于 top paragraph 定位）。"""
    chains = [m.group() for m in _D7_MODIFIER_RE.finditer(paragraph)]
    if not chains:
        return 0
    return max(c.count("的") for c in chains)


def _top_paragraphs_matching(
    paragraphs: list[str],
    predicate,
    limit: int = 2,
) -> list[tuple[int, str, int]]:
    """按 predicate(paragraph)->score 排序返回 top limit 段（score>0）。

    返回 (index, paragraph, score)；score 越大代表问题越严重。
    """
    scored: list[tuple[int, str, int]] = []
    for idx, p in enumerate(paragraphs, start=1):
        s = predicate(p)
        if s > 0:
            scored.append((idx, p, s))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:limit]


def _issue_for_dimension(
    dim_score: DimensionScore,
    text: str,
    abstract_words: Sequence[str],
) -> list[DirectnessIssue]:
    """按维度生成 issues；仅 yellow/red 触发。"""
    if dim_score.rating == "green":
        return []

    from analyze_prose_directness import (  # type: ignore[import-not-found]  # noqa: PLC0415
        _DIALOGUE_MARKERS,
        _PERSON_PRONOUNS,
        count_abstract_hits,
        has_rhetoric,
        split_paragraphs,
        split_sentences,
    )

    severity = "critical" if dim_score.rating == "red" else "medium"
    paragraphs = split_paragraphs(text)
    base_id = dim_score.key.split("_", 1)[0]
    issues: list[DirectnessIssue] = []

    if dim_score.key == "D1_rhetoric_density":
        def _pred(p: str) -> int:
            return sum(1 for s in split_sentences(p) if has_rhetoric(s))
        for idx, para, cnt in _top_paragraphs_matching(paragraphs, _pred, limit=2):
            issues.append(
                DirectnessIssue(
                    id=f"DIRECTNESS_{base_id}_{idx}",
                    dimension=dim_score.key,
                    severity=severity,
                    description=(
                        f"修辞密度 {dim_score.value:.4f} 触发 {dim_score.rating}，"
                        f"第 {idx} 段命中 {cnt} 处比喻/排比"
                    ),
                    suggest_rewrite="删除比喻/排比，直接写人物动作或剧情推进（showing 代 telling）",
                    line_range=(idx, idx),
                    evidence={"excerpt": para[:80]},
                )
            )
    elif dim_score.key == "D2_adj_verb_ratio":
        issues.append(
            DirectnessIssue(
                id=f"DIRECTNESS_{base_id}_ALL",
                dimension=dim_score.key,
                severity=severity,
                description=(
                    f"形容词/动词比 {dim_score.value:.4f}，形容词堆叠过多"
                ),
                suggest_rewrite="把形容词替换为强动词 + 具体名词（如'冰冷的目光'→'眼神钉住他'）",
                line_range=(1, len(paragraphs) or 1),
                evidence={"excerpt": text[:120]},
            )
        )
    elif dim_score.key == "D3_abstract_per_100_chars":
        def _pred(p: str) -> int:
            return count_abstract_hits(p, abstract_words)
        for idx, para, cnt in _top_paragraphs_matching(paragraphs, _pred, limit=2):
            issues.append(
                DirectnessIssue(
                    id=f"DIRECTNESS_{base_id}_{idx}",
                    dimension=dim_score.key,
                    severity=severity,
                    description=(
                        f"抽象词密度 {dim_score.value:.4f} 触发 {dim_score.rating}，"
                        f"第 {idx} 段命中 {cnt} 个抽象词"
                    ),
                    suggest_rewrite="用具体感官细节替换抽象形容词（如'莫名的不安'→'喉结滚了两下'）",
                    line_range=(idx, idx),
                    evidence={"excerpt": para[:80]},
                )
            )
    elif dim_score.key == "D4_sent_len_median":
        issues.append(
            DirectnessIssue(
                id=f"DIRECTNESS_{base_id}_ALL",
                dimension=dim_score.key,
                severity=severity,
                description=(
                    f"句长中位数 {dim_score.value:.2f} 落在 {dim_score.rating} 区间"
                ),
                suggest_rewrite=(
                    "拆长句（>35 字）为短句；或合并过碎短句保证阅读呼吸"
                ),
                line_range=(1, len(paragraphs) or 1),
                evidence={"excerpt": text[:120]},
            )
        )
    elif dim_score.key == "D5_empty_paragraphs":
        def _pred(p: str) -> int:
            if any(m in p for m in _DIALOGUE_MARKERS):
                return 0
            if any(pn in p for pn in _PERSON_PRONOUNS):
                return 0
            return max(1, len(p) // 40)
        for idx, para, _cnt in _top_paragraphs_matching(paragraphs, _pred, limit=2):
            issues.append(
                DirectnessIssue(
                    id=f"DIRECTNESS_{base_id}_{idx}",
                    dimension=dim_score.key,
                    severity=severity,
                    description=f"第 {idx} 段为空描写（无对话、无人物动作）",
                    suggest_rewrite="插入人物动作/心理独白或对话，避免长段纯环境",
                    line_range=(idx, idx),
                    evidence={"excerpt": para[:80]},
                )
            )
    elif dim_score.key == "D6_nesting_depth":
        for idx, para, cnt in _top_paragraphs_matching(
            paragraphs, _d6_nesting_predicate, limit=2
        ):
            issues.append(
                DirectnessIssue(
                    id=f"DIRECTNESS_{base_id}_{idx}",
                    dimension=dim_score.key,
                    severity=severity,
                    description=f"嵌套深度 {dim_score.value:.2f} 触发 {dim_score.rating}，第 {idx} 段平均 {cnt} 层嵌套",
                    suggest_rewrite="拆长嵌套句为短句，一句一动作，减少逗号分隔子句",
                    line_range=(idx, idx),
                    evidence={"excerpt": para[:80]},
                )
            )
    elif dim_score.key == "D7_modifier_chain_length":
        for idx, para, cnt in _top_paragraphs_matching(
            paragraphs, _d7_modifier_predicate, limit=2
        ):
            issues.append(
                DirectnessIssue(
                    id=f"DIRECTNESS_{base_id}_{idx}",
                    dimension=dim_score.key,
                    severity=severity,
                    description=f"修饰链长 {dim_score.value:.2f} 触发 {dim_score.rating}，第 {idx} 段最长链 {cnt} 的",
                    suggest_rewrite="削减多层'的'修饰，把修饰词改为直接叙述或动作描写",
                    line_range=(idx, idx),
                    evidence={"excerpt": para[:80]},
                )
            )
    return issues


def run_directness_check(
    chapter_text: str,
    *,
    chapter_no: int,
    scene_mode: str | None = None,
    thresholds: dict[str, Any] | None = None,
    abstract_words: Sequence[str] | None = None,
    directness_skip: bool = False,
    directness_tier: str | None = None,
) -> DirectnessReport:
    """对单章正文跑直白度评分（US-006 全场景激活 + directness_tier 阈值桶）。

    参数:
      chapter_text: 章节正文
      chapter_no: 章节号
      scene_mode: 场景模式（不影响激活，仅用于 bucket 选择）
      thresholds: 完整 YAML 结构（已 load_thresholds）或 None → 自动加载
      abstract_words: 抽象词表；None → 使用 prose-blacklist + seed 默认
      directness_skip: True → 跳过直白检查（向后兼容老 outline）
      directness_tier: 阈值桶选择（'explosive_hit' | 'standard'）；None → 沿用场景桶
    """
    activated = is_activated(scene_mode, chapter_no, directness_skip=directness_skip)
    if not activated:
        return DirectnessReport(
            skipped=True,
            reason="chapter_meta.directness_skip=true — 向后兼容老 outline",
            scene_mode=scene_mode,
            chapter_no=chapter_no,
            overall_score=0.0,
            passed=True,
            severity="skipped",
            dimensions=(),
            issues=(),
            metrics_raw={},
        )

    loaded = thresholds if thresholds is not None else load_thresholds()
    buckets = loaded.get("scenes", {}) if isinstance(loaded, dict) else {}
    root_tiers = loaded.get("tiers", {}) if isinstance(loaded, dict) else {}
    bucket_name, dim_thresholds = _resolve_scene_bucket(
        scene_mode, chapter_no, buckets,
        directness_tier=directness_tier, tiers=root_tiers,
    )

    if abstract_words is None:
        abstract_words = _load_abstract_words()

    metrics = _compute_metrics(chapter_text, abstract_words=abstract_words)

    # US-007: D6/D7 inline computation
    d6_nesting = _calc_d6_nesting_depth(chapter_text)
    d7_mean, d7_max = _calc_d7_modifier_chain_length(chapter_text)
    metrics["D6_nesting_depth"] = round(d6_nesting, 4)
    metrics["D7_modifier_chain_length"] = round(d7_mean, 4)

    dim_scores: list[DimensionScore] = []
    for key in DIMENSION_KEYS:
        raw_value = float(metrics.get(key, 0.0))
        dim_scores.append(score_dimension(key, raw_value, dim_thresholds))

    issues: list[DirectnessIssue] = []
    for ds in dim_scores:
        issues.extend(_issue_for_dimension(ds, chapter_text, abstract_words))

    any_red = any(d.rating == "red" for d in dim_scores)
    all_green = all(d.rating == "green" for d in dim_scores)
    if any_red:
        severity = "red"
        passed = False
    elif all_green:
        severity = "green"
        passed = True
    else:
        severity = "yellow"
        passed = True

    overall = sum(d.score for d in dim_scores) / max(len(dim_scores), 1)

    return DirectnessReport(
        skipped=False,
        reason=f"bucket={bucket_name}",
        scene_mode=scene_mode,
        chapter_no=chapter_no,
        overall_score=overall,
        passed=passed,
        severity=severity,
        dimensions=tuple(dim_scores),
        issues=tuple(issues),
        metrics_raw={
            "D1_rhetoric_density": metrics.get("D1_rhetoric_density", 0.0),
            "D2_adj_verb_ratio": metrics.get("D2_adj_verb_ratio", 0.0),
            "D3_abstract_per_100_chars": metrics.get("D3_abstract_per_100_chars", 0.0),
            "D4_sent_len_median": metrics.get("D4_sent_len_median", 0.0),
            "D5_empty_paragraphs": metrics.get("D5_empty_paragraphs", 0),
            "D6_nesting_depth": metrics.get("D6_nesting_depth", 0.0),
            "D7_modifier_chain_length": metrics.get("D7_modifier_chain_length", 0.0),
            "D7_modifier_max_chain": d7_max,
            "char_count": metrics.get("char_count", 0),
            "sentence_count": metrics.get("sentence_count", 0),
            "paragraph_count": metrics.get("paragraph_count", 0),
            "bucket_used": bucket_name,
        },
    )


def _load_abstract_words() -> Sequence[str]:
    """优先从 prose-blacklist.yaml 取 abstract_adjectives；失败回落 seed。"""
    try:
        from ink_writer.prose.blacklist_loader import load_blacklist  # noqa: PLC0415

        bundle = load_blacklist()
        words = [e.word for e in bundle.abstract_adjectives]
        if words:
            return tuple(words)
    except Exception:  # noqa: BLE001
        pass

    try:
        import sys as _sys  # noqa: PLC0415

        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        if str(scripts_dir) not in _sys.path:
            _sys.path.insert(0, str(scripts_dir))
        from analyze_prose_directness import (  # type: ignore[import-not-found]  # noqa: PLC0415
            _ABSTRACT_SEED,
        )

        return _ABSTRACT_SEED
    except Exception:  # noqa: BLE001
        return ()


def to_checker_output(report: DirectnessReport) -> dict[str, Any]:
    """把 DirectnessReport 转换为 checker-output-schema.md 标准 JSON 结构。"""
    if report.skipped:
        return {
            "agent": "directness-checker",
            "chapter": report.chapter_no,
            "overall_score": 100,
            "pass": True,
            "issues": [],
            "metrics": {"skipped": True, "reason": report.reason},
            "summary": f"章节级 directness_skip 生效，直白检查已跳过（{report.reason}）",
        }

    overall_100 = int(round(report.overall_score * 10))
    if report.dimensions:
        weakest = min(report.dimensions, key=lambda d: d.score)
        summary = (
            f"{_DIMENSION_LABELS.get(weakest.key, weakest.key)} 最低 "
            f"{weakest.score:.1f} → {report.severity}"
        )
    else:
        summary = f"无维度评分 → {report.severity}"

    return {
        "agent": "directness-checker",
        "chapter": report.chapter_no,
        "overall_score": overall_100,
        "pass": report.passed,
        "issues": [i.to_dict() for i in report.issues],
        "metrics": {
            "scene_mode": report.scene_mode,
            "severity": report.severity,
            "dimensions": [d.to_dict() for d in report.dimensions],
            "raw": report.metrics_raw,
        },
        "summary": summary,
    }


__all__ = [
    "ACTIVATION_SCENE_MODES",
    "DIMENSION_KEYS",
    "DirectnessIssue",
    "DirectnessReport",
    "DimensionScore",
    "GREEN_SCORE",
    "RED_SCORE",
    "SKIPPED_SCENE_MODES",
    "_calc_d6_nesting_depth",
    "_calc_d7_modifier_chain_length",
    "clear_cache",
    "is_activated",
    "load_thresholds",
    "run_directness_check",
    "score_dimension",
    "to_checker_output",
]
