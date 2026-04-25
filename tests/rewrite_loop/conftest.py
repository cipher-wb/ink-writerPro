"""rewrite_loop 测试公共 fixture（US-007 起）。"""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_chapter_text() -> str:
    return "第一段：主角站在街口张望。\n第二段：他犹豫了一下，转身离开。\n"


@pytest.fixture
def sample_case() -> dict[str, object]:
    return {
        "case_id": "CASE-DT-0042",
        "failure_description": "都市文主角全章无主动决策，沦为旁观者镜头。",
        "observable": [
            "全章无主动决策动词",
            "对手推进剧情而主角仅反应",
        ],
    }


@pytest.fixture
def sample_chunks() -> list[dict[str, object]]:
    return [
        {
            "chunk_id": "C-LOTUS-0007",
            "text": "他攥紧拳头，掌心沁出薄汗，决定不再等候——直接踏入议事厅。",
        },
        {
            "chunk_id": "C-LOTUS-0023",
            "text": "她推开椅子站起身，扔下一句：'我自己去问。'",
        },
    ]
