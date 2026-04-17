"""Phase-Seed-1 Batch 8/10 — taboo_language 类 100 条入库脚本。

R1/R2/R3/R4/R5 = 5/20/25/30/20，20 human + 80 llm，
追加到 anti-trope-seeds.json，更新 version→v1.8、total→800。

避开 taboo_language-001（闽南语讣告「转厝」）及 WebSearch 黑名单：
道家流行咒（临兵斗者皆阵列在前/急急如律令/天地无极乾坤借法）、
江湖老梗切口（天王盖地虎/宝塔镇河妖）、二次元日式敬语（様/さん/ちゃん）、
哈利波特咒（Avada Kedavra 等）、六字真言堆砌、D&D 系统咒。

策略：方言讳字 / 职业行话 / 地域切口 / 仪式词 / 冷门民族祈祷 /
失传古文字片段——每条都是精确的语言规则（何时/何地/谁/不得 ⇒ 后果）。
命中 M06（身份反差）+ M03（信息不对称）。
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
        "category": "taboo_language",
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
# R1 (5) — 日常禁忌语
# ---------------------------------------------------------------------------
R1 = [
    mk("taboo_language-002", "家中不得说「死」字须用「走了」", 1, ["universal"],
       "与 era『春节前三天』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo_language-003", "饭桌不得说「完」字须用「好了」", 1, ["universal"],
       "与 emotion『年终最后一天对任何决定的疲惫』搭配，激活 M03。",
       "human", ["M03"]),
    mk("taboo_language-004", "医院不得说「再见」须用「保重」", 1, ["urban", "realistic"],
       "与 profession『医院探视登记员』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-005", "出差前家人不得问「几时回」", 1, ["universal"],
       "与 emotion『独自旅行第三日的过度兴奋』搭配，激活 M03。",
       "llm"),
    mk("taboo_language-006", "除夕家中不得说「完」字", 1, ["history", "universal"],
       "与 era『春节前三天』搭配，激活 M03+M09。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 (20) — 具体地域/时代/民俗禁忌语
# ---------------------------------------------------------------------------
R2 = [
    mk("taboo_language-007", "粤语讣告中的「仙游」替代「死」", 2, ["realistic", "history"],
       "与 profession『殡仪馆追思稿代写员』搭配，激活 M06+M03。",
       "human", ["M06", "M03"]),
    mk("taboo_language-008", "北京梨园行「三六九等」不得乱序", 2, ["history", "realistic"],
       "与 profession『老戏班班主助理』搭配，激活 M06+M09。",
       "human", ["M06", "M09"]),
    mk("taboo_language-009", "潮汕丧事「过身」不得说成「走了」", 2, ["realistic", "history"],
       "与 mythology『孟婆熬汤加盐的手势』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo_language-010", "上海石库门邻里「吃翻生」忌说", 2, ["urban", "realistic"],
       "与 era『1992 年上海股票认购证摇号当天』搭配，激活 M03+M05。",
       "human", ["M03", "M05"]),
    mk("taboo_language-011", "川剧后台不得说「倒」字", 2, ["history", "realistic"],
       "与 taboo『戏班接客前须由小孩踩台』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-012", "东北民俗「狐仙」改称「小三家」", 2, ["history", "mystery"],
       "与 profession『胡家堂口香头』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-013", "湘西赶尸人夜呼「让路」", 2, ["xianxia", "mystery"],
       "与 era『惊蛰节气五更天』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo_language-014", "客家围屋晚辈不得直呼长辈名", 2, ["history", "realistic"],
       "与 taboo『家中八仙桌缺角那一边不得坐人』搭配，激活 M06+M09。",
       "llm"),
    mk("taboo_language-015", "胶东渔家出海不得说「翻」", 2, ["realistic", "history"],
       "与 taboo『渔民出海不得提「翻」字』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo_language-016", "江南丧仪「披麻」不得说「白」", 2, ["history", "realistic"],
       "与 taboo『丧服未脱不得见生人』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-017", "晋中钱庄账房「黄」字忌用", 2, ["history", "realistic"],
       "与 profession『票号老账房』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-018", "徽州祠堂告祖文不得提「离」字", 2, ["history", "realistic"],
       "与 object『一本被划掉一行的家谱』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-019", "闽粤茶楼「倒茶」须叩三指", 2, ["history", "realistic"],
       "与 profession『茶博士学徒』搭配，激活 M06+M09。",
       "llm"),
    mk("taboo_language-020", "吴语「无啥事体」忌在病房说", 2, ["urban", "realistic"],
       "与 profession『医院值夜护士』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-021", "北派评书台下不得叫「好」", 2, ["history", "realistic"],
       "与 profession『评书场老管事』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-022", "蜀地老话「走水」指火灾", 2, ["history", "realistic"],
       "与 era『1987 年大兴安岭林火燃烧第三日』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-023", "回族屠宰前须念「太斯米」", 2, ["history", "realistic"],
       "与 profession『清真屠宰场宰牲师』搭配，激活 M06+M09。",
       "llm"),
    mk("taboo_language-024", "西北民歌「花儿」丧期不唱", 2, ["history", "realistic"],
       "与 taboo『丧服未脱不得见生人』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-025", "湘潭老人寿诞不得讲「百」字", 2, ["history", "realistic"],
       "与 emotion『故人老去那一刻的心疼也松一口气』搭配，激活 M03+M07。",
       "llm"),
    mk("taboo_language-026", "江淮船帮暗语「压舱」不外传", 2, ["history", "realistic"],
       "与 profession『船帮水手头』搭配，激活 M03+M06。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 (25) — 职业/黑话/时代话语
# ---------------------------------------------------------------------------
R3 = [
    mk("taboo_language-027", "刑警卷宗里「失踪」一词不得连写", 3, ["mystery", "urban"],
       "与 profession『派出所失踪人口登记员』搭配，激活 M03+M09。",
       "human", ["M03", "M09"]),
    mk("taboo_language-028", "铁路调度「故障」须用「情况」", 3, ["realistic", "urban"],
       "与 era『1998 年九江大堤合龙那一夜』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo_language-029", "法医报告中「死亡」前不得空格", 3, ["mystery", "realistic"],
       "与 taboo『法医出庭不得佩戴任何首饰』搭配，激活 M03+M01。",
       "human", ["M03", "M01"]),
    mk("taboo_language-030", "地铁播报「闯入」须说成「越线」", 3, ["urban", "scifi"],
       "与 worldview『末班地铁末节车厢不得坐一个人』搭配，激活 M03+M09。",
       "human", ["M03", "M09"]),
    mk("taboo_language-031", "医院值班表「故去」须用代码", 3, ["realistic", "mystery"],
       "与 profession『医院探视登记员』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo_language-032", "殡仪馆登记「小名」一栏永远留空", 3, ["mystery", "urban"],
       "与 taboo『火化师封炉时不得说出死者小名』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-033", "老邮差分拣口诀不得教外人", 3, ["history", "realistic"],
       "与 profession『铁路邮运老班长』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-034", "旧码头挑夫「上肩」数三不得四", 3, ["history", "realistic"],
       "与 body_feature『左肩一道常年磨出的浅痕』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-035", "北京琉璃厂老掌柜说价不报整数", 3, ["history", "realistic"],
       "与 profession『古玩店学徒』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-036", "广东中医馆药方「斤」字不得顿笔", 3, ["history", "realistic"],
       "与 object『一张墨迹洇开的药方』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-037", "广州十三行暗语「花」指走私", 3, ["history", "mystery"],
       "与 era『1840 年鸦片战争宣战诏下达当晚』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo_language-038", "潮剧戏班后台「倒仓」不得明言", 3, ["history", "realistic"],
       "与 body_feature『嗓音忽然失去一个八度』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-039", "云南马帮「扎紧」暗示险情", 3, ["history", "realistic"],
       "与 profession『马帮头马把式』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo_language-040", "江湖郎中收诊银喊「谢赏」", 3, ["history", "realistic"],
       "与 profession『走方卖药郎中』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-041", "码头帮「掰子」指断约", 3, ["history", "mystery"],
       "与 conflict『必须替亲弟弟顶罪上战场』搭配，激活 M03+M02。",
       "llm"),
    mk("taboo_language-042", "票号老账房「撒印」前不得说话", 3, ["history", "realistic"],
       "与 era『1992 年上海股票认购证摇号当天』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-043", "老中药铺「麝」字须先避第三笔", 3, ["history", "mystery"],
       "与 object『一方只用过一次的松烟墨』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-044", "宫廷太医「龙体」后不得加形容词", 3, ["history"],
       "与 era『清末光绪大婚当天紫禁城』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-045", "清末邮驿「急件」上不得加名", 3, ["history"],
       "与 object『一封投错地址的挂号信』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-046", "老戏班「倒仓」指嗓子失声", 3, ["history", "realistic"],
       "与 body_feature『声带两道平行的旧痕』搭配，激活 M06+M01。",
       "llm"),
    mk("taboo_language-047", "民国报馆「社论」后不得加句号", 3, ["history"],
       "与 profession『文化馆放映员』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-048", "军营伙房「添饭」不得说「满」", 3, ["history", "realistic"],
       "与 profession『部队炊事班长』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-049", "冶炼厂「开炉」时不得见女工", 3, ["history", "realistic"],
       "与 era『1958 年大炼钢铁第一个春天』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-050", "船厂铆工交班暗语「留一颗」", 3, ["history", "realistic"],
       "与 era『1988 年海南建省前一天』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo_language-051", "渔港鱼栏「称鱼」不得读出零头", 3, ["realistic"],
       "与 profession『鱼栏过秤账房』搭配，激活 M03+M09。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 (30) — 秘传/冷门民族/仪式话语
# ---------------------------------------------------------------------------
R4 = [
    mk("taboo_language-052", "萨满「请神」三字须每字吐三气", 4, ["xianxia", "mystery"],
       "与 mythology『阎罗点名簿的第一页空白』搭配，激活 M03+M10。",
       "human", ["M03", "M10"]),
    mk("taboo_language-053", "摩尼教问候「光明之友」只问不答", 4, ["history", "mystery"],
       "与 era『阿拔斯白衣大食使节抵长安夜』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("taboo_language-054", "琉球祭祀「神歌」祭司之外不得听", 4, ["history", "mystery"],
       "与 mythology『日本·天照隐身岩洞第三十天』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo_language-055", "布朗族祭竹楼新歌只唱一半", 4, ["xianxia", "history"],
       "与 body_feature『歌喉里一道天生的粗气』搭配，激活 M06+M03。",
       "human", ["M06", "M03"]),
    mk("taboo_language-056", "纳西族东巴咒符「三声禁」", 4, ["xianxia", "mystery"],
       "与 mythology『纳西族东巴经的最后一页空白』搭配，激活 M03+M10。",
       "human", ["M03", "M10"]),
    mk("taboo_language-057", "阿昌族「瑞丽江」名不得在雨前说", 4, ["xianxia", "history"],
       "与 worldview『每场雨带走记忆最短的那一段』搭配，激活 M05+M03。",
       "human", ["M05", "M03"]),
    mk("taboo_language-058", "朝鲜族「阿里郎」丧日不唱", 4, ["history", "realistic"],
       "与 emotion『葬礼上笑出来之后的恐惧』搭配，激活 M03+M07。",
       "llm"),
    mk("taboo_language-059", "锡伯族「西迁」二字祭仪不得提", 4, ["history", "xianxia"],
       "与 era『1985 年居民身份证启用首日』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo_language-060", "鄂温克驯鹿部「索伦」音须压低", 4, ["history", "xianxia"],
       "与 profession『驯鹿牧业合作社会计』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-061", "赫哲族「伊玛堪」叙事死者名只一次", 4, ["xianxia", "history"],
       "与 mythology『黄泉路上的三生石反面』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-062", "京族「哈节」祈辞不得反念", 4, ["xianxia", "history"],
       "与 mythology『傣族泼水节的第一瓢水』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-063", "拉祜族「猎手叩首」五字须先呼气", 4, ["xianxia", "history"],
       "与 body_feature『胸前一道弓弦磨出的茧』搭配，激活 M03+M01。",
       "llm"),
    mk("taboo_language-064", "哈尼族「梯田开犁」祝词不得错序", 4, ["xianxia", "history"],
       "与 mythology『哈尼族四月太阳节的滑箩声』搭配，激活 M03+M09。",
       "llm"),
    mk("taboo_language-065", "黎族「三月三」对歌不得提名字", 4, ["xianxia", "romance"],
       "与 worldview『本名被喊满一百次后会引起回头』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-066", "满族「萨满神辞」结尾音不得压", 4, ["xianxia", "history"],
       "与 mythology『满族长白山鳌花鱼的三次变脸』搭配，激活 M03+M10。",
       "llm"),
    mk("taboo_language-067", "维吾尔「麦西来甫」开场词不得读全", 4, ["xianxia", "history"],
       "与 profession『乡文化站维文翻译』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-068", "哈萨克「阿肯弹唱」结束时不得笑", 4, ["xianxia", "history"],
       "与 emotion『无法为理应难过之事哭出来的困惑』搭配，激活 M03+M07。",
       "llm"),
    mk("taboo_language-069", "瑶族「盘王节」祭辞不得白日念", 4, ["xianxia", "history"],
       "与 mythology『畲族盘瓠王夜里走过的桥』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-070", "侗族「大歌」收尾不得有词", 4, ["xianxia", "history"],
       "与 taboo_language 自指：对结尾音的禁法，激活 M03+M08。",
       "llm"),
    mk("taboo_language-071", "畲族「凤凰歌」传女不传男", 4, ["xianxia", "history"],
       "与 profession『畲族歌师传人』搭配，激活 M06+M03。",
       "llm"),
    mk("taboo_language-072", "苗族「古歌」夜不过三段", 4, ["xianxia", "history"],
       "与 taboo『送葬队伍过完不得立即关门』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-073", "门巴族「六弦琴」曲不得错调", 4, ["xianxia", "history"],
       "与 object『一把音色特异的六弦琴』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-074", "珞巴族「抖露霞」词只在雨季说", 4, ["xianxia", "history"],
       "与 era『二十四节气「大雪」黎明』搭配，激活 M05+M03。",
       "llm"),
    mk("taboo_language-075", "塔吉克「鹰笛」调不得录下", 4, ["xianxia", "history"],
       "与 worldview『让自己的声音从所有录音里消失』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo_language-076", "回族「讨白」祈辞中「我」字须去", 4, ["xianxia", "history"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M03+M06。",
       "llm"),
    mk("taboo_language-077", "古藏文「敦煌写卷」地名不得倒", 4, ["xianxia", "history"],
       "与 era『敦煌藏经洞 1900 年被打开那一天』搭配，激活 M05+M03。",
       "llm"),
    mk("taboo_language-078", "伊斯兰书信开头「奉」字不得缺", 4, ["xianxia", "history"],
       "与 profession『清真寺阿訇文书』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-079", "东巴象形字「回家」不得正读", 4, ["xianxia", "history"],
       "与 emotion『路过年轻时住过的地方的平淡』搭配，激活 M03+M07。",
       "llm"),
    mk("taboo_language-080", "水族「水书」日子字不得誊抄", 4, ["xianxia", "history"],
       "与 object『一张被揉过的水书残页』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-081", "象雄文「苯教」诵经不得夹汉音", 4, ["xianxia", "history"],
       "与 taboo『翻译典籍不得在朔日起头』搭配，激活 M03+M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 (20) — 失传/神秘语言/时空话语
# ---------------------------------------------------------------------------
R5 = [
    mk("taboo_language-082", "不得在月食夜说出亡人小名", 5, ["xianxia", "mystery"],
       "与 taboo『火化师封炉时不得说出死者小名』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo_language-083", "读巴利语偈颂时不得看镜", 5, ["xianxia", "mystery"],
       "与 worldview『所有镜子记录上一被照者相貌一整天』搭配，激活 M03+M08。",
       "human", ["M03", "M08"]),
    mk("taboo_language-084", "古波斯祆教「胡玛」不得说两次", 5, ["xianxia", "history"],
       "与 mythology『古埃及·死者之书第 125 章的签名』搭配，激活 M10+M08。",
       "human", ["M10", "M08"]),
    mk("taboo_language-085", "西夏文「天授」不得夹金文", 5, ["xianxia", "history"],
       "与 era『西夏天盛年末河西走廊』搭配，激活 M05+M03。",
       "llm"),
    mk("taboo_language-086", "契丹小字「万岁」不得顿笔", 5, ["xianxia", "history"],
       "与 era『契丹保大五年二月十七酉时』搭配，激活 M05+M03。",
       "llm"),
    mk("taboo_language-087", "楔形泥版「吉尔伽美什」泥干后不刻", 5, ["xianxia", "history"],
       "与 mythology『苏美尔·吉尔伽美什失永生草的沙地』搭配，激活 M05+M10。",
       "llm"),
    mk("taboo_language-088", "古希腊「俄耳甫斯」颂诗结尾不得写", 5, ["xianxia", "romance"],
       "与 mythology『希腊·俄尔甫斯回头前一步的暂停』搭配，激活 M03+M05。",
       "llm"),
    mk("taboo_language-089", "古叙利亚「主恩临」三字不得连写", 5, ["xianxia", "history"],
       "与 profession『景教寺誊经人』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-090", "梵语「唵」字不得独诵百次", 5, ["xianxia", "history"],
       "与 worldview『本名被喊满一百次后会引起回头』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-091", "古埃及圣书体「名」字不得单书", 5, ["xianxia", "history"],
       "与 mythology『埃及·托特记账册的空白页数量』搭配，激活 M03+M10。",
       "llm"),
    mk("taboo_language-092", "凯尔特「德鲁伊」咒里不得有水字", 5, ["xianxia", "mystery"],
       "与 mythology『克尔特·德鲁伊三日不食看见符号』搭配，激活 M03+M10。",
       "llm"),
    mk("taboo_language-093", "玛雅历「剥皮之月」读音不得留音", 5, ["xianxia", "apocalypse"],
       "与 era『玛雅长计历 13.0.0.0.0 东八区凌晨』搭配，激活 M05+M10。",
       "llm"),
    mk("taboo_language-094", "荷马史诗「无名之人」不得对死者说", 5, ["xianxia", "history"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-095", "古北欧卢恩文「Algiz」不得倒写", 5, ["xianxia", "history"],
       "与 mythology『北欧·诸神黄昏前一日的晴天』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-096", "古日语「神遗び」祭辞生者前不念", 5, ["xianxia", "history"],
       "与 mythology『日本·天照隐身岩洞第三十天』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-097", "失传回鹘文「太阳」写错者须焚", 5, ["xianxia", "history"],
       "与 object『一块写着回鹘文的残木牍』搭配，激活 M01+M08。",
       "llm"),
    mk("taboo_language-098", "水书「龙日」二字不得出现在讣告", 5, ["xianxia", "mystery"],
       "与 taboo『墓志铭完稿不得在夜里晾干』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-099", "吐火罗文「光明」词只在日出前说", 5, ["xianxia", "history"],
       "与 era『古藏文敦煌写卷地名不得倒』之回声，激活 M05+M03。",
       "llm"),
    mk("taboo_language-100", "古藏 Bon 教密咒不得念满九遍", 5, ["xianxia", "mystery"],
       "与 worldview『一生只有三次完整原谅别人的机会』搭配，激活 M03+M08。",
       "llm"),
    mk("taboo_language-101", "楔形阿卡德语「永生」不得封入坟", 5, ["xianxia", "history"],
       "与 mythology『苏美尔·吉尔伽美什失永生草的沙地』搭配，激活 M03+M10。",
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

    assert data["version"] == "v1.7", f"unexpected: {data['version']}"
    assert data["total"] == 700, f"unexpected total: {data['total']}"
    existing = [s["seed_id"] for s in data["seeds"] if s["category"] == "taboo_language"]
    assert existing == ["taboo_language-001"], f"unexpected taboo_language: {existing}"

    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 800
    data["version"] = "v1.8"
    data["changelog"].append({
        "version": "v1.8",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 8/10 禁忌语言类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频禁忌语言套路（道家流行咒临兵斗者皆阵列在前/急急如律令/"
            "天地无极乾坤借法；江湖老梗切口天王盖地虎宝塔镇河妖；"
            "二次元日式敬语様さんちゃん；哈利波特咒；六字真言堆砌；D&D 系统咒）。"
            "策略：方言讳字 / 职业行话 / 地域切口 / 仪式词 / 冷门民族祈祷 / "
            "失传古文字片段。100 条覆盖中国八大方言讳字（粤闽潮吴湘客川晋）+ "
            "行业黑话（刑警/铁路/法医/地铁/殡仪/邮差/码头/中医/十三行/戏班）+ "
            "冷门民族祈祷语（萨满/摩尼/琉球/布朗/纳西/阿昌/锡伯/鄂温克/赫哲/京/"
            "拉祜/黎/京族/哈萨克/瑶/侗/畲/苗/门巴/珞巴/塔吉克/回/藏/水/象雄）+ "
            "失传古文字（西夏/契丹/楔形/古希腊/凯尔特/卢恩/回鹘/吐火罗/Bon/阿卡德）。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 taboo_language，version→v1.8，total→800")


if __name__ == "__main__":
    main()
