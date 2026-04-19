#!/usr/bin/env python3
"""
mine_hook_patterns.py - 从爆款对照集中抽取钩子模式库

扫描 benchmark/reference_corpus/ 全部章节，用正则+关键词匹配抽取章末/章首/章中的
钩子实例，按类型分类，输出 data/hook_patterns.json（≥200 条）。

用法:
    python scripts/mine_hook_patterns.py [--corpus-dir PATH] [--output PATH]
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
REFERENCE_DIR = BENCHMARK_DIR / "reference_corpus"
DATA_DIR = REPO_ROOT / "data"
DEFAULT_OUTPUT = DATA_DIR / "hook_patterns.json"


# ---------------------------------------------------------------------------
# Hook type taxonomy (aligned with reader-pull-checker)
# ---------------------------------------------------------------------------
HOOK_TYPES = ["crisis", "mystery", "emotion", "choice", "desire"]

POSITION_TYPES = ["open", "mid", "cliff"]

# ---------------------------------------------------------------------------
# Pattern definitions: (regex, hook_type, position, payoff_window_chapters)
# ---------------------------------------------------------------------------

CLIFF_PATTERNS: list[tuple[str, str, int, str]] = [
    # (regex, hook_type, payoff_window, description)
    # --- Mystery hooks ---
    (r"究竟.{0,20}[？?]", "mystery", 3, "究竟疑问句"),
    (r"到底.{0,20}[？?]", "mystery", 3, "到底疑问句"),
    (r"难道.{0,20}[？?]", "mystery", 2, "难道反问"),
    (r"[这那].{0,10}怎么可能", "mystery", 2, "不可能质疑"),
    (r"发生了什么", "mystery", 1, "事件悬念"),
    (r"[他她].*?是谁", "mystery", 5, "身份悬念"),
    (r"这.{0,6}秘密", "mystery", 10, "秘密引出"),
    (r"真相.{0,10}[？?]", "mystery", 5, "真相追问"),
    (r"隐藏.{0,10}什么", "mystery", 5, "隐藏信息"),
    (r"[这那].{0,6}意味着", "mystery", 3, "含义悬念"),
    (r"谜[底团].{0,10}[？?]", "mystery", 5, "谜团句"),
    (r"蹊跷", "mystery", 3, "蹊跷暗示"),
    (r"诡异.{0,6}[的地]", "mystery", 3, "诡异描写"),
    (r"[没无]人知道", "mystery", 5, "未知信息"),
    (r"答案.{0,10}[？?]", "mystery", 3, "答案悬念"),
    (r"为什么.{0,20}[？?]", "mystery", 3, "为什么追问"),
    (r"[这那]个人", "mystery", 3, "神秘人物"),
    (r"原来.{0,10}[是就]", "mystery", 1, "真相揭露"),
    (r"竟[然是]", "mystery", 2, "意外发现"),
    (r"不[，,].{0,10}不是", "mystery", 2, "否定认知"),
    (r"莫非.{0,15}[？?]", "mystery", 3, "莫非猜测"),
    (r"如果.{0,15}[呢？?]", "mystery", 3, "假设疑问"),
    (r"[他她]究竟", "mystery", 3, "他究竟"),
    (r"[怪奇]异", "mystery", 3, "怪异现象"),
    (r"似乎.{0,10}[不没]对", "mystery", 2, "似乎不对"),

    # --- Crisis hooks ---
    (r"不可能[！!]", "crisis", 1, "不可能惊叹"),
    (r"却[没不]想到", "crisis", 1, "意外转折"),
    (r"然而[，,]", "crisis", 1, "转折连词"),
    (r"可就在这时", "crisis", 1, "突发事件"),
    (r"突然[，,]", "crisis", 1, "突然转折"),
    (r"危[险机].{0,10}[来临降]", "crisis", 2, "危机降临"),
    (r"大难临头", "crisis", 1, "大难临头"),
    (r"[他她].*?倒[下了]", "crisis", 2, "角色倒下"),
    (r"鲜血.{0,10}[流喷涌]", "crisis", 1, "流血描写"),
    (r"[重致]伤", "crisis", 2, "受伤"),
    (r"[他她].*?消失", "crisis", 3, "角色消失"),
    (r"一切.*?改变", "crisis", 2, "局势剧变"),
    (r"还没有结束", "crisis", 1, "危机延续"),
    (r"才刚刚开始", "crisis", 2, "危机开始"),
    (r"来不及了", "crisis", 1, "时间紧迫"),
    (r"逃[！!]", "crisis", 1, "逃命"),
    (r"快[跑走逃闪][！!]", "crisis", 1, "逃命呼喊"),
    (r"完了[！!]", "crisis", 1, "绝望惊呼"),
    (r"死[定了！!]", "crisis", 2, "死亡威胁"),
    (r"杀.{0,6}[他她你我]", "crisis", 2, "杀意"),
    (r"中[了计毒]", "crisis", 2, "中计中毒"),
    (r"[他她].*?[吐喷]血", "crisis", 2, "吐血受创"),
    (r"天[崩塌裂]", "crisis", 3, "天崩地裂"),
    (r"爆炸", "crisis", 1, "爆炸"),
    (r"围[住困]", "crisis", 2, "包围"),
    (r"陷[阱入]", "crisis", 2, "陷阱"),
    (r"毒[！!，,]", "crisis", 2, "毒素"),
    (r"背叛", "crisis", 3, "背叛"),
    (r"[他她].*?叛变", "crisis", 3, "叛变"),
    (r"敌[人袭]", "crisis", 2, "敌袭"),
    (r"[他她].*?[跌摔]", "crisis", 1, "跌落"),

    # --- Emotion hooks ---
    (r"[他她它].*?笑了", "emotion", 2, "意味深长的笑"),
    (r"泪.{0,6}[流落下]", "emotion", 2, "流泪"),
    (r"心[中里].{0,10}[痛疼]", "emotion", 3, "心痛"),
    (r"[他她].*?哭了", "emotion", 2, "哭泣"),
    (r"再也.{0,10}不[能会]", "emotion", 5, "永别暗示"),
    (r"对不起", "emotion", 3, "道歉"),
    (r"我[爱喜欢]你", "emotion", 5, "告白"),
    (r"别[走离]开", "emotion", 3, "挽留"),
    (r"[他她].*?转身[离走]", "emotion", 2, "离别"),
    (r"永远.{0,6}[不再没]", "emotion", 5, "永别宣言"),
    (r"[他她].*?[紧握抓]住", "emotion", 2, "紧握不放"),
    (r"[他她].*?闭上眼", "emotion", 2, "闭眼场景"),
    (r"谢谢你", "emotion", 2, "感恩"),
    (r"[他她].*?沉默", "emotion", 2, "沉默"),
    (r"声音.{0,6}[颤哽]", "emotion", 2, "声音颤抖"),
    (r"眼[眶中].{0,6}[红湿]", "emotion", 2, "眼眶湿润"),
    (r"[他她].*?抱住", "emotion", 2, "拥抱"),
    (r"[他她].*?跪[下了]", "emotion", 3, "下跪"),

    # --- Desire hooks ---
    (r"一道.{0,10}[声光影]", "desire", 1, "神秘出现"),
    (r"一个.{0,10}出现", "desire", 1, "人物出现"),
    (r"下一刻", "desire", 1, "即将发生"),
    (r"瞬间[，,]", "desire", 1, "瞬间转变"),
    (r"终于.{0,6}[到来了]", "desire", 1, "期待兑现"),
    (r"就[要差快].*?[成了]", "desire", 2, "即将成功"),
    (r"[他她].*?突破", "desire", 1, "突破预兆"),
    (r"机[会缘].{0,10}[来到]", "desire", 2, "机会降临"),
    (r"宝[物藏].{0,10}[现出]", "desire", 3, "宝物出现"),
    (r"传承", "desire", 3, "传承机缘"),
    (r"[他她].*?睁开眼", "desire", 1, "睁眼觉醒"),
    (r"[金光芒].{0,6}[闪亮耀]", "desire", 1, "金光闪耀"),
    (r"晋[级升]", "desire", 2, "晋级"),
    (r"[他她].*?站[起了]来", "desire", 1, "站起来"),
    (r"成功了[！!]", "desire", 1, "成功惊呼"),
    (r"[他她].*?醒[来了过]", "desire", 1, "苏醒"),
    (r"回来了", "desire", 1, "归来"),
    (r"[他她].*?赢了", "desire", 1, "胜利"),

    # --- Choice hooks ---
    (r"是.{2,15}还是", "choice", 2, "二选一"),
    (r"[他她].*?犹豫", "choice", 1, "犹豫不决"),
    (r"必须.{0,10}选择", "choice", 2, "强制选择"),
    (r"两[条个].{0,10}路", "choice", 2, "两条路"),
    (r"来人[！!]", "choice", 1, "来人呼唤"),
    (r"谁[！!？?]", "choice", 1, "身份质问"),
    (r"你[！!]", "choice", 1, "指认"),
    (r"[他她].*?决定", "choice", 2, "做出决定"),
    (r"要[不否]要", "choice", 1, "要不要"),
    (r"[能否].{0,10}[？?]", "choice", 2, "能否疑问"),
    (r"答[应不]答应", "choice", 2, "答应与否"),
    (r"[走留]下", "choice", 2, "走还是留"),
]

OPEN_PATTERNS: list[tuple[str, str, int, str]] = [
    # Crisis openings
    (r"^.{0,20}[！!]$", "crisis", 1, "惊叹句开头"),
    (r"^.{0,10}[？?]$", "mystery", 2, "疑问句开头"),
    (r"[痛死危]", "crisis", 1, "危险词开头"),
    (r"砰|轰|啪|咔|嘭", "crisis", 1, "拟声词开头"),
    (r"不[！!]", "crisis", 1, "否定惊叹开头"),
    (r"小心[！!]", "crisis", 1, "警告开头"),
    (r"快[跑走逃闪]", "crisis", 1, "逃命开头"),
    (r"血", "crisis", 2, "血腥开头"),
    (r"杀", "crisis", 2, "杀意开头"),

    # Emotion openings
    (r"泪", "emotion", 2, "泪水开头"),
    (r"[他她].*?醒", "mystery", 1, "苏醒开头"),

    # Mystery openings
    (r"奇怪", "mystery", 3, "奇怪开头"),
    (r"异常", "mystery", 3, "异常开头"),
    (r"[这那]不对", "mystery", 2, "不对劲开头"),
    (r"梦", "mystery", 3, "梦境开头"),
    (r"回忆", "emotion", 3, "回忆开头"),

    # Desire openings
    (r"阳光", "desire", 2, "阳光开头"),
    (r"终于", "desire", 1, "终于开头"),
    (r"今天", "desire", 2, "今天开头"),

    # Dialogue openings
    (r'^"', "emotion", 2, "对话开头"),
    (r"^「", "emotion", 2, "对话开头书名号"),
    (r"^\u201c", "emotion", 2, "对话开头中文引号"),
]

MID_PATTERNS: list[tuple[str, str, int, str]] = [
    # Mid-chapter tension builders
    (r"[他她].*?[突忽]然.{0,10}[停住顿]", "mystery", 1, "突然停顿"),
    (r"不对[！!，,]", "mystery", 1, "不对劲"),
    (r"[他她].*?脸色[大骤突]变", "crisis", 1, "脸色大变"),
    (r"糟[了糕][！!]", "crisis", 1, "糟糕惊呼"),
    (r"一股.{0,10}[气息力量]", "desire", 2, "力量涌现"),
    (r"[心脑]海中.{0,10}[闪浮]", "mystery", 2, "灵光一闪"),
    (r"直觉告诉[他她]", "crisis", 2, "直觉警告"),
    (r"[他她].*?注意到", "mystery", 1, "注意到异常"),
    (r"[他她].*?发现", "mystery", 1, "发现异常"),
    (r"但[是却].{0,10}[没不无]", "crisis", 1, "但是转折"),
    (r"忽然.{0,10}[响传来]", "crisis", 1, "忽然声响"),
    (r"与此同时", "crisis", 2, "同时暗线"),
    (r"另一边", "crisis", 2, "暗线切换"),
    (r"谁也没想到", "mystery", 2, "意外事件"),
    (r"[他她].*?感觉到.{0,10}[不异]", "mystery", 2, "异常感知"),
    (r"[他她].*?皱[眉了]", "mystery", 1, "皱眉疑惑"),
    (r"等等[！!，,]", "crisis", 1, "等等打断"),
    (r"[他她].*?[回扭]头", "mystery", 1, "回头发现"),
    (r"有人.{0,6}[跟在偷]", "crisis", 2, "被跟踪"),
    (r"一股.{0,6}杀[意气]", "crisis", 2, "杀意涌现"),
    (r"[他她].*?[僵凝呆]", "crisis", 1, "角色僵住"),
    (r"气氛.{0,6}[变凝]", "crisis", 1, "气氛骤变"),
    (r"[他她].*?想起", "mystery", 2, "想起关键"),
    (r"[他她].*?看[到见]", "mystery", 1, "看到异常"),
    (r"门.{0,6}[开推被]", "mystery", 1, "门被打开"),
    (r"[他她].*?停[下住]", "crisis", 1, "突然停下"),
    (r"[他她].*?咬[牙了]", "choice", 1, "咬牙决心"),
    (r"时间.{0,6}[不来到]", "crisis", 1, "时间紧迫"),
    (r"[一只双].{0,6}眼[睛瞳]", "mystery", 2, "目光注视"),
    (r"影[子像].{0,6}[闪掠动]", "mystery", 2, "暗影闪过"),
]

# ---------------------------------------------------------------------------
# Genre-specific hook templates (not mined, but genre-enriched)
# ---------------------------------------------------------------------------

GENRE_HOOK_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "玄幻": [
        {"type": "desire", "trigger_template": "突破境界的前兆出现", "payoff_window": 2},
        {"type": "crisis", "trigger_template": "天劫降临/异象引来强敌", "payoff_window": 3},
        {"type": "mystery", "trigger_template": "血脉/传承的隐藏信息浮现", "payoff_window": 5},
        {"type": "desire", "trigger_template": "神器/丹药/秘法即将到手", "payoff_window": 2},
        {"type": "choice", "trigger_template": "宗门利益与个人道义冲突", "payoff_window": 3},
    ],
    "仙侠": [
        {"type": "mystery", "trigger_template": "前世记忆碎片浮现", "payoff_window": 10},
        {"type": "crisis", "trigger_template": "心魔/劫数突至", "payoff_window": 2},
        {"type": "desire", "trigger_template": "悟道/证道的关键契机", "payoff_window": 3},
        {"type": "emotion", "trigger_template": "道侣/师门的生离死别", "payoff_window": 5},
        {"type": "choice", "trigger_template": "斩情还是入魔的两难", "payoff_window": 3},
    ],
    "都市": [
        {"type": "crisis", "trigger_template": "商业阴谋/陷害被揭发", "payoff_window": 3},
        {"type": "desire", "trigger_template": "重大项目/交易即将成功", "payoff_window": 2},
        {"type": "emotion", "trigger_template": "感情纠葛中的误会/真相", "payoff_window": 3},
        {"type": "mystery", "trigger_template": "身份/身世的关键线索", "payoff_window": 5},
        {"type": "choice", "trigger_template": "亲情与事业的冲突抉择", "payoff_window": 2},
    ],
    "科幻": [
        {"type": "mystery", "trigger_template": "未知信号/异常数据出现", "payoff_window": 5},
        {"type": "crisis", "trigger_template": "系统崩溃/外星威胁逼近", "payoff_window": 2},
        {"type": "desire", "trigger_template": "技术突破/文明跃升在即", "payoff_window": 3},
        {"type": "choice", "trigger_template": "人性与理性的终极抉择", "payoff_window": 3},
        {"type": "emotion", "trigger_template": "AI/克隆体的情感觉醒", "payoff_window": 5},
    ],
    "游戏": [
        {"type": "desire", "trigger_template": "隐藏任务/稀有掉落出现", "payoff_window": 2},
        {"type": "crisis", "trigger_template": "公会战/BOSS战形势逆转", "payoff_window": 1},
        {"type": "mystery", "trigger_template": "游戏世界的隐藏真相", "payoff_window": 10},
        {"type": "choice", "trigger_template": "队友利益与个人收益冲突", "payoff_window": 2},
        {"type": "emotion", "trigger_template": "虚拟与现实的情感交织", "payoff_window": 5},
    ],
    "悬疑": [
        {"type": "mystery", "trigger_template": "关键证据/线索被发现", "payoff_window": 5},
        {"type": "crisis", "trigger_template": "凶手/威胁逼近主角", "payoff_window": 1},
        {"type": "choice", "trigger_template": "正义与私情的抉择", "payoff_window": 3},
        {"type": "emotion", "trigger_template": "受害者/嫌疑人的悲惨过往", "payoff_window": 3},
        {"type": "desire", "trigger_template": "真相即将水落石出", "payoff_window": 2},
    ],
    "历史": [
        {"type": "crisis", "trigger_template": "朝堂政变/战争爆发", "payoff_window": 3},
        {"type": "mystery", "trigger_template": "历史事件的隐秘真相", "payoff_window": 10},
        {"type": "choice", "trigger_template": "忠君与救民的两难", "payoff_window": 3},
        {"type": "emotion", "trigger_template": "家国情怀与个人命运交织", "payoff_window": 5},
        {"type": "desire", "trigger_template": "改变历史走向的关键时刻", "payoff_window": 2},
    ],
    "轻小说": [
        {"type": "emotion", "trigger_template": "告白/误会/心动瞬间", "payoff_window": 2},
        {"type": "mystery", "trigger_template": "角色的隐藏身份/过去", "payoff_window": 5},
        {"type": "crisis", "trigger_template": "关系危机/三角关系爆发", "payoff_window": 3},
        {"type": "desire", "trigger_template": "校园活动/比赛的高潮时刻", "payoff_window": 1},
        {"type": "choice", "trigger_template": "友情与爱情的选择", "payoff_window": 3},
    ],
    "末日": [
        {"type": "crisis", "trigger_template": "丧尸潮/异变潮来袭", "payoff_window": 1},
        {"type": "desire", "trigger_template": "安全区/物资/队友汇合", "payoff_window": 2},
        {"type": "mystery", "trigger_template": "灾变的真正起因线索", "payoff_window": 10},
        {"type": "choice", "trigger_template": "救人还是保全自己", "payoff_window": 1},
        {"type": "emotion", "trigger_template": "同伴牺牲/团队裂变", "payoff_window": 3},
    ],
    "克苏鲁": [
        {"type": "mystery", "trigger_template": "已知规则出现反常例外", "payoff_window": 5},
        {"type": "crisis", "trigger_template": "封印失效/污染扩散", "payoff_window": 2},
        {"type": "choice", "trigger_template": "救同伴还是阻断仪式", "payoff_window": 1},
        {"type": "emotion", "trigger_template": "理智值临界/记忆缺口", "payoff_window": 3},
        {"type": "desire", "trigger_template": "关键生存规则被确认", "payoff_window": 2},
    ],
    "电竞": [
        {"type": "crisis", "trigger_template": "对手临时换阵/核心战术被针对", "payoff_window": 1},
        {"type": "choice", "trigger_template": "保守拿分vs搏命翻盘", "payoff_window": 1},
        {"type": "desire", "trigger_template": "晋级只差一局", "payoff_window": 1},
        {"type": "emotion", "trigger_template": "队友公开承担责任/舆论撕裂", "payoff_window": 2},
        {"type": "mystery", "trigger_template": "对手隐藏战术被发现端倪", "payoff_window": 3},
    ],
    "直播文": [
        {"type": "crisis", "trigger_template": "直播切片被恶意剪辑上热搜", "payoff_window": 2},
        {"type": "choice", "trigger_template": "立刻回应还是拿证据反杀", "payoff_window": 2},
        {"type": "desire", "trigger_template": "平台首页推荐位只差最后一档", "payoff_window": 1},
        {"type": "emotion", "trigger_template": "核心粉丝团疑似倒戈", "payoff_window": 2},
        {"type": "mystery", "trigger_template": "爆料线索坐实/证据链闭环", "payoff_window": 3},
    ],
    "系统流": [
        {"type": "desire", "trigger_template": "系统奖励/新技能即将解锁", "payoff_window": 1},
        {"type": "mystery", "trigger_template": "系统隐藏功能/真正目的浮现", "payoff_window": 10},
        {"type": "crisis", "trigger_template": "系统惩罚/任务失败倒计时", "payoff_window": 1},
        {"type": "choice", "trigger_template": "两个系统任务互相矛盾", "payoff_window": 2},
        {"type": "emotion", "trigger_template": "系统绑定者之间的羁绊", "payoff_window": 5},
    ],
    "穿越": [
        {"type": "mystery", "trigger_template": "历史走向开始偏离/蝴蝶效应", "payoff_window": 5},
        {"type": "crisis", "trigger_template": "身份暴露危机/历史纠错力量", "payoff_window": 2},
        {"type": "desire", "trigger_template": "利用先知优势即将成功", "payoff_window": 1},
        {"type": "choice", "trigger_template": "改变历史还是顺应宿命", "payoff_window": 3},
        {"type": "emotion", "trigger_template": "与古人建立真挚感情后的离别预感", "payoff_window": 5},
    ],
}


def _pattern_id(regex: str, position: str, hook_type: str) -> str:
    h = hashlib.md5(f"{position}:{hook_type}:{regex}".encode()).hexdigest()[:8]
    return f"HP-{position[0].upper()}{hook_type[0].upper()}-{h}"


def _genre_pattern_id(genre: str, hook_type: str, idx: int) -> str:
    h = hashlib.md5(f"genre:{genre}:{hook_type}:{idx}".encode()).hexdigest()[:8]
    return f"HP-G{hook_type[0].upper()}-{h}"


def _extract_snippet(text: str, match: re.Match, context_chars: int = 40) -> str:
    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def scan_chapter(
    text: str,
    chapter_num: int,
    book_title: str,
) -> list[dict[str, Any]]:
    """Scan a single chapter for hook pattern matches."""
    results: list[dict[str, Any]] = []
    lines = text.strip().split("\n")
    if not lines:
        return results

    tail_text = "\n".join(lines[-15:]) if len(lines) >= 15 else text
    head_text = "\n".join(lines[:8]) if len(lines) >= 8 else text

    for regex, hook_type, payoff_window, desc in CLIFF_PATTERNS:
        for m in re.finditer(regex, tail_text):
            results.append({
                "regex": regex,
                "hook_type": hook_type,
                "position": "cliff",
                "payoff_window_chapters": payoff_window,
                "description": desc,
                "matched_text": m.group(),
                "snippet": _extract_snippet(tail_text, m),
                "source_ref": f"{book_title}/ch{chapter_num:03d}",
            })

    for regex, hook_type, payoff_window, desc in OPEN_PATTERNS:
        for m in re.finditer(regex, head_text):
            results.append({
                "regex": regex,
                "hook_type": hook_type,
                "position": "open",
                "payoff_window_chapters": payoff_window,
                "description": desc,
                "matched_text": m.group(),
                "snippet": _extract_snippet(head_text, m),
                "source_ref": f"{book_title}/ch{chapter_num:03d}",
            })

    mid_text = "\n".join(lines[5:-10]) if len(lines) > 20 else text
    for regex, hook_type, payoff_window, desc in MID_PATTERNS:
        matches = list(re.finditer(regex, mid_text))
        for m in matches[:3]:
            results.append({
                "regex": regex,
                "hook_type": hook_type,
                "position": "mid",
                "payoff_window_chapters": payoff_window,
                "description": desc,
                "matched_text": m.group(),
                "snippet": _extract_snippet(mid_text, m),
                "source_ref": f"{book_title}/ch{chapter_num:03d}",
            })

    return results


def read_chapter_text(book_dir: Path, ch_num: int) -> str | None:
    candidates = [
        book_dir / "chapters" / f"ch{ch_num:03d}.txt",
        book_dir / "chapters" / f"ch{ch_num:02d}.txt",
        book_dir / "chapters" / f"chapter_{ch_num}.txt",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def deduplicate_to_patterns(
    raw_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate raw matches into unique pattern entries with example counts."""
    grouped: dict[str, dict[str, Any]] = {}

    for m in raw_matches:
        key = f"{m['position']}:{m['hook_type']}:{m['regex']}"
        if key not in grouped:
            pid = _pattern_id(m["regex"], m["position"], m["hook_type"])
            grouped[key] = {
                "id": pid,
                "type": m["hook_type"],
                "position": m["position"],
                "trigger_template": m["regex"],
                "trigger_description": m["description"],
                "payoff_window_chapters": m["payoff_window_chapters"],
                "example_count": 0,
                "examples": [],
                "source_refs": [],
            }

        entry = grouped[key]
        entry["example_count"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append({
                "matched_text": m["matched_text"],
                "snippet": m["snippet"],
            })
        if len(entry["source_refs"]) < 5:
            ref = m["source_ref"]
            if ref not in entry["source_refs"]:
                entry["source_refs"].append(ref)

    return list(grouped.values())


def build_genre_patterns() -> list[dict[str, Any]]:
    """Build genre-specific hook template patterns."""
    patterns = []
    for genre, templates in GENRE_HOOK_TEMPLATES.items():
        for idx, tmpl in enumerate(templates):
            pid = _genre_pattern_id(genre, tmpl["type"], idx)
            patterns.append({
                "id": pid,
                "type": tmpl["type"],
                "position": "cliff",
                "trigger_template": tmpl["trigger_template"],
                "trigger_description": f"{genre}题材钩子模板",
                "payoff_window_chapters": tmpl["payoff_window"],
                "genre": genre,
                "example_count": 0,
                "examples": [],
                "source_refs": [],
            })
    return patterns


def mine_hook_patterns(
    corpus_dir: Path = REFERENCE_DIR,
    max_chapters_per_book: int = 30,
) -> dict[str, Any]:
    """Mine hook patterns from the reference corpus."""
    if not corpus_dir.exists():
        raise FileNotFoundError(f"Reference corpus not found: {corpus_dir}")

    all_matches: list[dict[str, Any]] = []
    books_scanned = 0
    chapters_scanned = 0

    book_dirs = sorted(
        [d for d in corpus_dir.iterdir() if d.is_dir() and (d / "manifest.json").exists()]
    )

    for book_dir in book_dirs:
        manifest_path = book_dir / "manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        title = manifest.get("title", book_dir.name)
        ch_count = min(manifest.get("chapters_count", 30), max_chapters_per_book)
        books_scanned += 1

        for ch in range(1, ch_count + 1):
            text = read_chapter_text(book_dir, ch)
            if not text or len(text) < 200:
                continue
            chapters_scanned += 1
            matches = scan_chapter(text, ch, title)
            all_matches.extend(matches)

    mined_patterns = deduplicate_to_patterns(all_matches)
    genre_patterns = build_genre_patterns()
    all_patterns = mined_patterns + genre_patterns

    for i, p in enumerate(all_patterns):
        p["id"] = p.get("id", f"HP-{i:04d}")

    type_counts = defaultdict(int)
    position_counts = defaultdict(int)
    for p in all_patterns:
        type_counts[p["type"]] += 1
        position_counts[p["position"]] += 1

    return {
        "version": "1.0.0",
        "description": "Hook patterns mined from reference corpus + genre templates",
        "stats": {
            "total_patterns": len(all_patterns),
            "books_scanned": books_scanned,
            "chapters_scanned": chapters_scanned,
            "raw_matches": len(all_matches),
            "by_type": dict(type_counts),
            "by_position": dict(position_counts),
        },
        "patterns": all_patterns,
    }


def save_patterns(data: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine hook patterns from reference corpus")
    parser.add_argument("--corpus-dir", type=Path, default=REFERENCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-chapters", type=int, default=30)
    args = parser.parse_args()

    data = mine_hook_patterns(
        corpus_dir=args.corpus_dir,
        max_chapters_per_book=args.max_chapters,
    )

    save_patterns(data, args.output)

    print(f"Mined {data['stats']['total_patterns']} hook patterns")
    print(f"  Books scanned: {data['stats']['books_scanned']}")
    print(f"  Chapters scanned: {data['stats']['chapters_scanned']}")
    print(f"  Raw matches: {data['stats']['raw_matches']}")
    print(f"  By type: {dict(data['stats']['by_type'])}")
    print(f"  By position: {dict(data['stats']['by_position'])}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
