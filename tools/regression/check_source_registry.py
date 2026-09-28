#!/usr/bin/env python3
"""Fail when deployment metadata references unknown source-registry IDs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

registry = json.loads(
    (ROOT / "data/source-registry/bootstrap.json").read_text()
)
known = {row["id"] for row in registry["sources"]}

references: list[tuple[str, str]] = []

audit = json.loads(
    (
        ROOT
        / "data/deployment/national-source-audit-2026-09-28.json"
    ).read_text()
)
references.extend(
    ("national-source-audit", row["source_id"])
    for row in audit["sources"]
    if row.get("source_id")
)

coverage = json.loads(
    (
        ROOT
        / "data/deployment/national-source-coverage.json"
    ).read_text()
)
references.extend(
    ("national-source-coverage", row["source_id"])
    for row in coverage["sources"]
    if row.get("source_id")
)

matrix = json.loads(
    (
        ROOT
        / "data/deployment/professional-completion-matrix.json"
    ).read_text()
)
for city in matrix["first_wave"]:
    for row in city["rows"]:
        if row.get("source_id"):
            references.append(
                (
                    f"matrix:{city['ibge']}:{row['field']}",
                    row["source_id"],
                )
            )

missing = sorted(
    {
        (origin, source_id)
        for origin, source_id in references
        if source_id not in known
    }
)

if missing:
    for origin, source_id in missing:
        print(f"ERROR unknown source_id {source_id!r} referenced by {origin}")
    raise SystemExit(1)

print(
    f"OK source registry consistency: "
    f"{len(references)} references, {len(known)} registered sources"
)
