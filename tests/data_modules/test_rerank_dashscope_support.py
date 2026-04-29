"""Rerank 客户端 DashScope native 接口支持回归

背景：用户 cipher 用同一把千问（阿里百炼）sk- key 同时跑 embedding 和 rerank，
要求 rerank 客户端支持 DashScope native 协议（不同于 Jina/Cohere 的 OpenAI 兼容）。

DashScope rerank API 与 Jina 的差异：
  URL:      /api/v1/services/rerank/text-rerank/text-rerank（固定全路径，非 /v1/rerank）
  请求体:    {"model":..., "input":{"query","documents"}, "parameters":{"top_n",...}}
  响应:      {"output":{"results":[...]}}（多一层 output 嵌套）

本测试不真实调 API（避免依赖 key 和网络），只测试 _build_url / _build_payload /
_parse_response 三个方法在 api_type="dashscope" 时的行为。
"""

from __future__ import annotations

import sys
import types

# api_client 模块 import 时需要 aiohttp。本测试只测纯 URL/payload/parse 逻辑，
# 不发起真实 HTTP，因此用 stub 模块代替 aiohttp 避免环境耦合（CI 节点已有 aiohttp，
# 此 stub 仅在缺失时生效）。
if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    aiohttp_stub.ClientSession = object  # type: ignore[attr-defined]
    aiohttp_stub.TCPConnector = object  # type: ignore[attr-defined]
    aiohttp_stub.ClientTimeout = object  # type: ignore[attr-defined]
    sys.modules["aiohttp"] = aiohttp_stub

from ink_writer.core.infra.api_client import RerankAPIClient  # noqa: E402
from ink_writer.core.infra.config import DataModulesConfig  # noqa: E402


def _make_dashscope_config(base_url: str = "https://dashscope.aliyuncs.com/api/v1") -> DataModulesConfig:
    cfg = DataModulesConfig()
    cfg.rerank_api_type = "dashscope"
    cfg.rerank_base_url = base_url
    cfg.rerank_model = "gte-rerank-v2"
    cfg.rerank_api_key = "sk-test-not-real"
    return cfg


def test_dashscope_url_appends_full_path_when_base_is_v1():
    """base_url=https://dashscope.aliyuncs.com/api/v1 时应自动补完整 rerank 路径。"""
    cfg = _make_dashscope_config("https://dashscope.aliyuncs.com/api/v1")
    client = RerankAPIClient(cfg)
    url = client._build_url()
    assert url == "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank", (
        f"DashScope rerank URL 拼接错误：{url}"
    )


def test_dashscope_url_passthrough_when_full_path_provided():
    """用户在 base_url 直接给了完整路径时不应再追加。"""
    full = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    cfg = _make_dashscope_config(full)
    client = RerankAPIClient(cfg)
    assert client._build_url() == full


def test_dashscope_payload_uses_nested_input_and_parameters():
    """DashScope 请求体必须用 input 和 parameters 嵌套（不是 Jina 的扁平结构）。"""
    cfg = _make_dashscope_config()
    client = RerankAPIClient(cfg)
    payload = client._build_payload(
        query="农村养殖",
        documents=["养鸡场建设", "科幻小说创作", "种田文写作技巧"],
        top_n=2,
    )

    assert payload["model"] == "gte-rerank-v2"
    assert "input" in payload
    assert payload["input"]["query"] == "农村养殖"
    assert payload["input"]["documents"] == ["养鸡场建设", "科幻小说创作", "种田文写作技巧"]
    assert "parameters" in payload
    assert payload["parameters"]["top_n"] == 2
    assert payload["parameters"]["return_documents"] is False

    # 不能出现 Jina 风格的扁平字段
    assert "query" not in payload, "DashScope 协议不应在顶层放 query"
    assert "documents" not in payload, "DashScope 协议不应在顶层放 documents"
    assert "top_n" not in payload, "DashScope 协议 top_n 在 parameters 内"


def test_dashscope_payload_omits_top_n_when_none():
    cfg = _make_dashscope_config()
    client = RerankAPIClient(cfg)
    payload = client._build_payload("q", ["d1"], top_n=None)
    assert "top_n" not in payload["parameters"]


def test_dashscope_parse_response_unwraps_output_nesting():
    """DashScope 响应在 data.output.results；解析必须能拿出来。"""
    cfg = _make_dashscope_config()
    client = RerankAPIClient(cfg)

    fake_response = {
        "output": {
            "results": [
                {"index": 0, "relevance_score": 0.95},
                {"index": 2, "relevance_score": 0.42},
            ]
        },
        "usage": {"total_tokens": 18},
        "request_id": "req-abc-123",
    }

    results = client._parse_response(fake_response)
    assert len(results) == 2
    assert results[0]["index"] == 0
    assert results[0]["relevance_score"] == 0.95
    assert results[1]["index"] == 2


def test_dashscope_parse_response_handles_empty_output():
    cfg = _make_dashscope_config()
    client = RerankAPIClient(cfg)
    assert client._parse_response({}) == []
    assert client._parse_response({"output": {}}) == []
    assert client._parse_response({"output": {"results": []}}) == []


def test_openai_branch_unchanged_for_jina_url():
    """守护：将 api_type 切回 openai，行为应回到 Jina/Cohere 兼容协议。"""
    cfg = DataModulesConfig()
    cfg.rerank_api_type = "openai"
    cfg.rerank_base_url = "https://api.jina.ai/v1"
    cfg.rerank_model = "jina-reranker-v3"
    cfg.rerank_api_key = "jina-test"
    client = RerankAPIClient(cfg)

    assert client._build_url() == "https://api.jina.ai/v1/rerank"

    payload = client._build_payload("q", ["d1", "d2"], top_n=1)
    # OpenAI 风格：扁平字段
    assert payload["query"] == "q"
    assert payload["documents"] == ["d1", "d2"]
    assert payload["top_n"] == 1
    assert "input" not in payload, "OpenAI 协议不应有 input 嵌套"
    assert "parameters" not in payload, "OpenAI 协议不应有 parameters 嵌套"

    # OpenAI 响应解析：顶层 results
    fake = {"results": [{"index": 0, "relevance_score": 0.9}]}
    assert client._parse_response(fake)[0]["relevance_score"] == 0.9


def test_config_auto_detects_dashscope_type_from_base_url(monkeypatch):
    """RERANK_BASE_URL 含 dashscope.aliyuncs.com 时 api_type 自动判为 dashscope。"""
    monkeypatch.setenv("RERANK_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    monkeypatch.delenv("RERANK_API_TYPE", raising=False)
    cfg = DataModulesConfig()
    assert cfg.rerank_api_type == "dashscope"


def test_config_explicit_rerank_api_type_overrides_auto_detect(monkeypatch):
    """显式 RERANK_API_TYPE 覆盖自动判定。"""
    monkeypatch.setenv("RERANK_BASE_URL", "https://api.jina.ai/v1")
    monkeypatch.setenv("RERANK_API_TYPE", "dashscope")
    cfg = DataModulesConfig()
    assert cfg.rerank_api_type == "dashscope"


def test_config_default_is_openai_for_jina_url(monkeypatch):
    monkeypatch.setenv("RERANK_BASE_URL", "https://api.jina.ai/v1")
    monkeypatch.delenv("RERANK_API_TYPE", raising=False)
    cfg = DataModulesConfig()
    assert cfg.rerank_api_type == "openai"
