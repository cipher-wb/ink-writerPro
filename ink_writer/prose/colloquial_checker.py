"""US-004: Colloquial-checker 5 维度白话度核心算法（PRD prose-anti-ai-overhaul）。

提供 5 维度（C1-C5）"白话度"评分：

  - C1 idiom_density        —— 成语命中数 / 千字
  - C2 quad_phrase_density  —— 4 字格数 / 千字（已扣除 C1 命中的成语 + 人名地名白名单）
  - C3 abstract_noun_chain  —— "A 的 B 的 C" 抽象名词链命中数 / 千字
  - C4 modifier_chain_avg   —— 每名词前修饰语链均长（基于 "的" 切分）
  - C5 abstract_subject     —— 段首句主语为抽象名词的占比（0..1）

5 维度全部 lower-is-better（"白话度"恰好与"装逼度"反向）。任一维度 <RED_SCORE → red；
全 ≥GREEN_SCORE → green；否则 yellow。激活策略由调用方决定（PRD 默认全场景激活）。

阈值结构：``thresholds[dim_key] = {"direction": "lower_is_better",
"green_max": float, "yellow_max": float}``。函数内不硬编码——默认值见
``_DEFAULT_THRESHOLDS``，由 ``run_colloquial_check(..., thresholds=...)`` 覆盖。

数据依赖：
  - ``ink_writer/prose/idiom_dict.txt``（≥ 500 常见成语，C1 词典）
  - ``ink-writer/assets/prose-blacklist.yaml`` ``pretentious_nouns`` 域（C3/C5 抽象名词集）
  - 内置 ``_DEFAULT_NAME_WHITELIST``（4 字常见网文人名/地名片段，C2 排除）
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


DIMENSION_KEYS: tuple[str, ...] = (
    "C1_idiom_density",
    "C2_quad_phrase_density",
    "C3_abstract_noun_chain",
    "C4_modifier_chain_avg",
    "C5_abstract_subject_rate",
)

_DIMENSION_LABELS: dict[str, str] = {
    "C1_idiom_density": "成语密度",
    "C2_quad_phrase_density": "四字格密度",
    "C3_abstract_noun_chain": "抽象名词链",
    "C4_modifier_chain_avg": "修饰语链均长",
    "C5_abstract_subject_rate": "抽象主语率",
}

GREEN_SCORE: float = 8.0
RED_SCORE: float = 6.0


# 默认阈值——5 维度全部 lower-is-better（直白档 / 爆款风）。
# 数值基于 PRD 设计目标 G1-G3：成语 ≤ 3/千字、四字格 ≤ 6/千字、嵌套深度 ≤ 1.5。
# US-014 calibration 脚本会用 5 爆款 + 5 严肃文学跑回归覆写这些占位值。
_DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "C1_idiom_density": {
        "direction": "lower_is_better",
        "green_max": 3.0,
        "yellow_max": 5.0,
    },
    "C2_quad_phrase_density": {
        "direction": "lower_is_better",
        "green_max": 6.0,
        "yellow_max": 10.0,
    },
    "C3_abstract_noun_chain": {
        "direction": "lower_is_better",
        "green_max": 0.5,
        "yellow_max": 1.5,
    },
    "C4_modifier_chain_avg": {
        "direction": "lower_is_better",
        "green_max": 1.5,
        "yellow_max": 2.5,
    },
    "C5_abstract_subject_rate": {
        "direction": "lower_is_better",
        "green_max": 0.10,
        "yellow_max": 0.25,
    },
}

_DEFAULT_IDIOM_PATH = Path(__file__).resolve().parent / "idiom_dict.txt"

# 4-char Chinese block 探测正则。覆盖 CJK 基本汉字 U+4E00 .. U+9FA5。
_QUAD_CHAR_RE = re.compile(r"[一-龥]{4}")
_HAN_RE = re.compile(r"[一-龥]")

# 段落 / 句子切分。与 directness_checker 一致以便互相印证。
_PARA_SPLIT_RE = re.compile(r"\n+")
_SENT_SPLIT_RE = re.compile(r"[。！？!?；;…]+")

# C5 主语判定时跳过的"非主语字符"——人称代词命中段首即认为主语非抽象名词。
_PERSON_PRONOUNS: frozenset[str] = frozenset(
    {"他", "她", "它", "我", "你", "咱", "您", "俺", "吾"}
)
_PRONOUN_PREFIXES: tuple[str, ...] = ("他们", "她们", "它们", "我们", "你们", "咱们", "诸位")

# C2 排除：常见 4 字人名 / 称谓 / 地名片段；命中即不计入"四字格"。
# 词表克制：保留高频"假阳性"，避免把所有人名都拉进来（ink-init 项目级人名靠 abstract_nouns
# 覆盖不到的部分由调用方传入 ``name_whitelist`` 注入项目专用名）。
_DEFAULT_NAME_WHITELIST: frozenset[str] = frozenset(
    {
        # 常见网文称谓
        "陛下殿下", "公子小姐", "皇上太子",
        # 网文常用书名号 / 通名
        "天地玄黄", "日月星辰",
        # 历史 / 神话
        "三皇五帝", "尧舜禹汤",
    }
)


@dataclass(frozen=True)
class DimensionScore:
    """单维度评分结果，结构与 directness_checker.DimensionScore 对齐。"""

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
class ColloquialReport:
    """完整白话度报告。``run_colloquial_check`` 返回 dict 时取 ``to_dict()``。"""

    overall_score: float
    passed: bool
    severity: str
    dimensions: tuple[DimensionScore, ...]
    metrics_raw: dict[str, Any]
    chain_hits: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2),
            "passed": self.passed,
            "severity": self.severity,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "metrics_raw": dict(self.metrics_raw),
            "chain_hits": [dict(h) for h in self.chain_hits],
        }


# ---------------------------------------------------------------------------
# Lazy-loaded shared resources
# ---------------------------------------------------------------------------


_IDIOM_CACHE: dict[tuple[str, int], frozenset[str]] = {}


def clear_cache() -> None:
    """测试钩子：清空 idiom_dict.txt 解析缓存。"""
    _IDIOM_CACHE.clear()


def _load_idioms(path: Path | None = None) -> frozenset[str]:
    """读取 idiom_dict.txt 返回成语集合；按 (path, mtime_ns) 缓存。

    格式：每行一个 4 字成语；``#`` 开头注释 / 空行忽略。文件缺失时返回空集，
    不抛异常（C1 维度自动得 0/千字 → green）。
    """
    target = (path or _DEFAULT_IDIOM_PATH).resolve()
    try:
        mtime_ns = target.stat().st_mtime_ns if target.exists() else 0
    except OSError:
        mtime_ns = 0
    cache_key = (str(target), mtime_ns)
    cached = _IDIOM_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not target.exists() or not target.is_file():
        _IDIOM_CACHE[cache_key] = frozenset()
        return frozenset()

    words: set[str] = set()
    try:
        with target.open("r", encoding="utf-8") as f:
            for raw in f:
                token = raw.strip()
                if not token or token.startswith("#"):
                    continue
                if _QUAD_CHAR_RE.fullmatch(token):
                    words.add(token)
    except OSError as exc:
        logger.warning("idiom_dict load failed: %s", exc)
        _IDIOM_CACHE[cache_key] = frozenset()
        return frozenset()

    bundle = frozenset(words)
    _IDIOM_CACHE[cache_key] = bundle
    return bundle


def _load_default_abstract_nouns() -> frozenset[str]:
    """从 prose-blacklist.yaml ``pretentious_nouns`` 取抽象名词集。

    YAML 缺失或加载失败时返回小型 fallback 集合；不抛异常。
    """
    try:
        from ink_writer.prose.blacklist_loader import load_blacklist  # noqa: PLC0415

        bundle = load_blacklist()
        words = {e.word for e in bundle.pretentious_nouns}
        if words:
            return frozenset(words)
    except Exception:  # noqa: BLE001
        pass

    return frozenset(
        {"宿命", "虚无", "苍茫", "沧桑", "孤寂", "静谧", "缥缈", "迷离", "缱绻"}
    )


# ---------------------------------------------------------------------------
# Scoring helpers (lower_is_better only)
# ---------------------------------------------------------------------------


def _rating_from_score(score: float) -> str:
    if score >= GREEN_SCORE:
        return "green"
    if score >= RED_SCORE:
        return "yellow"
    return "red"


def _score_lower_is_better(value: float, green_max: float, yellow_max: float) -> float:
    """与 directness_checker._score_lower_is_better 一致；保持跨 checker 一致曲线。"""
    if value <= green_max:
        return 10.0
    if value <= yellow_max:
        span = max(yellow_max - green_max, 1e-9)
        return max(0.0, 10.0 - 4.0 * ((value - green_max) / span))
    span = max(yellow_max, 1e-9)
    over = value - yellow_max
    return max(0.0, 6.0 - 6.0 * min(over / span, 1.0))


def score_dimension(
    metric_key: str, value: float, thresholds: dict[str, Any]
) -> DimensionScore:
    """单维度打分。未识别 metric / direction → 默认 10 分（中性）。"""
    dim = thresholds.get(metric_key) or _DEFAULT_THRESHOLDS.get(metric_key)
    if dim is None:
        return DimensionScore(
            key=metric_key,
            value=float(value),
            score=10.0,
            rating="green",
            direction="lower_is_better",
        )
    direction = dim.get("direction", "lower_is_better")
    if direction == "lower_is_better":
        score = _score_lower_is_better(
            float(value),
            green_max=float(dim["green_max"]),
            yellow_max=float(dim["yellow_max"]),
        )
    else:
        logger.warning(
            "colloquial_checker: unknown threshold direction %r for %s, default 10",
            direction,
            metric_key,
        )
        score = 10.0
    return DimensionScore(
        key=metric_key,
        value=float(value),
        score=round(float(score), 2),
        rating=_rating_from_score(score),
        direction=direction,
    )


# ---------------------------------------------------------------------------
# C1 — idiom density
# ---------------------------------------------------------------------------


def _han_char_count(text: str) -> int:
    """文本中汉字字符数；用于"千字"分母（标点 / ASCII / 空白不计）。"""
    return sum(1 for _ in _HAN_RE.finditer(text))


def _find_idioms(text: str, idiom_set: frozenset[str]) -> list[tuple[int, str]]:
    """扫描所有 4 字汉字窗口，凡是在 idiom_set 中的视为成语命中。

    返回 ``(start_index, idiom)`` 列表，按出现顺序。重叠窗口（如"一帆风顺顺水"
    含"一帆风顺"+"顺水推舟"理论可能）会双计——这是网文反 AI 味语境下"任何成语
    出现"都计入密度的需求。
    """
    if not idiom_set:
        return []
    hits: list[tuple[int, str]] = []
    # 借 _QUAD_CHAR_RE 滚动扫描；finditer 已 non-overlapping，但成语相邻位仍可能漏；
    # 因此独立按字符 stride=1 扫描每个起点的 4 字窗口。
    n = len(text)
    for i in range(n - 3):
        window = text[i : i + 4]
        if _QUAD_CHAR_RE.fullmatch(window) and window in idiom_set:
            hits.append((i, window))
    return hits


# ---------------------------------------------------------------------------
# C2 — quad phrase density
# ---------------------------------------------------------------------------


_HAN_RUN_RE = re.compile(r"[一-龥]+")


def _find_quad_phrases(
    text: str,
    *,
    idiom_set: frozenset[str],
    name_whitelist: frozenset[str],
) -> list[tuple[int, str]]:
    """识别"四字格排比" —— 连续 ≥ 3 个标点分隔的 4 字汉字片段构成的真排比。

    PRD 的真实信号是"成语堆叠 / 四字格排比"——*三个及以上* 平行 4 字单元才是排比；
    爆款风偶尔出现的两连 4 字短句（"刀风带响。陈风没躲" / "仰头喝光，抹一下嘴"）
    属于动作节奏而非装逼，不计。例：

      *计入*：``红尘滚滚，浮生若茶。岁月蹉跎，光阴荏苒。日月如梭，白驹过隙``
              （6 连 4 字格，明显堆砌）。
      *不计*：``刀风带响。陈风没躲``（仅 2 连，正常爆款短句）。

    扣除条件（命中后从 stack 里逐个剔除，剔除后 stack 仍 < 3 时整 stack 失效）：
      - 4 字片段属于成语词典（已在 C1 计过，这里不双计）
      - 属于人名 / 地名白名单
      - 同字四叠（"哈哈哈哈"）

    返回 ``(start_index, phrase)`` 列表（仅 stack ≥ 3 时计入，且只数"非过滤"项）。
    """
    # 1) 先按"任何非汉字字符"切分，得到所有汉字片段及其位置。
    segments: list[tuple[int, str]] = []
    for match in _HAN_RUN_RE.finditer(text):
        run = match.group(0)
        if not run:
            continue
        segments.append((match.start(), run))

    # 2) 顺序扫描，捕捉连续 4 字片段的"窗口"。窗口由"非 4 字"片段或文本结尾终止。
    #    每个窗口里再扣除 idiom / name / 同字四叠；剩余项 ≥ 2 才计入 hits。
    hits: list[tuple[int, str]] = []
    window: list[tuple[int, str]] = []

    def _flush() -> None:
        kept = [
            (pos, run)
            for pos, run in window
            if run not in idiom_set
            and run not in name_whitelist
            and len(set(run)) > 1
        ]
        if len(kept) >= 3:
            hits.extend(kept)
        window.clear()

    for pos, run in segments:
        if len(run) == 4:
            window.append((pos, run))
        else:
            _flush()
    _flush()

    return hits


# ---------------------------------------------------------------------------
# C3 — abstract noun chain "A 的 B 的 C"
# ---------------------------------------------------------------------------


_CHAIN_BREAKER_RE = re.compile(r"[，。！？；：,.!?;:\s　、…]")


def _find_abstract_chains(
    text: str,
    abstract_nouns: frozenset[str],
) -> list[dict[str, Any]]:
    """检测"抽象名词1 的 抽象名词2 的 抽象名词3"链。

    实现：句子切分后，按"的"分块，连续 ≥ 3 个块若全为抽象名词（或以抽象名词
    结尾的短语），命中。返回 ``[{position, snippet, members}]`` 列表。

    注意：宽松匹配——块内只要"出现"任一抽象名词即视为抽象（防止"宿命的孤寂的
    沧桑"中"宿命的"被切成"宿命"+空字符串）。
    """
    if not abstract_nouns:
        return []
    chains: list[dict[str, Any]] = []
    sentences = [s for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    cursor = 0
    for sent in sentences:
        idx = text.find(sent, cursor)
        if idx == -1:
            idx = cursor
        cursor = idx + len(sent)

        # 直接按"的"切句
        parts = sent.split("的")
        if len(parts) < 3:
            continue
        # parts[0..-2] 都"前面跟着的"，parts[-1] 是结尾。我们要找 ≥3 个连续抽象块。
        # 例："宿命的孤寂的沧桑" → split → ["宿命","孤寂","沧桑"]
        run: list[str] = []
        run_start_in_sent: int | None = None
        offset = 0
        for i, chunk in enumerate(parts):
            matched = _chunk_matches_abstract(chunk, abstract_nouns)
            if matched:
                if run_start_in_sent is None:
                    run_start_in_sent = offset + max(0, chunk.find(matched))
                run.append(matched)
            else:
                if len(run) >= 3:
                    snippet = "的".join(run)
                    chains.append(
                        {
                            "position": idx + (run_start_in_sent or 0),
                            "snippet": snippet,
                            "members": tuple(run),
                        }
                    )
                run = []
                run_start_in_sent = None
            offset += len(chunk) + (1 if i < len(parts) - 1 else 0)  # +1 for "的"
        if len(run) >= 3:
            snippet = "的".join(run)
            chains.append(
                {
                    "position": idx + (run_start_in_sent or 0),
                    "snippet": snippet,
                    "members": tuple(run),
                }
            )
    return chains


def _chunk_matches_abstract(
    chunk: str, abstract_nouns: frozenset[str]
) -> str | None:
    """如果 chunk 能在首部 *或* 尾部对齐到一个抽象名词，返回该词；否则 None。

    PRD "A 的 B 的 C" 链中：
      * 中间项（修饰位）—— 整个 chunk 即为抽象名词，例 ``"宿命"``；
      * 尾项（主名词）—— chunk 起首或结尾是抽象名词，例 ``"沧桑萦绕"`` 起首匹配
        ``沧桑``，``"他眼中的宿命"`` 末位匹配 ``宿命``。
    优先 4→3→2 字（取最长），首尾各试一次。命中即返回该词，未命中返回 ``None``。
    """
    if not chunk:
        return None
    for length in (4, 3, 2):
        if len(chunk) < length:
            continue
        prefix = chunk[:length]
        if prefix in abstract_nouns:
            return prefix
        suffix = chunk[-length:]
        if suffix in abstract_nouns:
            return suffix
    return None


# ---------------------------------------------------------------------------
# C4 — modifier chain length
# ---------------------------------------------------------------------------


_MODIFIER_RUN_RE = re.compile(
    r"(?:[一-龥]{1,6}的){2,}[一-龥]{1,6}"
)


def _modifier_chains(text: str) -> tuple[float, int, int]:
    """识别"X 的 X 的 ... 的 N"修饰链；返回 (mean_length, max_length, count)。

    *length* = 链中"的"的个数（即修饰词数）。N 即被修饰名词，不计入修饰数。
    至少要有 ≥ 2 个 "的" 的链才进入统计——单个 "的" 在中文里是底噪，强制只计
    "嵌套" 链。

    文本中无名词链时返回 (0.0, 0, 0)。
    """
    counts: list[int] = []
    for match in _MODIFIER_RUN_RE.finditer(text):
        snippet = match.group(0)
        modifier_count = snippet.count("的")
        counts.append(modifier_count)
    if not counts:
        return (0.0, 0, 0)
    return (sum(counts) / len(counts), max(counts), len(counts))


# ---------------------------------------------------------------------------
# C5 — abstract subject rate
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for block in _PARA_SPLIT_RE.split(text):
        stripped = block.strip().lstrip("　").strip()
        if stripped:
            paragraphs.append(stripped)
    return paragraphs


def _first_sentence(paragraph: str) -> str:
    parts = _SENT_SPLIT_RE.split(paragraph, maxsplit=1)
    return parts[0].strip() if parts else paragraph.strip()


def _subject_is_abstract(
    sentence: str,
    abstract_nouns: frozenset[str],
    *,
    head_window: int = 8,
) -> bool:
    """判断段首句的主语是否为抽象名词。

    启发式：
      1. 取首 ``head_window`` 个汉字内的内容；
      2. 若起首字符为人称代词（他 / 她 / 我 / 你 / 它 / 咱 / 您）→ False；
      3. 若起首两字属"代词复数"前缀（他们 / 我们 / 你们 / 咱们 / ...）→ False；
      4. 否则若 head 中出现任一抽象名词且位置在第一个动词前（这里简化：在第一个 "的" /
         非汉字断点之前）→ True；
      5. 其他 → False。
    """
    if not sentence:
        return False
    head = sentence[:head_window]
    if not head:
        return False

    if head.startswith(_PRONOUN_PREFIXES):
        return False
    if head[0] in _PERSON_PRONOUNS:
        return False

    # 找抽象名词；位置必须 ≤ 首"的"位置（保证它在主语而非定语后的宾语）。
    first_de = head.find("的")
    first_break = _CHAIN_BREAKER_RE.search(head)
    cutoff = len(head)
    if first_de != -1:
        cutoff = min(cutoff, first_de + 1)
    if first_break is not None:
        cutoff = min(cutoff, first_break.start())
    head_subject_zone = head[:cutoff]

    return any(noun in head_subject_zone for noun in abstract_nouns)


def _abstract_subject_rate(
    text: str,
    abstract_nouns: frozenset[str],
) -> tuple[float, int, int]:
    """C5：返回 (rate, abstract_count, total_paragraphs)。"""
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return (0.0, 0, 0)
    abstract_count = 0
    for para in paragraphs:
        sent = _first_sentence(para)
        if _subject_is_abstract(sent, abstract_nouns):
            abstract_count += 1
    return (abstract_count / len(paragraphs), abstract_count, len(paragraphs))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_colloquial_check(
    text: str,
    *,
    thresholds: dict[str, dict[str, Any]] | None = None,
    idiom_set: Sequence[str] | frozenset[str] | None = None,
    abstract_nouns: Sequence[str] | frozenset[str] | None = None,
    name_whitelist: Sequence[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """跑 5 维度白话度评分，返回 ``ColloquialReport.to_dict()`` 结构。

    Args:
      text: 章节正文（包含换行/段落）。
      thresholds: 完整 thresholds 字典（key = DIMENSION_KEYS）。None → 默认值。
      idiom_set: 自定义成语集；None → 加载 ``idiom_dict.txt``。
      abstract_nouns: 自定义抽象名词集；None → 取 ``prose-blacklist.pretentious_nouns``。
      name_whitelist: 自定义人名/地名 4 字白名单；None → ``_DEFAULT_NAME_WHITELIST``。

    Returns:
      ``{"overall_score": ..., "passed": ..., "severity": ..., "dimensions":
      [...], "metrics_raw": {...}, "chain_hits": [...]}``。

    分母处理：
      - C1/C2 用"千字"（``_han_char_count(text) / 1000``，分母最小 0.001 防 0div）。
      - C3 用"千字"，与 C1/C2 同一标度便于对比。
      - C4 是均值，无需千字归一。
      - C5 是占比 [0..1]。
    """
    resolved_thresholds = thresholds if thresholds is not None else _DEFAULT_THRESHOLDS

    if idiom_set is None:
        idioms = _load_idioms()
    elif isinstance(idiom_set, frozenset):
        idioms = idiom_set
    else:
        idioms = frozenset(idiom_set)

    if abstract_nouns is None:
        abstract = _load_default_abstract_nouns()
    elif isinstance(abstract_nouns, frozenset):
        abstract = abstract_nouns
    else:
        abstract = frozenset(abstract_nouns)

    if name_whitelist is None:
        names = _DEFAULT_NAME_WHITELIST
    elif isinstance(name_whitelist, frozenset):
        names = name_whitelist
    else:
        names = frozenset(name_whitelist)

    han_count = _han_char_count(text)
    kchar = max(han_count / 1000.0, 1e-3)

    idiom_hits = _find_idioms(text, idioms)
    quad_hits = _find_quad_phrases(text, idiom_set=idioms, name_whitelist=names)
    chain_hits = _find_abstract_chains(text, abstract)
    c4_mean, c4_max, c4_count = _modifier_chains(text)
    c5_rate, c5_abs, c5_total = _abstract_subject_rate(text, abstract)

    raw_values: dict[str, float] = {
        "C1_idiom_density": len(idiom_hits) / kchar,
        "C2_quad_phrase_density": len(quad_hits) / kchar,
        "C3_abstract_noun_chain": len(chain_hits) / kchar,
        "C4_modifier_chain_avg": c4_mean,
        "C5_abstract_subject_rate": c5_rate,
    }

    dim_scores = tuple(
        score_dimension(key, raw_values[key], resolved_thresholds)
        for key in DIMENSION_KEYS
    )

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

    metrics_raw: dict[str, Any] = {
        "char_count": han_count,
        "kchar": round(kchar, 4),
        "C1_idiom_density": round(raw_values["C1_idiom_density"], 4),
        "C1_idiom_hits_count": len(idiom_hits),
        "C2_quad_phrase_density": round(raw_values["C2_quad_phrase_density"], 4),
        "C2_quad_hits_count": len(quad_hits),
        "C3_abstract_noun_chain": round(raw_values["C3_abstract_noun_chain"], 4),
        "C3_chain_hits_count": len(chain_hits),
        "C4_modifier_chain_avg": round(c4_mean, 4),
        "C4_modifier_chain_max": c4_max,
        "C4_modifier_chain_count": c4_count,
        "C5_abstract_subject_rate": round(c5_rate, 4),
        "C5_abstract_paragraphs": c5_abs,
        "C5_total_paragraphs": c5_total,
    }

    report = ColloquialReport(
        overall_score=overall,
        passed=passed,
        severity=severity,
        dimensions=dim_scores,
        metrics_raw=metrics_raw,
        chain_hits=tuple(chain_hits),
    )
    return report.to_dict()


def to_checker_output(report: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    """把 ``run_colloquial_check`` 输出包成 checker-output-schema.md 标准结构。

    本 module 不直接返回此格式（保持算法层纯净），由 review pipeline 适配层调用。
    severity = red 时 ``pass=False``、``hard_blocked=True`` 给 polish-agent。
    """
    severity = report.get("severity", "green")
    weakest_label = "n/a"
    weakest_score = 10.0
    for dim in report.get("dimensions", ()):
        if dim["score"] < weakest_score:
            weakest_score = dim["score"]
            weakest_label = _DIMENSION_LABELS.get(dim["key"], dim["key"])

    overall_100 = int(round(float(report.get("overall_score", 0.0)) * 10))
    summary = f"{weakest_label} 最低 {weakest_score:.1f} → {severity}"

    return {
        "agent": "colloquial-checker",
        "chapter": chapter_no,
        "overall_score": overall_100,
        "pass": bool(report.get("passed", False)),
        "hard_blocked": severity == "red",
        "issues": [],  # 算法层不生成 issue 文本；polish-agent rewrite mode 拿 dimensions 即可
        "metrics": {
            "severity": severity,
            "dimensions": list(report.get("dimensions", ())),
            "raw": report.get("metrics_raw", {}),
            "chain_hits": list(report.get("chain_hits", ())),
        },
        "summary": summary,
    }


__all__ = [
    "ColloquialReport",
    "DIMENSION_KEYS",
    "DimensionScore",
    "GREEN_SCORE",
    "RED_SCORE",
    "clear_cache",
    "run_colloquial_check",
    "score_dimension",
    "to_checker_output",
]
