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
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def check_compression_needed(
    project_root: Path,
    current_chapter: int,
    chapters_per_volume: int = 50,
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
    chapters_per_volume: int = 50,
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
