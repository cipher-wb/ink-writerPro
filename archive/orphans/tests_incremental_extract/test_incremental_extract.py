"""Tests for incremental entity extraction: diff computation, config, savings."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ink_writer.incremental_extract.config import IncrementalExtractConfig, load_config
from ink_writer.incremental_extract.differ import (
    DiffResult,
    DiffType,
    EntityDiff,
    compute_entity_diff,
    _diff_fields,
    _normalize,
)


def _entity(eid: str, etype: str = "character", **kwargs) -> dict:
    return {"entity_id": eid, "entity_type": etype, **kwargs}


class TestIncrementalExtractConfig:
    def test_defaults(self):
        cfg = IncrementalExtractConfig()
        assert cfg.enabled is True
        assert cfg.skip_unchanged_entities is True
        assert cfg.always_extract_protagonist is True

    def test_load_config_missing(self, tmp_path: Path):
        cfg = load_config(tmp_path / "missing.yaml")
        assert cfg.enabled is True

    def test_load_config_from_file(self, tmp_path: Path):
        f = tmp_path / "test.yaml"
        f.write_text(yaml.dump({
            "enabled": False,
            "diff_confidence_threshold": 0.9,
        }))
        cfg = load_config(f)
        assert cfg.enabled is False
        assert cfg.diff_confidence_threshold == 0.9

    def test_load_config_empty(self, tmp_path: Path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        cfg = load_config(f)
        assert cfg.enabled is True


class TestEntityDiff:
    def test_new_entity(self):
        d = EntityDiff("e1", "character", DiffType.NEW, new_values={"name": "张三"})
        assert d.diff_type == DiffType.NEW
        dd = d.to_dict()
        assert dd["diff_type"] == "new"
        assert dd["new_values"]["name"] == "张三"

    def test_unchanged_entity(self):
        d = EntityDiff("e1", "character", DiffType.UNCHANGED)
        dd = d.to_dict()
        assert "changed_fields" not in dd

    def test_changed_entity(self):
        d = EntityDiff(
            "e1", "character", DiffType.CHANGED,
            changed_fields=["location", "status"],
            old_values={"location": "城东"},
            new_values={"location": "城西"},
        )
        assert len(d.changed_fields) == 2
        dd = d.to_dict()
        assert dd["changed_fields"] == ["location", "status"]


class TestDiffResult:
    def test_empty_result(self):
        r = DiffResult(chapter=2, prior_chapter=1)
        assert r.total_entities == 0
        assert r.savings_pct == 0.0

    def test_mixed_result(self):
        r = DiffResult(
            chapter=5, prior_chapter=4,
            new_entities=[EntityDiff("e1", "char", DiffType.NEW)],
            changed_entities=[EntityDiff("e2", "char", DiffType.CHANGED)],
            unchanged_entities=[
                EntityDiff("e3", "char", DiffType.UNCHANGED),
                EntityDiff("e4", "char", DiffType.UNCHANGED),
                EntityDiff("e5", "char", DiffType.UNCHANGED),
            ],
        )
        assert r.total_entities == 5
        assert r.skip_count == 3
        assert r.savings_pct == 60.0
        assert len(r.extraction_needed) == 2

    def test_to_dict(self):
        r = DiffResult(
            chapter=3, prior_chapter=2,
            new_entities=[EntityDiff("e1", "item", DiffType.NEW)],
        )
        d = r.to_dict()
        assert d["chapter"] == 3
        assert d["new"] == 1
        assert d["unchanged"] == 0


class TestComputeEntityDiff:
    def test_all_new(self):
        current = [_entity("e1"), _entity("e2")]
        prior = []
        result = compute_entity_diff(current, prior, 2, 1)
        assert len(result.new_entities) == 2
        assert len(result.unchanged_entities) == 0

    def test_all_unchanged(self):
        entities = [
            _entity("e1", name="张三", location="城东"),
            _entity("e2", name="李四", location="城西"),
        ]
        result = compute_entity_diff(entities, entities, 2, 1)
        assert len(result.unchanged_entities) == 2
        assert len(result.new_entities) == 0
        assert result.savings_pct == 100.0

    def test_changed_field(self):
        prior = [_entity("e1", location="城东")]
        current = [_entity("e1", location="城西")]
        result = compute_entity_diff(current, prior, 2, 1)
        assert len(result.changed_entities) == 1
        assert "location" in result.changed_entities[0].changed_fields

    def test_removed_entity(self):
        prior = [_entity("e1"), _entity("e2")]
        current = [_entity("e1")]
        result = compute_entity_diff(current, prior, 2, 1)
        assert len(result.removed_entities) == 1
        assert result.removed_entities[0].entity_id == "e2"

    def test_protagonist_always_extracted(self):
        entities = [_entity("protagonist", is_protagonist=True, location="山顶")]
        result = compute_entity_diff(entities, entities, 2, 1)
        assert len(result.changed_entities) == 1
        assert result.changed_entities[0].entity_id == "protagonist"

    def test_protagonist_skip_when_disabled(self):
        cfg = IncrementalExtractConfig(always_extract_protagonist=False)
        entities = [_entity("protagonist", is_protagonist=True, location="山顶")]
        result = compute_entity_diff(entities, entities, 2, 1, config=cfg)
        assert len(result.unchanged_entities) == 1

    def test_mixed_scenario(self):
        prior = [
            _entity("e1", name="张三", location="城东"),
            _entity("e2", name="李四", status="active"),
            _entity("e3", name="王五", status="active"),
        ]
        current = [
            _entity("e1", name="张三", location="城东"),
            _entity("e2", name="李四", status="injured"),
            _entity("e4", name="赵六"),
        ]
        result = compute_entity_diff(current, prior, 5, 4)
        assert len(result.unchanged_entities) == 1  # e1
        assert len(result.changed_entities) == 1  # e2
        assert len(result.new_entities) == 1  # e4
        assert len(result.removed_entities) == 1  # e3

    def test_empty_entity_id_skipped(self):
        current = [{"entity_type": "item"}, _entity("e1")]
        result = compute_entity_diff(current, [], 1, 0)
        assert len(result.new_entities) == 1

    def test_savings_60pct_threshold(self):
        """Simulate 20-chapter fixture: most entities unchanged → ≥60% savings."""
        prior = [_entity(f"e{i}", name=f"角色{i}", location="固定") for i in range(20)]
        current = list(prior)
        current.append(_entity("e_new", name="新角色"))
        current[0] = _entity("e0", name="角色0", location="变化了")

        result = compute_entity_diff(current, prior, 10, 9)
        assert result.savings_pct >= 60.0

    def test_diff_vs_full_identical(self):
        """Verify diff extraction covers all entities that full extraction would find."""
        prior = [_entity(f"e{i}", name=f"N{i}") for i in range(10)]
        current = [_entity(f"e{i}", name=f"N{i}") for i in range(10)]
        current[3] = _entity("e3", name="N3", status="changed")
        current.append(_entity("e10", name="N10"))

        result = compute_entity_diff(current, prior, 5, 4)

        all_accounted = (
            len(result.new_entities)
            + len(result.changed_entities)
            + len(result.unchanged_entities)
        )
        assert all_accounted == len(current)
        assert result.extraction_needed[0].entity_id in ("e3", "e10")


class TestNormalize:
    def test_string_strip(self):
        assert _normalize("  hello  ") == "hello"

    def test_none(self):
        assert _normalize(None) is None

    def test_dict_sorted(self):
        assert _normalize({"b": 1, "a": 2}) == _normalize({"a": 2, "b": 1})

    def test_list(self):
        assert _normalize([1, 2, 3]) == _normalize([1, 2, 3])

    def test_number(self):
        assert _normalize(42) == 42


class TestDiffFields:
    def test_no_diff(self):
        prior = {"name": "张三", "location": "城东"}
        current = {"name": "张三", "location": "城东"}
        changed, old, new = _diff_fields(prior, current)
        assert changed == []

    def test_field_changed(self):
        prior = {"name": "张三", "location": "城东"}
        current = {"name": "张三", "location": "城西"}
        changed, old, new = _diff_fields(prior, current)
        assert "location" in changed
        assert old["location"] == "城东"
        assert new["location"] == "城西"

    def test_new_field(self):
        prior = {"name": "张三"}
        current = {"name": "张三", "status": "injured"}
        changed, old, new = _diff_fields(prior, current)
        assert "status" in changed
        assert "status" not in old
        assert new["status"] == "injured"

    def test_skip_fields_ignored(self):
        prior = {"entity_id": "e1", "name": "张三"}
        current = {"entity_id": "e1", "name": "张三"}
        changed, _, _ = _diff_fields(prior, current)
        assert "entity_id" not in changed

    def test_whitespace_normalized(self):
        prior = {"name": "张三 "}
        current = {"name": "张三"}
        changed, _, _ = _diff_fields(prior, current)
        assert changed == []
