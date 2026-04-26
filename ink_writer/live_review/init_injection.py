"""US-LR-011: ink-init Step 99.5 — D (反向检索) + B (阈值告警) 组合 UI。

`check_genre(user_genre_input)` 返回 dict 含 warning_level / similar_cases /
genre_stats / suggested_actions / render_text，供 ink-init 末尾步骤直接消费。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ink_writer.live_review.config import LiveReviewConfig, load_config
from ink_writer.live_review.genre_retrieval import (
    DEFAULT_INDEX_DIR,
    retrieve_similar_cases,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GENRE_STATS = _REPO_ROOT / "data" / "live-review" / "genre_acceptance.json"

_GENRE_SPLIT_RE = re.compile(r"[+,，、/\s]+")


def _split_genres(user_input: str) -> list[str]:
    """Split user input by common separators; fallback to whole string."""
    parts = [p.strip() for p in _GENRE_SPLIT_RE.split(user_input or "") if p.strip()]
    return parts or ([user_input.strip()] if user_input and user_input.strip() else [])


def _disabled_response() -> dict:
    return {
        "warning_level": "ok",
        "similar_cases": [],
        "genre_stats": None,
        "suggested_actions": [],
        "render_text": "",
    }


def _load_genre_acceptance(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _match_genre_stats(
    candidates: list[str], acceptance: dict
) -> tuple[str | None, dict | None]:
    """Return (matched_genre_name, stats_dict) from acceptance.genres if any candidate hits."""
    genres_block = acceptance.get("genres") or {}
    for candidate in candidates:
        if candidate in genres_block:
            return candidate, genres_block[candidate]
    return None, None


def _build_render_text(
    user_input: str,
    warning_level: str,
    similar_cases: list[dict],
    matched_genre: str | None,
    genre_stats: dict | None,
    suggested_actions: list[str],
) -> str:
    lines: list[str] = []
    lines.append("📚 星河直播相似案例 (174 份直播 × 10+ 本/份)")
    if similar_cases:
        for i, case in enumerate(similar_cases, 1):
            score = case.get("score")
            score_str = f"{score}分" if isinstance(score, (int, float)) else "未评分"
            verdict = case.get("verdict") or "unknown"
            title = case.get("title_guess") or case.get("case_id", "")
            lines.append(
                f"  [{i}] {title} ({verdict} / {score_str}) "
                f"[cos={case.get('cosine_sim', 0):.3f}]"
            )
            comment = (case.get("overall_comment") or "").strip()
            if comment:
                lines.append(f"      → {comment}")
    else:
        lines.append("  (无相似案例)")

    lines.append("")
    if matched_genre and genre_stats:
        score_mean = genre_stats.get("score_mean")
        pass_rate = genre_stats.get("verdict_pass_rate")
        complaints = genre_stats.get("common_complaints") or []
        complaint_summary = ", ".join(
            f"{c.get('dimension', '?')}({c.get('frequency', 0):.0%})" for c in complaints[:3]
        ) or "无显著差评维度"
        score_text = f"{score_mean:.1f}" if isinstance(score_mean, (int, float)) else "无打分数据"
        pass_rate_text = (
            f"{pass_rate:.0%}" if isinstance(pass_rate, (int, float)) else "无签约信号"
        )
        lines.append(
            f"🎯 该题材统计 ({matched_genre}): 均分 {score_text} / 签约率 {pass_rate_text} / "
            f"主要差评 {complaint_summary}"
        )
    else:
        lines.append(
            f"🎯 该题材统计: 暂未在 174 份直播覆盖范围 (input='{user_input}'); 不构成阻断信号"
        )

    lines.append("")
    if warning_level == "warn":
        lines.append("⚠️ 警告：该题材整体得分低于 init_genre_warning_threshold，请二次确认。")

    if suggested_actions:
        lines.append("💡 写作建议：")
        for action in suggested_actions:
            lines.append(f"  - {action}")
    else:
        lines.append("💡 写作建议：参考相似案例 overall_comment 段。")

    return "\n".join(lines)


def _suggested_actions_for(
    warning_level: str, genre_stats: dict | None, similar_cases: list[dict]
) -> list[str]:
    actions: list[str] = []
    if warning_level == "warn" and genre_stats:
        complaints = genre_stats.get("common_complaints") or []
        for c in complaints[:3]:
            dim = c.get("dimension")
            if dim:
                actions.append(f"重点审查 {dim} 维度 — 该题材高频差评点")
    if warning_level == "no_data":
        actions.append("当前题材在 174 份直播中无聚合数据；可参考 top-K 相似案例回退判断。")
    if warning_level == "ok" and similar_cases:
        actions.append("沿用 top-K 相似案例的 overall_comment 经验；该题材整体接受度可。")
    return actions


def check_genre(
    user_genre_input: str,
    *,
    top_k: int = 3,
    config_path: Path | None = None,
    genre_stats_path: Path | None = None,
    index_dir: Path | None = None,
) -> dict:
    """Check user-input genre against live-review aggregated stats + retrieval.

    Returns a dict with keys:
      - warning_level: 'ok' | 'warn' | 'no_data'
      - similar_cases: list of retrieved cases (with cosine_sim)
      - genre_stats: matched genre's stats dict (or None)
      - suggested_actions: list of suggestions (may be empty)
      - render_text: ASCII-rendered terminal output
    """
    cfg: LiveReviewConfig = load_config(config_path)
    if not cfg.enabled or not cfg.inject_into.init:
        return _disabled_response()

    stats_path = Path(genre_stats_path) if genre_stats_path is not None else DEFAULT_GENRE_STATS
    idx_dir = Path(index_dir) if index_dir is not None else DEFAULT_INDEX_DIR
    threshold = cfg.init_genre_warning_threshold
    effective_top_k = top_k or cfg.init_top_k

    candidates = _split_genres(user_genre_input)
    acceptance = _load_genre_acceptance(stats_path)
    matched_genre, raw_stats = _match_genre_stats(candidates, acceptance)

    similar_cases = retrieve_similar_cases(
        user_genre_input, top_k=effective_top_k, index_dir=idx_dir
    )

    if matched_genre is None:
        warning_level = "no_data"
        genre_stats: dict | None = None
    else:
        score_mean = raw_stats.get("score_mean") if raw_stats else None
        if isinstance(score_mean, (int, float)) and score_mean < threshold:
            warning_level = "warn"
        else:
            warning_level = "ok"
        genre_stats = dict(raw_stats or {})
        genre_stats["genre"] = matched_genre

    suggested_actions = _suggested_actions_for(warning_level, genre_stats, similar_cases)
    render_text = _build_render_text(
        user_genre_input,
        warning_level,
        similar_cases,
        matched_genre,
        genre_stats,
        suggested_actions,
    )
    return {
        "warning_level": warning_level,
        "similar_cases": similar_cases,
        "genre_stats": genre_stats,
        "suggested_actions": suggested_actions,
        "render_text": render_text,
    }


__all__ = ["check_genre", "DEFAULT_GENRE_STATS"]
