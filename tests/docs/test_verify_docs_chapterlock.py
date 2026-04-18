"""v16 US-001：验证 verify_docs.py 的 ChapterLockManager 一致性守卫。

守卫规则：任何 ink-writer/skills/**/SKILL.md 出现
  - "ChapterLockManager 保护"
  - "parallel>1 安全"
这类正向并发安全声明时，必须与 ink_writer/parallel/pipeline_manager.py 的
诚实降级段（"尚未接入"）同步——若 pipeline_manager 仍声明"尚未接入"而
SKILL.md 却声称保护，即为文档-代码漂移，CI 必须 fail。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verify_docs import check_chapter_lock_consistency


def _write_pipeline(pipeline: Path, *, still_not_integrated: bool) -> None:
    """构造一个最小的 pipeline_manager.py 文本。

    still_not_integrated=True 表示其 docstring 仍包含 '尚未接入'（US-002 未完成）。
    """
    if still_not_integrated:
        pipeline.write_text(
            '"""章节级并发管线编排器。\n\n'
            '⚠️ 当前仅 parallel=1 安全。ChapterLockManager 尚未接入（原声明虚假）。\n'
            '"""\n',
            encoding="utf-8",
        )
    else:
        pipeline.write_text(
            '"""章节级并发管线编排器。\n\n'
            'ChapterLockManager 已接入，parallel>1 路径安全。\n'
            '"""\n',
            encoding="utf-8",
        )


def _write_skill(skills_dir: Path, skill_name: str, body: str) -> Path:
    skill_dir = skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture()
def fake_repo(tmp_path: Path) -> tuple[Path, Path]:
    skills = tmp_path / "skills"
    skills.mkdir()
    pipeline = tmp_path / "pipeline_manager.py"
    return skills, pipeline


class TestChapterLockGuard:
    def test_skill_with_false_claim_fails_when_pipeline_not_integrated(
        self, fake_repo: tuple[Path, Path]
    ) -> None:
        skills, pipeline = fake_repo
        _write_pipeline(pipeline, still_not_integrated=True)
        _write_skill(
            skills,
            "ink-auto",
            "---\nname: ink-auto\n---\n\n"
            "实体写入受 SQLite WAL + ChapterLockManager 保护\n",
        )

        findings = check_chapter_lock_consistency(skills, pipeline)
        assert findings, "期待检测到 SKILL.md 与 pipeline_manager.py 漂移"
        assert any(not f.ok for f in findings), "漂移应被标记为 not ok"

    def test_skill_without_claim_passes(self, fake_repo: tuple[Path, Path]) -> None:
        skills, pipeline = fake_repo
        _write_pipeline(pipeline, still_not_integrated=True)
        _write_skill(
            skills,
            "ink-auto",
            "---\nname: ink-auto\n---\n\n"
            "⚠️ 当前仅 parallel=1（串行）安全；parallel>1 未接 ChapterLockManager\n",
        )

        findings = check_chapter_lock_consistency(skills, pipeline)
        assert not findings, f"SKILL.md 未作虚假声明不应触发规则，got={findings}"

    def test_skill_with_claim_passes_when_pipeline_integrated(
        self, fake_repo: tuple[Path, Path]
    ) -> None:
        skills, pipeline = fake_repo
        _write_pipeline(pipeline, still_not_integrated=False)
        _write_skill(
            skills,
            "ink-auto",
            "---\nname: ink-auto\n---\n\n"
            "实体写入受 ChapterLockManager 保护\n",
        )

        findings = check_chapter_lock_consistency(skills, pipeline)
        # 允许报出 finding，但必须全部 ok（即 pipeline 已同步移除 '尚未接入'）。
        assert all(f.ok for f in findings)

    def test_parallel_safety_claim_also_triggers(
        self, fake_repo: tuple[Path, Path]
    ) -> None:
        skills, pipeline = fake_repo
        _write_pipeline(pipeline, still_not_integrated=True)
        _write_skill(
            skills,
            "ink-auto",
            "---\nname: ink-auto\n---\n\n"
            "当前 parallel>1 安全，可放心多开\n",
        )

        findings = check_chapter_lock_consistency(skills, pipeline)
        assert findings and any(not f.ok for f in findings)

    def test_missing_pipeline_or_skills_dir_is_noop(self, tmp_path: Path) -> None:
        findings = check_chapter_lock_consistency(
            tmp_path / "no-skills", tmp_path / "no-pipeline.py"
        )
        assert findings == []


def test_cli_exit_code_nonzero_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直接在真仓库外构造文件的 unit-level 验证已由上方覆盖；
    此测试额外断言 main() 在有漂移时返回非零（通过 monkeypatch 注入假 findings）。"""
    import verify_docs

    fake_finding = verify_docs.Finding("SKILL.md", "claim", "actual", ok=False)
    monkeypatch.setattr(verify_docs, "check_readme_templates", lambda: verify_docs.Finding("r", "c", "a", ok=True))
    monkeypatch.setattr(verify_docs, "check_topology_agents", lambda: verify_docs.Finding("t", "c", "a", ok=True))
    monkeypatch.setattr(verify_docs, "check_architecture_checkers", lambda: None)
    monkeypatch.setattr(verify_docs, "check_chapter_lock_consistency", lambda: [fake_finding])
    monkeypatch.setattr("sys.argv", ["verify_docs.py"])

    rc = verify_docs.main()
    assert rc == 1
