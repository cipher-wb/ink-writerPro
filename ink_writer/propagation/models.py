"""Pydantic models for propagation_debt.json (FIX-17 P4a)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
Status = Literal["open", "in_progress", "resolved", "wont_fix"]


class PropagationDebtItem(BaseModel):
    """单条反向传播债务记录。"""

    debt_id: str = Field(..., description="唯一债务 ID，格式建议 DEBT-<chapter>-<序号>")
    chapter_detected: int = Field(..., ge=1, description="检测到违规的章节号")
    rule_violation: str = Field(..., description="触发的规则名或违规描述")
    target_chapter: int = Field(..., ge=1, description="需要反向修复的目标章节号")
    severity: Severity = Field("medium", description="严重程度")
    suggested_fix: str = Field("", description="建议的修复方向（文本）")
    status: Status = Field("open", description="处理状态")


class PropagationDebtFile(BaseModel):
    """propagation_debt.json 顶层结构。"""

    schema_version: int = Field(1, description="schema 版本，用于未来迁移")
    items: List[PropagationDebtItem] = Field(default_factory=list)

    def get(self, debt_id: str) -> Optional[PropagationDebtItem]:
        for item in self.items:
            if item.debt_id == debt_id:
                return item
        return None

    def upsert(self, item: PropagationDebtItem) -> None:
        for idx, existing in enumerate(self.items):
            if existing.debt_id == item.debt_id:
                self.items[idx] = item
                return
        self.items.append(item)
