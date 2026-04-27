"""v14 US-005~011 (FIX-04): Step 3 Gate Orchestrator production entrypoint.

把 v13 孤儿 CheckerRunner + 5 个孤儿 gate 接进生产链路。

Design: tasks/design-fix-04-step3-gate-orchestrator.md

Mode（env INK_STEP3_RUNNER_MODE）:
  - off：不跑 runner（退回原 LLM 自律流程；紧急降级路径）
  - shadow：跑 runner 并写 review_metrics，但 exit 0 不阻断（观察用）
  - enforce（默认 / v16 US-005）：跑 runner，hard fail → exit 1 真阻断

CLI:
  python3 -m ink_writer.checker_pipeline.step3_runner \\
      --chapter-id N --state-dir .ink/ [--timeout 300] [--parallel 2] [--dry-run]

Exit codes:
  0 = 全 hard pass（或 shadow 模式总是 0）
  1 = 有 hard fail（enforce 模式才会触发）
  2 = 内部错误（load state 失败 / gate 本身抛异常）
"""
from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import (
        enable_windows_utf8_stdio as _enable_utf8_stdio,
    )
    from runtime_compat import (
        set_windows_proactor_policy as _set_proactor_policy,
    )
    _enable_utf8_stdio()
except Exception:
    _set_proactor_policy = None

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ink_writer.checker_pipeline.llm_checker_factory import make_llm_checker
from ink_writer.checker_pipeline.polish_llm_fn import make_llm_polish
from ink_writer.checker_pipeline.runner import (
    CheckerRunner,
    GateSpec,
    GateStatus,
    PipelineReport,
)

logger = logging.getLogger(__name__)

# v16 US-003（FIX-01 Phase B）：5 个 gate 的真 LLM checker 接入。
# - env INK_STEP3_LLM_CHECKER=off → 退回 benign stub（用于 CI 零 token 回归）。
# - 默认启用 LLM checker；具体模型在 llm_checker_factory.DEFAULT_CHECKER_MODEL。
_CHECKER_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _should_use_llm_polish() -> bool:
    """v16 US-004：是否启用真 LLM polish。

    判定与 ``_should_use_llm_checker`` 同语义：
      1. ``INK_STEP3_LLM_POLISH=off`` 显式关闭 → 原文透传 stub。
      2. ``INK_STEP3_LLM_POLISH=on`` 显式打开 → 始终走 LLM。
      3. 默认：有 ``ANTHROPIC_API_KEY`` 才走 LLM，否则 stub（CI 安全）。
    """
    env = os.environ.get("INK_STEP3_LLM_POLISH", "").strip().lower()
    if env == "off":
        return False
    if env == "on":
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _gate_polish(gate_name: str, project_root: Path) -> Callable[[str, str, int], str]:
    """统一 polish 工厂入口：US-004 默认走 LLM，env 关则原文透传。"""
    if not _should_use_llm_polish():

        def _stub(text: str, fix: str, ch_no: int) -> str:
            return text

        return _stub
    return make_llm_polish(gate_name, project_root=project_root)


def _should_use_llm_checker() -> bool:
    """是否启用真 LLM checker。

    判定优先级（从高到低）：
      1. ``INK_STEP3_LLM_CHECKER=off`` 显式关闭 → 始终走 stub。
      2. ``INK_STEP3_LLM_CHECKER=on`` 显式打开 → 始终走 LLM。
      3. 默认：有 ``ANTHROPIC_API_KEY`` 才走 LLM，否则 stub。

    该规则使无 API key 的 CI / pytest 默认安全（不会尝试 spawn ``claude`` CLI），
    同时生产用户配置 ``ANTHROPIC_API_KEY`` 后即获得真 LLM 检查。
    """
    env = os.environ.get("INK_STEP3_LLM_CHECKER", "").strip().lower()
    if env == "off":
        return False
    if env == "on":
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _gate_checker(gate_name: str, prompt_filename: str) -> Callable:
    """统一工厂入口：Phase B 默认走 LLM，env 关则退回 benign stub。

    v16 US-003：stub 返回 score=100（0-100 量纲满分）以便 gate 内部的
    ``passed = score >= threshold`` 判定为 pass，避免 stub 误阻断。
    """
    if not _should_use_llm_checker():

        def _stub(text: str, ch_no: int) -> dict:
            return {"score": 100.0, "violations": [], "passed": True}

        return _stub
    return make_llm_checker(gate_name, _CHECKER_PROMPTS_DIR / prompt_filename)

# Env knobs
MODE_ENV = "INK_STEP3_RUNNER_MODE"  # off / shadow / enforce
MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"
# v16 US-005：切换为 enforce 默认。hard gate fail → exit 1 真阻断 Step 4。
# 仍可通过 env INK_STEP3_RUNNER_MODE=shadow/off 显式降级。
DEFAULT_MODE = MODE_ENFORCE
VALID_MODES = {MODE_OFF, MODE_SHADOW, MODE_ENFORCE}


@dataclass
class GateFailure:
    gate_id: str
    severity: str  # 'hard' | 'soft'
    reason: str
    fix_suggestion: str | None = None
    raw_output: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "severity": self.severity,
            "reason": self.reason,
            "fix_suggestion": self.fix_suggestion,
            "raw_output": self.raw_output,
        }


@dataclass
class Step3Result:
    chapter_id: int
    mode: str
    passed: bool
    hard_fails: list[GateFailure] = field(default_factory=list)
    soft_fails: list[GateFailure] = field(default_factory=list)
    gate_results: dict = field(default_factory=dict)
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "chapter_id": self.chapter_id,
            "mode": self.mode,
            "passed": self.passed,
            "hard_fails": [f.to_dict() for f in self.hard_fails],
            "soft_fails": [f.to_dict() for f in self.soft_fails],
            "gate_results": self.gate_results,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


# ==================== Gate adapters ====================
# 把 5 个 gate 的不同签名适配为 CheckerRunner 期望的 (bool, float, str) 签名。
# 设计意图：adapter 从 review_bundle 提取 gate 需要的字段，调用 gate，转换输出。


def _make_hook_adapter(review_bundle: dict) -> Callable:
    """reader_pull.hook_retry_gate adapter（US-003：真 LLM checker / US-004：真 polish）。"""
    async def _adapter():
        from ink_writer.reader_pull.hook_retry_gate import run_hook_gate

        checker_fn = _gate_checker("reader_pull", "reader_pull.md")
        polish_fn = _gate_polish("reader_pull", Path(review_bundle.get("project_root", ".")))

        try:
            result = await asyncio.to_thread(
                run_hook_gate,
                chapter_text=review_bundle.get("chapter_text", ""),
                chapter_no=review_bundle.get("chapter_no", 0),
                project_root=review_bundle.get("project_root", "."),
                checker_fn=checker_fn,
                polish_fn=polish_fn,
            )
            passed = getattr(result, "passed", True)
            score = getattr(result, "final_score", 1.0)
            return (bool(passed), float(score), "")
        except Exception as exc:
            logger.warning("hook_gate adapter error (shadow safe-default): %s", exc)
            return (True, 1.0, "")  # shadow-safe: 不因 adapter bug 阻断

    return _adapter


def _make_emotion_adapter(review_bundle: dict) -> Callable:
    async def _adapter():
        from ink_writer.emotion.emotion_gate import run_emotion_gate

        checker_fn = _gate_checker("emotion", "emotion.md")
        polish_fn = _gate_polish("emotion", Path(review_bundle.get("project_root", ".")))

        try:
            result = await asyncio.to_thread(
                run_emotion_gate,
                chapter_text=review_bundle.get("chapter_text", ""),
                chapter_no=review_bundle.get("chapter_no", 0),
                project_root=review_bundle.get("project_root", "."),
                checker_fn=checker_fn,
                polish_fn=polish_fn,
            )
            passed = getattr(result, "passed", True)
            score = getattr(result, "final_score", 1.0)
            return (bool(passed), float(score), "")
        except Exception as exc:
            logger.warning("emotion_gate adapter error (shadow safe): %s", exc)
            return (True, 1.0, "")

    return _adapter


def _make_anti_detection_adapter(review_bundle: dict) -> Callable:
    async def _adapter():
        from ink_writer.anti_detection.anti_detection_gate import run_anti_detection_gate

        checker_fn = _gate_checker("anti_detection", "anti_detection.md")
        polish_fn = _gate_polish("anti_detection", Path(review_bundle.get("project_root", ".")))

        try:
            result = await asyncio.to_thread(
                run_anti_detection_gate,
                chapter_text=review_bundle.get("chapter_text", ""),
                chapter_no=review_bundle.get("chapter_no", 0),
                project_root=review_bundle.get("project_root", "."),
                checker_fn=checker_fn,
                polish_fn=polish_fn,
            )
            passed = getattr(result, "passed", True)
            score = getattr(result, "final_score", 1.0)
            return (bool(passed), float(score), "")
        except Exception as exc:
            logger.warning("anti_detection_gate adapter error (shadow safe): %s", exc)
            return (True, 1.0, "")

    return _adapter


def _make_voice_adapter(review_bundle: dict) -> Callable:
    async def _adapter():
        from ink_writer.voice_fingerprint.ooc_gate import run_voice_gate

        checker_fn = _gate_checker("voice", "voice.md")
        polish_fn = _gate_polish("voice", Path(review_bundle.get("project_root", ".")))

        try:
            result = await asyncio.to_thread(
                run_voice_gate,
                chapter_text=review_bundle.get("chapter_text", ""),
                chapter_no=review_bundle.get("chapter_no", 0),
                project_root=review_bundle.get("project_root", "."),
                checker_fn=checker_fn,
                polish_fn=polish_fn,
            )
            passed = getattr(result, "passed", True)
            score = getattr(result, "final_score", 1.0)
            return (bool(passed), float(score), "")
        except Exception as exc:
            logger.warning("voice_gate adapter error (shadow safe): %s", exc)
            return (True, 1.0, "")

    return _adapter


def _make_plotline_adapter(review_bundle: dict) -> Callable:
    async def _adapter():
        from ink_writer.plotline.tracker import scan_plotlines

        try:
            result = await asyncio.to_thread(
                scan_plotlines,
                db_path=review_bundle.get("db_path", ""),
                current_chapter=review_bundle.get("chapter_no", 0),
            )
            passed = getattr(result, "pass_", True) if hasattr(result, "pass_") else getattr(result, "passed", True)
            score = getattr(result, "overall_score", 1.0) / 100.0 if hasattr(result, "overall_score") else 1.0
            return (bool(passed), float(score), "")
        except Exception as exc:
            logger.warning("plotline scan_plotlines adapter error (shadow safe): %s", exc)
            return (True, 1.0, "")

    return _adapter


def _make_colloquial_adapter(review_bundle: dict) -> Callable:
    """US-005: colloquial-checker 程序化适配器（全场景激活，无 scene_mode 限制）。

    激活条件：
      - config/colloquial.yaml enabled=true（且 prose_overhaul_enabled=true）
      - 全场景激活，无 scene_mode 门控

    severity=red → FAILED + hard_blocked；非 red → PASS。
    """
    async def _adapter():
        import yaml

        from ink_writer.prose.colloquial_checker import (
            run_colloquial_check,
            to_checker_output,
        )

        chapter_text = review_bundle.get("chapter_text", "") or ""
        chapter_no = int(review_bundle.get("chapter_no", 0) or 0)

        try:
            # 读取 colloquial.yaml 开关
            config_path = Path(review_bundle.get("project_root", ".")) / "config" / "colloquial.yaml"
            colloquial_enabled = True
            thresholds_override = None
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                colloquial_enabled = cfg.get("enabled", True)
                thresholds_override = cfg.get("thresholds")

            # prose_overhaul_enabled 总开关降级
            ad_config_path = (
                Path(review_bundle.get("project_root", ".")) / "config" / "anti-detection.yaml"
            )
            if ad_config_path.exists():
                with open(ad_config_path, "r", encoding="utf-8") as f:
                    ad_cfg = yaml.safe_load(f) or {}
                if ad_cfg.get("prose_overhaul_enabled") is False:
                    colloquial_enabled = False

            if not colloquial_enabled:
                return (True, 1.0, "")

            if not chapter_text.strip():
                return (True, 1.0, "")

            report = await asyncio.to_thread(
                run_colloquial_check,
                chapter_text,
                thresholds=thresholds_override,
            )
            output = to_checker_output(report, chapter_no=chapter_no)

            passed = bool(output.get("pass", False))
            score = float(output.get("overall_score", 100)) / 100.0
            fix_prompt = ""
            if not passed:
                dims = output.get("metrics", {}).get("dimensions", [])
                red_dims = [d for d in dims if d.get("rating") == "red"]
                if red_dims:
                    fix_prompt = (
                        "colloquial-checker: "
                        + "; ".join(
                            f"{d['key']}={d['score']}"
                            for d in red_dims[:5]
                        )
                    )
            return (bool(passed), float(score), fix_prompt)
        except Exception as exc:
            logger.warning("colloquial adapter error (shadow safe): %s", exc)
            return (True, 1.0, "")

    return _adapter


def _make_directness_adapter(review_bundle: dict) -> Callable:
    """v22 US-006：directness-checker 程序化适配器（全场景激活 + 章节级 override）。

    US-006 全场景化：默认所有场景均激活。
    仅当 chapter_meta.directness_skip == true 时跳过（向后兼容）。
    chapter_meta.directness_tier 控制阈值桶选择（'explosive_hit' | 'standard'）。
    """
    async def _adapter():
        from ink_writer.prose.directness_checker import (
            is_activated,
            run_directness_check,
        )

        chapter_text = review_bundle.get("chapter_text", "") or ""
        chapter_no = int(review_bundle.get("chapter_no", 0) or 0)
        scene_mode = review_bundle.get("scene_mode")
        chapter_meta = review_bundle.get("chapter_meta") or {}
        directness_skip = bool(chapter_meta.get("directness_skip", False))
        directness_tier = chapter_meta.get("directness_tier")

        try:
            if not is_activated(scene_mode, chapter_no, directness_skip=directness_skip):
                return (True, 1.0, "")
            if not chapter_text.strip():
                # shadow-safe：章节文本缺失不阻断
                return (True, 1.0, "")

            report = await asyncio.to_thread(
                run_directness_check,
                chapter_text,
                chapter_no=chapter_no,
                scene_mode=scene_mode,
                directness_skip=directness_skip,
                directness_tier=directness_tier,
            )
            if report.skipped:
                return (True, 1.0, "")

            passed = report.passed
            score = report.overall_score / 10.0
            fix_prompt = ""
            if not passed and report.issues:
                fix_prompt = (
                    "directness-checker: "
                    + "; ".join(
                        f"{i.dimension}={i.description}[{i.suggest_rewrite}]"
                        for i in report.issues[:3]
                    )
                )
            return (bool(passed), float(score), fix_prompt)
        except Exception as exc:
            logger.warning("directness adapter error (shadow safe): %s", exc)
            return (True, 1.0, "")

    return _adapter


# ==================== Main runner ====================


def _build_review_bundle(chapter_id: int, state_dir: Path) -> dict:
    """Minimal review_bundle from state_dir + chapter text.

    v16 Phase B production：仅提取 step3_runner 基础 orchestration 需要的字段；
    后续按需扩展。
    """
    project_root = state_dir.parent if state_dir.name == ".ink" else state_dir
    db_path = str(state_dir / "index.db")
    # 简单章节文本定位：正文/第{NNNN}章-*.md（glob 取第一个）
    chapter_text = ""
    padded = f"{chapter_id:04d}"
    try:
        text_dir = project_root / "正文"
        if text_dir.exists():
            matches = sorted(text_dir.glob(f"第{padded}章*.md"))
            if matches:
                chapter_text = matches[0].read_text(encoding="utf-8")
    except Exception:
        pass  # shadow 模式下章节文本缺失不致命

    return {
        "chapter_no": chapter_id,
        "chapter_text": chapter_text,
        "project_root": str(project_root),
        "db_path": db_path,
    }


def _persist_result_to_db(result: Step3Result, state_dir: Path) -> None:
    """把 Step3Result 写入 index.db.review_metrics。"""
    try:
        import sqlite3
        db_path = state_dir / "index.db"
        if not db_path.exists():
            logger.warning("index.db missing at %s, skip persist", db_path)
            return
        # 直接 SQL，避免 IndexManager fixture 路径依赖
        severity_counts = {
            "hard": len(result.hard_fails),
            "soft": len(result.soft_fails),
        }
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO review_metrics
                (start_chapter, end_chapter, overall_score, dimension_scores,
                 severity_counts, critical_issues, report_file, notes, review_payload_json,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(start_chapter, end_chapter)
                DO UPDATE SET
                    overall_score=excluded.overall_score,
                    severity_counts=excluded.severity_counts,
                    review_payload_json=excluded.review_payload_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    result.chapter_id, result.chapter_id,
                    100.0 if result.passed else 50.0,
                    json.dumps({}),
                    json.dumps(severity_counts),
                    json.dumps([f.to_dict() for f in result.hard_fails]),
                    "",
                    f"step3_runner mode={result.mode}",
                    json.dumps(result.to_dict(), ensure_ascii=False),
                ),
            )
    except Exception as exc:
        logger.warning("persist_result_to_db failed: %s", exc)


async def run_step3(
    chapter_id: int,
    state_dir: Path,
    timeout_s: int = 300,
    parallel: int = 2,
    mode: str = DEFAULT_MODE,
    dry_run: bool = False,
) -> Step3Result:
    """Main entry: run 5-gate Step 3 orchestration for given chapter.

    Args:
      chapter_id: target chapter number
      state_dir: path to .ink/ directory
      timeout_s: total wall-clock budget
      parallel: max concurrent gates
      mode: off / shadow / enforce
      dry_run: don't write to DB even if gates pass
    """
    t0 = time.time()
    result = Step3Result(chapter_id=chapter_id, mode=mode, passed=True)

    if mode == MODE_OFF:
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    if mode not in VALID_MODES:
        result.passed = False
        result.error = f"invalid mode {mode!r}; valid: {VALID_MODES}"
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    try:
        bundle = _build_review_bundle(chapter_id, state_dir)
    except Exception as exc:
        result.passed = False
        result.error = f"build_review_bundle failed: {exc}"
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    runner = CheckerRunner(max_concurrency=parallel)
    runner.add(GateSpec(name="reader_pull", fn=_make_hook_adapter(bundle), is_hard_gate=True))
    runner.add(GateSpec(name="emotion", fn=_make_emotion_adapter(bundle), is_hard_gate=True))
    runner.add(GateSpec(name="anti_detection", fn=_make_anti_detection_adapter(bundle), is_hard_gate=True))
    runner.add(GateSpec(name="voice", fn=_make_voice_adapter(bundle), is_hard_gate=False))
    runner.add(GateSpec(name="plotline", fn=_make_plotline_adapter(bundle), is_hard_gate=True))
    # v22 US-005: directness gate——仅黄金三章/战斗/高潮/爽点场景激活；其他场景透明返回 PASS。
    # is_hard_gate=False：即便评分 Red，也不会 cancel 其他 gate；shadow/enforce 都先观察后阻断。
    runner.add(GateSpec(name="directness", fn=_make_directness_adapter(bundle), is_hard_gate=False))
    # US-005 prose anti-AI overhaul: colloquial gate——全场景激活，5 维度白话度门禁。
    # is_hard_gate=True：severity=red 时阻断并触发 polish 重写。
    runner.add(GateSpec(name="colloquial", fn=_make_colloquial_adapter(bundle), is_hard_gate=True))

    try:
        report: PipelineReport = await asyncio.wait_for(runner.run(), timeout=timeout_s)
    except TimeoutError:
        result.passed = False
        result.error = f"step3_runner timeout >{timeout_s}s"
        result.duration_ms = int((time.time() - t0) * 1000)
        return result
    except Exception as exc:
        result.passed = False
        result.error = f"runner exception: {exc}"
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    # Collect gate results
    for gate_result in report.results:
        result.gate_results[gate_result.name] = gate_result.to_dict()
        if gate_result.status == GateStatus.FAILED:
            gf = GateFailure(
                gate_id=gate_result.name,
                severity="hard" if gate_result.is_hard_gate else "soft",
                reason=gate_result.error or f"score={gate_result.score:.2f}",
                raw_output=gate_result.to_dict(),
            )
            if gate_result.is_hard_gate:
                result.hard_fails.append(gf)
            else:
                result.soft_fails.append(gf)

    # shadow 模式：无论 hard_fails 多少都标 passed=True（但仍记录 fails 供观察）
    if mode == MODE_SHADOW:
        result.passed = True
    else:  # enforce
        result.passed = len(result.hard_fails) == 0

    result.duration_ms = int((time.time() - t0) * 1000)

    if not dry_run:
        _persist_result_to_db(result, state_dir)

    return result


def main() -> int:
    # US-005: Windows asyncio subprocess support (no-op on Mac/Linux).
    if _set_proactor_policy is not None:
        _set_proactor_policy()
    parser = argparse.ArgumentParser(description="Step 3 Gate Runner (FIX-04)")
    parser.add_argument("--chapter-id", type=int, required=True, help="target chapter number")
    parser.add_argument("--state-dir", type=Path, required=True, help=".ink/ dir")
    parser.add_argument("--timeout", type=int, default=300, help="total timeout seconds")
    parser.add_argument("--parallel", type=int, default=2, help="max concurrent gates")
    parser.add_argument("--dry-run", action="store_true", help="don't write review_metrics")
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default=None,
                        help=f"override env {MODE_ENV}; default {DEFAULT_MODE}")
    parser.add_argument("--json", action="store_true", help="output JSON result to stdout")
    args = parser.parse_args()

    mode = args.mode or os.environ.get(MODE_ENV, DEFAULT_MODE)

    try:
        result = asyncio.run(run_step3(
            chapter_id=args.chapter_id,
            state_dir=args.state_dir,
            timeout_s=args.timeout,
            parallel=args.parallel,
            mode=mode,
            dry_run=args.dry_run,
        ))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        status_icon = "✅" if result.passed else "❌"
        print(f"{status_icon} step3_runner ch{result.chapter_id} mode={result.mode} "
              f"passed={result.passed} hard_fails={len(result.hard_fails)} "
              f"soft_fails={len(result.soft_fails)} duration={result.duration_ms}ms",
              file=sys.stderr)

    if result.error:
        return 2
    if mode == MODE_ENFORCE and not result.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
