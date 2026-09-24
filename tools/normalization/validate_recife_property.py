#!/usr/bin/env python3
"""Validate normalized Recife property NDJSON."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(
    r"(cpf|cnpj|razao_social|propriet|requerente|titular|email|telefone)",
    re.IGNORECASE,
)
KINDS = {"FISCAL_PROPERTY", "PROPERTY_TRANSACTION", "PERMIT_EVENT"}


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
            if record.get("record_kind") not in KINDS:
                errors.append(f"{prefix}: invalid record_kind")
            if record.get("municipality_ibge") != "2611606":
                errors.append(f"{prefix}: wrong municipality_ibge")
            if record.get("license") != "ODbL":
                errors.append(f"{prefix}: expected ODbL license")
            if record.get("public_release_allowed") is not True:
                errors.append(f"{prefix}: public_release_allowed must be true")

            key = record.get("upstream_key")
            if not isinstance(key, str) or not key:
                errors.append(f"{prefix}: upstream_key required")
            elif key in seen:
                errors.append(f"{prefix}: duplicate upstream_key={key}")
            seen.add(key)

            forbidden = [
                key
                for key in walk_keys(record)
                if FORBIDDEN.search(key)
            ]
            if forbidden:
                errors.append(
                    f"{prefix}: forbidden identity key(s): "
                    + ", ".join(sorted(set(forbidden)))
                )

            if record.get("record_kind") == "PROPERTY_TRANSACTION":
                match = record.get("match") or {}
                if match.get("confidence") == "CONFIRMED":
                    errors.append(
                        f"{prefix}: ITBI address/coordinate reconciliation "
                        "cannot default to CONFIRMED"
                    )

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
