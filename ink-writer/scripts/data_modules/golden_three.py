#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Golden three chapter strategy helpers.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Dict, List

try:
    from .genre_aliases import to_profile_key
except ImportError:  # pragma: no cover
    from genre_aliases import to_profile_key


DEFAULT_OPENING_STRATEGY = {
    "golden_three_enabled": True,
    "profile": "genre_adaptive_commercial",
    "gate": "hard_first_three",
}

GENRE_MODE_MAP = {
    "xianxia": "爽点种子/压制/不公/利益/力量信号",
    "shuangwen": "爽点种子/压制/不公/利益/力量信号",
    "urban-power": "爽点种子/压制/不公/利益/力量信号",
    "history-travel": "知识优势/身份差距/资源机会/规则卡位",
    "game-lit": "系统奖励/资源争夺/数值突破/规则差距",
    "livestream": "数据波动/利益冲突/即时反制/舆论反馈",
    "romance": "情绪暴击/关系反转/身份张力",
    "substitute": "情绪暴击/关系反转/身份张力",
    "mystery": "异常/线索冲突/倒计时",
    "rules-mystery": "异常/规则冲突/倒计时",
    "cosmic-horror": "异常/规则冲突/倒计时",
}

GENRE_TRIGGER_TOKENS = {
    "xianxia": ("压制", "羞辱", "境界", "灵石", "机缘", "杀", "打", "系统", "退婚"),
    "shuangwen": ("打脸", "羞辱", "压制", "奖励", "系统", "逆袭", "机会", "利益"),
    "urban-power": ("压制", "老板", "资源", "身份", "项目", "规则", "打脸", "背景"),
    "history-travel": ("身份", "规矩", "抄家", "婚约", "科举", "银子", "家法", "机会"),
    "game-lit": ("系统", "任务", "奖励", "副本", "等级", "资源", "倒计时", "掉落"),
    "livestream": ("热搜", "直播", "弹幕", "数据", "打赏", "封号", "对赌", "热度"),
    "romance": ("离婚", "婚约", "前任", "背叛", "怀孕", "订婚", "冷战", "相亲"),
    "substitute": ("替身", "白月光", "离婚", "前任", "误会", "订婚", "背叛", "身份"),
    "mystery": ("尸体", "失踪", "异常", "线索", "规则", "不能", "广播", "倒计时"),
    "rules-mystery": ("规则", "不能", "违反", "广播", "倒计时", "异常", "污染", "诡异"),
    "cosmic-horror": ("污染", "梦境", "异常", "低语", "规则", "倒计时", "失真", "不可名状"),
}

SCENIC_OPENING_PATTERNS = (
    r"^(天[色空]|夜[色空]|晨光|夕阳|阳光|微风|风里|雨夜|月色|星光|雾气|街道|山门|庭院)",
    r"^(清晨|凌晨|黄昏|夜里|半夜|这一日|这一天)",
)

ABSTRACT_OPENING_PATTERNS = (
    "人生",
    "命运",
    "岁月",
    "世界就是如此",
    "很多时候",
    "没有人知道",
    "直到很多年后",
    "后来他才知道",
)

WORLD_BUILDING_PATTERNS = (
    "这个世界",
    "这片大陆",
    "天下分为",
    "共有",
    "传说中",
    "按照等级",
    "宗门分为",
    "王朝",
)

BACKSTORY_PATTERNS = (
    "小时候",
    "很多年前",
    "三年前",
    "五年前",
    "回忆起",
    "从前",
    "那一年",
)


def is_golden_three_chapter(chapter: int) -> bool:
    try:
        return 1 <= int(chapter) <= 3
    except (TypeError, ValueError):
        return False


def build_default_preferences(existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    preferences = dict(existing or {})
    opening_strategy = preferences.get("opening_strategy")
    if not isinstance(opening_strategy, dict):
        opening_strategy = {}
    merged_opening_strategy = dict(DEFAULT_OPENING_STRATEGY)
    merged_opening_strategy.update(opening_strategy)
    preferences["opening_strategy"] = merged_opening_strategy
    return preferences


def split_points(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[，,；;、/\n]+", text)
    items: List[str] = []
    for part in parts:
        value = part.strip()
        if value and value not in items:
            items.append(value)
    return items


def infer_genre_mode(genre: str, genre_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    normalized = to_profile_key(str(genre or "").strip())
    if not normalized and isinstance(genre_profile, dict):
        normalized = to_profile_key(str(genre_profile.get("genre") or "").strip())
    normalized = normalized or "general"
    focus = GENRE_MODE_MAP.get(normalized, "强触发/高价值承诺/未闭合问题")
    trigger_tokens = list(GENRE_TRIGGER_TOKENS.get(normalized, ()))
    return {
        "genre_profile_key": normalized,
        "trigger_focus": focus,
        "trigger_tokens": trigger_tokens,
    }


def _compose_reader_promise(
    title: str,
    core_selling_points: List[str],
    genre_mode: Dict[str, Any],
    target_reader: str,
    platform: str,
) -> str:
    promise_parts: List[str] = []
    if core_selling_points:
        promise_parts.append(" / ".join(core_selling_points[:2]))
    focus = str(genre_mode.get("trigger_focus") or "").strip()
    if focus:
        promise_parts.append(focus)
    if target_reader:
        promise_parts.append(f"面向{target_reader}")
    if platform:
        promise_parts.append(f"{platform}可读")
    promise = "；".join(part for part in promise_parts if part).strip("；")
    if promise:
        return promise
    if title:
        return f"{title}在开篇三章内给出明确价值承诺与持续追读理由"
    return "开篇三章内给出明确价值承诺与持续追读理由"


def build_golden_three_plan(
    *,
    title: str = "",
    genre: str = "",
    target_reader: str = "",
    platform: str = "",
    opening_hook: str = "",
    core_selling_points: str = "",
    existing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    existing_plan = dict(existing or {})
    genre_mode = infer_genre_mode(genre)
    selling_points = split_points(core_selling_points)
    opening_trigger = str(opening_hook or "").strip() or (
        f"前300字交付{genre_mode['trigger_focus']}中的至少一项"
    )
    reader_promise = _compose_reader_promise(
        title=title,
        core_selling_points=selling_points,
        genre_mode=genre_mode,
        target_reader=target_reader,
        platform=platform,
    )
    shared_slow_zones = [
        "大段世界观讲解",
        "景物空镜",
        "无目标闲聊",
        "脱离冲突的哲思独白",
    ]

    generated = {
        "enabled": True,
        "profile": DEFAULT_OPENING_STRATEGY["profile"],
        "gate": DEFAULT_OPENING_STRATEGY["gate"],
        "generated_at": datetime.now().isoformat(),
        "genre": genre,
        "genre_profile_key": genre_mode["genre_profile_key"],
        "opening_hook": str(opening_hook or "").strip(),
        "reader_promise": reader_promise,
        "chapters": {
            "1": {
                "chapter": 1,
                "golden_three_role": "立触发、立承诺、立主角差异点",
                "opening_window_chars": 300,
                "opening_trigger": opening_trigger,
                "reader_promise": reader_promise,
                "must_deliver": [
                    "前300字出现强触发",
                    "前800字看清主角压力/独特抓手/核心问题",
                    "本章给出至少1个可见变化",
                ],
                "micro_payoffs": [
                    selling_points[0] if selling_points else "读者看见主角的独特优势",
                    "主角拿到一个明确行动理由",
                ],
                "end_hook_requirement": "留下高价值承诺 + 未闭合问题 + 可见变化",
                "forbidden_slow_zones": shared_slow_zones,
            },
            "2": {
                "chapter": 2,
                "golden_three_role": "接住首章钩子并升级代价/规则",
                "opening_window_chars": 500,
                "opening_trigger": "前500字回应第1章章末钩子，禁止重新起头",
                "reader_promise": reader_promise,
                "must_deliver": [
                    "快速回应上一章钩子",
                    "升级一层代价或规则",
                    "给至少1个微兑现",
                ],
                "micro_payoffs": [
                    selling_points[1] if len(selling_points) > 1 else "让读者确认承诺在兑现",
                    "下一章必须看的驱动力",
                ],
                "end_hook_requirement": "把期待从想继续看升级为必须看第3章",
                "forbidden_slow_zones": shared_slow_zones,
            },
            "3": {
                "chapter": 3,
                "golden_three_role": "完成首个小闭环并把读者送入长线主故事",
                "opening_window_chars": 500,
                "opening_trigger": "尽快承接前两章压力，禁止重新解释前情",
                "reader_promise": reader_promise,
                "must_deliver": [
                    "完成首个小闭环",
                    "主角/关系/资源/身份/规则认知至少一项显性变化",
                    "章末自然接到长线主故事",
                ],
                "micro_payoffs": [
                    "兑现一个首章承诺",
                    "明确后续主线入口",
                ],
                "end_hook_requirement": "章末把读者带入长线主故事，让第4章自然接棒",
                "forbidden_slow_zones": shared_slow_zones,
            },
        },
    }

    if existing_plan:
        merged = dict(existing_plan)
        for key, value in generated.items():
            if key == "chapters":
                existing_chapters = merged.get("chapters")
                if not isinstance(existing_chapters, dict):
                    existing_chapters = {}
                chapter_map = dict(existing_chapters)
                for chapter_key, chapter_plan in value.items():
                    current = chapter_map.get(chapter_key)
                    if isinstance(current, dict):
                        merged_chapter = dict(chapter_plan)
                        merged_chapter.update(current)
                        chapter_map[chapter_key] = merged_chapter
                    else:
                        chapter_map[chapter_key] = chapter_plan
                merged["chapters"] = chapter_map
            elif key not in merged:
                merged[key] = value
            elif key in {"enabled", "profile", "gate", "genre", "genre_profile_key", "opening_hook", "reader_promise"}:
                merged[key] = value
        return merged
    return generated


def resolve_golden_three_contract(
    *,
    chapter: int,
    preferences: Dict[str, Any] | None = None,
    golden_three_plan: Dict[str, Any] | None = None,
    genre_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not is_golden_three_chapter(chapter):
        return {}

    prefs = build_default_preferences(preferences)
    opening_strategy = prefs.get("opening_strategy") or {}
    if not bool(opening_strategy.get("golden_three_enabled", True)):
        return {}

    plan = dict(golden_three_plan or {})
    chapters = plan.get("chapters")
    if not isinstance(chapters, dict):
        chapters = {}

    chapter_plan = chapters.get(str(int(chapter)))
    if not isinstance(chapter_plan, dict):
        chapter_plan = build_golden_three_plan(
            title="",
            genre=str((genre_profile or {}).get("genre") or plan.get("genre") or ""),
        )["chapters"][str(int(chapter))]

    genre_mode = infer_genre_mode(
        str(plan.get("genre") or (genre_profile or {}).get("genre") or ""),
        genre_profile=genre_profile,
    )

    return {
        "enabled": True,
        "chapter": int(chapter),
        "profile": str(opening_strategy.get("profile") or DEFAULT_OPENING_STRATEGY["profile"]),
        "gate": str(opening_strategy.get("gate") or DEFAULT_OPENING_STRATEGY["gate"]),
        "genre_profile_key": genre_mode["genre_profile_key"],
        "golden_three_role": str(chapter_plan.get("golden_three_role") or ""),
        "opening_window_chars": int(chapter_plan.get("opening_window_chars") or 300),
        "opening_trigger": str(chapter_plan.get("opening_trigger") or ""),
        "reader_promise": str(chapter_plan.get("reader_promise") or plan.get("reader_promise") or ""),
        "must_deliver_this_chapter": list(chapter_plan.get("must_deliver", []) or []),
        "micro_payoffs": list(chapter_plan.get("micro_payoffs", []) or []),
        "end_hook_requirement": str(chapter_plan.get("end_hook_requirement") or ""),
        "forbidden_slow_zones": list(chapter_plan.get("forbidden_slow_zones", []) or []),
        "trigger_tokens": list(genre_mode.get("trigger_tokens") or []),
    }


def build_golden_three_guidance(contract: Dict[str, Any]) -> List[str]:
    if not isinstance(contract, dict) or not contract.get("enabled"):
        return []

    chapter = int(contract.get("chapter") or 0)
    guidance = [
        (
            f"黄金三章模式：第{chapter}章职责是“{contract.get('golden_three_role', '')}”，"
            f"前{contract.get('opening_window_chars', 300)}字内必须先交付触发点。"
        ),
        f"读者承诺：{contract.get('reader_promise', '本章必须给出清晰的继续阅读理由。')}",
    ]

    opening_trigger = str(contract.get("opening_trigger") or "").strip()
    if opening_trigger:
        guidance.append(f"开头触发要求：{opening_trigger}")

    must_deliver = list(contract.get("must_deliver_this_chapter") or [])
    if must_deliver:
        guidance.append("本章必须兑现：" + "；".join(str(item) for item in must_deliver[:3]))

    micro_payoffs = list(contract.get("micro_payoffs") or [])
    if micro_payoffs:
        guidance.append("微兑现建议：" + "；".join(str(item) for item in micro_payoffs[:2]))

    end_hook = str(contract.get("end_hook_requirement") or "").strip()
    if end_hook:
        guidance.append(f"章末钩子要求：{end_hook}")

    forbidden = list(contract.get("forbidden_slow_zones") or [])
    if forbidden:
        guidance.append("硬禁区：" + "；".join(str(item) for item in forbidden[:4]))

    return guidance


def build_golden_three_checklist(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(contract, dict) or not contract.get("enabled"):
        return []

    chapter = int(contract.get("chapter") or 0)
    opening_window_chars = int(contract.get("opening_window_chars") or 300)
    items: List[Dict[str, Any]] = [
        {
            "id": f"golden_three_opening_ch{chapter}",
            "label": f"前{opening_window_chars}字内交付强触发",
            "weight": 1.8,
            "required": True,
            "source": "golden_three.opening",
            "verify_hint": str(contract.get("opening_trigger") or "开头窗口内出现明确触发。"),
        },
        {
            "id": f"golden_three_promise_ch{chapter}",
            "label": "本章读者承诺可感知且不可回避",
            "weight": 1.6,
            "required": True,
            "source": "golden_three.promise",
            "verify_hint": str(contract.get("reader_promise") or "正文能复述本章卖点与承诺。"),
        },
        {
            "id": f"golden_three_hook_ch{chapter}",
            "label": "章末保留强驱动力，直接推向下一章",
            "weight": 1.6,
            "required": True,
            "source": "golden_three.hook",
            "verify_hint": str(contract.get("end_hook_requirement") or "章末必须留下未闭合问题。"),
        },
    ]

    for idx, entry in enumerate(contract.get("must_deliver_this_chapter", []) or [], start=1):
        items.append(
            {
                "id": f"golden_three_deliver_{chapter}_{idx}",
                "label": f"兑现项：{entry}",
                "weight": 1.3 if idx == 1 else 1.1,
                "required": idx <= 2,
                "source": "golden_three.deliver",
                "verify_hint": "正文里能定位到明确兑现段落。",
            }
        )
    return items


def _contains_trigger(text: str, trigger_tokens: List[str]) -> bool:
    if not trigger_tokens:
        return bool(re.search(r"(冲突|问题|代价|异常|不能|必须|压制|奖励|秘密|背叛|倒计时)", text))
    return any(token in text for token in trigger_tokens)


def analyze_golden_three_opening(
    *,
    text: str,
    chapter: int,
    genre_profile_key: str = "",
    contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not is_golden_three_chapter(chapter):
        return {"applied": False, "issues": [], "metrics": {}}

    ctx = dict(contract or {})
    window_chars = int(ctx.get("opening_window_chars") or (300 if int(chapter) == 1 else 500))
    opening = re.sub(r"\s+", "", str(text or ""))[:window_chars]
    opening_loose = str(text or "")[: max(window_chars, 220)]
    issues: List[Dict[str, Any]] = []
    penalty = 0.0

    profile_key = genre_profile_key or str(ctx.get("genre_profile_key") or "")
    trigger_tokens = list(ctx.get("trigger_tokens") or GENRE_TRIGGER_TOKENS.get(profile_key, ()))
    has_trigger = _contains_trigger(opening, trigger_tokens)

    if int(chapter) == 1 and not has_trigger:
        issues.append(
            {
                "id": "golden_three_missing_trigger",
                "severity": "high",
                "message": f"第1章前{window_chars}字内未出现强触发，黄金三章开局失手。",
                "count": 1,
            }
        )
        penalty += 0.32

    if any(re.search(pattern, opening_loose) for pattern in SCENIC_OPENING_PATTERNS):
        issues.append(
            {
                "id": "golden_three_scenic_opening",
                "severity": "high",
                "message": "黄金三章开头出现空景描写，触发点被景物空镜占位。",
                "count": 1,
            }
        )
        penalty += 0.24

    abstract_hits = [token for token in ABSTRACT_OPENING_PATTERNS if token in opening_loose]
    if abstract_hits:
        issues.append(
            {
                "id": "golden_three_abstract_opening",
                "severity": "high",
                "message": "黄金三章开头落入抽象感悟/总结腔，读者无法迅速抓住戏剧触发。",
                "count": len(abstract_hits),
                "examples": abstract_hits[:4],
            }
        )
        penalty += min(0.22, 0.08 * len(abstract_hits))

    world_hits = [token for token in WORLD_BUILDING_PATTERNS if token in opening_loose]
    if len(world_hits) >= 2:
        issues.append(
            {
                "id": "golden_three_world_building_dump",
                "severity": "high",
                "message": "黄金三章前置世界观说明过重，像设定书开场。",
                "count": len(world_hits),
                "examples": world_hits[:4],
            }
        )
        penalty += min(0.2, 0.06 * len(world_hits))

    backstory_hits = [token for token in BACKSTORY_PATTERNS if token in opening_loose]
    if backstory_hits:
        issues.append(
            {
                "id": "golden_three_backstory_dump",
                "severity": "medium",
                "message": "黄金三章开头长回忆/前情过多，拖慢触发兑现。",
                "count": len(backstory_hits),
                "examples": backstory_hits[:4],
            }
        )
        penalty += min(0.14, 0.05 * len(backstory_hits))

    score = round(max(0.0, 1.0 - penalty), 4)
    passed = not any(issue.get("severity") == "high" for issue in issues) and score >= 0.75
    return {
        "applied": True,
        "passed": passed,
        "issues": issues,
        "metrics": {
            "chapter": int(chapter),
            "opening_window_chars": window_chars,
            "genre_profile_key": profile_key,
            "trigger_detected": has_trigger,
            "opening_length": len(opening),
            "issue_count": len(issues),
            "score": score,
        },
    }
