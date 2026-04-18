"""v16 US-004：LLM 驱动的 polish 工厂。

替代 step3_runner 中 4 个 ``_stub_polish``（永远返回原文的桩函数），
通过 ``make_llm_polish(gate_name)`` 生成真正调用 ``call_claude(model='claude-sonnet-4-6',
task_type='polish')`` 的 polish 函数。

设计原则
--------
1. **原文优先**：超时/异常/无 fix_prompt → 返回原文，记日志；polish 永不致章节丢失。
2. **不改变剧情事实**：system prompt 严格约束仅修文字与节奏，不改人物/事件/设定。
3. **审计日志**：每次 polish 写入 ``.ink/reports/polish_ch{N}_gate_{name}.md``，便于
   回溯单章 polish 历史。
4. **可注入**：工厂接受 ``call_fn`` 参数供测试 mock，默认使用 ``call_claude``。
5. **SignatureCompat**：返回的 polish_fn 签名为
   ``(chapter_text, fix_prompt, chapter_no) -> str``，与既有 gate wrapper
   （hook_retry_gate / emotion_gate / anti_detection_gate / ooc_gate）完全兼容。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 默认模型：polish 用 Sonnet 4.6（PRD US-004 指定）兼顾质量与成本。
DEFAULT_POLISH_MODEL = "claude-sonnet-4-6"
DEFAULT_POLISH_TIMEOUT_S = 120.0
DEFAULT_POLISH_MAX_TOKENS = 8192  # 单章正文上限约 6-8k 字，预留余量

# Compact 的 system prompt，约 500 字，提取自 ink-writer/agents/polish-agent.md
# 的核心职责。CS 侧不要求 LLM 做 Read/Write 工具调用（那些由 skill 流程负责），
# 仅要求基于 fix_prompt 对章节文本做局部定向修复。
_POLISH_SYSTEM_PROMPT = """你是网文创作流水线的 polish-agent（精简版）。

# 核心职责
对输入章节正文做**基于 fix_prompt 的定向修复**，输出修复后的完整章节文本。

# 硬约束（违反则无效修复）
1. **不得改变剧情事实**：人物、场景、事件、对白关键含义必须保持。
2. **不得改变设定边界**：境界/能力/身份/世界规则以原文为准，不得越权。
3. **仅修文字与节奏**：允许改句式长短、词汇精度、段落切分、感官细节、视点过渡。
4. **不增章**：输出字数与原文差异 ≤ ±15%。
5. **不输出"修复报告"**：只输出**最终章节正文**，不要解释、不要 markdown 标题、
   不要「以下是修复后的章节」这类 meta 引语。

# fix_prompt 消费规则
- 若 fix_prompt 列明了具体 violations（如「章末钩子无力」、「次日清晨跳时开头」），
  逐条修复；修复不掉的项（如伏笔缺失需新增大纲级内容）**保持原文**，不自作主张编造。
- 若 fix_prompt 为空，返回原文不做修改。

# 输出
仅输出纯文本章节正文，不要 JSON、不要 markdown 码块、不要 ```。
"""


def _shadow_safe_passthrough(text: str, reason: str, gate_name: str) -> str:
    """polish 失败时的原文透传，并记 warning 日志。"""
    logger.warning(
        "%s polish: 失败降级，返回原文（reason=%s，len=%d）",
        gate_name,
        reason,
        len(text),
    )
    return text


def _write_audit_log(
    project_root: Path,
    gate_name: str,
    chapter_no: int,
    fix_prompt: str,
    before: str,
    after: str,
    outcome: str,
) -> None:
    """写入 ``.ink/reports/polish_ch{N}_gate_{name}.md`` 审计日志。

    多次 polish（同章同 gate）会追加到同一文件，按时间顺序区分 attempt。
    """
    try:
        reports_dir = project_root / ".ink" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        padded = f"{chapter_no:04d}"
        log_path = reports_dir / f"polish_ch{padded}_gate_{gate_name}.md"

        entry_lines = [
            f"## polish attempt — gate={gate_name} chapter={chapter_no}",
            f"- outcome: {outcome}",
            f"- before_len: {len(before)}",
            f"- after_len: {len(after)}",
            "",
            "### fix_prompt",
            "```",
            fix_prompt.strip() or "(empty)",
            "```",
            "",
            "### diff summary",
            f"- changed: {before != after}",
            "",
            "---",
            "",
        ]
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(entry_lines))
    except OSError as exc:
        # 审计日志写失败不阻断 polish 主流程
        logger.warning(
            "%s polish: 审计日志写失败 path=%s err=%s",
            gate_name,
            log_path if "log_path" in locals() else "(unknown)",
            exc,
        )


def make_llm_polish(
    gate_name: str,
    *,
    project_root: Optional[Path] = None,
    model: str = DEFAULT_POLISH_MODEL,
    max_tokens: int = DEFAULT_POLISH_MAX_TOKENS,
    timeout: float = DEFAULT_POLISH_TIMEOUT_S,
    call_fn: Optional[Callable[..., str]] = None,
    write_audit: bool = True,
) -> Callable[[str, str, int], str]:
    """工厂：返回 ``(chapter_text, fix_prompt, chapter_no) -> str`` 的 polish 函数。

    Args:
        gate_name: 5 个 gate 之一（``reader_pull`` / ``emotion`` / ``anti_detection``
            / ``voice`` / ``plotline``），主要影响日志与 user prompt 标签。
        project_root: 项目根路径（用于定位 .ink/reports/）。若 None 则不写审计日志。
        model: Claude 模型 ID，默认 ``claude-sonnet-4-6``。
        max_tokens: 响应上限 tokens；polish 输出接近原章节字数，需较大预算。
        timeout: 显式 timeout（秒），默认 120s。
        call_fn: 测试注入；默认用 ``api_client.call_claude``。
        write_audit: 是否写 ``.ink/reports/polish_ch{N}_gate_{name}.md``。
    """

    def _resolve_call_fn() -> Callable[..., str]:
        if call_fn is not None:
            return call_fn
        from ink_writer.core.infra.api_client import call_claude

        return call_claude

    def polish(chapter_text: str, fix_prompt: str, chapter_no: int) -> str:
        # 空 fix_prompt / 空正文 → 原文透传（无事可做）。
        if not chapter_text or not chapter_text.strip():
            return chapter_text
        if not fix_prompt or not fix_prompt.strip():
            if project_root is not None and write_audit:
                _write_audit_log(
                    project_root,
                    gate_name,
                    chapter_no,
                    fix_prompt,
                    chapter_text,
                    chapter_text,
                    outcome="skip_empty_fix",
                )
            return chapter_text

        user = (
            f"[gate] {gate_name}\n"
            f"[chapter_no] {chapter_no}\n"
            f"[fix_prompt]\n{fix_prompt}\n\n"
            f"[chapter_text]\n{chapter_text}\n\n"
            f"请依据 fix_prompt 修复章节；仅输出修复后的纯文本章节正文。"
        )

        fn = _resolve_call_fn()
        try:
            raw = fn(
                model=model,
                system=_POLISH_SYSTEM_PROMPT,
                user=user,
                max_tokens=max_tokens,
                timeout=timeout,
                task_type="polish",
            )
        except TypeError:
            # 兼容只接受 (model, system, user) 的 mock
            try:
                raw = fn(
                    model=model,
                    system=_POLISH_SYSTEM_PROMPT,
                    user=user,
                )
            except TimeoutError as exc:
                out = _shadow_safe_passthrough(
                    chapter_text, f"TimeoutError(simplified_sig): {exc}", gate_name
                )
                if project_root is not None and write_audit:
                    _write_audit_log(
                        project_root, gate_name, chapter_no, fix_prompt,
                        chapter_text, out, outcome="timeout_passthrough",
                    )
                return out
            except Exception as exc:
                out = _shadow_safe_passthrough(
                    chapter_text, f"error(simplified_sig): {exc}", gate_name
                )
                if project_root is not None and write_audit:
                    _write_audit_log(
                        project_root, gate_name, chapter_no, fix_prompt,
                        chapter_text, out, outcome="error_passthrough",
                    )
                return out
        except TimeoutError as exc:
            out = _shadow_safe_passthrough(
                chapter_text, f"TimeoutError: {exc}", gate_name
            )
            if project_root is not None and write_audit:
                _write_audit_log(
                    project_root, gate_name, chapter_no, fix_prompt,
                    chapter_text, out, outcome="timeout_passthrough",
                )
            return out
        except Exception as exc:
            out = _shadow_safe_passthrough(
                chapter_text, f"error: {exc}", gate_name
            )
            if project_root is not None and write_audit:
                _write_audit_log(
                    project_root, gate_name, chapter_no, fix_prompt,
                    chapter_text, out, outcome="error_passthrough",
                )
            return out

        if not isinstance(raw, str) or not raw.strip():
            out = _shadow_safe_passthrough(
                chapter_text, f"non-string or empty return (type={type(raw).__name__})",
                gate_name,
            )
            if project_root is not None and write_audit:
                _write_audit_log(
                    project_root, gate_name, chapter_no, fix_prompt,
                    chapter_text, out, outcome="invalid_return_passthrough",
                )
            return out

        # 字数校验：偏离原文太多 → 拒绝接受，原文透传（避免 polish 擅自改写整章）。
        before_len = len(chapter_text)
        after_len = len(raw)
        if before_len > 0 and (after_len < before_len * 0.5 or after_len > before_len * 2.0):
            out = _shadow_safe_passthrough(
                chapter_text,
                f"length_ratio out of [0.5, 2.0]: before={before_len} after={after_len}",
                gate_name,
            )
            if project_root is not None and write_audit:
                _write_audit_log(
                    project_root, gate_name, chapter_no, fix_prompt,
                    chapter_text, out, outcome="length_guard_passthrough",
                )
            return out

        if project_root is not None and write_audit:
            _write_audit_log(
                project_root, gate_name, chapter_no, fix_prompt,
                chapter_text, raw, outcome="success",
            )
        return raw

    # 便于测试断言
    polish.gate_name = gate_name  # type: ignore[attr-defined]
    polish.model = model  # type: ignore[attr-defined]
    return polish


__all__ = [
    "make_llm_polish",
    "DEFAULT_POLISH_MODEL",
    "DEFAULT_POLISH_TIMEOUT_S",
    "DEFAULT_POLISH_MAX_TOKENS",
]
