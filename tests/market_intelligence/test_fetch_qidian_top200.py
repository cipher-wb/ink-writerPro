"""US-007 — _fetch_one_book HTML 解析 + 重试退化的单元测试。

注：实跑爬虫由 PRD 验收脚本完成，这里只覆盖纯函数层面行为。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scripts.market_intelligence import fetch_qidian_top200 as mod

_FAKE_BOOK_HTML = """<!doctype html>
<html><body>
  <div class="book-info">
    <h1>
      <em>逆天剑神</em>
      <a class="writer">墨染笔</a>
    </h1>
    <p class="tag">
      <a>玄幻</a>
      <a>东方玄幻</a>
      <a>热血</a>
    </p>
  </div>
  <div class="book-intro">
    <p>少年陈青山天生废体，偶得上古剑魂传承。从此踏破九天，剑指无尽星河。</p>
  </div>
</body></html>
"""


def _fake_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_one_book_parses_html(monkeypatch):
    session = MagicMock()
    session.get = MagicMock(return_value=_fake_response(_FAKE_BOOK_HTML))

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)

    record = mod._fetch_one_book(7, "1234567890", session=session, max_retries=3)

    assert record is not None
    assert record["rank"] == 7
    assert record["title"] == "逆天剑神"
    assert record["author"] == "墨染笔"
    assert "玄幻" in record["genre_tags"]
    assert record["intro_full"].startswith("少年陈青山")
    assert record["intro_one_liner"] == "少年陈青山天生废体，偶得上古剑魂传承"
    assert record["url"].endswith("/book/1234567890/")
    assert "fetched_at" in record
    assert session.get.call_count == 1


def test_fetch_one_book_returns_none_after_retries(monkeypatch):
    session = MagicMock()
    session.get = MagicMock(side_effect=RuntimeError("boom"))

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)

    record = mod._fetch_one_book(3, "999", session=session, max_retries=2)

    assert record is None
    assert session.get.call_count == 2


@pytest.fixture(autouse=True)
def _isolate_data_paths(tmp_path, monkeypatch):
    """避免测试在仓库 data/ 落盘。"""
    monkeypatch.setattr(mod, "OUTPUT_PATH", tmp_path / "qidian_top200.jsonl")
    monkeypatch.setattr(mod, "PROGRESS_PATH", tmp_path / ".progress")
    yield
