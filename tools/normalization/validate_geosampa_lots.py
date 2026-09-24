#!/usr/bin/env python3
"""Validate normalized GeoSampa parcel NDJSON."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(
    r"(propriet|cpf|cnpj|requerente|titular|email|telefone)",
    re.IGNORECASE,
)


def walk_keys(value, prefix=""):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield prefix + key
            yield from walk_keys(nested, prefix + key + ".")
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item, prefix)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    errors = []
    count = 0
    seen = set()

    with args.path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            count += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_no}: invalid JSON: {exc}")
                continue

            prefix = f"line {line_no}"
            if record.get("schema_version") != "0.1.0":
                errors.append(f"{prefix}: invalid schema_version")
            if record.get("record_kind") != "URBAN_PARCEL":
                errors.append(f"{prefix}: record_kind must be URBAN_PARCEL")
            if record.get("source_id") != "sp-sao-paulo-geosampa-wfs":
                errors.append(f"{prefix}: wrong source_id")
            if record.get("municipality_ibge") != "3550308":
                errors.append(f"{prefix}: wrong municipality_ibge")

            key = record.get("upstream_key")
            if not isinstance(key, str) or not key:
                errors.append(f"{prefix}: upstream_key required")
            elif key in seen:
                errors.append(f"{prefix}: duplicate upstream_key={key}")
            seen.add(key)

            geometry = record.get("geometry")
            if not isinstance(geometry, dict) or geometry.get("type") not in {
                "Polygon",
                "MultiPolygon",
            }:
                errors.append(f"{prefix}: invalid parcel geometry")

            identity = record.get("identity") or {}
            lot = identity.get("fiscal_lot")
            condo = identity.get("condominium_code")
            sql = identity.get("sql_reference")
            if (lot == "0000" or condo not in {None, "", "00"}) and sql:
                errors.append(
                    f"{prefix}: condominium parcel must not fabricate unit SQL"
                )

            forbidden = [key for key in walk_keys(record) if FORBIDDEN.search(key)]
            if forbidden:
                errors.append(
                    f"{prefix}: forbidden person-centric key(s): "
                    + ", ".join(sorted(set(forbidden)))
                )

            if record.get("source_crs") != "EPSG:31983":
                errors.append(f"{prefix}: unexpected source CRS")

            if record.get("public_release_allowed") is not True:
                errors.append(f"{prefix}: public_release_allowed must be true")

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(
        json.dumps(
            {"ok": not errors, "records": count, "errors": len(errors)},
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
