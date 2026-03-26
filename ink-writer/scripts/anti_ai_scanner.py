#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anti-AI 自动扫描工具 - 检测文本中的AI写作痕迹

纯规则引擎实现，不依赖外部 LLM。实现 polish-guide.md 中定义的 7 层检查的自动化。

7 个检测维度：
  L1 高风险词汇检测
  L2 句式模式检测
  L3 形容词副词密度
  L4 四字套语密度
  L5 对话质量检测
  L6 段落结构分析
  L7 标点节奏

使用方法：
  python anti_ai_scanner.py --file <path>
  python anti_ai_scanner.py --project-root <path> --chapter <num>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import Counter

from runtime_compat import enable_windows_utf8_stdio, normalize_windows_path

# Windows UTF-8 输出修复
if sys.platform == "win32":
    enable_windows_utf8_stdio()


# ============================================================================
# 常量定义
# ============================================================================

HIGH_RISK_WORDS: Dict[str, List[str]] = {
    "总结词": [
        "综合", "总之", "总的来说", "总而言之", "由此可见",
        "不难看出", "显而易见", "毫无疑问", "毋庸置疑",
    ],
    "枚举词": [
        "首先", "其次", "最后", "第一", "第二", "第三",
        r"一方面.*另一方面",
    ],
    "学术腔": [
        "某种程度上", r"从.*角度来看", "值得注意的是",
        "不可否认", "客观来说", r"就.*而言",
    ],
    "逻辑连接": ["因此", "所以", "然而", "不过", "尽管如此", "与此同时"],
    "情绪直述": [
        "非常愤怒", "十分高兴", "无比悲伤", "极其紧张",
        "异常兴奋", r"格外.*感动",
    ],
    "动作套话": [
        "皱起眉头", "嘴角上扬", "目光深邃", "眼神坚定",
        "嘴角勾起一抹", "不由自主地",
    ],
    "环境套话": [
        "空气仿佛凝固", r"气氛.*微妙", "阳光透过", "微风拂过", "月光如水",
    ],
    "叙事填充": ["似乎", "仿佛", "好像", "宛如", "犹如", "不禁", "忍不住"],
    "抽象空泛": ["展现出", "呈现", "蕴含着", "折射出", "体现为", "彰显"],
    "机械收尾": [
        "一切才刚刚开始", "故事远没有结束",
        r"命运的齿轮.*转动", r"新的篇章.*开启",
    ],
}

# L3: 程度副词
DEGREE_ADVERBS = ["很", "非常", "十分", "极其", "异常", "格外", "无比"]

# L5: 空洞对话关键词
HOLLOW_DIALOGUE_WORDS = ["你好", "嗯", "是的", "好的", "哦", "啊", "对", "嗯嗯", "好吧"]

# 权重配置：每层的满分
LAYER_MAX_SCORES: Dict[str, int] = {
    "L1_high_risk_words": 25,
    "L2_sentence_pattern": 15,
    "L3_adjective_density": 10,
    "L4_idiom_density": 10,
    "L5_dialogue_quality": 15,
    "L6_paragraph_structure": 15,
    "L7_punctuation_rhythm": 10,
}

# 改写建议映射
CATEGORY_SUGGESTIONS: Dict[str, str] = {
    "总结词": "删除总结词，让读者自行体会",
    "枚举词": "打散为动作/对话/心理的混排",
    "学术腔": "换成角色内心独白或口语化表达",
    "逻辑连接": "用动作或场景转换替代逻辑连接词",
    "情绪直述": "改为具体的身体反应或行为描写",
    "动作套话": "替换为角色专属的习惯性小动作",
    "环境套话": "改为具体的物理感受，融入角色的五感",
    "叙事填充": "确认是否必要，删除或替换为更精确的描述",
    "抽象空泛": "用具体事例或画面替代抽象概括",
    "机械收尾": "用具体悬念或角色行动替代空泛收尾",
    "三段式": "打散为动作/对话/心理的混排",
    "同构句": "变换句式长短，穿插对话或心理活动",
    "清单化叙事": "改为正常叙事段落，融入场景描写",
    "程度副词过多": "删除多余副词，用具体描写替代",
    "双形容词修饰": "保留最精准的一个形容词",
    "四字词堆叠": "拆散四字词，用口语化表述替代部分",
    "空洞对话": "让对话携带信息：推进剧情、暴露性格或制造冲突",
    "说明书式对话": "将背景信息拆分到叙事段落，对话只保留关键语句",
    "单句成段过多": "合并部分短段，形成节奏起伏",
    "单句成段过少": "适当拆分长段，增加阅读节奏",
    "段落偏长": "拆分为 2-3 个短段，在动作/情绪转折处断开",
    "段落偏短": "合并相关短段，增强叙事连贯性",
    "过长段落": "在动作或情绪转折处拆段，每段不超过 200 字",
    "连续省略号": "减少省略号使用，用短句或沉默动作替代",
    "连续感叹号": "控制感叹号频率，用动作表现激动情绪",
    "逗号过多长句": "在逻辑断点处用句号断句",
}


# ============================================================================
# AntiAIScanner
# ============================================================================

class AntiAIScanner:
    """Anti-AI 扫描器：对文本执行 7 层规则检测，输出风险评分和改写建议。"""

    def __init__(self, text: str, filename: str = "", custom_wordlist: str = None):
        self.text = text
        self.filename = filename
        self.lines = text.splitlines()
        self.total_chars = len(re.sub(r"\s+", "", text))
        self.high_risk_segments: List[Dict[str, Any]] = []
        self._high_risk_words = dict(HIGH_RISK_WORDS)  # 复制默认词库
        if custom_wordlist:
            self._load_custom_wordlist(custom_wordlist)

    def _load_custom_wordlist(self, path: str) -> None:
        """从外部JSON文件加载自定义词库，合并到默认词库中。"""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for category, words in data.items():
                if category in self._high_risk_words:
                    # 合并，去重
                    existing = set(self._high_risk_words[category])
                    existing.update(words)
                    self._high_risk_words[category] = list(existing)
                else:
                    self._high_risk_words[category] = words
        except (json.JSONDecodeError, OSError) as e:
            print(f"\u26a0\ufe0f 加载自定义词库失败: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _add_segment(
        self,
        line: int,
        text: str,
        layer: str,
        category: str,
        suggestion: str = "",
    ) -> None:
        if not suggestion:
            suggestion = CATEGORY_SUGGESTIONS.get(category, "")
        self.high_risk_segments.append({
            "line": line,
            "text": text[:80],
            "layer": layer,
            "category": category,
            "suggestion": suggestion,
        })

    def _line_number_of(self, pos: int) -> int:
        """将字符偏移量转换为行号（1-based）。"""
        return self.text[:pos].count("\n") + 1

    # ------------------------------------------------------------------
    # L1: 高风险词汇检测
    # ------------------------------------------------------------------

    def scan_layer1_high_risk_words(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        total_hits = 0

        for category, patterns in self._high_risk_words.items():
            for pattern in patterns:
                for m in re.finditer(pattern, self.text):
                    line_num = self._line_number_of(m.start())
                    matched_text = m.group()
                    details.append({
                        "word": matched_text,
                        "category": category,
                        "line": line_num,
                    })
                    self._add_segment(line_num, matched_text, "L1", category)
                    total_hits += 1

        # 评分：每命中 1 个扣 2 分，上限 25
        max_score = LAYER_MAX_SCORES["L1_high_risk_words"]
        score = min(total_hits * 2, max_score)

        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # L2: 句式模式检测
    # ------------------------------------------------------------------

    def scan_layer2_sentence_pattern(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        issues = 0

        # (a) 检测"首先…其次…最后"三段式（同一段内出现）
        paragraphs = self.text.split("\n\n")
        char_offset = 0
        for para in paragraphs:
            if "首先" in para and "其次" in para and "最后" in para:
                line_num = self._line_number_of(char_offset)
                details.append({"type": "三段式", "line": line_num})
                self._add_segment(line_num, para[:60], "L2", "三段式")
                issues += 1
            char_offset += len(para) + 2  # +2 for \n\n

        # (b) 检测连续 3+ 个同构句（句长相近 + 首字相同）
        sentences = re.split(r"[。！？]", self.text)
        sentences = [s.strip() for s in sentences if s.strip()]
        for i in range(len(sentences) - 2):
            trio = sentences[i : i + 3]
            lengths = [len(s) for s in trio]
            # 句长相近：最大最小差不超过 5
            if max(lengths) - min(lengths) <= 5 and all(len(s) > 3 for s in trio):
                first_chars = [s[0] for s in trio]
                if len(set(first_chars)) == 1:
                    # 找到对应行号
                    pos = self.text.find(trio[0])
                    line_num = self._line_number_of(pos) if pos >= 0 else 0
                    details.append({
                        "type": "同构句",
                        "line": line_num,
                        "sentences": [s[:30] for s in trio],
                    })
                    self._add_segment(line_num, "；".join(s[:20] for s in trio), "L2", "同构句")
                    issues += 1

        # (c) 检测清单化叙事（连续的 · 或 - 开头行）
        consecutive_list = 0
        list_start_line = 0
        for idx, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if stripped and (stripped.startswith("·") or stripped.startswith("-") or stripped.startswith("•")):
                if consecutive_list == 0:
                    list_start_line = idx
                consecutive_list += 1
            else:
                if consecutive_list >= 3:
                    details.append({"type": "清单化叙事", "line": list_start_line, "count": consecutive_list})
                    self._add_segment(list_start_line, f"连续 {consecutive_list} 行清单格式", "L2", "清单化叙事")
                    issues += 1
                consecutive_list = 0
        if consecutive_list >= 3:
            details.append({"type": "清单化叙事", "line": list_start_line, "count": consecutive_list})
            self._add_segment(list_start_line, f"连续 {consecutive_list} 行清单格式", "L2", "清单化叙事")
            issues += 1

        max_score = LAYER_MAX_SCORES["L2_sentence_pattern"]
        score = min(issues * 5, max_score)
        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # L3: 形容词副词密度
    # ------------------------------------------------------------------

    def scan_layer3_adjective_density(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []

        # (a) 程度副词频率
        adverb_count = 0
        for adv in DEGREE_ADVERBS:
            for m in re.finditer(re.escape(adv), self.text):
                adverb_count += 1

        threshold = max(1, self.total_chars // 300) * 4  # 每 300 字不超过 4 个
        adverb_over = max(0, adverb_count - threshold)
        if adverb_over > 0:
            details.append({
                "type": "程度副词过多",
                "count": adverb_count,
                "threshold": threshold,
            })
            self._add_segment(
                0, f"程度副词 {adverb_count} 个（阈值 {threshold}）",
                "L3", "程度副词过多",
            )

        # (b) 连续两个形容词修饰同一名词（简化：检测 "XX的XX的" 模式）
        double_adj_pattern = re.compile(
            r"[\u4e00-\u9fff]{1,4}的[\u4e00-\u9fff]{1,4}的[\u4e00-\u9fff]{1,4}"
        )
        double_adj_hits = 0
        for m in double_adj_pattern.finditer(self.text):
            line_num = self._line_number_of(m.start())
            details.append({"type": "双形容词修饰", "line": line_num, "text": m.group()})
            self._add_segment(line_num, m.group(), "L3", "双形容词修饰")
            double_adj_hits += 1

        max_score = LAYER_MAX_SCORES["L3_adjective_density"]
        score = min(adverb_over * 2 + double_adj_hits * 2, max_score)
        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # L4: 四字套语密度
    # ------------------------------------------------------------------

    def scan_layer4_idiom_density(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []

        # 提取所有四字中文词
        four_char_pattern = re.compile(r"[\u4e00-\u9fff]{4}")
        matches = list(four_char_pattern.finditer(self.text))

        threshold = max(1, self.total_chars // 500) * 3  # 每 500 字不超过 3 个

        # 检测四字词连续堆叠（如"风和日丽，鸟语花香，万里无云"）
        stack_count = 0
        stack_issues = 0
        prev_end = -1
        stack_start_line = 0
        stack_words: List[str] = []

        for m in matches:
            # 允许中间有标点（逗号、顿号）
            gap = self.text[prev_end:m.start()] if prev_end >= 0 else ""
            gap_clean = gap.strip()
            if prev_end >= 0 and len(gap_clean) <= 1 and (not gap_clean or gap_clean in "，、,；;"):
                stack_count += 1
                stack_words.append(m.group())
            else:
                if stack_count >= 3:
                    details.append({
                        "type": "四字词堆叠",
                        "line": stack_start_line,
                        "count": stack_count,
                        "words": stack_words[:5],
                    })
                    self._add_segment(
                        stack_start_line,
                        "，".join(stack_words[:4]),
                        "L4", "四字词堆叠",
                    )
                    stack_issues += 1
                stack_count = 1
                stack_start_line = self._line_number_of(m.start())
                stack_words = [m.group()]
            prev_end = m.end()

        if stack_count >= 3:
            details.append({
                "type": "四字词堆叠",
                "line": stack_start_line,
                "count": stack_count,
                "words": stack_words[:5],
            })
            self._add_segment(
                stack_start_line,
                "，".join(stack_words[:4]),
                "L4", "四字词堆叠",
            )
            stack_issues += 1

        # 总量评分
        over = max(0, len(matches) - threshold)
        max_score = LAYER_MAX_SCORES["L4_idiom_density"]
        score = min(over + stack_issues * 3, max_score)

        if over > 0:
            details.append({
                "type": "四字词总量偏多",
                "count": len(matches),
                "threshold": threshold,
            })

        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # L5: 对话质量检测
    # ------------------------------------------------------------------

    def scan_layer5_dialogue_quality(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        issues = 0

        # 提取对话行（引号内容）
        dialogue_pattern = re.compile(r"[\u201c\u300c]([^\u201d\u300d]*)[\u201d\u300d]")

        hollow_count = 0
        long_dialogue_count = 0

        for m in dialogue_pattern.finditer(self.text):
            content = m.group(1).strip()
            line_num = self._line_number_of(m.start())

            # (a) 空洞对话
            if content in HOLLOW_DIALOGUE_WORDS or (len(content) <= 3 and not re.search(r"[\u4e00-\u9fff]{2,}", content)):
                hollow_count += 1
                if hollow_count <= 5:  # 只记录前 5 个
                    details.append({"type": "空洞对话", "line": line_num, "text": content})
                    self._add_segment(line_num, f"\u201c{content}\u201d", "L5", "空洞对话")

            # (b) 说明书式对话（对话行超过 100 字）
            if len(content) > 100:
                long_dialogue_count += 1
                details.append({"type": "说明书式对话", "line": line_num, "length": len(content)})
                self._add_segment(line_num, content[:60], "L5", "说明书式对话")

        issues = hollow_count + long_dialogue_count
        max_score = LAYER_MAX_SCORES["L5_dialogue_quality"]
        score = min(hollow_count * 2 + long_dialogue_count * 4, max_score)
        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # L6: 段落结构分析
    # ------------------------------------------------------------------

    def scan_layer6_paragraph_structure(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        issues = 0

        paragraphs = [p.strip() for p in self.text.split("\n\n") if p.strip()]
        if not paragraphs:
            max_score = LAYER_MAX_SCORES["L6_paragraph_structure"]
            return {"score": 0, "max": max_score, "details": []}

        para_lengths = [len(re.sub(r"\s+", "", p)) for p in paragraphs]

        # (a) 单句成段比例（目标 25-45%）
        single_sentence_count = 0
        for p in paragraphs:
            # 单句：段落内只有一个句号/问号/叹号
            sentence_ends = len(re.findall(r"[。！？]", p))
            if sentence_ends <= 1:
                single_sentence_count += 1

        single_ratio = single_sentence_count / len(paragraphs) if paragraphs else 0
        if single_ratio < 0.25:
            details.append({
                "type": "单句成段过少",
                "ratio": round(single_ratio * 100, 1),
                "target": "25-45%",
            })
            self._add_segment(0, f"单句成段比例 {single_ratio*100:.1f}%（目标 25-45%）", "L6", "单句成段过少")
            issues += 1
        elif single_ratio > 0.45:
            details.append({
                "type": "单句成段过多",
                "ratio": round(single_ratio * 100, 1),
                "target": "25-45%",
            })
            self._add_segment(0, f"单句成段比例 {single_ratio*100:.1f}%（目标 25-45%）", "L6", "单句成段过多")
            issues += 1

        # (b) 段落平均长度（目标 20-100 字）
        avg_len = sum(para_lengths) / len(para_lengths) if para_lengths else 0
        if avg_len < 20:
            details.append({"type": "段落偏短", "avg_length": round(avg_len, 1), "target": "20-100"})
            self._add_segment(0, f"段落平均长度 {avg_len:.1f} 字（目标 20-100）", "L6", "段落偏短")
            issues += 1
        elif avg_len > 100:
            details.append({"type": "段落偏长", "avg_length": round(avg_len, 1), "target": "20-100"})
            self._add_segment(0, f"段落平均长度 {avg_len:.1f} 字（目标 20-100）", "L6", "段落偏长")
            issues += 1

        # (c) 检测过长段落（>300 字）
        char_offset = 0
        for i, para in enumerate(paragraphs):
            para_len = para_lengths[i]
            if para_len > 300:
                line_num = self._line_number_of(self.text.find(para[:30])) if para else 0
                details.append({"type": "过长段落", "line": line_num, "length": para_len})
                self._add_segment(line_num, para[:60], "L6", "过长段落")
                issues += 1

        max_score = LAYER_MAX_SCORES["L6_paragraph_structure"]
        score = min(issues * 4, max_score)
        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # L7: 标点节奏
    # ------------------------------------------------------------------

    def scan_layer7_punctuation_rhythm(self) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        issues = 0

        # (a) 连续省略号（…… 连续出现 2+ 次）
        for m in re.finditer(r"(……){2,}", self.text):
            line_num = self._line_number_of(m.start())
            details.append({"type": "连续省略号", "line": line_num})
            self._add_segment(line_num, m.group()[:20], "L7", "连续省略号")
            issues += 1

        # 也检测连续 6+ 个点的情况
        for m in re.finditer(r"\.{6,}|。{2,}|·{4,}", self.text):
            line_num = self._line_number_of(m.start())
            details.append({"type": "连续省略号", "line": line_num})
            self._add_segment(line_num, m.group()[:20], "L7", "连续省略号")
            issues += 1

        # (b) 连续感叹号（！连续出现 3+ 次）
        for m in re.finditer(r"[！!]{3,}", self.text):
            line_num = self._line_number_of(m.start())
            details.append({"type": "连续感叹号", "line": line_num, "count": len(m.group())})
            self._add_segment(line_num, m.group(), "L7", "连续感叹号")
            issues += 1

        # (c) 长句逗号过多（一句话中逗号超过 4 个）
        sentences = re.split(r"[。！？\n]", self.text)
        for sent in sentences:
            comma_count = len(re.findall(r"[，,]", sent))
            if comma_count > 4 and len(sent.strip()) > 10:
                pos = self.text.find(sent[:20])
                line_num = self._line_number_of(pos) if pos >= 0 else 0
                details.append({
                    "type": "逗号过多长句",
                    "line": line_num,
                    "comma_count": comma_count,
                    "length": len(sent.strip()),
                })
                self._add_segment(line_num, sent.strip()[:60], "L7", "逗号过多长句")
                issues += 1

        max_score = LAYER_MAX_SCORES["L7_punctuation_rhythm"]
        score = min(issues * 3, max_score)
        return {"score": score, "max": max_score, "details": details}

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def scan_all(self) -> Dict[str, Any]:
        """执行全部 7 层扫描，返回汇总结果。"""
        layer_results = {
            "L1_high_risk_words": self.scan_layer1_high_risk_words(),
            "L2_sentence_pattern": self.scan_layer2_sentence_pattern(),
            "L3_adjective_density": self.scan_layer3_adjective_density(),
            "L4_idiom_density": self.scan_layer4_idiom_density(),
            "L5_dialogue_quality": self.scan_layer5_dialogue_quality(),
            "L6_paragraph_structure": self.scan_layer6_paragraph_structure(),
            "L7_punctuation_rhythm": self.scan_layer7_punctuation_rhythm(),
        }

        total_score = sum(r["score"] for r in layer_results.values())
        total_max = sum(r["max"] for r in layer_results.values())

        # 归一化到 0-100
        risk_score = round(total_score / total_max * 100) if total_max > 0 else 0

        if risk_score < 30:
            risk_level = "low"
        elif risk_score <= 60:
            risk_level = "medium"
        else:
            risk_level = "high"

        # 生成摘要
        summary_parts: List[str] = []
        category_counter: Counter = Counter()
        for seg in self.high_risk_segments:
            category_counter[seg["category"]] += 1

        for cat, cnt in category_counter.most_common(3):
            summary_parts.append(f"{cat}偏多({cnt}处)")

        # 补充段落结构摘要
        l6 = layer_results["L6_paragraph_structure"]
        for d in l6["details"]:
            if d["type"] == "段落偏长":
                summary_parts.append(f"段落偏长(平均{d['avg_length']}字)")
                break
            if d["type"] == "段落偏短":
                summary_parts.append(f"段落偏短(平均{d['avg_length']}字)")
                break

        summary = "主要问题：" + "、".join(summary_parts) if summary_parts else "未发现明显AI写作痕迹"

        return {
            "file": self.filename,
            "total_chars": self.total_chars,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "layer_scores": layer_results,
            "high_risk_segments": self.high_risk_segments,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # 报告格式化
    # ------------------------------------------------------------------

    def format_report(self, result: Dict[str, Any]) -> str:
        """格式化为可读的 Markdown 报告。"""
        lines: List[str] = []

        risk_icon = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"}
        level = result["risk_level"]

        lines.append("=" * 60)
        lines.append(f"Anti-AI 扫描报告")
        lines.append("=" * 60)
        lines.append(f"文件: {result['file']}")
        lines.append(f"总字数: {result['total_chars']}")
        lines.append(f"风险评分: {result['risk_score']}/100 [{risk_icon.get(level, level)}]")
        lines.append("")

        # 各层得分
        lines.append("-" * 60)
        lines.append("各层得分:")
        lines.append("-" * 60)

        layer_names = {
            "L1_high_risk_words": "L1 高风险词汇",
            "L2_sentence_pattern": "L2 句式模式",
            "L3_adjective_density": "L3 形容词副词密度",
            "L4_idiom_density": "L4 四字套语密度",
            "L5_dialogue_quality": "L5 对话质量",
            "L6_paragraph_structure": "L6 段落结构",
            "L7_punctuation_rhythm": "L7 标点节奏",
        }

        for key, name in layer_names.items():
            layer = result["layer_scores"][key]
            bar_len = 20
            filled = round(layer["score"] / layer["max"] * bar_len) if layer["max"] > 0 else 0
            bar = "#" * filled + "." * (bar_len - filled)
            lines.append(f"  {name:16s}  [{bar}] {layer['score']:2d}/{layer['max']}")

        # 高风险段落
        segments = result.get("high_risk_segments", [])
        if segments:
            lines.append("")
            lines.append("-" * 60)
            lines.append(f"高风险段落 (共 {len(segments)} 处):")
            lines.append("-" * 60)
            for seg in segments[:20]:  # 最多显示 20 条
                line_info = f"L{seg['line']:>4d}" if seg["line"] > 0 else "     "
                lines.append(f"  [{seg['layer']}] 行{line_info} [{seg['category']}]")
                lines.append(f"         {seg['text']}")
                if seg.get("suggestion"):
                    lines.append(f"         -> {seg['suggestion']}")
            if len(segments) > 20:
                lines.append(f"  ... 还有 {len(segments) - 20} 处未显示")

        # 摘要
        lines.append("")
        lines.append("=" * 60)
        lines.append(result["summary"])
        lines.append("=" * 60)

        return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def _resolve_file(args: argparse.Namespace) -> Path:
    """根据命令行参数解析要扫描的文件路径。"""
    if args.file:
        path = normalize_windows_path(args.file)
        if not path.exists():
            print(f"文件不存在: {path}", file=sys.stderr)
            sys.exit(1)
        return path

    if args.chapter is not None:
        # 需要 project-root
        from project_locator import resolve_project_root
        from chapter_paths import find_chapter_file

        try:
            project_root = resolve_project_root(args.project_root)
        except FileNotFoundError as e:
            print(f"无法定位项目根目录: {e}", file=sys.stderr)
            sys.exit(1)

        chapter_path = find_chapter_file(project_root, args.chapter)
        if not chapter_path:
            print(f"找不到第 {args.chapter} 章文件（项目: {project_root}）", file=sys.stderr)
            sys.exit(1)
        return chapter_path

    print("请指定 --file 或 --chapter 参数", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anti-AI 自动扫描工具 - 检测文本中的AI写作痕迹",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python anti_ai_scanner.py --file 第0042章-暗流涌动.md
  python anti_ai_scanner.py --project-root ./my-novel --chapter 42
  python anti_ai_scanner.py --file chapter.md --format json --output report.json
""".strip(),
    )
    parser.add_argument("--file", help="要扫描的文件路径")
    parser.add_argument("--project-root", default=None, help="项目根目录")
    parser.add_argument("--chapter", type=int, help="章节号（需配合 --project-root 使用）")
    parser.add_argument("--output", help="输出文件路径（默认输出到控制台）")
    parser.add_argument("--wordlist", help="自定义词库JSON文件路径")
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="markdown",
        help="输出格式（默认 markdown）",
    )

    args = parser.parse_args()

    file_path = _resolve_file(args)

    # 读取文件
    text = file_path.read_text(encoding="utf-8")
    if not text.strip():
        print(f"文件内容为空: {file_path}", file=sys.stderr)
        sys.exit(1)

    # 扫描
    scanner = AntiAIScanner(text, filename=file_path.name, custom_wordlist=args.wordlist)
    result = scanner.scan_all()

    # 输出
    if args.format == "json":
        output_text = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        output_text = scanner.format_report(result)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")
        print(f"报告已保存至: {output_path}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
