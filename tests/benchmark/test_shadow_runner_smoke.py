"""US-017 smoke tests — 5-chapter shadow runner (no LLM, no heavy deps).

CI-safe: runs in seconds; asserts ShadowRunner骨架能端到端跑通并产出 metrics/report。
真 300 章由用户手动触发（`python -m benchmark.e2e_shadow_300 --chapters 300`）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.e2e_shadow_300 import (
    DEFAULT_MILESTONES,
    ShadowMetrics,
    ShadowRunner,
    _mock_data_payload,
    _mock_write_chapter,
    _percentile,
    generate_report,
)


class TestMockGeneration:
    def test_mock_chapter_size_in_range(self):
        text = _mock_write_chapter(1)
        # 1-2 KB 正常章节节奏
        assert 1000 <= len(text) <= 3000, f"got {len(text)} chars"
        assert "第1章" in text

    def test_mock_chapter_unique_per_num(self):
        t1 = _mock_write_chapter(1)
        t5 = _mock_write_chapter(5)
        assert "第1章" in t1 and "第5章" in t5

    def test_mock_payload_has_required_fields(self):
        p = _mock_data_payload(3)
        assert p["chapter"] == 3
        assert len(p["entities"]) >= 3
        assert any(e.get("is_protagonist") for e in p["entities"])
        assert len(p["scenes"]) >= 1


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_p50(self):
        # nearest-rank: p50 of 10 items → index 4（第 5 小），值 = 5
        assert _percentile(list(range(1, 11)), 50) == 5.0

    def test_p95(self):
        assert _percentile(list(range(1, 101)), 95) == 95.0


class TestShadowRunnerSmoke:
    """5-chapter end-to-end smoke test（毫秒级，CI 秒级）。"""

    @pytest.fixture
    def runner(self, tmp_path):
        r = ShadowRunner(
            chapters=5,
            project_root=tmp_path,
            milestones=(2, 5),          # smoke 里程碑
            real_retriever=False,       # mock retriever
            retriever_sample_every=1,   # 每章采样便于断言
        )
        yield r
        r.cleanup()

    def test_run_produces_all_metrics(self, runner):
        metrics = runner.run()
        assert metrics.chapters == 5
        # G1
        assert len(metrics.wall_time_per_chapter_s) == 5
        assert all(t >= 0 for t in metrics.wall_time_per_chapter_s)
        assert metrics.g1_mean_s >= 0
        # G2/G3 milestones
        assert len(metrics.milestones) >= 2
        for m in metrics.milestones:
            assert m.state_json_bytes > 0, "state.json 应已写入"
            assert m.index_db_bytes > 0, "index.db 应已写入"
        # G4
        assert len(metrics.context_pack_chars) == 5
        assert metrics.g4_mean_chars > 0
        # G5（每章采样）
        assert len(metrics.retriever_latency_ms) == 5
        assert metrics.g5_p50_ms >= 0
        assert metrics.g5_p95_ms >= metrics.g5_p50_ms

    def test_chapter_files_written(self, runner, tmp_path):
        runner.run()
        chapters_dir = tmp_path / "正文"
        files = sorted(chapters_dir.glob("第*.md"))
        assert len(files) == 5
        for f in files:
            content = f.read_text(encoding="utf-8")
            assert len(content) > 500  # 非空且有内容

    def test_milestones_monotonic_growth(self, runner):
        metrics = runner.run()
        # index.db 应随章节递增（或至少不缩）
        db_sizes = [m.index_db_bytes for m in metrics.milestones]
        assert db_sizes == sorted(db_sizes)

    def test_to_dict_roundtrip_json(self, runner):
        metrics = runner.run()
        d = metrics.to_dict()
        # JSON 可序列化
        s = json.dumps(d, ensure_ascii=False)
        loaded = json.loads(s)
        assert loaded["chapters"] == 5
        assert "g1_wall_time_per_chapter" in loaded
        assert "g2_g3_milestones" in loaded
        assert "g4_context_pack" in loaded
        assert "g5_retriever_latency" in loaded


class TestReportGeneration:
    def test_generate_report_writes_file(self, tmp_path):
        m = ShadowMetrics(chapters=5)
        m.wall_time_per_chapter_s = [0.1, 0.2, 0.15, 0.18, 0.22]
        m.context_pack_chars = [1000, 1100, 1200, 1300, 1400]
        m.retriever_latency_ms = [0.5, 0.6, 0.55, 0.7, 0.65]
        from benchmark.e2e_shadow_300 import MilestoneSample
        m.milestones = [
            MilestoneSample(chapter=2, state_json_bytes=1024, index_db_bytes=2048, wall_time_s_cum=0.3),
            MilestoneSample(chapter=5, state_json_bytes=2048, index_db_bytes=4096, wall_time_s_cum=0.85),
        ]

        report_path = tmp_path / "report.md"
        generate_report(m, report_path, smoke=True)

        text = report_path.read_text(encoding="utf-8")
        assert "300 章 Shadow 压测报告" in text
        assert "SMOKE 模式" in text
        assert "G1" in text and "G2" in text and "G5" in text
        assert "| 2 |" in text  # milestone 章号
        # 真数字 TODO 标注
        assert "真数字" in text or "待人工触发" in text

    def test_generate_report_full_mode(self, tmp_path):
        m = ShadowMetrics(chapters=300)
        from benchmark.e2e_shadow_300 import MilestoneSample
        m.milestones = [MilestoneSample(chapter=300, state_json_bytes=0, index_db_bytes=0, wall_time_s_cum=0)]

        report_path = tmp_path / "report.md"
        generate_report(m, report_path, smoke=False)
        text = report_path.read_text(encoding="utf-8")
        assert "FULL 模式" in text


class TestCLIEntryPoint:
    """CLI smoke: 只检查入口可调用，不真写 reports/ 目录。"""

    def test_main_returns_zero(self, tmp_path):
        from benchmark.e2e_shadow_300 import main
        rc = main([
            "--chapters", "3",
            "--report", str(tmp_path / "r.md"),
            "--metrics-json", str(tmp_path / "m.json"),
        ])
        assert rc == 0
        assert (tmp_path / "r.md").exists()
        assert (tmp_path / "m.json").exists()
        data = json.loads((tmp_path / "m.json").read_text())
        assert data["chapters"] == 3
