"""US-005: directness-checker 单元 + 集成测试。

覆盖：
  - 激活条件（scene_mode + chapter_no 组合）
  - 打分曲线（lower_is_better / mid_is_better 两类）
  - 阈值 loader（YAML 缺失 fallback、mtime 缓存、scene 分桶）
  - 端到端 3 段 fixture：直白达标 → Green；修辞堆砌 → Red；空描写泛滥 → Red
  - step3_runner 集成：scene_mode 门控 + adapter 的 (passed, score, fix) 返回
"""

from __future__ import annotations

import asyncio
import sqlite3
import textwrap
from contextlib import closing
from pathlib import Path

import pytest
from ink_writer.prose.directness_checker import (
    ACTIVATION_SCENE_MODES,
    DIMENSION_KEYS,
    GREEN_SCORE,
    RED_SCORE,
    SKIPPED_SCENE_MODES,
    DimensionScore,
    DirectnessIssue,
    DirectnessReport,
    clear_cache,
    is_activated,
    load_thresholds,
    run_directness_check,
    score_dimension,
    to_checker_output,
)

# ---------------------------------------------------------------------------
# Activation gating
# ---------------------------------------------------------------------------


class TestActivation:
    @pytest.mark.parametrize("mode", sorted(ACTIVATION_SCENE_MODES))
    def test_explicit_scene_modes_activate(self, mode: str) -> None:
        assert is_activated(mode, chapter_no=99) is True

    @pytest.mark.parametrize("mode", sorted(SKIPPED_SCENE_MODES))
    def test_all_scene_modes_activate_including_skipped(self, mode: str) -> None:
        """US-006: 全场景激活 — 旧 SKIPPED 也进入。"""
        assert is_activated(mode, chapter_no=99) is True

    @pytest.mark.parametrize("ch", [1, 2, 3])
    def test_chapter_one_to_three_activates_without_scene_mode(self, ch: int) -> None:
        assert is_activated(None, chapter_no=ch) is True

    def test_chapter_beyond_three_also_activates(self) -> None:
        """US-006: 全场景激活 — 旧 [1,3] 门禁已删除。"""
        assert is_activated(None, chapter_no=4) is True
        assert is_activated(None, chapter_no=100) is True

    def test_explicit_scene_mode_always_activates(self) -> None:
        """US-006: 即便 slow_build 在章节 2 也激活。"""
        assert is_activated("slow_build", chapter_no=2) is True


# ---------------------------------------------------------------------------
# Scoring curves
# ---------------------------------------------------------------------------


class TestScoringLowerIsBetter:
    def _thresholds(self) -> dict:
        return {
            "D1_rhetoric_density": {
                "direction": "lower_is_better",
                "green_max": 0.0247,
                "yellow_max": 0.0399,
            }
        }

    def test_value_below_green_max_scores_ten(self) -> None:
        ds = score_dimension("D1_rhetoric_density", 0.0, self._thresholds())
        assert ds.score == 10.0
        assert ds.rating == "green"

    def test_value_at_green_max_scores_ten(self) -> None:
        ds = score_dimension("D1_rhetoric_density", 0.0247, self._thresholds())
        assert ds.score == 10.0

    def test_value_at_yellow_max_scores_six(self) -> None:
        ds = score_dimension("D1_rhetoric_density", 0.0399, self._thresholds())
        assert ds.score == pytest.approx(6.0, abs=0.01)
        assert ds.rating == "yellow"

    def test_value_midway_in_yellow_band_between_eight_and_six(self) -> None:
        mid = (0.0247 + 0.0399) / 2  # → score = 8.0
        ds = score_dimension("D1_rhetoric_density", mid, self._thresholds())
        assert 7.9 <= ds.score <= 8.1

    def test_value_well_beyond_yellow_scores_red(self) -> None:
        ds = score_dimension("D1_rhetoric_density", 0.2, self._thresholds())
        assert ds.score < RED_SCORE
        assert ds.rating == "red"

    def test_score_never_below_zero(self) -> None:
        ds = score_dimension("D1_rhetoric_density", 999.0, self._thresholds())
        assert ds.score == 0.0
        assert ds.rating == "red"


class TestScoringMidIsBetter:
    def _thresholds(self) -> dict:
        return {
            "D4_sent_len_median": {
                "direction": "mid_is_better",
                "green_low": 13.0,
                "green_high": 17.625,
                "yellow_low": 8.375,
                "yellow_high": 22.25,
            }
        }

    @pytest.mark.parametrize("val", [13.0, 15.0, 17.625])
    def test_inside_green_band_scores_ten(self, val: float) -> None:
        ds = score_dimension("D4_sent_len_median", val, self._thresholds())
        assert ds.score == 10.0
        assert ds.rating == "green"

    @pytest.mark.parametrize("val", [8.375, 22.25])
    def test_at_yellow_boundary_scores_six(self, val: float) -> None:
        ds = score_dimension("D4_sent_len_median", val, self._thresholds())
        assert ds.score == pytest.approx(6.0, abs=0.01)

    def test_below_yellow_low_scores_red(self) -> None:
        ds = score_dimension("D4_sent_len_median", 3.0, self._thresholds())
        assert ds.score < RED_SCORE
        assert ds.rating == "red"

    def test_above_yellow_high_scores_red(self) -> None:
        ds = score_dimension("D4_sent_len_median", 60.0, self._thresholds())
        assert ds.score < RED_SCORE


class TestUnknownDirection:
    def test_unknown_direction_falls_back_to_ten(self) -> None:
        ds = score_dimension(
            "D1_rhetoric_density",
            0.1,
            {"D1_rhetoric_density": {"direction": "novel_fantasy"}},
        )
        assert ds.score == 10.0


# ---------------------------------------------------------------------------
# Thresholds loader
# ---------------------------------------------------------------------------


class TestLoadThresholds:
    def setup_method(self) -> None:
        clear_cache()

    def test_missing_file_returns_fallback(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such.yaml"
        thresholds = load_thresholds(missing)
        assert "scenes" in thresholds
        assert "golden_three" in thresholds["scenes"]

    def test_malformed_yaml_returns_fallback(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("::: not yaml :::\n  - [", encoding="utf-8")
        thresholds = load_thresholds(bad)
        assert "scenes" in thresholds
        assert "golden_three" in thresholds["scenes"]

    def test_real_seed_file_loads_with_expected_scenes(self) -> None:
        # 仓内 reports/seed_thresholds.yaml 应至少含 golden_three 与 other
        thresholds = load_thresholds()
        scenes = thresholds.get("scenes", {})
        assert "golden_three" in scenes
        # combat 可能 inherits_from，but key 必须存在
        assert "combat" in scenes or "other" in scenes


# ---------------------------------------------------------------------------
# End-to-end fixtures: Green / Red(rhetoric) / Red(empty)
# ---------------------------------------------------------------------------


_DIRECT_GREEN = textwrap.dedent(
    """
    他推开门，走进屋子，看见桌上摆着三封信。
    "你来了。"老人抬起头，把茶杯推到他面前。
    他拉开椅子，坐下，伸手摸了一下最上面那封信的封口。
    "这封是林老板寄的。"老人慢慢开口，"他说账目对不上。"
    他没有立刻回答。他把信封翻了个面，看了看邮戳的日期。
    "我去一趟苏州。"他站起来，把剑扛上肩，"三天内回来。"
    老人点了点头，从抽屉里取出一袋银子，递过去：
    "路上小心，别惹钱帮的人。"
    """
).strip()


_RHETORIC_RED = textwrap.dedent(
    """
    他如同一座孤山，仿佛在黑夜里伫立，宛如那株恍惚的残梅，犹如不可名状的幽魂。
    风仿佛是哀歌，仿佛是叹息，仿佛是遗忘。
    他是剑，他是心，他是命运。
    她是风，她是雨，她是归宿。
    它是光，它是影，它是轮回。
    命运仿佛难以言喻，仿佛隐隐若现，仿佛莫名其妙，仿佛朦朦胧胧。
    他宛如恍惚地走着，宛如恍惚地笑着，宛如恍惚地叹息。
    空气仿佛凝固，仿佛静止，仿佛消散。
    """
).strip()


_EMPTY_DESC_RED = textwrap.dedent(
    """
    远山连绵，层峦叠嶂，晨雾弥漫在山谷之间，云霞泛着淡淡的金光，飘散在天边。
    林间传来溪水的声响，清脆，绵长，回荡在幽深的山林里，飘散在风中。
    古老的石阶爬满青苔，蜿蜒向上，消失在浓密的松林深处，看不见尽头。
    一阵风吹过，松枝轻摇，松针簌簌落下，铺满整条石阶，厚厚一层。
    远处的庙宇隐在云雾里，屋檐的轮廓若隐若现，钟声隐隐从云端飘来。
    松林深处传来鸟鸣，此起彼伏，一声一声，回荡在山谷间，久久不息。
    """
).strip()


class TestRunDirectnessCheckEndToEnd:
    """端到端：真实 compute_metrics + 真实阈值。

    注：这里依赖 jieba 分词——首次加载 ~200ms，本文件全部用例共享该模型。
    """

    def test_slow_build_runs_after_full_scene_activation(self) -> None:
        """US-006 前 slow_build 不激活；US-006 后全场景激活。"""
        report = run_directness_check(
            _DIRECT_GREEN,
            chapter_no=42,
            scene_mode="slow_build",
        )
        assert not report.skipped
        assert report.passed is True

    def test_direct_prose_is_green_or_yellow(self) -> None:
        """直白达标 fixture 不应出现任何 red 维度。"""
        report = run_directness_check(
            _DIRECT_GREEN,
            chapter_no=1,
            scene_mode="golden_three",
        )
        assert not report.skipped
        assert report.severity in {"green", "yellow"}, (
            f"direct fixture 意外触发 red：{[d.to_dict() for d in report.dimensions]}"
        )
        assert report.passed is True
        # 无 red 维度 → critical 级 issues 必须为空
        criticals = [i for i in report.issues if i.severity == "critical"]
        assert criticals == []

    def test_rhetoric_overload_is_red(self) -> None:
        """修辞堆砌（比喻/排比/抽象词密集）→ D1 或 D3 触发 red。"""
        report = run_directness_check(
            _RHETORIC_RED,
            chapter_no=1,
            scene_mode="golden_three",
        )
        assert not report.skipped
        assert report.severity == "red"
        assert report.passed is False
        red_dims = {d.key for d in report.dimensions if d.rating == "red"}
        assert red_dims & {"D1_rhetoric_density", "D3_abstract_per_100_chars"}, (
            f"rhetoric fixture 未命中 D1/D3：{[d.to_dict() for d in report.dimensions]}"
        )
        # issues 必须附 line_range + excerpt + suggest_rewrite
        assert report.issues
        for issue in report.issues:
            assert issue.line_range[0] >= 1
            assert issue.suggest_rewrite
            assert "excerpt" in issue.evidence

    def test_empty_description_overload_is_red(self) -> None:
        """空描写（纯环境段落，无对话无人物动作）→ D5 触发 red。

        baseline 的 D5 按章级绝对段数计算（green ≤50.5、yellow ≤68.25、red >68.25），
        单份 fixture 仅 6 段不够样本量——repeat 20 次得 120 段纯环境，稳稳越过 red 线。
        """
        repeated = "\n\n".join([_EMPTY_DESC_RED] * 20)
        report = run_directness_check(
            repeated,
            chapter_no=1,
            scene_mode="golden_three",
        )
        assert not report.skipped
        d5 = next(d for d in report.dimensions if d.key == "D5_empty_paragraphs")
        assert d5.rating == "red", (
            f"empty fixture D5 未触发 red：{d5.to_dict()}"
        )
        assert report.severity == "red"
        assert report.passed is False
        # D5 相关 issue 必须出现，并带段级 line_range + excerpt
        d5_issues = [i for i in report.issues if i.dimension == "D5_empty_paragraphs"]
        assert d5_issues, f"D5 red 无对应 issue：{[i.to_dict() for i in report.issues]}"
        for issue in d5_issues:
            assert issue.line_range[0] >= 1
            assert issue.evidence.get("excerpt")


# ---------------------------------------------------------------------------
# Checker output shape
# ---------------------------------------------------------------------------


class TestCheckerOutput:
    def test_skipped_payload(self) -> None:
        report = DirectnessReport(
            skipped=True,
            reason="scene_mode='slow_build' 不激活",
            scene_mode="slow_build",
            chapter_no=42,
            overall_score=0.0,
            passed=True,
            severity="skipped",
            dimensions=(),
            issues=(),
            metrics_raw={},
        )
        out = to_checker_output(report)
        assert out["agent"] == "directness-checker"
        assert out["pass"] is True
        assert out["overall_score"] == 100
        assert out["metrics"]["skipped"] is True

    def test_red_payload_has_issues(self) -> None:
        dims = tuple(
            DimensionScore(key=k, value=0.5, score=4.0, rating="red", direction="lower_is_better")
            for k in DIMENSION_KEYS
        )
        issues = (
            DirectnessIssue(
                id="DIRECTNESS_D1_1",
                dimension="D1_rhetoric_density",
                severity="critical",
                description="desc",
                suggest_rewrite="rewrite",
                line_range=(1, 2),
                evidence={"excerpt": "hello"},
            ),
        )
        report = DirectnessReport(
            skipped=False,
            reason="bucket=golden_three",
            scene_mode="golden_three",
            chapter_no=1,
            overall_score=4.0,
            passed=False,
            severity="red",
            dimensions=dims,
            issues=issues,
            metrics_raw={"char_count": 1000},
        )
        out = to_checker_output(report)
        assert out["pass"] is False
        assert out["overall_score"] == 40
        assert out["issues"][0]["dimension"] == "D1_rhetoric_density"
        assert out["metrics"]["severity"] == "red"


# ---------------------------------------------------------------------------
# step3_runner integration
# ---------------------------------------------------------------------------


def _mk_step3_project(tmp_path: Path, chapter_text: str, chapter_no: int) -> Path:
    project = tmp_path / "book"
    ink_dir = project / ".ink"
    ink_dir.mkdir(parents=True)
    text_dir = project / "正文"
    text_dir.mkdir()
    padded = f"{chapter_no:04d}"
    (text_dir / f"第{padded}章-测试章.md").write_text(chapter_text, encoding="utf-8")
    with closing(sqlite3.connect(str(ink_dir / "index.db"))) as conn:
        conn.execute(
            """
            CREATE TABLE review_metrics (
                start_chapter INTEGER NOT NULL,
                end_chapter INTEGER NOT NULL,
                overall_score REAL DEFAULT 0,
                dimension_scores TEXT,
                severity_counts TEXT,
                critical_issues TEXT,
                report_file TEXT,
                notes TEXT,
                review_payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (start_chapter, end_chapter)
            )
            """
        )
    return project


class TestStep3RunnerDirectnessAdapter:
    def test_directness_gate_runs_on_chapter_without_scene_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """chapter_no=50 且无 scene_mode → 按 other 兜底执行直白评分。"""
        monkeypatch.delenv("INK_STEP3_LLM_CHECKER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _mk_step3_project(tmp_path, _DIRECT_GREEN, chapter_no=50)
        result = asyncio.run(
            run_step3(
                chapter_id=50,
                state_dir=project / ".ink",
                mode="enforce",
                dry_run=True,
            )
        )
        assert result.passed is True
        directness_gate = result.gate_results.get("directness")
        assert directness_gate is not None
        assert directness_gate["status"] == "passed"

    def test_directness_gate_activates_for_golden_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """chapter_no=1 即便无 scene_mode 也应激活直白评分。"""
        monkeypatch.delenv("INK_STEP3_LLM_CHECKER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _mk_step3_project(tmp_path, _RHETORIC_RED * 2, chapter_no=1)
        result = asyncio.run(
            run_step3(
                chapter_id=1,
                state_dir=project / ".ink",
                mode="enforce",
                dry_run=True,
                parallel=10,  # 全并发，防 runner 早停
            )
        )
        directness_gate = result.gate_results.get("directness")
        assert directness_gate is not None
        # 修辞堆砌 → directness 评分应 FAILED；但 is_hard_gate=False，不阻断 passed
        assert directness_gate["status"] == "failed"
        assert directness_gate["is_hard_gate"] is False

    def test_directness_soft_failure_does_not_contribute_to_hard_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """即便 directness FAILED，它也进 soft_fails，不入 hard_fails。"""
        monkeypatch.delenv("INK_STEP3_LLM_CHECKER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _mk_step3_project(tmp_path, _RHETORIC_RED * 2, chapter_no=1)
        result = asyncio.run(
            run_step3(
                chapter_id=1,
                state_dir=project / ".ink",
                mode="enforce",
                dry_run=True,
                parallel=10,
            )
        )
        hard_ids = {f.gate_id for f in result.hard_fails}
        soft_ids = {f.gate_id for f in result.soft_fails}
        assert "directness" not in hard_ids
        if result.gate_results.get("directness", {}).get("status") == "failed":
            assert "directness" in soft_ids


# ---------------------------------------------------------------------------
# Sanity: constants exposed
# ---------------------------------------------------------------------------


class TestExports:
    def test_dimension_keys_stable(self) -> None:
        assert DIMENSION_KEYS == (
            "D1_rhetoric_density",
            "D2_adj_verb_ratio",
            "D3_abstract_per_100_chars",
            "D4_sent_len_median",
            "D5_empty_paragraphs",
            "D6_nesting_depth",
            "D7_modifier_chain_length",
        )

    def test_activation_set_has_four_modes(self) -> None:
        assert frozenset(
            {"golden_three", "combat", "climax", "high_point"}
        ) == ACTIVATION_SCENE_MODES

    def test_score_thresholds_stable(self) -> None:
        assert GREEN_SCORE == 8.0
        assert RED_SCORE == 6.0
