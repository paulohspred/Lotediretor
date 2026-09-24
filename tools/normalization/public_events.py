#!/usr/bin/env python3
"""Normalize ObrasGov and PNCP snapshots into LoteDiretor public events.

This module deliberately avoids parcel matching from vague text. PNCP
publications remain unresolved until another official identifier, geometry,
address or document creates a defensible property relationship.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def stable_event_id(source_id: str, source_event_id: str, event_type: str) -> str:
    material = f"{source_id}|{source_event_id}|{event_type}".encode("utf-8")
    return "evt_" + hashlib.sha256(material).hexdigest()[:24]


def nested(record: dict, *path):
    value = record
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def clean_date(value):
    if not isinstance(value, str) or not value:
        return None
    return value[:10]


def clean_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    return value


def manifest_context(manifest: dict, raw_file: Path) -> dict:
    page = None
    for item in manifest.get("pages", []):
        if item.get("raw_file") == raw_file.name:
            page = item
            break
    return {
        "captured_at": manifest.get("captured_at") or iso_now(),
        "source_url": (page or {}).get("final_url")
        or (page or {}).get("requested_url"),
        "snapshot_sha256": (page or {}).get("sha256"),
        "query": manifest.get("query") or manifest.get("filters") or {},
        "source_updated_at": manifest.get("source_updated_at"),
    }


def obrasgov_event(record: dict, ctx: dict) -> dict | None:
    project_id = record.get("id_projeto_investimento")
    if not project_id:
        return None

    status = record.get("situacao")
    mapping = {
        "Cadastrada": ("PROJECT_PLANNED", "PLANNED"),
        "Em execução": ("WORK_STARTED", "EXECUTION"),
        "Paralisada": ("WORK_PAUSED", "EXECUTION"),
        "Concluída": ("WORK_COMPLETED", "COMPLETED"),
        "Cancelada": ("CANCELLED", "CANCELLED"),
        "Inacabada": ("OTHER", "UNKNOWN"),
    }
    event_type, lifecycle = mapping.get(status, ("OTHER", "UNKNOWN"))

    address = record.get("desc_endereco")
    match = {
        "method": "OFFICIAL_ADDRESS" if address else "UNRESOLVED",
        "confidence": "SUPPORTED" if address else "UNKNOWN",
        "distance_m": None,
        "notes": (
            "Address comes from the ObrasGov project record and is not yet "
            "parcel-resolved."
            if address
            else "No property-level relationship established."
        ),
    }

    source_event_id = str(project_id)
    source_url = ctx.get("source_url") or (
        "https://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento"
    )
    return {
        "schema_version": "0.1.0",
        "event_id": stable_event_id(
            "br-obrasgov-api", source_event_id, event_type
        ),
        "event_type": event_type,
        "lifecycle_stage": lifecycle,
        "title": record.get("desc_nome"),
        "summary": record.get("desc_projeto") or record.get("desc_meta_global"),
        "source_id": "br-obrasgov-api",
        "source_event_id": source_event_id,
        "authority": record.get("organizacao_resp") or "ObrasGov.br",
        "access_class": "OPEN_REUSABLE",
        "municipality_ibge": None,
        "event_date": clean_date(
            record.get("dt_inicial_efetiva")
            or record.get("dt_inicial_prevista")
            or record.get("dt_cadastro")
        ),
        "published_at": None,
        "valid_from": None,
        "valid_to": clean_date(
            record.get("dt_final_efetiva") or record.get("dt_final_prevista")
        ),
        "status_text": status,
        "progress_percent": None,
        "planned_value_brl": None,
        "executed_value_brl": None,
        "responsible_organization": record.get("organizacao_resp"),
        "location": {
            "address": address,
            "latitude": None,
            "longitude": None,
            "geometry": None,
            "geometry_crs": None,
        },
        "identifiers": {
            "obrasgov_project_id": source_event_id,
            "pncp_control_number": None,
            "process_number": None,
            "permit_number": None,
            "gazette_edition": None,
            "legal_act_id": None,
            "property_public_ids": [],
        },
        "document_urls": [],
        "related_event_ids": [],
        "match": match,
        "captured_at": ctx["captured_at"],
        "provenance": {
            "source_url": source_url,
            "document_id": source_event_id,
            "snapshot_sha256": ctx.get("snapshot_sha256"),
            "parser_version": "public_events.py/0.1.0",
            "license": None,
            "source_updated_at": ctx.get("source_updated_at"),
            "notes": "Normalized from ObrasGov public API snapshot.",
        },
        "warnings": [
            "Project address or municipality context does not by itself prove "
            "intersection with a parcel."
        ],
    }


def pncp_event(record: dict, ctx: dict) -> dict | None:
    control = record.get("numeroControlePNCP")
    if not control:
        return None

    query = ctx.get("query") or {}
    municipality = query.get("codigoMunicipioIbge")
    authority = (
        nested(record, "orgaoEntidade", "razaoSocial")
        or record.get("orgaoEntidadeRazaoSocial")
        or "PNCP"
    )
    publication = (
        record.get("dataPublicacaoPncp")
        or record.get("dataPublicacaoPNCP")
    )
    process_number = record.get("processo") or record.get("numeroProcesso")

    source_event_id = str(control)
    source_url = ctx.get("source_url") or (
        "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
    )
    return {
        "schema_version": "0.1.0",
        "event_id": stable_event_id(
            "br-pncp-open-api", source_event_id, "PROCUREMENT_PUBLISHED"
        ),
        "event_type": "PROCUREMENT_PUBLISHED",
        "lifecycle_stage": "PROCUREMENT",
        "title": record.get("objetoCompra"),
        "summary": record.get("informacaoComplementar"),
        "source_id": "br-pncp-open-api",
        "source_event_id": source_event_id,
        "authority": authority,
        "access_class": "OPEN_REUSABLE",
        "municipality_ibge": municipality,
        "event_date": clean_date(publication),
        "published_at": clean_datetime(publication),
        "valid_from": None,
        "valid_to": None,
        "status_text": record.get("situacaoCompraNome"),
        "progress_percent": None,
        "planned_value_brl": record.get("valorTotalEstimado"),
        "executed_value_brl": None,
        "responsible_organization": authority,
        "location": None,
        "identifiers": {
            "obrasgov_project_id": None,
            "pncp_control_number": source_event_id,
            "process_number": str(process_number) if process_number else None,
            "permit_number": None,
            "gazette_edition": None,
            "legal_act_id": None,
            "property_public_ids": [],
        },
        "document_urls": [],
        "related_event_ids": [],
        "match": {
            "method": "UNRESOLVED",
            "confidence": "UNKNOWN",
            "distance_m": None,
            "notes": (
                "Municipality filter refers to the administrative unit of the "
                "procurement and must not be treated as project/property location."
            ),
        },
        "captured_at": ctx["captured_at"],
        "provenance": {
            "source_url": source_url,
            "document_id": source_event_id,
            "snapshot_sha256": ctx.get("snapshot_sha256"),
            "parser_version": "public_events.py/0.1.0",
            "license": None,
            "source_updated_at": None,
            "notes": "Normalized from PNCP public consultation snapshot.",
        },
        "warnings": [
            "Do not attach this procurement to a parcel from object text alone.",
            "Supplier/person identity is not used for property discovery.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        choices=["obrasgov-projects", "pncp-publications"],
    )
    parser.add_argument("raw", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Defaults to manifest.json beside the raw page.",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    raw = load_json(args.raw)
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
        raise SystemExit("raw input must contain a data array")

    manifest_path = args.manifest or args.raw.with_name("manifest.json")
    manifest = load_json(manifest_path)
    ctx = manifest_context(manifest, args.raw)

    normalizer = (
        obrasgov_event
        if args.source == "obrasgov-projects"
        else pncp_event
    )
    events = []
    skipped = 0
    for record in raw["data"]:
        if not isinstance(record, dict):
            skipped += 1
            continue
        event = normalizer(record, ctx)
        if event is None:
            skipped += 1
            continue
        events.append(event)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "source": args.source,
                "input_records": len(raw["data"]),
                "events": len(events),
                "skipped": skipped,
                "output": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
