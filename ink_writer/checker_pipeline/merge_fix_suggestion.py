"""US-016 / F-011: merge fix suggestions across prose-craft checkers.

polish-agent 在 US-015 前直接消费 3-5 份文笔 checker 的 report（prose-impact /
sensory-immersion / flow-naturalness / ooc / proofreading / editor-wisdom），
同一"镜头单调 / 感官沙漠 / 句式平坦 / voice 漂移 / 对话失辨"问题会被多次触发，
token 膨胀且修复指令互相打架。

本模块按 ``ink-writer/references/checker-merge-matrix.md`` 规定的矩阵，把 N 份
checker report 合并成 ``merged_fix_suggestion.json``：

    {
      "shot":     {"master_checker": "prose-impact-checker", "violations": [...], "fix_prompt": "..."},
      "sensory":  {"master_checker": "sensory-immersion-checker", ...},
      "rhythm":   {"master_checker": "flow-naturalness-checker",  ...},
      "voice":    {"master_checker": "ooc-checker",               ...},
      "dialogue": {"master_checker": "flow-naturalness-checker",  ...}
    }

合并规则：
  1. 每份 report 的 violations/issues 按 matrix 归入对应维度。
  2. 同维度内 type 相同的 violation 仅保留 severity 最高的一条，并把所有来源
     checker 合并到 ``source_checkers``。
  3. 主 checker 的 fix_prompt（若存在）作为该维度 fix_prompt 的主干；其他从
     checker 的 fix_suggestion 拼接为补充。
  4. 主 checker 缺失时，降级用从 checker 的 suggestion 合成 fix_prompt。

API:
  merge_fix_suggestions(reports) -> dict[str, dict]
  write_merged_fix_suggestion(reports, out_path) -> Path
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 5 个受控维度（key 与 matrix 对齐）
DIMENSIONS: tuple[str, ...] = ("shot", "sensory", "rhythm", "voice", "dialogue")

# 主 checker
MASTER_CHECKER: dict[str, str] = {
    "shot": "prose-impact-checker",
    "sensory": "sensory-immersion-checker",
    "rhythm": "flow-naturalness-checker",
    "voice": "ooc-checker",
    "dialogue": "flow-naturalness-checker",
}

# 从 checker（仅用于文档化；实际归类走 _dimensions_for_violation 基于 type 前缀）
SLAVE_CHECKERS: dict[str, list[str]] = {
    "shot": ["proofreading-checker", "editor-wisdom-checker"],
    "sensory": ["prose-impact-checker", "editor-wisdom-checker"],
    "rhythm": ["prose-impact-checker", "proofreading-checker"],
    "voice": ["voice-fingerprint", "anti-detection-checker"],
    "dialogue": ["ooc-checker", "prose-impact-checker"],
}

# Severity 优先级（数值越大越严重）
SEVERITY_RANK: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "warning": 2,  # 等价 medium
    "low": 1,
    "info": 0,
}

# type 关键词 → 维度映射（前缀/包含匹配，所有 type 预设大写）
TYPE_KEYWORDS: dict[str, str] = {
    "SHOT_": "shot",
    "CLOSEUP_": "shot",
    "COMBAT_THREE_STAGE": "shot",
    "SCENE_NO_SWITCH": "shot",
    "SENSORY_": "sensory",
    "VISUAL_OVERLOAD": "sensory",
    "NON_VISUAL_SPARSE": "sensory",
    "ROTATION_": "sensory",
    "PLAN_ROTATION": "sensory",
    "SENTENCE_": "rhythm",
    "CV_": "rhythm",
    "SHORT_STREAK": "rhythm",
    "TENSE_CONJUNCTION": "rhythm",
    "SCENE_CV_MISMATCH": "rhythm",
    "VOICE_": "voice",
    "OOC_": "voice",
    "FINGERPRINT_": "voice",
    "DIALOGUE_": "dialogue",
    "DIALOG_": "dialogue",
}

# checker → 默认维度（当 violation 没有 type 或 type 不在 TYPE_KEYWORDS 里时用）
CHECKER_DEFAULT_DIMENSION: dict[str, str] = {
    "prose-impact-checker": "shot",
    "sensory-immersion-checker": "sensory",
    "flow-naturalness-checker": "rhythm",
    "ooc-checker": "voice",
    "voice-fingerprint": "voice",
    "anti-detection-checker": "voice",
    # proofreading / editor-wisdom 同时覆盖多维，没有 type 时不归任何维度（避免误归）
}


def _classify_dimension(violation: dict, checker: str) -> str | None:
    """给定一条 violation 与来源 checker，返回它所属维度（或 None 跳过）。"""
    vtype = str(violation.get("type", "")).upper()
    if vtype:
        for prefix, dim in TYPE_KEYWORDS.items():
            if vtype.startswith(prefix) or prefix.rstrip("_") in vtype:
                return dim
    # type 未命中 → 用 checker 默认维度兜底
    return CHECKER_DEFAULT_DIMENSION.get(checker)


def _sev_rank(severity: str | None) -> int:
    return SEVERITY_RANK.get((severity or "").lower(), 0)


def _collect_violations(report: dict) -> list[dict]:
    """兼容 ``violations`` / ``issues`` 两种字段名。"""
    raw = report.get("violations")
    if raw is None:
        raw = report.get("issues", [])
    return [dict(v) for v in raw or [] if isinstance(v, dict)]


def merge_fix_suggestions(reports: list[dict]) -> dict[str, dict[str, Any]]:
    """把 N 份 checker report 合并为维度化 merged_fix_suggestion。

    Args:
      reports: list of checker reports. 每份至少含 ``agent`` 字段；推荐含
        ``violations`` 或 ``issues`` (list of dict with type/severity/suggestion)、
        ``fix_prompt`` (str, 可选)、``fix_suggestion`` (str, 可选)。

    Returns:
      dict，key 为 ``DIMENSIONS`` 中的 5 个维度；每个 value 形如
      ``{"master_checker": str, "violations": [...], "fix_prompt": str}``。
      当某维度无命中时，仍保留 key 但 violations/fix_prompt 为空。
    """
    # buckets[dim] = {
    #   "violations": {dedup_key: merged_violation},
    #   "master_prompt": str | None,
    #   "slave_prompts": list[tuple[checker_name, prompt]],
    # }
    buckets: dict[str, dict[str, Any]] = {
        dim: {"violations": {}, "master_prompt": None, "slave_prompts": []}
        for dim in DIMENSIONS
    }

    for report in reports or []:
        if not isinstance(report, dict):
            continue
        checker = str(report.get("agent") or report.get("checker") or "").strip()
        if not checker:
            continue

        # 1. 归入 violations
        for v in _collect_violations(report):
            dim = _classify_dimension(v, checker)
            if dim is None or dim not in buckets:
                continue
            vtype = str(v.get("type", "")).upper() or "UNTYPED"
            dedup_key = vtype
            existing = buckets[dim]["violations"].get(dedup_key)
            new_sev = (v.get("severity") or "").lower()
            new_entry = {
                "type": vtype,
                "severity": new_sev or "medium",
                "source_checkers": [checker],
                "suggestion": v.get("suggestion") or v.get("description") or "",
                "location": v.get("location") or "",
            }
            if existing is None:
                buckets[dim]["violations"][dedup_key] = new_entry
            else:
                # 合并：severity 取 max；source_checkers 去重追加；suggestion 择优（长的）
                if _sev_rank(new_sev) > _sev_rank(existing["severity"]):
                    existing["severity"] = new_sev or existing["severity"]
                if checker not in existing["source_checkers"]:
                    existing["source_checkers"].append(checker)
                if len(new_entry["suggestion"]) > len(existing["suggestion"]):
                    existing["suggestion"] = new_entry["suggestion"]
                if not existing["location"] and new_entry["location"]:
                    existing["location"] = new_entry["location"]

        # 2. 归入 prompt
        fix_prompt = str(report.get("fix_prompt") or report.get("fix_suggestion") or "").strip()
        if not fix_prompt:
            continue
        # 优先判定：checker 是哪个维度的主？
        matched_master = False
        for dim in DIMENSIONS:
            if MASTER_CHECKER[dim] == checker:
                # 只有当该 checker 确实在本 report 里为该维度贡献了 violation（或
                # 该 checker 默认归属该维度）才接主 prompt，避免 flow-naturalness
                # 一份 prompt 重复写入 rhythm+dialogue。
                if buckets[dim]["violations"] or CHECKER_DEFAULT_DIMENSION.get(checker) == dim:
                    if buckets[dim]["master_prompt"] is None:
                        buckets[dim]["master_prompt"] = fix_prompt
                        matched_master = True
        if matched_master:
            continue
        # 从 checker：把 prompt 追加到它贡献了 violation 的所有维度
        touched_dims = {
            dim for dim in DIMENSIONS
            if any(checker in v["source_checkers"] for v in buckets[dim]["violations"].values())
        }
        for dim in touched_dims:
            buckets[dim]["slave_prompts"].append((checker, fix_prompt))

    # 3. 组装输出
    result: dict[str, dict[str, Any]] = {}
    for dim in DIMENSIONS:
        bucket = buckets[dim]
        violations = list(bucket["violations"].values())
        # violations 排序：severity 降序 → type 字母序
        violations.sort(key=lambda x: (-_sev_rank(x["severity"]), x["type"]))

        master_prompt = bucket["master_prompt"]
        slave_prompts = bucket["slave_prompts"]
        fix_prompt = _compose_fix_prompt(dim, master_prompt, slave_prompts, violations)

        result[dim] = {
            "master_checker": MASTER_CHECKER[dim],
            "violations": violations,
            "fix_prompt": fix_prompt,
        }
    return result


def _compose_fix_prompt(
    dim: str,
    master_prompt: str | None,
    slave_prompts: list[tuple[str, str]],
    violations: list[dict],
) -> str:
    """拼 fix_prompt：主为主干，从 prompt / violations 补充。"""
    if not master_prompt and not slave_prompts and not violations:
        return ""
    parts: list[str] = []
    dim_label = {
        "shot": "镜头",
        "sensory": "感官",
        "rhythm": "句式节奏",
        "voice": "voice",
        "dialogue": "对话",
    }[dim]
    if master_prompt:
        parts.append(f"【{dim_label}｜主】{master_prompt}")
    elif violations:
        # 无主 prompt → 用 violations 的 suggestion 合成
        bullets = [f"- [{v['severity']}] {v['type']}: {v['suggestion']}" for v in violations if v["suggestion"]]
        if bullets:
            parts.append(f"【{dim_label}｜合成】\n" + "\n".join(bullets))
    for checker, prompt in slave_prompts:
        parts.append(f"【{dim_label}｜从·{checker}】{prompt}")
    return "\n\n".join(parts).strip()


def write_merged_fix_suggestion(
    reports: list[dict],
    out_path: Path | str,
) -> Path:
    """合并并写入 JSON 文件。返回写入路径。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged = merge_fix_suggestions(reports)
    out_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


__all__ = [
    "DIMENSIONS",
    "MASTER_CHECKER",
    "SLAVE_CHECKERS",
    "merge_fix_suggestions",
    "write_merged_fix_suggestion",
]
