#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Style Anchor - 风格锚定模块

在前10章写完后计算聚合风格指纹，存储为 .ink/style_anchor.json。
后续每100章可对比当前风格与锚点，检测漂移。

依赖: style_sampler.py 的特征提取基础设施。
"""

import json
import re
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

from ink_writer.core.infra.config import get_config


def _extract_text_features(text: str) -> Dict[str, float]:
    """从文本中提取风格特征（与 style_sampler 的特征提取逻辑一致）"""
    compact = re.sub(r"\s+", "", text)
    total_chars = max(1, len(compact))

    # 句长统计
    sentences = re.split(r"[。！？…]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_lengths = [len(re.sub(r"\s+", "", s)) for s in sentences]
    avg_sentence_length = (
        round(sum(sentence_lengths) / len(sentence_lengths), 2)
        if sentence_lengths
        else 0.0
    )

    # 短句占比 (≤8字)
    short_count = sum(1 for sl in sentence_lengths if sl <= 8)
    short_sentence_ratio = (
        round(short_count / len(sentence_lengths), 4)
        if sentence_lengths
        else 0.0
    )

    # 对话占比
    dialogue_chars = sum(
        len(m.group(0))
        for m in re.finditer(r'[\u201c\u201d"](.*?)[\u201c\u201d"]', text, re.DOTALL)
    )
    dialogue_ratio = round(dialogue_chars / total_chars, 4)

    # 段落平均长度
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    para_lengths = [len(re.sub(r"\s+", "", p)) for p in paragraphs]
    avg_paragraph_length = (
        round(sum(para_lengths) / len(para_lengths), 2)
        if para_lengths
        else 0.0
    )

    # 感叹号密度 (per 1000 chars)
    exclamation_count = text.count("！") + text.count("!")
    exclamation_density = round(exclamation_count / (total_chars / 1000), 4)

    return {
        "avg_sentence_length": avg_sentence_length,
        "short_sentence_ratio": short_sentence_ratio,
        "dialogue_ratio": dialogue_ratio,
        "avg_paragraph_length": avg_paragraph_length,
        "exclamation_density": exclamation_density,
    }


def compute_anchor(project_root: str, chapters: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    计算风格锚点。默认使用前10章的正文。

    返回聚合指纹 dict，包含每个指标的均值和标准差。
    """
    root = Path(project_root)
    text_dir = root / "正文"

    if chapters is None:
        chapters = list(range(1, 11))

    all_features: List[Dict[str, float]] = []
    for ch in chapters:
        padded = f"{ch:04d}"
        # 尝试带标题和不带标题的文件名
        candidates = list(text_dir.glob(f"第{padded}章*.md"))
        if not candidates:
            continue
        text = candidates[0].read_text(encoding="utf-8")
        if len(text.strip()) < 200:
            continue
        features = _extract_text_features(text)
        all_features.append(features)

    if len(all_features) < 3:
        return {"error": "章节数据不足（需至少3章有效正文）", "chapters_found": len(all_features)}

    # 聚合：每个指标的均值和标准差
    keys = all_features[0].keys()
    anchor: Dict[str, Any] = {
        "version": 1,
        "chapters_used": len(all_features),
        "chapter_range": [min(chapters), max(chapters)],
        "metrics": {},
    }
    for key in keys:
        values = [f[key] for f in all_features]
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        anchor["metrics"][key] = {
            "mean": round(mean, 4),
            "stdev": round(stdev, 4),
        }

    return anchor


def save_anchor(project_root: str, anchor: Optional[Dict[str, Any]] = None) -> str:
    """计算并保存风格锚点到 .ink/style_anchor.json"""
    if anchor is None:
        anchor = compute_anchor(project_root)

    if "error" in anchor:
        return anchor["error"]

    path = Path(project_root) / ".ink" / "style_anchor.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(anchor, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"风格锚点已保存: {path} (基于{anchor['chapters_used']}章)"


def check_drift(project_root: str, recent_chapters: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    对比当前风格与锚点，检测漂移。

    recent_chapters: 最近要检查的章节列表。默认取最近10章。
    返回漂移报告。
    """
    root = Path(project_root)
    anchor_path = root / ".ink" / "style_anchor.json"

    if not anchor_path.exists():
        return {"status": "skip", "reason": "风格锚点不存在，跳过漂移检测"}

    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    anchor_metrics = anchor.get("metrics", {})

    if not anchor_metrics:
        return {"status": "skip", "reason": "风格锚点数据为空"}

    # 确定最近章节范围
    if recent_chapters is None:
        text_dir = root / "正文"
        all_chapters = sorted(
            int(m.group(1))
            for f in text_dir.glob("第*章*.md")
            if (m := re.match(r"第(\d+)章", f.name))
        )
        if len(all_chapters) < 15:
            return {"status": "skip", "reason": f"总章节数不足15章（当前{len(all_chapters)}章），跳过漂移检测"}
        recent_chapters = all_chapters[-10:]

    current = compute_anchor(project_root, chapters=recent_chapters)
    if "error" in current:
        return {"status": "skip", "reason": current["error"]}

    current_metrics = current.get("metrics", {})

    # 比对
    drift_warnings: List[Dict[str, Any]] = []
    for key, anchor_data in anchor_metrics.items():
        if key not in current_metrics:
            continue
        anchor_mean = anchor_data["mean"]
        anchor_stdev = max(anchor_data["stdev"], 0.01)  # 避免除以0
        current_mean = current_metrics[key]["mean"]

        # Z-score: 偏离几个标准差
        z_score = abs(current_mean - anchor_mean) / anchor_stdev
        deviation_pct = (
            abs(current_mean - anchor_mean) / max(anchor_mean, 0.01) * 100
        )

        if z_score > 2.0:
            drift_warnings.append({
                "metric": key,
                "anchor_mean": anchor_mean,
                "current_mean": round(current_mean, 4),
                "z_score": round(z_score, 2),
                "deviation_pct": round(deviation_pct, 1),
                "severity": "high" if z_score > 3.0 else "medium",
            })

    return {
        "status": "checked",
        "anchor_chapters": anchor.get("chapter_range", []),
        "current_chapters": [min(recent_chapters), max(recent_chapters)],
        "drift_count": len(drift_warnings),
        "warnings": drift_warnings,
    }
