#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for migrate.py — lightweight schema migration framework."""

import json

import pytest

from migrate import (
    CURRENT_SCHEMA_VERSION,
    _migrations,
    detect_version,
    migration,
    run_migrations,
)


# ---------------------------------------------------------------------------
# detect_version
# ---------------------------------------------------------------------------


def test_detect_version_with_field():
    assert detect_version({"schema_version": 6}) == 6


def test_detect_version_missing_field_defaults_to_5():
    assert detect_version({}) == 5


# ---------------------------------------------------------------------------
# migration decorator
# ---------------------------------------------------------------------------


def test_migration_decorator_registers_function():
    """The @migration decorator should append to the global _migrations list."""
    original_len = len(_migrations)
    # The module already registers v5 and v6 migrations on import,
    # so just verify they are present and sorted.
    versions = [v for v, _ in _migrations]
    assert versions == sorted(versions)
    assert original_len >= 2  # at least v5->v6 and v6->v7


# ---------------------------------------------------------------------------
# run_migrations — file not found
# ---------------------------------------------------------------------------


def test_run_migrations_file_not_found(tmp_path):
    missing = tmp_path / "state.json"
    with pytest.raises(SystemExit):
        run_migrations(missing)


# ---------------------------------------------------------------------------
# run_migrations — already up to date
# ---------------------------------------------------------------------------


def test_run_migrations_already_current(tmp_path):
    state_file = tmp_path / "state.json"
    state = {"schema_version": CURRENT_SCHEMA_VERSION, "foo": "bar"}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    result = run_migrations(state_file)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION
    assert result["foo"] == "bar"


def test_run_migrations_above_current(tmp_path):
    state_file = tmp_path / "state.json"
    state = {"schema_version": CURRENT_SCHEMA_VERSION + 1}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    result = run_migrations(state_file)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION + 1


# ---------------------------------------------------------------------------
# run_migrations — full migration from v5 to CURRENT
# ---------------------------------------------------------------------------


def test_run_migrations_v5_to_current(tmp_path):
    state_file = tmp_path / "state.json"
    # v5 has no schema_version field
    state = {"chapters": []}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    result = run_migrations(state_file)

    assert result["schema_version"] == CURRENT_SCHEMA_VERSION
    # backup files should exist for each intermediate version
    assert (tmp_path / "state.json.bak.5").exists()
    assert (tmp_path / "state.json.bak.6").exists()
    # result should be written back to disk
    on_disk = json.loads(state_file.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == CURRENT_SCHEMA_VERSION


def test_run_migrations_v6_to_current(tmp_path):
    state_file = tmp_path / "state.json"
    state = {"schema_version": 6}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    result = run_migrations(state_file)

    assert result["schema_version"] == CURRENT_SCHEMA_VERSION
    assert (tmp_path / "state.json.bak.6").exists()
    assert not (tmp_path / "state.json.bak.5").exists()
    # harness_config should be injected by v6->v7 migration
    assert "harness_config" in result
    assert result["harness_config"]["computational_gate_enabled"] is True


# ---------------------------------------------------------------------------
# run_migrations — missing migration function
# ---------------------------------------------------------------------------


def test_run_migrations_missing_migration_func(tmp_path, monkeypatch):
    """If a required migration step is missing, sys.exit(1) is called."""
    state_file = tmp_path / "state.json"
    # Create a state at version 4 — no migration from v4 exists
    state = {"schema_version": 4}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(SystemExit):
        run_migrations(state_file)


# ---------------------------------------------------------------------------
# Individual migration functions
# ---------------------------------------------------------------------------


def test_migrate_v5_to_v6():
    state = {"chapters": [], "title": "test"}
    # find the v5 migration
    func = dict(_migrations)[5]
    result = func(state)
    assert result["schema_version"] == 6
    assert result["title"] == "test"


def test_migrate_v6_to_v7():
    state = {"schema_version": 6}
    func = dict(_migrations)[6]
    result = func(state)
    assert result["schema_version"] == 7
    assert "harness_config" in result
    hc = result["harness_config"]
    assert hc["reader_verdict_mode"] == "core"
    assert hc["reader_verdict_thresholds"]["pass"] == 32
    assert hc["reader_verdict_thresholds"]["enhance"] == 25
    assert hc["reader_verdict_thresholds"]["rewrite_min"] == 0


# ---------------------------------------------------------------------------
# run_migrations — custom migration via monkeypatch
# ---------------------------------------------------------------------------


def test_run_migrations_with_custom_migration(tmp_path, monkeypatch):
    """Verify that run_migrations uses the _migrations registry correctly
    by injecting a custom single-step migration."""
    import migrate

    # Temporarily override CURRENT_SCHEMA_VERSION and _migrations
    monkeypatch.setattr(migrate, "CURRENT_SCHEMA_VERSION", 100)
    original_migrations = migrate._migrations[:]
    monkeypatch.setattr(
        migrate,
        "_migrations",
        [(99, lambda s: {**s, "schema_version": 100, "custom": True})],
    )

    state_file = tmp_path / "state.json"
    state = {"schema_version": 99}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    result = migrate.run_migrations(state_file)
    assert result["schema_version"] == 100
    assert result["custom"] is True
    assert (tmp_path / "state.json.bak.99").exists()

    # Restore (monkeypatch handles _migrations and CURRENT_SCHEMA_VERSION)
