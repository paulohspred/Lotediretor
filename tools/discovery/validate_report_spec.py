#!/usr/bin/env python3
"""Validate professional report spec and first-wave readiness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "data/property-dossier/report-spec.json"
MATRIX = ROOT / "data/deployment/professional-completion-matrix.json"
READINESS = ROOT / "data/property-dossier/report-readiness.json"


def main() -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))

    errors: list[str] = []
    warnings: list[str] = []

    matrix_fields = {row["field"] for row in matrix["first_wave"][0]["rows"]}
    detail_sections = [
        section
        for section in spec.get("sections", [])
        if section.get("section_type") == "DETAIL"
    ]

    owners: dict[str, list[str]] = {}
    for section in detail_sections:
        for field in section.get("source_matrix_fields", []):
            owners.setdefault(field, []).append(section["id"])

    orphan = matrix_fields - set(owners)
    unknown = set(owners) - matrix_fields
    duplicates = {
        field: sections
        for field, sections in owners.items()
        if len(sections) > 1
    }
    if orphan:
        errors.append(f"unmapped L3 fields: {sorted(orphan)}")
    if unknown:
        errors.append(f"unknown report fields: {sorted(unknown)}")
    if duplicates:
        errors.append(f"multiply mapped detail fields: {duplicates}")

    first_wave = {
        city["ibge"]: city
        for city in matrix.get("first_wave", [])
    }
    readiness_cities = {
        city["ibge"]: city
        for city in readiness.get("cities", [])
    }
    if set(first_wave) != set(readiness_cities):
        errors.append("report readiness cities do not match first-wave matrix")

    for ibge, city in first_wave.items():
        prefix = f"{ibge}:{city['city']}"
        ready = readiness_cities.get(ibge)
        if not ready:
            continue

        gaps = [
            row["field"]
            for row in city["rows"]
            if row["status"] == "GAP"
        ]
        expected = "BLOCKED" if gaps else "REPORTABLE_WITH_LIMITATIONS"
        if ready.get("l3_report_status") != expected:
            errors.append(
                f"{prefix}: l3_report_status={ready.get('l3_report_status')!r}, "
                f"expected {expected!r}"
            )

        section_map = {
            item["section_id"]: item
            for item in ready.get("sections", [])
        }
        for section in detail_sections:
            current = section_map.get(section["id"])
            if not current:
                errors.append(
                    f"{prefix}: missing readiness section {section['id']}"
                )
                continue
            statuses = [
                next(
                    row["status"]
                    for row in city["rows"]
                    if row["field"] == field
                )
                for field in section["source_matrix_fields"]
            ]
            if "GAP" in statuses:
                expected_section = "BLOCKED"
            elif all(status == "READY" for status in statuses):
                expected_section = "READY"
            else:
                expected_section = "REPORTABLE_WITH_LIMITATIONS"

            if current.get("status") != expected_section:
                errors.append(
                    f"{prefix}/{section['id']}: status="
                    f"{current.get('status')!r}, expected "
                    f"{expected_section!r}"
                )

        if gaps:
            warnings.append(f"{prefix}: GAP fields remain: {gaps}")

    if "registry_due_diligence" not in (
        spec.get("output_modes", {})
        .get("PUBLIC_PROPERTY_REPORT", {})
        .get("private_sections_hidden", [])
    ):
        errors.append(
            "public report must hide registry_due_diligence by default"
        )

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        json.dumps(
            {
                "ok": not errors,
                "matrix_fields": len(matrix_fields),
                "detail_sections": len(detail_sections),
                "cities": len(first_wave),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
