"""Shared fixtures for live_review tests (US-LR-001+)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def schemas_dir() -> Path:
    return Path(__file__).parents[2] / "schemas"


@pytest.fixture
def load_schema(schemas_dir):
    def _load(name: str) -> dict:
        with open(schemas_dir / name, encoding="utf-8") as f:
            return json.load(f)

    return _load
