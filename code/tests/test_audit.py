from __future__ import annotations

import csv
import tempfile
import unittest
from unittest.mock import patch
import builtins
from datetime import timezone, datetime
from pathlib import Path

from audit.evidence import EvidenceCorpus, infer_state
from audit.identity import IdentityIndex
from audit.intent import deletion_intent
from audit.models import Observation, Provenance
from audit.planner import plan
from audit.validation import validate_rows


NOW = datetime(2026, 1, 3, tzinfo=timezone.utc)


class FakePolicy:
    def __init__(self, actions): self.actions = actions
    def action_for(self, category):
        return "DISABLE" if category == "DATA_FLOW" else self.actions.get(category)


def observation(resource, category, state, system="account_service", when=NOW):
    return Observation(system, resource, category, state, {"user_1"}, {},
                       Provenance("evidence_1", "synthetic", "row=1", when))


class AuditTests(unittest.TestCase):
    def make_identity_dataset(self, identities, audit=()):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        with (root / "user_identities.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["user_id", "name", "email", "phone", "email_hash", "updated_at"])
            writer.writeheader(); writer.writerows(identities)
        with (root / "user_audit_log.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"])
            writer.writeheader(); writer.writerows(audit)
        return temp, root

    def test_shared_phone_does_not_merge_people(self):
        rows = [
            {"user_id": "user_1", "name": "A", "email": "a@example.test", "phone": "+1 555 0100", "email_hash": "ha", "updated_at": "2026-01-01T00:00:00Z"},
            {"user_id": "user_2", "name": "B", "email": "b@example.test", "phone": "+1 555 0100", "email_hash": "hb", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        temp, root = self.make_identity_dataset(rows)
        try: self.assertEqual(IdentityIndex(root).resolve("a@example.test").user_id, "user_1")
        finally: temp.cleanup()

    def test_historical_email_resolves_to_stable_user(self):
        rows = [{"user_id": "user_1", "name": "A", "email": "new@example.test", "phone": "+1 555 0100", "email_hash": "newhash", "updated_at": "2026-01-02T00:00:00Z"}]
        audit = [{"audit_id": "audit_1", "user_id": "user_1", "event_time": "2026-01-02T00:00:00Z", "field_name": "email", "old_value": "old@example.test", "new_value": "new@example.test"}]
        temp, root = self.make_identity_dataset(rows, audit)
        try: self.assertEqual(IdentityIndex(root).resolve("OLD@example.test").user_id, "user_1")
        finally: temp.cleanup()

    def test_active_flow_is_disabled_before_record_cleanup(self):
        policy = FakePolicy({"USER_PROFILE": "DELETE"})
        observations = [observation("account_1", "USER_PROFILE", "PRESENT"),
                        observation("data_flow_1", "DATA_FLOW", "ACTIVE", "integration_service")]
        status, steps = plan(policy, observations)
        self.assertEqual(status, "INCOMPLETE")
        remediation = [s["operation"] for s in steps if s["phase"] == "REMEDIATION"]
        self.assertEqual(remediation, ["DISABLE_DATA_FLOW", "DELETE_RECORD"])

    def test_required_retained_record_is_verified_present(self):
        status, steps = plan(FakePolicy({"SECURITY_AUDIT_LOG": "RETAIN"}),
                             [observation("audit_record_1", "SECURITY_AUDIT_LOG", "PRESENT", "security_service")])
        self.assertEqual(status, "COMPLETE")
        self.assertEqual(steps[0]["operation"], "VERIFY_RECORD_PRESENT")

    def test_missing_retained_record_is_not_complete(self):
        status, steps = plan(FakePolicy({"SECURITY_AUDIT_LOG": "RETAIN"}),
                             [observation("audit_record_1", "SECURITY_AUDIT_LOG", "ABSENT", "security_service")])
        self.assertEqual(status, "INCOMPLETE")
        self.assertEqual(steps[0]["operation"], "VERIFY_RECORD_PRESENT")
        self.assertEqual(steps[0]["evidence_id"], "")

    def test_noncanonical_flow_state_cannot_crash_validation(self):
        status, steps = plan(FakePolicy({}),
                             [observation("data_flow_1", "DATA_FLOW", "PRESENT", "integration_service")])
        self.assertEqual(status, "INCOMPLETE")
        self.assertIn("DISABLE_DATA_FLOW", [step["operation"] for step in steps])
        validate_rows([{"case_id": "case_1", "deletion_status": status, "steps": steps}],
                      ["case_1"], {"evidence_1"})

    def test_latest_temporal_observation_wins(self):
        corpus = EvidenceCorpus.__new__(EvidenceCorpus)
        corpus.activities = []; corpus.manifest_rows = []
        earlier = observation("account_1", "USER_PROFILE", "PRESENT", when=datetime(2026, 1, 2, tzinfo=timezone.utc))
        later = observation("account_1", "USER_PROFILE", "ABSENT", when=NOW)
        corpus.observations = [earlier, later]
        got = corpus.for_subject("user_1", [], [], datetime(2026, 1, 1, tzinfo=timezone.utc), NOW, NOW)
        self.assertEqual([item.state for item in got], ["ABSENT"])

    def test_ambiguous_or_non_deletion_intent_fails_closed(self):
        self.assertFalse(deletion_intent("Send my data export; do not delete my account."))
        self.assertTrue(deletion_intent("Please permanently erase my account and personal data."))

    def test_multilingual_and_scoped_negation_intent(self):
        positives = [
            "Veuillez supprimer mon compte.", "Por favor, borren mi cuenta.",
            "Bitte entfernen Sie mein Konto.", "请删除我的账户。",
            "アカウントを消去してください。", "Proszę usunąć moje konto.",
            "Delete my account. Do not close other household accounts.",
        ]
        negatives = [
            "Please don't erase anything from my account.",
            "Bitte löschen Sie mein Konto nicht.",
            "I accidentally deleted an order; please restore it.",
            "Please remove my phone number from my profile and update it.",
        ]
        self.assertTrue(all(deletion_intent(text) for text in positives))
        self.assertFalse(any(deletion_intent(text) for text in negatives))

    def test_report_window_rejects_other_subject_resource(self):
        corpus = EvidenceCorpus.__new__(EvidenceCorpus)
        corpus.manifest_rows = []; corpus.resource_links = {}; corpus.sql_scopes = []
        corpus.activities = [{"resource_id": "data_flow_2", "event_time": NOW.isoformat(),
                              "source_system": "deletion_worker"}]
        other = Observation("integration_service", "data_flow_2", "DATA_FLOW", "DISABLED",
                            {"user_2"}, {}, Provenance("evidence_1", "synthetic", "row=1", NOW))
        corpus.observations = [other]
        got = corpus.for_subject("user_1", [], [], NOW, NOW, NOW)
        self.assertEqual(got, [])

    def test_unknown_process_state_is_not_treated_as_safe(self):
        self.assertEqual(infer_state("integration_service", {"resource_id": "data_flow_1"}), "UNKNOWN")
        self.assertEqual(infer_state("backup_service", {"resource_id": "backup_1"}), "UNKNOWN")
        self.assertEqual(infer_state("support_platform", {"full_name": "Ann Lee"}), "PRESENT")

    def test_missing_image_extractor_becomes_coverage_gap(self):
        corpus = EvidenceCorpus.__new__(EvidenceCorpus); corpus.gaps = []
        original_import = builtins.__import__
        def import_without_ocr(name, *args, **kwargs):
            if name == "rapidocr_onnxruntime": raise ImportError("synthetic missing OCR")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=import_without_ocr):
            corpus._parse_image(Path("missing.png"), {"file_id": "evidence_x", "file_path": "missing.png", "captured_at": "2026-01-01T00:00:00Z"})
        self.assertEqual(len(corpus.gaps), 1)
        self.assertIn("OCR unavailable", corpus.gaps[0].reason)


if __name__ == "__main__":
    unittest.main()
