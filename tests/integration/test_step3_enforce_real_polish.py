"""v16 US-004 集成测试：enforce 模式 + 违规章节 → polish 修复 → 重查通过。

场景：
- checker 第 1 次返回低分 + hard fail（模拟 LLM 判定违规）；
- polish_fn 被 gate wrapper 调用，mock 返回一个"已修复版本"；
- checker 第 2 次在"已修复版本"上返回高分 + passed=True；
- 预期 run_step3 最终 passed=True（polish 生效）且 polish 审计日志被写入。

这里用 mock 隔离 LLM，不实际调网络；核心验证 US-004 的"retry loop is meaningful"
（AC 描述）——即 polish_fn 的返回值被 gate wrapper 应用并影响重查结果。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


CLEAN_CHAPTER = (
    "山风掠过屋檐。少年把剑扛在肩上，数着脚下的青砖。\n\n"
    "他没有回头。身后那扇木门吱呀作响，却终究合上了。\n\n"
    "远处传来钟声，一声，又一声。他停了停，把剑换到另一边。"
) * 20


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "book"
    ink_dir = project / ".ink"
    ink_dir.mkdir(parents=True)
    text_dir = project / "正文"
    text_dir.mkdir()
    (text_dir / "第0001章-集成测试章.md").write_text(CLEAN_CHAPTER, encoding="utf-8")

    db_path = ink_dir / "index.db"
    with closing(sqlite3.connect(str(db_path))) as conn:
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


class _StatefulChecker:
    """第 1 次返回 fail，第 2 次起返回 pass。模拟 polish 生效后 checker 重查通过。"""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, **kwargs) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return json.dumps({
                "score": 30,
                "violations": [
                    {"id": "HARD_FLAT_CURVE", "severity": "hard", "description": "情绪平坦"}
                ],
                "passed": False,
            })
        return json.dumps({"score": 95, "violations": [], "passed": True})


def _always_fail_call(**kwargs) -> str:
    return json.dumps({
        "score": 30,
        "violations": [
            {"id": "HARD_X", "severity": "hard", "description": "持续 hard fail"}
        ],
        "passed": False,
    })


def _polish_call(**kwargs) -> str:
    """mock LLM polish：返回一个略作改写但总长度接近原文的版本。"""
    user = kwargs.get("user", "")
    # 正文长度接近原文 → 通过 polish 工厂的 length_guard。
    polished = (
        "山风依旧，少年把剑换了位置。他的目光越发坚定。\n\n"
        "心头的火光闪烁了一下，随即平稳下来。脚下的青砖微凉。\n\n"
        "钟声一声一声延续。他终于迈步，步伐不再犹豫。"
    ) * 20
    return polished


class TestStep3EnforceRealPolish:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("INK_STEP3_LLM_CHECKER", "on")
        monkeypatch.setenv("INK_STEP3_LLM_POLISH", "on")

    def test_polish_triggers_and_recovers_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """emotion gate 首查 hard fail → polish 介入 → 次查 pass → 整体 enforce passed=True。"""
        from ink_writer.checker_pipeline import llm_checker_factory, polish_llm_fn
        import ink_writer.checker_pipeline.step3_runner as step3_runner

        # emotion gate 使用"stateful checker"（先 fail 后 pass）；其它 gate 恒 pass。
        # polish 对所有 gate 使用同一 mock（返回已修复文本）。
        stateful = _StatefulChecker()

        original_make_checker = llm_checker_factory.make_llm_checker
        original_make_polish = polish_llm_fn.make_llm_polish

        def fake_make_checker(gate_name: str, prompt_path: Path, **kw):
            if gate_name == "emotion":
                return original_make_checker(gate_name, prompt_path, call_fn=stateful)
            # 其它 gate 返回 pass call_fn
            return original_make_checker(
                gate_name,
                prompt_path,
                call_fn=lambda **kwargs: json.dumps(
                    {"score": 95, "violations": [], "passed": True}
                ),
            )

        def fake_make_polish(gate_name: str, **kw):
            return original_make_polish(gate_name, call_fn=_polish_call, **kw)

        monkeypatch.setattr(step3_runner, "make_llm_checker", fake_make_checker)
        monkeypatch.setattr(step3_runner, "make_llm_polish", fake_make_polish)

        project = _make_project(tmp_path)
        result = asyncio.run(step3_runner.run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="enforce",
            dry_run=True,
            parallel=5,
        ))

        # emotion gate 应恢复 pass（因为 polish 生效 + 二次检查 pass）
        assert result.passed is True, (
            f"期望 polish 修复后 enforce 通过，hard_fails="
            f"{[f.gate_id for f in result.hard_fails]}"
        )
        # checker 被调用至少 2 次（第一次 fail，第二次 pass）
        assert stateful.call_count >= 2, (
            f"期望 stateful checker ≥2 次调用（fail 后 polish 再查），实际 {stateful.call_count}"
        )

        # 审计日志应记录 polish 成功
        audit = project / ".ink" / "reports" / "polish_ch0001_gate_emotion.md"
        assert audit.exists(), "polish 成功应写审计日志"
        content = audit.read_text(encoding="utf-8")
        assert "outcome: success" in content

    def test_polish_cannot_rescue_always_failing_checker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """checker 持续 hard fail + polish 无法修正 → enforce 模式仍阻断。"""
        from ink_writer.checker_pipeline import llm_checker_factory, polish_llm_fn
        import ink_writer.checker_pipeline.step3_runner as step3_runner

        original_make_checker = llm_checker_factory.make_llm_checker
        original_make_polish = polish_llm_fn.make_llm_polish

        def fake_make_checker(gate_name: str, prompt_path: Path, **kw):
            if gate_name == "emotion":
                return original_make_checker(gate_name, prompt_path, call_fn=_always_fail_call)
            return original_make_checker(
                gate_name,
                prompt_path,
                call_fn=lambda **kwargs: json.dumps(
                    {"score": 95, "violations": [], "passed": True}
                ),
            )

        def fake_make_polish(gate_name: str, **kw):
            return original_make_polish(gate_name, call_fn=_polish_call, **kw)

        monkeypatch.setattr(step3_runner, "make_llm_checker", fake_make_checker)
        monkeypatch.setattr(step3_runner, "make_llm_polish", fake_make_polish)

        project = _make_project(tmp_path)
        result = asyncio.run(step3_runner.run_step3(
            chapter_id=1,
            state_dir=project / ".ink",
            mode="enforce",
            dry_run=True,
            parallel=5,
        ))

        # emotion 持续 hard fail → 整体 passed=False
        assert result.passed is False
        assert any(f.gate_id == "emotion" for f in result.hard_fails)
