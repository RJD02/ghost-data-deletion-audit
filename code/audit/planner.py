from __future__ import annotations

from .models import Observation, Step
from .policy import Policy


PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OP_RANK = {
    "REPORT_REMAINING_RECORD": 0, "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2, "REPORT_RESTORE_RISK": 3,
    "DISABLE_DATA_FLOW": 0, "BLOCK_RESTORE": 1, "DELETE_RECORD": 2,
    "REDACT_RECORD": 3, "ANONYMIZE_RECORD": 4,
    "VERIFY_RECORD_ABSENT": 0, "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2, "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4, "VERIFY_RESTORE_BLOCKED": 5,
}


def compliant(action: str, state: str, category: str = "") -> bool:
    if category == "BACKUP_ARCHIVE":
        return state == "BLOCKED"
    return {
        "DELETE": state == "ABSENT",
        "REDACT": state == "REDACTED",
        "ANONYMIZE": state == "ANONYMIZED",
        "RETAIN": state == "PRESENT",
        "DISABLE": state in {"DISABLED", "ABSENT"},
    }.get(action, True)


def finding_for(action: str, observation: Observation) -> Step | None:
    evidence = observation.provenance.evidence_id
    common = ("FINDING", observation.system_id, observation.resource_id)
    if action == "DELETE" and observation.state in {"PRESENT", "REDACTED", "ANONYMIZED"}:
        return Step(*common, "REPORT_REMAINING_RECORD", "PRESENT", evidence)
    if action in {"REDACT", "ANONYMIZE"} and observation.state == "PRESENT":
        return Step(*common, "REPORT_EXPOSED_PII", "PRESENT", evidence)
    if action == "DISABLE" and observation.state == "ACTIVE":
        return Step(*common, "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", evidence)
    if observation.category == "BACKUP_ARCHIVE" and observation.state == "ACTIVE":
        return Step(*common, "REPORT_RESTORE_RISK", "ACTIVE", evidence)
    return None


def remediation_for(action: str, observation: Observation) -> Step | None:
    common = ("REMEDIATION", observation.system_id, observation.resource_id)
    if observation.category == "BACKUP_ARCHIVE" and observation.state in {"ACTIVE", "PRESENT", "UNKNOWN"}:
        return Step(*common, "BLOCK_RESTORE", "BLOCKED", "")
    mapping = {
        "DELETE": ("DELETE_RECORD", "ABSENT"),
        "REDACT": ("REDACT_RECORD", "REDACTED"),
        "ANONYMIZE": ("ANONYMIZE_RECORD", "ANONYMIZED"),
        "DISABLE": ("DISABLE_DATA_FLOW", "DISABLED"),
    }
    if action in mapping and not compliant(action, observation.state, observation.category):
        if action in {"REDACT", "ANONYMIZE"} and observation.state != "PRESENT":
            return None
        operation, state = mapping[action]
        return Step(*common, operation, state, "")
    return None


def verification_for(action: str, observation: Observation, evidence: str) -> Step | None:
    common = ("VERIFICATION", observation.system_id, observation.resource_id)
    if observation.category == "BACKUP_ARCHIVE":
        return Step(*common, "VERIFY_RESTORE_BLOCKED", "BLOCKED", evidence)
    mapping = {
        "DELETE": ("VERIFY_RECORD_ABSENT", "ABSENT"),
        "REDACT": ("VERIFY_RECORD_REDACTED", "REDACTED"),
        "ANONYMIZE": ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
        "RETAIN": ("VERIFY_RECORD_PRESENT", "PRESENT"),
        "DISABLE": ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    }
    if action not in mapping: return None
    operation, state = mapping[action]
    return Step(*common, operation, state, evidence)


def plan(policy: Policy, observations: list[Observation]) -> tuple[str, list[dict]]:
    findings: list[Step] = []
    remediations: list[Step] = []
    relevant: list[tuple[Observation, str]] = []
    for observation in observations:
        action = policy.action_for(observation.category)
        if not action: continue
        relevant.append((observation, action))
        finding = finding_for(action, observation)
        if finding: findings.append(finding)
        remediation = remediation_for(action, observation)
        if remediation: remediations.append(remediation)

    # De-duplicate observations that multiple adapters established identically.
    def dedupe(steps: list[Step]) -> list[Step]:
        seen: dict[tuple[str, str, str], Step] = {}
        for step in steps:
            seen[(step.operation, step.system_id, step.resource_id)] = step
        return list(seen.values())

    findings, remediations = dedupe(findings), dedupe(remediations)
    incomplete = any(not compliant(action, observation.state, observation.category)
                     for observation, action in relevant)
    verification: list[Step] = []
    seen_resources: set[tuple[str, str]] = set()
    for observation, action in relevant:
        key = (observation.system_id, observation.resource_id)
        if key in seen_resources: continue
        seen_resources.add(key)
        evidence = "" if incomplete else observation.provenance.evidence_id
        verification_step = verification_for(action, observation, evidence)
        if verification_step: verification.append(verification_step)

    steps = findings + remediations + verification
    steps.sort(key=lambda step: (PHASE_RANK[step.phase], OP_RANK[step.operation],
                                 step.system_id, step.resource_id))
    return ("INCOMPLETE" if incomplete else "COMPLETE"), [s.as_dict(i + 1) for i, s in enumerate(steps)]
