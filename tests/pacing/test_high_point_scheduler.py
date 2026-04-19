"""Tests for ink_writer.pacing.high_point_scheduler."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest
import yaml

from ink_writer.pacing.high_point_scheduler import (
    HIGH_POINT_TYPES,
    INTENSITY_COMBO,
    INTENSITY_MILESTONE,
    INTENSITY_MINOR,
    HighPointRecord,
    HighPointRecipe,
    SchedulerConfig,
    _base_intensity,
    _chapters_since_intensity,
    _consecutive_no_hp,
    _payoff_window,
    _pick_type,
    _recent_type_counts,
    schedule_high_point,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def default_config() -> SchedulerConfig:
    return SchedulerConfig()


def _make_record(
    chapter: int,
    hp_type: str | None = "face_slap",
    intensity: str = INTENSITY_MINOR,
    had: bool = True,
) -> HighPointRecord:
    return HighPointRecord(
        chapter_no=chapter,
        high_point_type=hp_type,
        intensity=intensity,
        had_high_point=had,
    )


# ── Config tests ────────────────────────────────────────────────────────────

class TestSchedulerConfig:
    def test_defaults(self):
        cfg = SchedulerConfig()
        assert cfg.max_consecutive_no_hp == 2
        assert cfg.combo_window == 5
        assert cfg.milestone_window == 12
        assert cfg.type_repeat_limit == 2
        assert cfg.climax_zone_start == 0.85

    def test_from_yaml(self, tmp_path: Path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml.dump({
            "max_consecutive_no_hp": 3,
            "combo_window": 7,
            "milestone_window": 15,
        }), encoding="utf-8")
        cfg = SchedulerConfig.from_yaml(yaml_path)
        assert cfg.max_consecutive_no_hp == 3
        assert cfg.combo_window == 7
        assert cfg.milestone_window == 15
        assert cfg.type_repeat_limit == 2  # default

    def test_from_yaml_missing_file(self, tmp_path: Path):
        cfg = SchedulerConfig.from_yaml(tmp_path / "nonexistent.yaml")
        assert cfg == SchedulerConfig()

    def test_from_yaml_empty_file(self, tmp_path: Path):
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("", encoding="utf-8")
        cfg = SchedulerConfig.from_yaml(yaml_path)
        assert cfg == SchedulerConfig()


# ── Helper function tests ───────────────────────────────────────────────────

class TestHelpers:
    def test_base_intensity_opening(self, default_config: SchedulerConfig):
        assert _base_intensity(0.05, default_config) == INTENSITY_MINOR

    def test_base_intensity_middle(self, default_config: SchedulerConfig):
        assert _base_intensity(0.5, default_config) == INTENSITY_COMBO

    def test_base_intensity_climax(self, default_config: SchedulerConfig):
        assert _base_intensity(0.9, default_config) == INTENSITY_MILESTONE

    def test_base_intensity_regular(self, default_config: SchedulerConfig):
        assert _base_intensity(0.3, default_config) == INTENSITY_MINOR

    def test_consecutive_no_hp_all_have(self):
        history = [_make_record(i) for i in range(1, 4)]
        assert _consecutive_no_hp(history) == 0

    def test_consecutive_no_hp_trailing_gap(self):
        history = [
            _make_record(1),
            _make_record(2, hp_type=None, had=False),
            _make_record(3, hp_type=None, had=False),
        ]
        assert _consecutive_no_hp(history) == 2

    def test_consecutive_no_hp_gap_then_hp(self):
        history = [
            _make_record(1, hp_type=None, had=False),
            _make_record(2),
            _make_record(3, hp_type=None, had=False),
        ]
        assert _consecutive_no_hp(history) == 1

    def test_consecutive_no_hp_empty(self):
        assert _consecutive_no_hp([]) == 0

    def test_chapters_since_intensity_found(self):
        history = [
            _make_record(1, intensity=INTENSITY_COMBO),
            _make_record(2, intensity=INTENSITY_MINOR),
            _make_record(3, intensity=INTENSITY_MINOR),
        ]
        assert _chapters_since_intensity(history, INTENSITY_COMBO) == 3

    def test_chapters_since_intensity_not_found(self):
        history = [_make_record(i, intensity=INTENSITY_MINOR) for i in range(1, 4)]
        assert _chapters_since_intensity(history, INTENSITY_MILESTONE) is None

    def test_chapters_since_intensity_last_one(self):
        history = [
            _make_record(1, intensity=INTENSITY_MINOR),
            _make_record(2, intensity=INTENSITY_COMBO),
        ]
        assert _chapters_since_intensity(history, INTENSITY_COMBO) == 1

    def test_recent_type_counts(self):
        history = [
            _make_record(1, hp_type="face_slap"),
            _make_record(2, hp_type="face_slap"),
            _make_record(3, hp_type="villain_fail"),
        ]
        counts = _recent_type_counts(history, window=5)
        assert counts["face_slap"] == 2
        assert counts["villain_fail"] == 1

    def test_recent_type_counts_respects_window(self):
        history = [
            _make_record(1, hp_type="face_slap"),
            _make_record(2, hp_type="face_slap"),
            _make_record(3, hp_type="villain_fail"),
            _make_record(4, hp_type="hidden_strength"),
            _make_record(5, hp_type="level_up_kill"),
        ]
        counts = _recent_type_counts(history, window=3)
        assert "face_slap" not in counts
        assert counts.get("villain_fail") == 1

    def test_payoff_window_values(self):
        assert _payoff_window(INTENSITY_MINOR) == 1
        assert _payoff_window(INTENSITY_COMBO) == 2
        assert _payoff_window(INTENSITY_MILESTONE) == 3


# ── Type picker tests ──────────────────────────────────────────────────────

class TestPickType:
    def test_avoids_overused_type(self, default_config: SchedulerConfig):
        history = [
            _make_record(i, hp_type="face_slap") for i in range(1, 4)
        ]
        chosen = _pick_type(history, default_config, 0.5)
        assert chosen != "face_slap"

    def test_prefers_climax_types(self, default_config: SchedulerConfig):
        chosen = _pick_type([], default_config, 0.95)
        assert chosen in ["level_up_kill", "villain_fail", "face_slap"]

    def test_prefers_opening_types(self, default_config: SchedulerConfig):
        chosen = _pick_type([], default_config, 0.05)
        assert chosen in ["hidden_strength", "face_slap", "sweet_surprise"]

    def test_avoids_immediate_repeat(self, default_config: SchedulerConfig):
        history = [_make_record(1, hp_type="face_slap")]
        chosen = _pick_type(history, default_config, 0.3)
        assert chosen != "face_slap"

    def test_always_returns_valid_type(self, default_config: SchedulerConfig):
        history = [
            _make_record(i, hp_type=t) for i, t in enumerate(HIGH_POINT_TYPES * 2)
        ]
        chosen = _pick_type(history, default_config, 0.5)
        assert chosen in HIGH_POINT_TYPES


# ── Main scheduler tests ───────────────────────────────────────────────────

class TestScheduleHighPoint:
    def test_basic_output_schema(self, default_config: SchedulerConfig):
        recipe = schedule_high_point(
            chapter_no=10,
            volume_position=0.3,
            last_5_chapter_high_points=[],
            config=default_config,
        )
        assert isinstance(recipe, HighPointRecipe)
        assert recipe.high_point_type in HIGH_POINT_TYPES
        assert recipe.intensity in (INTENSITY_MINOR, INTENSITY_COMBO, INTENSITY_MILESTONE)
        assert recipe.payoff_window >= 1
        assert isinstance(recipe.require_high_point, bool)
        assert isinstance(recipe.rationale, str)

    def test_dict_input_accepted(self, default_config: SchedulerConfig):
        recipe = schedule_high_point(
            chapter_no=5,
            volume_position=0.2,
            last_5_chapter_high_points=[
                {"chapter_no": 4, "high_point_type": "face_slap",
                 "intensity": "minor", "had_high_point": True},
            ],
            config=default_config,
        )
        assert recipe.high_point_type in HIGH_POINT_TYPES

    def test_forces_hp_after_consecutive_gap(self, default_config: SchedulerConfig):
        history = [
            _make_record(i, hp_type=None, had=False) for i in range(1, 4)
        ]
        recipe = schedule_high_point(
            chapter_no=4,
            volume_position=0.3,
            last_5_chapter_high_points=history,
            config=default_config,
        )
        assert recipe.require_high_point is True
        assert "强制" in recipe.rationale

    def test_climax_gets_milestone(self, default_config: SchedulerConfig):
        recipe = schedule_high_point(
            chapter_no=95,
            volume_position=0.95,
            last_5_chapter_high_points=[],
            config=default_config,
        )
        assert recipe.intensity == INTENSITY_MILESTONE
        assert recipe.payoff_window == 3

    def test_opening_chapter_boost(self, default_config: SchedulerConfig):
        recipe = schedule_high_point(
            chapter_no=1,
            volume_position=0.01,
            last_5_chapter_high_points=[],
            config=default_config,
        )
        assert recipe.intensity in (INTENSITY_COMBO, INTENSITY_MILESTONE)
        assert "黄金" in recipe.rationale or "开篇" in recipe.rationale

    def test_combo_upgrade_when_overdue(self, default_config: SchedulerConfig):
        history = [
            _make_record(i, intensity=INTENSITY_MINOR)
            for i in range(1, 6)
        ]
        recipe = schedule_high_point(
            chapter_no=6,
            volume_position=0.3,
            last_5_chapter_high_points=history,
            config=default_config,
        )
        assert recipe.intensity in (INTENSITY_COMBO, INTENSITY_MILESTONE)

    def test_milestone_upgrade_when_overdue(self, default_config: SchedulerConfig):
        history = [
            _make_record(i, intensity=INTENSITY_MINOR)
            for i in range(1, 6)
        ]
        cfg = SchedulerConfig(milestone_window=3)
        recipe = schedule_high_point(
            chapter_no=6,
            volume_position=0.3,
            last_5_chapter_high_points=history,
            config=cfg,
        )
        assert recipe.intensity == INTENSITY_MILESTONE

    def test_volume_position_clamped(self, default_config: SchedulerConfig):
        recipe_low = schedule_high_point(1, -0.5, [], config=default_config)
        recipe_high = schedule_high_point(1, 1.5, [], config=default_config)
        assert recipe_low.high_point_type in HIGH_POINT_TYPES
        assert recipe_high.high_point_type in HIGH_POINT_TYPES

    def test_empty_history(self, default_config: SchedulerConfig):
        recipe = schedule_high_point(
            chapter_no=10,
            volume_position=0.5,
            last_5_chapter_high_points=[],
            config=default_config,
        )
        assert recipe.require_high_point is True


# ── 50-chapter simulation test ──────────────────────────────────────────────

class TestFiftyChapterSimulation:
    """Simulates 50 consecutive chapters and verifies constraints."""

    @pytest.fixture
    def simulation_results(self) -> list[HighPointRecipe]:
        config = SchedulerConfig()
        total_chapters = 50
        history: list[HighPointRecord] = []
        recipes: list[HighPointRecipe] = []

        for ch in range(1, total_chapters + 1):
            vol_pos = ch / total_chapters
            recent = history[-5:] if history else []

            recipe = schedule_high_point(
                chapter_no=ch,
                volume_position=vol_pos,
                last_5_chapter_high_points=recent,
                config=config,
            )
            recipes.append(recipe)

            history.append(HighPointRecord(
                chapter_no=ch,
                high_point_type=recipe.high_point_type,
                intensity=recipe.intensity,
                had_high_point=recipe.require_high_point,
            ))

        return recipes

    def test_no_three_consecutive_without_hp(
        self, simulation_results: list[HighPointRecipe],
    ):
        consecutive_no_hp = 0
        for recipe in simulation_results:
            if not recipe.require_high_point:
                consecutive_no_hp += 1
            else:
                consecutive_no_hp = 0
            assert consecutive_no_hp < 3, (
                f"Found {consecutive_no_hp} consecutive chapters without "
                f"high-point at chapter around index {simulation_results.index(recipe)}"
            )

    def test_density_variance_within_limit(
        self, simulation_results: list[HighPointRecipe],
    ):
        window = 5
        densities: list[float] = []
        for i in range(0, len(simulation_results), window):
            chunk = simulation_results[i:i + window]
            hp_count = sum(1 for r in chunk if r.require_high_point)
            densities.append(hp_count / len(chunk))

        if len(densities) >= 2:
            var = statistics.variance(densities)
            assert var <= 0.2, (
                f"High-point density variance {var:.3f} exceeds 0.2. "
                f"Densities per window: {densities}"
            )

    def test_type_diversity(self, simulation_results: list[HighPointRecipe]):
        types_used = {r.high_point_type for r in simulation_results}
        assert len(types_used) >= 3, (
            f"Only {len(types_used)} types used in 50 chapters: {types_used}"
        )

    def test_has_combo_and_milestone(
        self, simulation_results: list[HighPointRecipe],
    ):
        intensities = {r.intensity for r in simulation_results}
        assert INTENSITY_COMBO in intensities, "No combo high-point in 50 chapters"
        assert INTENSITY_MILESTONE in intensities, "No milestone high-point in 50 chapters"

    def test_climax_chapters_are_milestone(
        self, simulation_results: list[HighPointRecipe],
    ):
        total = len(simulation_results)
        climax_start = int(total * 0.85)
        for recipe in simulation_results[climax_start:]:
            assert recipe.intensity == INTENSITY_MILESTONE, (
                f"Chapter in climax zone has intensity {recipe.intensity}, "
                f"expected milestone"
            )

    def test_opening_chapters_boosted(
        self, simulation_results: list[HighPointRecipe],
    ):
        for recipe in simulation_results[:3]:
            assert recipe.intensity in (INTENSITY_COMBO, INTENSITY_MILESTONE), (
                f"Opening chapter has intensity {recipe.intensity}, "
                f"expected combo or milestone"
            )

    def test_all_recipes_valid(self, simulation_results: list[HighPointRecipe]):
        for recipe in simulation_results:
            assert recipe.high_point_type in HIGH_POINT_TYPES
            assert recipe.intensity in (
                INTENSITY_MINOR, INTENSITY_COMBO, INTENSITY_MILESTONE,
            )
            assert recipe.payoff_window >= 1
            assert len(recipe.rationale) > 0


# ── Config file integration test ────────────────────────────────────────────

class TestConfigFileIntegration:
    def test_default_config_loads(self):
        cfg = SchedulerConfig.from_yaml()
        assert cfg.max_consecutive_no_hp >= 1

    def test_custom_config_applied(self, tmp_path: Path):
        yaml_path = tmp_path / "custom.yaml"
        yaml_path.write_text(yaml.dump({
            "max_consecutive_no_hp": 1,
            "combo_window": 3,
        }), encoding="utf-8")
        cfg = SchedulerConfig.from_yaml(yaml_path)
        history = [
            _make_record(1, hp_type=None, had=False),
            _make_record(2, hp_type=None, had=False),
        ]
        recipe = schedule_high_point(
            chapter_no=3,
            volume_position=0.3,
            last_5_chapter_high_points=history,
            config=cfg,
        )
        assert recipe.require_high_point is True
        assert "强制" in recipe.rationale
