"""v16 US-010：gf_validator 单元测试（17 case，PRD AC 15+）。

覆盖：
- GF-1：dimension 白名单 + 22+ 禁用词
- GF-2：cost 可量化 / 可被反派利用 / 前 10 章可见
- GF-3：one_liner ≤20 字 + 动作 + 反直觉
- 全通过用例（三重合格的典型金手指）
- 边界：缺字段 / 空串 / 字数刚好 20 / 21
"""

from __future__ import annotations

import pytest

from ink_writer.creativity.gf_validator import (
    BANNED_WORDS,
    GF3_MAX_CHARS,
    VALID_DIMENSIONS,
    validate_golden_finger,
)
from ink_writer.creativity.name_validator import Severity


# ---------- helpers ----------


def _full_pass_spec() -> dict:
    """三重全过的典型金手指。"""
    return {
        "dimension": "信息",
        "cost": "每次使用扣减主角 1 年寿命；触发即被对手同步定位。",
        "one_liner": "我能听见死人的谎话，但每次少一年。",
    }


# ---------- TestFullPass ----------


class TestFullPass:
    def test_clean_spec_passes(self):
        r = validate_golden_finger(_full_pass_spec())
        assert r.passed, f"期望全过，violations={[v.id for v in r.violations]}"
        assert r.violations == []


# ---------- GF-1 ----------


class TestGF1Dimension:
    def test_valid_dimension_passes_gf1(self):
        r = validate_golden_finger(_full_pass_spec())
        gf1_ids = [v.id for v in r.violations if v.id.startswith("GF1")]
        assert gf1_ids == []

    def test_invalid_dimension_fails(self):
        spec = _full_pass_spec()
        spec["dimension"] = "修为"  # 不在白名单
        r = validate_golden_finger(spec)
        assert any(v.id == "GF1_DIMENSION_NOT_IN_WHITELIST" for v in r.violations)
        assert not r.passed

    def test_missing_dimension_fails(self):
        spec = _full_pass_spec()
        spec["dimension"] = ""
        r = validate_golden_finger(spec)
        assert any(v.id == "GF1_MISSING_DIMENSION" for v in r.violations)

    @pytest.mark.parametrize("banned", [
        "修为暴涨",
        "无限金币",
        "系统签到",
        "作弊器",
        "外挂",
        "吞噬天赋",
        "觉醒面板",
        "抽卡",
        "万倍返还",
        "境界飞升",
    ])
    def test_banned_word_triggers_hard_fail(self, banned: str):
        spec = _full_pass_spec()
        spec["cost"] = f"{spec['cost']}，附加{banned}。"
        r = validate_golden_finger(spec)
        matched = [v for v in r.violations if v.id == "GF1_BANNED_WORD"]
        assert matched, f"期望命中禁用词「{banned}」"
        assert matched[0].matched_token == banned
        assert matched[0].severity == Severity.HARD

    def test_banned_words_list_size_min_22(self):
        assert len(BANNED_WORDS) >= 22, f"PRD 要求 ≥20，实际 {len(BANNED_WORDS)}"

    def test_valid_dimensions_count_8(self):
        assert len(VALID_DIMENSIONS) == 8, "GF-1 维度白名单应为 8 类"


# ---------- GF-2 ----------


class TestGF2Cost:
    def test_not_quantifiable_fails(self):
        spec = _full_pass_spec()
        spec["cost"] = "需消耗法力，有点难受，被反派捕捉，立即显现。"
        r = validate_golden_finger(spec)
        assert any(v.id == "GF2_COST_NOT_QUANTIFIABLE" for v in r.violations)

    def test_not_adversary_exploitable_fails(self):
        spec = _full_pass_spec()
        # 有数字 + 立即，但无反派利用
        spec["cost"] = "每次使用扣减 1 年寿命，立即体现在身体上。"
        r = validate_golden_finger(spec)
        assert any(
            v.id == "GF2_COST_NOT_ADVERSARY_EXPLOITABLE" for v in r.violations
        )

    def test_not_visible_early_fails(self):
        spec = _full_pass_spec()
        # 有数字 + 被反派定位，但无前 10 章可见强度词（避开 "每次"/"立即"/"当场" 等）
        spec["cost"] = "累计使用 1 年后会被对手远端识别，慢慢显现在血脉上。"
        r = validate_golden_finger(spec)
        assert any(v.id == "GF2_COST_NOT_VISIBLE_EARLY" for v in r.violations)

    def test_missing_cost_fails(self):
        spec = _full_pass_spec()
        spec["cost"] = ""
        r = validate_golden_finger(spec)
        assert any(v.id == "GF2_MISSING_COST" for v in r.violations)


# ---------- GF-3 ----------


class TestGF3OneLiner:
    def test_length_boundary_at_20_passes(self):
        # 字数严格 ≤ 20
        spec = _full_pass_spec()
        # 构造一个动作 + 反直觉 + 恰 20 字的 one_liner
        spec["one_liner"] = "我每杀一人就老一岁，但能倒流一分钟。"
        r = validate_golden_finger(spec)
        assert not any(v.id == "GF3_OVER_LENGTH" for v in r.violations)

    def test_length_over_20_fails(self):
        spec = _full_pass_spec()
        spec["one_liner"] = (
            "我能听见世界上所有死去亡灵说出口的谎言，但每次都要付出一年的寿命代价。"
        )
        r = validate_golden_finger(spec)
        assert any(v.id == "GF3_OVER_LENGTH" for v in r.violations)

    def test_missing_action_fails(self):
        spec = _full_pass_spec()
        spec["one_liner"] = "世界很沉默，但无比奇妙。"  # 无动作/代价动词
        r = validate_golden_finger(spec)
        assert any(v.id == "GF3_NO_ACTION" for v in r.violations)

    def test_missing_counterintuitive_fails(self):
        spec = _full_pass_spec()
        # 有动作但没"但/除了/必须/代价"
        spec["one_liner"] = "我能听见死人的秘密。"
        r = validate_golden_finger(spec)
        assert any(v.id == "GF3_NO_COUNTERINTUITIVE" for v in r.violations)

    def test_missing_one_liner_fails(self):
        spec = _full_pass_spec()
        spec["one_liner"] = ""
        r = validate_golden_finger(spec)
        assert any(v.id == "GF3_MISSING_ONE_LINER" for v in r.violations)

    def test_gf3_max_chars_constant(self):
        assert GF3_MAX_CHARS == 20


# ---------- injection / 集成 ----------


class TestInjection:
    def test_custom_banned_words_override(self):
        spec = _full_pass_spec()
        spec["cost"] = spec["cost"] + " CUSTOM_BAD"
        r = validate_golden_finger(spec, banned_words=("CUSTOM_BAD",))
        assert any(
            v.id == "GF1_BANNED_WORD" and v.matched_token == "CUSTOM_BAD"
            for v in r.violations
        )

    def test_to_dict_serializable(self):
        import json
        r = validate_golden_finger({"dimension": "", "cost": "", "one_liner": ""})
        d = r.to_dict()
        assert d["passed"] is False
        assert json.dumps(d, ensure_ascii=False)

    def test_multiple_violations_all_recorded(self):
        # 完全失败的 spec：无效 dimension + 空 cost + 超长 one_liner
        spec = {
            "dimension": "纯战斗力",
            "cost": "",
            "one_liner": "这是一段很长很长但是没有任何动作和反直觉信号的废话句子",
        }
        r = validate_golden_finger(spec)
        ids = {v.id for v in r.violations}
        # 至少 3 个 GF 群组都有违规
        assert any(i.startswith("GF1") for i in ids)
        assert any(i.startswith("GF2") for i in ids)
        assert any(i.startswith("GF3") for i in ids)
