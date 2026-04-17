"""Phase-Seed-1 Batch 9/10 — body_feature 类 100 条入库脚本。

R1/R2/R3/R4/R5 = 5/20/25/30/20，20 human + 80 llm，
追加到 anti-trope-seeds.json，更新 version→v1.9、total→900。

避开 body_feature-001（左手小指先天缺失一节）及 WebSearch 黑名单：
异色瞳/紫瞳/金瞳/红瞳；白发红眼；玛丽苏绝色冰肌；霸总1.8米八块腹肌；
修仙仙骨/灵根/丹田；反派额疤/独眼/断臂；吸血鬼苍白尖牙；二次元猫耳狐尾；
梗化胎记（凤凰徽记/图腾）。

策略：细小的、真实可观察的身体特征——微小疤痕/不对称/习惯性小动作/
细部纹理/生理微反应。激活 M04（角色错位）+ M01（代价可视化）。
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
        "category": "body_feature",
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
# R1 (5) — 日常细小特征
# ---------------------------------------------------------------------------
R1 = [
    mk("body_feature-002", "右手食指比左手食指长半毫米", 1, ["universal"],
       "与 profession『钟表匠学徒』搭配，激活 M04。",
       "human", ["M04"]),
    mk("body_feature-003", "左耳垂有一个没穿过耳洞的小孔", 1, ["universal"],
       "与 emotion『对从未发生的遗憾的具体怀念』搭配，激活 M04+M03。",
       "human", ["M04", "M03"]),
    mk("body_feature-004", "笑的时候左边嘴角先动", 1, ["universal"],
       "与 emotion『被表白后短暂厌恶对方的惊讶』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-005", "右膝盖小时跳皮筋摔的疤", 1, ["realistic", "universal"],
       "与 era『开学第一周』搭配，激活 M01+M06。",
       "llm"),
    mk("body_feature-006", "说话时下巴会微微前伸", 1, ["universal"],
       "与 emotion『被夸耀时想要打断对方的冲动』搭配，激活 M04+M06。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R2 (20) — 较具体细节
# ---------------------------------------------------------------------------
R2 = [
    mk("body_feature-007", "左肩胛一道旧烫伤的月牙形疤", 2, ["realistic", "history"],
       "与 era『1958 年大炼钢铁第一个春天』搭配，激活 M01+M05。",
       "human", ["M01", "M05"]),
    mk("body_feature-008", "右眼视力比左眼弱半档", 2, ["urban", "mystery"],
       "与 profession『法医助理』搭配，激活 M04+M03。",
       "human", ["M04", "M03"]),
    mk("body_feature-009", "锁骨中间一颗指甲盖大的痣", 2, ["romance", "universal"],
       "与 object『一条常年戴着的银项链』搭配，激活 M04+M06。",
       "human", ["M04", "M06"]),
    mk("body_feature-010", "手腕内侧一道几乎褪去的割痕", 2, ["mystery", "urban"],
       "与 emotion『被原谅之后的不适』搭配，激活 M01+M07。",
       "human", ["M01", "M07"]),
    mk("body_feature-011", "左手拇指指甲比右手宽", 2, ["universal"],
       "与 profession『玉雕学徒』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-012", "下嘴唇正中有一道浅裂", 2, ["universal"],
       "与 emotion『说出重话之后假装一切如常的克制』搭配，激活 M04+M01。",
       "llm"),
    mk("body_feature-013", "后颈有三根特别黑的毛", 2, ["mystery", "universal"],
       "与 emotion『被人注视到发痒的后颈』搭配，激活 M06+M04。",
       "llm"),
    mk("body_feature-014", "右手小指关节常年红肿", 2, ["realistic"],
       "与 profession『茶馆学徒』搭配，激活 M01+M06。",
       "llm"),
    mk("body_feature-015", "右耳耳蜗里一颗天生的红点", 2, ["mystery", "universal"],
       "与 taboo『夜半钟响不得应声』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-016", "右手背一枚硬币大的色素沉淀", 2, ["realistic"],
       "与 era『1985 年彩电凭票供应最后一周』搭配，激活 M01+M06。",
       "llm"),
    mk("body_feature-017", "左眼下方一道细细的泪痕", 2, ["romance", "mystery"],
       "与 emotion『无法为理应难过之事哭出来的困惑』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-018", "一哭左脸会先变红", 2, ["universal"],
       "与 emotion『被说「你变了」之后的虚假坚守』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-019", "睡觉时左眼会先闭上", 2, ["universal"],
       "与 conflict『劝服另一个时空的自己不要救自己』搭配，激活 M04。",
       "llm"),
    mk("body_feature-020", "大拇指向后弯能超过 90 度", 2, ["universal"],
       "与 profession『手风琴演奏员』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-021", "睁眼瞬间右眼先开", 2, ["universal"],
       "与 conflict『必须让昨日的自己刺杀今日的自己』搭配，激活 M04+M05。",
       "llm"),
    mk("body_feature-022", "右耳道比左耳深一点", 2, ["universal"],
       "与 worldview『每个人只能听见一种频段的真话』搭配，激活 M03+M04。",
       "llm"),
    mk("body_feature-023", "左手比右手长半厘米", 2, ["universal"],
       "与 taboo『写信给尚未出生的人须用左手』搭配，激活 M04+M05。",
       "llm"),
    mk("body_feature-024", "右边眉毛比左边浓", 2, ["universal"],
       "与 emotion『忽然想起童年伙伴名字时的自责』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-025", "后腰一颗永不褪色的红痣", 2, ["romance", "xianxia"],
       "与 worldview『真正爱过的人月底听见一次敲门声』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-026", "脖子右侧一颗随情绪变深的痣", 2, ["xianxia", "romance"],
       "与 worldview『心跳加速时胸前小痣变深』回声搭配，激活 M04+M07。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R3 (25) — 中等稀缺
# ---------------------------------------------------------------------------
R3 = [
    mk("body_feature-027", "脚底长着一颗朝外的痣", 3, ["xianxia", "mystery"],
       "与 mythology『畲族盘瓠王夜里走过的桥』搭配，激活 M04+M10。",
       "human", ["M04", "M10"]),
    mk("body_feature-028", "胸口正中央一道新月形胎记", 3, ["xianxia", "mystery"],
       "与 worldview『孩子乳牙里藏着父母出生前的秘密』搭配，激活 M04+M06。",
       "human", ["M04", "M06"]),
    mk("body_feature-029", "眼角走向和母亲几乎重合", 3, ["urban", "realistic"],
       "与 emotion『照镜发现自己变得像母亲的一瞬』搭配，激活 M06+M04。",
       "human", ["M06", "M04"]),
    mk("body_feature-030", "食指无意识摩挲拇指的习惯", 3, ["universal"],
       "与 emotion『看陌生人做出自己私密动作的狼狈』搭配，激活 M06+M03。",
       "human", ["M06", "M03"]),
    mk("body_feature-031", "右手掌心一道月牙形旧伤", 3, ["universal"],
       "与 worldview『左手掌有一条只属于自己的时间线』搭配，激活 M05+M01。",
       "human", ["M05", "M01"]),
    mk("body_feature-032", "左手指纹在无名指上缺失", 3, ["mystery"],
       "与 taboo『替他人签字须先签自己名再涂掉』搭配，激活 M03+M04。",
       "llm"),
    mk("body_feature-033", "鼻梁下一颗因紧张变色的小痣", 3, ["mystery", "urban"],
       "与 emotion『被爱人误解却选择不解释的宁愿』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-034", "舌尖一小块终年麻木", 3, ["xianxia", "mystery"],
       "与 mythology『神农尝百草漏尝的一种』搭配，激活 M01+M10。",
       "llm"),
    mk("body_feature-035", "左耳听不见某一特定频率", 3, ["scifi", "xianxia"],
       "与 worldview『每个人只能听见一种频段的真话』搭配，激活 M03+M04。",
       "llm"),
    mk("body_feature-036", "呼吸时胸腔比肋骨先动", 3, ["mystery"],
       "与 conflict『说服永远无法开口的证人作证』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-037", "脚背正中一道绳索勒痕旧疤", 3, ["mystery", "history"],
       "与 era『唐朝安史之乱前第七年夏收』搭配，激活 M01+M05。",
       "llm"),
    mk("body_feature-038", "耳垂背后有一颗隐秘胎记", 3, ["mystery", "xianxia"],
       "与 taboo『收养之子五岁生日前不得改姓』搭配，激活 M06+M03。",
       "llm"),
    mk("body_feature-039", "指甲半月痕比常人多一层", 3, ["xianxia", "mystery"],
       "与 worldview『说谎者 24 小时后嘴唇发黑』搭配，激活 M04+M01。",
       "llm"),
    mk("body_feature-040", "说谎时左手会无意识握拳", 3, ["universal"],
       "与 conflict『不说谎的前提下让所有人都误会自己』搭配，激活 M03+M04。",
       "llm"),
    mk("body_feature-041", "额头正中一颗小时留下的疤", 3, ["universal"],
       "与 era『1986 年义务教育法颁布那天』搭配，激活 M01+M05。",
       "llm"),
    mk("body_feature-042", "声带两道平行的旧痕", 3, ["mystery", "xianxia"],
       "与 conflict『让自己的声音从所有录音消失』搭配，激活 M06+M01。",
       "llm"),
    mk("body_feature-043", "鼻尖左侧一根永远拔不掉的黑毛", 3, ["universal"],
       "与 emotion『被表白后短暂厌恶对方的惊讶』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-044", "下颌一侧长着多余的小臼齿", 3, ["mystery"],
       "与 profession『牙科诊所前台』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-045", "左边锁骨比右边低半厘米", 3, ["universal"],
       "与 emotion『被夸耀时想要打断对方的冲动』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-046", "左右眉弓的角度差 3 度", 3, ["universal"],
       "与 profession『素描老师』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-047", "心脏位置偏右一厘米", 3, ["scifi", "mystery"],
       "与 taboo『把自己的心跳写下后不得读出』搭配，激活 M04+M08。",
       "llm"),
    mk("body_feature-048", "虹膜颜色带微弱金斑", 3, ["xianxia", "mystery"],
       "与 worldview『初见时对方眼眶里短暂出现你的姓氏』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-049", "前额发际线中间一道浅凹陷", 3, ["universal"],
       "与 profession『理发师』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-050", "左手食指背一道被咬过的牙印", 3, ["universal", "mystery"],
       "与 emotion『自己得救时想起未得救陌生人的羞耻』搭配，激活 M01+M07。",
       "llm"),
    mk("body_feature-051", "右脚脚心一颗会生长的痣", 3, ["mystery", "xianxia"],
       "与 worldview『每件物品记得最后一次被触摸的温度』搭配，激活 M04+M08。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R4 (30) — 稀缺
# ---------------------------------------------------------------------------
R4 = [
    mk("body_feature-052", "颈下一撮天生的柔毛", 4, ["xianxia", "mystery"],
       "与 mythology『山海经·英招身为马而人面』搭配，激活 M06+M10。",
       "human", ["M06", "M10"]),
    mk("body_feature-053", "舌根下一枚米粒大的银疤", 4, ["mystery", "xianxia"],
       "与 conflict『说服永远无法开口的证人作证』搭配，激活 M03+M01。",
       "human", ["M03", "M01"]),
    mk("body_feature-054", "无名指指纹跟食指指纹完全一样", 4, ["mystery", "scifi"],
       "与 profession『刑事科学技术员』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("body_feature-055", "右耳耳垂比左耳长一截", 4, ["xianxia", "mystery"],
       "与 mythology『山海经·奢比尸之人耳长于口三寸』搭配，激活 M06+M10。",
       "human", ["M06", "M10"]),
    mk("body_feature-056", "右手小指天生比左手短一毫米", 4, ["universal"],
       "与 conflict『要同时赢两场你无法公开参加的比赛』搭配，激活 M03+M06。",
       "human", ["M03", "M06"]),
    mk("body_feature-057", "瞳孔颜色不对称", 4, ["xianxia", "mystery"],
       "与 worldview『陌生人第一次对视能读出对方一个后悔』搭配，激活 M06+M03。",
       "human", ["M06", "M03"]),
    mk("body_feature-058", "胸口一道只能在月光下看见的纹路", 4, ["xianxia", "mystery"],
       "与 taboo『夜里听雨须先唤一个已死之人』搭配，激活 M04+M08。",
       "llm"),
    mk("body_feature-059", "右肩胛骨下一枚蝶翼形浅纹", 4, ["xianxia", "mystery"],
       "与 mythology『苗族蝴蝶妈妈生十二蛋的顺序』搭配，激活 M06+M10。",
       "llm"),
    mk("body_feature-060", "手腕处一圈浅浅的勒痕", 4, ["mystery", "urban"],
       "与 emotion『对自己仓皇时的温柔』搭配，激活 M01+M07。",
       "llm"),
    mk("body_feature-061", "额角一颗会忽隐忽现的痣", 4, ["xianxia", "mystery"],
       "与 worldview『每当有人忘了你你便短暂失忆一次』搭配，激活 M08+M06。",
       "llm"),
    mk("body_feature-062", "左胸上方一颗随心跳变深的浅痣", 4, ["xianxia", "romance"],
       "与 worldview『心跳加速时胸前小痣微微变深』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-063", "一粒从不褪色的胎记沉到骨缝", 4, ["xianxia", "mystery"],
       "与 conflict『必须对抗一个由自己记忆构成的敌人』搭配，激活 M07+M08。",
       "llm"),
    mk("body_feature-064", "掌心一道月牙形常磨的浅纹", 4, ["mystery", "xianxia"],
       "与 mythology『精卫填海带回的第一枚石子』搭配，激活 M01+M10。",
       "llm"),
    mk("body_feature-065", "左眼角下方一道泪痣", 4, ["romance", "xianxia"],
       "与 worldview『每条河下游能听见上游承诺』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-066", "眉骨高出常人半分", 4, ["xianxia", "mystery"],
       "与 mythology『满族长白山鳌花鱼的三次变脸』搭配，激活 M06+M10。",
       "llm"),
    mk("body_feature-067", "虎牙比常人略长", 4, ["universal"],
       "与 worldview『早晨六点整所有人牙齿微凉』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-068", "舌头侧面一道看不清的浅裂", 4, ["mystery"],
       "与 taboo_language『古藏 Bon 教密咒不得念满九遍』搭配，激活 M03+M08。",
       "llm"),
    mk("body_feature-069", "右肩胛一道天生的新月疤", 4, ["xianxia", "mystery"],
       "与 mythology『藏族格萨尔王失而复得的护心镜』搭配，激活 M06+M10。",
       "llm"),
    mk("body_feature-070", "右耳后一颗与故人同位的浅痣", 4, ["mystery", "universal"],
       "与 conflict『必须阻止所有人记起一个已死去的朋友』搭配，激活 M06+M08。",
       "llm"),
    mk("body_feature-071", "背部一处童年烫伤的痕迹", 4, ["realistic", "universal"],
       "与 emotion『被恶意攻击时忽然回到童年的缩小』搭配，激活 M06+M08。",
       "llm"),
    mk("body_feature-072", "喉结处一颗会跳动的浅痣", 4, ["xianxia", "romance"],
       "与 body_feature 自指：对 worldview-022『真话打喷嚏』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-073", "左手无名指永远比右手略肿", 4, ["mystery", "romance"],
       "与 conflict『在离婚协议上签下不相关之人的名字』搭配，激活 M01+M06。",
       "llm"),
    mk("body_feature-074", "耳道里残留的海水的咸味", 4, ["apocalypse", "universal"],
       "与 era『2004 年印度洋海啸次日』搭配，激活 M01+M05。",
       "llm"),
    mk("body_feature-075", "小指第二节的细纹每年多一道", 4, ["xianxia", "mystery"],
       "与 worldview『每次被背叛背叛者手指多一道纹』搭配，激活 M01+M06。",
       "llm"),
    mk("body_feature-076", "胸前一道弓弦磨出的茧", 4, ["history", "xianxia"],
       "与 profession『猎户传人』搭配，激活 M01+M06。",
       "llm"),
    mk("body_feature-077", "额头正中一道命字形的细痕", 4, ["xianxia", "mystery"],
       "与 worldview『名字里藏着能杀死自己的那一笔』搭配，激活 M06+M08。",
       "llm"),
    mk("body_feature-078", "头发长得比常人略快", 4, ["xianxia", "mystery"],
       "与 worldview『说秘密瞬间听者头发略变长』搭配，激活 M01+M03。",
       "llm"),
    mk("body_feature-079", "瞳孔里有一环不易察觉的灰", 4, ["xianxia", "scifi"],
       "与 emotion『被自己的梦抛弃时的孤绝』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-080", "右手掌纹少一条生命线", 4, ["xianxia", "mystery"],
       "与 taboo『不得把自己的死亡日告诉相信者』搭配，激活 M03+M08。",
       "llm"),
    mk("body_feature-081", "脚踝一圈看得见的锁链印", 4, ["mystery", "history"],
       "与 era『伪满康德十年新京立春』搭配，激活 M01+M06。",
       "llm"),
]

# ---------------------------------------------------------------------------
# R5 (20) — 哲学/神秘/时空身体
# ---------------------------------------------------------------------------
R5 = [
    mk("body_feature-082", "胎记形状是自己未出生前一个梦", 5, ["xianxia", "scifi"],
       "与 worldview『每人一生都是别人做过的一个梦』搭配，激活 M05+M06。",
       "human", ["M05", "M06"]),
    mk("body_feature-083", "影子比自己矮两寸", 5, ["xianxia", "mystery"],
       "与 taboo『不得让自己影子先迈步过门槛』搭配，激活 M06+M08。",
       "human", ["M06", "M08"]),
    mk("body_feature-084", "瞳孔里映出不属于这世界的光", 5, ["scifi", "xianxia"],
       "与 era『玛雅长计历 13.0.0.0.0 东八区凌晨』搭配，激活 M05+M10。",
       "human", ["M05", "M10"]),
    mk("body_feature-085", "心脏每一次跳动声音不同", 5, ["xianxia", "mystery"],
       "与 taboo『把自己的心跳写下后不得读出』搭配，激活 M04+M08。",
       "llm"),
    mk("body_feature-086", "手心里藏着一个别人看不见的字", 5, ["xianxia", "mystery"],
       "与 conflict『让一本尚未写出的书提前自毁』搭配，激活 M03+M06。",
       "llm"),
    mk("body_feature-087", "身上比常人少一块肌肉", 5, ["scifi", "xianxia"],
       "与 conflict『主角必须证明自己从未存在』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-088", "血的温度比体温低三度", 5, ["xianxia", "scifi"],
       "与 worldview『死亡是借来的寿命须还给最后见死者』搭配，激活 M01+M08。",
       "llm"),
    mk("body_feature-089", "指甲上浮现过的三行古文", 5, ["xianxia", "mystery"],
       "与 taboo_language『失传回鹘文「太阳」写错者须焚』搭配，激活 M03+M10。",
       "llm"),
    mk("body_feature-090", "眼泪蒸发速度比常人快", 5, ["xianxia", "scifi"],
       "与 emotion『无法为理应难过之事哭出来的困惑』搭配，激活 M04+M07。",
       "llm"),
    mk("body_feature-091", "呼吸比常人慢一拍", 5, ["scifi", "xianxia"],
       "与 worldview『所有真话被说出前一秒已被听见』搭配，激活 M05+M04。",
       "llm"),
    mk("body_feature-092", "头发里有一根天生是银色", 5, ["xianxia", "mystery"],
       "与 worldview『说谎者 24 小时后嘴唇发黑』搭配，激活 M04+M01。",
       "llm"),
    mk("body_feature-093", "骨骼里多了一块没有名字的小骨", 5, ["scifi", "xianxia"],
       "与 profession『骨密度扫描仪校准员』搭配，激活 M04+M10。",
       "llm"),
    mk("body_feature-094", "手指在数数时总多出一个", 5, ["xianxia", "scifi"],
       "与 conflict『让两个互斥的真相同时为真』搭配，激活 M10+M04。",
       "llm"),
    mk("body_feature-095", "身上一处永远不长汗毛", 5, ["xianxia", "mystery"],
       "与 taboo『不得同时梦见自己与自己的名字』搭配，激活 M04+M08。",
       "llm"),
    mk("body_feature-096", "皮肤在月圆夜会微微透光", 5, ["xianxia", "mystery"],
       "与 taboo『谎话在当日月圆时被墙壁记住』搭配，激活 M04+M08。",
       "llm"),
    mk("body_feature-097", "心跳与人对视时会共振", 5, ["xianxia", "romance"],
       "与 emotion『陌生人第一次对视能读出对方一个后悔』搭配，激活 M04+M03。",
       "llm"),
    mk("body_feature-098", "牙齿不透 X 光", 5, ["scifi", "mystery"],
       "与 profession『口腔影像科技师』搭配，激活 M03+M04。",
       "llm"),
    mk("body_feature-099", "脚印留下的时间比踩踏瞬间长", 5, ["xianxia", "mystery"],
       "与 worldview『每件物品记得最后一次被触摸的温度』搭配，激活 M05+M04。",
       "llm"),
    mk("body_feature-100", "体内某处一直有两个心脏声", 5, ["scifi", "xianxia"],
       "与 conflict『与自己合谋谋杀自己的另一个版本』搭配，激活 M04+M06。",
       "llm"),
    mk("body_feature-101", "照镜时少一道影子", 5, ["xianxia", "mystery"],
       "与 worldview『所有镜子记录上一被照者相貌一整天』搭配，激活 M06+M08。",
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

    # 内容级去重：防止 value 字面重复（本批只检查本批内）
    values = [s["value"] for s in ALL_SEEDS]
    assert len(set(values)) == len(values), f"duplicate value: {[v for v in values if values.count(v) > 1]}"

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

    assert data["version"] == "v1.8", f"unexpected: {data['version']}"
    assert data["total"] == 800, f"unexpected total: {data['total']}"
    existing = [s["seed_id"] for s in data["seeds"] if s["category"] == "body_feature"]
    assert existing == ["body_feature-001"], f"unexpected body_feature: {existing}"

    data["seeds"].extend(ALL_SEEDS)
    data["total"] = 900
    data["version"] = "v1.9"
    data["changelog"].append({
        "version": "v1.9",
        "date": "2026-04-17",
        "delta": 100,
        "note": (
            "Batch 9/10 身体特征类入库。分布 R1/R2/R3/R4/R5 = 5/20/25/30/20；"
            "R4+R5=50%，R5=20%。20 条用户 review 通过 (source=human)，"
            "80 条 LLM 生成 (source=llm)。WebSearch 反查已剔除起点+番茄双平台"
            "高频身体特征套路（异色瞳紫瞳金瞳红瞳/白发红眼/玛丽苏绝色冰肌/"
            "霸总1.8米八块腹肌/修仙仙骨灵根丹田/反派额疤独眼断臂/吸血鬼苍白尖牙/"
            "二次元猫耳狐尾/梗化胎记凤凰徽记图腾）。"
            "策略：细小的、真实可观察的身体特征——微小疤痕 / 不对称 / "
            "习惯性小动作 / 细部纹理 / 生理微反应。"
            "直接激活 M04（角色错位）+ M01（代价可视化）。"
        ),
    })

    with SEEDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ 已追加 100 条 body_feature，version→v1.9，total→900")


if __name__ == "__main__":
    main()
