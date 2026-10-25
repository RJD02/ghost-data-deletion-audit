from __future__ import annotations

import csv
import json
import re
import shlex
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

from .identity import normalize_email
from .models import CoverageGap, Observation, Provenance, parse_time


TABLE_SYSTEM = {
    "customer_profiles": "account_service",
    "customer_accounts": "account_service",
    "search_documents_primary": "search_service",
    "customer_search_documents": "search_service",
    "customer_analytics_profiles": "analytics_platform",
    "support_records": "support_platform",
    "customer_exports": "export_service",
    "connector_subscriptions": "integration_service",
    "backup_restore_entries": "backup_service",
    "security_audit_records": "security_service",
}

COLLECTION_SYSTEM = {
    "customer_profiles": "account_service", "profile_lookups": "account_service",
    "customer_accounts": "account_service", "account_profiles": "account_service",
    "customer_search_documents": "search_service", "search_documents": "search_service",
    "index_queries": "search_service", "customer_analytics_profiles": "analytics_platform",
    "analytics_profiles": "analytics_platform", "support_records": "support_platform",
    "support_tickets": "support_platform", "customer_exports": "export_service",
    "connector_subscriptions": "integration_service", "backup_restore_entries": "backup_service",
    "security_audit_records": "security_service", "account_tombstones": "identity_service",
}

DIRECT_ID_KEYS = {
    "user_id", "customer_reference", "subject_reference", "email", "owner_email",
    "requester_email", "customer_email", "email_hash", "lookup_key", "lookup_value",
    "subject_selector", "subject_ref",
    "correlation_key", "subject_key", "matched_value", "match_key",
}


def _identifier_values(value: Any, key: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k in DIRECT_ID_KEYS and v not in (None, "", "null"):
                found.add(normalize_email(str(v)))
            found |= _identifier_values(v, k)
    elif isinstance(value, list):
        for item in value:
            found |= _identifier_values(item, key)
    return found


def infer_system(resource_id: str, hint: str = "") -> str:
    hint = (hint or "").casefold()
    if hint in {"account_service", "search_service", "analytics_platform", "support_platform",
                "export_service", "integration_service", "backup_service", "security_service",
                "identity_service", "marketing_platform", "object_storage", "cache_service",
                "email_delivery_service", "legal_service"}:
        return hint
    prefixes = {
        "account_": "account_service", "search_": "search_service",
        "analytics_": "analytics_platform", "support_": "support_platform",
        "export_": "export_service", "data_flow_": "integration_service",
        "backup_": "backup_service", "audit_record_": "security_service",
        "tombstone_": "identity_service", "marketing_": "marketing_platform",
        "object_": "object_storage", "cache_": "cache_service",
        "email_log_": "email_delivery_service", "legal_": "legal_service",
    }
    return next((system for prefix, system in prefixes.items() if resource_id.startswith(prefix)), hint or "unknown")


def infer_category(system: str, resource_id: str, source_kind: str = "") -> str:
    if resource_id.startswith("tombstone_"): return "ACCOUNT_TOMBSTONE"
    if system == "account_service": return "USER_PROFILE"
    if system == "search_service": return "SEARCH_INDEX_ENTRY"
    if system == "analytics_platform": return "ANALYTICS_PROFILE"
    if system == "support_platform":
        return "SUPPORT_ATTACHMENT" if source_kind == "pdf" else "SUPPORT_MESSAGE"
    if system in {"export_service", "object_store"}: return "USER_EXPORT"
    if system == "object_storage": return "SUPPORT_ATTACHMENT"
    if system == "integration_service": return "DATA_FLOW"
    if system == "backup_service": return "BACKUP_ARCHIVE"
    if system == "security_service": return "SECURITY_AUDIT_LOG"
    if system == "identity_service": return "ACCOUNT_TOMBSTONE"
    if system == "marketing_platform": return "MARKETING_PROFILE"
    if system == "cache_service": return "CACHE_ENTRY"
    if system == "email_delivery_service": return "EMAIL_DELIVERY_LOG"
    if system == "legal_service": return "LEGAL_HOLD_RECORD"
    return "UNKNOWN"


def refine_category(category: str, record: dict[str, Any]) -> str:
    if record.get("declared_category"):
        return str(record["declared_category"])
    event = str(record.get("event", "")).casefold()
    if "contact_lookup" in event or "email_opt_in" in record:
        return "SECONDARY_IDENTIFIER"
    if "telemetry" in event or record.get("record_type") == "product_telemetry":
        return "PRODUCT_TELEMETRY"
    return category


def infer_state(system: str, record: dict[str, Any]) -> str:
    declared = str(record.get("declared_state", "")).upper()
    if declared in {"NOT_FOUND", "ABSENT"}: return "ABSENT"
    if declared in {"ANONYMIZED", "REDACTED", "DISABLED", "BLOCKED", "ACTIVE"}: return declared
    if declared in {"FOUND", "IDENTIFIABLE", "PRESENT"}: return "PRESENT"
    if record.get("marker_found") in (False, 0, "0", "false"): return "PRESENT"
    if record.get("matched_value") not in (None, "", "null"): return "PRESENT"
    event = str(record.get("event", "")).casefold()
    result = str(record.get("result", "")).casefold()
    if record.get("status_code") == 404 or record.get("http_status") == "404" or record.get("rows") == "0":
        return "ABSENT"
    if system == "integration_service":
        enabled = record.get("enabled")
        if enabled in (True, 1, "1", "true"): return "ACTIVE"
        if enabled in (False, 0, "0", "false"): return "DISABLED"
        return "UNKNOWN"
    if system == "backup_service":
        if record.get("eligible") in (True, 1, "1", "true") and record.get("deletion_block") in (False, 0, "0", "false"):
            return "ACTIVE"
        allowed = record.get("restore_allowed")
        if allowed in (True, 1, "1", "true"): return "ACTIVE"
        if allowed in (False, 0, "0", "false"): return "BLOCKED"
        if record.get("deletion_block") in (True, 1, "1", "true"): return "BLOCKED"
        return "UNKNOWN"
    if record.get("rows") not in (None, "0", 0):
        return "PRESENT"
    if result in {"miss", "not_found", "absent"} or record.get("total_hits") == "0":
        return "ABSENT"
    direct = [record.get(k) for k in ("customer_reference", "user_id", "subject_reference", "email",
                                      "owner_email", "requester_email", "customer_email", "phone",
                                      "requester_phone", "email_hash", "full_name", "requester_name")]
    if system == "analytics_platform" and not any(v not in (None, "", "null") for v in direct):
        return "ANONYMIZED"
    if system in {"support_platform", "email_delivery_service"} and not any(
        record.get(k) not in (None, "", "null") for k in
        ("name", "full_name", "display_name", "customer_name", "requester_name",
         "requester_email", "requester_phone", "email", "phone", "email_hash")
    ):
        return "REDACTED"
    if system == "identity_service" and not any(
        record.get(k) not in (None, "", "null") for k in
        ("name", "full_name", "display_name", "customer_name", "email", "phone", "email_hash")
    ):
        return "REDACTED"
    if "not_found" in event or "lookup_miss" in event:
        return "ABSENT"
    return "PRESENT"


class EvidenceCorpus:
    def __init__(self, dataset: Path):
        self.dataset = dataset
        self.observations: list[Observation] = []
        self.gaps: list[CoverageGap] = []
        self.valid_evidence_ids: set[str] = set()
        self.resource_links: dict[str, set[str]] = {}
        self.activities: list[dict[str, str]] = []
        self.manifest_rows: list[dict[str, str]] = []
        self.sql_scopes: list[dict[str, Any]] = []
        self._load_activity_links()
        self._load_manifest()

    def _load_activity_links(self) -> None:
        path = self.dataset / "system_activity.csv"
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                self.activities.append(row)
                if row["event_type"] != "LINK_RESOURCE_IDENTITY":
                    continue
                self.resource_links.setdefault(row["resource_id"], set()).update(
                    _identifier_values({"lookup_value": row["details"]})
                )
                # LINK details are prose; exact identifier tokens are still typed by syntax.
                self.resource_links[row["resource_id"]].update(
                    token.casefold().rstrip(".;,") for token in row["details"].split()
                    if "@" in token or token.startswith("user_")
                )
                aliases = re.findall(r"\(([^()]+)\)", row["details"])
                self.resource_links[row["resource_id"]].update(alias.casefold() for alias in aliases)

    def _load_manifest(self) -> None:
        with (self.dataset / "evidence_files.csv").open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.manifest_rows = rows
        for row in rows:
            evidence_id = row["file_id"]
            self.valid_evidence_ids.add(evidence_id)
            path = self.dataset / row["file_path"]
            suffix = path.suffix.casefold()
            try:
                if suffix == ".json": self._parse_json(path, row)
                elif suffix == ".sql": self._parse_sql(path, row)
                elif suffix in {".log", ".txt"}: self._parse_text(path, row)
                elif suffix == ".pdf": self._parse_pdf(path, row)
                elif suffix in {".png", ".jpg", ".jpeg"}:
                    self._parse_image(path, row)
                else:
                    self.gaps.append(CoverageGap(evidence_id, str(path), f"unsupported evidence type {suffix}"))
            except Exception as exc:
                self.gaps.append(CoverageGap(evidence_id, str(path), f"extraction failed: {type(exc).__name__}: {exc}"))

    def _emit(self, row: dict[str, str], path: Path, location: str, record: dict[str, Any],
              system: str, resource_id: str, observed_at: str, source_kind: str = "") -> None:
        if not resource_id:
            return
        system = infer_system(resource_id, system)
        identifiers = _identifier_values(record) | self.resource_links.get(resource_id, set())
        identifiers.update(str(v).casefold() for v in record.get("trace_identifiers", []))
        self.observations.append(Observation(
            system_id=system,
            resource_id=resource_id,
            category=refine_category(infer_category(system, resource_id, source_kind), record),
            state=infer_state(system, record),
            identifiers=identifiers,
            fields=record,
            provenance=Provenance(
                evidence_id=row["file_id"], path=row["file_path"], location=location,
                observed_at=max(parse_time(observed_at or row["captured_at"]), parse_time(row["captured_at"])),
            ),
        ))

    def _parse_json(self, path: Path, row: dict[str, str]) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("service_exports"), dict):
            for system, groups in data["service_exports"].items():
                for group, records in groups.items():
                    for index, original in enumerate(records):
                        record = dict(original)
                        resource_id = str(record.get("resource_id", ""))
                        if group == "profile_lookups" and isinstance(record.get("profile"), dict):
                            record.update(record["profile"])
                        if group == "index_queries" and isinstance(record.get("hits"), dict):
                            record["total_hits"] = record["hits"].get("total")
                            documents = record["hits"].get("documents") or []
                            if documents: record.update(documents[0])
                        self._emit(row, path, f"service_exports.{system}.{group}[{index}]", record,
                                   system, resource_id, record.get("observed_at", data.get("exported_at", "")))
            return
        if isinstance(data, dict) and isinstance(data.get("snapshots"), list):
            for si, snapshot in enumerate(data["snapshots"]):
                collection = str(snapshot.get("collection") or snapshot.get("data_store") or "")
                for ri, original in enumerate(snapshot.get("records", [])):
                    record = dict(original)
                    if isinstance(record.get("document"), dict): record.update(record["document"])
                    resource_id = str(record.get("resource_id", ""))
                    system = str(record.get("system") or COLLECTION_SYSTEM.get(collection, ""))
                    self._emit(row, path, f"snapshots[{si}].records[{ri}]", record, system, resource_id,
                               record.get("recorded_at") or snapshot.get("captured_at") or data.get("captured_at", ""))
            return
        records = data.get("records", []) if isinstance(data, dict) else data
        if isinstance(records, list):
            for index, original in enumerate(records):
                if not isinstance(original, dict): continue
                record = dict(original)
                resource_id = str(record.get("resource_id", ""))
                system = str(record.get("system", ""))
                self._emit(row, path, f"records[{index}]", record, system, resource_id,
                           record.get("observed_at") or record.get("recorded_at") or
                           record.get("created_at") or (data.get("captured_at", "") if isinstance(data, dict) else ""))

    def _parse_sql(self, path: Path, row: dict[str, str]) -> None:
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        try:
            db.executescript(path.read_text(encoding="utf-8"))
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                if table == "snapshot_scope": continue
                scoped_resources: set[str] = set()
                scoped_systems: set[str] = set()
                for index, sqlrow in enumerate(db.execute(f'SELECT * FROM "{table}"')):
                    record: dict[str, Any] = dict(sqlrow)
                    for key in ("payload", "record_json", "document"):
                        if isinstance(record.get(key), str) and record[key].lstrip().startswith("{"):
                            try: record.update(json.loads(record[key]))
                            except json.JSONDecodeError: pass
                    resource_id = str(record.get("resource_id", ""))
                    system = str(record.get("system_id") or record.get("system") or TABLE_SYSTEM.get(table, ""))
                    resolved_system = infer_system(resource_id, system)
                    if resource_id:
                        scoped_resources.add(resource_id)
                        scoped_systems.add(resolved_system)
                    observed = str(record.get("updated_at") or record.get("captured_at") or row["captured_at"])
                    self._emit(row, path, f"table={table},row={index + 1}", record, system, resource_id, observed)
                if scoped_systems:
                    self.sql_scopes.append({
                        "evidence_id": row["file_id"], "file_path": row["file_path"],
                        "captured_at": row["captured_at"], "table": table,
                        "systems": scoped_systems, "resources": scoped_resources,
                    })
        finally:
            db.close()

    @staticmethod
    def _kv(line: str) -> dict[str, str]:
        result: dict[str, str] = {}
        json_start = line.find("{")
        if json_start >= 0:
            try:
                payload = json.loads(line[json_start:])
                result.update({str(k): str(v).casefold() if isinstance(v, bool) else str(v)
                               for k, v in payload.items() if not isinstance(v, (dict, list))})
            except json.JSONDecodeError:
                pass
        try: tokens = shlex.split(line)
        except ValueError: tokens = line.split()
        for token in tokens:
            if "=" in token:
                key, value = token.split("=", 1)
                result[key] = value.rstrip(",")
        normalized = line.replace('\\"', '"')
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"]*)\"|([^\s|]+))", normalized):
            result[match.group(1)] = (match.group(2) if match.group(2) is not None else match.group(3)).rstrip(",")
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 5:
            result.setdefault("service", parts[2])
            result.setdefault("trace_id", parts[3])
            result.setdefault("event", parts[4])
        return result

    def _parse_text(self, path: Path, row: dict[str, str]) -> None:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        trace_ids: dict[str, set[str]] = {}
        for line in lines:
            parsed = self._kv(line)
            trace = parsed.get("trace_id") or parsed.get("requestId")
            if trace:
                trace_ids.setdefault(trace, set()).update(_identifier_values(parsed))
        for lineno, line in enumerate(lines, 1):
            if line.lstrip().startswith("-") and line.count("|") >= 5:
                parts = [part.strip() for part in line.lstrip("- ").split("|")]
                if len(parts) >= 6:
                    observed, system, resource_id, category, state, identifier = parts[:6]
                    record = {"resource_id": resource_id, "declared_category": category,
                              "declared_state": state, "lookup_value": identifier}
                    self._emit(row, path, f"line={lineno}", record, system, resource_id, observed)
                    continue
            record = self._kv(line)
            match = re.search(r"\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|marketing|object|cache|email_log)_\d+\b", line)
            resource_id = record.get("resource_id") or (match.group(0) if match else "")
            if not resource_id: continue
            event = record.get("event", "")
            if event.endswith("_started"): continue
            system = record.get("service") or record.get("function") or record.get("logger") or record.get("system") or record.get("target_system") or ""
            trace = record.get("trace_id") or record.get("requestId")
            if trace in trace_ids:
                record["trace_identifiers"] = sorted(trace_ids[trace])
            record["raw_line"] = line
            self._emit(row, path, f"line={lineno}", record, system, resource_id,
                       line[:20] if re.match(r"\d{4}-\d\d-\d\dT", line) else row["captured_at"])

    def _parse_pdf(self, path: Path, row: dict[str, str]) -> None:
        run = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                             text=True, capture_output=True)
        text = run.stdout
        resources = sorted(set(re.findall(
            r"\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|marketing|object|cache|email_log)_\d+\b", text
        )))
        identifiers = sorted(set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)))
        users = sorted(set(re.findall(r"\buser_\d+\b", text)))
        text_fold = text.casefold()
        for resource_id, linked in self.resource_links.items():
            aliases = [identifier for identifier in linked
                       if identifier and "@" not in identifier and not identifier.startswith("user_")]
            if any(alias in text_fold for alias in aliases):
                resources.append(resource_id)
        resources = sorted(set(resources))
        for resource_id in resources:
            system = infer_system(resource_id, row.get("origin", ""))
            record = {"resource_id": resource_id, "email": identifiers[0] if identifiers else None,
                      "customer_reference": users[0] if users else None, "text": text}
            self._emit(row, path, f"pdf resource={resource_id}", record, system, resource_id,
                       row["captured_at"], "pdf")

    def _parse_image(self, path: Path, row: dict[str, str]) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            self.gaps.append(CoverageGap(row["file_id"], str(path),
                                         "image OCR unavailable; install requirements.txt"))
            return
        if not hasattr(self, "_ocr"):
            self._ocr = RapidOCR()
        result, _ = self._ocr(str(path))
        if not result:
            self.gaps.append(CoverageGap(row["file_id"], str(path), "image OCR returned no text"))
            return
        tokens = [str(item[1]) for item in result if float(item[2]) >= 0.70]
        joined = "\n".join(tokens)
        joined_fold = joined.casefold()
        resources: set[str] = set(re.findall(
            r"\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|marketing|object|cache|email_log)_\d+\b",
            joined_fold,
        ))
        for resource_id, identifiers in self.resource_links.items():
            if any(identifier and identifier in joined_fold for identifier in identifiers):
                resources.add(resource_id)
        for resource_id in sorted(resources):
            positions = [i for i, token in enumerate(tokens) if resource_id in token.casefold()]
            center = positions[0] if positions else 0
            window = tokens[max(0, center - 12):center + 24] if positions else tokens
            window_text = "\n".join(window)
            emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", window_text)
            users = re.findall(r"\buser_\d+\b", window_text.casefold())
            system = infer_system(resource_id, row.get("origin", ""))
            declared = "PRESENT"
            if system == "integration_service":
                declared = "DISABLED" if re.search(r"\b(disabled|stopped)\b", window_text, re.I) else "ACTIVE"
            elif system == "backup_service": declared = "ACTIVE"
            elif system == "identity_service": declared = "REDACTED" if not emails else "PRESENT"
            record = {"resource_id": resource_id, "lookup_value": emails[0] if emails else (users[0] if users else None),
                      "ocr_text": window_text, "declared_state": declared}
            self._emit(row, path, f"ocr resource={resource_id}", record, system, resource_id,
                       row["captured_at"], "image")

    def for_subject(self, user_id: str, emails: Iterable[str], hashes: Iterable[str],
                    requested_at, reported_at, audit_at) -> list[Observation]:
        needles = {user_id.casefold(), *(x.casefold() for x in emails), *(x.casefold() for x in hashes)}
        matched = [o for o in self.observations
                   if requested_at <= o.provenance.observed_at <= audit_at and o.identifiers & needles]
        latest: dict[tuple[str, str], Observation] = {}
        for observation in matched:
            key = (observation.system_id, observation.resource_id)
            if key not in latest or latest[key].provenance.observed_at <= observation.provenance.observed_at:
                latest[key] = observation
        # Workflow timing links identifier-free final records to the request, but
        # state still comes only from independently captured evidence.
        near_report = {
            activity["resource_id"] for activity in self.activities
            if abs(parse_time(activity["event_time"]) - reported_at) <= timedelta(minutes=15)
            and activity["source_system"] in {"deletion_worker", "privacy_intake"}
        }
        by_resource: dict[str, list[Observation]] = {}
        for observation in self.observations:
            if requested_at <= observation.provenance.observed_at <= audit_at:
                by_resource.setdefault(observation.resource_id, []).append(observation)
        for resource_id in near_report:
            candidates = by_resource.get(resource_id, [])
            owners = set(self.resource_links.get(resource_id, set()))
            owners.update(set().union(*(observation.identifiers for observation in self.observations
                                        if observation.resource_id == resource_id)))
            if owners and not owners & needles:
                continue
            if candidates:
                observation = max(candidates, key=lambda item: item.provenance.observed_at)
                if observation.state in {"ABSENT", "ANONYMIZED", "REDACTED", "DISABLED", "BLOCKED"} or (
                    observation.category in {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}
                    and observation.state == "PRESENT"
                ):
                    latest[(observation.system_id, observation.resource_id)] = observation
                continue
            system = infer_system(resource_id)
            scopes = [scope for scope in getattr(self, "sql_scopes", [])
                      if system in scope["systems"]
                      and requested_at <= parse_time(scope["captured_at"]) <= audit_at]
            if scopes:
                scope = max(scopes, key=lambda item: item["captured_at"])
                if resource_id not in scope["resources"]:
                    latest[(system, resource_id)] = Observation(
                        system_id=system, resource_id=resource_id,
                        category=infer_category(system, resource_id), state="ABSENT",
                        identifiers={user_id.casefold()},
                        fields={"scope_table": scope["table"]},
                        provenance=Provenance(
                            scope["evidence_id"], scope["file_path"],
                            f"table={scope['table']},scoped absence",
                            parse_time(scope["captured_at"]),
                        ),
                    )
        return list(latest.values())
