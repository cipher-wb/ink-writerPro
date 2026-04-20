#!/usr/bin/env python3
"""analyze_prose_directness.py — 直白密度 5 维度基线扫描脚本（US-001）

扫描 benchmark 起点实书语料，按章节输出 5 维度直白密度指标，供 US-002 汇总成
阈值报告，US-005 directness-checker 据此判定 Green/Yellow/Red。

五维度：
  D1 rhetoric_density  —— （比喻 + 排比）/ 总句数
  D2 adj_verb_ratio    —— 形容词 / 动词（jieba.posseg）
  D3 abstract_density  —— 抽象词命中次数 / 每 100 字
  D4 sent_len_median   —— 句长中位数（jieba 词数）
  D5 empty_paragraphs  —— 无对话、无人物动作的纯描写段落数

场景分类：golden_three（第 1-3 章） > combat（标题含战斗关键词或动词密度高） > other。

用法::

    python scripts/analyze_prose_directness.py \\
        --corpus benchmark/reference_corpus \\
        --output reports/prose-directness-stats.json

注：抽象词表使用内置种子列表；US-003 产出 ``ink-writer/assets/prose-blacklist.yaml``
后，可用 ``--blacklist`` 指向 YAML 覆盖种子列表。
"""
from __future__ import annotations

import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio  # type: ignore[import-not-found]

    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
from collections.abc import Iterable, Sequence  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

# 种子抽象词表（US-003 `prose-blacklist.yaml` 上线后会扩展至 ≥50 条）。保持与
# 通用套话口吻一致，覆盖网文常见"说了等于没说"的虚词。
_ABSTRACT_SEED: tuple[str, ...] = (
    "莫名", "无尽", "难以言喻", "仿佛", "似乎", "似有若无", "若有若无",
    "恍惚", "恍若", "宛如", "犹如", "隐隐", "淡淡", "微微", "仿若",
    "隐约", "朦胧", "迷离", "空灵", "虚无", "缥缈", "飘渺", "浩渺",
    "深邃", "莫测", "不可名状", "难以名状", "不可思议", "难以形容",
    "某种", "不知为何", "不知不觉", "鬼使神差",
)

# 标题含这些关键词时判定为战斗场景（第 1-3 章除外——那几章优先走 golden_three）。
_COMBAT_TITLE_KEYWORDS: tuple[str, ...] = ("战", "斗", "杀", "剑", "拳", "刀", "搏", "斩", "决")

# 比喻连词 / 标记词；避免用单字"如""像"——单字误报率高。
_SIMILE_MARKERS: tuple[str, ...] = (
    "如同", "好像", "仿佛", "宛如", "犹如", "恍若", "仿若", "像是", "似的", "一般",
    "好似", "酷似",
)

# 句子切分：常见中文句末标点。
_SENT_SPLIT_RE = re.compile(r"[。！？!?；;…]+")

# 段落切分：连续空行或换行即分段。
_PARA_SPLIT_RE = re.compile(r"\n+")

# 对话标记：中英文引号。显式 unicode 转义避免编辑器/源码层面把弯引号折叠成直引号。
_DIALOGUE_MARKERS: tuple[str, ...] = (
    '"',  # U+0022
    "'",  # U+0027
    "\u201c",  # "
    "\u201d",  # "
    "\u2018",  # '
    "\u2019",  # '
    "\u300c",  # 「
    "\u300d",  # 」
    "\u300e",  # 『
    "\u300f",  # 』
)

# 辅助动词/系动词：不计入 D5 "人物动作" 检测。
_AUX_VERBS: frozenset[str] = frozenset(
    {"是", "有", "能", "会", "可以", "要", "想", "为", "乃", "成", "变", "变成", "成为"}
)

# 人称代词：出现代词通常意味着段落在描述人物而非纯境。
_PERSON_PRONOUNS: tuple[str, ...] = ("他", "她", "它", "我", "你", "咱", "您")


def _lazy_jieba() -> Any:
    """延迟导入 jieba。首次加载 ~200ms，避免测试收集期额外开销。"""
    import jieba.posseg as pseg  # noqa: PLC0415

    return pseg


def split_sentences(text: str) -> list[str]:
    """按中文句末标点切分句子；空串过滤。"""
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def split_paragraphs(text: str) -> list[str]:
    """按空行切分段落。兼顾网文常见首行缩进的"　　"全角空格。"""
    paragraphs: list[str] = []
    for block in _PARA_SPLIT_RE.split(text):
        stripped = block.strip().lstrip("\u3000").strip()
        if stripped:
            paragraphs.append(stripped)
    return paragraphs


def has_simile(sentence: str) -> bool:
    """句子是否包含明喻标记。保守判定：必须命中多字标记词之一。"""
    return any(marker in sentence for marker in _SIMILE_MARKERS)


def has_parallelism(sentence: str) -> bool:
    """排比启发式：3+ 个以相同首字开头的逗号/顿号分隔子句。

    真实的排比检测需语法分析，此处用最保守的"首字重复"规则，能 cover 多数明显
    的三段排比（"他是…他是…他是…"），漏报优先于误报。
    """
    segments = [seg.strip() for seg in re.split(r"[，、]", sentence) if seg.strip()]
    if len(segments) < 3:
        return False
    first_chars = [seg[0] for seg in segments[:3]]
    return len(set(first_chars)) == 1


def has_rhetoric(sentence: str) -> bool:
    """D1 判定：句子是否含比喻或排比。"""
    return has_simile(sentence) or has_parallelism(sentence)


def count_abstract_hits(text: str, abstract_words: Sequence[str]) -> int:
    """统计抽象词命中次数（重复计数）。"""
    return sum(text.count(word) for word in abstract_words)


def _count_pos(
    text: str,
    *,
    pseg: Any | None = None,
) -> tuple[int, int, int]:
    """返回 (adj_count, verb_count, content_verb_count)。

    content_verb_count 剔除辅助/系动词，用于 D5 判定段落是否有人物动作。
    """
    if pseg is None:
        pseg = _lazy_jieba()
    adj = verb = content_verb = 0
    for word, pos in pseg.cut(text):
        if pos.startswith("a"):
            adj += 1
        elif pos.startswith("v"):
            verb += 1
            if word not in _AUX_VERBS:
                content_verb += 1
    return adj, verb, content_verb


def _sent_word_lengths(sentences: Iterable[str], *, jieba_mod: Any | None = None) -> list[int]:
    if jieba_mod is None:
        import jieba as jieba_mod  # type: ignore[no-redef]  # noqa: PLC0415
    return [len(list(jieba_mod.cut(s))) for s in sentences]


def is_empty_description(paragraph: str, *, pseg: Any | None = None) -> bool:
    """D5 判定：段落是否为无对话、无人物动作的纯描写段。

    启发式（pseg 入参保留以便未来细化）：
      1. 不含对话标记（中英文引号等）；
      2. 不含人称代词——无"他/她/我/你/咱"之类的主体代词，任何动词都归为
         环境/意境描写。
    """
    del pseg  # 目前未使用，保留签名以便后续细化
    text = paragraph.strip()
    if not text:
        return False
    if any(marker in text for marker in _DIALOGUE_MARKERS):
        return False
    return not any(pronoun in text for pronoun in _PERSON_PRONOUNS)


def compute_metrics(
    text: str,
    *,
    abstract_words: Sequence[str] = _ABSTRACT_SEED,
    pseg: Any | None = None,
    jieba_mod: Any | None = None,
) -> dict[str, float | int]:
    """计算单篇文本的 5 维度指标。"""
    if pseg is None:
        pseg = _lazy_jieba()
    if jieba_mod is None:
        import jieba as jieba_mod  # type: ignore[no-redef]  # noqa: PLC0415

    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)
    total_sentences = len(sentences) or 1
    char_len = len(text) or 1

    rhetoric_hits = sum(1 for s in sentences if has_rhetoric(s))
    adj, verb, _ = _count_pos(text, pseg=pseg)
    abstract_hits = count_abstract_hits(text, abstract_words)

    sent_word_lens = _sent_word_lengths(sentences, jieba_mod=jieba_mod) if sentences else []
    sent_len_median = float(statistics.median(sent_word_lens)) if sent_word_lens else 0.0

    empty_paras = sum(1 for p in paragraphs if is_empty_description(p, pseg=pseg))

    adj_verb_ratio = adj / verb if verb else float(adj)

    return {
        "char_count": len(text),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "D1_rhetoric_density": round(rhetoric_hits / total_sentences, 4),
        "D2_adj_verb_ratio": round(adj_verb_ratio, 4),
        "D3_abstract_per_100_chars": round(abstract_hits * 100 / char_len, 4),
        "D4_sent_len_median": round(sent_len_median, 2),
        "D5_empty_paragraphs": empty_paras,
        "_raw": {
            "rhetoric_hits": rhetoric_hits,
            "adj_count": adj,
            "verb_count": verb,
            "abstract_hits": abstract_hits,
        },
    }


def classify_scene(
    chapter_num: int,
    title: str,
    text: str,
    *,
    pseg: Any | None = None,
    verb_density_threshold: float = 0.18,
    sample_chars: int = 2000,
) -> str:
    """场景分类：golden_three > combat > other。

    golden_three 只认章节号（1-3）。combat 用标题关键词做主判据，辅以前 2000 字
    的实义动词密度超阈值作为 fallback（真实战斗段动词会比对话多）。
    """
    if 1 <= chapter_num <= 3:
        return "golden_three"
    if any(kw in title for kw in _COMBAT_TITLE_KEYWORDS):
        return "combat"
    sample = text[:sample_chars]
    if not sample:
        return "other"
    _adj, _verb, content_verb = _count_pos(sample, pseg=pseg)
    density = content_verb / max(len(sample), 1)
    if density >= verb_density_threshold:
        return "combat"
    return "other"


def _iter_chapter_files(
    corpus: Path,
    *,
    max_chapters: int,
    max_books: int | None,
) -> list[tuple[str, int, Path]]:
    """遍历 ``corpus/*/chapters/ch###.txt``，返回 (book, chapter_num, path)。"""
    entries: list[tuple[str, int, Path]] = []
    books = sorted(d for d in corpus.iterdir() if d.is_dir())
    if max_books is not None:
        books = books[:max_books]
    for book_dir in books:
        chapters_dir = book_dir / "chapters"
        if not chapters_dir.is_dir():
            continue
        files = sorted(chapters_dir.glob("ch*.txt"))[:max_chapters]
        for path in files:
            m = re.match(r"ch(\d+)", path.stem)
            if not m:
                continue
            entries.append((book_dir.name, int(m.group(1)), path))
    return entries


def run_analysis(
    corpus: Path,
    output: Path,
    *,
    max_chapters: int = 30,
    max_books: int | None = None,
    abstract_words: Sequence[str] = _ABSTRACT_SEED,
) -> list[dict[str, Any]]:
    """扫描语料并输出 JSONL 到 output。返回全部记录（便于测试断言）。"""
    pseg = _lazy_jieba()
    import jieba as jieba_mod  # noqa: PLC0415

    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    entries = _iter_chapter_files(corpus, max_chapters=max_chapters, max_books=max_books)
    for book, chapter_num, path in entries:
        text = path.read_text(encoding="utf-8")
        metrics = compute_metrics(
            text,
            abstract_words=abstract_words,
            pseg=pseg,
            jieba_mod=jieba_mod,
        )
        scene = classify_scene(chapter_num, path.stem, text, pseg=pseg)
        records.append(
            {
                "book": book,
                "chapter": chapter_num,
                "file": str(path.relative_to(corpus.parent)) if path.is_relative_to(corpus.parent) else str(path),
                "scene": scene,
                "metrics": metrics,
            }
        )

    with output.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=Path("benchmark/reference_corpus"))
    parser.add_argument("--output", type=Path, default=Path("reports/prose-directness-stats.json"))
    parser.add_argument("--max-chapters", type=int, default=30)
    parser.add_argument("--max-books", type=int, default=None, help="调试用：仅扫前 N 本")
    parser.add_argument(
        "--blacklist",
        type=Path,
        default=None,
        help="可选：prose-blacklist.yaml（US-003 产出），覆盖种子抽象词表",
    )
    return parser


def _load_blacklist(path: Path) -> Sequence[str]:
    """加载 US-003 的 YAML 黑名单，返回抽象词列表（abstract_adjectives 域）。"""
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - 生产环境 requirements 里有 PyYAML
        raise RuntimeError("需要 PyYAML 才能加载 --blacklist") from exc
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries = data.get("abstract_adjectives") or []
    words: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            words.append(entry)
        elif isinstance(entry, dict) and "word" in entry:
            words.append(str(entry["word"]))
    return tuple(words) or _ABSTRACT_SEED


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    abstract = _ABSTRACT_SEED
    if args.blacklist and args.blacklist.exists():
        abstract = _load_blacklist(args.blacklist)
    records = run_analysis(
        args.corpus,
        args.output,
        max_chapters=args.max_chapters,
        max_books=args.max_books,
        abstract_words=abstract,
    )
    print(f"analyze_prose_directness: wrote {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
