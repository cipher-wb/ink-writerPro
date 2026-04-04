"""
ink-writer benchmark — 爬虫配置
"""

import pathlib

# === 路径配置 ===
BENCHMARK_DIR = pathlib.Path(__file__).parent
CORPUS_DIR = BENCHMARK_DIR / "corpus"
CORPUS_INDEX = BENCHMARK_DIR / "corpus_index.json"

# === 起点移动站配置 ===
BASE_URL = "https://m.qidian.com"

# 排行榜类型
RANK_TYPES = {
    "yuepiao": "月票榜",
    "hotsales": "畅销榜",
    "readindex": "阅读指数榜",
    "rec": "推荐榜",
}

# 题材分类 (catId)
GENRES = {
    -1: "全站",
    21: "玄幻",
    22: "仙侠",
    4: "都市",
    5: "历史",
    9: "科幻",
    7: "游戏",
    2: "武侠",
    6: "军事",
    8: "悬疑",
    10: "轻小说",
}

# 目标题材 (要爬取的)
TARGET_GENRES = [21, 22, 4, 5, 9, 7]  # 玄幻/仙侠/都市/历史/科幻/游戏

# === 请求配置 ===
REQUEST_DELAY_MIN = 3.0  # 最小请求间隔（秒）
REQUEST_DELAY_MAX = 6.0  # 最大请求间隔（秒）
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # 指数退避基数

# UA池
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/119.0.6045.169 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Redmi Note 12 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; M2102J20SG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Mobile Safari/537.36",
]

# 通用请求头 (不设 Accept-Encoding，让 httpx 自动处理解压)
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://m.qidian.com/",
    "Connection": "keep-alive",
}

# === 爬取范围 ===
MAX_BOOKS_PER_GENRE = 20  # 每个题材最多爬多少本
MAX_FREE_CHAPTERS = 30    # 每本书最多爬多少章免费章节
MIN_CHAPTER_WORDS = 500   # 章节最少字数（过滤太短的）
