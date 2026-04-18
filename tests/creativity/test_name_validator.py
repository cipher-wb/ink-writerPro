"""v16 US-009：name_validator 单元测试（24 case）。

覆盖 PRD AC 要求：
- 合法书名（PASS）
- 陈词后缀（"林战神"类书名后缀不适用；这里用 "都市 × 战神" 结尾示例）
- 陈词前缀（"我的斗罗大陆"）
- combo 人名组合禁用（"萧尘" 姓+末字）
- male/female 完整黑名单命中
- 空串 / 纯空白
- 非中文/拼音书名通过
- role=side vs main 的 combo soft/hard 差异
- blacklist_path 注入测试
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.creativity.name_validator import (
    Severity,
    ValidationResult,
    validate_book_title,
    validate_character_name,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """每个用例独立加载，避免测试之间缓存污染。"""
    from ink_writer.creativity.name_validator import reset_cache
    reset_cache()
    yield
    reset_cache()


class TestBookTitle:
    # -------- 合法书名 --------
    def test_clean_title_passes(self):
        r = validate_book_title("山风穿门")
        assert r.passed
        assert r.violations == []

    def test_chinese_poetic_title_passes(self):
        r = validate_book_title("一剑问长生")
        assert r.passed

    def test_english_title_passes(self):
        # 拼音/英文书名不误杀
        r = validate_book_title("Le Petit Prince")
        assert r.passed

    # -------- 陈词前缀（hard）--------
    @pytest.mark.parametrize("bad_title", [
        "我的斗罗大陆",
        "全球高武",
        "无敌从吃饭开始",
        "最强反派系统",
        "重生成真千金",
        "重生之都市狂龙",
        "穿越成反派",
        "史上最强师祖",
        "都市最强医仙",
        "校花的贴身高手",
        "美女总裁的至尊保镖",
        "天才少年",
        "绝世武神",
        "超级系统",
    ])
    def test_prefix_ban_blocks(self, bad_title: str):
        r = validate_book_title(bad_title)
        assert not r.passed, f"「{bad_title}」应被前缀黑名单拦截"
        assert any(v.id == "BOOK_TITLE_PREFIX_BAN" for v in r.violations)
        assert r.suggestion, "应给出重抽建议"

    # -------- 陈词后缀（hard）--------
    @pytest.mark.parametrize("bad_title", [
        "都市战神",
        "大陆剑神",
        "青云丹帝",
        "归来仙尊",
        "从零开始的龙傲天",
        "万古无敌",
        "重炼至尊",
        "九天武帝",
        "九州狂龙",
        "无垠霸主",
        "凡人修罗",
    ])
    def test_suffix_ban_blocks(self, bad_title: str):
        r = validate_book_title(bad_title)
        assert not r.passed, f"「{bad_title}」应被后缀黑名单拦截"
        assert any(v.id == "BOOK_TITLE_SUFFIX_BAN" for v in r.violations)

    # -------- 边界 --------
    def test_empty_title_hard_fails(self):
        r = validate_book_title("")
        assert not r.passed
        assert any(v.id == "BOOK_TITLE_EMPTY" for v in r.violations)

    def test_whitespace_only_title_hard_fails(self):
        r = validate_book_title("   \n  ")
        assert not r.passed
        assert any(v.id == "BOOK_TITLE_EMPTY" for v in r.violations)

    def test_both_prefix_and_suffix_ban_recorded(self):
        r = validate_book_title("我的大陆战神")
        assert not r.passed
        ids = {v.id for v in r.violations}
        assert "BOOK_TITLE_PREFIX_BAN" in ids
        assert "BOOK_TITLE_SUFFIX_BAN" in ids

    # -------- 注入 --------
    def test_blacklist_path_injection(self, tmp_path: Path):
        alt = tmp_path / "bl.json"
        alt.write_text(
            json.dumps({
                "book_title_prefix_ban": {"tokens": ["TESTBAD"]},
                "book_title_suffix_ban": {"tokens": []},
            }),
            encoding="utf-8",
        )
        r = validate_book_title("TESTBAD开头", blacklist_path=alt)
        assert not r.passed
        assert r.violations[0].matched_token == "TESTBAD"


class TestCharacterName:
    # -------- 合法名 --------
    def test_non_banned_name_passes(self):
        r = validate_character_name("卫砚之")
        assert r.passed
        assert r.violations == []

    def test_pinyin_name_passes(self):
        r = validate_character_name("Arthur")
        assert r.passed

    # -------- male/female 完整命中 --------
    def test_male_full_match_hard_fails(self):
        r = validate_character_name("叶辰")
        assert not r.passed
        assert any(v.id == "NAME_MALE_BAN" for v in r.violations)

    def test_female_full_match_hard_fails(self):
        r = validate_character_name("苏婉清")
        assert not r.passed
        assert any(v.id == "NAME_FEMALE_BAN" for v in r.violations)

    # -------- combo_ban（surname × given_suffix）--------
    # 使用未列入 male/female 白名单但仍命中 combo 模板的组合
    # （surname_tokens=['萧','林','叶','楚','顾','秦','陆'] ×
    #  given_suffix_tokens=['尘','风','寒','云','逸','辰','墨','天']）。
    def test_combo_ban_main_role_hard(self):
        # "陆云" — 姓 ∈ surname, 末 ∈ given_suffix，但不在 male 黑名单。
        r = validate_character_name("陆云", role="main")
        hard = [v for v in r.violations if v.severity == Severity.HARD]
        assert hard and any(v.id == "NAME_COMBO_BAN" for v in hard)
        assert not r.passed

    def test_combo_ban_side_role_soft(self):
        r = validate_character_name("陆云", role="side")
        # side 角色 combo_ban 降为 soft，passed=True
        assert r.passed is True
        soft = [v for v in r.violations if v.severity == Severity.SOFT]
        assert soft and soft[0].id == "NAME_COMBO_BAN"

    def test_combo_ban_three_char_main_hard(self):
        # "林星辰" — 首 ∈ surname，末 ∈ given_suffix，中间任意。
        r = validate_character_name("林星辰", role="main")
        assert not r.passed
        assert any(v.id == "NAME_COMBO_BAN" for v in r.violations)

    def test_name_not_in_combo_passes(self):
        r = validate_character_name("墨渊山")
        assert r.passed

    # -------- 边界 --------
    def test_empty_name_hard_fails(self):
        r = validate_character_name("")
        assert not r.passed
        assert any(v.id == "NAME_EMPTY" for v in r.violations)

    def test_single_char_name_no_combo_check(self):
        # 单字名无 combo 判定
        r = validate_character_name("萧")
        # "萧" 不在 male/female 名单里 → 应 pass
        assert r.passed

    # -------- 注入 --------
    def test_character_blacklist_injection(self, tmp_path: Path):
        alt = tmp_path / "bl.json"
        alt.write_text(
            json.dumps({
                "male": ["张三"],
                "female": [],
                "name_combo_ban": {
                    "surname_tokens": ["A"],
                    "given_suffix_tokens": ["B"],
                },
            }),
            encoding="utf-8",
        )
        r = validate_character_name("张三", blacklist_path=alt)
        assert not r.passed


class TestValidationResult:
    def test_to_dict_serializable(self):
        r = validate_book_title("我的斗罗大陆")
        d = r.to_dict()
        assert d["passed"] is False
        assert isinstance(d["violations"], list)
        assert d["violations"][0]["severity"] == "hard"
        # 确保完全可 json.dumps
        assert json.dumps(d, ensure_ascii=False)

    def test_hard_and_soft_partition(self):
        # "陆云" 未列入 male 完整黑名单，仅命中 combo → side role 变 soft
        r = validate_character_name("陆云", role="side")
        assert r.hard_violations == []
        assert len(r.soft_violations) == 1
