"""M5 US-007: tests for EvidenceChain.channel A/B 通道字段。

字段语义：M5 spec §7.4 防过拟合护栏。channel 默认 None（向后兼容），
ink-write CLI --channel A|B 时透传到 evidence_chain.json，方便后续按通道
切片回溯指标。本测试只覆盖 dataclass / to_dict / planning_writer 链路；
config/ab_channels.yaml 的 enabled 切真行为由 M5 之后真实质量验证阶段验。
"""

from __future__ import annotations

import json
from pathlib import Path

from ink_writer.evidence_chain import (
    EvidenceChain,
    write_planning_evidence_chain,
)


def _build_planning_evidence(
    *,
    book: str = "都市A",
    stage: str = "init",
    channel: str | None = None,
    outcome: str = "delivered",
) -> EvidenceChain:
    return EvidenceChain(
        book=book,
        chapter="",  # planning 阶段无 chapter
        phase="planning",
        stage=stage,
        channel=channel,
        outcome=outcome,
        produced_at="2026-04-25T13:00:00+00:00",
    )


def test_channel_default_none() -> None:
    """新建 EvidenceChain 默认 channel=None；to_dict 输出 channel 键。"""
    ev = EvidenceChain(book="都市A", chapter="ch001")
    assert ev.channel is None
    payload = ev.to_dict()
    assert "channel" in payload
    assert payload["channel"] is None


def test_channel_a() -> None:
    """显式 channel='A' 写入后 to_dict 持久化原值。"""
    ev = EvidenceChain(book="都市A", chapter="ch002", channel="A")
    assert ev.channel == "A"
    assert ev.to_dict()["channel"] == "A"


def test_channel_b() -> None:
    """显式 channel='B' 同样持久化。"""
    ev = EvidenceChain(book="都市A", chapter="ch003", channel="B")
    assert ev.to_dict()["channel"] == "B"


def test_planning_evidence_writes_channel(tmp_path: Path) -> None:
    """planning_writer 透传 channel 到 stages[i]：写盘后读回 channel='A'。"""
    ev = _build_planning_evidence(channel="A")

    written = write_planning_evidence_chain(
        book="都市A",
        evidence=ev,
        base_dir=tmp_path,
    )

    assert written.exists()
    with open(written, encoding="utf-8") as fh:
        doc = json.load(fh)

    assert doc["overall_passed"] is True
    assert len(doc["stages"]) == 1
    assert doc["stages"][0]["channel"] == "A"
    assert doc["stages"][0]["stage"] == "init"
