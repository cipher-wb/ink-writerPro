"""Statistical sentence diversity analysis for AI-taste detection."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from ink_writer.anti_detection.config import AntiDetectionConfig

_SENTENCE_SPLIT = re.compile(r"[。？！…]+")
_DIALOGUE_RE = re.compile(r'[\u201c\u300c]([^\u201d\u300d]*?)[\u201d\u300d]')
_DIALOGUE_RE_STRAIGHT = re.compile(r'"([^"]*)"')
_CAUSAL_WORDS = re.compile(r"因为|所以|于是|因此|由于|导致|结果|从而|进而")
# US-014：连接词密度（递进 / 转折 / 并列 / 总结 / 递进式 AI 书面语）
_CONJUNCTION_WORDS = re.compile(
    r"不仅|不但|而且|此外|另外|同时|与此同时|"
    r"尽管如此|话虽如此|虽然|但是|然而|不过|可是|却|"
    r"总而言之|综上所述|总的来说|归根结底|"
    r"首先|其次|再者|最后|"
    r"毫无疑问|显而易见|不言而喻|众所周知|可想而知|"
    r"值得一提的是|值得注意的是|不得不提的是|不可否认"
)
_EXCLAMATION = re.compile(r"[！!]")
_ELLIPSIS = re.compile(r"[…]+|\.{3,}")
_QUESTION = re.compile(r"[？?]")


@dataclass
class DiversityViolation:
    id: str
    severity: str
    description: str
    location: str = ""
    fix_suggestion: str = ""


@dataclass
class DiversityReport:
    violations: list[DiversityViolation] = field(default_factory=list)
    sentence_cv: float = 0.0
    sentence_mean: float = 0.0
    short_ratio: float = 0.0
    long_ratio: float = 0.0
    dialogue_ratio: float = 0.0
    single_sentence_para_ratio: float = 0.0
    paragraph_cv: float = 0.0
    exclamation_density: float = 0.0
    ellipsis_density: float = 0.0
    question_density: float = 0.0
    total_punctuation_density: float = 0.0
    causal_density: float = 0.0
    conjunction_density: float = 0.0
    has_critical: bool = False


def _split_sentences(text: str) -> list[str]:
    raw = _SENTENCE_SPLIT.split(text)
    return [s.strip() for s in raw if s.strip()]


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n\s*\n|\n", text)
    return [p.strip() for p in paras if p.strip()]


def conjunction_density(text: str) -> float:
    """Return the conjunction count per 1000 characters.

    Covers progressive / transitional / summarizing / enumerative / omniscient-
    judgment connectives commonly over-used in AI-generated Chinese prose.
    Used by the anti-detection gate (US-014) alongside ``causal_density`` to
    catch textbook-style writing. Returns 0.0 for empty / very short inputs.
    """
    if not text:
        return 0.0
    total_chars = len(text)
    if total_chars < 100:
        return 0.0
    count = len(_CONJUNCTION_WORDS.findall(text))
    kchars = total_chars / 1000
    return count / kchars if kchars > 0 else 0.0


def analyze_diversity(text: str, config: AntiDetectionConfig) -> DiversityReport:
    """Analyze text for sentence diversity and return violations."""
    report = DiversityReport()
    if not text or len(text) < 100:
        return report

    sentences = _split_sentences(text)
    if len(sentences) < 3:
        return report

    lengths = [len(s) for s in sentences]
    mean_len = statistics.mean(lengths)
    std_len = statistics.stdev(lengths) if len(lengths) > 1 else 0.0
    cv = std_len / mean_len if mean_len > 0 else 0.0

    report.sentence_cv = cv
    report.sentence_mean = mean_len

    short_count = sum(1 for ln in lengths if ln <= 8)
    long_count = sum(1 for ln in lengths if ln >= 35)
    total = len(lengths)
    report.short_ratio = short_count / total
    report.long_ratio = long_count / total

    if cv < config.sentence_cv_min:
        report.violations.append(DiversityViolation(
            id="AD_SENTENCE_CV",
            severity="high",
            description=f"句长变异系数={cv:.2f}（阈值≥{config.sentence_cv_min}），节奏过于均匀",
            fix_suggestion="交替使用碎句（≤8字）和长流句（≥35字），制造心电图式节奏",
        ))

    if mean_len < config.sentence_mean_min:
        report.violations.append(DiversityViolation(
            id="AD_SENTENCE_FRAGMENTATION",
            severity="high",
            description=f"句长均值={mean_len:.1f}字（阈值≥{config.sentence_mean_min}，标杆28字），碎片化严重",
            fix_suggestion="合并连续短句为25-40字复合句，用逗号串联动作和细节",
        ))

    if report.short_ratio > config.short_sentence_ratio_max:
        report.violations.append(DiversityViolation(
            id="AD_SHORT_SENTENCE_EXCESS",
            severity="high",
            description=f"短句占比={report.short_ratio:.0%}（阈值≤{config.short_sentence_ratio_max:.0%}），短句过多",
            fix_suggestion="短句仅在紧张/冲击时刻使用，其余合并为中长句",
        ))

    if report.long_ratio < config.long_sentence_ratio_min:
        report.violations.append(DiversityViolation(
            id="AD_LONG_SENTENCE_DEFICIT",
            severity="medium",
            description=f"长句占比={report.long_ratio:.0%}（阈值≥{config.long_sentence_ratio_min:.0%}），缺乏长句纵深",
            fix_suggestion="在描写/内心段落插入≥35字长句，展现细腻纹理",
        ))

    paragraphs = _split_paragraphs(text)
    if paragraphs:
        para_lens = [len(p) for p in paragraphs]
        single_count = sum(1 for p in paragraphs if len(_split_sentences(p)) <= 1)
        report.single_sentence_para_ratio = single_count / len(paragraphs)
        if len(para_lens) > 1:
            pmean = statistics.mean(para_lens)
            pstd = statistics.stdev(para_lens)
            report.paragraph_cv = pstd / pmean if pmean > 0 else 0.0
        else:
            report.paragraph_cv = 0.0

        if report.single_sentence_para_ratio < config.single_sentence_paragraph_ratio_min:
            report.violations.append(DiversityViolation(
                id="AD_PARAGRAPH_REGULAR",
                severity="high",
                description=f"单句段占比={report.single_sentence_para_ratio:.0%}（阈值≥{config.single_sentence_paragraph_ratio_min:.0%}），段落结构过于工整",
                fix_suggestion="拆分长段为碎片段，增加单句段制造呼吸感",
            ))

        if report.paragraph_cv < config.paragraph_cv_min:
            report.violations.append(DiversityViolation(
                id="AD_PARAGRAPH_CV",
                severity="medium",
                description=f"段落长度变异系数={report.paragraph_cv:.2f}（阈值≥{config.paragraph_cv_min}），段落长度过于均匀",
                fix_suggestion="交替使用长段（100+字）和碎片段（≤15字），增加视觉节奏",
            ))

    dialogue_chars = sum(len(m.group(1)) for m in _DIALOGUE_RE.finditer(text))
    dialogue_chars += sum(len(m.group(1)) for m in _DIALOGUE_RE_STRAIGHT.finditer(text))
    total_chars = len(text)
    report.dialogue_ratio = dialogue_chars / total_chars if total_chars > 0 else 0.0

    if report.dialogue_ratio < config.dialogue_ratio_min:
        report.violations.append(DiversityViolation(
            id="AD_DIALOGUE_LOW",
            severity="high",
            description=f"对话占比={report.dialogue_ratio:.0%}（阈值≥{config.dialogue_ratio_min:.0%}），缺乏角色互动",
            fix_suggestion="将内心独白转化为角色对话，增加直接引语",
        ))

    kchars = total_chars / 1000 if total_chars > 0 else 1
    exc_count = len(_EXCLAMATION.findall(text))
    ell_count = len(_ELLIPSIS.findall(text))
    que_count = len(_QUESTION.findall(text))
    report.exclamation_density = exc_count / kchars
    report.ellipsis_density = ell_count / kchars
    report.question_density = que_count / kchars
    report.total_punctuation_density = (exc_count + ell_count + que_count) / kchars

    if report.exclamation_density < config.exclamation_density_min:
        report.violations.append(DiversityViolation(
            id="AD_EXCLAMATION_LOW",
            severity="high",
            description=f"感叹号密度={report.exclamation_density:.1f}/千字（阈值≥{config.exclamation_density_min}，标杆3.8）",
            fix_suggestion="角色情绪爆发时使用感叹号，不要为追求冷静而压制情感",
        ))

    if report.ellipsis_density < config.ellipsis_density_min:
        report.violations.append(DiversityViolation(
            id="AD_ELLIPSIS_LOW",
            severity="medium",
            description=f"省略号密度={report.ellipsis_density:.1f}/千字（阈值≥{config.ellipsis_density_min}，标杆2.8）",
            fix_suggestion="欲言又止/震惊/思索时使用省略号，增加戏剧停顿",
        ))

    if report.total_punctuation_density < config.total_emotion_punctuation_min:
        report.violations.append(DiversityViolation(
            id="AD_EMOTION_PUNCT_LOW",
            severity="high",
            description=f"情感标点总密度={report.total_punctuation_density:.1f}/千字（阈值≥{config.total_emotion_punctuation_min}）",
            fix_suggestion="增加感叹号、省略号、反问句，让角色情绪外化",
        ))

    causal_matches = _CAUSAL_WORDS.findall(text)
    per_200 = len(causal_matches) / (total_chars / 200) if total_chars >= 200 else 0
    report.causal_density = per_200

    if per_200 > config.causal_density_max:
        report.violations.append(DiversityViolation(
            id="AD_CAUSAL_DENSE",
            severity="medium",
            description=f"因果连接词密度={per_200:.1f}/200字（阈值≤{config.causal_density_max}），逻辑链过密",
            fix_suggestion="删除中间因果环节，让读者自行推断，保留叙事跳跃感",
        ))

    conj_per_k = conjunction_density(text)
    report.conjunction_density = conj_per_k
    if conj_per_k > config.conjunction_density_max:
        report.violations.append(DiversityViolation(
            id="AD_CONJUNCTION_DENSE",
            severity="medium",
            description=(
                f"连接词密度={conj_per_k:.1f}/千字（阈值≤{config.conjunction_density_max}），"
                f"'不仅/而且/尽管如此/毫无疑问'等书面连接词过多，AI 书面腔偏重"
            ),
            fix_suggestion="删除递进/转折/总结连接词，用画面和动作推进叙事，让逻辑隐藏在细节中",
        ))

    report.has_critical = any(v.severity == "critical" for v in report.violations)
    return report
