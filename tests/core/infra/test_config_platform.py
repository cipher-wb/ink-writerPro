from ink_writer.core.infra.config import DataModulesConfig


def test_pacing_platform_fanqie_tighter():
    cfg = DataModulesConfig()
    cfg.platform = "fanqie"
    assert cfg.pacing_words_per_point_block == 500


def test_pacing_platform_qidian_default():
    cfg = DataModulesConfig()
    cfg.platform = "qidian"
    assert cfg.pacing_words_per_point_block == cfg.pacing_words_per_point_acceptable


def test_strand_platform_fanqie_shorter():
    cfg = DataModulesConfig()
    cfg.platform = "fanqie"
    assert cfg.strand_quest_max_consecutive_platform == 3


def test_strand_platform_qidian_default():
    cfg = DataModulesConfig()
    cfg.platform = "qidian"
    assert cfg.strand_quest_max_consecutive_platform == cfg.strand_quest_max_consecutive


def test_platform_default_is_qidian():
    cfg = DataModulesConfig()
    assert cfg.platform == "qidian"


def test_platform_setter_rejects_invalid():
    cfg = DataModulesConfig()
    cfg.platform = "invalid"
    assert cfg.platform == "qidian"  # unchanged
