#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))

from main import audit_file  # noqa: E402


def signature(step: dict) -> tuple:
    return tuple(step[k] for k in ("phase", "system_id", "resource_id", "operation", "state", "evidence_id"))


def alignment_key(step: dict) -> tuple:
    return tuple(step[k] for k in ("phase", "system_id", "resource_id", "operation"))


def sequence_key(step: dict) -> tuple:
    return tuple(step[k] for k in ("phase", "operation", "system_id", "resource_id"))


def main() -> int:
    dataset = ROOT / "dataset"
    predicted, _ = audit_file(dataset, dataset / "sample_deletion_requests.csv")
    prediction = {r["case_id"]: r for r in predicted}
    with (dataset / "sample_output.csv").open(encoding="utf-8", newline="") as fh:
        expected = list(csv.DictReader(fh))
    status_correct = exact_correct = field_correct = field_total = sequence_correct = 0
    step_true_positive = step_predicted = step_expected = 0
    mismatches = []
    for gold in expected:
        pred = prediction[gold["case_id"]]
        gold_steps = json.loads(gold["steps_json"])
        pred_steps = pred["steps"]
        status_correct += pred["deletion_status"] == gold["deletion_status"]
        exact_correct += pred_steps == gold_steps
        sequence_correct += [sequence_key(s) for s in pred_steps] == [sequence_key(s) for s in gold_steps]
        gold_signatures, pred_signatures = set(map(signature, gold_steps)), set(map(signature, pred_steps))
        step_true_positive += len(gold_signatures & pred_signatures)
        step_predicted += len(pred_signatures)
        step_expected += len(gold_signatures)
        gold_by_key = {alignment_key(step): step for step in gold_steps}
        pred_by_key = {alignment_key(step): step for step in pred_steps}
        for key in gold_by_key.keys() | pred_by_key.keys():
            for field in ("phase", "system_id", "resource_id", "operation", "state", "evidence_id"):
                field_total += 1
                if key in gold_by_key and key in pred_by_key:
                    field_correct += gold_by_key[key][field] == pred_by_key[key][field]
        if pred["deletion_status"] != gold["deletion_status"] or pred_steps != gold_steps:
            mismatches.append({"case_id": gold["case_id"], "expected_status": gold["deletion_status"],
                               "predicted_status": pred["deletion_status"], "expected_steps": len(gold_steps),
                               "predicted_steps": len(pred_steps)})
    precision = step_true_positive / step_predicted if step_predicted else 1.0
    recall = step_true_positive / step_expected if step_expected else 1.0
    print(json.dumps({"cases": len(expected), "status_accuracy": status_correct / len(expected),
                      "exact_step_accuracy": exact_correct / len(expected),
                      "step_precision": precision, "step_recall": recall,
                      "step_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                      "field_accuracy": field_correct / field_total if field_total else 1.0,
                      "sequence_accuracy": sequence_correct / len(expected), "mismatches": mismatches}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
