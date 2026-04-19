"""Phase-Seed-1 Batch 2/10 — era 类 100 条入库脚本。

按 R1/R2/R3/R4/R5 = 5/20/25/30/20 分布生成时代类种子，
20 条 human（用户 review 通过）+ 80 条 llm，追加到 anti-trope-seeds.json，
更新 version→v1.2、total→200、changelog。

避开 era-001（2003 非典夏天）、era-002（末世第 47 日）及 WebSearch 黑名单。
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

import json
from pathlib import Path

SEEDS_FILE = (
    Path(__file__).resolve().parents[1]
    / "ink-writer"
    / "skills"
    / "ink-init"
    / "references"
    / "creativity"
    / "anti-trope-seeds.json"
)


def mk(seed_id, value, rarity, tags, pairing, source, meta=None):
    obj = {
        "seed_id": seed_id,
        "category": "era",
        "value": value,
        "rarity": rarity,
        "genre_tags": tags,
        "example_pairing": pairing,
        "source": source,
    }
    if meta:
        obj["meta_rules_hit"] = meta
    return obj


# ---------------------------------------------------------------------------
# R1 常见 (5 条) — 日常时间锚
# ---------------------------------------------------------------------------
R1 = [
    mk("era-003", "月末发工资日", 1, ["universal"],
       "与 profession『药店夜班售货员』搭配，激活 M09 权力颗粒度。",
       "human", ["M09"]),
    mk("era-004", "立冬前最后一个黄昏", 1, ["universal"],
       "与 emotion『对失败的眷恋』搭配，激活 M07 欲望悖论。",
       "human", ["M07"]),
    mk("era-005", "周日下午四点", 1, ["universal"],
       "与 profession『殡仪接待员』搭配，激活 M03 信息不对称。",
       "llm"),
    mk("era-006", "开学第一周", 1, ["urban", "realistic"],
       "与 object『一张被改过的成绩单』搭配，激活 M09 权力颗粒度。",
       "llm"),
    mk("era-007", "春节前三天", 1, ["universal"],
       "与 taboo『不得在祖宗牌位前数钱』搭配，激活 M03。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 偏常见 (20 条) — 现代公共事件切片
# ---------------------------------------------------------------------------
R2 = [
    mk("era-008", "1999 年千禧年倒计时最后五分钟", 2, ["urban", "realistic"],
       "与 object『1987 年中奖彩票存根』搭配，激活 M05 时空错位。",
       "human", ["M05"]),
    mk("era-009", "2001 年中国入世前夕", 2, ["urban", "realistic"],
       "与 profession『外贸单证员』搭配，激活 M09 权力颗粒度。",
       "human", ["M09"]),
    mk("era-010", "1986 年切尔诺贝利首日", 2, ["scifi", "apocalypse"],
       "与 worldview『空气里有味道的生物』搭配，激活 M10 尺度跃迁。",
       "human", ["M10"]),
    mk("era-011", "2015 年股灾那个周一早上", 2, ["urban", "realistic"],
       "与 profession『营业部大堂经理』搭配，激活 M01 代价可视化。",
       "human", ["M01"]),
    mk("era-012", "1997 年香港回归夜", 2, ["realistic", "history"],
       "与 object『一本尚未贴完的回归纪念邮册』搭配，激活 M05。",
       "llm"),
    mk("era-013", "2008 年北京奥运开幕后一周", 2, ["realistic", "urban"],
       "与 emotion『集体狂欢之后的空落』搭配，激活 M07。",
       "llm"),
    mk("era-014", "2020 年封城第一天", 2, ["realistic", "urban"],
       "与 profession『社区团购团长』搭配，激活 M01+M09。",
       "llm"),
    mk("era-015", "1989 年柏林墙倒塌那一夜", 2, ["realistic", "history"],
       "与 object『一块水泥碎片』搭配，激活 M05 时空错位。",
       "llm"),
    mk("era-016", "1984 年洛杉矶奥运归国班机", 2, ["realistic", "history"],
       "与 profession『随队翻译』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-017", "1978 年十一届三中全会前夕", 2, ["history", "realistic"],
       "与 profession『公社会计』搭配，激活 M09 权力颗粒度。",
       "llm"),
    mk("era-018", "2014 年马航 MH370 失联当晚", 2, ["realistic", "mystery"],
       "与 body_feature『颈后一小点永不褪色的痣』搭配，激活 M08。",
       "llm"),
    mk("era-019", "2012 年玛雅末日流言那一周", 2, ["apocalypse", "urban"],
       "与 taboo『那一周不得预约明年的手术』搭配，激活 M07。",
       "llm"),
    mk("era-020", "2006 年青藏铁路通车首班", 2, ["realistic", "history"],
       "与 profession『氧气瓶维护员』搭配，激活 M01 代价可视化。",
       "llm"),
    mk("era-021", "2005 年神六返回舱着陆瞬间", 2, ["scifi", "realistic"],
       "与 taboo_language『着陆前禁止对讲机里说「完」字』搭配，激活 M03。",
       "llm"),
    mk("era-022", "2011 年本·拉登击毙日", 2, ["realistic"],
       "与 profession『夜班国际新闻编辑』搭配，激活 M03 信息不对称。",
       "llm"),
    mk("era-023", "1994 年分税制改革前一夜", 2, ["history", "realistic"],
       "与 profession『县级税务所出纳』搭配，激活 M09。",
       "llm"),
    mk("era-024", "1992 年邓小平南巡首讲那日", 2, ["history", "realistic"],
       "与 emotion『风向翻页前的犹豫』搭配，激活 M07。",
       "llm"),
    mk("era-025", "1985 年居民身份证启用首日", 2, ["realistic", "history"],
       "与 object『一张写错名字的身份证』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-026", "2013 年 H7N9 首例报告日", 2, ["realistic", "apocalypse"],
       "与 profession『禽类批发市场收银员』搭配，激活 M01。",
       "llm"),
    mk("era-027", "1982 年现行宪法颁布当日", 2, ["history", "realistic"],
       "与 taboo『条文被抄错一个字不得外传』搭配，激活 M03。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 中等稀缺 (25 条) — 冷门朝代切片/节气/冷门历史节点
# ---------------------------------------------------------------------------
R3 = [
    mk("era-028", "辽国天庆五年秋", 3, ["history"],
       "与 taboo『使节不得回头看御座』搭配，激活 M03 信息不对称。",
       "human", ["M03"]),
    mk("era-029", "1911 年武昌首义后第三夜", 3, ["history", "realistic"],
       "与 taboo_language『旗人请安的「喳」改说「是」』搭配，激活 M06。",
       "human", ["M06"]),
    mk("era-030", "1950 年抗美援朝首批入朝前夜", 3, ["history", "realistic"],
       "与 object『一封未寄出的家书』搭配，激活 M01 代价可视化。",
       "human", ["M01"]),
    mk("era-031", "1976 年唐山大地震前七小时", 3, ["urban", "realistic", "mystery"],
       "与 body_feature『后颈一小片红斑发热』搭配，激活 M08 系统反噬。",
       "human", ["M08"]),
    mk("era-032", "二十四节气「大雪」黎明", 3, ["xianxia", "mystery"],
       "与 mythology『山神在雪前下山收账』搭配，激活 M05 时空错位。",
       "human", ["M05"]),
    mk("era-033", "五代后唐明宗长兴三年冬", 3, ["history"],
       "与 profession『内廷起居郎』搭配，激活 M09 权力颗粒度。",
       "llm"),
    mk("era-034", "北宋徽宗宣和七年除夕", 3, ["history"],
       "与 object『一柄汴京金明池赐宴牌』搭配，激活 M05。",
       "llm"),
    mk("era-035", "南明永历十三年滇西残冬", 3, ["history"],
       "与 taboo『正朔二字不得妄用』搭配，激活 M03。",
       "llm"),
    mk("era-036", "渤海国大仁秀在位初年", 3, ["history"],
       "与 profession『靺鞨语译官』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-037", "西夏天盛年末河西走廊", 3, ["history"],
       "与 taboo_language『党项秘字写错则斩』搭配，激活 M03+M01。",
       "llm"),
    mk("era-038", "金国大定二十九年秋收", 3, ["history"],
       "与 body_feature『耳垂缺口』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-039", "元朝至正二十五年立夏", 3, ["history"],
       "与 conflict『红巾军与元廷同日祭天』搭配，激活 M02 反向冲突。",
       "llm"),
    mk("era-040", "大清同治七年直隶大旱", 3, ["history", "realistic"],
       "与 profession『县衙粮秤校对吏』搭配，激活 M09+M01。",
       "llm"),
    mk("era-041", "1905 年废科举令颁布当日", 3, ["history"],
       "与 emotion『半生所学作废的空茫』搭配，激活 M07。",
       "llm"),
    mk("era-042", "1923 年临城劫车案当周", 3, ["history"],
       "与 profession『铁路三等乘务员』搭配，激活 M03。",
       "llm"),
    mk("era-043", "1936 年西安事变前一日", 3, ["history"],
       "与 object『一封未拆的密电』搭配，激活 M03。",
       "llm"),
    mk("era-044", "1945 年日本投降诏书当晚", 3, ["history"],
       "与 taboo『不得在家中开灯庆祝』搭配，激活 M03。",
       "llm"),
    mk("era-045", "1958 年大炼钢铁第一个春天", 3, ["history", "realistic"],
       "与 object『一口被砸掉一只耳的铁锅』搭配，激活 M01+M09。",
       "llm"),
    mk("era-046", "1971 年九一三事件之后第三天", 3, ["history"],
       "与 profession『机要秘书』搭配，激活 M03 信息不对称。",
       "llm"),
    mk("era-047", "1986 年义务教育法颁布那天", 3, ["history", "realistic"],
       "与 profession『民办教师转公办前夕』搭配，激活 M06。",
       "llm"),
    mk("era-048", "1997 年邓小平逝世当日早高峰", 3, ["realistic"],
       "与 taboo『广播员不得换声调』搭配，激活 M03。",
       "llm"),
    mk("era-049", "2003 年神五升空瞬间", 3, ["scifi", "realistic"],
       "与 profession『基地食堂值班员』搭配，激活 M09。",
       "llm"),
    mk("era-050", "2010 年上海世博闭幕夜", 3, ["urban", "realistic"],
       "与 profession『志愿者领队』搭配，激活 M07 欲望悖论。",
       "llm"),
    mk("era-051", "农历辛亥年立秋前一日", 3, ["history", "xianxia"],
       "与 taboo『那一日不得开仓放粮』搭配，激活 M08。",
       "llm"),
    mk("era-052", "惊蛰节气五更天", 3, ["xianxia", "mystery"],
       "与 body_feature『左肩被雷击过的白痕』搭配，激活 M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 稀缺 (30 条) — 微小切片/具体事件前后/非主流历史
# ---------------------------------------------------------------------------
R4 = [
    mk("era-053", "1998 年九江大堤合龙那一夜", 4, ["urban", "realistic"],
       "与 profession『水文值班员』搭配，激活 M01+M09。",
       "human", ["M01", "M09"]),
    mk("era-054", "1992 年上海股票认购证摇号当天", 4, ["urban", "realistic"],
       "与 object『一张未填姓名的认购证』搭配，激活 M09 权力颗粒度。",
       "human", ["M09"]),
    mk("era-055", "1969 年阿波罗登月时北京早八点", 4, ["scifi", "history"],
       "与 taboo『广播员不得解说此条外电』搭配，激活 M03 信息不对称。",
       "human", ["M03"]),
    mk("era-056", "1988 年海南建省前一天", 4, ["urban", "realistic"],
       "与 profession『公交票证经办员』搭配，激活 M05 时空错位。",
       "human", ["M05"]),
    mk("era-057", "唐朝安史之乱前第七年夏收", 4, ["history"],
       "与 body_feature『右手茧痕刚消』搭配，激活 M01 代价可视化。",
       "human", ["M01"]),
    mk("era-058", "2001 年 9·11 当晚的中国新闻联播", 4, ["urban", "realistic"],
       "与 profession『值夜班字幕员』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("era-059", "1987 年大兴安岭林火燃烧第三日", 4, ["realistic"],
       "与 emotion『远方烟火让人心安的愧疚』搭配，激活 M07。",
       "llm"),
    mk("era-060", "1980 年深圳划为特区那个黄昏", 4, ["realistic", "history"],
       "与 profession『边防证审核员』搭配，激活 M09 权力颗粒度。",
       "llm"),
    mk("era-061", "1985 年彩电凭票供应最后一周", 4, ["realistic"],
       "与 object『一张转让给陌生人的票』搭配，激活 M09+M01。",
       "llm"),
    mk("era-062", "1991 年苏联解体当夜的北京胡同", 4, ["realistic", "history"],
       "与 emotion『异乡的垮塌让本地人沉默』搭配，激活 M07。",
       "llm"),
    mk("era-063", "1993 年《活着》戛纳得奖日清晨", 4, ["realistic"],
       "与 profession『文化馆放映员』搭配，激活 M03。",
       "llm"),
    mk("era-064", "1995 年第一批寻呼机退市前夜", 4, ["realistic"],
       "与 object『一串未回复的数字留言』搭配，激活 M05。",
       "llm"),
    mk("era-065", "1996 年台海危机最紧张那一周", 4, ["realistic", "history"],
       "与 profession『海防连值夜哨兵』搭配，激活 M01。",
       "llm"),
    mk("era-066", "1999 年使馆被炸次日的新华社", 4, ["history", "realistic"],
       "与 taboo『新闻稿不得带数字之外的形容词』搭配，激活 M03。",
       "llm"),
    mk("era-067", "2000 年广电关停个人电台那个月", 4, ["urban", "realistic"],
       "与 profession『凌晨三点的调频 DJ』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-068", "2004 年印度洋海啸次日", 4, ["realistic", "apocalypse"],
       "与 body_feature『耳道里残留的海水』搭配，激活 M01。",
       "llm"),
    mk("era-069", "2007 年首届 iPhone 发布会中国午夜", 4, ["scifi", "realistic"],
       "与 profession『山寨机翻盖厂组长』搭配，激活 M10 尺度跃迁。",
       "llm"),
    mk("era-070", "2013 年雅安地震救援第 72 小时", 4, ["realistic"],
       "与 object『一张字迹被血浸透的寻人启事』搭配，激活 M01。",
       "llm"),
    mk("era-071", "2016 年英国脱欧公投揭晓日", 4, ["realistic"],
       "与 profession『驻伦敦外汇交易员』搭配，激活 M09。",
       "llm"),
    mk("era-072", "2017 年比特币跌破两万美元那夜", 4, ["urban", "realistic"],
       "与 emotion『数字归零时的轻微快感』搭配，激活 M07。",
       "llm"),
    mk("era-073", "2019 年巴黎圣母院大火首日", 4, ["realistic", "mystery"],
       "与 taboo『那一夜不得在钟楼下许愿』搭配，激活 M08。",
       "llm"),
    mk("era-074", "2022 年俄乌战争爆发次晨", 4, ["realistic", "apocalypse"],
       "与 profession『中欧班列调度员』搭配，激活 M09+M01。",
       "llm"),
    mk("era-075", "2025 年 AI 四级考试首次实施前夜", 4, ["scifi", "urban"],
       "与 profession『代考的文心机器人』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-076", "宋金绍兴议和前夜临安城", 4, ["history"],
       "与 taboo_language『不得在酒楼讲「北」字』搭配，激活 M03。",
       "llm"),
    mk("era-077", "元明鼎革前最后一个元宵", 4, ["history"],
       "与 object『一盏写着旧年号的花灯』搭配，激活 M05+M06。",
       "llm"),
    mk("era-078", "明末李自成破京前三日", 4, ["history"],
       "与 profession『午门守卒』搭配，激活 M01。",
       "llm"),
    mk("era-079", "1840 年鸦片战争宣战诏下达当晚", 4, ["history"],
       "与 profession『两广总督衙门六品笔帖式』搭配，激活 M09。",
       "llm"),
    mk("era-080", "清末光绪大婚当天紫禁城", 4, ["history"],
       "与 taboo『后宫不得同时熄灭两盏宫灯』搭配，激活 M03。",
       "llm"),
    mk("era-081", "民国十六年上海「四一二」前夜", 4, ["history", "realistic"],
       "与 profession『码头计件工人工头』搭配，激活 M09。",
       "llm"),
    mk("era-082", "1945 年无条件投降广播前八分钟", 4, ["history"],
       "与 profession『电台播音前值机员』搭配，激活 M03+M01。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 极稀缺 (20 条) — 文明纪元/历法交叠/被遗忘瞬间
# ---------------------------------------------------------------------------
R5 = [
    mk("era-083", "敦煌藏经洞 1900 年被打开那一天", 5, ["history", "mystery"],
       "与 object『一卷被揉过的经帙』搭配，激活 M05+M09。",
       "human", ["M05", "M09"]),
    mk("era-084", "玛雅长计历 13.0.0.0.0 东八区凌晨", 5, ["apocalypse", "scifi"],
       "与 worldview『每个文明的末日时刻同步重置』搭配，激活 M10 尺度跃迁。",
       "human", ["M10"]),
    mk("era-085", "农历甲子年甲子月甲子日甲子时", 5, ["xianxia", "mystery"],
       "与 taboo『不得在四甲之时报出自己姓氏』搭配，激活 M08 系统反噬。",
       "human", ["M08"]),
    mk("era-086", "太阳黑子第 25 活动周期峰值夜", 5, ["scifi", "apocalypse"],
       "与 worldview『所有电磁记忆当夜被回收』搭配，激活 M10。",
       "llm"),
    mk("era-087", "格里高利历颁布首日的大明浙江", 5, ["history"],
       "与 profession『民间择日先生』搭配，激活 M05+M09。",
       "llm"),
    mk("era-088", "民国黄帝纪元 4608 年", 5, ["history", "xianxia"],
       "与 taboo_language『奏折开头必称「黄帝」二字』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-089", "契丹保大五年二月十七酉时", 5, ["history"],
       "与 object『一枚鎏金符牌』搭配，激活 M09 权力颗粒度。",
       "llm"),
    mk("era-090", "夏商断代认定的武王伐纣那一日", 5, ["history", "xianxia"],
       "与 mythology『姜子牙钓台的星象』搭配，激活 M05+M10。",
       "llm"),
    mk("era-091", "太平天国天历己未九年天父节", 5, ["history"],
       "与 taboo『那一日不得称孔丘之名』搭配，激活 M03。",
       "llm"),
    mk("era-092", "金箓斋醮三元节中元酉时", 5, ["xianxia", "mystery"],
       "与 taboo_language『咒中不得夹汉字』搭配，激活 M08。",
       "llm"),
    mk("era-093", "伪满康德十年新京立春", 5, ["history"],
       "与 profession『满铁情报补录员』搭配，激活 M06 身份反差。",
       "llm"),
    mk("era-094", "侯景之乱前夜建康城楼头钟响", 5, ["history"],
       "与 body_feature『右耳失聪半日』搭配，激活 M01。",
       "llm"),
    mk("era-095", "阴山匈奴王庭坠星那一夜", 5, ["history", "xianxia"],
       "与 mythology『天狼与参宿四对饮』搭配，激活 M10。",
       "llm"),
    mk("era-096", "郑和第七次下西洋返航前新月", 5, ["history"],
       "与 object『一枚未送出的青花瓷碎片』搭配，激活 M05。",
       "llm"),
    mk("era-097", "回历 1399 年麦加清真寺事件当夜", 5, ["history", "mystery"],
       "与 taboo『朝拜队列不得回头』搭配，激活 M03+M08。",
       "llm"),
    mk("era-098", "印加「第五个太阳」纪元末日", 5, ["apocalypse", "universal"],
       "与 worldview『太阳四次熄灭人类四次重启』搭配，激活 M10。",
       "llm"),
    mk("era-099", "墨子止楚攻宋那一夜郢都", 5, ["history", "xianxia"],
       "与 conflict『以守代攻说服君主』搭配，激活 M02 反向冲突。",
       "llm"),
    mk("era-100", "阿拔斯白衣大食使节抵长安夜", 5, ["history"],
       "与 taboo_language『通事不得译错一个真主之名』搭配，激活 M03+M06。",
       "llm"),
    mk("era-101", "元丰八年司马光入阁前一刻", 5, ["history"],
       "与 emotion『旧政与新政之间那一口气』搭配，激活 M07。",
       "llm"),
    mk("era-102", "伽利略见木星四卫夜的大明南京", 5, ["history", "scifi"],
       "与 conflict『钦天监同夜记录失踪三星』搭配，激活 M05+M10。",
       "llm"),
]


ALL_SEEDS = R1 + R2 + R3 + R4 + R5


def main() -> None:
    # ---- 预检 ----
    from collections import Counter
    assert len(ALL_SEEDS) == 100, f"Expected 100 seeds, got {len(ALL_SEEDS)}"

    rarity_dist = Counter(s["rarity"] for s in ALL_SEEDS)
    expected = {1: 5, 2: 20, 3: 25, 4: 30, 5: 20}
    assert dict(rarity_dist) == expected, f"Rarity mismatch: {dict(rarity_dist)}"

    src_dist = Counter(s["source"] for s in ALL_SEEDS)
    assert src_dist["human"] == 20, f"human count {src_dist['human']} != 20"
    assert src_dist["llm"] == 80, f"llm count {src_dist['llm']} != 80"

    # 稀缺硬约束
    r4r5 = rarity_dist[4] + rarity_dist[5]
    assert r4r5 >= 50, f"R4+R5 = {r4r5} < 50"
    assert rarity_dist[5] >= 20, f"R5 = {rarity_dist[5]} < 20"

    # seed_id 唯一
    ids = [s["seed_id"] for s in ALL_SEEDS]
    assert len(set(ids)) == len(ids), "duplicate seed_id"

    # value 长度
    for s in ALL_SEEDS:
        assert 1 <= len(s["value"]) <= 40, f"bad value len: {s['seed_id']} ({len(s['value'])})"

    print(f"✓ 预检通过：100 条，分布 {dict(sorted(rarity_dist.items()))}，"
          f"human={src_dist['human']} llm={src_dist['llm']}")

    # ---- 入库 ----
    with SEEDS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # 校验当前状态
    assert data["version"] == "v1.1", f"unexpected current version: {data['version']}"
    assert data["total"] == 100, f"unexpected total: {data['total']}"
    existing_era = [s["seed_id"] for s in data["seeds"] if s["category"] == "era"]
    assert set(existing_era) == {"era-001", "era-002"}, f"unexpected era: {existing_era}"

    # 追加
    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 200
    data["version"] = "v1.2"
    data["changelog"].append({
        "version": "v1.2",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 2/10 时代类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频时代套路（七零八零九零穿越/清宫雍正康熙/明清崇祯正德/三国/"
            "南北朝/民国军阀/末世首日/核战废土/宫斗朝代/1988番茄爆款年份 等）。"
            "策略：精确到事件/节气/历法交叠/文明纪元/冷门朝代，避开朝代名直接堆砌。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 era 种子，version→v1.2，total→200")


if __name__ == "__main__":
    main()
