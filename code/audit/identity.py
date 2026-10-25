from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .models import Subject


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


class IdentityIndex:
    """Exact, namespace-aware identity resolution; names never create links."""

    def __init__(self, dataset: Path):
        self.by_user: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {"emails": set(), "email_hashes": set(), "phones": set(), "audit_ids": set()}
        )
        self.email_to_users: dict[str, set[str]] = defaultdict(set)
        with (dataset / "user_identities.csv").open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                uid = row["user_id"]
                self._add(uid, "emails", normalize_email(row["email"]))
                self._add(uid, "email_hashes", row["email_hash"].strip().casefold())
                self._add(uid, "phones", normalize_phone(row["phone"]))
        with (dataset / "user_audit_log.csv").open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                uid, field = row["user_id"], row["field_name"]
                self.by_user[uid]["audit_ids"].add(row["audit_id"])
                for value in (row["old_value"], row["new_value"]):
                    if field == "email":
                        self._add(uid, "emails", normalize_email(value))
                    elif field == "email_hash":
                        self._add(uid, "email_hashes", value.strip().casefold())
                    elif field == "phone":
                        self._add(uid, "phones", normalize_phone(value))

    def _add(self, uid: str, namespace: str, value: str) -> None:
        if not value:
            return
        self.by_user[uid][namespace].add(value)
        if namespace == "emails":
            self.email_to_users[value].add(uid)

    def resolve(self, request_email: str) -> Subject | None:
        users = self.email_to_users.get(normalize_email(request_email), set())
        if len(users) != 1:
            return None
        uid = next(iter(users))
        values = self.by_user[uid]
        return Subject(
            user_id=uid,
            emails=frozenset(values["emails"]),
            email_hashes=frozenset(values["email_hashes"]),
            phones=frozenset(values["phones"]),
            audit_ids=frozenset(values["audit_ids"]),
        )

