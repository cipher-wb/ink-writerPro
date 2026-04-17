"""静态 fixture 测试：验证 /ink-init --quick 创意基础设施不回退。

覆盖 6 项验收（US-014）：
1. anti-trope-seeds-schema.json 合法（Draft-07）且能校验 anti-trope-seeds.json skeleton
2. meta-creativity-rules.md 至少含 M01-M10 十条规则
3. book-title-patterns.json 7 种修辞标签每种 ≥10 条
4. blacklist.json 含 book_title_suffix_ban / prefix_ban / name_combo_ban 扩展
5. nicknames.json ≥100 条，且含 rarity + style_tags 字段
6. given_names.json 新增 rough / smoky / jianghu 三风格桶
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NAMING_DIR = REPO_ROOT / "data" / "naming"
CREATIVITY_DIR = REPO_ROOT / "ink-writer" / "skills" / "ink-init" / "references" / "creativity"


def _load_json(path: Path) -> dict | list:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# (1) anti-trope-seeds schema + skeleton 合法性
# ---------------------------------------------------------------------------

class TestAntiTropeSeeds:
    def test_schema_is_valid_draft07(self):
        jsonschema = pytest.importorskip("jsonschema")
        schema = _load_json(CREATIVITY_DIR / "anti-trope-seeds-schema.json")
        jsonschema.Draft7Validator.check_schema(schema)

    def test_skeleton_validates_against_schema(self):
        jsonschema = pytest.importorskip("jsonschema")
        schema = _load_json(CREATIVITY_DIR / "anti-trope-seeds-schema.json")
        data = _load_json(CREATIVITY_DIR / "anti-trope-seeds.json")
        jsonschema.validate(data, schema)

    def test_skeleton_has_expected_shape(self):
        data = _load_json(CREATIVITY_DIR / "anti-trope-seeds.json")
        assert isinstance(data, dict)
        assert "seeds" in data and isinstance(data["seeds"], list)
        assert "version" in data
        # skeleton 保持 total=0，Phase-Seed-1 交互补充后递增
        assert data.get("total", 0) == 0


# ---------------------------------------------------------------------------
# (2) meta-creativity-rules.md 至少 M01-M10
# ---------------------------------------------------------------------------

class TestMetaCreativityRules:
    def test_m01_to_m10_all_present(self):
        text = (CREATIVITY_DIR / "meta-creativity-rules.md").read_text(encoding="utf-8")
        found = set(re.findall(r"M(\d{2})", text))
        required = {f"{i:02d}" for i in range(1, 11)}
        missing = required - found
        assert not missing, f"缺失元规则编号：{sorted(missing)}"


# ---------------------------------------------------------------------------
# (3) book-title-patterns.json 7 修辞标签覆盖
# ---------------------------------------------------------------------------

REQUIRED_RHETORIC_TAGS = [
    "pun",
    "homophone",
    "antithesis",
    "irony",
    "oxymoron",
    "concrete_abstract",
    "anachronism",
]


class TestBookTitlePatterns:
    def test_all_seven_rhetoric_tags_covered_at_least_10(self):
        data = _load_json(NAMING_DIR / "book-title-patterns.json")
        counter: Counter[str] = Counter()
        for bucket_key in ("V1", "V2", "V3"):
            bucket = data.get(bucket_key, [])
            assert isinstance(bucket, list) and bucket, f"{bucket_key} 桶应为非空 list"
            for entry in bucket:
                for tag in entry.get("rhetoric_tags", []):
                    counter[tag] += 1
        for tag in REQUIRED_RHETORIC_TAGS:
            assert counter[tag] >= 10, f"修辞标签 {tag} 只出现 {counter[tag]} 次，需 ≥10"

    def test_v1_v2_v3_each_has_at_least_50_patterns(self):
        data = _load_json(NAMING_DIR / "book-title-patterns.json")
        for bucket_key in ("V1", "V2", "V3"):
            assert len(data[bucket_key]) >= 50, f"{bucket_key} 模板不足 50 条"


# ---------------------------------------------------------------------------
# (4) blacklist.json 禁用词扩展
# ---------------------------------------------------------------------------

class TestBlacklistExtensions:
    def test_suffix_ban_has_at_least_15_tokens(self):
        data = _load_json(NAMING_DIR / "blacklist.json")
        tokens = data["book_title_suffix_ban"]["tokens"]
        assert isinstance(tokens, list)
        assert len(tokens) >= 15
        for required in ("神帝", "至尊", "龙傲天", "战神"):
            assert required in tokens, f"后缀黑名单缺失必备词：{required}"

    def test_prefix_ban_has_at_least_10_tokens(self):
        data = _load_json(NAMING_DIR / "blacklist.json")
        tokens = data["book_title_prefix_ban"]["tokens"]
        assert isinstance(tokens, list)
        assert len(tokens) >= 10
        for required in ("我的", "全球", "最强", "重生之"):
            assert required in tokens, f"前缀黑名单缺失必备词：{required}"

    def test_name_combo_ban_surname_suffix_cartesian(self):
        data = _load_json(NAMING_DIR / "blacklist.json")
        combo = data["name_combo_ban"]
        for required in ("萧", "林", "叶", "楚", "顾", "秦", "陆"):
            assert required in combo["surname_tokens"]
        for required in ("尘", "风", "寒", "云", "逸", "辰", "墨", "天"):
            assert required in combo["given_suffix_tokens"]


# ---------------------------------------------------------------------------
# (5) nicknames.json ≥100 条，字段齐全
# ---------------------------------------------------------------------------

class TestNicknames:
    def test_at_least_100_entries(self):
        data = _load_json(NAMING_DIR / "nicknames.json")
        entries = data["nicknames"]
        assert isinstance(entries, list)
        assert len(entries) >= 100

    def test_every_entry_has_rarity_and_style_tags(self):
        data = _load_json(NAMING_DIR / "nicknames.json")
        for entry in data["nicknames"]:
            assert "nickname" in entry and entry["nickname"]
            assert 1 <= entry["rarity"] <= 5
            assert isinstance(entry["style_tags"], list) and entry["style_tags"]


# ---------------------------------------------------------------------------
# (6) given_names.json 新增 rough / smoky / jianghu
# ---------------------------------------------------------------------------

class TestGivenNamesBuckets:
    def test_rough_smoky_jianghu_buckets_exist(self):
        data = _load_json(NAMING_DIR / "given_names.json")
        for bucket in ("rough", "smoky", "jianghu"):
            assert bucket in data, f"given_names 缺失风格桶：{bucket}"
            b = data[bucket]
            assert "male" in b and "female" in b
            # 元字段（以 _ 开头）仅作说明，数据至少要 30+ 条
            assert len(b["male"]) >= 30, f"{bucket}.male 素材少于 30 条"
            assert len(b["female"]) >= 30, f"{bucket}.female 素材少于 30 条"

    def test_style_tag_mapping_declared(self):
        """rough→V1 / smoky→V2 / jianghu→V3 映射通过 _style_tag 元字段声明"""
        data = _load_json(NAMING_DIR / "given_names.json")
        mapping = {"rough": "V1", "smoky": "V2", "jianghu": "V3"}
        for bucket, expected in mapping.items():
            tag = data[bucket].get("_style_tag")
            assert tag == expected, f"{bucket}._style_tag 应为 {expected}，实际 {tag}"
