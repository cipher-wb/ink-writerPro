"""US-020 (FIX-18 P5b): data-agent 规格声明 progression_events 输出契约的元测试。

由于 data-agent 是 Claude Skill agent（Markdown 规格 + LLM 执行），无 Python 实现可直接调用，
本测试通过两层验证守住契约：
1. 规格层：data-agent.md 必须包含 Step B.7.6 节、6 维度 enum、字段说明
2. 数据层：mock 一份 data-agent JSON 输出，断言字段齐全 / dimension 合法 / 空数组允许
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_AGENT_SPEC = REPO_ROOT / "ink-writer" / "agents" / "data-agent.md"

ALLOWED_DIMENSIONS = {"立场", "关系", "境界", "知识", "情绪", "目标"}
REQUIRED_EVENT_FIELDS = {"character_id", "dimension"}  # to 必填但 from/cause 可选
ALL_EVENT_FIELDS = {"character_id", "dimension", "from", "to", "cause"}


# ───────────────────── 规格层断言 ─────────────────────

@pytest.fixture(scope="module")
def spec_text() -> str:
    assert DATA_AGENT_SPEC.exists(), f"data-agent 规格缺失：{DATA_AGENT_SPEC}"
    return DATA_AGENT_SPEC.read_text(encoding="utf-8")


def test_spec_declares_progression_events_section(spec_text: str) -> None:
    assert "progression_events" in spec_text, "规格未提及 progression_events"
    assert "Step B.7.6" in spec_text or "角色演进切片" in spec_text, \
        "规格缺少 Step B.7.6 角色演进切片章节"


def test_spec_declares_six_dimensions(spec_text: str) -> None:
    for dim in ALLOWED_DIMENSIONS:
        assert dim in spec_text, f"规格未声明 dimension 枚举值：{dim}"


def test_spec_declares_empty_array_when_no_change(spec_text: str) -> None:
    # 规格必须明确说明无变化时输出 []
    assert "progression_events" in spec_text and "[]" in spec_text, \
        "规格缺少无变化时输出空数组的说明"


def test_spec_declares_field_schema(spec_text: str) -> None:
    # 字段说明段落要点必须出现
    for token in ("character_id", "dimension", "from", "to", "cause"):
        assert token in spec_text, f"规格字段说明缺少 {token}"


# ───────────────────── 数据层断言（mock JSON） ─────────────────────

def _mock_data_agent_output(events: list[dict]) -> dict:
    """模拟 data-agent 一次完整输出，仅关注 progression_events 字段。"""
    return {
        "entities_appeared": [],
        "entities_new": [],
        "state_changes": [],
        "relationships_new": [],
        "scenes_chunked": 0,
        "progression_events": events,
        "uncertain": [],
        "warnings": [],
    }


def _validate_progression_events(payload: dict) -> None:
    """契约校验：可被 Step 5 解析端复用的最小规则集。"""
    assert "progression_events" in payload, "缺少 progression_events 字段"
    events = payload["progression_events"]
    assert isinstance(events, list), "progression_events 必须为数组"
    for i, ev in enumerate(events):
        assert isinstance(ev, dict), f"事件 {i} 非对象"
        missing = REQUIRED_EVENT_FIELDS - ev.keys()
        assert not missing, f"事件 {i} 缺必填字段：{missing}"
        assert ev["dimension"] in ALLOWED_DIMENSIONS, \
            f"事件 {i} dimension 非法：{ev['dimension']}（允许 {ALLOWED_DIMENSIONS}）"
        # to 是核心目标值，必须存在
        assert "to" in ev and ev["to"], f"事件 {i} 缺 to 值"
        # 不允许出现 schema 外字段
        unknown = ev.keys() - ALL_EVENT_FIELDS
        assert not unknown, f"事件 {i} 含未知字段：{unknown}"


def test_mock_output_full_event_passes() -> None:
    payload = _mock_data_agent_output([
        {
            "character_id": "xiaoyan",
            "dimension": "境界",
            "from": "斗者",
            "to": "斗师",
            "cause": "突破",
        }
    ])
    _validate_progression_events(payload)


def test_mock_output_minimal_event_passes() -> None:
    # from / cause 可省略
    payload = _mock_data_agent_output([
        {"character_id": "char_a", "dimension": "目标", "to": "保护妹妹"}
    ])
    _validate_progression_events(payload)


def test_mock_output_empty_array_allowed() -> None:
    payload = _mock_data_agent_output([])
    _validate_progression_events(payload)


def test_mock_output_all_six_dimensions_round_trip() -> None:
    events = [
        {"character_id": f"c_{dim}", "dimension": dim, "to": "v"}
        for dim in ALLOWED_DIMENSIONS
    ]
    payload = _mock_data_agent_output(events)
    _validate_progression_events(payload)


def test_mock_output_invalid_dimension_rejected() -> None:
    payload = _mock_data_agent_output([
        {"character_id": "x", "dimension": "power_level", "to": "v"}
    ])
    with pytest.raises(AssertionError, match="dimension 非法"):
        _validate_progression_events(payload)


def test_mock_output_missing_required_rejected() -> None:
    payload = _mock_data_agent_output([
        {"dimension": "境界", "to": "斗师"}  # 缺 character_id
    ])
    with pytest.raises(AssertionError, match="缺必填字段"):
        _validate_progression_events(payload)


def test_mock_output_missing_to_rejected() -> None:
    payload = _mock_data_agent_output([
        {"character_id": "x", "dimension": "境界"}
    ])
    with pytest.raises(AssertionError, match="缺 to 值"):
        _validate_progression_events(payload)


def test_mock_output_unknown_field_rejected() -> None:
    payload = _mock_data_agent_output([
        {"character_id": "x", "dimension": "境界", "to": "斗师", "extra": "?"}
    ])
    with pytest.raises(AssertionError, match="未知字段"):
        _validate_progression_events(payload)


def test_mock_output_is_serializable_json() -> None:
    """data-agent 输出契约要求纯 JSON。"""
    payload = _mock_data_agent_output([
        {"character_id": "x", "dimension": "关系", "from": "陌生", "to": "盟友", "cause": "并肩作战"}
    ])
    s = json.dumps(payload, ensure_ascii=False)
    parsed = json.loads(s)
    _validate_progression_events(parsed)
