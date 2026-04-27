"""PRD US-004: colloquial_checker 5 维度白话度评分测试。

3 个端到端 fixture（爆款文 / AI 装逼文 / 严肃文学）+ 单维度算法回归 +
公共 API 边界用例。

AC 重点：
  1. 5 维度结构与 ``DimensionScore`` 字段一致；
  2. 阈值参数化（不硬编码）—— ``thresholds`` 入参可覆盖默认；
  3. C1 用 ≥ 500 词 idiom_dict 检索；
  4. C2 排除成语 + 名字白名单 + 同字四叠；
  5. C3 命中位置返回；
  6. C4 返回均值 + 最长链；
  7. C5 段首句主语为抽象名词的占比；
  8. fixture 方向：爆款 green、AI 装逼 red、严肃 yellow/red。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.prose.colloquial_checker import (
    DIMENSION_KEYS,
    GREEN_SCORE,
    RED_SCORE,
    ColloquialReport,
    DimensionScore,
    _abstract_subject_rate,
    _find_abstract_chains,
    _find_idioms,
    _find_quad_phrases,
    _load_idioms,
    _modifier_chains,
    _subject_is_abstract,
    clear_cache,
    run_colloquial_check,
    score_dimension,
    to_checker_output,
)

# ---------------------------------------------------------------------------
# Module fixtures (autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_cache()


# ---------------------------------------------------------------------------
# Section 1 — 词典加载 & 数量门槛
# ---------------------------------------------------------------------------


class TestIdiomDictionary:
    def test_idiom_dict_loads_at_least_500_entries(self) -> None:
        """PRD AC：``idiom_dict.txt`` ≥ 500 常见成语。"""
        idioms = _load_idioms()
        assert len(idioms) >= 500, f"idiom_dict 仅 {len(idioms)} 条，PRD 要求 ≥ 500"

    def test_idiom_dict_only_contains_4char_han(self) -> None:
        """每条必须为 4 字汉字（非 4 字 / 含 ASCII / 含标点的条目应被 loader 丢弃）。"""
        idioms = _load_idioms()
        for w in idioms:
            assert len(w) == 4, f"非 4 字成语 {w!r} 入库"
            assert all("一" <= ch <= "龥" for ch in w), f"非汉字成语 {w!r} 入库"

    def test_seed_idioms_present(self) -> None:
        """常见 PRD 范畴成语必须落在词典里。"""
        idioms = _load_idioms()
        for seed in ("一帆风顺", "心潮澎湃", "百战百胜", "白驹过隙", "感慨万千"):
            assert seed in idioms, f"种子成语 {seed!r} 缺失"

    def test_loader_handles_missing_file(self, tmp_path: Path) -> None:
        """文件不存在时 loader 返回空集，不抛异常（C1 维度自动 0/kchar → green）。"""
        bogus = tmp_path / "nope.txt"
        idioms = _load_idioms(bogus)
        assert idioms == frozenset()


# ---------------------------------------------------------------------------
# Section 2 — 单维度算法回归
# ---------------------------------------------------------------------------


class TestC1IdiomDensity:
    def test_idiom_match_returns_position_and_word(self) -> None:
        text = "他一帆风顺地完成了任务，又一举两得。"
        idioms = frozenset({"一帆风顺", "一举两得"})
        hits = _find_idioms(text, idioms)
        words = [w for _, w in hits]
        assert "一帆风顺" in words
        assert "一举两得" in words

    def test_no_idioms_in_text_returns_empty(self) -> None:
        idioms = frozenset({"一帆风顺"})
        assert _find_idioms("他踢门进去，吼了一句。", idioms) == []

    def test_empty_idiom_set_returns_empty(self) -> None:
        assert _find_idioms("一帆风顺一举两得", frozenset()) == []


class TestC2QuadPhraseDensity:
    def test_three_consecutive_quads_form_a_stack(self) -> None:
        """≥ 3 连续 4 字格才计入。"""
        text = "群山苍茫，日月星辰，沧海桑田。"
        hits = _find_quad_phrases(text, idiom_set=frozenset(), name_whitelist=frozenset())
        assert len(hits) == 3

    def test_two_consecutive_quads_below_threshold(self) -> None:
        """爆款风偶尔的 2 连 4 字格不计入（动作节奏，非装逼）。"""
        text = "刀风带响。陈风没躲，反手抓住刀背。"
        hits = _find_quad_phrases(text, idiom_set=frozenset(), name_whitelist=frozenset())
        assert hits == []

    def test_idioms_excluded_then_stack_breaks(self) -> None:
        """3 连 4 字格中若 2 个是成语剔除后剩 1 → stack 失效。"""
        idioms = frozenset({"风起云涌", "沧海桑田"})
        text = "风起云涌，沧海桑田，群山苍茫。"
        hits = _find_quad_phrases(text, idiom_set=idioms, name_whitelist=frozenset())
        assert hits == []

    def test_name_whitelist_excludes(self) -> None:
        text = "天地玄黄，日月星辰，沧海桑田，万物归一。"
        names = frozenset({"天地玄黄"})
        hits = _find_quad_phrases(text, idiom_set=frozenset(), name_whitelist=names)
        words = [w for _, w in hits]
        assert "天地玄黄" not in words
        # 剩 3 项仍 ≥ 3 → 仍计入
        assert len(words) == 3

    def test_same_char_quad_excluded(self) -> None:
        """同字四叠（哈哈哈哈）属于象声/语气词，不计入"四字格"。"""
        text = "哈哈哈哈，呵呵呵呵，啊啊啊啊。"
        hits = _find_quad_phrases(text, idiom_set=frozenset(), name_whitelist=frozenset())
        assert hits == []


class TestC3AbstractNounChain:
    def test_three_chained_abstract_nouns(self) -> None:
        text = "宿命的孤寂的沧桑萦绕在他心头。"
        ab = frozenset({"宿命", "孤寂", "沧桑"})
        chains = _find_abstract_chains(text, ab)
        assert len(chains) == 1
        assert chains[0]["snippet"].count("的") == 2  # 3 nouns + 2 of 的

    def test_two_chained_below_threshold(self) -> None:
        text = "宿命的孤寂感涌上心头。"
        ab = frozenset({"宿命", "孤寂"})
        assert _find_abstract_chains(text, ab) == []

    def test_chain_returns_position(self) -> None:
        text = "前略宿命的孤寂的沧桑结尾"
        ab = frozenset({"宿命", "孤寂", "沧桑"})
        chains = _find_abstract_chains(text, ab)
        assert chains[0]["position"] >= 0  # 位置应可定位到链首

    def test_empty_abstract_set_returns_empty(self) -> None:
        assert _find_abstract_chains("宿命的孤寂的沧桑萦绕。", frozenset()) == []


class TestC4ModifierChain:
    def test_long_modifier_chain_detected(self) -> None:
        """坚定的明亮的温暖的目光 → 3 个修饰链"""
        text = "他递来坚定的明亮的温暖的目光。"
        mean, mx, count = _modifier_chains(text)
        assert mx == 3
        assert count == 1
        assert mean == 3.0

    def test_no_modifier_chain_returns_zeros(self) -> None:
        text = "他踹开门，走进去。屋里黑乎乎。"
        mean, mx, count = _modifier_chains(text)
        assert (mean, mx, count) == (0.0, 0, 0)

    def test_single_de_below_threshold(self) -> None:
        """单个'的'是中文底噪，不计入修饰链。"""
        text = "他的手枪。她的眼神。"
        _, _, count = _modifier_chains(text)
        assert count == 0

    def test_mean_aggregates_across_chains(self) -> None:
        text = "坚定的明亮的目光。柔软的温暖的灯光。"
        mean, mx, count = _modifier_chains(text)
        assert count == 2
        assert mx == 2
        assert mean == 2.0


class TestC5AbstractSubjectRate:
    def test_pronoun_subject_not_abstract(self) -> None:
        ab = frozenset({"宿命"})
        assert _subject_is_abstract("他凝视宿命。", ab) is False

    def test_abstract_noun_subject_detected(self) -> None:
        ab = frozenset({"宿命"})
        assert _subject_is_abstract("宿命如尘。", ab) is True

    def test_plural_pronoun_prefix_not_abstract(self) -> None:
        ab = frozenset({"宿命"})
        assert _subject_is_abstract("他们追逐宿命的踪迹。", ab) is False

    def test_rate_aggregates_paragraphs(self) -> None:
        text = "宿命如尘。\n\n他踢开门。\n\n孤寂萦绕。\n\n她笑了。"
        ab = frozenset({"宿命", "孤寂"})
        rate, abs_count, total = _abstract_subject_rate(text, ab)
        assert total == 4
        assert abs_count == 2
        assert rate == 0.5


# ---------------------------------------------------------------------------
# Section 3 — 打分曲线
# ---------------------------------------------------------------------------


class TestScoreDimension:
    def test_lower_is_better_green_at_zero(self) -> None:
        thresholds = {"X": {"direction": "lower_is_better", "green_max": 3.0, "yellow_max": 5.0}}
        ds = score_dimension("X", 0.0, thresholds)
        assert ds.score == 10.0
        assert ds.rating == "green"

    def test_lower_is_better_yellow_in_band(self) -> None:
        thresholds = {"X": {"direction": "lower_is_better", "green_max": 3.0, "yellow_max": 5.0}}
        # 取 yellow 带中段（4.5）；边界 4.0 处恰好 = GREEN_SCORE，会落 green。
        ds = score_dimension("X", 4.5, thresholds)
        assert RED_SCORE <= ds.score < GREEN_SCORE
        assert ds.rating == "yellow"

    def test_lower_is_better_red_above_yellow(self) -> None:
        thresholds = {"X": {"direction": "lower_is_better", "green_max": 3.0, "yellow_max": 5.0}}
        ds = score_dimension("X", 100.0, thresholds)
        assert ds.score < RED_SCORE
        assert ds.rating == "red"

    def test_unknown_metric_falls_back_neutral(self) -> None:
        ds = score_dimension("UNKNOWN_METRIC", 99.0, {})
        assert ds.score == 10.0
        assert ds.rating == "green"


# ---------------------------------------------------------------------------
# Section 4 — End-to-end 三 fixture（PRD AC 主验收）
# ---------------------------------------------------------------------------


# 爆款风：动作驱动、短句、对话 + 第三人称代词主语
BANHUAN_FIXTURE = """陈风一脚踹开木门。

屋里只有三个人。

最右边那个先动。他抽刀就劈，刀风带响。陈风没躲，反手抓住刀背，硬生生掰断。

那人愣了。

陈风一拳砸过去，砸在他鼻梁上。血溅到墙上。

剩下两个对视一眼，转身就跑。

陈风冷笑一声，捡起断刀。

外面天黑了。"""


# AI 装逼文：成语堆叠 + 抽象名词链 + 抽象主语 + 排比四字格
AI_PRETENTIOUS_FIXTURE = """苍茫的暮色笼罩大地，群山苍茫，日月星辰。

孤寂的、宿命的、沧桑的羁绊缠绕在他心头，浮生的、流年的、惆怅的缱绻萦绕不去。

宿命如尘，浮生若梦。万物归于寂静，世间的纷扰仿佛都已远去。这一刻，时间停止了流动，唯有心中那份莫名的怅然挥之不去。风起云涌，沧海桑田。

红尘滚滚，浮生若茶。岁月蹉跎，光阴荏苒。日月如梭，白驹过隙。"""


# 严肃文学：直白动作叙述 + 偶发 1-2 成语作为文学性点缀
SERIOUS_FIXTURE = """父亲在院子里劈柴。这门手艺，他做了三十年。

斧头落下，木屑飞起。他停了一下，擦汗，抡起来再砍。

我站在屋檐下看。十年前他也是这样劈柴，那时我还小，他还有头黑发。日月如梭，如今鬓边斑白，背也微驼。岁月不饶人，他常这么说。

母亲走出来，递给他一碗水。他接过，仰头喝光，抹一下嘴，把碗递回去。

"今年的柴够烧了。" 他说。

母亲笑了笑，没说话。一时间，三人皆是百感交集，谁也没再开口。

风吹过院子里那棵老槐树，叶子沙沙响。

我突然想起，他这一辈子，砍过多少柴。光阴荏苒，他终究老了。"""


class TestEndToEndFixtures:
    """PRD AC：爆款 green、AI 装逼 red、严肃 yellow/red。"""

    def test_banhuan_passes_green(self) -> None:
        report = run_colloquial_check(BANHUAN_FIXTURE)
        assert report["passed"] is True
        assert report["severity"] == "green"
        # 关键维度：装逼词链 / 成语 / 抽象主语都应为 0
        raw = report["metrics_raw"]
        assert raw["C1_idiom_hits_count"] == 0
        assert raw["C3_chain_hits_count"] == 0
        assert raw["C5_abstract_paragraphs"] == 0

    def test_ai_pretentious_blocks_red(self) -> None:
        report = run_colloquial_check(AI_PRETENTIOUS_FIXTURE)
        assert report["passed"] is False
        assert report["severity"] == "red"
        # 至少 3 个维度命中 red（成语 / 四字格排比 / 抽象主语率，C3 取决于词典）
        red_dims = [d for d in report["dimensions"] if d["rating"] == "red"]
        assert len(red_dims) >= 3, f"AI 装逼文应至少 3 维度 red，实测 {len(red_dims)}"
        # 必命中：成语堆叠
        c1 = next(d for d in report["dimensions"] if d["key"] == "C1_idiom_density")
        assert c1["rating"] == "red"

    def test_serious_lands_in_yellow_or_red(self) -> None:
        report = run_colloquial_check(SERIOUS_FIXTURE)
        assert report["severity"] in {"yellow", "red"}, (
            f"严肃文学应为 yellow/red，实测 {report['severity']}"
        )

    def test_relative_ordering_overall_score(self) -> None:
        """爆款 overall_score > 严肃 ≥ AI（直白档下）。"""
        s_banhuan = run_colloquial_check(BANHUAN_FIXTURE)["overall_score"]
        s_serious = run_colloquial_check(SERIOUS_FIXTURE)["overall_score"]
        s_ai = run_colloquial_check(AI_PRETENTIOUS_FIXTURE)["overall_score"]
        assert s_banhuan > s_ai, "爆款分应高于 AI 装逼文"
        assert s_serious >= s_ai, "严肃文学分应不低于 AI 装逼文"


# ---------------------------------------------------------------------------
# Section 5 — 公共 API 边界用例
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_run_returns_required_keys(self) -> None:
        report = run_colloquial_check("正文")
        for key in ("overall_score", "passed", "severity", "dimensions", "metrics_raw"):
            assert key in report, f"返回结构缺 {key!r}"

    def test_dimensions_cover_all_five(self) -> None:
        report = run_colloquial_check("正文")
        keys = {d["key"] for d in report["dimensions"]}
        assert keys == set(DIMENSION_KEYS)

    def test_dimension_score_dataclass_shape(self) -> None:
        ds = DimensionScore(
            key="C1_idiom_density",
            value=0.0,
            score=10.0,
            rating="green",
            direction="lower_is_better",
        )
        d = ds.to_dict()
        assert d == {
            "key": "C1_idiom_density",
            "value": 0.0,
            "score": 10.0,
            "rating": "green",
            "direction": "lower_is_better",
        }

    def test_thresholds_can_be_overridden(self) -> None:
        """阈值参数化：自定义阈值能改变评级方向。"""
        # 极松阈值 → AI 装逼文也能通过
        loose = {
            key: {"direction": "lower_is_better", "green_max": 1e6, "yellow_max": 1e7}
            for key in DIMENSION_KEYS
        }
        report = run_colloquial_check(AI_PRETENTIOUS_FIXTURE, thresholds=loose)
        assert report["severity"] == "green"
        assert report["passed"] is True

    def test_custom_idiom_set_overrides_default(self) -> None:
        """显式传入 idiom_set 覆盖词典文件加载。"""
        report = run_colloquial_check(
            "他一帆风顺，又一举两得。",
            idiom_set=frozenset(),  # 空集合 → 不识别任何成语
        )
        assert report["metrics_raw"]["C1_idiom_hits_count"] == 0

    def test_custom_abstract_nouns_overrides_default(self) -> None:
        """自定义 abstract_nouns 覆盖 prose-blacklist 加载。"""
        text = "孤独的悲伤的绝望萦绕在心头。"
        report = run_colloquial_check(
            text, abstract_nouns=frozenset({"孤独", "悲伤", "绝望"})
        )
        assert report["metrics_raw"]["C3_chain_hits_count"] >= 1

    def test_empty_text_does_not_crash(self) -> None:
        report = run_colloquial_check("")
        assert report["severity"] in {"green", "yellow", "red"}
        assert report["metrics_raw"]["char_count"] == 0

    def test_to_checker_output_shape(self) -> None:
        report = run_colloquial_check(BANHUAN_FIXTURE)
        out = to_checker_output(report, chapter_no=42)
        assert out["agent"] == "colloquial-checker"
        assert out["chapter"] == 42
        assert out["pass"] is True
        assert out["hard_blocked"] is False
        assert "summary" in out

    def test_to_checker_output_hard_blocked_on_red(self) -> None:
        report = run_colloquial_check(AI_PRETENTIOUS_FIXTURE)
        out = to_checker_output(report, chapter_no=1)
        assert out["pass"] is False
        assert out["hard_blocked"] is True

    def test_colloquial_report_dataclass_to_dict(self) -> None:
        cr = ColloquialReport(
            overall_score=8.0,
            passed=True,
            severity="green",
            dimensions=(),
            metrics_raw={"x": 1},
            chain_hits=(),
        )
        d = cr.to_dict()
        assert d["overall_score"] == 8.0
        assert d["passed"] is True
        assert d["severity"] == "green"
        assert d["dimensions"] == []
        assert d["metrics_raw"] == {"x": 1}
        assert d["chain_hits"] == []


# ---------------------------------------------------------------------------
# Section 6 — 缓存隔离
# ---------------------------------------------------------------------------


class TestCacheBehaviour:
    def test_clear_cache_drops_idiom_set(self, tmp_path: Path) -> None:
        from ink_writer.prose import colloquial_checker as cc

        custom = tmp_path / "idioms.txt"
        custom.write_text("一帆风顺\n", encoding="utf-8")
        s1 = cc._load_idioms(custom)
        assert "一帆风顺" in s1
        custom.write_text("百战百胜\n", encoding="utf-8")
        cc.clear_cache()
        s2 = cc._load_idioms(custom)
        assert "百战百胜" in s2
        assert "一帆风顺" not in s2

    def test_cache_key_uses_mtime_for_invalidation(self, tmp_path: Path) -> None:
        from ink_writer.prose import colloquial_checker as cc

        custom = tmp_path / "idioms.txt"
        custom.write_text("一帆风顺\n", encoding="utf-8")
        s1 = cc._load_idioms(custom)
        # 同一文件 + 同一 mtime → 命中缓存
        s2 = cc._load_idioms(custom)
        assert s1 is s2  # frozenset identity preserved by cache
