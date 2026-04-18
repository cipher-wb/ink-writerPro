"""Reflection agent — produces macro-level "emergent phenomena" bullets.

US-022: every N chapters (default 50) scan the most-recent chapter summaries
and the character-progression ledger to surface patterns that the writer may
not be tracking explicitly: repeated entities, emotion peaks, dense
foreshadow clusters, multi-chapter arcs, etc.  The output is a small JSON
manifest at ``.ink/reflections.json`` that the context-agent can append to
its memory section (L2 long-memory layer).

Design principles:
- Pure Python heuristics (zero-LLM) — identical rationale to the L1
  compressor.  A ``use_llm`` hook is exposed for future upgrade but not wired
  to any SDK in this module.
- No hard dependency on the index DB; the agent reads JSON/MD files under
  ``.ink/`` that are already written by existing pipelines (summaries dir,
  progressions file, index.db is optional).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_INTERVAL = 50
DEFAULT_BULLET_MIN = 3
DEFAULT_BULLET_MAX = 5
REFLECTIONS_FILE = "reflections.json"


@dataclass
class ReflectionResult:
    chapter: int
    window: int
    bullets: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    mode: str = "heuristic"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Data loading helpers (all defensive: missing files -> empty inputs).
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z][A-Za-z0-9_]+")


def _load_recent_summaries(project_root: Path, chapter: int, window: int) -> List[Dict[str, Any]]:
    summaries_dir = project_root / ".ink" / "summaries"
    out: List[Dict[str, Any]] = []
    start = max(1, chapter - window + 1)
    for ch in range(start, chapter + 1):
        f = summaries_dir / f"ch{ch:04d}.md"
        if not f.exists():
            continue
        raw = f.read_text(encoding="utf-8")
        body = raw
        fm: Dict[str, str] = {}
        m = _FM_RE.match(raw)
        if m:
            for line in m.group(1).split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
            body = m.group(2).strip()
        out.append({"chapter": ch, "frontmatter": fm, "body": body})
    return out


def _load_progressions(project_root: Path, chapter: int, window: int) -> List[Dict[str, Any]]:
    """Read progression rows, preferring the JSON cache over index.db."""
    start = chapter - window + 1
    # Preferred: JSON snapshot (written by progression module tests/pipelines).
    json_path = project_root / ".ink" / "progressions.json"
    if json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else raw.get("progressions", [])
            return [r for r in rows if int(r.get("chapter_no", 0)) >= start and int(r.get("chapter_no", 0)) <= chapter]
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback: index.db character_evolution_ledger (optional).
    db = project_root / ".ink" / "index.db"
    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT chapter as chapter_no, entity_id, dimension, from_value, to_value, cause
                FROM character_evolution_ledger
                WHERE chapter >= ? AND chapter <= ?
                ORDER BY chapter
                """,
                (start, chapter),
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return []
    return []


def _load_foreshadow(project_root: Path) -> List[Dict[str, Any]]:
    f = project_root / ".ink" / "foreshadow.json"
    if not f.exists():
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(raw, list):
        return raw
    return raw.get("items", raw.get("foreshadows", []))


# ---------------------------------------------------------------------------
# Heuristics: surface emergent phenomena.
# ---------------------------------------------------------------------------

_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def _top_entities(summaries: List[Dict[str, Any]], min_hits: int = 3) -> List[Tuple[str, int]]:
    """Rough entity frequency using CJK bigrams (2-char names)."""
    counts: Dict[str, int] = {}
    for entry in summaries:
        text = entry.get("body", "")
        for i in range(len(text) - 1):
            a, b = text[i], text[i + 1]
            if _CJK_CHAR_RE.match(a) and _CJK_CHAR_RE.match(b):
                bigram = a + b
                counts[bigram] = counts.get(bigram, 0) + 1
    # drop common stopword bigrams / frequent function words
    stop = {
        "自己", "他们", "这个", "那个", "一下", "一些", "可以", "时候",
        "然后", "但是", "因为", "所以", "再次", "上风", "交手", "发生",
        "章节", "关键", "内容", "事件", "进展", "获得", "取得",
    }
    ranked = [(k, v) for k, v in counts.items() if v >= min_hits and k not in stop]
    ranked.sort(key=lambda x: (-x[1], x[0]))
    return ranked[:5]


def _progression_hotspots(progressions: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for row in progressions:
        eid = str(row.get("entity_id") or row.get("char_id") or "")
        if not eid:
            continue
        counts[eid] = counts.get(eid, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [(k, v) for k, v in ranked if v >= 2][:3]


def _foreshadow_density(
    foreshadows: List[Dict[str, Any]], chapter: int, window: int
) -> int:
    start = chapter - window + 1
    open_items = 0
    for item in foreshadows:
        status = (item.get("status") or "").lower()
        planted_at = int(item.get("planted_chapter") or item.get("introduced_chapter") or 0)
        if planted_at >= start and planted_at <= chapter and status != "resolved":
            open_items += 1
    return open_items


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------

def run_reflection(
    project_root: Path | str,
    current_chapter: int,
    window: int = DEFAULT_INTERVAL,
    use_llm: bool = False,
    write: bool = True,
) -> ReflectionResult:
    """Analyse the last ``window`` chapters and produce emergent bullets.

    Always returns a :class:`ReflectionResult`.  When ``write=True`` the result
    is persisted to ``.ink/reflections.json``.  Callers who only want a
    preview (e.g. CLI dry-run) can pass ``write=False``.
    """
    project_root = Path(project_root)
    window = max(5, int(window))

    summaries = _load_recent_summaries(project_root, current_chapter, window)
    progressions = _load_progressions(project_root, current_chapter, window)
    foreshadows = _load_foreshadow(project_root)

    bullets: List[str] = []
    evidence: Dict[str, Any] = {}

    # (1) Recurring entities.
    top_entities = _top_entities(summaries)
    if top_entities:
        ent_desc = "、".join(f"{n}×{c}" for n, c in top_entities[:3])
        bullets.append(f"高频实体：{ent_desc}（近{window}章反复出现，考虑推进其专属剧情）")
        evidence["top_entities"] = top_entities

    # (2) Progression hotspots.
    hotspots = _progression_hotspots(progressions)
    if hotspots:
        hs_desc = "、".join(f"{eid}({cnt}条)" for eid, cnt in hotspots)
        bullets.append(f"角色演进热点：{hs_desc}——近{window}章累积多条维度变化")
        evidence["progression_hotspots"] = hotspots

    # (3) Foreshadow density.
    fore_open = _foreshadow_density(foreshadows, current_chapter, window)
    if fore_open >= 3:
        bullets.append(f"伏笔密度警戒：近{window}章新植入{fore_open}条未回收伏笔，建议排兑现表")
        evidence["foreshadow_open_in_window"] = fore_open

    # (4) Arc length signal: if window chapters all exist, call out the stretch.
    if len(summaries) >= max(10, window // 2):
        bullets.append(
            f"跨度观察：近{window}章已积累{len(summaries)}条摘要，适合一次中线回望+悬念再聚焦"
        )
        evidence["summary_span"] = len(summaries)

    # (5) Fallback — if nothing else surfaced, add a neutral observation.
    if not bullets:
        bullets.append(
            f"第{current_chapter}章例行反省：近{window}章无显著信号，维持当前节奏"
        )

    # Clamp to 3-5 bullets.
    while len(bullets) < DEFAULT_BULLET_MIN:
        bullets.append(f"保留位：第{current_chapter}章时保持既有主线不偏离")
    bullets = bullets[:DEFAULT_BULLET_MAX]

    result = ReflectionResult(
        chapter=current_chapter,
        window=window,
        bullets=bullets,
        evidence=evidence,
        mode="llm_prompt" if use_llm else "heuristic",
    )

    if write:
        ink_dir = project_root / ".ink"
        ink_dir.mkdir(parents=True, exist_ok=True)
        out = ink_dir / REFLECTIONS_FILE
        # Preserve history: append to list if file already has entries.
        history: List[Dict[str, Any]] = []
        if out.exists():
            try:
                prev = json.loads(out.read_text(encoding="utf-8"))
                if isinstance(prev, dict) and "history" in prev:
                    history = list(prev.get("history") or [])
                elif isinstance(prev, list):
                    history = list(prev)
            except (json.JSONDecodeError, OSError):
                history = []
        history.append(result.to_dict())
        payload = {
            "latest": result.to_dict(),
            "history": history[-10:],  # keep last 10 reflections max
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def load_reflections(project_root: Path | str) -> Optional[Dict[str, Any]]:
    """Load the most recent reflections payload, if any.

    Returns ``None`` when no file exists or when the file is corrupted.
    """
    f = Path(project_root) / ".ink" / REFLECTIONS_FILE
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        return {"latest": raw[-1], "history": raw}
    return None


def should_trigger(current_chapter: int, interval: int = DEFAULT_INTERVAL) -> bool:
    """Helper: trigger reflection on multiples of the interval (>= interval)."""
    if current_chapter < interval:
        return False
    return current_chapter % interval == 0
