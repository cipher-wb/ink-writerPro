"""US-LR-014: docs/live-review-integration.md + CLAUDE.md + check_links.py 验证."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_PATH = _REPO_ROOT / "docs" / "live-review-integration.md"
_CHECK_LINKS_PATH = _REPO_ROOT / "scripts" / "live-review" / "check_links.py"
_CLAUDE_MD_PATH = _REPO_ROOT / "CLAUDE.md"


def _load_check_links_module():
    """Import scripts/live-review/check_links.py as a module despite hyphen."""
    spec = importlib.util.spec_from_file_location(
        "live_review_check_links", str(_CHECK_LINKS_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("live_review_check_links", module)
    spec.loader.exec_module(module)
    return module


def test_doc_exists() -> None:
    """AC: docs/live-review-integration.md 存在并非空。"""
    assert _DOC_PATH.exists(), f"missing doc: {_DOC_PATH}"
    assert _DOC_PATH.stat().st_size > 0


def test_mermaid_blocks_valid_syntax() -> None:
    """AC: 至少 1 个 mermaid 块 + 含 graph/flowchart 关键字 + [ 与 ] 数量平衡。"""
    text = _DOC_PATH.read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)
    assert len(blocks) >= 1, "expected at least one mermaid code block"
    for idx, block in enumerate(blocks):
        assert re.search(r"\b(graph|flowchart)\b", block), (
            f"mermaid block #{idx} missing graph/flowchart keyword"
        )
        open_brackets = block.count("[")
        close_brackets = block.count("]")
        assert open_brackets == close_brackets, (
            f"mermaid block #{idx} bracket imbalance: "
            f"{open_brackets} '[' vs {close_brackets} ']'"
        )


def test_internal_links_resolvable() -> None:
    """AC: 所有 `[text](path)` 相对内部链接可达 (跑 check_links 无失败)。"""
    module = _load_check_links_module()
    failures = module.check_links(_DOC_PATH, repo_root=_REPO_ROOT)
    assert failures == [], (
        "unreachable internal links found:\n  " + "\n  ".join(failures)
    )


def test_claude_md_mentions_live_review() -> None:
    """AC: CLAUDE.md 含 'Live-Review' 字符串 + 链向 docs/live-review-integration.md。"""
    text = _CLAUDE_MD_PATH.read_text(encoding="utf-8")
    assert "Live-Review" in text, "CLAUDE.md missing 'Live-Review' literal"
    assert "docs/live-review-integration.md" in text, (
        "CLAUDE.md missing link to docs/live-review-integration.md"
    )


@pytest.mark.parametrize(
    "section",
    [
        "## 模块定位",
        "## 架构概览",
        "## 数据流",
        "## 主题域",
        "## 如何添加新数据",
        "## 如何调阈值",
        "## 用户手动操作清单",
        "## FAQ",
        "## Smoke test 段",
    ],
)
def test_doc_has_required_sections(section: str) -> None:
    """Sanity guard: 9 强制章节标题在 doc 里都能找到。"""
    text = _DOC_PATH.read_text(encoding="utf-8")
    assert section in text, f"missing required section: {section}"
