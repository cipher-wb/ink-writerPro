#!/usr/bin/env python3
"""US-LR-014: markdown 内部链接可达性检查器。

扫 markdown 文件内 ``[text](path)`` 格式相对链接, 验证 path 在 md 同级目录或
repo root 是否可达。http(s)/mailto/anchor-only 链接跳过。

Exposed API:
    check_links(md_path: Path, repo_root: Path | None = None) -> list[str]
        返回不可达链接列表 (`[text](path)` 形式 + 行号); 全部可达时返回空列表。

CLI:
    python3 scripts/live-review/check_links.py docs/live-review-integration.md

退出码:
    0  全部链接可达
    1  存在不可达链接 (stderr 列每条 + 行号)
    2  输入文件不存在
"""
from __future__ import annotations

# US-LR-014: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Match [text](url) but not ![alt](image) image syntax (skip leading !).
# Greedy text capture is safe because nested brackets are rare in our docs;
# url stops at first whitespace or closing paren.
_LINK_PATTERN = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# URL prefixes that should be skipped (external / non-file).
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://", "ftps://")


def _is_external_or_anchor(url: str) -> bool:
    """Return True for URLs we don't validate (external / anchor-only)."""
    if url.startswith("#"):
        return True
    return bool(url.startswith(_SKIP_PREFIXES))


def _strip_anchor(url: str) -> str:
    """Drop ``#anchor`` and ``?query`` suffix from a relative path."""
    for sep in ("#", "?"):
        if sep in url:
            url = url.split(sep, 1)[0]
    return url


def _resolve_candidates(url: str, md_dir: Path, repo_root: Path) -> list[Path]:
    """Return candidate paths to test; file is reachable if any exists."""
    path = _strip_anchor(url)
    if not path:
        return []
    candidates: list[Path] = []
    # Same-dir relative resolution.
    candidates.append((md_dir / path).resolve())
    # Repo-root absolute resolution (e.g. ``docs/foo.md`` from any nested md).
    candidates.append((repo_root / path.lstrip("/")).resolve())
    return candidates


def check_links(md_path: Path, repo_root: Path | None = None) -> list[str]:
    """Scan markdown file and return a list of unreachable link descriptors.

    Each descriptor is the original ``[text](url)`` string prefixed with the
    line number (e.g. ``L42: [foo](bar.md)``). Empty list = all links resolve.
    """
    md_path = Path(md_path).resolve()
    repo_root = (repo_root or _REPO_ROOT).resolve()
    if not md_path.exists():
        raise FileNotFoundError(f"markdown not found: {md_path}")
    text = md_path.read_text(encoding="utf-8")
    md_dir = md_path.parent

    failures: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in _LINK_PATTERN.finditer(line):
            url = match.group(2)
            if _is_external_or_anchor(url):
                continue
            candidates = _resolve_candidates(url, md_dir, repo_root)
            if not any(c.exists() for c in candidates):
                failures.append(f"L{line_no}: {match.group(0)}")
    return failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check markdown internal link reachability."
    )
    parser.add_argument(
        "markdown",
        type=Path,
        help="markdown file to scan (e.g. docs/live-review-integration.md)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT,
        help="repo root used for absolute-style relative paths (default: auto)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    md_path = args.markdown
    if not md_path.exists():
        print(f"ERROR: markdown not found: {md_path}", file=sys.stderr)
        return 2
    failures = check_links(md_path, repo_root=args.repo_root)
    if failures:
        print(
            f"FAIL: {len(failures)} unreachable link(s) in {md_path}:",
            file=sys.stderr,
        )
        for entry in failures:
            print(f"  {entry}", file=sys.stderr)
        return 1
    print(f"OK: all internal links reachable in {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
