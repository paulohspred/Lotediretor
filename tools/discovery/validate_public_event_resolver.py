#!/usr/bin/env python3
"""Validate public-event source resolver against the source registry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/source-registry/bootstrap.json"
RESOLVER = ROOT / "data/public-events/source-resolver.json"

FIRST_WAVE = {
    "3550308": "São Paulo",
    "2611606": "Recife",
    "3304557": "Rio de Janeiro",
    "3106200": "Belo Horizonte",
    "2507507": "João Pessoa",
}
REQUIRED_ROLES = {"LICENSING", "GAZETTE", "PROCESS_QUERY"}
EVENT_TYPES = {
    "PROJECT_PLANNED", "PROCUREMENT_PUBLISHED", "CONTRACTED", "LICENSED",
    "APPROVED", "PROCESS_OPENED", "PROCESS_MOVEMENT",
    "LEGAL_ACT_PUBLISHED", "WORK_STARTED", "WORK_PAUSED",
    "WORK_RESUMED", "WORK_COMPLETED", "CANCELLED", "OTHER",
}


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    resolver = json.loads(RESOLVER.read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in registry["sources"]}

    errors: list[str] = []
    warnings: list[str] = []

    for item in resolver.get("federal", []):
        source_id = item.get("source_id")
        if source_id not in sources:
            errors.append(f"federal resolver references unknown source {source_id!r}")
        for event_type in item.get("event_types", []):
            if event_type not in EVENT_TYPES:
                errors.append(
                    f"federal source {source_id}: unknown event_type {event_type!r}"
                )

    seen: set[str] = set()
    for city in resolver.get("municipalities", []):
        ibge = str(city.get("ibge", ""))
        name = city.get("city")
        prefix = f"{ibge}:{name}"
        if ibge in seen:
            errors.append(f"{prefix}: duplicate municipality")
        seen.add(ibge)

        if ibge not in FIRST_WAVE:
            warnings.append(f"{prefix}: outside first wave")
        elif FIRST_WAVE[ibge] != name:
            errors.append(
                f"{prefix}: expected city name {FIRST_WAVE[ibge]!r}"
            )

        city_sources = city.get("sources", [])
        roles = {item.get("role") for item in city_sources}
        missing_roles = REQUIRED_ROLES - roles
        if missing_roles:
            errors.append(
                f"{prefix}: missing event-source roles {sorted(missing_roles)}"
            )

        for item in city_sources:
            source_id = item.get("source_id")
            if source_id not in sources:
                errors.append(f"{prefix}: unknown source {source_id!r}")
                continue
            for event_type in item.get("event_types", []):
                if event_type not in EVENT_TYPES:
                    errors.append(
                        f"{prefix}/{source_id}: unknown event_type {event_type!r}"
                    )

            source = sources[source_id]
            mode = str(item.get("ingest_mode", ""))
            if (
                source.get("access_class") in
                {"AUTHENTICATED_PUBLIC", "RESTRICTED_PERSONAL", "USER_PRIVATE"}
                and "OPEN" in mode
            ):
                errors.append(
                    f"{prefix}/{source_id}: access class "
                    f"{source.get('access_class')} cannot use open ingest mode"
                )
            if "CAPTCHA" in str(source.get("verification_status", "")):
                if "CAPTCHA" not in mode and "MANUAL" not in mode:
                    errors.append(
                        f"{prefix}/{source_id}: CAPTCHA source must remain "
                        "manual/explicitly non-automated"
                    )

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
                "first_wave_cities": len(seen),
                "federal_sources": len(resolver.get("federal", [])),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
