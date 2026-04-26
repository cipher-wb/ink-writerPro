"""tests for ink_writer.rewrite_loop.human_review（US-010）。"""

from __future__ import annotations

import json
from pathlib import Path

from ink_writer.rewrite_loop.human_review import (
    save_rewrite_history,
    write_human_review_record,
)


def test_save_rewrite_history_writes_4_versions(tmp_path: Path) -> None:
    history = [
        "draft r0 — original",
        "draft r1 — after polish 1",
        "draft r2 — after polish 2",
        "draft r3 — after polish 3 (still failing)",
    ]
    paths = save_rewrite_history(
        book="demo-book",
        chapter="ch001",
        history=history,
        base_dir=tmp_path,
    )

    assert len(paths) == 4
    chapters_dir = tmp_path / "data" / "demo-book" / "chapters"
    for i, expected_text in enumerate(history):
        rN = chapters_dir / f"ch001.r{i}.txt"
        assert rN.exists(), f"r{i} 未写盘"
        assert paths[i] == rN
        assert rN.read_text(encoding="utf-8") == expected_text


def test_write_human_review_record_appends_jsonl(tmp_path: Path) -> None:
    rewrite_history_paths = [
        tmp_path / "data" / "demo" / "chapters" / "ch001.r0.txt",
        tmp_path / "data" / "demo" / "chapters" / "ch001.r1.txt",
    ]
    evidence_chain_path = (
        tmp_path / "data" / "demo" / "chapters" / "ch001.evidence.json"
    )

    out_path = write_human_review_record(
        book="demo",
        chapter="ch001",
        blocking_cases=["case-001", {"case_id": "case-002", "severity": "P0"}],
        rewrite_attempts=3,
        rewrite_history_paths=rewrite_history_paths,
        evidence_chain_path=evidence_chain_path,
        base_dir=tmp_path,
    )

    assert out_path == tmp_path / "data" / "demo" / "needs_human_review.jsonl"
    assert out_path.exists()

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["book"] == "demo"
    assert record["chapter"] == "ch001"
    assert record["rewrite_attempts"] == 3
    assert record["blocking_cases"] == [
        "case-001",
        {"case_id": "case-002", "severity": "P0"},
    ]
    assert record["rewrite_history_paths"] == [str(p) for p in rewrite_history_paths]
    assert record["evidence_chain_path"] == str(evidence_chain_path)
    assert "marked_at" in record and record["marked_at"].endswith("Z")


def test_write_human_review_record_single_write_call(tmp_path: Path) -> None:
    """review §三 #3 修复：jsonl record 必须经一次 fh.write 调用写出。

    旧实现 fh.write(json) + fh.write("\n") 两次调用，并发 append 时两个进程
    的 json 与 \\n 可能交错产出 ``<json1><json2>\\n\\n``，整行解析炸。新
    实现合并为单 write —— 用 monkey-patch 拦截 fh.write 计数次数，未来
    若有人改回双 write 立即失败。
    """
    from unittest.mock import patch

    real_open = open
    write_calls: list[str] = []

    class _CountingFh:
        def __init__(self, fh):
            self._fh = fh

        def write(self, s):
            write_calls.append(s)
            return self._fh.write(s)

        def __enter__(self):
            self._fh.__enter__()
            return self

        def __exit__(self, *a):
            return self._fh.__exit__(*a)

    def fake_open(path, *args, **kwargs):
        # 只拦截 needs_human_review.jsonl 的 append 调用；其他文件（mkdir 等
        # 不走 open）正常放行
        if str(path).endswith("needs_human_review.jsonl"):
            return _CountingFh(real_open(path, *args, **kwargs))
        return real_open(path, *args, **kwargs)

    with patch("ink_writer.rewrite_loop.human_review.open", side_effect=fake_open):
        write_human_review_record(
            book="demo",
            chapter="ch001",
            blocking_cases=["case-001"],
            rewrite_attempts=1,
            rewrite_history_paths=[],
            evidence_chain_path=tmp_path / "ev.json",
            base_dir=tmp_path,
        )

    # 关键断言：只调用了 1 次 fh.write，且整行末尾正好 1 个 \n
    assert len(write_calls) == 1, (
        f"expected single fh.write call (atomic JSONL line); got {len(write_calls)}: "
        f"{[s[:40] for s in write_calls]}"
    )
    assert write_calls[0].endswith("\n")
    assert not write_calls[0].endswith("\n\n")


def test_write_human_review_appends_not_overwrites(tmp_path: Path) -> None:
    common = dict(
        book="demo",
        chapter="ch001",
        blocking_cases=["case-001"],
        rewrite_attempts=3,
        rewrite_history_paths=[],
        evidence_chain_path=tmp_path / "evidence.json",
        base_dir=tmp_path,
    )

    write_human_review_record(**common)
    out_path = write_human_review_record(**{**common, "chapter": "ch002"})

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    chapters = [json.loads(line)["chapter"] for line in lines]
    assert chapters == ["ch001", "ch002"]
