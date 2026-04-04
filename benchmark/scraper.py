#!/usr/bin/env python3
"""
ink-writer benchmark — 起点中文网爬虫
从 m.qidian.com (移动站SSR) 爬取热门小说免费章节

用法:
    python benchmark/scraper.py --test --limit 1        # 单本测试
    python benchmark/scraper.py --genre 玄幻            # 爬取某题材
    python benchmark/scraper.py --all                   # 爬取所有目标题材
    python benchmark/scraper.py --book 1035420986       # 爬取指定书籍ID
    python benchmark/scraper.py --resume                # 断点续爬
"""

import argparse
import asyncio
import html
import json
import logging
import pathlib
import random
import re
import sys
import time
from datetime import datetime
from typing import Any

import httpx

# 添加 benchmark 目录到路径
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import (
    BASE_URL, CORPUS_DIR, CORPUS_INDEX, DEFAULT_HEADERS, GENRES,
    MAX_BOOKS_PER_GENRE, MAX_FREE_CHAPTERS, MAX_RETRIES, MIN_CHAPTER_WORDS,
    RANK_TYPES, REQUEST_DELAY_MAX, REQUEST_DELAY_MIN, RETRY_BACKOFF,
    TARGET_GENRES, USER_AGENTS,
)

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")


# ============================================================
# 核心工具函数
# ============================================================

def random_ua() -> str:
    return random.choice(USER_AGENTS)


async def random_delay():
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    await asyncio.sleep(delay)


def extract_page_context(html_text: str) -> dict | None:
    """从 SSR HTML 中提取 pageContext JSON 数据

    起点移动站使用 vite-plugin-ssr，数据在:
    <script id="vite-plugin-ssr_pageContext" type="application/json">{...}</script>
    """
    # 方式1: 精确匹配 vite-plugin-ssr 标签
    pattern1 = r'<script\s+id="vite-plugin-ssr_pageContext"\s+type="application/json">(.*?)</script>'
    match = re.search(pattern1, html_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            # 数据可能在 data["pageContext"] 或直接在 data 中
            if "pageContext" in data:
                return data["pageContext"]
            return data
        except json.JSONDecodeError:
            pass

    # 方式2: 任何 type="application/json" 包含 pageContext
    pattern2 = r'<script[^>]*type="application/json"[^>]*>(.*?)</script>'
    for match in re.finditer(pattern2, html_text, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                if "pageContext" in data:
                    return data["pageContext"]
                if "pageProps" in data:
                    return data
        except json.JSONDecodeError:
            continue

    # 方式3: 包含 pageContext 的独立 script 内容
    pattern3 = r'<script[^>]*>\s*(\{"pageContext".*?\})\s*</script>'
    match = re.search(pattern3, html_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return data.get("pageContext", data)
        except json.JSONDecodeError:
            pass

    return None


def navigate_json(data: dict, path: str) -> Any:
    """用点分路径访问嵌套JSON: 'pageProps.pageData.bookInfo'"""
    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if current is None:
            return None
    return current


def clean_chapter_content(raw_content: str) -> str:
    """清理章节内容：去HTML标签，反转义"""
    if not raw_content:
        return ""
    # 反转义HTML实体
    text = html.unescape(raw_content)
    # 去除HTML标签，保留段落换行
    text = re.sub(r'<p[^>]*>', '\n', text)
    text = re.sub(r'</p>', '', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    # 清理多余空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


def sanitize_filename(name: str) -> str:
    """将书名转为安全的文件名"""
    # 移除不安全字符
    safe = re.sub(r'[<>:"/\\|?*]', '', name)
    safe = safe.strip()
    return safe[:80] if safe else "unknown"


# ============================================================
# 爬虫核心类
# ============================================================

class QidianScraper:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None
        self.scraped_book_ids: set[str] = set()
        self._load_progress()

    def _load_progress(self):
        """加载已爬取的书籍ID（断点续爬）"""
        if CORPUS_INDEX.exists():
            try:
                index = json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))
                self.scraped_book_ids = {b["book_id"] for b in index}
                log.info(f"已加载进度: {len(self.scraped_book_ids)} 本已爬取")
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_index(self, books: list[dict]):
        """保存/更新语料库索引"""
        existing = []
        if CORPUS_INDEX.exists():
            try:
                existing = json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        existing_ids = {b["book_id"] for b in existing}
        for book in books:
            if book["book_id"] not in existing_ids:
                existing.append(book)

        CORPUS_INDEX.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _fetch(self, url: str) -> str | None:
        """带重试的HTTP GET"""
        for attempt in range(MAX_RETRIES):
            try:
                headers = {**DEFAULT_HEADERS, "User-Agent": random_ua()}
                resp = await self.client.get(url, headers=headers, follow_redirects=True, timeout=30)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 403:
                    log.warning(f"403 Forbidden: {url} — 可能触发反爬，等待更长时间")
                    await asyncio.sleep(REQUEST_DELAY_MAX * (attempt + 2))
                else:
                    log.warning(f"HTTP {resp.status_code}: {url}")
            except httpx.TimeoutException:
                log.warning(f"Timeout (attempt {attempt+1}): {url}")
            except httpx.RequestError as e:
                log.warning(f"Request error (attempt {attempt+1}): {e}")

            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                await asyncio.sleep(wait)

        log.error(f"Failed after {MAX_RETRIES} retries: {url}")
        return None

    # ----------------------------------------------------------
    # 排行榜爬取
    # ----------------------------------------------------------

    async def fetch_ranking(self, genre_id: int, rank_type: str = "yuepiao") -> list[dict]:
        """爬取某题材某排行榜的书籍列表（第1页，20本）"""
        now = datetime.now()
        date_str = now.strftime("%Y%m")
        cat_str = f"catid{genre_id}" if genre_id != -1 else "catid-1"
        url = f"{BASE_URL}/rank/{rank_type}/{cat_str}/{date_str}/"

        log.info(f"爬取排行榜: {GENRES.get(genre_id, genre_id)} - {RANK_TYPES.get(rank_type, rank_type)}")
        html_text = await self._fetch(url)
        if not html_text:
            return []

        page_data = extract_page_context(html_text)
        if not page_data:
            log.warning(f"无法提取 pageContext: {url}")
            # 保存HTML用于调试
            debug_path = CORPUS_DIR / f"_debug_ranking_{genre_id}_{rank_type}.html"
            debug_path.write_text(html_text[:5000], encoding="utf-8")
            return []

        # 尝试多种路径提取排行数据
        books_data = None
        for path in [
            "pageProps.pageData.records",
            "pageProps.pageData.list",
            "pageProps.pageData",
            "pageContext.pageProps.pageData.records",
            "pageContext.pageProps.pageData",
        ]:
            result = navigate_json(page_data, path)
            if isinstance(result, list) and len(result) > 0:
                books_data = result
                break

        if not books_data:
            # 也可能整个page_data就是一个包含书籍的结构
            if isinstance(page_data, dict):
                for key in ["records", "list", "books", "items"]:
                    if key in page_data and isinstance(page_data[key], list):
                        books_data = page_data[key]
                        break

        if not books_data:
            log.warning(f"排行榜数据为空或格式未知: {url}")
            debug_path = CORPUS_DIR / f"_debug_ranking_json_{genre_id}_{rank_type}.json"
            debug_path.write_text(
                json.dumps(page_data, ensure_ascii=False, indent=2)[:10000],
                encoding="utf-8",
            )
            return []

        books = []
        for item in books_data[:MAX_BOOKS_PER_GENRE]:
            book_id = str(item.get("bid") or item.get("bookId") or item.get("bId") or "")
            if not book_id:
                continue
            books.append({
                "book_id": book_id,
                "title": item.get("bName") or item.get("bookName") or "",
                "author": item.get("bAuth") or item.get("authorName") or "",
                "genre": item.get("cat") or item.get("catName") or GENRES.get(genre_id, ""),
                "sub_genre": item.get("subCat") or item.get("subCatName") or "",
                "word_count_str": item.get("cnt") or item.get("wordsCnt") or "",
                "rank_metric": item.get("rankCnt") or "",
                "synopsis": item.get("desc") or "",
            })

        log.info(f"  排行榜获取 {len(books)} 本书")
        return books

    async def fetch_rankings_for_genre(self, genre_id: int) -> list[dict]:
        """爬取某题材的多个排行榜，去重合并"""
        all_books = {}
        for rank_type in ["yuepiao", "hotsales", "readindex"]:
            await random_delay()
            books = await self.fetch_ranking(genre_id, rank_type)
            for b in books:
                if b["book_id"] not in all_books:
                    all_books[b["book_id"]] = b

        result = list(all_books.values())[:MAX_BOOKS_PER_GENRE]
        log.info(f"  {GENRES.get(genre_id, genre_id)} 去重后: {len(result)} 本")
        return result

    # ----------------------------------------------------------
    # 书籍详情
    # ----------------------------------------------------------

    async def fetch_book_detail(self, book_id: str) -> dict | None:
        """爬取书籍详情页，获取完整元数据"""
        url = f"{BASE_URL}/book/{book_id}/"
        html_text = await self._fetch(url)
        if not html_text:
            return None

        page_data = extract_page_context(html_text)
        if not page_data:
            return None

        # 尝试多种路径
        book_info = None
        for path in [
            "pageProps.pageData.bookInfo",
            "pageProps.pageData",
            "pageContext.pageProps.pageData.bookInfo",
        ]:
            result = navigate_json(page_data, path)
            if isinstance(result, dict) and ("bookName" in result or "bName" in result):
                book_info = result
                break

        if not book_info:
            return None

        return {
            "book_id": book_id,
            "title": book_info.get("bookName") or book_info.get("bName") or "",
            "author": book_info.get("authorName") or book_info.get("bAuth") or "",
            "genre": book_info.get("subCateName") or book_info.get("cat") or "",
            "genre_id": book_info.get("unitCategoryId") or book_info.get("catId") or "",
            "tags": book_info.get("bookTag") or "",
            "word_count": book_info.get("wordsCnt") or 0,
            "word_count_str": book_info.get("showWordsCnt") or "",
            "collections": book_info.get("collect") or 0,
            "month_ticket": book_info.get("monthTicket") or 0,
            "recommendations": book_info.get("recomAll") or 0,
            "synopsis": book_info.get("desc") or "",
            "status": book_info.get("bookStatus") or "",
            "url": f"https://www.qidian.com/book/{book_id}/",
        }

    # ----------------------------------------------------------
    # 章节目录
    # ----------------------------------------------------------

    async def fetch_catalog(self, book_id: str) -> list[dict]:
        """爬取章节目录，返回章节列表"""
        url = f"{BASE_URL}/book/{book_id}/catalog/"
        html_text = await self._fetch(url)
        if not html_text:
            return []

        # 从HTML中提取章节链接
        # 模式: /chapter/{bookId}/{chapterId}/
        chapters = []
        pattern = rf'/chapter/{book_id}/(\d+)/'
        seen_ids = set()

        # 同时尝试从 pageContext 提取
        page_data = extract_page_context(html_text)
        if page_data:
            # 尝试从JSON中提取章节列表
            for path in [
                "pageProps.pageData.vs",
                "pageProps.pageData.chapters",
                "pageProps.pageData.volumeList",
            ]:
                volumes = navigate_json(page_data, path)
                if isinstance(volumes, list):
                    for vol in volumes:
                        ch_list = vol.get("cs") or vol.get("chapters") or []
                        if isinstance(vol, dict) and isinstance(ch_list, list):
                            for ch in ch_list:
                                ch_id = str(ch.get("id") or ch.get("cid") or ch.get("chapterId") or "")
                                if ch_id and ch_id not in seen_ids:
                                    seen_ids.add(ch_id)
                                    is_vip = ch.get("sS") == 1 or ch.get("vipStatus", 0) != 0
                                    chapters.append({
                                        "chapter_id": ch_id,
                                        "title": ch.get("cN") or ch.get("chapterName") or "",
                                        "is_vip": is_vip,
                                    })

        # 如果JSON方式没获取到，用正则从HTML提取
        if not chapters:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, "lxml")
            for link in soup.find_all("a", href=re.compile(rf'/chapter/{book_id}/\d+')):
                href = link.get("href", "")
                match = re.search(rf'/chapter/{book_id}/(\d+)', href)
                if match:
                    ch_id = match.group(1)
                    if ch_id not in seen_ids:
                        seen_ids.add(ch_id)
                        title = link.get_text(strip=True)
                        # 检查是否有VIP标记
                        is_vip = bool(link.find(class_=re.compile(r'vip|lock|pay', re.I)))
                        chapters.append({
                            "chapter_id": ch_id,
                            "title": title,
                            "is_vip": is_vip,
                        })

        return chapters

    # ----------------------------------------------------------
    # 章节内容
    # ----------------------------------------------------------

    async def fetch_chapter(self, book_id: str, chapter_id: str) -> dict | None:
        """爬取单章内容"""
        url = f"{BASE_URL}/chapter/{book_id}/{chapter_id}/"
        html_text = await self._fetch(url)
        if not html_text:
            return None

        page_data = extract_page_context(html_text)
        if not page_data:
            return None

        ch_info = None
        for path in [
            "pageProps.pageData.chapterInfo",
            "pageProps.pageData",
            "pageContext.pageProps.pageData.chapterInfo",
        ]:
            result = navigate_json(page_data, path)
            if isinstance(result, dict) and ("content" in result or "txt" in result):
                ch_info = result
                break

        if not ch_info:
            return None

        raw_content = ch_info.get("content") or ch_info.get("txt") or ""
        clean_text = clean_chapter_content(raw_content)

        if len(clean_text) < MIN_CHAPTER_WORDS:
            return None  # 太短，可能是VIP截断

        return {
            "chapter_id": chapter_id,
            "title": ch_info.get("chapterName") or ch_info.get("cN") or "",
            "content": clean_text,
            "word_count": ch_info.get("wordsCount") or ch_info.get("cnt") or len(clean_text),
            "vip_status": ch_info.get("vipStatus") or ch_info.get("sS") or 0,
            "update_time": ch_info.get("updateTime") or ch_info.get("uT") or "",
        }

    # ----------------------------------------------------------
    # 完整书籍爬取
    # ----------------------------------------------------------

    async def scrape_book(self, book_id: str, book_meta: dict | None = None) -> dict | None:
        """爬取单本书的完整数据（元数据+免费章节）"""
        if book_id in self.scraped_book_ids:
            log.info(f"  跳过已爬取: {book_id}")
            return None

        log.info(f"爬取书籍: {book_id}")

        # 1. 获取详情
        await random_delay()
        detail = await self.fetch_book_detail(book_id)
        if not detail:
            log.warning(f"  无法获取书籍详情: {book_id}")
            return None

        title = detail["title"]
        log.info(f"  书名: {title} | 作者: {detail['author']} | 题材: {detail['genre']}")

        # 合并已有的元数据
        if book_meta:
            for k, v in book_meta.items():
                if k not in detail or not detail[k]:
                    detail[k] = v

        # 2. 获取目录
        await random_delay()
        catalog = await self.fetch_catalog(book_id)
        if not catalog:
            log.warning(f"  无法获取章节目录: {title}")
            return None

        # 不依赖 sS 字段判断免费（实测 sS 含义不可靠）
        # 直接按顺序从第1章开始爬取，用实际内容长度判断是否被截断
        # 跳过"作品相关"类非正文章节
        story_chapters = [ch for ch in catalog if re.search(r'第\d+章|章\d+', ch.get("title", ""))]
        if not story_chapters:
            story_chapters = catalog  # fallback: 全部按顺序

        target_chapters = story_chapters[:MAX_FREE_CHAPTERS]
        log.info(f"  目录: {len(catalog)}章, 正文: {len(story_chapters)}章, 目标: {len(target_chapters)}章")

        # 3. 逐章爬取（连续3章内容被截断则认为后续都是VIP，停止）
        chapters_data = []
        consecutive_truncated = 0
        for i, ch in enumerate(target_chapters):
            await random_delay()
            ch_data = await self.fetch_chapter(book_id, ch["chapter_id"])
            if ch_data:
                consecutive_truncated = 0  # 获取成功，重置计数
                chapters_data.append(ch_data)
                log.info(f"    ch{i+1:03d}: {ch_data['title']} ({ch_data['word_count']}字)")
            else:
                consecutive_truncated += 1
                log.warning(f"    ch{i+1:03d}: 内容不足/截断 ({ch['chapter_id']})")
                if consecutive_truncated >= 3:
                    log.info(f"    连续{consecutive_truncated}章截断，判定为VIP区间，停止")
                    break

        if not chapters_data:
            log.warning(f"  无有效章节: {title}")
            return None

        # 4. 保存到文件
        safe_title = sanitize_filename(title)
        book_dir = CORPUS_DIR / safe_title
        book_dir.mkdir(parents=True, exist_ok=True)

        # 保存元数据
        metadata = {
            **detail,
            "chapter_count": len(chapters_data),
            "scraped_at": datetime.now().isoformat(),
        }
        (book_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 保存章节
        ch_dir = book_dir / "chapters"
        ch_dir.mkdir(exist_ok=True)
        for j, ch_data in enumerate(chapters_data):
            ch_file = ch_dir / f"ch{j+1:03d}.txt"
            ch_file.write_text(ch_data["content"], encoding="utf-8")

        # 更新索引
        self.scraped_book_ids.add(book_id)
        index_entry = {
            "book_id": book_id,
            "title": title,
            "author": detail["author"],
            "genre": detail["genre"],
            "word_count": detail.get("word_count", 0),
            "collections": detail.get("collections", 0),
            "chapter_count": len(chapters_data),
            "dir": safe_title,
        }
        self._save_index([index_entry])

        log.info(f"  ✓ 完成: {title} ({len(chapters_data)}章)")
        return index_entry

    # ----------------------------------------------------------
    # 批量爬取
    # ----------------------------------------------------------

    async def scrape_genre(self, genre_id: int) -> list[dict]:
        """爬取某题材的热门书籍"""
        genre_name = GENRES.get(genre_id, str(genre_id))
        log.info(f"\n{'='*60}")
        log.info(f"开始爬取题材: {genre_name} (catId={genre_id})")
        log.info(f"{'='*60}")

        books = await self.fetch_rankings_for_genre(genre_id)
        if not books:
            log.warning(f"  未获取到{genre_name}的排行榜数据")
            return []

        results = []
        for i, book in enumerate(books):
            log.info(f"\n--- [{i+1}/{len(books)}] ---")
            result = await self.scrape_book(book["book_id"], book)
            if result:
                results.append(result)

        log.info(f"\n{genre_name} 完成: {len(results)}/{len(books)} 本成功")
        return results

    async def scrape_all(self):
        """爬取所有目标题材"""
        log.info("开始全量爬取")
        total_results = []
        for genre_id in TARGET_GENRES:
            results = await self.scrape_genre(genre_id)
            total_results.extend(results)
            log.info(f"累计完成: {len(total_results)} 本")

        log.info(f"\n全量爬取完成: {len(total_results)} 本")
        return total_results

    async def run(self, args):
        """主入口"""
        async with httpx.AsyncClient() as client:
            self.client = client

            if args.book:
                await self.scrape_book(args.book)
            elif args.genre:
                # 查找genre_id
                genre_id = None
                for gid, gname in GENRES.items():
                    if gname == args.genre or str(gid) == args.genre:
                        genre_id = gid
                        break
                if genre_id is None:
                    log.error(f"未知题材: {args.genre}. 可选: {list(GENRES.values())}")
                    return
                await self.scrape_genre(genre_id)
            elif args.test:
                # 测试模式：爬一个排行榜，取前N本
                limit = args.limit or 1
                books = await self.fetch_ranking(21, "yuepiao")  # 玄幻月票
                for book in books[:limit]:
                    await self.scrape_book(book["book_id"], book)
            elif args.all:
                await self.scrape_all()
            elif args.resume:
                # 断点续爬：爬所有题材，已爬的自动跳过
                await self.scrape_all()
            else:
                log.info("请指定模式: --test, --genre, --book, --all, --resume")


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="起点中文网热门小说爬虫")
    parser.add_argument("--test", action="store_true", help="测试模式（爬1本验证）")
    parser.add_argument("--limit", type=int, help="测试模式爬取数量限制")
    parser.add_argument("--genre", type=str, help="爬取指定题材（如: 玄幻）")
    parser.add_argument("--book", type=str, help="爬取指定书籍ID")
    parser.add_argument("--all", action="store_true", help="爬取所有目标题材")
    parser.add_argument("--resume", action="store_true", help="断点续爬")
    args = parser.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    asyncio.run(QidianScraper().run(args))


if __name__ == "__main__":
    main()
