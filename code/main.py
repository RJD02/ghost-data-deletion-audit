#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit.evidence import EvidenceCorpus  # noqa: E402
from audit.identity import IdentityIndex  # noqa: E402
from audit.intent import deletion_intent  # noqa: E402
from audit.models import parse_time  # noqa: E402
from audit.planner import plan  # noqa: E402
from audit.policy import Policy  # noqa: E402
from audit.validation import numeric_case_key, validate_rows, write_output  # noqa: E402


def audit_file(dataset: Path, requests_path: Path) -> tuple[list[dict], dict]:
    identities = IdentityIndex(dataset)
    evidence = EvidenceCorpus(dataset)
    if evidence.gaps:
        details = "; ".join(f"{gap.evidence_id}: {gap.reason}" for gap in evidence.gaps[:5])
        more = f" (+{len(evidence.gaps) - 5} more)" if len(evidence.gaps) > 5 else ""
        raise RuntimeError(f"evidence extraction incomplete: {details}{more}")
    policy = Policy(dataset)
    with requests_path.open(encoding="utf-8", newline="") as fh:
        requests = list(csv.DictReader(fh))

    rows: list[dict] = []
    diagnostics = {"coverage_gaps": [gap.__dict__ for gap in evidence.gaps], "cases": {}}
    for request in requests:
        case_id = request["case_id"]
        case_notes: list[str] = []
        if not deletion_intent(request["request_text"]):
            rows.append({"case_id": case_id, "deletion_status": "NOT_APPLICABLE", "steps": []})
            diagnostics["cases"][case_id] = ["request does not authorize deletion"]
            continue
        subject = identities.resolve(request["email"])
        if subject is None:
            rows.append({"case_id": case_id, "deletion_status": "INCOMPLETE", "steps": []})
            diagnostics["cases"][case_id] = ["request email did not resolve uniquely to a subject"]
            continue
        observations = evidence.for_subject(subject.user_id, subject.emails, subject.email_hashes,
                                            parse_time(request["requested_at"]), parse_time(request["reported_at"]),
                                            parse_time(request["audit_at"]))
        status, steps = plan(policy, observations)
        if not observations:
            status = "INCOMPLETE"
            case_notes.append("no readable, in-scope state evidence resolved to the subject")
        rows.append({"case_id": case_id, "deletion_status": status, "steps": steps})
        case_notes.append(f"resolved {len(observations)} latest resource observations for {subject.user_id}")
        diagnostics["cases"][case_id] = case_notes

    rows.sort(key=lambda row: numeric_case_key(row["case_id"]))
    validate_rows(rows, [r["case_id"] for r in requests], evidence.valid_evidence_ids)
    diagnostics["summary"] = {
        "requests": len(requests), "observations": len(evidence.observations),
        "coverage_gaps": len(evidence.gaps),
        "status_counts": {status: sum(r["deletion_status"] == status for r in rows)
                          for status in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")},
    }
    return rows, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic personal-data deletion audit")
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "output.csv")
    parser.add_argument("--diagnostics", type=Path)
    args = parser.parse_args()
    requests = args.requests or args.dataset / "deletion_requests.csv"
    rows, diagnostics = audit_file(args.dataset.resolve(), requests.resolve())
    write_output(args.output.resolve(), rows)
    if args.diagnostics:
        args.diagnostics.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(diagnostics["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
