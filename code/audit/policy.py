from __future__ import annotations

import csv
from pathlib import Path


class Policy:
    def __init__(self, dataset: Path):
        with (dataset / "deletion_rules.csv").open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.actions = {row["data_category"]: row["required_action"] for row in rows}
        self.rule_ids = {row["data_category"]: row["rule_id"] for row in rows}

    def action_for(self, category: str) -> str | None:
        if category == "DATA_FLOW": return "DISABLE"
        return self.actions.get(category)

