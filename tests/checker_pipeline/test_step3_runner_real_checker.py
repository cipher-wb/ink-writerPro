"""v16 US-003：step3_runner 接入真 LLM checker 的集成测试。

策略
----
真 LLM 调用在 CI 不可行。本测试 monkeypatch ``make_llm_checker``（或其底层
``call_claude``），强制让 reader_pull/emotion/anti_detection/voice 4 个 gate
对"违规章节"返回 hard fail，验证 step3_runner 的 enforce 模式能真正阻断
（≥2 个 gate 返回 passed=False），这即为 US-003 AC "构造违规章节文本…至少
2 个 gate 返回 passed=False" 的可复现 CI 等价验证。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest


_BAD_CHAPTER_TEXT = (
    # 时间标记开头 + 众所周知 AI 套话 + 条目化段落：触发 anti_detection ZT + reader_pull hard。
    "次日清晨，主角睁开眼。众所周知，这是他人生最重要的一天。\n\n"
    "首先，他洗漱；其次，他出门；最后，他去工作。\n\n"
    "不仅如此，而且他还顺便救了只猫。与此同时，天空变黑。"
)


_CLEAN_CHAPTER_TEXT = (
    # 无 ZT 触发词的中性章节文本；留给 pass 路径测试使用。
    "山风掠过屋檐。少年把剑扛在肩上，数着脚下的青砖。\n\n"
    "他没有回头。身后那扇木门吱呀作响，却终究合上了。\n\n"
    "远处传来钟声，一声，又一声。他停了停，把剑换到另一边。"
)


def _make_project(tmp_path: Path, *, bad: bool = True) -> Path:
    project = tmp_path / "book"
    ink_dir = project / ".ink"
    ink_dir.mkdir(parents=True)
    text_dir = project / "正文"
    text_dir.mkdir()
    body = _BAD_CHAPTER_TEXT if bad else _CLEAN_CHAPTER_TEXT
    filename = "第0001章-违规测试章.md" if bad else "第0001章-干净测试章.md"
    (text_dir / filename).write_text(body * 10, encoding="utf-8")

    db_path = ink_dir / "index.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE review_metrics (
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
        """)
    return project


def _fail_call_fn(gate_name: str):
    """返回一个固定输出 hard-fail 的 call_fn（模拟 LLM 判定违规章节）。"""

    def _fn(**kwargs):
        return json.dumps({
            "score": 30,  # <60 典型 hard fail 分段
            "violations": [
                {
                    "id": f"HARD_{gate_name.upper()}_FAKE",
                    "severity": "hard",
                    "location": "整章",
                    "description": "mock: 违规章节被 hard 阻断",
                }
            ],
            "passed": False,
        })

    return _fn


def _pass_call_fn():
    def _fn(**kwargs):
        # 0-100 量纲；95 远超 threshold(70-80)，确保 gate 内部 passed=True。
        return json.dumps({"score": 95, "violations": [], "passed": True})

    return _fn


@pytest.fixture
def force_llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INK_STEP3_LLM_CHECKER", "on")


@pytest.fixture
def patch_factory_to_fail_n_gates(monkeypatch: pytest.MonkeyPatch):
    """Patch make_llm_checker 以便 N 个指定 gate 返回 hard fail，其余 pass。"""

    def _apply(failing_gates: set[str]) -> None:
        import ink_writer.checker_pipeline.step3_runner as step3_runner
        from ink_writer.checker_pipeline import llm_checker_factory

        original = llm_checker_factory.make_llm_checker

        def fake_make(gate_name: str, prompt_path: Path, **kw):
            if gate_name in failing_gates:
                return original(gate_name, prompt_path, call_fn=_fail_call_fn(gate_name))
            return original(gate_name, prompt_path, call_fn=_pass_call_fn())

        # step3_runner 通过 `from ... import make_llm_checker`，需在其命名空间替换。
        monkeypatch.setattr(step3_runner, "make_llm_checker", fake_make)

    return _apply


class TestStep3RunnerRealChecker:
    def test_enforce_mode_blocks_when_two_gates_fail(
        self, tmp_path: Path, force_llm_on, patch_factory_to_fail_n_gates
    ) -> None:
        """US-003 AC：构造违规章节，≥2 个 gate 返回 passed=False，enforce 模式应阻断。

        注意：``CheckerRunner`` 的 early-termination 机制会在任一 hard gate 失败后
        ``cancel_event.set()``，使后续未启动的 gate 标记为 CANCELLED。将 ``parallel``
        调到 >= gate 总数（5），确保所有 gate 都在 FIRST hard fail 之前已 acquire
        semaphore、进入运行态，从而能独立走完并各自记录 hard fail。
        """
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _make_project(tmp_path)
        # 让 anti_detection + reader_pull 两个 gate hard fail
        patch_factory_to_fail_n_gates({"anti_detection", "reader_pull"})

        result = asyncio.run(run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="enforce",
            dry_run=True,
            parallel=5,  # 5 个 gate 全并发，绕过 runner 的早期取消机制
        ))
        # ≥2 个 hard fail
        assert len(result.hard_fails) >= 2, (
            f"预期 ≥2 gate hard fail，实际 {len(result.hard_fails)}："
            f"{[f.gate_id for f in result.hard_fails]}"
        )
        # enforce 模式下 passed=False
        assert result.passed is False
        # 失败 gate_id 应包含两个指定的
        failed_ids = {f.gate_id for f in result.hard_fails}
        assert "anti_detection" in failed_ids
        assert "reader_pull" in failed_ids

    def test_shadow_mode_records_fails_but_passes(
        self, tmp_path: Path, force_llm_on, patch_factory_to_fail_n_gates
    ) -> None:
        """shadow 模式：即使 ≥2 gate fail，passed 仍为 True（US-003 不改变此行为）。"""
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _make_project(tmp_path)
        patch_factory_to_fail_n_gates({"emotion", "voice"})

        result = asyncio.run(run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="shadow",
            dry_run=True,
        ))
        assert result.passed is True  # shadow always pass
        # 但 fails 仍应被记录（hard 或 soft 取决于 gate is_hard_gate 配置）
        total_fails = len(result.hard_fails) + len(result.soft_fails)
        assert total_fails >= 1

    def test_all_gates_pass_enforce_mode_ok(
        self, tmp_path: Path, force_llm_on, patch_factory_to_fail_n_gates
    ) -> None:
        """全 gate（LLM 侧）返回 pass + 章节文本无 ZT 触发 → enforce 通过。"""
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _make_project(tmp_path, bad=False)
        patch_factory_to_fail_n_gates(set())  # 空集合 = 所有都 pass

        result = asyncio.run(run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="enforce",
            dry_run=True,
        ))
        assert result.passed is True, (
            f"期望 enforce 通过，hard_fails={[f.gate_id for f in result.hard_fails]}"
        )
        assert len(result.hard_fails) == 0

    def test_llm_off_env_falls_back_to_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """INK_STEP3_LLM_CHECKER=off → 不调 LLM，走 stub，全 pass（需清洁文本）。"""
        monkeypatch.setenv("INK_STEP3_LLM_CHECKER", "off")
        from ink_writer.checker_pipeline.step3_runner import run_step3

        project = _make_project(tmp_path, bad=False)
        result = asyncio.run(run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="enforce",
            dry_run=True,
        ))
        assert result.passed is True, (
            f"期望 stub 通过，hard_fails={[f.gate_id for f in result.hard_fails]}"
        )
        assert len(result.hard_fails) == 0

    def test_default_no_api_key_uses_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """默认 + 无 ANTHROPIC_API_KEY → 走 stub（CI 安全）。"""
        monkeypatch.delenv("INK_STEP3_LLM_CHECKER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from ink_writer.checker_pipeline.step3_runner import run_step3, _should_use_llm_checker

        assert _should_use_llm_checker() is False
        project = _make_project(tmp_path, bad=False)
        result = asyncio.run(run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="enforce",
            dry_run=True,
        ))
        assert result.passed is True, (
            f"期望 stub 通过，hard_fails={[f.gate_id for f in result.hard_fails]}"
        )
