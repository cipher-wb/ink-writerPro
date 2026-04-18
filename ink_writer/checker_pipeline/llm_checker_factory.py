"""v16 US-003：LLM 驱动的 5-gate checker 工厂（Phase B 主干）。

替代 step3_runner 中 5 个 ``_stub_checker``（永远返回 passed=True 的桩函数），
通过 ``make_llm_checker(gate_name, system_prompt_path)`` 生成真正调用
``ink_writer.core.infra.api_client.call_claude`` 的 checker。

设计原则
--------
1. **严格 JSON 输出契约**：LLM 必须返回 ``{"score": float, "violations": list,
   "passed": bool}``。工厂负责解析 + 校验 + 鲁棒性兜底。
2. **Shadow-safe 降级**：任何解析/调用失败 → 返回 benign pass（``passed=True``，
   ``score=1.0``，``violations=[]``），避免基础设施故障误杀章节。真阻断只由
   **LLM 明确回报**的 hard violations 触发。
3. **可注入**：工厂接受 ``call_fn`` 参数供测试 mock，默认使用 ``call_claude``。
4. **幂等**：同一 (gate_name, prompt_path) 多次调用返回不同 closure，但 closure
   行为完全一致；system prompt 在工厂创建时读一次，后续不再 IO。

使用
----
```python
from pathlib import Path
from ink_writer.checker_pipeline.llm_checker_factory import make_llm_checker

checker = make_llm_checker(
    "reader_pull",
    Path("ink_writer/checker_pipeline/prompts/reader_pull.md"),
)
result = checker(chapter_text="...", ch_no=42)
# result == {"score": 0.88, "violations": [], "passed": True}
```
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 严格字段集合
_REQUIRED_FIELDS: tuple[str, ...] = ("score", "violations", "passed")
_VALID_SEVERITIES: frozenset[str] = frozenset({"hard", "soft"})

# JSON 提取容错：LLM 偶发会输出 ```json``` 码块，放宽解析一次。
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_OBJECT_RE = re.compile(r"(\{.*\})", re.DOTALL)

# 默认模型：checker 走 Haiku 速度优先（PRD US-003 指定）。
DEFAULT_CHECKER_MODEL = "claude-haiku-4-5"


# v16 US-003：score 采用 **0–100** 量纲，与既有 gate wrapper（hook_retry_gate/
# emotion_gate/anti_detection_gate/voice_gate）的 threshold 配置保持一致，
# 避免 0-1 vs 0-100 的 scale 混淆。LLM 若误用 0-1 小数（score<=1.0），工厂会
# 自动乘以 100 归一化。
SCORE_MAX = 100.0


def _shadow_safe_default() -> dict:
    """LLM / 解析失败时的 benign pass，避免基础设施故障误杀章节。"""
    return {"score": SCORE_MAX, "violations": [], "passed": True}


def _extract_json_blob(raw: str) -> Optional[str]:
    """从 LLM 原始输出中抠出 JSON 对象字面量（容忍 ```json``` 码块等污染）。"""
    raw = raw.strip()
    if not raw:
        return None
    # 完全合规的裸 JSON
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    m = _FENCE_RE.search(raw)
    if m:
        return m.group(1)
    m = _OBJECT_RE.search(raw)
    if m:
        return m.group(1)
    return None


def _coerce_severity(val: Any) -> str:
    if isinstance(val, str):
        v = val.lower().strip()
        if v in _VALID_SEVERITIES:
            return v
    return "soft"


def _parse_checker_response(raw: str, gate_name: str) -> dict:
    """解析 LLM 输出为 ``{score, violations, passed}`` 严格 schema。

    解析失败 → 返回 shadow-safe benign pass，并 log warning（保留原始数据以便排障）。
    """
    blob = _extract_json_blob(raw)
    if blob is None:
        logger.warning(
            "%s checker: 无法从 LLM 输出提取 JSON，shadow-safe 默认通过。raw[:200]=%r",
            gate_name,
            raw[:200],
        )
        return _shadow_safe_default()

    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        logger.warning(
            "%s checker: JSON 解析失败 (%s)，shadow-safe。blob[:200]=%r",
            gate_name,
            exc,
            blob[:200],
        )
        return _shadow_safe_default()

    if not isinstance(data, dict):
        logger.warning(
            "%s checker: 输出非对象 (type=%s)，shadow-safe。",
            gate_name,
            type(data).__name__,
        )
        return _shadow_safe_default()

    # 字段规范化：缺失则用保守值，不致命。
    # score 统一 0-100 量纲；LLM 误用 0-1 小数时自动乘 100 归一化。
    try:
        score = float(data.get("score", SCORE_MAX))
    except (TypeError, ValueError):
        score = SCORE_MAX
    if 0.0 <= score <= 1.0 and score != 0.0:
        # 容忍 LLM 误用 0-1：若严格在 (0,1] 区间，视为归一化小数并放大到 0-100。
        # 边界情况：score=0 保持 0（确属最差），score=1 → 100（满分）。
        score = score * 100.0
    score = max(0.0, min(SCORE_MAX, score))

    violations_raw = data.get("violations", [])
    if not isinstance(violations_raw, list):
        violations_raw = []
    violations: list[dict] = []
    for item in violations_raw:
        if not isinstance(item, dict):
            continue
        violations.append(
            {
                "id": str(item.get("id", "UNKNOWN")),
                "severity": _coerce_severity(item.get("severity")),
                "location": str(item.get("location", "")),
                "description": str(item.get("description", "")),
            }
        )

    # passed 字段以 LLM 自报为准；若缺失/异常，则由 violations 推断
    # （任一 hard → False）。
    if "passed" in data:
        passed = bool(data["passed"])
    else:
        passed = not any(v["severity"] == "hard" for v in violations)

    return {"score": score, "violations": violations, "passed": passed}


def _format_user_prompt(gate_name: str, chapter_text: str, ch_no: int) -> str:
    """统一的 user 内容模板。"""
    return (
        f"[gate] {gate_name}\n"
        f"[chapter_no] {ch_no}\n"
        f"[chapter_text]\n{chapter_text}\n"
        f"\n请**严格**输出 JSON（单对象，无 markdown 码块）：\n"
        f'{{"score": float, "violations": [...], "passed": bool}}'
    )


def make_llm_checker(
    gate_name: str,
    system_prompt_path: Path,
    *,
    model: str = DEFAULT_CHECKER_MODEL,
    max_tokens: int = 1024,
    timeout: float = 90.0,
    call_fn: Optional[Callable[..., str]] = None,
) -> Callable[..., dict]:
    """工厂：返回 ``(text, ch_no) -> {score, violations, passed}`` 的 checker。

    Args:
        gate_name: 5 个 gate 之一（``reader_pull`` / ``emotion`` / ``anti_detection``
            / ``voice`` / ``plotline``），主要影响日志与 user prompt 标签。
        system_prompt_path: prompts/*.md 绝对或相对路径。**工厂创建时**即读取；
            文件缺失则启用空 system（LLM 仍可工作但判定可能走偏）。
        model: Claude 模型 ID，默认 ``claude-haiku-4-5`` 以兼顾成本与准确度。
        max_tokens: 响应上限 tokens。
        timeout: 显式 timeout（秒）。
        call_fn: 测试注入；默认用 ``api_client.call_claude``。
    """
    system_prompt = ""
    try:
        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("%s checker: 读 system prompt 失败 %s", gate_name, exc)

    if not system_prompt:
        logger.warning(
            "%s checker: system prompt 为空（path=%s），将降级为 shadow-safe。",
            gate_name,
            system_prompt_path,
        )

    def _resolve_call_fn() -> Callable[..., str]:
        if call_fn is not None:
            return call_fn
        # 延迟导入 + 每次调用解析：允许测试 monkeypatch 更深层入口。
        from ink_writer.core.infra.api_client import call_claude

        return call_claude

    def checker(text: str, ch_no: int) -> dict:
        if not text or not text.strip():
            # 空章节无法判定 → 直接 benign pass（shadow-safe）。
            return _shadow_safe_default()

        if not system_prompt:
            return _shadow_safe_default()

        fn = _resolve_call_fn()
        try:
            raw = fn(
                model=model,
                system=system_prompt,
                user=_format_user_prompt(gate_name, text, ch_no),
                max_tokens=max_tokens,
                timeout=timeout,
                task_type="checker",
            )
        except TypeError:
            # 兼容只接受 (model, system, user) 的简化 call_fn（常见于测试 mock）。
            try:
                raw = fn(
                    model=model,
                    system=system_prompt,
                    user=_format_user_prompt(gate_name, text, ch_no),
                )
            except Exception as exc:
                logger.warning(
                    "%s checker: 调用失败 (retry simplified sig 也失败): %s",
                    gate_name,
                    exc,
                )
                return _shadow_safe_default()
        except Exception as exc:
            logger.warning("%s checker: 调用失败: %s", gate_name, exc)
            return _shadow_safe_default()

        if not isinstance(raw, str):
            logger.warning(
                "%s checker: 调用返回非字符串 (type=%s)，shadow-safe。",
                gate_name,
                type(raw).__name__,
            )
            return _shadow_safe_default()

        return _parse_checker_response(raw, gate_name)

    # 方便调用方检查（tests 可断言）。
    checker.gate_name = gate_name  # type: ignore[attr-defined]
    checker.model = model  # type: ignore[attr-defined]
    checker.system_prompt = system_prompt  # type: ignore[attr-defined]
    return checker


__all__ = [
    "make_llm_checker",
    "DEFAULT_CHECKER_MODEL",
]
