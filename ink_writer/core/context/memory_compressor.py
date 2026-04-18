#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Compressor — 跨卷记忆压缩模块

将多章摘要压缩为卷级 mega-summary，释放上下文空间给近期章节。
由 ink-write Step 0 在新卷第1章时自动触发。

用法（通过 ink.py CLI）:
    python ink.py --project-root <path> memory compress-volume --volume <N>
    python ink.py --project-root <path> memory check-compression-needed --chapter <N>
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CHAPTERS_PER_VOLUME = int(os.environ.get("INK_CHAPTERS_PER_VOLUME", "50"))

# US-022: Chapter-level L1 compression defaults.
# L1 compresses N consecutive chapter summaries down to 3-5 bullet lines,
# keeping the runtime context pack small.  L2 remains the volume-level
# mega-summary (LLM-driven or heuristic).
DEFAULT_L1_WINDOW = int(os.environ.get("INK_L1_WINDOW", "8"))
DEFAULT_L1_BULLETS = int(os.environ.get("INK_L1_BULLETS", "3"))


def check_compression_needed(
    project_root: Path,
    current_chapter: int,
    chapters_per_volume: int = DEFAULT_CHAPTERS_PER_VOLUME,
) -> Dict[str, Any]:
    """检查是否需要执行卷级记忆压缩。

    Returns:
        {
            "needed": true/false,
            "volume_to_compress": N or null,
            "reason": "..."
        }
    """
    if current_chapter <= chapters_per_volume:
        return {"needed": False, "volume_to_compress": None, "reason": "尚未超过首卷"}

    summaries_dir = project_root / ".ink" / "summaries"
    if not summaries_dir.exists():
        return {"needed": False, "volume_to_compress": None, "reason": "summaries目录不存在"}

    # 计算应压缩的卷号
    current_volume = (current_chapter - 1) // chapters_per_volume + 1
    target_volume = current_volume - 1  # 压缩上一卷

    if target_volume < 1:
        return {"needed": False, "volume_to_compress": None, "reason": "首卷无需压缩"}

    # 检查是否已有 mega-summary
    mega_file = summaries_dir / f"vol{target_volume}_mega.md"
    if mega_file.exists():
        return {"needed": False, "volume_to_compress": None, "reason": f"vol{target_volume} mega-summary已存在"}

    # 检查是否有足够的章节摘要
    vol_start = (target_volume - 1) * chapters_per_volume + 1
    vol_end = target_volume * chapters_per_volume
    existing_summaries = []
    for ch in range(vol_start, vol_end + 1):
        ch_file = summaries_dir / f"ch{ch:04d}.md"
        if ch_file.exists():
            existing_summaries.append(ch)

    if len(existing_summaries) < 10:
        return {"needed": False, "volume_to_compress": None, "reason": f"vol{target_volume} 摘要不足10章"}

    return {
        "needed": True,
        "volume_to_compress": target_volume,
        "chapter_range": [vol_start, vol_end],
        "available_summaries": len(existing_summaries),
        "reason": f"vol{target_volume} (ch{vol_start}-{vol_end}) 有{len(existing_summaries)}章摘要待压缩",
    }


def load_volume_summaries(
    project_root: Path,
    volume_num: int,
    chapters_per_volume: int = DEFAULT_CHAPTERS_PER_VOLUME,
) -> List[Dict[str, Any]]:
    """加载一个卷的所有章节摘要。"""
    summaries_dir = project_root / ".ink" / "summaries"
    vol_start = (volume_num - 1) * chapters_per_volume + 1
    vol_end = volume_num * chapters_per_volume

    summaries = []
    for ch in range(vol_start, vol_end + 1):
        ch_file = summaries_dir / f"ch{ch:04d}.md"
        if not ch_file.exists():
            continue
        content = ch_file.read_text(encoding="utf-8")

        # 提取 frontmatter 和正文
        frontmatter = {}
        body = content
        fm_match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split('\n'):
                if ':' in line:
                    key, val = line.split(':', 1)
                    frontmatter[key.strip()] = val.strip().strip('"')
            body = fm_match.group(2).strip()

        summaries.append({
            "chapter": ch,
            "frontmatter": frontmatter,
            "body": body,
        })

    return summaries


def build_mega_summary_prompt(
    summaries: List[Dict[str, Any]],
    volume_num: int,
) -> str:
    """构建mega-summary的生成提示词（供LLM使用）。"""
    ch_range = f"ch{summaries[0]['chapter']}-ch{summaries[-1]['chapter']}" if summaries else "unknown"

    prompt = f"""请将以下第{volume_num}卷({ch_range})的{len(summaries)}章摘要压缩为一个500字以内的卷级mega-summary。

必须保留：
1. 本卷2-3个关键剧情转折点
2. 主角和核心角色的状态变化（起始→结束）
3. 本卷新埋设且未解决的伏笔列表
4. 已消亡/退场/新登场的重要角色
5. 本卷结束时的主要悬念/未闭合问题

输出格式：
```markdown
---
volume: {volume_num}
chapters: {ch_range}
compressed_from: {len(summaries)}章
---

## 卷级摘要
[500字以内的核心剧情概要]

## 角色状态变化
| 角色 | 卷初状态 | 卷末状态 |
|------|---------|---------|

## 活跃伏笔
- [伏笔1]
- [伏笔2]

## 卷末悬念
[主要悬念和未闭合问题]
```

以下是各章摘要：

"""
    for s in summaries:
        ch = s["chapter"]
        body = s["body"][:300]  # 截取每章前300字
        prompt += f"\n### 第{ch}章\n{body}\n"

    return prompt


def save_mega_summary(
    project_root: Path,
    volume_num: int,
    content: str,
) -> Path:
    """保存mega-summary到文件。"""
    summaries_dir = project_root / ".ink" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    mega_file = summaries_dir / f"vol{volume_num}_mega.md"
    mega_file.write_text(content, encoding="utf-8")
    return mega_file


# ---------------------------------------------------------------------------
# US-022: L1 chapter-level compression (8 chapter summaries -> 3 bullets).
# ---------------------------------------------------------------------------

_SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?.])\s*")


def _select_salient_sentences(body: str, max_sentences: int = 2) -> List[str]:
    """从一章摘要正文里挑选最显著的 1-2 句。

    启发式：
    - 首句（主题/目标句）
    - 最长句（通常信息密度最高 / 结果或反转）
    - 去重 + trim
    """
    text = re.sub(r"\s+", " ", body or "").strip()
    if not text:
        return []
    # 去掉 markdown heading 与列表符
    text = re.sub(r"^#+\s*", "", text)
    text = text.replace("- ", "")
    sents = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s and s.strip()]
    if not sents:
        return [text[:80]]
    picks: List[str] = []
    picks.append(sents[0])
    if len(sents) > 1:
        longest = max(sents[1:], key=len)
        if longest != picks[0] and len(longest) > 8:
            picks.append(longest)
    # cap each sentence length to keep bullets short
    return [s[:120] for s in picks[:max_sentences]]


def compress_chapter_window(
    project_root: Path,
    end_chapter: int,
    window: int = DEFAULT_L1_WINDOW,
    bullet_target: int = DEFAULT_L1_BULLETS,
    use_llm: Optional[bool] = None,
) -> Dict[str, Any]:
    """将最近 ``window`` 个章节摘要压缩为 ``bullet_target`` 条 bullet。

    默认走纯 Python 启发式（零 LLM 费用）。设置 ``use_llm=True`` 或
    环境变量 ``INK_USE_LLM_COMPRESSOR=1`` 时返回 ``{"prompt": ...}`` 供调用方
    发给 LLM；实际 LLM 调用交给上层（保持本模块零外部依赖）。

    Returns:
        {
            "chapter_range": [start, end],
            "bullets": ["...", "..."],   # 3-5 条
            "source_chapters": [...],
            "mode": "heuristic" | "llm_prompt",
            "prompt": "..."               # 仅 mode=llm_prompt 时存在
        }
    """
    bullet_target = max(3, min(5, int(bullet_target or DEFAULT_L1_BULLETS)))
    start = max(1, end_chapter - window + 1)
    summaries_dir = project_root / ".ink" / "summaries"

    entries: List[Dict[str, Any]] = []
    for ch in range(start, end_chapter + 1):
        ch_file = summaries_dir / f"ch{ch:04d}.md"
        if not ch_file.exists():
            continue
        raw = ch_file.read_text(encoding="utf-8")
        body = raw
        fm_match = re.match(r"^---\n.*?\n---\n(.*)", raw, re.DOTALL)
        if fm_match:
            body = fm_match.group(1).strip()
        entries.append({"chapter": ch, "body": body})

    source_chapters = [e["chapter"] for e in entries]

    env_force_llm = os.environ.get("INK_USE_LLM_COMPRESSOR", "").strip() == "1"
    effective_llm = bool(use_llm) or env_force_llm

    if effective_llm:
        # Build a prompt for caller-side LLM compression.
        lines = [
            f"请将第{start}-{end_chapter}章共{len(entries)}条摘要压缩为{bullet_target}条 bullet，",
            "每条 <=60 字，突出推动剧情的关键事件/角色状态变化/新伏笔。",
            "输出严格为 markdown 列表，每行一条。",
            "",
        ]
        for e in entries:
            lines.append(f"[第{e['chapter']}章] {e['body'][:240]}")
        return {
            "chapter_range": [start, end_chapter],
            "bullets": [],
            "source_chapters": source_chapters,
            "mode": "llm_prompt",
            "prompt": "\n".join(lines),
        }

    # Heuristic bullet synthesis.
    bullets: List[str] = []
    if not entries:
        return {
            "chapter_range": [start, end_chapter],
            "bullets": [],
            "source_chapters": [],
            "mode": "heuristic",
        }

    # Strategy: evenly sample the window and extract a salient line per sample.
    step = max(1, len(entries) // bullet_target)
    sampled: List[Dict[str, Any]] = []
    for i in range(0, len(entries), step):
        sampled.append(entries[i])
        if len(sampled) >= bullet_target:
            break
    # ensure we always include the last chapter (most recent bridge).
    if entries[-1] not in sampled:
        if len(sampled) >= bullet_target:
            sampled[-1] = entries[-1]
        else:
            sampled.append(entries[-1])

    for entry in sampled[:bullet_target]:
        sents = _select_salient_sentences(entry["body"], max_sentences=1)
        text = sents[0] if sents else entry["body"][:60]
        bullets.append(f"第{entry['chapter']}章：{text}")

    return {
        "chapter_range": [start, end_chapter],
        "bullets": bullets,
        "source_chapters": source_chapters,
        "mode": "heuristic",
    }


def save_l1_summary(
    project_root: Path,
    end_chapter: int,
    result: Dict[str, Any],
) -> Path:
    """保存 L1 压缩结果到 ``.ink/summaries/l1_chXXXX.json``。"""
    summaries_dir = project_root / ".ink" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    out = summaries_dir / f"l1_ch{end_chapter:04d}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
