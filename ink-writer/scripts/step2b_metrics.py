#!/usr/bin/env python3
"""Step 2B 风格适配前置指标计算 (US-004)

在 Step 2B 执行前快速统计正文的句长均值和对话占比，
决定是否进入"定向检查模式"（仅处理3项残留职责）。

达标条件：句长均值 > 20字 且 对话占比 > 10%
  → 进入定向检查模式（拆超长句 + 删总结式旁白 + 清模板腔）
  → 否则执行原有全量风格适配

用法:
    python3 step2b_metrics.py --chapter-file <path>
    python3 step2b_metrics.py --text "正文内容"

输出:
    JSON: {avg_sentence_length, dialogue_ratio, targeted_mode, long_sentences, summary_phrases}
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '.',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 句长计算
# ---------------------------------------------------------------------------

# 按中文句末标点分句（。？！?!）
_SENTENCE_SPLIT = re.compile(r'[。？！?!]+')

# 对话标记：「」
_DIALOGUE_PATTERN = re.compile(r'「[^」]*」')

# 超长句阈值
_LONG_SENTENCE_THRESHOLD = 55


def _split_sentences(text: str) -> list[str]:
    """按句号/问号/感叹号分句，过滤空句。"""
    raw = _SENTENCE_SPLIT.split(text)
    return [s.strip() for s in raw if s.strip()]


def calc_avg_sentence_length(text: str) -> float:
    """计算句长均值（按字符数，含标点）。"""
    sentences = _split_sentences(text)
    if not sentences:
        return 0.0
    return sum(len(s) for s in sentences) / len(sentences)


# ---------------------------------------------------------------------------
# 对话占比
# ---------------------------------------------------------------------------

def calc_dialogue_ratio(text: str) -> float:
    """计算对话占比 = 「」内文字字数 / 总字数。"""
    total = len(text.replace('\n', '').replace(' ', ''))
    if total == 0:
        return 0.0
    dialogue_chars = sum(
        len(m.group()[1:-1])  # 去掉「」本身
        for m in _DIALOGUE_PATTERN.finditer(text)
    )
    return dialogue_chars / total


# ---------------------------------------------------------------------------
# 超长句检测
# ---------------------------------------------------------------------------

def find_long_sentences(text: str, threshold: int = _LONG_SENTENCE_THRESHOLD) -> list[dict]:
    """找出超过阈值的非对话句。"""
    # 先移除对话内容再分句
    text_no_dialogue = _DIALOGUE_PATTERN.sub('', text)
    sentences = _split_sentences(text_no_dialogue)
    results = []
    for s in sentences:
        if len(s) > threshold:
            results.append({
                "length": len(s),
                "preview": s[:60] + ("..." if len(s) > 60 else ""),
            })
    return results


# ---------------------------------------------------------------------------
# 总结式旁白检测
# ---------------------------------------------------------------------------

# AI痕迹短语（总结式旁白）
_SUMMARY_PHRASES = [
    "由此可见", "换句话说", "总而言之", "可以说",
    "不得不说", "事实上", "毫无疑问", "众所周知",
    "不言而喻", "归根结底", "简而言之",
]

_SUMMARY_PATTERN = re.compile('|'.join(re.escape(p) for p in _SUMMARY_PHRASES))


def find_summary_phrases(text: str) -> list[dict]:
    """检测总结式旁白短语。"""
    results = []
    for m in _SUMMARY_PATTERN.finditer(text):
        # 获取所在行号（近似）
        line_num = text[:m.start()].count('\n') + 1
        results.append({
            "phrase": m.group(),
            "line": line_num,
            "context": text[max(0, m.start() - 10):m.end() + 10],
        })
    return results


# ---------------------------------------------------------------------------
# 综合评估
# ---------------------------------------------------------------------------

def evaluate(text: str) -> dict:
    """计算所有指标并判断是否进入定向检查模式。"""
    avg_len = calc_avg_sentence_length(text)
    dial_ratio = calc_dialogue_ratio(text)
    targeted = avg_len > 20 and dial_ratio > 0.10
    long_sents = find_long_sentences(text)
    summary = find_summary_phrases(text)

    return {
        "avg_sentence_length": round(avg_len, 1),
        "dialogue_ratio": round(dial_ratio, 4),
        "dialogue_ratio_pct": f"{dial_ratio * 100:.1f}%",
        "targeted_mode": targeted,
        "mode": "targeted" if targeted else "full",
        "long_sentences_count": len(long_sents),
        "long_sentences": long_sents,
        "summary_phrases_count": len(summary),
        "summary_phrases": summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 2B 前置指标计算：句长均值 + 对话占比"
    )
    parser.add_argument("--chapter-file", type=str, help="章节文件路径")
    parser.add_argument("--text", type=str, help="直接传入正文文本")
    args = parser.parse_args()

    if args.chapter_file:
        text = Path(args.chapter_file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        parser.error("必须提供 --chapter-file 或 --text")
        return

    result = evaluate(text)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
