"""Phase-Seed-1 Batch 4/10 — worldview 类 100 条入库脚本。

R1/R2/R3/R4/R5 = 5/20/25/30/20，20 human + 80 llm，
追加到 anti-trope-seeds.json，更新 version→v1.4、total→400。

避开 worldview-001（说谎→白头发）及 WebSearch 黑名单：
修仙阶段（练气/筑基/金丹/元婴/化神/渡劫/飞升）、斗气九段、魔法九级、
洪荒封神、灵气复苏、天道系统、签到系统、诸天万界、主神空间、
人妖魔神四族、六道轮回、东玄西幻体系分层。

策略：抛弃"等级体系"，改用"一条精确规则 + 具体代价"，
每条都直接激活 M01/M03/M07/M08。
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
        "category": "worldview",
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
# R1 常见 (5 条) — 日常规则锚
# ---------------------------------------------------------------------------
R1 = [
    mk("worldview-002", "下雨天晾不干的衣服当日不会被认领", 1, ["urban", "realistic"],
       "与 profession『街角洗衣店老板娘』搭配，激活 M09 权力颗粒度。",
       "human", ["M09"]),
    mk("worldview-003", "每天 23:59 的电梯按钮只响一下", 1, ["urban", "mystery"],
       "与 era『月末发工资日』搭配，激活 M05 时空错位。",
       "human", ["M05"]),
    mk("worldview-004", "立春后第一个周日是默认谈判日", 1, ["urban", "realistic"],
       "与 profession『合同科内勤』搭配，激活 M09。",
       "llm"),
    mk("worldview-005", "公交车整点发车时车上无人讲话", 1, ["urban"],
       "与 emotion『集体默契的安静』搭配，激活 M03。",
       "llm"),
    mk("worldview-006", "寄给自己地址的信第二天一定退回", 1, ["urban", "realistic"],
       "与 object『一张被退回的信封』搭配，激活 M03+M07。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 偏常见 (20 条)
# ---------------------------------------------------------------------------
R2 = [
    mk("worldview-007", "所有钥匙在主人去世当天自动变钝", 2, ["urban", "mystery"],
       "与 object『一串黄铜钥匙圈』搭配，激活 M01+M08。",
       "human", ["M01", "M08"]),
    mk("worldview-008", "本名被喊满一百次后会引起回头", 2, ["xianxia", "mystery"],
       "与 taboo_language『亲友之间必须用小名相称』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("worldview-009", "每当有人说「我永远」天上暗一格", 2, ["universal"],
       "与 emotion『承诺出口后的怯意』搭配，激活 M07+M01。",
       "human", ["M07", "M01"]),
    mk("worldview-010", "镜子后方留存上一照镜者 30 秒神色", 2, ["mystery", "urban"],
       "与 profession『美容院镜台值班员』搭配，激活 M03。",
       "human", ["M03"]),
    mk("worldview-011", "每个人一生只能被真心爱一次", 2, ["romance", "universal"],
       "与 emotion『知道机会已用完的安静』搭配，激活 M07。",
       "llm"),
    mk("worldview-012", "同名同姓的两人不会同城过夜", 2, ["urban", "mystery"],
       "与 conflict『必须让亲哥哥以为自己死在十年前』搭配，激活 M06。",
       "llm"),
    mk("worldview-013", "照片拍下的瞬间都会轻微老化", 2, ["urban", "scifi"],
       "与 object『一本相册里的泛黄照』搭配，激活 M01+M05。",
       "llm"),
    mk("worldview-014", "每场雨带走记忆最短的那一段", 2, ["xianxia", "urban"],
       "与 era『二十四节气「大雪」黎明』搭配，激活 M05。",
       "llm"),
    mk("worldview-015", "早晨六点整所有人牙齿微凉", 2, ["urban", "mystery"],
       "与 body_feature『虎牙比常人略长』搭配，激活 M03。",
       "llm"),
    mk("worldview-016", "手掌新茧讲述上个月的主要事", 2, ["mystery", "xianxia"],
       "与 profession『掌纹师』搭配，激活 M03+M09。",
       "llm"),
    mk("worldview-017", "临终前一周的日历自动消失", 2, ["mystery", "apocalypse"],
       "与 object『一本被撕到一半的台历』搭配，激活 M03+M01。",
       "llm"),
    mk("worldview-018", "收到的快递里夹着一根陌生头发", 2, ["urban", "mystery"],
       "与 profession『快递分拣员』搭配，激活 M03+M06。",
       "llm"),
    mk("worldview-019", "一生只能取钱 9999 次", 2, ["urban", "scifi"],
       "与 profession『柜员』搭配，激活 M01+M09。",
       "llm"),
    mk("worldview-020", "末班地铁末节车厢不得坐一个人", 2, ["urban", "mystery"],
       "与 taboo『末班车不得换座』搭配，激活 M08+M03。",
       "llm"),
    mk("worldview-021", "心跳加速时胸前小痣微微变深", 2, ["urban", "romance"],
       "与 body_feature『左胸上方一颗浅痣』搭配，激活 M01。",
       "llm"),
    mk("worldview-022", "说真话时打一个小小的喷嚏", 2, ["universal"],
       "与 conflict『不说谎的前提下让所有人都误会自己』搭配，激活 M03。",
       "llm"),
    mk("worldview-023", "婚礼当天听不见钟声", 2, ["romance", "urban"],
       "与 taboo『婚礼上不得提钟字』搭配，激活 M03+M08。",
       "llm"),
    mk("worldview-024", "一生中有一次替别人挡雨的机会", 2, ["universal"],
       "与 object『一把旧油纸伞』搭配，激活 M01+M07。",
       "llm"),
    mk("worldview-025", "红灯停时每人想起一次旧事", 2, ["urban"],
       "与 emotion『短暂沉默里的遗憾』搭配，激活 M07。",
       "llm"),
    mk("worldview-026", "梦里说过的话醒来会重复一次", 2, ["xianxia", "mystery"],
       "与 taboo『醒后不得立即开口』搭配，激活 M03+M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 中等稀缺 (25 条) — 信息不对称+权力规则
# ---------------------------------------------------------------------------
R3 = [
    mk("worldview-027", "重要决定必须当面做电话邮件作不生效", 3, ["urban", "mystery"],
       "与 profession『见证律师』搭配，激活 M09+M03。",
       "human", ["M09", "M03"]),
    mk("worldview-028", "所有承诺写入空气违约者当夜失眠", 3, ["xianxia", "universal"],
       "与 emotion『睡不着时的清醒』搭配，激活 M01+M08。",
       "human", ["M01", "M08"]),
    mk("worldview-029", "陌生人的善意有固定配额用完即耗尽", 3, ["urban", "universal"],
       "与 conflict『必须说服陌生人抢走自己背包』搭配，激活 M01+M07。",
       "human", ["M01", "M07"]),
    mk("worldview-030", "每次被背叛背叛者手指多一道纹", 3, ["xianxia", "mystery"],
       "与 body_feature『小指第二节的细纹』搭配，激活 M01+M06。",
       "human", ["M01", "M06"]),
    mk("worldview-031", "一生须隐瞒一个秘密否则不能死", 3, ["xianxia", "mystery"],
       "与 taboo『临终前不得说尽』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("worldview-032", "两人同说一句话那一刻世界静音一秒", 3, ["xianxia", "scifi"],
       "与 conflict『必须在没有语言的前提下完成一场辩论』搭配，激活 M05+M03。",
       "llm"),
    mk("worldview-033", "所有宠物知道主人何时会死", 3, ["urban", "mystery"],
       "与 profession『宠物医院值夜医生』搭配，激活 M03+M01。",
       "llm"),
    mk("worldview-034", "名字里藏着能杀死自己的那一笔", 3, ["xianxia", "mystery"],
       "与 taboo_language『签字时不得写全名』搭配，激活 M01+M08。",
       "llm"),
    mk("worldview-035", "身份证芯片每年新增一行自动摘要", 3, ["scifi", "urban"],
       "与 profession『户籍系统维护员』搭配，激活 M03+M09。",
       "llm"),
    mk("worldview-036", "任何一对人不能相互保密超过七年", 3, ["universal"],
       "与 emotion『第七年的坦白』搭配，激活 M03+M07。",
       "llm"),
    mk("worldview-037", "每本书被读完时作者会咳嗽一声", 3, ["xianxia", "mystery"],
       "与 object『一本手抄本小说』搭配，激活 M05+M03。",
       "llm"),
    mk("worldview-038", "临终一句话在世间回响三天", 3, ["mystery", "universal"],
       "与 taboo『不得在回响期内复述』搭配，激活 M03+M08。",
       "llm"),
    mk("worldview-039", "电视关机瞬间残余图像人会记住三秒", 3, ["scifi", "urban"],
       "与 era『1997 年邓小平逝世当日早高峰』搭配，激活 M05+M03。",
       "llm"),
    mk("worldview-040", "一生只有三次完整原谅别人的机会", 3, ["universal"],
       "与 conflict『在大仇得报时选择与仇家和解』搭配，激活 M02+M07。",
       "llm"),
    mk("worldview-041", "拥抱超过七秒双方共享一段记忆", 3, ["xianxia", "romance"],
       "与 taboo『初次见面不得拥抱满 10 秒』搭配，激活 M05+M08。",
       "llm"),
    mk("worldview-042", "日落时抬头者当夜做梦必带雨", 3, ["xianxia", "mystery"],
       "与 emotion『雨梦里的释然』搭配，激活 M07+M08。",
       "llm"),
    mk("worldview-043", "说「再见」越多两人再见的概率越低", 3, ["urban", "romance"],
       "与 taboo_language『送别时只准说一次再见』搭配，激活 M03+M07。",
       "llm"),
    mk("worldview-044", "6 个最好朋友里必有一人为自己撒过谎", 3, ["urban", "mystery"],
       "与 emotion『相信之后的侦测欲』搭配，激活 M03+M07。",
       "llm"),
    mk("worldview-045", "手写名字比打字名字更难被遗忘", 3, ["xianxia", "universal"],
       "与 object『一本署名纪念册』搭配，激活 M03+M06。",
       "llm"),
    mk("worldview-046", "每人心脏里有一枚别人不知道的符号", 3, ["xianxia", "mystery"],
       "与 profession『心电图记录员』搭配，激活 M03+M06。",
       "llm"),
    mk("worldview-047", "所有锁都认识自己的钥匙", 3, ["xianxia", "mystery"],
       "与 object『一把从未对上锁孔的铜钥匙』搭配，激活 M06+M09。",
       "llm"),
    mk("worldview-048", "每千人里有一人从未被任何人注视过", 3, ["urban", "mystery"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M03+M09。",
       "llm"),
    mk("worldview-049", "每条河下游能听见上游承诺", 3, ["xianxia", "mystery"],
       "与 profession『水文站值夜员』搭配，激活 M05+M03。",
       "llm"),
    mk("worldview-050", "死者声音附在活人最习惯说的词上", 3, ["mystery", "xianxia"],
       "与 taboo_language『不得过度重复一个口头禅』搭配，激活 M03+M08。",
       "llm"),
    mk("worldview-051", "说谎者 24 小时后嘴唇发黑", 3, ["xianxia", "mystery"],
       "与 body_feature『嘴唇颜色比常人深半度』搭配，激活 M01+M06。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 稀缺 (30 条) — 奇异规则+结构反差
# ---------------------------------------------------------------------------
R4 = [
    mk("worldview-052", "每个人只能听见一种频段的真话", 4, ["scifi", "xianxia"],
       "与 profession『声学调音师』搭配，激活 M03+M10。",
       "human", ["M03", "M10"]),
    mk("worldview-053", "影子知道主人下一步但说不出", 4, ["xianxia", "mystery"],
       "与 taboo『影不得在日正午离体』搭配，激活 M08+M03。",
       "human", ["M08", "M03"]),
    mk("worldview-054", "孩子乳牙里藏着父母出生前的秘密", 4, ["mystery", "xianxia"],
       "与 body_feature『一颗迟迟不落的乳牙』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("worldview-055", "陌生人第一次对视能读出对方一个后悔", 4, ["xianxia", "urban"],
       "与 emotion『被瞬间识破的刺痛』搭配，激活 M03+M07。",
       "human", ["M03", "M07"]),
    mk("worldview-056", "告别时回头的一方当日寿命减一", 4, ["xianxia", "mystery"],
       "与 taboo『火车站月台不得回头招手』搭配，激活 M01+M08。",
       "human", ["M01", "M08"]),
    mk("worldview-057", "夫妻间只能有一人知道孩子生父", 4, ["urban", "mystery"],
       "与 taboo_language『家中不得用「亲生」二字』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("worldview-058", "一生一次把「不」说成「是」的赦免", 4, ["xianxia", "universal"],
       "与 conflict『必须让自己忘记一件事才能完成它』搭配，激活 M02+M07。",
       "llm"),
    mk("worldview-059", "所有镜子记录上一被照者相貌一整天", 4, ["mystery", "xianxia"],
       "与 conflict『与只在镜里存在的仇人达成停战』搭配，激活 M06+M03。",
       "llm"),
    mk("worldview-060", "梦中说出的名字醒来永远不认识此人", 4, ["xianxia", "mystery"],
       "与 taboo『梦醒不得立即复述』搭配，激活 M03+M06。",
       "llm"),
    mk("worldview-061", "日记每年自动删除一行最真的话", 4, ["mystery", "scifi"],
       "与 object『一本日记本缺页』搭配，激活 M03+M01。",
       "llm"),
    mk("worldview-062", "一生只遇见三个真相信自己的人", 4, ["universal"],
       "与 emotion『相信被用光时的空落』搭配，激活 M07+M01。",
       "llm"),
    mk("worldview-063", "每当有人忘了你你便短暂失忆一次", 4, ["mystery", "xianxia"],
       "与 body_feature『额角一颗会忽隐忽现的痣』搭配，激活 M08+M06。",
       "llm"),
    mk("worldview-064", "谎话在当日月圆时被墙壁记住", 4, ["xianxia", "mystery"],
       "与 object『一面贴着旧报纸的老墙』搭配，激活 M03+M08。",
       "llm"),
    mk("worldview-065", "指纹在死亡时自动填入档案", 4, ["scifi", "mystery"],
       "与 profession『档案抹除专员』搭配，激活 M09+M03。",
       "llm"),
    mk("worldview-066", "全人类罪孽汇总到某只未知动物身上", 4, ["xianxia", "apocalypse"],
       "与 mythology『共业替罪兽的古老传说』搭配，激活 M10+M01。",
       "llm"),
    mk("worldview-067", "说秘密瞬间听者头发略变长", 4, ["xianxia", "mystery"],
       "与 body_feature『头发长得比常人略快』搭配，激活 M01+M03。",
       "llm"),
    mk("worldview-068", "一生三分钟能听见已故亲人声音", 4, ["xianxia", "mystery"],
       "与 profession『通灵副业的客服』搭配，激活 M05+M01。",
       "llm"),
    mk("worldview-069", "被爱者离开时回头的人不再被爱", 4, ["romance", "universal"],
       "与 taboo『送别时不得走超过三步再回头』搭配，激活 M07+M08。",
       "llm"),
    mk("worldview-070", "人类共享遗憾池每日自动平均分配", 4, ["scifi", "xianxia"],
       "与 emotion『陌生遗憾找不到出处的茫然』搭配，激活 M10+M07。",
       "llm"),
    mk("worldview-071", "每座桥下住着一个被遗忘的约定", 4, ["xianxia", "mystery"],
       "与 object『一根桥墩上褪色的红绳』搭配，激活 M03+M05。",
       "llm"),
    mk("worldview-072", "相机第 100 次按快门自动瞎一个镜头", 4, ["scifi", "mystery"],
       "与 profession『婚礼摄影师』搭配，激活 M01+M09。",
       "llm"),
    mk("worldview-073", "每座城都有一条永不下雨的街", 4, ["xianxia", "mystery"],
       "与 era『2020 年封城第一天』搭配，激活 M05+M09。",
       "llm"),
    mk("worldview-074", "日出日落时所有人保持无声一分钟", 4, ["xianxia", "universal"],
       "与 taboo『晨昏静默不得破』搭配，激活 M03+M08。",
       "llm"),
    mk("worldview-075", "陌生人临终遗言出现在无关者梦里", 4, ["xianxia", "mystery"],
       "与 profession『夜班急诊护士』搭配，激活 M05+M03。",
       "llm"),
    mk("worldview-076", "背弃承诺者月底收到一封无字信", 4, ["mystery", "xianxia"],
       "与 object『一封被拆开后又封起来的信』搭配，激活 M03+M08。",
       "llm"),
    mk("worldview-077", "初见时对方眼眶里短暂出现你的姓氏", 4, ["xianxia", "romance"],
       "与 body_feature『虹膜颜色带微弱金斑』搭配，激活 M03+M06。",
       "llm"),
    mk("worldview-078", "左手掌有一条只属于自己的时间线", 4, ["scifi", "xianxia"],
       "与 body_feature『掌心一道月牙形旧伤』搭配，激活 M05+M06。",
       "llm"),
    mk("worldview-079", "被诬陷者名字 24 小时从无名墓碑消失", 4, ["mystery", "xianxia"],
       "与 era『清末光绪大婚当天紫禁城』搭配，激活 M03+M05。",
       "llm"),
    mk("worldview-080", "真正爱过的人月底听见一次敲门声", 4, ["romance", "mystery"],
       "与 emotion『门被敲响时的迟疑』搭配，激活 M07+M01。",
       "llm"),
    mk("worldview-081", "每个人只能被错过三次", 4, ["universal", "romance"],
       "与 conflict『必须让暗恋者彻底不爱自己』搭配，激活 M07+M02。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 极稀缺 (20 条) — 哲学/时空/自指悖论
# ---------------------------------------------------------------------------
R5 = [
    mk("worldview-082", "整个世界每天午夜消失三秒钟", 5, ["scifi", "xianxia"],
       "与 era『农历甲子年甲子月甲子日甲子时』搭配，激活 M05+M10。",
       "human", ["M05", "M10"]),
    mk("worldview-083", "每说一次「我爱你」宇宙膨胀一个粒子", 5, ["scifi", "romance"],
       "与 conflict『让自己的声音从所有录音里消失』搭配，激活 M10+M07。",
       "human", ["M10", "M07"]),
    mk("worldview-084", "死亡是借来的寿命须还给最后见死者", 5, ["xianxia", "mystery"],
       "与 profession『殡仪馆化妆师』搭配，激活 M01+M02。",
       "human", ["M01", "M02"]),
    mk("worldview-085", "人只看得见自己的死亡时刻", 5, ["xianxia", "mystery"],
       "与 emotion『对倒数的麻木』搭配，激活 M03+M07。",
       "llm"),
    mk("worldview-086", "每人有一本自己写却从未读过的书", 5, ["xianxia", "scifi"],
       "与 object『一本封面已磨白的手稿』搭配，激活 M03+M07。",
       "llm"),
    mk("worldview-087", "世界尽头写在出生第一口啼哭里", 5, ["xianxia", "mythology"] if False else ["xianxia", "universal"],
       "与 mythology『送子娘娘在产床边默念那一句』搭配，激活 M10+M05。",
       "llm"),
    mk("worldview-088", "时间向前走但人只向后活", 5, ["scifi", "xianxia"],
       "与 body_feature『皱纹从颈部开始向脸蔓延』搭配，激活 M05+M10。",
       "llm"),
    mk("worldview-089", "被忘记的人活在无法进入的城市", 5, ["xianxia", "mystery"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M05+M09。",
       "llm"),
    mk("worldview-090", "每人沉默时都是另一个人的声音", 5, ["xianxia", "scifi"],
       "与 taboo_language『沉默时不得在心里默念姓』搭配，激活 M06+M03。",
       "llm"),
    mk("worldview-091", "所有真话被说出前一秒已被听见", 5, ["scifi", "mystery"],
       "与 taboo『答复之前不得过听者耳』搭配，激活 M03+M05。",
       "llm"),
    mk("worldview-092", "每人一生都是别人做过的一个梦", 5, ["xianxia", "scifi"],
       "与 worldview 自指：对 worldview-001 的回声，激活 M10+M07。",
       "llm"),
    mk("worldview-093", "所有词语都有一个等价但相反的词", 5, ["xianxia", "scifi"],
       "与 taboo_language『辞典第 7 页不得独立出现』搭配，激活 M03+M10。",
       "llm"),
    mk("worldview-094", "光是记忆最慢的形式", 5, ["scifi", "xianxia"],
       "与 object『一盏走得比别家慢的旧灯』搭配，激活 M10+M05。",
       "llm"),
    mk("worldview-095", "每人影子是某个死者留下来的", 5, ["xianxia", "mystery"],
       "与 mythology『三生石旁的影债簿』搭配，激活 M10+M06。",
       "llm"),
    mk("worldview-096", "死亡以字母表顺序发生", 5, ["scifi", "apocalypse"],
       "与 taboo『A 姓者不得领先排队』搭配，激活 M01+M09。",
       "llm"),
    mk("worldview-097", "每人只能被深刻想念九次", 5, ["xianxia", "romance"],
       "与 emotion『第九次想念之后的寂静』搭配，激活 M01+M07。",
       "llm"),
    mk("worldview-098", "所有未发生的事都已在别处发生", 5, ["scifi", "xianxia"],
       "与 conflict『阻止一个尚未发生的承诺被兑现』搭配，激活 M05+M10。",
       "llm"),
    mk("worldview-099", "每件物品记得最后一次被触摸的温度", 5, ["xianxia", "mystery"],
       "与 object『一枚放在旧抽屉里的铜戒指』搭配，激活 M05+M01。",
       "llm"),
    mk("worldview-100", "名字在自杀时刻自动从所有文字消失", 5, ["mystery", "scifi"],
       "与 taboo_language『自尽者姓名不得被重新抄写』搭配，激活 M03+M09。",
       "llm"),
    mk("worldview-101", "自己名字念满 10000 次后变成风", 5, ["xianxia", "mythology"] if False else ["xianxia", "universal"],
       "与 mythology『巫师入风一法』搭配，激活 M10+M01。",
       "llm"),
]


ALL_SEEDS = R1 + R2 + R3 + R4 + R5


def main() -> None:
    from collections import Counter
    assert len(ALL_SEEDS) == 100, f"Expected 100, got {len(ALL_SEEDS)}"

    rarity_dist = Counter(s["rarity"] for s in ALL_SEEDS)
    expected = {1: 5, 2: 20, 3: 25, 4: 30, 5: 20}
    assert dict(rarity_dist) == expected, f"Rarity mismatch: {dict(rarity_dist)}"

    src_dist = Counter(s["source"] for s in ALL_SEEDS)
    assert src_dist["human"] == 20 and src_dist["llm"] == 80, f"Source mismatch: {dict(src_dist)}"

    assert rarity_dist[4] + rarity_dist[5] >= 50
    assert rarity_dist[5] >= 20

    ids = [s["seed_id"] for s in ALL_SEEDS]
    assert len(set(ids)) == len(ids), "duplicate seed_id"

    # genre_tags enum 检查（防 mythology/其他非 enum 再犯）
    ENUM = {"xianxia", "urban", "apocalypse", "scifi", "mystery",
            "game", "history", "realistic", "romance", "universal"}
    for s in ALL_SEEDS:
        assert 1 <= len(s["value"]) <= 40, f"{s['seed_id']} len={len(s['value'])}"
        for t in s["genre_tags"]:
            assert t in ENUM, f"{s['seed_id']} invalid tag: {t}"

    print(f"✓ 预检通过：100 条，分布 {dict(sorted(rarity_dist.items()))}，"
          f"human={src_dist['human']} llm={src_dist['llm']}")

    # ---- 入库 ----
    with SEEDS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["version"] == "v1.3", f"unexpected version: {data['version']}"
    assert data["total"] == 300, f"unexpected total: {data['total']}"
    existing = [s["seed_id"] for s in data["seeds"] if s["category"] == "worldview"]
    assert existing == ["worldview-001"], f"unexpected worldview: {existing}"

    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 400
    data["version"] = "v1.4"
    data["changelog"].append({
        "version": "v1.4",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 4/10 世界观类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频世界观套路（修仙阶段练气筑基金丹元婴化神渡劫飞升/斗气九段/"
            "魔法九级/洪荒封神/灵气复苏/天道系统/签到系统/诸天万界/主神空间/"
            "人妖魔神四族/六道轮回/东玄西幻体系分层）。"
            "策略：抛弃「等级体系」，用「一条精确规则 + 具体代价」直接激活 "
            "M01/M03/M07/M08。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 worldview，version→v1.4，total→400")


if __name__ == "__main__":
    main()
