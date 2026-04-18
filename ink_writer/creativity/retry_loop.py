"""v16 US-012：Quick Mode 5 次重抽 + 降档循环。

调用方提供 ``generate_fn(aggression) -> scheme`` + ``validate_fn(scheme) ->
ValidationResult``。本模块负责：
- 最多 5 次重抽（任一 validator fail 触发）。
- 连续 5 次失败 → aggression 降档（4→3→2→1）。
- 降到 1 仍失败 → 抛 ``CreativityExhaustedError``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ink_writer.creativity.name_validator import ValidationResult

MAX_RETRIES_PER_LEVEL = 5
DEFAULT_MAX_AGGRESSION = 4
MIN_AGGRESSION = 1


class CreativityExhaustedError(RuntimeError):
    """5 次重抽 × 4 档位仍无合法方案时抛出。"""


@dataclass
class RetryAttempt:
    aggression: int
    attempt: int  # 1-based within level
    scheme: Any
    result: ValidationResult

    def to_dict(self) -> dict:
        return {
            "aggression": self.aggression,
            "attempt": self.attempt,
            "passed": self.result.passed,
            "violations": [v.to_dict() for v in self.result.violations],
        }


@dataclass
class RetryReport:
    scheme: Any
    final_aggression: int
    attempts: list[RetryAttempt] = field(default_factory=list)
    downgraded: bool = False

    def to_dict(self) -> dict:
        return {
            "final_aggression": self.final_aggression,
            "downgraded": self.downgraded,
            "attempts": [a.to_dict() for a in self.attempts],
        }


def run_quick_mode_with_retry(
    generate_fn: Callable[[int], Any],
    validate_fn: Callable[[Any], ValidationResult],
    *,
    start_aggression: int = DEFAULT_MAX_AGGRESSION,
    max_retries_per_level: int = MAX_RETRIES_PER_LEVEL,
) -> RetryReport:
    """按 aggression 档位重试生成 → 校验循环。

    Args:
        generate_fn: 根据当前 aggression 生成 scheme（dict 或任意对象）。
        validate_fn: 对 scheme 跑校验，返回 ValidationResult。
        start_aggression: 起始档位（默认 4）。
        max_retries_per_level: 单档位最多重试次数（默认 5）。

    Raises:
        CreativityExhaustedError: 降到档位 1 仍 5 次失败。

    Returns:
        RetryReport，含最终通过的 scheme + 历史 attempts。
    """
    attempts: list[RetryAttempt] = []
    downgraded = False
    aggression = start_aggression

    while aggression >= MIN_AGGRESSION:
        for attempt in range(1, max_retries_per_level + 1):
            scheme = generate_fn(aggression)
            result = validate_fn(scheme)
            attempts.append(
                RetryAttempt(
                    aggression=aggression,
                    attempt=attempt,
                    scheme=scheme,
                    result=result,
                )
            )
            if result.passed:
                return RetryReport(
                    scheme=scheme,
                    final_aggression=aggression,
                    attempts=attempts,
                    downgraded=downgraded,
                )
        # 单档位耗尽 → 降档
        aggression -= 1
        downgraded = True

    raise CreativityExhaustedError(
        f"Quick Mode 创意耗尽：{len(attempts)} 次尝试（{DEFAULT_MAX_AGGRESSION}→{MIN_AGGRESSION}）均未通过。"
    )


__all__ = [
    "CreativityExhaustedError",
    "MAX_RETRIES_PER_LEVEL",
    "RetryAttempt",
    "RetryReport",
    "run_quick_mode_with_retry",
]
