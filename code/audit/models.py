from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Subject:
    user_id: str
    emails: frozenset[str]
    email_hashes: frozenset[str]
    phones: frozenset[str]
    audit_ids: frozenset[str] = frozenset()


@dataclass
class Provenance:
    evidence_id: str
    path: str
    location: str
    observed_at: datetime
    detail: str = ""


@dataclass
class Observation:
    system_id: str
    resource_id: str
    category: str
    state: str
    identifiers: set[str]
    fields: dict[str, Any]
    provenance: Provenance


@dataclass
class CoverageGap:
    evidence_id: str
    path: str
    reason: str


@dataclass
class Step:
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    def as_dict(self, step_no: int) -> dict[str, Any]:
        return {
            "step_no": step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }


@dataclass
class AuditResult:
    case_id: str
    deletion_status: str
    steps: list[dict[str, Any]]
    diagnostics: list[str] = field(default_factory=list)

