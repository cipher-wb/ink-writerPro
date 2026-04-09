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

# Style RAG 优先题材（先构建这3类的风格参考库）
STYLE_RAG_PRIORITY_GENRES = [21, 22, 4]  # 玄幻/仙侠/都市

# Style RAG 场景类型关键词（用于自动标注片段）
SCENE_TYPE_KEYWORDS = {
    "战斗": ["出手", "攻击", "一拳", "一剑", "杀", "斩", "劈", "挡", "闪", "爆发",
             "碰撞", "击飞", "鲜血", "重伤", "战", "冲", "扑"],
    "对话": ["说道", "问道", "笑道", "冷声", "答道", "喊道", "怒道", "低语",
             "开口", "接话", "回答", "追问"],
    "情感": ["心中", "感觉", "泪", "痛", "喜", "悲", "怒", "惧", "愧",
             "温暖", "心疼", "不舍", "感动", "难过"],
    "悬念": ["究竟", "到底", "秘密", "隐藏", "真相", "谜", "诡异", "异常",
             "不对劲", "蹊跷", "线索"],
    "日常": ["吃", "喝", "睡", "走", "笑", "聊", "逛", "做饭", "休息",
             "早上", "傍晚", "天亮"],
    "高潮": ["突破", "觉醒", "逆转", "震惊", "不可能", "奇迹", "碾压",
             "爆发", "释放", "终于"],
    "过渡": ["之后", "随后", "接下来", "与此同时", "另一边", "回到"],
}

# 情绪关键词（用于片段情绪标注）
EMOTION_KEYWORDS = {
    "紧张": ["紧张", "心跳", "冷汗", "屏息", "颤抖", "危险", "死"],
    "热血": ["热血", "燃烧", "冲", "战", "豪气", "壮志", "怒吼"],
    "悲伤": ["泪", "哭", "痛", "失去", "离别", "死去", "悲", "心碎"],
    "轻松": ["笑", "乐", "有趣", "好玩", "轻松", "惬意", "舒适"],
    "震惊": ["震惊", "不可能", "怎么可能", "瞳孔", "难以置信", "目瞪口呆"],
    "愤怒": ["愤怒", "怒", "恨", "该死", "混蛋", "可恶", "杀了"],
    "温馨": ["温暖", "温柔", "关心", "照顾", "微笑", "安慰", "陪伴"],
}

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
MAX_FREE_CHAPTERS = 50    # 每本书最多爬多少章免费章节（v10.6: 30→50，更多场景覆盖）
MIN_CHAPTER_WORDS = 500   # 章节最少字数（过滤太短的）

# === Style RAG 配置 ===
STYLE_RAG_DB = BENCHMARK_DIR / "style_rag.db"
STYLE_RAG_MIN_FRAGMENT_WORDS = 200   # 片段最少字数
STYLE_RAG_MAX_FRAGMENT_WORDS = 800   # 片段最大字数
STYLE_RAG_MIN_QUALITY_SCORE = 0.5    # 最低质量分（过滤异常差的片段）

# === 优先爬取书单（头部标杆，手动指定） ===
# 这些书在各题材排行榜长期稳居前列，爬虫优先处理
PRIORITY_BOOKS = {
    # 玄幻
    "玄幻": [
        "夜无疆",          # 辰东，月票榜常客
        "万相之王",         # 天蚕土豆
        "大奉打更人",       # 卖报小郎君
        "斗破苍穹",         # 天蚕土豆（经典标杆）
        "遮天",            # 辰东（经典标杆）
    ],
    # 仙侠
    "仙侠": [
        "苟在武道世界成圣",  # 已有语料
        "青山",            # 会说话的肘子，已有语料
        "凡人修仙传",       # 忘语（经典标杆）
        "仙业",            # 已有语料
    ],
    # 都市
    "都市": [
        "以神通之名",       # 已有语料
        "全职高手",         # 蝴蝶蓝（经典标杆）
        "大王饶命",         # 会说话的肘子
    ],
}
