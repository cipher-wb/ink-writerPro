"""Voice fingerprint data model, learning, and scoring logic."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ink_writer.voice_fingerprint.config import (
    DeviationThresholds,
    LearningConfig,
    VoiceFingerprintConfig,
    load_config,
)

VOCABULARY_LEVELS = ["文雅", "书面", "口语", "白话", "粗犷"]
VOCAB_LEVEL_INDEX = {v: i for i, v in enumerate(VOCABULARY_LEVELS)}


@dataclass
class VoiceFingerprint:
    entity_id: str
    catchphrases: list[str] = field(default_factory=list)
    speech_habits: list[str] = field(default_factory=list)
    vocabulary_level: str = "口语"
    tone: str = ""
    dialect_markers: list[str] = field(default_factory=list)
    forbidden_expressions: list[str] = field(default_factory=list)
    learned_chapter: int = 0
    last_updated_chapter: int = 0

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "catchphrases": self.catchphrases,
            "speech_habits": self.speech_habits,
            "vocabulary_level": self.vocabulary_level,
            "tone": self.tone,
            "dialect_markers": self.dialect_markers,
            "forbidden_expressions": self.forbidden_expressions,
            "learned_chapter": self.learned_chapter,
            "last_updated_chapter": self.last_updated_chapter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceFingerprint:
        return cls(
            entity_id=data.get("entity_id", ""),
            catchphrases=data.get("catchphrases", []),
            speech_habits=data.get("speech_habits", []),
            vocabulary_level=data.get("vocabulary_level", "口语"),
            tone=data.get("tone", ""),
            dialect_markers=data.get("dialect_markers", []),
            forbidden_expressions=data.get("forbidden_expressions", []),
            learned_chapter=data.get("learned_chapter", 0),
            last_updated_chapter=data.get("last_updated_chapter", 0),
        )


@dataclass
class VoiceViolation:
    violation_id: str
    severity: str  # "critical" | "high" | "medium" | "low"
    entity_id: str
    entity_name: str
    description: str
    suggestion: str
    must_fix: bool = False


@dataclass
class VoiceScoreResult:
    entity_id: str
    entity_name: str
    score: float
    violations: list[VoiceViolation] = field(default_factory=list)
    passed: bool = True


@dataclass
class ChapterVoiceReport:
    chapter_no: int
    overall_score: float
    character_scores: list[VoiceScoreResult] = field(default_factory=list)
    violations: list[VoiceViolation] = field(default_factory=list)
    passed: bool = True
    distinctiveness_issues: list[VoiceViolation] = field(default_factory=list)


def load_fingerprint_from_db(
    db_path: str | Path,
    entity_id: str,
) -> VoiceFingerprint | None:
    """Load the latest voice fingerprint for an entity from character_evolution_ledger."""
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT voice_fingerprint_json, chapter FROM character_evolution_ledger "
            "WHERE entity_id = ? AND voice_fingerprint_json IS NOT NULL "
            "ORDER BY chapter DESC LIMIT 1",
            (entity_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()

    if row is None:
        return None

    try:
        data = json.loads(row["voice_fingerprint_json"])
    except (json.JSONDecodeError, TypeError):
        return None

    fp = VoiceFingerprint.from_dict(data)
    fp.entity_id = entity_id
    fp.last_updated_chapter = row["chapter"]
    return fp


def load_all_fingerprints(
    db_path: str | Path,
    entity_ids: list[str] | None = None,
) -> dict[str, VoiceFingerprint]:
    """Load latest voice fingerprints for multiple entities."""
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            rows = conn.execute(
                f"SELECT entity_id, voice_fingerprint_json, chapter "
                f"FROM character_evolution_ledger "
                f"WHERE entity_id IN ({placeholders}) AND voice_fingerprint_json IS NOT NULL "
                f"ORDER BY entity_id, chapter DESC",
                entity_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT entity_id, voice_fingerprint_json, chapter "
                "FROM character_evolution_ledger "
                "WHERE voice_fingerprint_json IS NOT NULL "
                "ORDER BY entity_id, chapter DESC"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()

    result: dict[str, VoiceFingerprint] = {}
    for row in rows:
        eid = row["entity_id"]
        if eid in result:
            continue
        try:
            data = json.loads(row["voice_fingerprint_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        fp = VoiceFingerprint.from_dict(data)
        fp.entity_id = eid
        fp.last_updated_chapter = row["chapter"]
        result[eid] = fp

    return result


def save_fingerprint_to_db(
    db_path: str | Path,
    fingerprint: VoiceFingerprint,
    chapter: int,
) -> None:
    """Save voice fingerprint JSON to character_evolution_ledger."""
    db_path = str(db_path)
    fp_json = json.dumps(fingerprint.to_dict(), ensure_ascii=False)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO character_evolution_ledger (entity_id, chapter, voice_fingerprint_json) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(entity_id, chapter) DO UPDATE SET "
            "voice_fingerprint_json = excluded.voice_fingerprint_json",
            (fingerprint.entity_id, chapter, fp_json),
        )
        conn.commit()
    finally:
        conn.close()


def merge_fingerprint(
    existing: VoiceFingerprint,
    new_data: dict,
    chapter: int,
    learning_config: LearningConfig | None = None,
) -> VoiceFingerprint:
    """Append-only merge of new voice data into existing fingerprint."""
    if learning_config is None:
        learning_config = LearningConfig()

    merged = VoiceFingerprint(
        entity_id=existing.entity_id,
        catchphrases=list(existing.catchphrases),
        speech_habits=list(existing.speech_habits),
        vocabulary_level=existing.vocabulary_level,
        tone=existing.tone or new_data.get("tone", ""),
        dialect_markers=list(existing.dialect_markers),
        forbidden_expressions=list(existing.forbidden_expressions),
        learned_chapter=existing.learned_chapter or chapter,
        last_updated_chapter=chapter,
    )

    for cp in new_data.get("catchphrases", []):
        if cp and cp not in merged.catchphrases:
            if len(merged.catchphrases) < learning_config.max_catchphrases:
                merged.catchphrases.append(cp)

    for sh in new_data.get("speech_habits", []):
        if sh and sh not in merged.speech_habits:
            if len(merged.speech_habits) < learning_config.max_speech_habits:
                merged.speech_habits.append(sh)

    for dm in new_data.get("dialect_markers", []):
        if dm and dm not in merged.dialect_markers:
            merged.dialect_markers.append(dm)

    for fe in new_data.get("forbidden_expressions", []):
        if fe and fe not in merged.forbidden_expressions:
            if len(merged.forbidden_expressions) < learning_config.max_forbidden_expressions:
                merged.forbidden_expressions.append(fe)

    new_vocab = new_data.get("vocabulary_level")
    if new_vocab and new_vocab in VOCAB_LEVEL_INDEX:
        merged.vocabulary_level = new_vocab

    new_tone = new_data.get("tone")
    if new_tone:
        merged.tone = new_tone

    return merged


def _extract_dialogue_for_entity(chapter_text: str, entity_name: str) -> list[str]:
    """Extract dialogue lines attributed to a specific character."""
    lines: list[str] = []
    patterns = [
        rf'{re.escape(entity_name)}[：:]["「](.+?)[」"]',
        rf'{re.escape(entity_name)}(?:说|道|喊|叫|笑|怒|问|答|叹|吼|嘟囔|嘀咕|低声|冷声|沉声|淡淡)(?:道)?[：:，,]?\s*["「](.+?)[」"]',
        rf'["「](.+?)[」"]\s*{re.escape(entity_name)}(?:说|道|喊)',
    ]
    for pat in patterns:
        matches = re.findall(pat, chapter_text, re.DOTALL)
        lines.extend(matches)
    return lines


def score_chapter_voice(
    chapter_text: str,
    chapter_no: int,
    character_fingerprints: dict[str, tuple[str, VoiceFingerprint]],
    config: VoiceFingerprintConfig | None = None,
) -> ChapterVoiceReport:
    """Score a chapter's voice consistency against known fingerprints.

    Args:
        chapter_text: Full chapter text.
        chapter_no: Chapter number.
        character_fingerprints: {entity_id: (entity_name, fingerprint)}.
        config: Voice fingerprint config.

    Returns:
        ChapterVoiceReport with per-character scores and violations.
    """
    if config is None:
        config = load_config()

    thresholds = config.deviation_thresholds
    all_violations: list[VoiceViolation] = []
    character_scores: list[VoiceScoreResult] = []

    for entity_id, (entity_name, fp) in character_fingerprints.items():
        dialogue_lines = _extract_dialogue_for_entity(chapter_text, entity_name)
        violations: list[VoiceViolation] = []
        score = 100.0

        if not dialogue_lines:
            character_scores.append(VoiceScoreResult(
                entity_id=entity_id,
                entity_name=entity_name,
                score=100.0,
                passed=True,
            ))
            continue

        dialogue_text = " ".join(dialogue_lines)

        for fe in fp.forbidden_expressions:
            if fe and fe in dialogue_text:
                v = VoiceViolation(
                    violation_id="VOICE_FORBIDDEN_EXPRESSION",
                    severity=thresholds.forbidden_expression_severity,
                    entity_id=entity_id,
                    entity_name=entity_name,
                    description=f"角色「{entity_name}」使用了禁忌表达: 「{fe}」",
                    suggestion=f"移除或替换「{fe}」，使用符合角色语气指纹的表达",
                    must_fix=True,
                )
                violations.append(v)
                score -= 25.0

        catchphrase_found = 0
        for cp in fp.catchphrases:
            if cp and cp in chapter_text:
                catchphrase_found += 1

        if fp.catchphrases and catchphrase_found == 0:
            chapters_since = chapter_no - fp.last_updated_chapter
            if chapters_since >= thresholds.catchphrase_absence_chapters:
                v = VoiceViolation(
                    violation_id="VOICE_CATCHPHRASE_ABSENT",
                    severity="medium",
                    entity_id=entity_id,
                    entity_name=entity_name,
                    description=(
                        f"角色「{entity_name}」已连续{chapters_since}章未使用任何口头禅"
                        f"（已知: {', '.join(fp.catchphrases[:3])}）"
                    ),
                    suggestion=f"在对话中自然融入角色口头禅",
                    must_fix=False,
                )
                violations.append(v)
                score -= 10.0

        if fp.vocabulary_level and fp.vocabulary_level in VOCAB_LEVEL_INDEX:
            expected_idx = VOCAB_LEVEL_INDEX[fp.vocabulary_level]
            avg_line_len = sum(len(l) for l in dialogue_lines) / max(len(dialogue_lines), 1)
            inferred_idx = _infer_vocab_level_from_length(avg_line_len)
            diff = abs(expected_idx - inferred_idx) / max(len(VOCABULARY_LEVELS) - 1, 1)
            if diff > thresholds.vocabulary_level_mismatch:
                v = VoiceViolation(
                    violation_id="VOICE_VOCAB_MISMATCH",
                    severity="medium",
                    entity_id=entity_id,
                    entity_name=entity_name,
                    description=(
                        f"角色「{entity_name}」的用词层次偏离："
                        f"预期「{fp.vocabulary_level}」，实际对话风格不符"
                    ),
                    suggestion=f"调整对话用词层次至「{fp.vocabulary_level}」级别",
                    must_fix=False,
                )
                violations.append(v)
                score -= 15.0

        for v in violations:
            all_violations.append(v)

        score = max(score, 0.0)
        character_scores.append(VoiceScoreResult(
            entity_id=entity_id,
            entity_name=entity_name,
            score=score,
            violations=violations,
            passed=score >= config.score_threshold,
        ))

    distinctiveness_issues = _check_voice_distinctiveness(
        chapter_text, character_fingerprints, thresholds,
    )
    all_violations.extend(distinctiveness_issues)

    if character_scores:
        overall_score = sum(cs.score for cs in character_scores) / len(character_scores)
    else:
        overall_score = 100.0

    if distinctiveness_issues:
        overall_score -= 5.0 * len(distinctiveness_issues)
        overall_score = max(overall_score, 0.0)

    passed = overall_score >= config.score_threshold

    return ChapterVoiceReport(
        chapter_no=chapter_no,
        overall_score=overall_score,
        character_scores=character_scores,
        violations=all_violations,
        passed=passed,
        distinctiveness_issues=distinctiveness_issues,
    )


def _infer_vocab_level_from_length(avg_len: float) -> int:
    """Heuristic: shorter dialogue → more colloquial, longer → more literary."""
    if avg_len < 8:
        return 3  # 白话
    elif avg_len < 15:
        return 2  # 口语
    elif avg_len < 25:
        return 1  # 书面
    else:
        return 0  # 文雅


def _check_voice_distinctiveness(
    chapter_text: str,
    character_fingerprints: dict[str, tuple[str, VoiceFingerprint]],
    thresholds: DeviationThresholds,
) -> list[VoiceViolation]:
    """Check if different characters have distinct dialogue styles."""
    issues: list[VoiceViolation] = []
    entities = list(character_fingerprints.items())

    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            eid_a, (name_a, fp_a) = entities[i]
            eid_b, (name_b, fp_b) = entities[j]

            lines_a = _extract_dialogue_for_entity(chapter_text, name_a)
            lines_b = _extract_dialogue_for_entity(chapter_text, name_b)

            if len(lines_a) < 2 or len(lines_b) < 2:
                continue

            avg_len_a = sum(len(l) for l in lines_a) / len(lines_a)
            avg_len_b = sum(len(l) for l in lines_b) / len(lines_b)
            len_diff = abs(avg_len_a - avg_len_b) / max(avg_len_a, avg_len_b, 1)

            vocab_a = VOCAB_LEVEL_INDEX.get(fp_a.vocabulary_level, 2)
            vocab_b = VOCAB_LEVEL_INDEX.get(fp_b.vocabulary_level, 2)
            vocab_diff = abs(vocab_a - vocab_b) / max(len(VOCABULARY_LEVELS) - 1, 1)

            combined_diff = (len_diff + vocab_diff) / 2.0

            if combined_diff < thresholds.distinctiveness_min_diff:
                v = VoiceViolation(
                    violation_id="VOICE_INDISTINCT",
                    severity="medium",
                    entity_id=f"{eid_a}+{eid_b}",
                    entity_name=f"{name_a}+{name_b}",
                    description=(
                        f"角色「{name_a}」与「{name_b}」的对话风格过于相似"
                        f"（差异度{combined_diff:.2f} < 阈值{thresholds.distinctiveness_min_diff}）"
                    ),
                    suggestion=(
                        f"增大两人的说话风格差异："
                        f"一个用长句一个用短句、一个温和一个粗暴、一个直白一个含蓄"
                    ),
                    must_fix=False,
                )
                issues.append(v)

    return issues
