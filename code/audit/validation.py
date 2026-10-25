from __future__ import annotations

import csv
import json
from pathlib import Path


ALLOWED_STATUS = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
ALLOWED = {
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
}
FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def numeric_case_key(case_id: str) -> tuple[int, str]:
    try: return int(case_id.rsplit("_", 1)[1]), case_id
    except (IndexError, ValueError): return 10**12, case_id


def validate_rows(rows: list[dict], request_ids: list[str], valid_evidence: set[str]) -> None:
    require([r["case_id"] for r in rows] == sorted(request_ids, key=numeric_case_key),
            "output rows are missing, duplicated, or not sorted by case_id")
    require(len(rows) == len(set(request_ids)) == len(request_ids),
            "output row count does not match unique request IDs")
    for row in rows:
        require(row["deletion_status"] in ALLOWED_STATUS,
                f"{row['case_id']}: invalid deletion_status {row['deletion_status']!r}")
        steps = row["steps"]
        require(isinstance(steps, list), f"{row['case_id']}: steps must be a list")
        require(row["deletion_status"] != "NOT_APPLICABLE" or steps == [],
                f"{row['case_id']}: NOT_APPLICABLE must have no steps")
        for number, step in enumerate(steps, 1):
            require(set(step) == FIELDS, f"{row['case_id']} step {number}: invalid fields")
            require(step["step_no"] == number,
                    f"{row['case_id']} step {number}: nonconsecutive step_no")
            require((step["phase"], step["operation"], step["state"]) in ALLOWED,
                    f"{row['case_id']} step {number}: invalid phase/operation/state")
            if step["phase"] == "FINDING" or row["deletion_status"] == "COMPLETE":
                require(step["evidence_id"] in valid_evidence,
                        f"{row['case_id']} step {number}: invalid evidence_id")
            else:
                require(step["evidence_id"] == "",
                        f"{row['case_id']} step {number}: future work must have empty evidence_id")


def write_output(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["case_id", "deletion_status", "steps_json"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"case_id": row["case_id"], "deletion_status": row["deletion_status"],
                             "steps_json": json.dumps(row["steps"], ensure_ascii=False, separators=(",", ":"))})
