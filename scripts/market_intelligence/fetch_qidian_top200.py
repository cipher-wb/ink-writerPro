#!/usr/bin/env python3
"""US-007: 爬取起点 top200 榜单作为 genre-novelty-checker 的真相源。

合规守则
========
- ``UA`` 显式声明教育/非商业用途 + 联系邮箱（PRD US-007）。
- 启动时检查 ``robots.txt``，命中 disallow 直接退出（不抓取）。
- 每个 HTTP 请求间隔 ``RATE_LIMIT_SECONDS = 1.0`` 秒。
- 单条 ``_fetch_one_book`` 失败重试 ``max_retries = 3`` 次后跳过。
- ``data/market_intelligence/.qidian_top200_progress`` 持久化已抓 rank，
  CTRL-C 后 ``--target`` 重跑可从断点续。

输出
----
``data/market_intelligence/qidian_top200.jsonl``，每行一条 ::

    {"rank": 1, "title": "...", "author": "...", "url": "...",
     "genre_tags": [...], "intro_one_liner": "...", "intro_full": "...",
     "fetched_at": "2026-04-25T..."}

PRD 说明：实跑遇到反爬或 HTML 结构变化时，可 commit 空 jsonl 并在
commit message 标 ``[manual-fallback-needed]``，US-014 e2e 用 fixture 跑。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_INK_SCRIPTS = _REPO_ROOT / "ink-writer" / "scripts"
for _candidate in (_REPO_ROOT, _INK_SCRIPTS):
    _sp = str(_candidate)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)


UA = (
    "ink-writer/M4 (educational/non-commercial; "
    "contact: insectwb@gmail.com)"
)
BASE_URL = "https://www.qidian.com"
RANK_URL_TEMPLATE = "https://www.qidian.com/rank/yuepiao/page{page}/"
BOOK_INFO_URL_TEMPLATE = "https://www.qidian.com/book/{book_id}/"
RATE_LIMIT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TARGET = 200
PAGES_PER_RANK = 10  # 起点月票榜 1 页 20 条 × 10 页 = 200

DATA_DIR = Path("data/market_intelligence")
OUTPUT_PATH = DATA_DIR / "qidian_top200.jsonl"
PROGRESS_PATH = DATA_DIR / ".qidian_top200_progress"
ROBOTS_URL = "https://www.qidian.com/robots.txt"


def _check_robots_txt(*, session: requests.Session | None = None) -> bool:
    """简易 robots.txt 检查：返回 True 表示允许，False 阻断。"""
    sess = session or requests.Session()
    try:
        resp = sess.get(ROBOTS_URL, headers={"User-Agent": UA}, timeout=10)
        resp.raise_for_status()
        text = resp.text
    except Exception as exc:
        print(f"[robots] failed to fetch robots.txt: {exc}; abort", file=sys.stderr)
        return False

    current_agent: str | None = None
    applies = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current_agent = value
            applies = current_agent in ("*", UA.split("/", 1)[0])
        elif key == "disallow" and applies:
            if value in ("/", "/rank", "/rank/yuepiao", "/book"):
                print(
                    f"[robots] disallow rule hits: {value!r}; abort",
                    file=sys.stderr,
                )
                return False
    return True


def _load_progress() -> set[int]:
    if not PROGRESS_PATH.exists():
        return set()
    ranks: set[int] = set()
    with PROGRESS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ranks.add(int(line))
            except ValueError:
                continue
    return ranks


def _save_progress_one(rank: int) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{rank}\n")


def _append_jsonl(record: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _http_get(url: str, *, session: requests.Session) -> requests.Response:
    resp = session.get(url, headers={"User-Agent": UA}, timeout=15)
    resp.raise_for_status()
    return resp


def _fetch_rank_page(
    page: int, *, session: requests.Session
) -> list[tuple[int, str]]:
    """抓 1 页榜单 → [(rank, book_id), ...]。"""
    url = RANK_URL_TEMPLATE.format(page=page)
    resp = _http_get(url, session=session)
    soup = BeautifulSoup(resp.text, "html.parser")
    pairs: list[tuple[int, str]] = []
    for li in soup.select("ul.rank-view-list li"):
        rank_attr = li.get("data-rid") or li.get("data-rank")
        try:
            rank = int(rank_attr) if rank_attr else 0
        except (TypeError, ValueError):
            rank = 0
        a = li.select_one("h4 a") or li.select_one("a.name")
        if not a:
            continue
        href = a.get("href") or ""
        book_id = ""
        for token in href.strip("/").split("/"):
            if token.isdigit():
                book_id = token
                break
        if not book_id:
            continue
        if rank == 0:
            rank = (page - 1) * 20 + len(pairs) + 1
        pairs.append((rank, book_id))
    return pairs


def _fetch_one_book(
    rank: int,
    book_id: str,
    *,
    session: requests.Session,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict | None:
    """抓单本书详情。失败 ``max_retries`` 次后返回 None。"""
    url = BOOK_INFO_URL_TEMPLATE.format(book_id=book_id)
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = _http_get(url, session=session)
            soup = BeautifulSoup(resp.text, "html.parser")

            title_node = soup.select_one("h1 em") or soup.select_one(".book-info h1 em")
            title = title_node.get_text(strip=True) if title_node else ""

            author_node = soup.select_one("h1 a.writer") or soup.select_one("a.writer")
            author = author_node.get_text(strip=True) if author_node else ""

            tag_nodes = soup.select(".book-info .tag span") or soup.select(
                "p.tag a"
            )
            genre_tags = [t.get_text(strip=True) for t in tag_nodes if t.get_text(strip=True)]

            intro_node = soup.select_one("div.book-intro p") or soup.select_one(
                "#book-intro-detail p"
            )
            intro_full = intro_node.get_text(" ", strip=True) if intro_node else ""
            intro_one_liner = intro_full.split("。", 1)[0][:120] if intro_full else ""

            return {
                "rank": rank,
                "title": title,
                "author": author,
                "url": url,
                "genre_tags": genre_tags,
                "intro_one_liner": intro_one_liner,
                "intro_full": intro_full,
                "fetched_at": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:
            last_err = exc
            time.sleep(RATE_LIMIT_SECONDS * (attempt + 1))
    print(
        f"[fetch] rank {rank} book {book_id} gave up after {max_retries} retries: {last_err}",
        file=sys.stderr,
    )
    return None


def run(*, target: int = DEFAULT_TARGET, max_retries: int = DEFAULT_MAX_RETRIES) -> int:
    session = requests.Session()
    if not _check_robots_txt(session=session):
        return 1

    done = _load_progress()
    fetched = 0
    skipped = 0
    pages = max(1, (target + 19) // 20)
    pages = min(pages, PAGES_PER_RANK)

    for page in range(1, pages + 1):
        try:
            pairs = _fetch_rank_page(page, session=session)
        except Exception as exc:
            print(f"[rank] page {page} failed: {exc}", file=sys.stderr)
            time.sleep(RATE_LIMIT_SECONDS)
            continue
        time.sleep(RATE_LIMIT_SECONDS)

        for rank, book_id in pairs:
            if rank > target:
                continue
            if rank in done:
                skipped += 1
                continue
            record = _fetch_one_book(
                rank, book_id, session=session, max_retries=max_retries
            )
            time.sleep(RATE_LIMIT_SECONDS)
            if record is None:
                continue
            _append_jsonl(record)
            _save_progress_one(rank)
            fetched += 1

    print(f"[done] fetched={fetched} skipped(resumed)={skipped} target={target}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Qidian top200 monthly-rank book intros into "
            "data/market_intelligence/qidian_top200.jsonl. Polite UA, robots "
            "respected, 1 req/s rate limit, checkpoint-resumable."
        ),
    )
    parser.add_argument(
        "--target",
        type=int,
        default=DEFAULT_TARGET,
        help="Number of top books to fetch (default: 200)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Max retries per book before skipping (default: 3)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — Mac/Linux no-op
        pass

    args = _build_parser().parse_args(argv)
    return run(target=args.target, max_retries=args.max_retries)


if __name__ == "__main__":
    sys.exit(main())
