#!/usr/bin/env python3
"""Static validation for the Phase G PostGIS schema contract.

This does not execute PostgreSQL. It verifies that the migration contains the
schemas/tables/views and privacy/provenance invariants declared by the contract.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "database/schema-contract.json"
MIGRATION = ROOT / "database/migrations/001_initial_postgis.sql"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    sql = MIGRATION.read_text(encoding="utf-8")
    lowered = sql.lower()

    errors: list[str] = []
    warnings: list[str] = []

    for schema_name, schema in contract["schemas"].items():
        create_schema = f"create schema if not exists {schema_name}".lower()
        if create_schema not in lowered:
            errors.append(f"missing schema declaration: {schema_name}")

        for table in schema.get("tables", []):
            pattern = re.compile(
                rf"create\s+table\s+{re.escape(schema_name)}\.{re.escape(table)}\s*\(",
                re.IGNORECASE,
            )
            if not pattern.search(sql):
                errors.append(f"missing table: {schema_name}.{table}")

        for view in schema.get("views", []):
            pattern = re.compile(
                rf"create\s+view\s+{re.escape(schema_name)}\.{re.escape(view)}\s+as",
                re.IGNORECASE,
            )
            if not pattern.search(sql):
                errors.append(f"missing view: {schema_name}.{view}")

    required_fragments = {
        "postgis extension": "create extension if not exists postgis",
        "pgcrypto extension": "create extension if not exists pgcrypto",
        "canonical SRID 4674": "geometry(geometry, 4674)",
        "snapshot sha256": "sha256 text not null",
        "normalized record snapshot FK": "snapshot_id uuid not null references ld_catalog.snapshot",
        "assertion source record FK": "source_record_id uuid references ld_catalog.normalized_record",
        "assertion public-release flag": "public_release_allowed boolean not null default false",
        "derived assertion guard": "assertion_class <> 'derived_analysis'",
        "explicit unknown table": "create table ld_evidence.unknown",
        "heritage typed table": "create table ld_domain.heritage_feature",
        "utility typed table": "create table ld_domain.utility_context",
        "public event typed table": "create table ld_domain.public_event",
        "public-safe view filter": "a.public_release_allowed = true",
    }
    for label, fragment in required_fragments.items():
        if fragment not in lowered:
            errors.append(f"missing invariant fragment: {label}")

    prohibited_public_columns = [
        r"\bowner_name\b",
        r"\bproprietario\b",
        r"\bcpf\b",
        r"\bcnpj_proprietario\b",
        r"\bowner_cpf\b",
    ]
    for pattern in prohibited_public_columns:
        if re.search(pattern, sql, flags=re.IGNORECASE):
            errors.append(
                f"public schema contains prohibited person-centric column: {pattern}"
            )

    if "begin;" not in lowered or not lowered.rstrip().endswith("commit;"):
        errors.append("migration must be transaction wrapped with BEGIN/COMMIT")

    if "st_isvalid" not in lowered:
        warnings.append("no geometry validity checks found")

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        json.dumps(
            {
                "ok": not errors,
                "schemas": len(contract["schemas"]),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
