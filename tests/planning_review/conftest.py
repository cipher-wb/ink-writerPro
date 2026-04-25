"""M4 planning_review 共享 fixtures。"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.evidence_chain import EvidenceChain


@pytest.fixture
def planning_base_dir(tmp_path: Path) -> Path:
    """每个测试独立的 base_dir，避免状态污染。"""
    return tmp_path


@pytest.fixture
def sample_planning_evidence_init() -> EvidenceChain:
    """ink-init 阶段的示例 EvidenceChain（4 个 checker 全过）。"""
    ev = EvidenceChain(
        book="test-book",
        chapter="",
        phase="planning",
        stage="ink-init",
        produced_at="2026-04-25T10:00:00+00:00",
        outcome="passed",
    )
    ev.record_checkers(
        [
            {"id": "genre-novelty", "score": 0.72, "blocked": False, "cases_hit": []},
            {
                "id": "golden-finger-spec",
                "score": 0.81,
                "blocked": False,
                "cases_hit": [],
            },
            {"id": "naming-style", "score": 0.92, "blocked": False, "cases_hit": []},
            {
                "id": "protagonist-motive",
                "score": 0.75,
                "blocked": False,
                "cases_hit": [],
            },
        ]
    )
    return ev
