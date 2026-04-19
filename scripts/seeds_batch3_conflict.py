"""Phase-Seed-1 Batch 3/10 — conflict 类 100 条入库脚本。

R1/R2/R3/R4/R5 = 5/20/25/30/20，20 human + 80 llm，
追加到 anti-trope-seeds.json，更新 version→v1.3、total→300。

避开 conflict-001（说服反派不拯救世界）及 WebSearch 黑名单：
打脸反派/踩脚装逼、撕渣男、虐家族、师门欺压、豪门资源争夺、
宫斗争宠、系统对抗、天道逆改、丧尸末世、神级功法争夺、重生复仇。
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
        "category": "conflict",
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
# R1 常见 (5 条) — 日常微冲突锚
# ---------------------------------------------------------------------------
R1 = [
    mk("conflict-002", "被要求在职场两位前辈之间站队", 1, ["urban", "realistic"],
       "与 profession『新入职试用期员工』搭配，激活 M09 权力颗粒度。",
       "human", ["M09"]),
    mk("conflict-003", "家族聚餐被安排连续相亲三天", 1, ["urban", "realistic"],
       "与 emotion『对失败的眷恋』搭配，激活 M07 欲望悖论。",
       "human", ["M07"]),
    mk("conflict-004", "替领导顶下一个不属于自己的错", 1, ["urban", "realistic"],
       "与 profession『行政三级秘书』搭配，激活 M09。",
       "llm"),
    mk("conflict-005", "邻居因水表位置长期纠纷", 1, ["urban", "realistic"],
       "与 object『一张房屋产权证复印件』搭配，激活 M09。",
       "llm"),
    mk("conflict-006", "在好友与爱人之间被迫选听一方秘密", 1, ["universal"],
       "与 emotion『知情后的背叛感』搭配，激活 M07。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 偏常见 (20 条) — 具体代价显性冲突
# ---------------------------------------------------------------------------
R2 = [
    mk("conflict-007", "必须当众烧掉自己最珍贵的一封情书", 2, ["urban", "romance"],
       "与 object『一枚信封里的铜钥匙』搭配，激活 M01 代价可视化。",
       "human", ["M01"]),
    mk("conflict-008", "必须在师父面前承认偷过师兄的东西", 2, ["xianxia", "universal"],
       "与 taboo_language『门规里「偷」字必须替换为「取」』搭配，激活 M06。",
       "human", ["M06"]),
    mk("conflict-009", "必须放走一个曾差点杀自己的人", 2, ["universal"],
       "与 emotion『恨到习惯之后的麻木』搭配，激活 M07。",
       "human", ["M07"]),
    mk("conflict-010", "必须把救命恩人亲手送进监狱", 2, ["urban", "mystery"],
       "与 profession『派出所档案员』搭配，激活 M02 反向冲突。",
       "human", ["M02"]),
    mk("conflict-011", "必须替亲弟弟顶罪上战场", 2, ["history", "realistic"],
       "与 object『一张被撕一半的入伍通知书』搭配，激活 M06+M01。",
       "llm"),
    mk("conflict-012", "必须当面向杀父仇人道歉", 2, ["universal"],
       "与 emotion『屈辱之后的轻盈』搭配，激活 M07+M02。",
       "llm"),
    mk("conflict-013", "必须向爱人坦白父亲是她家仇人", 2, ["romance", "universal"],
       "与 taboo『家族内不得互报对方姓氏』搭配，激活 M03。",
       "llm"),
    mk("conflict-014", "必须在千人前背诵对方的悔过书", 2, ["realistic", "history"],
       "与 profession『县文化馆誊录员』搭配，激活 M06。",
       "llm"),
    mk("conflict-015", "必须独自承担全班偷窃的骂名", 2, ["urban", "realistic"],
       "与 body_feature『眉骨一处旧疤』搭配，激活 M01。",
       "llm"),
    mk("conflict-016", "必须从母亲手里抢回户口本", 2, ["urban", "realistic"],
       "与 taboo『不得向长辈扬手』搭配，激活 M01+M03。",
       "llm"),
    mk("conflict-017", "为救同伴必须违抗上级命令", 2, ["universal"],
       "与 profession『武警中队副班长』搭配，激活 M09。",
       "llm"),
    mk("conflict-018", "必须把最后一碗米让给讨厌的人", 2, ["realistic", "history"],
       "与 era『1958 年大炼钢铁第一个春天』搭配，激活 M01+M07。",
       "llm"),
    mk("conflict-019", "必须在法庭上指认好友", 2, ["mystery", "urban"],
       "与 profession『法院书记员』搭配，激活 M03+M06。",
       "llm"),
    mk("conflict-020", "必须主动烧掉家谱换取家族安全", 2, ["history"],
       "与 taboo『堂屋香案前不得动火』搭配，激活 M01+M08。",
       "llm"),
    mk("conflict-021", "必须亲手拆除亡父留下的老房", 2, ["realistic", "urban"],
       "与 object『一块门楣木雕』搭配，激活 M01。",
       "llm"),
    mk("conflict-022", "必须在婚礼上说出那句不该说的话", 2, ["romance", "urban"],
       "与 emotion『诚实之后的安静』搭配，激活 M07。",
       "llm"),
    mk("conflict-023", "必须替继母瞒住父亲的病情", 2, ["urban", "realistic"],
       "与 taboo_language『家中不得说「危」字』搭配，激活 M03。",
       "llm"),
    mk("conflict-024", "必须当众为自己起的外号道歉", 2, ["urban", "realistic"],
       "与 profession『小学班主任』搭配，激活 M06。",
       "llm"),
    mk("conflict-025", "为保留岗位必须出卖前辈", 2, ["urban", "realistic"],
       "与 profession『证券公司晨会记录员』搭配，激活 M09。",
       "llm"),
    mk("conflict-026", "必须劝亲生子认陌生人为父", 2, ["universal", "romance"],
       "与 taboo『不得让孩子两次改姓』搭配，激活 M06+M03。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 中等稀缺 (25 条) — 反向冲突/权力颗粒度
# ---------------------------------------------------------------------------
R3 = [
    mk("conflict-027", "必须帮反派完成反派最后一次正确的事", 3, ["universal"],
       "与 profession『法警执行副手』搭配，激活 M02+M07。",
       "human", ["M02", "M07"]),
    mk("conflict-028", "必须阻止自己十年前的那条决定发生", 3, ["scifi", "universal"],
       "与 era『1999 年千禧年倒计时最后五分钟』搭配，激活 M05 时空错位。",
       "human", ["M05"]),
    mk("conflict-029", "必须把自己名字从花名册抹掉但要活下去", 3, ["mystery", "universal"],
       "与 taboo『不得在册上留血印』搭配，激活 M01+M03。",
       "human", ["M01", "M03"]),
    mk("conflict-030", "为自证清白必须先证明自己是凶手", 3, ["mystery", "urban"],
       "与 profession『刑事科学技术员』搭配，激活 M02+M03。",
       "human", ["M02", "M03"]),
    mk("conflict-031", "必须阻止所有人记起一个已死去的朋友", 3, ["mystery", "urban"],
       "与 body_feature『右耳后一颗与故人同位的浅痣』搭配，激活 M08。",
       "human", ["M08"]),
    mk("conflict-032", "必须让一个相信自己的陌生人对自己失望", 3, ["universal"],
       "与 emotion『被卸下信任时的轻松』搭配，激活 M07。",
       "llm"),
    mk("conflict-033", "必须让暗恋者彻底不爱自己", 3, ["romance", "urban"],
       "与 object『一张被故意写错的明信片』搭配，激活 M02+M07。",
       "llm"),
    mk("conflict-034", "必须向孩子解释爷爷还活着但不愿见他", 3, ["urban", "realistic"],
       "与 body_feature『老人左手缺一节小指』搭配，激活 M03+M07。",
       "llm"),
    mk("conflict-035", "为完成遗愿须烧掉即将发表的论文", 3, ["realistic", "urban"],
       "与 profession『高校讲师待评副高』搭配，激活 M01+M07。",
       "llm"),
    mk("conflict-036", "必须说服医生留下一个想死的病人", 3, ["urban", "realistic"],
       "与 taboo『急诊室门不得两次关死』搭配，激活 M02。",
       "llm"),
    mk("conflict-037", "必须让自己被开除以换组长升职", 3, ["urban", "realistic"],
       "与 profession『中层储备干部』搭配，激活 M09+M02。",
       "llm"),
    mk("conflict-038", "在邻居不知情时替其照料失智父亲", 3, ["urban", "realistic"],
       "与 emotion『旁观者代入的愧疚』搭配，激活 M07。",
       "llm"),
    mk("conflict-039", "必须主动从榜单第一让到第二位", 3, ["universal"],
       "与 object『一块金字匾』搭配，激活 M09+M07。",
       "llm"),
    mk("conflict-040", "要说服仇家女儿嫁进自家以保她命", 3, ["history", "romance"],
       "与 taboo『不得在媒人前提及旧怨』搭配，激活 M02+M03。",
       "llm"),
    mk("conflict-041", "必须写一篇永不会被看到的悼词", 3, ["realistic", "urban"],
       "与 profession『殡仪馆追思稿代写员』搭配，激活 M01+M07。",
       "llm"),
    mk("conflict-042", "要在庆功会上推翻自己的署名作品", 3, ["realistic", "urban"],
       "与 emotion『荣誉之后的空落』搭配，激活 M07+M02。",
       "llm"),
    mk("conflict-043", "两人同时落水必须先救讨厌那个", 3, ["universal"],
       "与 taboo『先救之人不得告知被救事实』搭配，激活 M02+M01。",
       "llm"),
    mk("conflict-044", "必须让亲哥哥以为自己死在十年前", 3, ["universal", "mystery"],
       "与 object『一张被划掉名字的墓碑照片』搭配，激活 M06+M03。",
       "llm"),
    mk("conflict-045", "必须代替父亲向全村道歉", 3, ["realistic", "history"],
       "与 era『1976 年唐山大地震前七小时』搭配，激活 M01+M06。",
       "llm"),
    mk("conflict-046", "必须说服爱人不要救自己", 3, ["romance", "universal"],
       "与 emotion『拒绝被爱时的刺痛』搭配，激活 M07+M02。",
       "llm"),
    mk("conflict-047", "必须把发明签给曾抄袭自己的人", 3, ["realistic", "urban"],
       "与 profession『专利代理人』搭配，激活 M02+M09。",
       "llm"),
    mk("conflict-048", "必须让相信者看到真相但不让他崩溃", 3, ["universal"],
       "与 taboo_language『揭露时不得用「一直」二字』搭配，激活 M03。",
       "llm"),
    mk("conflict-049", "要同时赢两场你无法公开参加的比赛", 3, ["scifi", "urban"],
       "与 body_feature『右手小指天生比左手短一毫米』搭配，激活 M03+M06。",
       "llm"),
    mk("conflict-050", "必须说服陌生人抢走自己背包", 3, ["mystery", "urban"],
       "与 object『背包里的一枚定位扣』搭配，激活 M02+M03。",
       "llm"),
    mk("conflict-051", "必须让曾判自己无罪的法官知道真相", 3, ["mystery"],
       "与 profession『基层法院退休法官』搭配，激活 M02+M03。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 稀缺 (30 条) — 结构反转/身份两难/不能胜利的胜利
# ---------------------------------------------------------------------------
R4 = [
    mk("conflict-052", "必须在说服反派自杀的同时阻止他自杀", 4, ["universal"],
       "与 worldview『同一人同一日两种誓皆成真』搭配，激活 M02+M07。",
       "human", ["M02", "M07"]),
    mk("conflict-053", "必须替天敌完成其上任者最后一次仪式", 4, ["xianxia", "mystery"],
       "与 mythology『敌宗法师的接引咒』搭配，激活 M02+M06。",
       "human", ["M02", "M06"]),
    mk("conflict-054", "必须给敌人一份你曾需要却没得到的礼物", 4, ["universal"],
       "与 object『一盒未拆封的磁带』搭配，激活 M07+M01。",
       "human", ["M07", "M01"]),
    mk("conflict-055", "必须帮暗恋对象嫁给他讨厌的人", 4, ["romance"],
       "与 emotion『成全时刻的轻微释然』搭配，激活 M07。",
       "human", ["M07"]),
    mk("conflict-056", "发现自己是卧底时须伪造被感化的证据", 4, ["mystery"],
       "与 profession『反恐情报岗分析员』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("conflict-057", "必须让亲妹妹误认自己为凶手以保护真凶", 4, ["mystery"],
       "与 taboo_language『供词里不得出现任何家人称呼』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("conflict-058", "替永不相信自己的母亲说她等了五十年的那句话", 4, ["urban", "realistic"],
       "与 era『农历辛亥年立秋前一日』搭配，激活 M07+M05。",
       "llm"),
    mk("conflict-059", "必须让昨日的自己刺杀今日的自己", 4, ["scifi", "xianxia"],
       "与 worldview『时间线共享一副肉身』搭配，激活 M05+M08。",
       "llm"),
    mk("conflict-060", "劝服另一个时空的自己不要救自己", 4, ["scifi"],
       "与 profession『量子纠缠信号员』搭配，激活 M05+M02。",
       "llm"),
    mk("conflict-061", "向陌生人借走他身上唯一一件父亲遗物", 4, ["universal"],
       "与 emotion『借出之前的犹豫』搭配，激活 M01+M07。",
       "llm"),
    mk("conflict-062", "救老师不救百人还要不被社会追责", 4, ["realistic", "urban"],
       "与 taboo『救援日志不得涂改第二行』搭配，激活 M01+M02。",
       "llm"),
    mk("conflict-063", "不说谎的前提下让所有人都误会自己", 4, ["mystery", "universal"],
       "与 profession『法庭速录员』搭配，激活 M03+M06。",
       "llm"),
    mk("conflict-064", "不杀人的前提下除掉一个人", 4, ["mystery"],
       "与 taboo『任务单不得出现动词「除」』搭配，激活 M02+M03。",
       "llm"),
    mk("conflict-065", "在离婚协议上签下不相关之人的名字", 4, ["urban", "realistic"],
       "与 object『一枚被磨平的印章』搭配，激活 M03+M06。",
       "llm"),
    mk("conflict-066", "为死去的对手完成他生前发起的诉讼", 4, ["urban", "mystery"],
       "与 profession『合议庭代理审判长』搭配，激活 M02+M09。",
       "llm"),
    mk("conflict-067", "让自己名字从历史消失但留下父亲的", 4, ["history"],
       "与 object『一本手抄家谱』搭配，激活 M03+M06。",
       "llm"),
    mk("conflict-068", "让一条河的古名被重新写进市志", 4, ["history", "urban"],
       "与 profession『地方志编撰室外聘写手』搭配，激活 M05+M09。",
       "llm"),
    mk("conflict-069", "在敌我同时需要自己的时刻选择不选边", 4, ["universal"],
       "与 emotion『中立带来的孤立感』搭配，激活 M07+M02。",
       "llm"),
    mk("conflict-070", "让自己被列入通缉令而家人毫不知情", 4, ["mystery", "urban"],
       "与 taboo_language『家书不得提「通」字』搭配，激活 M03+M06。",
       "llm"),
    mk("conflict-071", "在正义与法律冲突时替法律辩护", 4, ["universal"],
       "与 profession『司法行政官见习期律师』搭配，激活 M02+M09。",
       "llm"),
    mk("conflict-072", "让手上染血的事实终生压进档案", 4, ["mystery"],
       "与 object『一只加密档案夹』搭配，激活 M03+M01。",
       "llm"),
    mk("conflict-073", "让杀父仇人活着并有尊严地死去", 4, ["universal"],
       "与 emotion『放下之后的不适』搭配，激活 M02+M07。",
       "llm"),
    mk("conflict-074", "让十年前说出的一句话被所有人遗忘", 4, ["xianxia", "mystery"],
       "与 taboo『忘言咒不得在晴天施』搭配，激活 M08+M03。",
       "llm"),
    mk("conflict-075", "不改过去的前提下阻止现在发生", 4, ["scifi"],
       "与 worldview『因果链只允许被读一次』搭配，激活 M05+M02。",
       "llm"),
    mk("conflict-076", "代替死者在婚礼上说「我愿意」", 4, ["romance", "mystery"],
       "与 object『一对刻着陌生名字的对戒』搭配，激活 M06+M03。",
       "llm"),
    mk("conflict-077", "让只认出你的人继续不认识你", 4, ["universal"],
       "与 body_feature『左颧骨旧疤形状的变化』搭配，激活 M06+M03。",
       "llm"),
    mk("conflict-078", "在大仇得报时选择与仇家和解", 4, ["universal"],
       "与 emotion『仇恨卸下之后的空洞』搭配，激活 M02+M07。",
       "llm"),
    mk("conflict-079", "不退位的前提下让继承者提前掌权", 4, ["history"],
       "与 profession『尚书房随笔太监』搭配，激活 M09+M02。",
       "llm"),
    mk("conflict-080", "替没人愿意替的小人物挡下舆论", 4, ["urban", "realistic"],
       "与 profession『危机公关公司初级顾问』搭配，激活 M09+M07。",
       "llm"),
    mk("conflict-081", "发布最终版前把真相删掉保留假象", 4, ["mystery", "scifi"],
       "与 taboo_language『版本号不得带 rc 字样』搭配，激活 M03。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 极稀缺 (20 条) — 哲学/时空/自指悖论
# ---------------------------------------------------------------------------
R5 = [
    mk("conflict-082", "主角必须同时是法官和被告", 5, ["universal", "mystery"],
       "与 worldview『审判日当日每人审判自己』搭配，激活 M02+M08。",
       "human", ["M02", "M08"]),
    mk("conflict-083", "主角必须证明自己从未存在", 5, ["scifi", "mystery"],
       "与 object『一张所有人都记得却无法出示的照片』搭配，激活 M03+M09。",
       "human", ["M03", "M09"]),
    mk("conflict-084", "必须对抗一个由自己记忆构成的敌人", 5, ["xianxia", "scifi"],
       "与 body_feature『不褪色的胎记沉进骨缝』搭配，激活 M07+M08。",
       "human", ["M07", "M08"]),
    mk("conflict-085", "必须让自己忘记一件事才能完成它", 5, ["xianxia", "scifi"],
       "与 taboo『忘字符不得抄第二遍』搭配，激活 M08+M03。",
       "llm"),
    mk("conflict-086", "时间倒流中劝未来的自己不要后悔", 5, ["scifi"],
       "与 era『玛雅长计历 13.0.0.0.0 东八区凌晨』搭配，激活 M05+M07。",
       "llm"),
    mk("conflict-087", "阻止一个尚未发生的承诺被兑现", 5, ["scifi", "xianxia"],
       "与 worldview『口头承诺提前折现』搭配，激活 M05+M01。",
       "llm"),
    mk("conflict-088", "与自己合谋谋杀自己的另一个版本", 5, ["scifi"],
       "与 body_feature『心脏位置偏右一厘米』搭配，激活 M06+M08。",
       "llm"),
    mk("conflict-089", "让自己在别人的梦里缺席", 5, ["xianxia", "mystery"],
       "与 taboo_language『梦语里不得指名』搭配，激活 M03+M08。",
       "llm"),
    mk("conflict-090", "让一本尚未写出的书提前自毁", 5, ["scifi", "xianxia"],
       "与 object『一管未开封的墨』搭配，激活 M05+M01。",
       "llm"),
    mk("conflict-091", "让已发生的事在档案里显示从未发生", 5, ["mystery", "scifi"],
       "与 profession『档案抹除专员』搭配，激活 M03+M09。",
       "llm"),
    mk("conflict-092", "让自己的声音从所有录音消失", 5, ["scifi", "mystery"],
       "与 body_feature『声带两道平行的旧痕』搭配，激活 M06+M03。",
       "llm"),
    mk("conflict-093", "在没有语言的前提下完成一场辩论", 5, ["universal"],
       "与 taboo『辩场地砖不得被踩第二次』搭配，激活 M02+M03。",
       "llm"),
    mk("conflict-094", "与只在镜里存在的仇人达成停战", 5, ["xianxia", "mystery"],
       "与 object『一面从未背反照人的铜镜』搭配，激活 M06+M02。",
       "llm"),
    mk("conflict-095", "与一段从未存在的记忆展开决斗", 5, ["xianxia", "scifi"],
       "与 emotion『熟悉感无处落脚时的惊慌』搭配，激活 M07+M08。",
       "llm"),
    mk("conflict-096", "说服永远无法开口的证人作证", 5, ["mystery"],
       "与 body_feature『舌根下一枚米粒大的银疤』搭配，激活 M03+M01。",
       "llm"),
    mk("conflict-097", "让被神指定的人自愿放弃神的眷顾", 5, ["xianxia", "universal"],
       "与 mythology『神选者名字刻在掌纹里』搭配，激活 M07+M08。",
       "llm"),
    mk("conflict-098", "在所有计时器停走的瞬间完成抉择", 5, ["scifi"],
       "与 worldview『时间停顿时抉择仍计入命数』搭配，激活 M05+M01。",
       "llm"),
    mk("conflict-099", "让一道永不可解的方程自我矛盾后归零", 5, ["scifi"],
       "与 profession『数学所在编博士后』搭配，激活 M10+M08。",
       "llm"),
    mk("conflict-100", "让两个互斥的真相同时为真", 5, ["mystery", "scifi"],
       "与 worldview『真相允许并列成立』搭配，激活 M10+M02。",
       "llm"),
    mk("conflict-101", "让自己的影子替自己承受一次罪责", 5, ["xianxia", "mystery"],
       "与 taboo『影不得在日正午离体』搭配，激活 M08+M01。",
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

    for s in ALL_SEEDS:
        assert 1 <= len(s["value"]) <= 40, f"{s['seed_id']} len={len(s['value'])}"

    print(f"✓ 预检通过：100 条，分布 {dict(sorted(rarity_dist.items()))}，"
          f"human={src_dist['human']} llm={src_dist['llm']}")

    # ---- 入库 ----
    with SEEDS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["version"] == "v1.2", f"unexpected version: {data['version']}"
    assert data["total"] == 200, f"unexpected total: {data['total']}"
    existing_conflict = [s["seed_id"] for s in data["seeds"] if s["category"] == "conflict"]
    assert existing_conflict == ["conflict-001"], f"unexpected conflict: {existing_conflict}"

    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 300
    data["version"] = "v1.3"
    data["changelog"].append({
        "version": "v1.3",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 3/10 冲突类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频冲突套路（打脸反派/踩脚装逼/撕渣男/虐家族/师门欺压/豪门资源争夺/"
            "宫斗争宠/系统对抗/天道逆改/丧尸末世/神级功法争夺/重生复仇）。"
            "策略：冲突对象从「人/资源」转向「规则/记忆/时间/自己」，"
            "强调不能获胜的胜利、反向冲突、自指悖论。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 conflict，version→v1.3，total→300")


if __name__ == "__main__":
    main()
