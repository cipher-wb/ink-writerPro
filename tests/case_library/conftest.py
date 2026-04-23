"""Shared fixtures for case_library tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_case_dict() -> dict:
    """A minimum-valid Case dict matching schemas/case_schema.json."""
    return {
        "case_id": "CASE-2026-0001",
        "title": "主角接到电话 3 秒就不慌，反应不真实",
        "status": "active",
        "severity": "P1",
        "domain": "writing_quality",
        "layer": ["downstream"],
        "tags": ["reader_immersion", "protagonist_reaction"],
        "scope": {
            "genre": ["all"],
            "chapter": ["all"],
        },
        "source": {
            "type": "editor_review",
            "raw_text": "主角接到电话3秒就不慌了",
            "ingested_at": "2026-04-23",
        },
        "failure_pattern": {
            "description": "突发事件→主角理性恢复之间缺情绪缓冲",
            "observable": [
                "突发事件后到理性反应之间字符数 < 200",
            ],
        },
        "bound_assets": {},
        "resolution": {},
        "evidence_links": [],
    }


@pytest.fixture
def tmp_case_dir(tmp_path: Path) -> Path:
    d = tmp_path / "case_library" / "cases"
    d.mkdir(parents=True)
    return d
