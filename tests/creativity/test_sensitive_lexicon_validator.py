"""v16 US-011：sensitive_lexicon_validator 单元测试。

覆盖：
- 档位 1 保守：任何 L0/L1/L2/L3 都 HARD；
- 档位 2 平衡：L0 允许（V1/V2/V3），L1 仅 V2/V3 允许，L2/L3 禁；
- 档位 3 激进：L2 仅 V3 允许；
- 档位 4 疯批：L2 仅 V3 允许；L3 全档禁；
- 密度上限校验；
- 参数非法。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.creativity.sensitive_lexicon_validator import (
    VALID_AGGRESSION_LEVELS,
    VALID_VOICES,
    validate_density,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_cache()
    yield
    reset_cache()


class TestInvalidParams:
    def test_invalid_voice(self):
        r = validate_density("text", voice="V4", aggression=2)
        assert not r.passed
        assert any(v.id == "LEX_INVALID_VOICE" for v in r.violations)

    def test_invalid_aggression(self):
        r = validate_density("text", voice="V1", aggression=99)
        assert not r.passed
        assert any(v.id == "LEX_INVALID_AGGRESSION" for v in r.violations)

    def test_constants_sizes(self):
        assert VALID_VOICES == {"V1", "V2", "V3"}
        assert VALID_AGGRESSION_LEVELS == {1, 2, 3, 4}


class TestAggressionLevel1:
    """档位 1 保守：零容忍。任何 L0/L1/L2/L3 均 HARD。"""

    def test_clean_text_passes(self):
        text = "山风吹过屋檐。" * 100
        r = validate_density(text, voice="V1", aggression=1)
        assert r.passed

    def test_l0_in_level_1_fails(self):
        # "老子" 是 L0，档位 1 禁
        text = "老子" * 10 + ("山风吹过屋檐。" * 100)
        r = validate_density(text, voice="V1", aggression=1)
        assert not r.passed
        assert any(v.id == "LEX_L0_NOT_ALLOWED_IN_LEVEL_1" for v in r.violations)


class TestAggressionLevel2:
    def test_l0_in_v1_allowed(self):
        # 档位 2 下 L0 允许全档；少量出现 + 大背景稀释
        text = "老子笑了一下。" + ("山风吹过屋檐，云层低垂。" * 100)
        r = validate_density(text, voice="V1", aggression=2)
        assert r.passed, f"violations={[v.id for v in r.violations]}"

    def test_l1_in_v1_fails(self):
        # L1 在 V1 永远 HARD（不管档位）
        text = "卧槽一下。" + "山风吹过屋檐。" * 100
        r = validate_density(text, voice="V1", aggression=2)
        assert not r.passed
        assert any(v.id == "LEX_L1_NOT_ALLOWED_IN_VOICE" for v in r.violations)

    def test_l1_in_v2_allowed(self):
        text = "卧槽一下。" + "山风吹过屋檐，云层低垂。" * 500
        r = validate_density(text, voice="V2", aggression=2)
        # 一次 L1 + 大背景稀释，总密度应低于 0.2% 上限
        assert r.passed, f"violations={[v.id for v in r.violations]}"

    def test_l2_in_v3_aggression_2_fails(self):
        # L2 在档位 <3 不允许，即使 V3
        text = "腰软一下。" + "山风吹过屋檐。" * 100
        r = validate_density(text, voice="V3", aggression=2)
        assert not r.passed
        assert any(v.id == "LEX_L2_NOT_ALLOWED_IN_VOICE" for v in r.violations)


class TestAggressionLevel3:
    def test_l2_in_v3_aggression_3_allowed(self):
        text = "腰软一下。" + "山风吹过屋檐，云层低垂。" * 500
        r = validate_density(text, voice="V3", aggression=3)
        assert r.passed, f"violations={[v.id for v in r.violations]}"

    def test_l2_in_v2_aggression_3_fails(self):
        # L2 在 V2 禁，即使档位 3
        text = "腰软一下。" + "山风吹过屋檐。" * 500
        r = validate_density(text, voice="V2", aggression=3)
        assert not r.passed
        assert any(v.id == "LEX_L2_NOT_ALLOWED_IN_VOICE" for v in r.violations)


class TestAggressionLevel4:
    def test_l2_in_v3_aggression_4_allowed(self):
        text = "腰软一下。眼神勾魂。" + "山风吹过屋檐，云层低垂。" * 500
        r = validate_density(text, voice="V3", aggression=4)
        assert r.passed, f"violations={[v.id for v in r.violations]}"


class TestL3RedLine:
    def test_l3_always_hard_regardless_of_voice_or_aggression(self):
        for voice in ("V1", "V2", "V3"):
            for agg in (1, 2, 3, 4):
                text = "L3_RED_LINE_TOKEN_A" + "山风吹过屋檐。" * 500
                r = validate_density(text, voice=voice, aggression=agg)
                assert not r.passed, f"voice={voice} agg={agg} 应因 L3 阻断"
                assert any(
                    v.id == "LEX_L3_RED_LINE" for v in r.violations
                ), f"voice={voice} agg={agg} 未命中 L3 规则"


class TestDensityCap:
    def test_density_over_cap_hard_fails(self):
        # 档位 2 上限 ≈ 0.2%。用大量 L0 堆密度：100 次 "老子" = 200 字 L0，
        # 正文总长必须 < 100000 字才会超 0.2%。构造 50000 字总长场景 OK。
        l0_spam = "老子" * 1000  # 2000 字 L0
        bg = "山风吹过屋檐。" * 1000  # ~8000 字背景
        text = l0_spam + bg
        r = validate_density(text, voice="V2", aggression=2)
        assert not r.passed
        assert any(v.id == "LEX_DENSITY_OVER_CAP" for v in r.violations)

    def test_density_within_cap_passes(self):
        # 1 次 "老子" = 2 字 L0，背景 1000 字 → 密度 0.2%
        bg = "山风吹过屋檐，云层低垂。" * 100
        text = "老子" + bg
        r = validate_density(text, voice="V2", aggression=2)
        assert r.passed, f"violations={[v.id for v in r.violations]}"


class TestInjection:
    def test_custom_lexicon_path(self, tmp_path: Path):
        alt = tmp_path / "lex.json"
        alt.write_text(
            json.dumps({
                "L0": [], "L1": [], "L2": [],
                "L3": ["CUSTOM_RED"],
            }),
            encoding="utf-8",
        )
        text = "CUSTOM_RED 在此。"
        r = validate_density(
            text, voice="V2", aggression=2, lexicon_path=alt
        )
        assert not r.passed
        assert any(v.id == "LEX_L3_RED_LINE" for v in r.violations)

    def test_empty_text_passes(self):
        r = validate_density("", voice="V1", aggression=1)
        assert r.passed
