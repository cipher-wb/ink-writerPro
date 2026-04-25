"""Case dataclass + enums with lossless round-trip to/from dict.

These models mirror ``schemas/case_schema.json`` (spec §3.2). YAML/JSON is the
authoritative persistence format; this module is only the in-memory
representation. ``Case.from_dict`` assumes input already passed
``validate_case_dict`` — failure modes here raise ``KeyError`` / ``ValueError``
rather than a typed error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CaseStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    RESOLVED = "resolved"
    REGRESSED = "regressed"
    RETIRED = "retired"


class CaseSeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class CaseDomain(StrEnum):
    WRITING_QUALITY = "writing_quality"
    INFRA_HEALTH = "infra_health"


class CaseLayer(StrEnum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    REFERENCE_GAP = "reference_gap"
    INFRA_HEALTH = "infra_health"


class SourceType(StrEnum):
    EDITOR_REVIEW = "editor_review"
    SELF_AUDIT = "self_audit"
    REGRESSION = "regression"
    INFRA_CHECK = "infra_check"


@dataclass
class Scope:
    genre: list[str] = field(default_factory=list)
    chapter: list[str] = field(default_factory=list)
    trigger: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scope:
        return cls(
            genre=list(data.get("genre", [])),
            chapter=list(data.get("chapter", [])),
            trigger=data.get("trigger"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.genre:
            out["genre"] = list(self.genre)
        if self.chapter:
            out["chapter"] = list(self.chapter)
        if self.trigger is not None:
            out["trigger"] = self.trigger
        return out


@dataclass
class Source:
    type: SourceType
    raw_text: str
    ingested_at: str
    reviewer: str | None = None
    ingested_from: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Source:
        return cls(
            type=SourceType(data["type"]),
            raw_text=data["raw_text"],
            ingested_at=data["ingested_at"],
            reviewer=data.get("reviewer"),
            ingested_from=data.get("ingested_from"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.type.value,
            "raw_text": self.raw_text,
            "ingested_at": self.ingested_at,
        }
        if self.reviewer is not None:
            out["reviewer"] = self.reviewer
        if self.ingested_from is not None:
            out["ingested_from"] = self.ingested_from
        return out


@dataclass
class FailurePattern:
    description: str
    observable: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailurePattern:
        return cls(
            description=data["description"],
            observable=list(data["observable"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "observable": list(self.observable),
        }


@dataclass
class Case:
    case_id: str
    title: str
    status: CaseStatus
    severity: CaseSeverity
    domain: CaseDomain
    layer: list[CaseLayer]
    tags: list[str]
    scope: Scope
    source: Source
    failure_pattern: FailurePattern
    bound_assets: dict[str, Any] = field(default_factory=dict)
    resolution: dict[str, Any] = field(default_factory=dict)
    evidence_links: list[dict[str, Any]] = field(default_factory=list)
    # M5 fields — optional, backward-compatible with the 410 active cases.
    recurrence_history: list[dict[str, Any]] = field(default_factory=list)
    meta_rule_id: str | None = None
    sovereign: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Case:
        return cls(
            case_id=data["case_id"],
            title=data["title"],
            status=CaseStatus(data["status"]),
            severity=CaseSeverity(data["severity"]),
            domain=CaseDomain(data["domain"]),
            layer=[CaseLayer(item) for item in data["layer"]],
            tags=list(data.get("tags", [])),
            scope=Scope.from_dict(data.get("scope", {})),
            source=Source.from_dict(data["source"]),
            failure_pattern=FailurePattern.from_dict(data["failure_pattern"]),
            bound_assets=dict(data.get("bound_assets", {})),
            resolution=dict(data.get("resolution", {})),
            evidence_links=[dict(item) for item in data.get("evidence_links", [])],
            recurrence_history=[dict(item) for item in data.get("recurrence_history", [])],
            meta_rule_id=data.get("meta_rule_id"),
            sovereign=bool(data.get("sovereign", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "case_id": self.case_id,
            "title": self.title,
            "status": self.status.value,
            "severity": self.severity.value,
            "domain": self.domain.value,
            "layer": [item.value for item in self.layer],
            "tags": list(self.tags),
            "scope": self.scope.to_dict(),
            "source": self.source.to_dict(),
            "failure_pattern": self.failure_pattern.to_dict(),
            "bound_assets": dict(self.bound_assets),
            "resolution": dict(self.resolution),
            "evidence_links": [dict(item) for item in self.evidence_links],
            "recurrence_history": [dict(item) for item in self.recurrence_history],
            "meta_rule_id": self.meta_rule_id,
            "sovereign": self.sovereign,
        }
        return out
