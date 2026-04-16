"""Tests for voice fingerprint data model, learning, scoring, and DB operations."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ink_writer.voice_fingerprint.config import (
    DeviationThresholds,
    LearningConfig,
    VoiceFingerprintConfig,
)
from ink_writer.voice_fingerprint.fingerprint import (
    ChapterVoiceReport,
    VoiceFingerprint,
    VoiceScoreResult,
    VoiceViolation,
    _check_voice_distinctiveness,
    _extract_dialogue_for_entity,
    _infer_vocab_level_from_length,
    load_all_fingerprints,
    load_fingerprint_from_db,
    merge_fingerprint,
    save_fingerprint_to_db,
    score_chapter_voice,
)


# ---- Fixtures ----

@pytest.fixture
def sample_fingerprint():
    return VoiceFingerprint(
        entity_id="xiaoyan",
        catchphrases=["斗之力，无处不在", "三十年河东"],
        speech_habits=["喜欢用反问句", "生气时用短句"],
        vocabulary_level="粗犷",
        tone="倔强不服输",
        dialect_markers=["老子"],
        forbidden_expressions=["在下", "请多指教"],
        learned_chapter=1,
        last_updated_chapter=10,
    )


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        conn = sqlite3.connect(f.name)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS character_evolution_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                chapter INTEGER NOT NULL,
                arc_phase TEXT,
                personality_delta TEXT,
                voice_sample TEXT,
                motivation_shift TEXT,
                relationship_shifts TEXT,
                voice_fingerprint_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(entity_id, chapter)
            )
        """)
        conn.commit()
        conn.close()
        yield f.name


# ---- VoiceFingerprint dataclass tests ----

def test_fingerprint_to_dict(sample_fingerprint):
    d = sample_fingerprint.to_dict()
    assert d["entity_id"] == "xiaoyan"
    assert d["catchphrases"] == ["斗之力，无处不在", "三十年河东"]
    assert d["vocabulary_level"] == "粗犷"
    assert d["tone"] == "倔强不服输"
    assert d["forbidden_expressions"] == ["在下", "请多指教"]


def test_fingerprint_from_dict():
    data = {
        "entity_id": "linran",
        "catchphrases": ["有意思"],
        "speech_habits": ["冷静分析"],
        "vocabulary_level": "书面",
        "tone": "淡然",
        "forbidden_expressions": [],
    }
    fp = VoiceFingerprint.from_dict(data)
    assert fp.entity_id == "linran"
    assert fp.catchphrases == ["有意思"]
    assert fp.vocabulary_level == "书面"


def test_fingerprint_from_dict_defaults():
    fp = VoiceFingerprint.from_dict({})
    assert fp.entity_id == ""
    assert fp.vocabulary_level == "口语"
    assert fp.catchphrases == []
    assert fp.learned_chapter == 0


# ---- DB operations ----

def test_save_and_load_fingerprint(db_path, sample_fingerprint):
    save_fingerprint_to_db(db_path, sample_fingerprint, chapter=10)
    loaded = load_fingerprint_from_db(db_path, "xiaoyan")
    assert loaded is not None
    assert loaded.entity_id == "xiaoyan"
    assert loaded.catchphrases == ["斗之力，无处不在", "三十年河东"]
    assert loaded.vocabulary_level == "粗犷"
    assert loaded.tone == "倔强不服输"
    assert loaded.last_updated_chapter == 10


def test_load_fingerprint_not_found(db_path):
    result = load_fingerprint_from_db(db_path, "nonexistent")
    assert result is None


def test_load_fingerprint_no_table():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        conn = sqlite3.connect(f.name)
        conn.close()
        result = load_fingerprint_from_db(f.name, "any")
        assert result is None


def test_save_fingerprint_upsert(db_path, sample_fingerprint):
    save_fingerprint_to_db(db_path, sample_fingerprint, chapter=10)
    updated = VoiceFingerprint(
        entity_id="xiaoyan",
        catchphrases=["斗之力，无处不在", "新口头禅"],
        vocabulary_level="白话",
    )
    save_fingerprint_to_db(db_path, updated, chapter=10)
    loaded = load_fingerprint_from_db(db_path, "xiaoyan")
    assert loaded.catchphrases == ["斗之力，无处不在", "新口头禅"]
    assert loaded.vocabulary_level == "白话"


def test_load_all_fingerprints(db_path, sample_fingerprint):
    save_fingerprint_to_db(db_path, sample_fingerprint, chapter=10)
    fp2 = VoiceFingerprint(entity_id="linran", catchphrases=["有意思"], vocabulary_level="书面")
    save_fingerprint_to_db(db_path, fp2, chapter=5)

    all_fps = load_all_fingerprints(db_path)
    assert "xiaoyan" in all_fps
    assert "linran" in all_fps
    assert all_fps["xiaoyan"].vocabulary_level == "粗犷"
    assert all_fps["linran"].catchphrases == ["有意思"]


def test_load_all_fingerprints_with_filter(db_path, sample_fingerprint):
    save_fingerprint_to_db(db_path, sample_fingerprint, chapter=10)
    fp2 = VoiceFingerprint(entity_id="linran", catchphrases=["有意思"])
    save_fingerprint_to_db(db_path, fp2, chapter=5)

    result = load_all_fingerprints(db_path, entity_ids=["xiaoyan"])
    assert "xiaoyan" in result
    assert "linran" not in result


def test_load_all_fingerprints_latest_only(db_path):
    fp_old = VoiceFingerprint(entity_id="xiaoyan", catchphrases=["旧口头禅"], vocabulary_level="口语")
    save_fingerprint_to_db(db_path, fp_old, chapter=5)
    fp_new = VoiceFingerprint(entity_id="xiaoyan", catchphrases=["新口头禅"], vocabulary_level="粗犷")
    save_fingerprint_to_db(db_path, fp_new, chapter=15)

    result = load_all_fingerprints(db_path)
    assert result["xiaoyan"].catchphrases == ["新口头禅"]
    assert result["xiaoyan"].last_updated_chapter == 15


# ---- Merge ----

def test_merge_fingerprint_append_only(sample_fingerprint):
    new_data = {
        "catchphrases": ["新口头禅", "斗之力，无处不在"],  # one duplicate
        "speech_habits": ["新习惯"],
        "forbidden_expressions": ["请多指教", "新禁忌"],  # one duplicate
        "tone": "暴躁易怒",
    }
    merged = merge_fingerprint(sample_fingerprint, new_data, chapter=20)
    assert "新口头禅" in merged.catchphrases
    assert merged.catchphrases.count("斗之力，无处不在") == 1  # no duplicate
    assert "新习惯" in merged.speech_habits
    assert "新禁忌" in merged.forbidden_expressions
    assert merged.forbidden_expressions.count("请多指教") == 1
    assert merged.tone == "暴躁易怒"
    assert merged.learned_chapter == 1  # preserved
    assert merged.last_updated_chapter == 20


def test_merge_fingerprint_max_limits():
    existing = VoiceFingerprint(
        entity_id="test",
        catchphrases=["a", "b", "c", "d", "e"],
    )
    config = LearningConfig(max_catchphrases=5)
    new_data = {"catchphrases": ["f"]}
    merged = merge_fingerprint(existing, new_data, chapter=10, learning_config=config)
    assert len(merged.catchphrases) == 5  # cap at max
    assert "f" not in merged.catchphrases


def test_merge_fingerprint_empty_new_data(sample_fingerprint):
    merged = merge_fingerprint(sample_fingerprint, {}, chapter=20)
    assert merged.catchphrases == sample_fingerprint.catchphrases
    assert merged.tone == sample_fingerprint.tone


# ---- Dialogue extraction ----

def test_extract_dialogue_basic():
    text = '萧炎："斗之力，无处不在！"\n路人说道："你是谁？"'
    lines = _extract_dialogue_for_entity(text, "萧炎")
    assert len(lines) >= 1
    assert any("斗之力" in l for l in lines)


def test_extract_dialogue_various_patterns():
    text = (
        '萧炎冷声道："你找死。"\n'
        '萧炎笑："有意思。"\n'
        '"我不会输的。"萧炎说\n'
    )
    lines = _extract_dialogue_for_entity(text, "萧炎")
    assert len(lines) >= 2


def test_extract_dialogue_no_match():
    text = '林渊："有意思。"'
    lines = _extract_dialogue_for_entity(text, "萧炎")
    assert lines == []


# ---- Vocab level inference ----

def test_infer_vocab_short():
    assert _infer_vocab_level_from_length(5) == 3  # 白话

def test_infer_vocab_medium():
    assert _infer_vocab_level_from_length(12) == 2  # 口语

def test_infer_vocab_long():
    assert _infer_vocab_level_from_length(20) == 1  # 书面

def test_infer_vocab_very_long():
    assert _infer_vocab_level_from_length(30) == 0  # 文雅


# ---- Chapter scoring ----

def test_score_no_characters():
    report = score_chapter_voice("一些文本", 1, {})
    assert report.passed is True
    assert report.overall_score == 100.0


def test_score_no_dialogue():
    fp = VoiceFingerprint(entity_id="linran", catchphrases=["有意思"])
    report = score_chapter_voice(
        "没有对话的叙事段落",
        1,
        {"linran": ("林渊", fp)},
    )
    assert report.passed is True
    assert report.character_scores[0].score == 100.0


def test_score_forbidden_expression_violation():
    fp = VoiceFingerprint(
        entity_id="xiaoyan",
        catchphrases=[],
        forbidden_expressions=["请多指教"],
        vocabulary_level="粗犷",
        last_updated_chapter=1,
    )
    text = '萧炎："请多指教，前辈。"'
    report = score_chapter_voice(
        text, 5,
        {"xiaoyan": ("萧炎", fp)},
    )
    assert any(v.violation_id == "VOICE_FORBIDDEN_EXPRESSION" for v in report.violations)
    found = [v for v in report.violations if v.violation_id == "VOICE_FORBIDDEN_EXPRESSION"]
    assert found[0].severity == "critical"
    assert found[0].must_fix is True


def test_score_catchphrase_absent_warning():
    fp = VoiceFingerprint(
        entity_id="xiaoyan",
        catchphrases=["斗之力无处不在"],
        vocabulary_level="口语",
        last_updated_chapter=1,
    )
    text = '萧炎："我会变强的。"'
    config = VoiceFingerprintConfig(
        deviation_thresholds=DeviationThresholds(catchphrase_absence_chapters=3),
    )
    report = score_chapter_voice(text, 10, {"xiaoyan": ("萧炎", fp)}, config=config)
    assert any(v.violation_id == "VOICE_CATCHPHRASE_ABSENT" for v in report.violations)


def test_score_catchphrase_present_no_warning():
    fp = VoiceFingerprint(
        entity_id="xiaoyan",
        catchphrases=["斗之力"],
        vocabulary_level="口语",
        last_updated_chapter=1,
    )
    text = '萧炎冷声道："斗之力，无处不在。"'
    report = score_chapter_voice(text, 10, {"xiaoyan": ("萧炎", fp)})
    catchphrase_violations = [v for v in report.violations if v.violation_id == "VOICE_CATCHPHRASE_ABSENT"]
    assert len(catchphrase_violations) == 0


def test_score_overall_below_threshold():
    fp = VoiceFingerprint(
        entity_id="xiaoyan",
        forbidden_expressions=["在下", "请多指教", "前辈慢走"],
        vocabulary_level="粗犷",
        last_updated_chapter=1,
    )
    text = '萧炎："在下萧炎，请多指教，前辈慢走。"'
    config = VoiceFingerprintConfig(score_threshold=60.0)
    report = score_chapter_voice(text, 5, {"xiaoyan": ("萧炎", fp)}, config=config)
    assert report.passed is False


# ---- Distinctiveness ----

def test_distinctiveness_similar_characters():
    fp_a = VoiceFingerprint(entity_id="a", vocabulary_level="口语")
    fp_b = VoiceFingerprint(entity_id="b", vocabulary_level="口语")
    text = (
        '张三说道："你好啊。"\n'
        '李四说道："你好啊。"\n'
        '张三道："真是有趣。"\n'
        '李四道："确实有趣。"\n'
    )
    thresholds = DeviationThresholds(distinctiveness_min_diff=0.5)
    issues = _check_voice_distinctiveness(
        text,
        {"a": ("张三", fp_a), "b": ("李四", fp_b)},
        thresholds,
    )
    assert len(issues) >= 1
    assert issues[0].violation_id == "VOICE_INDISTINCT"


def test_distinctiveness_different_characters():
    fp_a = VoiceFingerprint(entity_id="a", vocabulary_level="文雅")
    fp_b = VoiceFingerprint(entity_id="b", vocabulary_level="粗犷")
    text = (
        '诸葛亮沉声道："此乃天机，不可妄言。"\n'
        '诸葛亮道："且看此番运势如何。"\n'
        '张飞喊："老子不管那些！干就完了！"\n'
        '张飞吼："谁敢拦路？"\n'
    )
    thresholds = DeviationThresholds(distinctiveness_min_diff=0.2)
    issues = _check_voice_distinctiveness(
        text,
        {"a": ("诸葛亮", fp_a), "b": ("张飞", fp_b)},
        thresholds,
    )
    assert len(issues) == 0


# ---- 300-chapter simulation ----

def test_300_chapter_simulation():
    """Simulate 300 chapters and ensure OOC score stays below 5."""
    fp_mc = VoiceFingerprint(
        entity_id="mc",
        catchphrases=["斗之力"],
        speech_habits=["反问句"],
        vocabulary_level="口语",
        tone="冷静",
        forbidden_expressions=["啊呀"],
        learned_chapter=1,
        last_updated_chapter=1,
    )
    fp_rival = VoiceFingerprint(
        entity_id="rival",
        catchphrases=["不自量力"],
        speech_habits=["嘲讽"],
        vocabulary_level="书面",
        tone="嚣张",
        forbidden_expressions=["对不起"],
        learned_chapter=1,
        last_updated_chapter=1,
    )

    config = VoiceFingerprintConfig(score_threshold=60.0)
    total_ooc_violations = 0

    for ch in range(1, 301):
        fp_mc.last_updated_chapter = max(fp_mc.last_updated_chapter, ch - 2)
        fp_rival.last_updated_chapter = max(fp_rival.last_updated_chapter, ch - 2)

        text = (
            f'第{ch}章\n'
            f'主角冷声道："斗之力，今天就让你见识一下。"\n'
            f'对手笑道："不自量力的蝼蚁。"\n'
            f'主角道："你确定？"\n'
            f'对手沉声道："有意思，来吧。"\n'
        )
        report = score_chapter_voice(
            text, ch,
            {"mc": ("主角", fp_mc), "rival": ("对手", fp_rival)},
            config=config,
        )
        total_ooc_violations += len([v for v in report.violations if v.severity in ("critical", "high")])

    ooc_score = total_ooc_violations / 300.0
    assert ooc_score < 5, f"OOC score {ooc_score} exceeds limit 5"
