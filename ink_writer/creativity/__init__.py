"""v16 US-009～US-013：creativity validator 子系统。

子模块导出清单：
- ``name_validator``（US-009）：书名与人名陈词黑名单硬校验。
- ``gf_validator``（US-010，未实装）：金手指三重约束。
- ``sensitive_lexicon_validator``（US-011，未实装）：L0-L3 敏感词密度。
- ``perturbation_engine`` / ``retry_loop``（US-012，未实装）：扰动 + 降档。
- ``cli``（US-013，未实装）：Quick Mode 脚本入口。
"""

from ink_writer.creativity.name_validator import (
    Severity,
    ValidationResult,
    Violation,
    validate_book_title,
    validate_character_name,
)

__all__ = [
    "Severity",
    "ValidationResult",
    "Violation",
    "validate_book_title",
    "validate_character_name",
]
