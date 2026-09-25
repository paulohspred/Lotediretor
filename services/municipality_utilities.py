#!/usr/bin/env python3
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path("/srv/lotediretor/app")
RESOLVER = ROOT / "data/utilities/municipality-provider-resolver.json"
REGISTRY = ROOT / "data/source-registry/bootstrap.json"

SERVICE_LABELS = {
    "electricity": "Energia elétrica",
    "gas": "Gás canalizado",
    "water_sewer": "Água e esgoto",
    "telecom": "Telecom",
    "drainage": "Drenagem",
    "public_lighting": "Iluminação pública",
}


@lru_cache(maxsize=1)
def _data():
    resolver = json.loads(RESOLVER.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    source_map = {item["id"]: item for item in registry["sources"]}
    return resolver, source_map


def load(ibge: str) -> dict:
    resolver, source_map = _data()
    city = next(
        (item for item in resolver["municipalities"] if item.get("ibge") == ibge),
        None,
    )
    if not city:
        return {}
    output = {}
    for service_type, entries in city.get("services", {}).items():
        normalized = []
        for entry in entries:
            source_id = entry.get("provider_source_id")
            source = source_map.get(source_id) or {}
            normalized.append(
                {
                    "service_type": service_type,
                    "provider_source_id": source_id,
                    "provider_authority": source.get("authority") or source_id,
                    "role": entry.get("role"),
                    "evidence_level": entry.get("evidence_level"),
                    "technical_source_ids": entry.get("technical_source_ids") or [],
                    "missing": entry.get("missing") or [],
                    "caveat": entry.get("caveat") or entry.get("note"),
                }
            )
        output[service_type] = normalized
    return output


def report_values(utilities: dict) -> list[dict]:
    values = []
    for service_type in [
        "electricity",
        "gas",
        "water_sewer",
        "telecom",
        "drainage",
        "public_lighting",
    ]:
        for entry in utilities.get(service_type) or []:
            label = SERVICE_LABELS.get(service_type, service_type)
            provider = entry.get("provider_authority") or entry.get("provider_source_id")
            values.extend(
                [
                    {"label": f"{label} · referência", "value": provider},
                    {
                        "label": f"{label} · evidência",
                        "value": entry.get("evidence_level"),
                    },
                ]
            )
    values.append(
        {
            "label": "Limite de interpretação",
            "value": (
                "Prestador, área de concessão ou contexto de rede não comprovam "
                "ligação, disponibilidade nem capacidade técnica no lote."
            ),
        }
    )
    return values
