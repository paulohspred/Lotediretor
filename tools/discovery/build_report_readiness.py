#!/usr/bin/env python3
"""Recompute report-readiness section statuses from the completion matrix.

The professional completion matrix is the source of truth for field status.
Section status in report-readiness.json is *derived* and must never be edited
by hand: this script rewrites it deterministically while preserving curated
fields (unresolved_items, query_only_fields, private_on_demand_fields).

Usage:
    python3 tools/discovery/build_report_readiness.py          # rewrite file
    python3 tools/discovery/build_report_readiness.py --check  # CI: fail on drift
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "data/property-dossier/report-spec.json"
MATRIX = ROOT / "data/deployment/professional-completion-matrix.json"
READINESS = ROOT / "data/property-dossier/report-readiness.json"


def section_status(statuses: list[str]) -> str:
    if "GAP" in statuses:
        return "BLOCKED"
    # Sections with no matrix fields (e.g. purely federal context) carry no
    # municipal gap and are READY, mirroring validate_report_spec.py.
    if all(status == "READY" for status in statuses):
        return "READY"
    return "REPORTABLE_WITH_LIMITATIONS"


def build(spec: dict, matrix: dict, readiness: dict) -> dict:
    detail_sections = [
        section
        for section in spec.get("sections", [])
        if section.get("section_type") == "DETAIL"
    ]
    matrix_by_city = {city["ibge"]: city for city in matrix["first_wave"]}

    for city in readiness.get("cities", []):
        source = matrix_by_city.get(city["ibge"])
        if source is None:
            continue
        row_status = {row["field"]: row["status"] for row in source["rows"]}
        current = {
            item["section_id"]: item for item in city.get("sections", [])
        }
        rebuilt = []
        for section in detail_sections:
            fields = section.get("source_matrix_fields", [])
            matrix_statuses = {
                field: row_status.get(field, "GAP") for field in fields
            }
            previous = current.get(section["id"], {})
            rebuilt.append(
                {
                    "section_id": section["id"],
                    "status": section_status(list(matrix_statuses.values())),
                    "matrix_statuses": matrix_statuses,
                    "unresolved_items": previous.get("unresolved_items", []),
                    "query_only_fields": previous.get("query_only_fields", []),
                    "private_on_demand_fields": previous.get(
                        "private_on_demand_fields", []
                    ),
                }
            )
        city["sections"] = rebuilt
        gaps = [f for f, s in row_status.items() if s == "GAP"]
        city["l3_report_status"] = (
            "BLOCKED" if gaps else "REPORTABLE_WITH_LIMITATIONS"
        )
    return readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    original_text = READINESS.read_text(encoding="utf-8")
    rebuilt = build(spec, matrix, json.loads(original_text))
    rebuilt_text = json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if rebuilt_text != original_text:
            print(
                "report-readiness.json is out of date; run "
                "tools/discovery/build_report_readiness.py",
                file=sys.stderr,
            )
            return 1
        print("report-readiness.json up to date")
        return 0

    READINESS.write_text(rebuilt_text, encoding="utf-8")
    print(f"rewrote {READINESS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
