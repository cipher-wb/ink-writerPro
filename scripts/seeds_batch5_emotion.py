"""Phase-Seed-1 Batch 5/10 — emotion 类 100 条入库脚本。

R1/R2/R3/R4/R5 = 5/20/25/30/20，20 human + 80 llm，
追加到 anti-trope-seeds.json，更新 version→v1.5、total→500。

避开 emotion-001（对失败的眷恋）及 WebSearch 黑名单：
男频热血/爽/装逼/打脸/复仇/无敌/逆袭；
女频甜宠/虐恋/BE/HE/狗血/病娇/双洁/马甲文/重生复仇；
简单的喜怒哀乐单层情绪。

策略：矛盾情感 / 第二阶情感 / 延迟情感 / 错位情感 / 不愿承认的情感，
直接命中 M06（身份反差）+ M07（欲望悖论）。
"""
from __future__ import annotations

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
        "category": "emotion",
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
# R1 (5) — 日常情感锚
# ---------------------------------------------------------------------------
R1 = [
    mk("emotion-002", "被人注视到发痒的后颈", 1, ["universal"],
       "与 profession『茶馆学徒』搭配，激活 M06。",
       "human", ["M06"]),
    mk("emotion-003", "看见陌生人哭出自己想哭的泪", 1, ["urban", "universal"],
       "与 worldview『人类共享遗憾池每日自动平均分配』搭配，激活 M07。",
       "human", ["M07"]),
    mk("emotion-004", "对开很久的旧零食袋的沉默", 1, ["urban", "realistic"],
       "与 object『一只放在柜里的旧饼干铁盒』搭配，激活 M07。",
       "llm"),
    mk("emotion-005", "周一早晨的薄薄倦意", 1, ["urban", "realistic"],
       "与 era『月末发工资日』搭配，激活 M09。",
       "llm"),
    mk("emotion-006", "看电视剧提前预感悲剧的钝痛", 1, ["urban", "universal"],
       "与 worldview『所有宠物知道主人何时会死』搭配，激活 M07。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 (20)
# ---------------------------------------------------------------------------
R2 = [
    mk("emotion-007", "听见前任婚讯时的分层释然", 2, ["romance", "urban"],
       "与 object『一张未寄出的分手信』搭配，激活 M07。",
       "human", ["M07"]),
    mk("emotion-008", "被误当作别人时短暂的贪恋", 2, ["romance", "urban"],
       "与 conflict『让只认出你的人继续不认识你』搭配，激活 M06+M07。",
       "human", ["M06", "M07"]),
    mk("emotion-009", "原本憎恨的人病倒后的空白", 2, ["urban", "realistic"],
       "与 profession『医院探视登记员』搭配，激活 M02+M07。",
       "human", ["M02", "M07"]),
    mk("emotion-010", "替别人做到了自己没做到的事的酸", 2, ["urban", "realistic"],
       "与 emotion『对失败的眷恋』回应，激活 M07。",
       "human", ["M07"]),
    mk("emotion-011", "录音回放自己声音时的陌生", 2, ["universal"],
       "与 worldview『让自己的声音从所有录音里消失』搭配，激活 M06+M03。",
       "llm"),
    mk("emotion-012", "对敌人表扬的防卫性抗拒", 2, ["universal"],
       "与 conflict『必须在大仇得报时选择和解』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-013", "旧屋被拆前最后一次关门的无言", 2, ["realistic", "urban"],
       "与 conflict『必须亲手拆除亡父留下的老房』搭配，激活 M01+M07。",
       "llm"),
    mk("emotion-014", "成为别人口中「当年他」的错愕", 2, ["urban", "realistic"],
       "与 profession『同学会组织者』搭配，激活 M06。",
       "llm"),
    mk("emotion-015", "父母第一次向自己低头时的被挖空", 2, ["urban", "realistic"],
       "与 era『农历辛亥年立秋前一日』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-016", "收到意外示好时的轻微不配", 2, ["romance", "universal"],
       "与 object『一束没有署名的花』搭配，激活 M07。",
       "llm"),
    mk("emotion-017", "打通多年不联系的人电话时的失声", 2, ["universal"],
       "与 taboo_language『开口第一句不得用「你还记得」』搭配，激活 M03+M07。",
       "llm"),
    mk("emotion-018", "独自旅行第三日的过度兴奋", 2, ["urban", "realistic"],
       "与 era『周日下午四点』搭配，激活 M07。",
       "llm"),
    mk("emotion-019", "夺回本该属于自己的东西后的失重", 2, ["universal"],
       "与 object『一份被篡改过的遗嘱』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-020", "照镜发现自己变得像母亲的一瞬", 2, ["universal"],
       "与 body_feature『眼角走向与母亲几乎重合』搭配，激活 M06。",
       "llm"),
    mk("emotion-021", "婚礼上想起不该想起之人的克制", 2, ["romance"],
       "与 taboo『婚礼当天不得闭眼超过三秒』搭配，激活 M07。",
       "llm"),
    mk("emotion-022", "对陌生小孩的愤怒后的惭愧", 2, ["urban", "universal"],
       "与 era『开学第一周』搭配，激活 M07+M06。",
       "llm"),
    mk("emotion-023", "被夸耀时想要打断对方的冲动", 2, ["universal"],
       "与 taboo_language『奖状誊写者不得笑』搭配，激活 M07+M06。",
       "llm"),
    mk("emotion-024", "看自己童年照片时的嫉妒", 2, ["universal"],
       "与 object『一张贴在相册最前的黑白照』搭配，激活 M07。",
       "llm"),
    mk("emotion-025", "年终最后一天对任何决定的疲惫", 2, ["urban", "realistic"],
       "与 era『春节前三天』搭配，激活 M09+M07。",
       "llm"),
    mk("emotion-026", "名字被陌生口音叫错的亲切", 2, ["universal"],
       "与 taboo_language『方言版本不得统一』搭配，激活 M06+M07。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 (25) — 矛盾/延迟情感
# ---------------------------------------------------------------------------
R3 = [
    mk("emotion-027", "赢下不愿赢那场比赛的耻感", 3, ["universal"],
       "与 conflict『必须主动从榜单第一让到第二位』搭配，激活 M02+M07。",
       "human", ["M02", "M07"]),
    mk("emotion-028", "故人老去那一刻的心疼也松一口气", 3, ["urban", "universal"],
       "与 era『1997 年邓小平逝世当日早高峰』搭配，激活 M07+M05。",
       "human", ["M07", "M05"]),
    mk("emotion-029", "对曾施舍自己的人的怨", 3, ["urban", "realistic"],
       "与 profession『慈善机构登记处志工』搭配，激活 M07+M02。",
       "human", ["M07", "M02"]),
    mk("emotion-030", "被原谅之后的不适", 3, ["universal"],
       "与 taboo『原谅不得说两遍』搭配，激活 M07+M08。",
       "human", ["M07", "M08"]),
    mk("emotion-031", "看陌生人做出自己私密动作的狼狈", 3, ["urban", "mystery"],
       "与 body_feature『食指无意识摩挲拇指的习惯』搭配，激活 M06+M03。",
       "human", ["M06", "M03"]),
    mk("emotion-032", "对陌生善意的短暂憎恨", 3, ["urban", "universal"],
       "与 worldview『陌生人的善意有固定配额用完即耗尽』搭配，激活 M07。",
       "llm"),
    mk("emotion-033", "被说「你变了」之后的虚假坚守", 3, ["universal"],
       "与 profession『童年玩伴的同班同学』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-034", "爱人在外人面前比自己面前更松弛的酸", 3, ["romance", "urban"],
       "与 taboo_language『家中不得重复外人之夸』搭配，激活 M07+M03。",
       "llm"),
    mk("emotion-035", "忽然想起童年伙伴名字时的自责", 3, ["universal"],
       "与 worldview『被忘记的人活在无法进入的城市』搭配，激活 M07+M03。",
       "llm"),
    mk("emotion-036", "对自己救过的人的淡漠", 3, ["universal"],
       "与 profession『急救车副驾』搭配，激活 M07+M06。",
       "llm"),
    mk("emotion-037", "长辈从远方寄来咸菜的负罪", 3, ["realistic", "urban"],
       "与 object『一只用旧信封包着的咸菜罐』搭配，激活 M01+M07。",
       "llm"),
    mk("emotion-038", "别人替自己承担时的轻微满足", 3, ["universal"],
       "与 conflict『替没人愿意替的小人物挡下舆论』搭配，激活 M07+M02。",
       "llm"),
    mk("emotion-039", "葬礼上笑出来之后的恐惧", 3, ["mystery", "urban"],
       "与 taboo『丧仪白花不得别在左耳』搭配，激活 M07+M08。",
       "llm"),
    mk("emotion-040", "目送爱人去见情人时的理解", 3, ["romance"],
       "与 conflict『必须帮暗恋对象嫁给他讨厌的人』搭配，激活 M07+M02。",
       "llm"),
    mk("emotion-041", "无法为理应难过之事哭出来的困惑", 3, ["universal"],
       "与 taboo_language『悼词不得留空第三行』搭配，激活 M07。",
       "llm"),
    mk("emotion-042", "被表白后短暂厌恶对方的惊讶", 3, ["romance"],
       "与 profession『心理咨询师的咨询者』搭配，激活 M07+M06。",
       "llm"),
    mk("emotion-043", "母亲开始像孩子一样依赖自己时的失措", 3, ["urban", "realistic"],
       "与 body_feature『母亲手上新起的老年斑』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-044", "路过年轻时住过的地方的平淡", 3, ["universal"],
       "与 era『2010 年上海世博闭幕夜』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-045", "作品被陌生人欣赏时的怯意", 3, ["realistic", "urban"],
       "与 profession『独立插画师』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-046", "被长期合作者辞退时的解放", 3, ["urban", "realistic"],
       "与 conflict『必须让自己被开除以换组长升职』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-047", "旧友在网上晒幸福时祝福混冷漠", 3, ["urban"],
       "与 profession『朋友圈屏蔽管理员』搭配，激活 M07+M03。",
       "llm"),
    mk("emotion-048", "久未联系朋友死讯麻木后的愧疚", 3, ["universal"],
       "与 worldview『每本日记每年自动删除一行最真的话』搭配，激活 M07。",
       "llm"),
    mk("emotion-049", "听见久违家乡话时的后退", 3, ["urban", "realistic"],
       "与 taboo_language『乡音不得与普通话混用』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-050", "被爱人纠正口头禅时的羞怯", 3, ["romance"],
       "与 taboo_language『二人不得有超过三个共同口头禅』搭配，激活 M06。",
       "llm"),
    mk("emotion-051", "对陌生狗的好意后的防卫", 3, ["urban", "universal"],
       "与 body_feature『左手背一道旧狗牙印』搭配，激活 M06。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 (30) — 错位/延迟/结构性情感
# ---------------------------------------------------------------------------
R4 = [
    mk("emotion-052", "爱人最爱自己那一刻想离开的冲动", 4, ["romance"],
       "与 conflict『必须说服爱人不要救自己』搭配，激活 M07+M02。",
       "human", ["M07", "M02"]),
    mk("emotion-053", "仇人临终时替他整理衣领的安静", 4, ["universal"],
       "与 taboo『仇人床前不得抬高手』搭配，激活 M02+M07。",
       "human", ["M02", "M07"]),
    mk("emotion-054", "替反派流下的那一滴泪", 4, ["universal", "mystery"],
       "与 profession『刑场监斩副手』搭配，激活 M06+M07。",
       "human", ["M06", "M07"]),
    mk("emotion-055", "故亲人生日短信的错愕与不忍拆穿", 4, ["mystery", "urban"],
       "与 object『一张早年填错生日的登记表』搭配，激活 M03+M07。",
       "human", ["M03", "M07"]),
    mk("emotion-056", "看见孩子重演自己错过的麻木", 4, ["realistic", "urban"],
       "与 worldview『孩子乳牙里藏着父母出生前的秘密』搭配，激活 M06+M07。",
       "human", ["M06", "M07"]),
    mk("emotion-057", "爱过之人变平庸的失望甚于背叛", 4, ["romance", "universal"],
       "与 emotion 自指：对 emotion-001『对失败的眷恋』搭配，激活 M07。",
       "human", ["M07"]),
    mk("emotion-058", "所有人都相信自己之时忽然的自我怀疑", 4, ["universal"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-059", "站在高处时想起地面人名字的荒唐", 4, ["universal"],
       "与 era『1969 年阿波罗登月时北京早八点』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-060", "被人原谅却无法原谅自己的孤独", 4, ["universal"],
       "与 taboo『忏悔厅窗户不得超过一日不拉开』搭配，激活 M07+M01。",
       "llm"),
    mk("emotion-061", "帮过对手一次之后的羞愤", 4, ["universal"],
       "与 conflict『必须帮反派完成反派最后一次正确的事』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-062", "对自己仓皇时的温柔", 4, ["universal"],
       "与 body_feature『手腕处一圈浅浅的勒痕』搭配，激活 M01+M07。",
       "llm"),
    mk("emotion-063", "知道被背叛仍替对方找借口的疲惫", 4, ["romance", "urban"],
       "与 worldview『每次被背叛背叛者手指多一道纹』搭配，激活 M07+M01。",
       "llm"),
    mk("emotion-064", "看年轻同事完成自己做不成的梦的失语", 4, ["urban", "realistic"],
       "与 profession『主管转岗培训师』搭配，激活 M07+M06。",
       "llm"),
    mk("emotion-065", "被爱人误解却选择不解释的宁愿", 4, ["romance"],
       "与 taboo『夫妻间不得讲出「其实」二字』搭配，激活 M07+M03。",
       "llm"),
    mk("emotion-066", "自己得救时想起未得救陌生人的羞耻", 4, ["universal"],
       "与 era『2004 年印度洋海啸次日』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-067", "孩子第一次叫错自己名字的愣", 4, ["urban", "romance"],
       "与 body_feature『母亲声带一处先天小结』搭配，激活 M06。",
       "llm"),
    mk("emotion-068", "读别人日记里关于自己部分的战栗", 4, ["mystery", "urban"],
       "与 object『一本被翻开第 43 页的皮面日记』搭配，激活 M03+M07。",
       "llm"),
    mk("emotion-069", "决定离婚那一天爱得最深", 4, ["romance"],
       "与 era『立春后第一个周日』搭配，激活 M07+M02。",
       "llm"),
    mk("emotion-070", "胜利之后最先想起的是自己的懒散", 4, ["universal"],
       "与 profession『体育总局考核干部』搭配，激活 M07。",
       "llm"),
    mk("emotion-071", "站在自己曾许愿的树下不敢许愿", 4, ["xianxia", "universal"],
       "与 object『一条褪色的红绸带』搭配，激活 M07+M08。",
       "llm"),
    mk("emotion-072", "给陌生人指路之后的过度满足", 4, ["urban"],
       "与 profession『地铁口保安』搭配，激活 M07+M06。",
       "llm"),
    mk("emotion-073", "听到自己不信的广告语时忽然相信", 4, ["urban", "scifi"],
       "与 era『2000 年广电关停个人电台那个月』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-074", "说出重话之后假装一切如常的克制", 4, ["universal"],
       "与 taboo_language『第二句话不得以「我」开头』搭配，激活 M03+M07。",
       "llm"),
    mk("emotion-075", "对抛弃自己之人产生母性关怀的恐惧", 4, ["romance", "universal"],
       "与 emotion 自指：对 emotion-001 的二阶引申，激活 M07+M06。",
       "llm"),
    mk("emotion-076", "亲手将爱人逼走之后的如释重负", 4, ["romance"],
       "与 conflict『必须让暗恋者彻底不爱自己』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-077", "多年未见的老师递茶杯时的微颤", 4, ["realistic", "urban"],
       "与 profession『退休中学教研组长』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-078", "母亲第一次不认得自己时的短暂自由感", 4, ["realistic", "urban"],
       "与 body_feature『母亲左眼开始浑浊』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-079", "自己发起葬礼上哭不出来的冷漠", 4, ["mystery"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-080", "被仇家后代救活时的羞愧", 4, ["universal"],
       "与 conflict『让杀父仇人活着并有尊严地死去』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-081", "被恶意攻击时忽然回到童年的缩小", 4, ["universal"],
       "与 body_feature『背部一处童年烫伤的痕迹』搭配，激活 M06+M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 (20) — 哲学/自指/不可命名
# ---------------------------------------------------------------------------
R5 = [
    mk("emotion-082", "对自己即将产生的情感的抗拒", 5, ["xianxia", "universal"],
       "与 worldview『每说一次「我爱你」宇宙膨胀一个粒子』搭配，激活 M07+M08。",
       "human", ["M07", "M08"]),
    mk("emotion-083", "对从未发生的遗憾的具体怀念", 5, ["scifi", "universal"],
       "与 conflict『阻止尚未发生的承诺被兑现』搭配，激活 M05+M07。",
       "human", ["M05", "M07"]),
    mk("emotion-084", "被自己的梦抛弃时的孤绝", 5, ["xianxia", "mystery"],
       "与 worldview『每人一生都是别人做过的一个梦』搭配，激活 M07+M10。",
       "human", ["M07", "M10"]),
    mk("emotion-085", "未爱过的人眼中看见爱的倒影的冷", 5, ["romance", "xianxia"],
       "与 taboo_language『对视时不得先眨眼』搭配，激活 M03+M07。",
       "llm"),
    mk("emotion-086", "听见时间停止一瞬的松绑", 5, ["scifi", "xianxia"],
       "与 worldview『在所有计时器停走的瞬间完成抉择』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-087", "记忆还未形成就已知会忘的哀悼", 5, ["xianxia", "mystery"],
       "与 worldview『每场雨带走记忆最短的那一段』搭配，激活 M07+M05。",
       "llm"),
    mk("emotion-088", "对一个不存在替身的全部思念", 5, ["romance", "xianxia"],
       "与 body_feature『对方的影子多出一只小指』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-089", "面具背后真实比面具更空的发现", 5, ["universal"],
       "与 taboo『卸下面具的瞬间不得照镜』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-090", "听见自己出生时哭声的愧疚", 5, ["xianxia", "mystery"],
       "与 mythology『产床边送子神默诵那一句』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-091", "对下一次恋爱已提前释怀的冷", 5, ["romance", "xianxia"],
       "与 worldview『一生只能被真心爱一次』搭配，激活 M07+M01。",
       "llm"),
    mk("emotion-092", "看见光里有自己影子的陌生愉悦", 5, ["xianxia", "scifi"],
       "与 body_feature『光照下脖颈处多一道浅影』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-093", "对一切新事物的熟识感", 5, ["scifi", "xianxia"],
       "与 worldview『所有未发生的事都已在别处发生』搭配，激活 M10+M07。",
       "llm"),
    mk("emotion-094", "名字被念错却更想回答的荒诞", 5, ["universal"],
       "与 taboo_language『方言版本不得统一』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-095", "必死之人的笑里听出自己笑的温度", 5, ["mystery", "xianxia"],
       "与 profession『临终关怀护工』搭配，激活 M06+M07。",
       "llm"),
    mk("emotion-096", "对明天的不真切感占据今日", 5, ["scifi", "universal"],
       "与 era『玛雅长计历 13.0.0.0.0 东八区凌晨』搭配，激活 M05+M07。",
       "llm"),
    mk("emotion-097", "与陌生人同看同片云的无因喜悦", 5, ["urban", "xianxia"],
       "与 worldview『日出日落时所有人保持无声一分钟』搭配，激活 M07+M05。",
       "llm"),
    mk("emotion-098", "在得到一切的瞬间全部归还的冲动", 5, ["universal"],
       "与 conflict『必须在所有计时器停走的瞬间完成抉择』搭配，激活 M02+M07。",
       "llm"),
    mk("emotion-099", "听自己死亡那天乌云密度的预感", 5, ["xianxia", "mystery"],
       "与 worldview『人只看得见自己的死亡时刻』搭配，激活 M03+M07。",
       "llm"),
    mk("emotion-100", "被世界温柔对待后的离场欲", 5, ["universal"],
       "与 emotion 自指：对 emotion-001 反向构成闭环，激活 M07+M02。",
       "llm"),
    mk("emotion-101", "对自己在他人记忆里褪色速度的确认", 5, ["xianxia", "scifi"],
       "与 worldview『每本日记每年自动删除一行最真的话』搭配，激活 M07+M03。",
       "llm"),
]


ALL_SEEDS = R1 + R2 + R3 + R4 + R5


def main() -> None:
    from collections import Counter
    assert len(ALL_SEEDS) == 100

    rarity_dist = Counter(s["rarity"] for s in ALL_SEEDS)
    assert dict(rarity_dist) == {1: 5, 2: 20, 3: 25, 4: 30, 5: 20}

    src_dist = Counter(s["source"] for s in ALL_SEEDS)
    assert src_dist["human"] == 20 and src_dist["llm"] == 80

    assert rarity_dist[4] + rarity_dist[5] >= 50
    assert rarity_dist[5] >= 20

    ids = [s["seed_id"] for s in ALL_SEEDS]
    assert len(set(ids)) == len(ids), "duplicate seed_id"

    ENUM = {"xianxia", "urban", "apocalypse", "scifi", "mystery",
            "game", "history", "realistic", "romance", "universal"}
    for s in ALL_SEEDS:
        assert 1 <= len(s["value"]) <= 40, f"{s['seed_id']} len={len(s['value'])}"
        for t in s["genre_tags"]:
            assert t in ENUM, f"{s['seed_id']} invalid tag: {t}"

    print(f"✓ 预检通过：100 条，分布 {dict(sorted(rarity_dist.items()))}，"
          f"human={src_dist['human']} llm={src_dist['llm']}")

    with SEEDS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["version"] == "v1.4", f"unexpected: {data['version']}"
    assert data["total"] == 400, f"unexpected total: {data['total']}"
    existing = [s["seed_id"] for s in data["seeds"] if s["category"] == "emotion"]
    assert existing == ["emotion-001"], f"unexpected emotion: {existing}"

    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 500
    data["version"] = "v1.5"
    data["changelog"].append({
        "version": "v1.5",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 5/10 情感类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频情感套路（男频热血/爽/装逼/打脸/复仇/无敌/逆袭；"
            "女频甜宠/虐恋/BE/HE/狗血/病娇/双洁/马甲文/重生复仇；"
            "单层喜怒哀乐情绪）。"
            "策略：矛盾情感/第二阶情感/延迟情感/错位情感/不愿承认的情感，"
            "直接命中 M06（身份反差）+ M07（欲望悖论）。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 emotion，version→v1.5，total→500")


if __name__ == "__main__":
    main()
