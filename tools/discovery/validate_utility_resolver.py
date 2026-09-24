#!/usr/bin/env python3
"""Validate the first-wave municipality -> utility provider resolver.

The validator is intentionally offline. It checks structural invariants and
cross-references every provider/technical source against the source registry.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/source-registry/bootstrap.json"
RESOLVER = ROOT / "data/utilities/municipality-provider-resolver.json"

REQUIRED_MUNICIPALITIES = {
    "3550308": "São Paulo",
    "2611606": "Recife",
    "3304557": "Rio de Janeiro",
    "3106200": "Belo Horizonte",
    "2507507": "João Pessoa",
}
REQUIRED_SERVICES = {
    "electricity",
    "gas",
    "water_sewer",
    "telecom",
    "drainage",
    "public_lighting",
}
EVIDENCE_LEVELS = {
    "PROVIDER_TERRITORY_ONLY",
    "NETWORK_CONTEXT",
    "PARCEL_AVAILABILITY",
    "SUBMUNICIPAL_REQUIRED",
}
TERRITORY_TYPES = {"MUNICIPALITY", "SUBMUNICIPAL"}


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    resolver = json.loads(RESOLVER.read_text(encoding="utf-8"))

    source_ids = {source["id"] for source in registry["sources"]}
    errors: list[str] = []
    warnings: list[str] = []

    if resolver.get("schema_version") != "0.1.0":
        errors.append("resolver schema_version must be 0.1.0")

    municipalities = resolver.get("municipalities")
    if not isinstance(municipalities, list):
        errors.append("municipalities must be an array")
        municipalities = []

    seen_municipalities: set[str] = set()
    for municipality in municipalities:
        ibge = str(municipality.get("ibge", ""))
        prefix = f"{ibge or '?'}:{municipality.get('city', '?')}"

        if ibge in seen_municipalities:
            errors.append(f"{prefix}: duplicate municipality")
        seen_municipalities.add(ibge)

        if ibge not in REQUIRED_MUNICIPALITIES:
            warnings.append(f"{prefix}: municipality is outside first wave")
        elif municipality.get("city") != REQUIRED_MUNICIPALITIES[ibge]:
            errors.append(
                f"{prefix}: city name does not match expected "
                f"{REQUIRED_MUNICIPALITIES[ibge]!r}"
            )

        services = municipality.get("services")
        if not isinstance(services, dict):
            errors.append(f"{prefix}: services must be an object")
            continue

        missing_services = REQUIRED_SERVICES - set(services)
        extra_services = set(services) - REQUIRED_SERVICES
        if missing_services:
            errors.append(
                f"{prefix}: missing services {sorted(missing_services)}"
            )
        if extra_services:
            warnings.append(
                f"{prefix}: extra services {sorted(extra_services)}"
            )

        for service_type in REQUIRED_SERVICES:
            entries = services.get(service_type, [])
            service_prefix = f"{prefix}:{service_type}"
            if not isinstance(entries, list) or not entries:
                errors.append(f"{service_prefix}: provider list must be non-empty")
                continue

            for idx, entry in enumerate(entries):
                ep = f"{service_prefix}[{idx}]"
                provider_source_id = entry.get("provider_source_id")
                if provider_source_id not in source_ids:
                    errors.append(
                        f"{ep}: unknown provider_source_id={provider_source_id!r}"
                    )

                technical_source_ids = entry.get("technical_source_ids")
                if not isinstance(technical_source_ids, list) or not technical_source_ids:
                    errors.append(f"{ep}: technical_source_ids must be non-empty")
                else:
                    for source_id in technical_source_ids:
                        if source_id not in source_ids:
                            errors.append(
                                f"{ep}: unknown technical source {source_id!r}"
                            )

                level = entry.get("evidence_level")
                if level not in EVIDENCE_LEVELS:
                    errors.append(f"{ep}: invalid evidence_level={level!r}")

                territory = entry.get("territory")
                if not isinstance(territory, dict):
                    errors.append(f"{ep}: territory must be an object")
                    continue

                territory_type = territory.get("type")
                if territory_type not in TERRITORY_TYPES:
                    errors.append(
                        f"{ep}: invalid territory.type={territory_type!r}"
                    )
                if territory_type == "MUNICIPALITY":
                    if str(territory.get("value", "")) != ibge:
                        errors.append(
                            f"{ep}: municipality territory must match {ibge}"
                        )
                if territory_type == "SUBMUNICIPAL":
                    if not (
                        territory.get("description")
                        or territory.get("neighborhoods")
                    ):
                        errors.append(
                            f"{ep}: submunicipal territory needs description "
                            "or neighborhoods"
                        )
                    if level != "SUBMUNICIPAL_REQUIRED":
                        errors.append(
                            f"{ep}: submunicipal territory must use "
                            "SUBMUNICIPAL_REQUIRED evidence level"
                        )

                if level == "PARCEL_AVAILABILITY":
                    warnings.append(
                        f"{ep}: PARCEL_AVAILABILITY requires a property-specific "
                        "official query/document and should be reviewed manually"
                    )

    missing_municipalities = set(REQUIRED_MUNICIPALITIES) - seen_municipalities
    if missing_municipalities:
        errors.append(
            "missing first-wave municipalities: "
            + ", ".join(sorted(missing_municipalities))
        )

    rio = next(
        (item for item in municipalities if str(item.get("ibge")) == "3304557"),
        None,
    )
    if rio:
        water_entries = rio.get("services", {}).get("water_sewer", [])
        if len(water_entries) < 2:
            errors.append(
                "Rio de Janeiro water_sewer must preserve multiple "
                "submunicipal concession territories"
            )
        if not all(
            entry.get("territory", {}).get("type") == "SUBMUNICIPAL"
            for entry in water_entries
        ):
            errors.append(
                "Rio de Janeiro water_sewer entries must be SUBMUNICIPAL"
            )

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        json.dumps(
            {
                "ok": not errors,
                "municipalities": len(municipalities),
                "services_per_municipality": len(REQUIRED_SERVICES),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
