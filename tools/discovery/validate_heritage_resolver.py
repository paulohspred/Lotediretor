#!/usr/bin/env python3
"""Validate the first-wave three-level heritage resolver."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/source-registry/bootstrap.json"
RESOLVER = ROOT / "data/heritage/first-wave-resolver.json"

FIRST_WAVE = {
    "3550308": "São Paulo",
    "2611606": "Recife",
    "3304557": "Rio de Janeiro",
    "3106200": "Belo Horizonte",
    "2507507": "João Pessoa",
}
LEVELS = {"federal", "state", "municipal"}
CAPABILITIES = {
    "PROTECTED_ASSET",
    "PENDING_PROTECTION",
    "SURROUNDING_AREA",
    "PROTECTED_AREA",
    "ARCHAEOLOGY",
    "LEGAL_ACT",
    "APPROVAL_AUTHORITY",
}


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    resolver = json.loads(RESOLVER.read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in registry["sources"]}

    errors: list[str] = []
    warnings: list[str] = []

    if resolver.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")

    federal = resolver.get("federal")
    if not isinstance(federal, dict):
        errors.append("federal must be an object")
    elif federal.get("source_id") not in sources:
        errors.append(
            f"federal references unknown source {federal.get('source_id')!r}"
        )

    seen: set[str] = set()
    for city in resolver.get("municipalities", []):
        ibge = str(city.get("ibge", ""))
        name = city.get("city")
        prefix = f"{ibge}:{name}"

        if ibge in seen:
            errors.append(f"{prefix}: duplicate municipality")
        seen.add(ibge)

        expected = FIRST_WAVE.get(ibge)
        if expected is None:
            warnings.append(f"{prefix}: outside first wave")
        elif expected != name:
            errors.append(f"{prefix}: expected city name {expected!r}")

        levels = city.get("levels")
        if not isinstance(levels, dict):
            errors.append(f"{prefix}: levels must be an object")
            continue

        missing_levels = LEVELS - set(levels)
        if missing_levels:
            errors.append(
                f"{prefix}: missing levels {sorted(missing_levels)}"
            )

        for level_name in LEVELS:
            level = levels.get(level_name)
            lp = f"{prefix}:{level_name}"
            if not isinstance(level, dict):
                errors.append(f"{lp}: level must be an object")
                continue

            source_ids = level.get("source_ids")
            if not isinstance(source_ids, list) or not source_ids:
                errors.append(f"{lp}: source_ids must be non-empty")
            else:
                for source_id in source_ids:
                    if source_id not in sources:
                        errors.append(f"{lp}: unknown source {source_id!r}")

            capabilities = level.get("capabilities")
            if not isinstance(capabilities, list) or not capabilities:
                errors.append(f"{lp}: capabilities must be non-empty")
            else:
                unknown = set(capabilities) - CAPABILITIES
                if unknown:
                    errors.append(
                        f"{lp}: unknown capabilities {sorted(unknown)}"
                    )

        state_caps = set(
            levels.get("state", {}).get("capabilities", [])
        )
        municipal_caps = set(
            levels.get("municipal", {}).get("capabilities", [])
        )
        if "LEGAL_ACT" not in state_caps:
            warnings.append(f"{prefix}: state level has no LEGAL_ACT capability")
        if not (
            {"PROTECTED_ASSET", "PROTECTED_AREA"}
            & municipal_caps
        ):
            errors.append(
                f"{prefix}: municipal level must resolve asset or protected area"
            )

        if not city.get("rules"):
            errors.append(f"{prefix}: rules must be non-empty")
        if not isinstance(city.get("missing", []), list):
            errors.append(f"{prefix}: missing must be an array")

    missing_cities = set(FIRST_WAVE) - seen
    if missing_cities:
        errors.append(
            "missing first-wave municipalities: "
            + ", ".join(sorted(missing_cities))
        )

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        json.dumps(
            {
                "ok": not errors,
                "cities": len(seen),
                "levels_per_city": len(LEVELS),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
