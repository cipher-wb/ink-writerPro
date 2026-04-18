"""US-018 (FIX-17 P4e): propagation 全链路端到端集成测试。

场景：30 章 mock 项目
- 第 5 章定设：师父是张三
- 第 25 章被 continuity-checker 发现矛盾（师父名字与前文冲突，target=5）
- 触发 macro-review（current_chapter=30, interval=30）→ drift_detector 应捕获 1 条
- 该 debt 持久化到 .ink/propagation_debt.json
- ink-plan（规划第 31 章起的新卷）：
  * load_active_debts → 取回 1 条未关闭 debt
  * render_debts_for_plan → markdown 含该 debt（硬约束注入）
  * filter_debts_for_range([1,10]) → 命中（target_chapter=5）
- 模拟 plan 消化：mark_debts_resolved([debt_id]) → 重新加载后 status='resolved'
"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.propagation import (
    DebtStore,
    filter_debts_for_range,
    load_active_debts,
    mark_debts_resolved,
    render_debts_for_plan,
    run_propagation,
    should_run,
)


pytestmark = pytest.mark.integration


CONFLICT_RULE = "character.master_name"
CONFLICT_FIX = "回到第 5 章确认师父姓名，与第 25 章保持一致"


def _create_review_metrics_table(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_metrics (
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
        conn.commit()
    finally:
        conn.close()


def _seed_30_chapters_with_conflict(db_path: Path) -> None:
    """30 章均为 clean review；仅第 25 章 continuity-checker 触发 cross_chapter_conflict → target=5。"""
    conn = sqlite3.connect(str(db_path))
    try:
        for ch in range(1, 31):
            if ch == 25:
                # 只由 continuity-checker 上报（未冒泡到 critical_issues），
                # 测试 drift_detector 能从 checker_results 单一来源精准捕获 1 条
                critical = []
                payload = {
                    "checker_results": {
                        "continuity-checker": {
                            "violations": [
                                {
                                    "type": "cross_chapter_conflict",
                                    "target_chapter": 5,
                                    "severity": "high",
                                    "rule": CONFLICT_RULE,
                                    "message": "第 25 章称师父为李四，与第 5 章‘张三’矛盾",
                                    "suggested_fix": CONFLICT_FIX,
                                }
                            ]
                        }
                    }
                }
            else:
                critical = []
                payload = {"checker_results": {}}
            conn.execute(
                """
                INSERT INTO review_metrics (
                    start_chapter, end_chapter, overall_score,
                    critical_issues, review_payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ch,
                    ch,
                    85.0,
                    json.dumps(critical, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def mock_project(tmp_path: Path) -> Path:
    db_path = tmp_path / ".ink" / "index.db"
    _create_review_metrics_table(db_path)
    _seed_30_chapters_with_conflict(db_path)
    return tmp_path


def test_propagation_e2e_detects_drift_persists_and_consumes(mock_project: Path):
    # --- 0. 触发门禁：current=30, interval=30 → should_run=True ---
    assert should_run(30, env={"INK_PROPAGATION_INTERVAL": "30"}) is True

    # --- 1. macro-review 触发 run_propagation：读取真实 DB ---
    stderr = io.StringIO()
    drifts = run_propagation(
        mock_project,
        current_chapter=30,
        env={"INK_PROPAGATION_INTERVAL": "30"},
        stderr=stderr,
    )

    # 精确命中：1 条 drift，target=5, chapter_detected=25
    assert len(drifts) == 1, f"expected 1 drift, got {len(drifts)}: {drifts}"
    (drift,) = drifts
    assert drift.chapter_detected == 25
    assert drift.target_chapter == 5
    assert drift.severity == "high"
    assert drift.status == "open"
    assert CONFLICT_RULE in drift.rule_violation
    assert "Propagation: 1 drifts detected" in stderr.getvalue()

    # --- 2. 落盘：propagation_debt.json 存在且包含该 debt ---
    debt_file = mock_project / ".ink" / "propagation_debt.json"
    assert debt_file.exists()
    payload = json.loads(debt_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["target_chapter"] == 5
    assert payload["items"][0]["status"] == "open"

    # --- 3. ink-plan 消费：硬约束渲染 + 区间过滤 ---
    active = load_active_debts(mock_project)
    assert len(active) == 1
    assert active[0].debt_id == drift.debt_id

    rendered = render_debts_for_plan(active)
    assert "待消化的反向传播债务" in rendered
    assert drift.debt_id in rendered
    assert "target_ch=5" in rendered
    assert CONFLICT_RULE in rendered

    # 规划新卷第 31-60 章：target=5 不在该区间
    out_of_range = filter_debts_for_range(active, 31, 60)
    assert out_of_range == []
    # 若 planner 重规划 1-10 章段：命中
    in_range = filter_debts_for_range(active, 1, 10)
    assert len(in_range) == 1
    assert in_range[0].target_chapter == 5

    # --- 4. 模拟 plan 消化：mark_debts_resolved ---
    changed = mark_debts_resolved(mock_project, [drift.debt_id])
    assert changed == [drift.debt_id]

    # 重新加载验证 status='resolved'
    reloaded = DebtStore(project_root=mock_project).load()
    assert len(reloaded.items) == 1
    assert reloaded.items[0].status == "resolved"

    # active 列表应为空（resolved 不再 active）
    assert load_active_debts(mock_project) == []

    # 幂等：再次 mark_debts_resolved 不应报错且返回空
    assert mark_debts_resolved(mock_project, [drift.debt_id]) == []


def test_propagation_e2e_no_conflict_project_yields_empty(tmp_path: Path):
    """零回归：30 章全部 clean → 不产生 drift、不建文件。"""
    db_path = tmp_path / ".ink" / "index.db"
    _create_review_metrics_table(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        for ch in range(1, 31):
            conn.execute(
                """
                INSERT INTO review_metrics (
                    start_chapter, end_chapter, overall_score,
                    critical_issues, review_payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (ch, ch, 90.0, "[]", json.dumps({"checker_results": {}})),
            )
        conn.commit()
    finally:
        conn.close()

    stderr = io.StringIO()
    drifts = run_propagation(
        tmp_path,
        current_chapter=30,
        env={"INK_PROPAGATION_INTERVAL": "30"},
        stderr=stderr,
    )
    assert drifts == []
    assert "Propagation: 0 drifts detected" in stderr.getvalue()
    assert not (tmp_path / ".ink" / "propagation_debt.json").exists()
    assert load_active_debts(tmp_path) == []
