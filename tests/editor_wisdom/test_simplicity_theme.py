"""Tests for US-004: editor-wisdom 新增 simplicity 主题域.

Covers:
  - rules.json 含 ≥12 条 category=="simplicity" 规则（PRD AC 门禁）
  - 每条 simplicity 规则必带 id / rule / why / severity / applies_to / source_files
  - applies_to 值在扩展后的 VALID_APPLIES_TO 白名单内
  - config/editor-wisdom.yaml 的 categories 列表含 simplicity
  - EditorWisdomConfig.categories 从 YAML 加载正确
  - EditorWisdomConfig.directness_recall 从 YAML 加载正确
  - writer-injection 在黄金三章 (chapter_no <= 3) 时 simplicity 类 ≥5 条
  - writer-injection 在 scene_mode in {combat, climax, high_point} 时 simplicity 类 ≥5 条
  - writer-injection 在 scene_mode=slow_build / chapter_no=10 时不触发 simplicity 下限
  - 默认 EditorWisdomConfig 含 simplicity category
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from ink_writer.editor_wisdom.config import (
    DirectnessRecall,
    EditorWisdomConfig,
    load_config,
)
from ink_writer.editor_wisdom.retriever import Rule
from ink_writer.editor_wisdom.writer_injection import (
    DIRECTNESS_SCENE_MODES,
    build_writer_constraints,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "data" / "editor-wisdom" / "rules.json"
CONFIG_PATH = REPO_ROOT / "config" / "editor-wisdom.yaml"


# ---------------------------------------------------------------------------
# rules.json 门禁
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def all_rules() -> list[dict]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def simplicity_rules(all_rules: list[dict]) -> list[dict]:
    return [r for r in all_rules if r.get("category") == "simplicity"]


class TestRulesGate:
    def test_at_least_twelve_simplicity_rules(self, simplicity_rules: list[dict]) -> None:
        """PRD AC: 新增 ≥12 条 simplicity 主题域规则."""
        assert len(simplicity_rules) >= 12, (
            f"Expected ≥12 simplicity rules, got {len(simplicity_rules)}"
        )

    def test_every_simplicity_rule_has_required_fields(
        self, simplicity_rules: list[dict]
    ) -> None:
        required = {"id", "category", "rule", "why", "severity", "applies_to", "source_files"}
        for r in simplicity_rules:
            missing = required - r.keys()
            assert not missing, f"Rule {r.get('id')} missing fields: {missing}"
            assert r["category"] == "simplicity"
            assert isinstance(r["rule"], str) and r["rule"].strip()
            assert isinstance(r["why"], str) and r["why"].strip()
            assert r["severity"] in {"hard", "soft", "info"}
            assert isinstance(r["applies_to"], list) and r["applies_to"]
            assert isinstance(r["source_files"], list) and r["source_files"]

    def test_applies_to_values_in_extended_whitelist(
        self, simplicity_rules: list[dict]
    ) -> None:
        """US-004 扩展后的 VALID_APPLIES_TO 必须覆盖所有使用到的值."""
        sys.path.insert(
            0,
            str(REPO_ROOT / "scripts" / "editor-wisdom"),
        )
        from importlib import import_module

        extract_mod = import_module("05_extract_rules")
        valid = extract_mod.VALID_APPLIES_TO
        for scene in ("combat", "climax", "high_point"):
            assert scene in valid, f"{scene} must be in VALID_APPLIES_TO"
        for r in simplicity_rules:
            for v in r["applies_to"]:
                assert v in valid, f"Rule {r['id']} has invalid applies_to={v}"

    def test_simplicity_rules_cover_directness_scenes(
        self, simplicity_rules: list[dict]
    ) -> None:
        """简化规则整体上必须覆盖 golden_three/combat/climax/high_point 四类场景."""
        seen: set[str] = set()
        for r in simplicity_rules:
            seen.update(r["applies_to"])
        for scene in ("golden_three", "combat", "climax", "high_point"):
            assert scene in seen, f"No simplicity rule applies to {scene}"

    def test_rule_ids_unique(self, all_rules: list[dict]) -> None:
        ids = [r["id"] for r in all_rules]
        assert len(ids) == len(set(ids)), "Duplicate rule ids in rules.json"


# ---------------------------------------------------------------------------
# config/editor-wisdom.yaml 主题域注册 + loader
# ---------------------------------------------------------------------------


class TestConfigLoading:
    def test_categories_in_default_config(self) -> None:
        """默认 dataclass 构造就含 simplicity（兜底）."""
        cfg = EditorWisdomConfig()
        assert "simplicity" in cfg.categories

    def test_yaml_categories_includes_simplicity(self) -> None:
        cfg = load_config(CONFIG_PATH)
        assert "simplicity" in cfg.categories
        assert "opening" in cfg.categories  # 原有类别保留

    def test_default_directness_recall(self) -> None:
        cfg = EditorWisdomConfig()
        assert cfg.directness_recall.floor_per_category == 5
        assert "simplicity" in cfg.directness_recall.floor_categories
        assert set(cfg.directness_recall.scene_modes) == {"combat", "climax", "high_point"}

    def test_yaml_directness_recall_loaded(self) -> None:
        cfg = load_config(CONFIG_PATH)
        assert cfg.directness_recall.floor_per_category == 5
        assert "simplicity" in cfg.directness_recall.floor_categories
        assert set(cfg.directness_recall.scene_modes) == {"combat", "climax", "high_point"}

    def test_load_config_missing_directness_recall_uses_defaults(
        self, tmp_path: Path
    ) -> None:
        """旧版 YAML 无 directness_recall 节时 fallback 到默认 DirectnessRecall."""
        stub = tmp_path / "editor-wisdom.yaml"
        stub.write_text(
            "enabled: true\nretrieval_top_k: 3\n",
            encoding="utf-8",
        )
        cfg = load_config(stub)
        assert cfg.directness_recall == DirectnessRecall()

    def test_load_config_malformed_directness_recall_uses_defaults(
        self, tmp_path: Path
    ) -> None:
        stub = tmp_path / "editor-wisdom.yaml"
        stub.write_text(
            "directness_recall:\n  scene_modes: not_a_list\n  floor_per_category: 'abc'\n",
            encoding="utf-8",
        )
        cfg = load_config(stub)
        # scene_modes not a list → default；per_category bad int → default
        assert cfg.directness_recall.scene_modes == DirectnessRecall().scene_modes
        assert cfg.directness_recall.floor_per_category == DirectnessRecall().floor_per_category

    def test_load_config_malformed_categories_uses_defaults(
        self, tmp_path: Path
    ) -> None:
        stub = tmp_path / "editor-wisdom.yaml"
        stub.write_text("categories: not_a_list\n", encoding="utf-8")
        cfg = load_config(stub)
        assert cfg.categories == EditorWisdomConfig().categories


# ---------------------------------------------------------------------------
# writer-injection 场景感知召回
# ---------------------------------------------------------------------------


@dataclass
class MockSceneRetriever:
    """Mock 支持类别过滤 + 查询无关稳定输出。所有调用返回相同排序结果，便于断言."""

    all_rules: list[Rule] = field(default_factory=list)

    def retrieve(
        self, query: str, k: int = 5, category: str | None = None
    ) -> list[Rule]:
        if category is None:
            return list(self.all_rules[:k])
        matches = [r for r in self.all_rules if r.category == category]
        return matches[:k]


def _make_rule(
    rid: str,
    category: str,
    severity: str = "hard",
    applies_to: list[str] | None = None,
) -> Rule:
    return Rule(
        id=rid,
        category=category,
        rule=f"rule-{rid}",
        why=f"why-{rid}",
        severity=severity,
        applies_to=applies_to or ["all_chapters"],
        source_files=[f"{rid}.md"],
        score=0.5,
    )


def _build_mixed_pool() -> list[Rule]:
    """Pool: 1 随机 + 10 simplicity + 3 opening + 3 taboo + 3 hook.

    默认 retrieve(k=5) 返回头 5 条 (1 random + 4 simplicity)，
    categroy="simplicity" retrieve 返回 10 条 simplicity。
    """
    rules: list[Rule] = [_make_rule("R-PACING", "pacing")]
    for i in range(10):
        rules.append(_make_rule(f"S-{i:02d}", "simplicity"))
    for i in range(3):
        rules.append(_make_rule(f"O-{i:02d}", "opening"))
    for i in range(3):
        rules.append(_make_rule(f"T-{i:02d}", "taboo"))
    for i in range(3):
        rules.append(_make_rule(f"H-{i:02d}", "hook"))
    return rules


def _enabled_config(**overrides: object) -> EditorWisdomConfig:
    cfg = EditorWisdomConfig(enabled=True)
    cfg.inject_into.writer = True
    cfg.retrieval_top_k = 5
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


class TestWriterInjectionSceneAwareRecall:
    def test_golden_three_chapter_injects_simplicity_floor(self) -> None:
        """chapter_no=1 时 simplicity 类 ≥5 条（PRD AC）."""
        retriever = MockSceneRetriever(all_rules=_build_mixed_pool())
        cfg = _enabled_config()
        section = build_writer_constraints(
            "对抗与冲突的开场戏",
            chapter_no=1,
            config=cfg,
            retriever=retriever,
        )
        simplicity_ids = {r.id for r in section.rules if r.category == "simplicity"}
        assert len(simplicity_ids) >= 5, (
            f"Expected ≥5 simplicity rules in golden_three, got {len(simplicity_ids)}"
        )

    @pytest.mark.parametrize("scene_mode", sorted(DIRECTNESS_SCENE_MODES))
    def test_directness_scene_mode_injects_simplicity_floor(self, scene_mode: str) -> None:
        retriever = MockSceneRetriever(all_rules=_build_mixed_pool())
        cfg = _enabled_config()
        section = build_writer_constraints(
            "剧情剧烈冲突",
            chapter_no=10,
            config=cfg,
            retriever=retriever,
            scene_mode=scene_mode,
        )
        simplicity_ids = {r.id for r in section.rules if r.category == "simplicity"}
        assert len(simplicity_ids) >= 5, (
            f"Expected ≥5 simplicity rules for scene_mode={scene_mode}, got {len(simplicity_ids)}"
        )

    @pytest.mark.parametrize("scene_mode", ["slow_build", "emotional", "other", None])
    def test_non_directness_scenes_skip_simplicity_floor(
        self, scene_mode: str | None
    ) -> None:
        """非 directness 场景（chapter>3, scene_mode 非 {combat/climax/high_point}) 不触发 simplicity 下限."""
        retriever = MockSceneRetriever(all_rules=_build_mixed_pool())
        cfg = _enabled_config()
        section = build_writer_constraints(
            "抒情铺垫章节",
            chapter_no=10,
            config=cfg,
            retriever=retriever,
            scene_mode=scene_mode,
        )
        # retrieve(k=5) 返回前 5 条 = pacing + 4 simplicity；无下限补召回
        simplicity_ids = {r.id for r in section.rules if r.category == "simplicity"}
        # 只要没补到 5 条，就说明 directness floor 未触发（4 条不等于 0，但 <5 即可）
        assert len(simplicity_ids) < 5, (
            f"Non-directness scenes should not enforce simplicity floor, got {len(simplicity_ids)} rules"
        )

    def test_custom_floor_per_category_respected(self) -> None:
        """config.directness_recall.floor_per_category 支持 override."""
        retriever = MockSceneRetriever(all_rules=_build_mixed_pool())
        cfg = _enabled_config()
        cfg.directness_recall = DirectnessRecall(
            scene_modes=("combat",),
            floor_categories=("simplicity",),
            floor_per_category=8,
        )
        section = build_writer_constraints(
            "激战",
            chapter_no=15,
            config=cfg,
            retriever=retriever,
            scene_mode="combat",
        )
        simplicity_ids = {r.id for r in section.rules if r.category == "simplicity"}
        assert len(simplicity_ids) >= 8

    def test_disabled_config_skips_injection(self) -> None:
        retriever = MockSceneRetriever(all_rules=_build_mixed_pool())
        cfg = EditorWisdomConfig(enabled=False)
        cfg.inject_into.writer = True
        section = build_writer_constraints(
            "章节大纲",
            chapter_no=1,
            config=cfg,
            retriever=retriever,
            scene_mode="combat",
        )
        assert section.empty
