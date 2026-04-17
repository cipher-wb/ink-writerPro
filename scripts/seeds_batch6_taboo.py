"""Phase-Seed-1 Batch 6/10 — taboo 类 100 条入库脚本。

R1/R2/R3/R4/R5 = 5/20/25/30/20，20 human + 80 llm，
追加到 anti-trope-seeds.json，更新 version→v1.6、total→600。

避开 taboo-001（不能在日出前说出真名）及 WebSearch 黑名单：
修仙宗门戒律（血脉禁咒/真名禁忌/师徒禁忌/本命法宝/同门相残）；
通用民俗大而泛（孕妇摘果/抱小孩/搬家、半夜照镜、婚衣不带口袋、
戴孝不进新房、百日不婚、四眼人入洞房）。

策略：细颗粒 + 精确触发条件 + 可视后果；
情境化（时间/空间/身份/职业）+ 精确操作 + 明确代价。
直接激活 M01（代价可视化）+ M08（系统反噬）。
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
        "category": "taboo",
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
# R1 (5) — 日常禁忌锚
# ---------------------------------------------------------------------------
R1 = [
    mk("taboo-002", "家中八仙桌缺角那一边不得坐人", 1, ["history", "realistic"],
       "与 object『一张抬脚处缺了一块的老八仙桌』搭配，激活 M09。",
       "human", ["M09"]),
    mk("taboo-003", "新发的工资当天不得存银行", 1, ["urban", "realistic"],
       "与 era『月末发工资日』搭配，激活 M07+M09。",
       "human", ["M07", "M09"]),
    mk("taboo-004", "饭桌上不得用筷子指人", 1, ["universal"],
       "与 emotion『对陌生小孩的愤怒后的惭愧』搭配，激活 M06。",
       "llm"),
    mk("taboo-005", "厨房刀不得横放在砧板上过夜", 1, ["urban", "realistic"],
       "与 object『一柄用了十二年的菜刀』搭配，激活 M08。",
       "llm"),
    mk("taboo-006", "小孩满月前名字不得被外人写下", 1, ["realistic", "xianxia"],
       "与 worldview『本名被喊满一百次后会引起回头』搭配，激活 M03+M06。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 (20)
# ---------------------------------------------------------------------------
R2 = [
    mk("taboo-007", "祖屋东厢房夜里不得留灯", 2, ["history", "mystery"],
       "与 profession『守宅老佣人』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo-008", "送伞须先展开再送不得合着递", 2, ["universal"],
       "与 worldview『一生中有一次替别人挡雨的机会』搭配，激活 M01。",
       "human", ["M01"]),
    mk("taboo-009", "订婚戒指掉地不得立即捡起", 2, ["romance", "universal"],
       "与 object『一枚在地板缝里的银戒』搭配，激活 M01+M07。",
       "human", ["M01", "M07"]),
    mk("taboo-010", "父母健在不得剪光头超过一次", 2, ["history", "realistic"],
       "与 body_feature『头顶一圈永不退色的浅痕』搭配，激活 M06+M08。",
       "human", ["M06", "M08"]),
    mk("taboo-011", "葬礼上不得提未出生者姓氏", 2, ["mystery", "history"],
       "与 worldview『死者声音附在活人最习惯说的词上』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-012", "送葬队伍过完不得立即关门", 2, ["history", "mystery"],
       "与 taboo_language『门环不得连响两下』搭配，激活 M08。",
       "llm"),
    mk("taboo-013", "借出的筷子不得成双归还", 2, ["realistic", "xianxia"],
       "与 worldview『每件物品记得最后一次被触摸的温度』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo-014", "怀孕第七月不得拍全家福", 2, ["realistic", "mystery"],
       "与 body_feature『孕中隐约浮现的胎痣位置』搭配，激活 M08+M06。",
       "llm"),
    mk("taboo-015", "岳父过世百日内不得剃须", 2, ["history", "realistic"],
       "与 era『1945 年日本投降诏书当晚』搭配，激活 M06。",
       "llm"),
    mk("taboo-016", "新屋落成先泼水后迎火", 2, ["history", "xianxia"],
       "与 object『一只用过三代的红铜火盆』搭配，激活 M08+M01。",
       "llm"),
    mk("taboo-017", "嫁衣开剪不得在未时", 2, ["history", "romance"],
       "与 profession『县裁缝铺里的学徒』搭配，激活 M08+M09。",
       "llm"),
    mk("taboo-018", "夜半钟响不得应声", 2, ["xianxia", "mystery"],
       "与 era『惊蛰节气五更天』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-019", "井水倒出盆后不得回灌", 2, ["history", "realistic"],
       "与 worldview『每条河下游能听见上游承诺』搭配，激活 M05+M08。",
       "llm"),
    mk("taboo-020", "梁上燕巢不得毁", 2, ["history", "universal"],
       "与 mythology『宅神与双燕共三世之约』搭配，激活 M08+M10。",
       "llm"),
    mk("taboo-021", "祖坟边的树不得独自修剪", 2, ["history", "mystery"],
       "与 profession『族内指定的坟司』搭配，激活 M08+M03。",
       "llm"),
    mk("taboo-022", "过年贴对联前门必先扫三遍", 2, ["history", "realistic"],
       "与 era『春节前三天』搭配，激活 M09+M03。",
       "llm"),
    mk("taboo-023", "农历七月半溪水不得饮", 2, ["history", "xianxia"],
       "与 mythology『中元鬼节放水灯的由来』搭配，激活 M08+M10。",
       "llm"),
    mk("taboo-024", "丧服未脱不得见生人", 2, ["history", "realistic"],
       "与 emotion『葬礼上笑出来之后的恐惧』搭配，激活 M06+M08。",
       "llm"),
    mk("taboo-025", "祭祀前十二个时辰不得同房", 2, ["history", "xianxia"],
       "与 profession『族中指定的祭祀官』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-026", "产房门帘不得掀两次", 2, ["history", "mystery"],
       "与 mythology『送子娘娘一产只念一遍名』搭配，激活 M03+M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 (25) — 职业/地域/时代规则
# ---------------------------------------------------------------------------
R3 = [
    mk("taboo-027", "军医开夜车灯不得照病号脸", 3, ["realistic", "history"],
       "与 profession『战地外科助理』搭配，激活 M03+M01。",
       "human", ["M03", "M01"]),
    mk("taboo-028", "记者采访死者家属不得掏本子", 3, ["realistic", "urban"],
       "与 profession『都市晚报社会版记者』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo-029", "外交翻译不得让两边同时开口", 3, ["realistic", "history"],
       "与 profession『国宴首席翻译』搭配，激活 M03+M02。",
       "human", ["M03", "M02"]),
    mk("taboo-030", "法医出庭不得佩戴任何首饰", 3, ["mystery", "realistic"],
       "与 body_feature『无名指磨出的戒痕』搭配，激活 M01+M06。",
       "human", ["M01", "M06"]),
    mk("taboo-031", "老刑警退休前不得读自己最早卷宗", 3, ["mystery", "urban"],
       "与 era『1976 年唐山大地震前七小时』搭配，激活 M03+M05。",
       "human", ["M03", "M05"]),
    mk("taboo-032", "国博修复师不得在馆内剪指甲", 3, ["history", "mystery"],
       "与 profession『书画修复组三级修复师』搭配，激活 M08+M03。",
       "llm"),
    mk("taboo-033", "翻译典籍不得在朔日起头", 3, ["history", "xianxia"],
       "与 era『格里高利历颁布首日的大明浙江』搭配，激活 M05+M08。",
       "llm"),
    mk("taboo-034", "庙祝每日第一次开殿不得回首", 3, ["xianxia", "history"],
       "与 mythology『三宝殿晨课第一炷香的禁法』搭配，激活 M08+M03。",
       "llm"),
    mk("taboo-035", "矿工下井前须拍左肩三下", 3, ["realistic", "history"],
       "与 profession『瓦斯检测兼值夜矿工』搭配，激活 M01+M08。",
       "llm"),
    mk("taboo-036", "渔民出海不得提「翻」字", 3, ["realistic", "history"],
       "与 taboo_language『桨下不得数到四』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo-037", "屠夫收工后不得回头看案板", 3, ["realistic", "history"],
       "与 body_feature『右手掌心一道终年不愈的小口』搭配，激活 M01+M06。",
       "llm"),
    mk("taboo-038", "墓碑刻字不得在雨天", 3, ["history", "mystery"],
       "与 profession『刻碑老匠人』搭配，激活 M08+M01。",
       "llm"),
    mk("taboo-039", "掘墓人每日工毕须换鞋", 3, ["mystery", "history"],
       "与 body_feature『鞋底永远带着一层薄灰』搭配，激活 M08+M06。",
       "llm"),
    mk("taboo-040", "守陵人三代以内不得嫁娶", 3, ["history", "xianxia"],
       "与 profession『祖传皇陵守陵人』搭配，激活 M01+M06。",
       "llm"),
    mk("taboo-041", "棋院死局复盘不得开启门窗", 3, ["mystery", "universal"],
       "与 profession『职业棋手裁判组』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-042", "戏班接客前须由小孩踩台", 3, ["history", "realistic"],
       "与 profession『地方小戏班三代戏子』搭配，激活 M08+M06。",
       "llm"),
    mk("taboo-043", "画师给活人画像不得画双眼全开", 3, ["history", "xianxia"],
       "与 profession『画楼肖像师』搭配，激活 M01+M08。",
       "llm"),
    mk("taboo-044", "钟表匠更换齿轮不得念出数字", 3, ["history", "mystery"],
       "与 object『一只走慢三分钟的怀表』搭配，激活 M05+M03。",
       "llm"),
    mk("taboo-045", "酿酒师封坛日不得照镜", 3, ["history", "realistic"],
       "与 profession『老字号酒坊三代酿酒师』搭配，激活 M08+M06。",
       "llm"),
    mk("taboo-046", "染坊第一缸色不得印上花", 3, ["history", "realistic"],
       "与 profession『染坊大师傅收徒第一日』搭配，激活 M09+M03。",
       "llm"),
    mk("taboo-047", "邮差送错信不得当场开封", 3, ["realistic", "mystery"],
       "与 object『一封投错地址的挂号信』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo-048", "守夜人遇陌生敲门不得先开口", 3, ["mystery", "xianxia"],
       "与 worldview『夜里接到自己声音留言不得删除』回声，激活 M03+M08。",
       "llm"),
    mk("taboo-049", "守城人换岗时不得握手", 3, ["history", "realistic"],
       "与 era『1996 年台海危机最紧张那一周』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-050", "产婆接完生不得看新生儿第二眼", 3, ["history", "mystery"],
       "与 mythology『接生婆婆眼里的替身之说』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-051", "书坊新雕版不得先印自家名", 3, ["history", "realistic"],
       "与 profession『匠作监的刻书房雕版工』搭配，激活 M09+M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 (30) — 奇异规则+强反噬
# ---------------------------------------------------------------------------
R4 = [
    mk("taboo-052", "读亡人日记超过三页须焚最后一页", 4, ["mystery", "xianxia"],
       "与 conflict『读别人日记里关于自己的部分』搭配，激活 M01+M08。",
       "human", ["M01", "M08"]),
    mk("taboo-053", "遇两面镜对照时须闭左眼过去", 4, ["mystery", "xianxia"],
       "与 worldview『所有镜子记录上一被照者相貌一整天』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo-054", "替人送婚书的使者不得抬头过檐", 4, ["history", "romance"],
       "与 mythology『月老错红线不得更正』搭配，激活 M06+M08。",
       "human", ["M06", "M08"]),
    mk("taboo-055", "收养之子五岁生日前不得改姓", 4, ["realistic", "universal"],
       "与 taboo_language『家中不得用「亲生」二字』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo-056", "火化师封炉时不得说出死者小名", 4, ["mystery", "urban"],
       "与 profession『殡仪馆火化师』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo-057", "打火机第二次点燃不得为自己", 4, ["universal", "mystery"],
       "与 object『一只刻有双字的铜打火机』搭配，激活 M01+M07。",
       "human", ["M01", "M07"]),
    mk("taboo-058", "给陌生人写讣告不得写全其生辰", 4, ["mystery", "history"],
       "与 profession『殡仪馆追思稿代写员』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-059", "地铁换乘时不得喊出站名", 4, ["urban", "scifi"],
       "与 worldview『末班地铁末节车厢不得坐一个人』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-060", "做梦梦见自己名字不得立即记录", 4, ["xianxia", "mystery"],
       "与 body_feature『梦中手心会短暂发烫』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-061", "替他人签字须先签自己名再涂掉", 4, ["mystery", "realistic"],
       "与 object『一支只写过自己名的旧钢笔』搭配，激活 M06+M03。",
       "llm"),
    mk("taboo-062", "老宅拆迁主梁不得在清晨见光", 4, ["history", "mystery"],
       "与 conflict『必须亲手拆除亡父留下的老房』搭配，激活 M01+M08。",
       "llm"),
    mk("taboo-063", "双胞胎出生三日内不得共喂一勺", 4, ["mystery", "realistic"],
       "与 body_feature『二人瞳孔微妙不同』搭配，激活 M06+M08。",
       "llm"),
    mk("taboo-064", "公墓门口烛火不得用火柴点", 4, ["mystery", "xianxia"],
       "与 object『一只永远点不完的红烛』搭配，激活 M01+M08。",
       "llm"),
    mk("taboo-065", "婚礼当晚灯泡不得换新的", 4, ["romance", "mystery"],
       "与 emotion『婚礼上想起不该想起之人的克制』搭配，激活 M07+M08。",
       "llm"),
    mk("taboo-066", "买墓者不得亲自量尺寸", 4, ["mystery", "history"],
       "与 profession『墓地销售员』搭配，激活 M09+M01。",
       "llm"),
    mk("taboo-067", "写已故者姓名后不得再沾同一墨", 4, ["mystery", "history"],
       "与 object『一方只用过一次的松烟墨』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-068", "临终人面前不得先讲第二句话", 4, ["mystery", "urban"],
       "与 emotion『多年未见的老师递茶杯时的微颤』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo-069", "新生儿啼哭第一声不得被录音", 4, ["mystery", "scifi"],
       "与 emotion『听见自己出生时哭声的愧疚』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo-070", "夜里接长途不得先报家址", 4, ["mystery", "urban"],
       "与 era『2001 年 9·11 当晚的中国新闻联播』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo-071", "领养文书签署当日不得拍合影", 4, ["mystery", "realistic"],
       "与 profession『民政局领养科的登记员』搭配，激活 M06+M03。",
       "llm"),
    mk("taboo-072", "墓志铭完稿不得在夜里晾干", 4, ["history", "mystery"],
       "与 profession『刻碑老匠人』搭配，激活 M08+M01。",
       "llm"),
    mk("taboo-073", "给昏迷者念信不得念完最后一句", 4, ["mystery", "urban"],
       "与 emotion『决定离婚那一天爱得最深』搭配，激活 M07+M03。",
       "llm"),
    mk("taboo-074", "替别人守灵第三日不得离开", 4, ["mystery", "history"],
       "与 taboo『丧服未脱不得见生人』搭配，激活 M01+M08。",
       "llm"),
    mk("taboo-075", "生日当天不得穿别人送的鞋", 4, ["universal"],
       "与 body_feature『左脚天生比右脚大半号』搭配，激活 M06+M08。",
       "llm"),
    mk("taboo-076", "乔迁第一夜不得从外锁门", 4, ["urban", "mystery"],
       "与 object『一把从不对上锁孔的铜钥匙』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-077", "寡言人临别不得互问姓名", 4, ["universal", "mystery"],
       "与 emotion『打通多年不联系的人电话时的失声』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo-078", "寻人启事贴出后不得添照片", 4, ["mystery", "urban"],
       "与 profession『派出所失踪人口登记员』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo-079", "遗产宣读完毕前不得合卷宗", 4, ["mystery", "realistic"],
       "与 object『一份被篡改过的遗嘱』搭配，激活 M09+M03。",
       "llm"),
    mk("taboo-080", "夜里接到自己声音留言不得删除", 4, ["scifi", "mystery"],
       "与 worldview『让自己的声音从所有录音里消失』搭配，激活 M06+M08。",
       "llm"),
    mk("taboo-081", "替未成年人代持身份证不得过午", 4, ["realistic", "mystery"],
       "与 era『1985 年居民身份证启用首日』搭配，激活 M03+M09。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 (20) — 哲学/时空禁忌
# ---------------------------------------------------------------------------
R5 = [
    mk("taboo-082", "不得在自己尚未出生之地许下誓言", 5, ["xianxia", "scifi"],
       "与 worldview『世界尽头写在出生第一口啼哭里』搭配，激活 M05+M08。",
       "human", ["M05", "M08"]),
    mk("taboo-083", "把自己的心跳写下后不得读出", 5, ["xianxia", "mystery"],
       "与 body_feature『心脏位置偏右一厘米』搭配，激活 M01+M08。",
       "human", ["M01", "M08"]),
    mk("taboo-084", "在镜中对答不得超过两个问题", 5, ["xianxia", "mystery"],
       "与 conflict『与只在镜里存在的仇人达成停战』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo-085", "不得同时梦见自己与自己的名字", 5, ["xianxia", "scifi"],
       "与 worldview『名字里藏着能杀死自己的那一笔』搭配，激活 M06+M08。",
       "llm"),
    mk("taboo-086", "死前一日不得回望来时的路", 5, ["xianxia", "mystery"],
       "与 emotion『听自己死亡那天乌云密度的预感』搭配，激活 M07+M08。",
       "llm"),
    mk("taboo-087", "不得把自己未来借给陌生人一天", 5, ["scifi", "xianxia"],
       "与 worldview『每人左手掌有一条只属于自己的时间线』搭配，激活 M05+M08。",
       "llm"),
    mk("taboo-088", "为他人许愿不得以自己之名", 5, ["xianxia", "mythology"] if False else ["xianxia", "universal"],
       "与 mythology『许愿台只收一次真名』搭配，激活 M08+M01。",
       "llm"),
    mk("taboo-089", "夜里听雨须先唤一个已死之人", 5, ["xianxia", "mystery"],
       "与 worldview『每场雨带走记忆最短的那一段』搭配，激活 M05+M08。",
       "llm"),
    mk("taboo-090", "同一年内不得两次原谅同一件事", 5, ["universal"],
       "与 emotion『被原谅之后的不适』搭配，激活 M07+M08。",
       "llm"),
    mk("taboo-091", "写信给尚未出生的人须用左手", 5, ["xianxia", "scifi"],
       "与 body_feature『左手小指先天缺失一节』搭配，激活 M05+M06。",
       "llm"),
    mk("taboo-092", "不得在所有钟停走的一秒内开口", 5, ["scifi", "xianxia"],
       "与 conflict『在所有计时器停走的瞬间完成抉择』搭配，激活 M05+M02。",
       "llm"),
    mk("taboo-093", "替天记账不得以真名自述", 5, ["xianxia", "mythology"] if False else ["xianxia", "mystery"],
       "与 profession『阴曹生死簿誊录员』搭配，激活 M06+M03。",
       "llm"),
    mk("taboo-094", "不得听见自己哭声后立刻笑", 5, ["universal", "mystery"],
       "与 emotion『葬礼上笑出来之后的恐惧』搭配，激活 M07+M08。",
       "llm"),
    mk("taboo-095", "不得让自己影子先迈步过门槛", 5, ["xianxia", "mystery"],
       "与 worldview『影子知道主人下一步但说不出』搭配，激活 M06+M08。",
       "llm"),
    mk("taboo-096", "为陌生人寻魂不得用自己名", 5, ["xianxia", "mystery"],
       "与 profession『通灵副业的客服』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo-097", "一本书被读过第 99 次不得续读", 5, ["xianxia", "scifi"],
       "与 worldview『每本书第一次被读完时作者会咳嗽一声』搭配，激活 M05+M08。",
       "llm"),
    mk("taboo-098", "不得同时持两个不相识之人的名字", 5, ["mystery", "xianxia"],
       "与 conflict『让自己名字从历史消失但留下父亲的』搭配，激活 M06+M03。",
       "llm"),
    mk("taboo-099", "向未相识者行告别礼不得抬眼", 5, ["xianxia", "universal"],
       "与 emotion『被误当作别人时短暂的贪恋』搭配，激活 M06+M07。",
       "llm"),
    mk("taboo-100", "不得把自己的死亡日告诉相信者", 5, ["xianxia", "mystery"],
       "与 worldview『人只看得见自己的死亡时刻』搭配，激活 M03+M07。",
       "llm"),
    mk("taboo-101", "陌生人的临终一句话不得独听", 5, ["mystery", "xianxia"],
       "与 worldview『临终一句话在世间回响三天』搭配，激活 M05+M03。",
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

    assert data["version"] == "v1.5", f"unexpected: {data['version']}"
    assert data["total"] == 500, f"unexpected total: {data['total']}"
    existing = [s["seed_id"] for s in data["seeds"] if s["category"] == "taboo"]
    assert existing == ["taboo-001"], f"unexpected taboo: {existing}"

    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 600
    data["version"] = "v1.6"
    data["changelog"].append({
        "version": "v1.6",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 6/10 禁忌类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频禁忌套路（修仙宗门戒律：血脉禁咒/真名禁忌/师徒禁忌/本命法宝/"
            "同门相残；通用民俗大而泛：孕妇摘果抱小孩搬家/半夜照镜/婚衣不带口袋/"
            "戴孝不进新房/百日不婚/四眼人入洞房）。"
            "策略：细颗粒 + 精确触发条件 + 可视后果；情境化（时间/空间/身份/职业）"
            "+ 精确操作 + 明确代价。直接激活 M01（代价可视化）+ M08（系统反噬）。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 taboo，version→v1.6，total→600")


if __name__ == "__main__":
    main()
