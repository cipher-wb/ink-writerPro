"""tests for write_evidence_chain / save_rewrite_history 原子性（review §二 P1#3）。

手段：
1. 正常写完后目录不留 ``.tmp`` 残骸。
2. mock json.dumps 抛错模拟"序列化失败"，验证目标文件**保持旧内容**而非被截空。
3. mock os.fsync 抛 OSError 模拟 fsync 失败 → 不能让原子写崩，目标文件仍正确。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ink_writer.evidence_chain import EvidenceChain, write_evidence_chain
from ink_writer.rewrite_loop.human_review import save_rewrite_history


def _build_min_evidence(book: str = "TBook", chapter: str = "ch001") -> EvidenceChain:
    return EvidenceChain(book=book, chapter=chapter, dry_run=False, outcome="delivered")


def test_write_evidence_chain_leaves_no_tmp_files_after_success(tmp_path: Path) -> None:
    write_evidence_chain(
        book="A", chapter="ch1", evidence=_build_min_evidence("A", "ch1"), base_dir=tmp_path
    )
    chapters_dir = tmp_path / "A" / "chapters"
    siblings = list(chapters_dir.iterdir())
    # 只能有一个最终 .json，没有任何 .tmp 残留
    assert [p.name for p in siblings] == ["ch1.evidence.json"]


def test_write_evidence_chain_preserves_old_content_on_serialization_failure(
    tmp_path: Path,
) -> None:
    """正常写一次（旧内容）→ 第二次 json.dumps 抛错 → 旧文件原样保留，无半截覆盖。"""
    book, chapter = "A", "ch1"
    target = tmp_path / book / "chapters" / f"{chapter}.evidence.json"

    # 第一次正常写
    write_evidence_chain(
        book=book, chapter=chapter, evidence=_build_min_evidence(book, chapter),
        base_dir=tmp_path,
    )
    old_bytes = target.read_bytes()

    # 第二次：mock json.dumps 抛错
    with patch(
        "ink_writer.evidence_chain.writer.json.dumps",
        side_effect=RuntimeError("simulated serialize fail"),
    ):
        with pytest.raises(RuntimeError, match="simulated serialize fail"):
            write_evidence_chain(
                book=book, chapter=chapter,
                evidence=_build_min_evidence(book, chapter),
                base_dir=tmp_path,
            )

    # 旧内容必须原样保留
    assert target.read_bytes() == old_bytes
    # 也不能留下 .tmp 残骸
    siblings = list((tmp_path / book / "chapters").iterdir())
    assert [p.name for p in siblings] == [f"{chapter}.evidence.json"]


def test_write_evidence_chain_survives_fsync_failure(tmp_path: Path) -> None:
    """mock os.fsync 抛 OSError → 不能影响最终落盘，文件存在且 JSON 可还原。"""
    with patch(
        "ink_writer.evidence_chain.writer.os.fsync", side_effect=OSError("fsync nope")
    ):
        out = write_evidence_chain(
            book="B", chapter="ch2",
            evidence=_build_min_evidence("B", "ch2"), base_dir=tmp_path,
        )
    assert out.exists()
    with open(out, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["book"] == "B"
    assert loaded["chapter"] == "ch2"


def test_save_rewrite_history_writes_4_versions_atomically(tmp_path: Path) -> None:
    history = ["r0 初稿", "r1 第一次重写", "r2 第二次", "r3 最终"]
    paths = save_rewrite_history(
        book="X", chapter="ch5", history=history, base_dir=tmp_path,
    )
    assert len(paths) == 4
    for i, p in enumerate(paths):
        assert p.exists()
        assert p.read_text(encoding="utf-8") == history[i]
    # 目录内只有 4 个 .rN.txt，无任何 .tmp 残骸
    chapters_dir = tmp_path / "data" / "X" / "chapters"
    siblings = sorted(p.name for p in chapters_dir.iterdir())
    assert siblings == ["ch5.r0.txt", "ch5.r1.txt", "ch5.r2.txt", "ch5.r3.txt"]


def test_save_rewrite_history_first_file_preserved_when_second_fails(
    tmp_path: Path,
) -> None:
    """先正常写 r0；再让 r1 写入失败；r0 必须不被损坏，且无 r1.tmp 残骸。"""
    history = ["r0 初稿", "r1 即将失败"]

    real_replace = __import__("os").replace

    def fail_on_r1(src, dst):
        if str(dst).endswith(".r1.txt"):
            raise OSError("simulated replace fail")
        return real_replace(src, dst)

    with patch("ink_writer.rewrite_loop.human_review.os.replace", side_effect=fail_on_r1):
        with pytest.raises(OSError, match="simulated replace fail"):
            save_rewrite_history(
                book="X", chapter="ch5", history=history, base_dir=tmp_path,
            )

    chapters_dir = tmp_path / "data" / "X" / "chapters"
    files = sorted(p.name for p in chapters_dir.iterdir())
    assert files == ["ch5.r0.txt"]
    assert (chapters_dir / "ch5.r0.txt").read_text(encoding="utf-8") == "r0 初稿"
