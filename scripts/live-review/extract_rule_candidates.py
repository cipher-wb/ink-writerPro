#!/usr/bin/env python3
"""US-LR-009: 规则候选抽取器 — 从 live_review jsonl 中用 LLM 抽通用规则，
再用 BAAI/bge-small-zh-v1.5 与现有 editor-wisdom rules.json 做 cosine 去重。

输出 ``rule_candidates.json``（候选 ID 用 ``RC-NNNN``，不进 rules.json；
``approved`` 字段初始 ``null`` 等待 US-LR-010 人工审核）。

CLI:
    python3 scripts/live-review/extract_rule_candidates.py \\
        --jsonl-dir data/live-review/extracted \\
        --rules-json data/editor-wisdom/rules.json \\
        --out data/live-review/rule_candidates.json \\
        --threshold 0.85

测试 / 离线模式:
    --mock-llm <fixture.json> 直接用本地候选 JSON（绕过 anthropic SDK）。

退出码:
    0  全流程成功
    1  LLM 输出非 JSON / 候选必填字段缺失 / cosine 失败 / 写盘失败
    2  目录或文件参数错误
"""
from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BGE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_REQUIRED_LLM_FIELDS = ("category", "rule", "why", "severity", "applies_to")
_VALID_CATEGORIES = {
    "opening",
    "hook",
    "golden_finger",
    "character",
    "pacing",
    "highpoint",
    "taboo",
    "genre",
    "ops",
    "misc",
}
_VALID_SEVERITIES = {"hard", "soft", "info"}
_VALID_APPLIES_TO = {"all_chapters", "golden_three", "opening_only"}


class CandidateExtractionError(RuntimeError):
    """fail-loud：LLM 输出非 JSON / schema 违反 / cosine 失败 / IO 失败。"""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract candidate rules from live-review jsonl with LLM + bge cosine dedupe.",
    )
    p.add_argument("--jsonl-dir", dest="jsonl_dir", required=True,
                   help="目录：扫描 *.jsonl（跳过 _ 开头）作为 LLM 输入材料")
    p.add_argument("--rules-json", dest="rules_json",
                   default=str(_REPO_ROOT / "data" / "editor-wisdom" / "rules.json"),
                   help="现有 editor-wisdom 规则集 (用于 cosine 去重)")
    p.add_argument("--out", dest="out",
                   default=str(_REPO_ROOT / "data" / "live-review" / "rule_candidates.json"),
                   help="候选输出 JSON 数组路径")
    p.add_argument("--mock-llm", dest="mock_llm",
                   help="测试 / 离线模式：候选 JSON 数组 fixture 路径，绕过 LLM 调用")
    p.add_argument("--threshold", type=float, default=0.85,
                   help="cosine 去重阈值 (默认 0.85)")
    p.add_argument("--model", default="claude-sonnet-4-6",
                   help="LLM 模型 (mock 模式忽略)")
    p.add_argument("--batch-size", dest="batch_size", type=int, default=0,
                   help="LLM 分批大小：每批 N 个 jsonl 文件单独调用一次（默认 0=全量单批）；"
                        "用于上下文受限的 LLM (deepseek 128K / GLM 128K)，跨批合并去重。")
    return p


def _iter_jsonl_files(jsonl_dir: Path) -> list[Path]:
    return sorted(p for p in jsonl_dir.glob("*.jsonl") if not p.name.startswith("_"))


def _collect_bvids(jsonl_dir: Path) -> list[str]:
    bvids: set[str] = set()
    for path in _iter_jsonl_files(jsonl_dir):
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CandidateExtractionError(
                    f"jsonl parse failed: {path.name}: {exc}"
                ) from exc
            bvid = rec.get("bvid")
            if isinstance(bvid, str) and bvid:
                bvids.add(bvid)
    return sorted(bvids)


def _load_existing_rules(path: Path) -> list[dict]:
    if not path.is_file():
        raise CandidateExtractionError(f"rules.json not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CandidateExtractionError(f"rules.json parse failed: {exc}") from exc
    if not isinstance(data, list):
        raise CandidateExtractionError("rules.json root must be a JSON array")
    return data


def _strip_markdown_fence(raw: str) -> str:
    """deepseek / glm 偶尔吐 ```json ... ``` 代码块；剥外层围栏只留 JSON 主体。"""
    text = raw.strip()
    if text.startswith("```"):
        # ```json\n...\n```  或  ```\n...\n```
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _parse_llm_output(raw: str) -> list[dict]:
    text = _strip_markdown_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CandidateExtractionError(
            f"LLM output is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, list):
        raise CandidateExtractionError(
            f"LLM output must be a JSON array, got {type(data).__name__}"
        )
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise CandidateExtractionError(
                f"LLM output item #{i} is not an object: {type(item).__name__}"
            )
    return data


def _normalize_candidate(cand: dict) -> dict:
    """字段类型软容错：LLM 偶尔吐 applies_to=str 而非 list[str]，统一拉成 list。"""
    if isinstance(cand.get("applies_to"), str):
        cand["applies_to"] = [cand["applies_to"]]
    return cand


def _validate_candidate_fields(cand: dict, idx: int) -> None:
    missing = [f for f in _REQUIRED_LLM_FIELDS if f not in cand]
    if missing:
        raise CandidateExtractionError(
            f"candidate #{idx} missing required fields: {missing}"
        )
    if cand["category"] not in _VALID_CATEGORIES:
        raise CandidateExtractionError(
            f"candidate #{idx} category invalid: {cand['category']!r}"
        )
    if cand["severity"] not in _VALID_SEVERITIES:
        raise CandidateExtractionError(
            f"candidate #{idx} severity invalid: {cand['severity']!r}"
        )
    if not isinstance(cand["applies_to"], list) or not cand["applies_to"]:
        raise CandidateExtractionError(
            f"candidate #{idx} applies_to must be non-empty list"
        )
    for v in cand["applies_to"]:
        if v not in _VALID_APPLIES_TO:
            raise CandidateExtractionError(
                f"candidate #{idx} applies_to has invalid value: {v!r}"
            )
    if not isinstance(cand["rule"], str) or len(cand["rule"]) > 120:
        raise CandidateExtractionError(
            f"candidate #{idx} rule must be string ≤120 chars"
        )
    if not isinstance(cand["why"], str) or not cand["why"]:
        raise CandidateExtractionError(
            f"candidate #{idx} why must be non-empty string"
        )


def _compute_dup_with(
    candidates: list[dict],
    existing_rules: list[dict],
    threshold: float,
) -> list[list[str] | None]:
    """对每条候选返回 dup_with (list[EW-id] 或 None)；threshold 用 > 比较。"""
    if not candidates or not existing_rules:
        return [None for _ in candidates]
    try:
        import numpy as np  # noqa: PLC0415
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except ImportError as exc:
        raise CandidateExtractionError(
            f"cosine dedupe requires sentence-transformers + numpy: {exc}"
        ) from exc

    try:
        model = SentenceTransformer(_BGE_MODEL_NAME)
        existing_emb = model.encode(
            [r["rule"] for r in existing_rules],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        candidate_emb = model.encode(
            [c["rule"] for c in candidates],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        existing_emb = np.asarray(existing_emb, dtype=np.float32)
        candidate_emb = np.asarray(candidate_emb, dtype=np.float32)
        sim = candidate_emb @ existing_emb.T  # (n_cand, n_existing)
    except Exception as exc:  # noqa: BLE001
        raise CandidateExtractionError(
            f"bge cosine computation failed: {exc}"
        ) from exc

    out: list[list[str] | None] = []
    for i in range(sim.shape[0]):
        hits = [
            existing_rules[j]["id"]
            for j in range(sim.shape[1])
            if float(sim[i, j]) > threshold
        ]
        out.append(hits or None)
    return out


def _call_llm(model_name: str, jsonl_records_blob: str) -> str:
    """实跑 LLM。env-driven 自动选 GLM / anthropic。mock 路径不会进这里。"""
    from ink_writer.live_review._llm_provider import make_client  # noqa: PLC0415

    try:
        client, effective_model = make_client(default_model=model_name)
    except RuntimeError as exc:
        raise CandidateExtractionError(str(exc)) from exc
    prompt = (
        "你是网文写作规则提炼专家。下方是若干本小说被星河直播逐一点评的 jsonl 记录"
        "（含分数 / 评语 / 多维度问题）。请从中提炼**通用规则**（剥离作品语境，"
        "不要写'本作', 不要绑定具体角色名），输出严格 JSON 数组（不要 markdown）；"
        "每条规则含字段 rule (≤120 字符的祈使句) / why / category / severity"
        " (hard|soft|info) / applies_to (子集 [all_chapters, golden_three, opening_only])。"
        "category 只能取: opening / hook / golden_finger / character / pacing / "
        "highpoint / taboo / genre / ops / misc。"
        "\n\njsonl records:\n"
        f"{jsonl_records_blob}"
    )
    msg = client.messages.create(
        model=effective_model,
        max_tokens=8192,  # deepseek thinking 模式 reasoning + content 共享 max_tokens 配额
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _read_jsonl_blob(jsonl_dir: Path, files: list[Path] | None = None) -> str:
    """拼 jsonl 为 LLM blob。``files=None`` 走全量单批；否则只拼传入的文件。"""
    parts: list[str] = []
    iter_files = files if files is not None else _iter_jsonl_files(jsonl_dir)
    for path in iter_files:
        parts.append(f"# {path.name}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _build_candidate(
    raw: dict,
    *,
    rc_index: int,
    source_bvids: list[str],
    dup_with: list[str] | None,
) -> dict:
    return {
        "id": f"RC-{rc_index:04d}",
        "category": raw["category"],
        "rule": raw["rule"],
        "why": raw["why"],
        "severity": raw["severity"],
        "applies_to": list(raw["applies_to"]),
        "source_files": [f"live_review_bvid:{b}" for b in source_bvids],
        "dup_with": dup_with,
        "approved": None,
        "source_bvids": list(source_bvids),
    }


def run(
    *,
    jsonl_dir: Path,
    rules_json: Path,
    out_path: Path,
    mock_llm: Path | None,
    threshold: float,
    model_name: str,
    batch_size: int = 0,
) -> list[dict]:
    if not jsonl_dir.is_dir():
        raise CandidateExtractionError(f"jsonl-dir not a directory: {jsonl_dir}")
    bvids = _collect_bvids(jsonl_dir)
    if not bvids:
        raise CandidateExtractionError(
            f"no bvids collected from {jsonl_dir} (empty jsonl?)"
        )
    existing_rules = _load_existing_rules(rules_json)

    parsed: list[dict] = []
    if mock_llm is not None:
        if not mock_llm.is_file():
            raise CandidateExtractionError(f"mock-llm fixture not found: {mock_llm}")
        llm_raw = mock_llm.read_text(encoding="utf-8")
        parsed.extend(_parse_llm_output(llm_raw))
    else:
        files = _iter_jsonl_files(jsonl_dir)
        if batch_size <= 0 or batch_size >= len(files):
            blob = _read_jsonl_blob(jsonl_dir)
            llm_raw = _call_llm(model_name, blob)
            parsed.extend(_parse_llm_output(llm_raw))
        else:
            n_batches = (len(files) + batch_size - 1) // batch_size
            for b in range(n_batches):
                batch_files = files[b * batch_size : (b + 1) * batch_size]
                blob = _read_jsonl_blob(jsonl_dir, batch_files)
                print(
                    f"[batch {b + 1}/{n_batches}] {len(batch_files)} files "
                    f"→ LLM (~{len(blob)} chars)",
                    file=sys.stderr,
                )
                try:
                    llm_raw = _call_llm(model_name, blob)
                    batch_parsed = _parse_llm_output(llm_raw)
                except CandidateExtractionError as exc:
                    print(
                        f"[batch {b + 1}/{n_batches}] WARN: skipping batch ({exc})",
                        file=sys.stderr,
                    )
                    continue
                print(
                    f"[batch {b + 1}/{n_batches}] OK +{len(batch_parsed)} candidates",
                    file=sys.stderr,
                )
                parsed.extend(batch_parsed)
            if not parsed:
                raise CandidateExtractionError(
                    f"all {n_batches} batches failed; no candidates extracted"
                )

    parsed = [_normalize_candidate(c) for c in parsed]
    valid: list[dict] = []
    for i, c in enumerate(parsed):
        try:
            _validate_candidate_fields(c, i)
        except CandidateExtractionError as exc:
            print(
                f"[validate] WARN: candidate #{i} skipped: {exc}",
                file=sys.stderr,
            )
            continue
        valid.append(c)
    if not valid:
        raise CandidateExtractionError(
            f"all {len(parsed)} parsed candidates failed validation"
        )
    parsed = valid

    dup_with_list = _compute_dup_with(parsed, existing_rules, threshold)

    candidates = [
        _build_candidate(
            raw,
            rc_index=i + 1,
            source_bvids=bvids,
            dup_with=dup_with_list[i],
        )
        for i, raw in enumerate(parsed)
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return candidates


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        candidates = run(
            jsonl_dir=Path(args.jsonl_dir),
            rules_json=Path(args.rules_json),
            out_path=Path(args.out),
            mock_llm=Path(args.mock_llm) if args.mock_llm else None,
            threshold=float(args.threshold),
            model_name=args.model,
            batch_size=int(args.batch_size),
        )
    except CandidateExtractionError as exc:
        print(f"[extract_rule_candidates] FAIL: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"[extract_rule_candidates] not found: {exc}", file=sys.stderr)
        return 2

    dup_count = sum(1 for c in candidates if c["dup_with"])
    print(
        f"[extract_rule_candidates] OK {len(candidates)} candidates "
        f"({dup_count} dup) → {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
