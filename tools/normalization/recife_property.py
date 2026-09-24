#!/usr/bin/env python3
"""Normalize approved Recife CKAN property datasets into NDJSON."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FORBIDDEN_KEY = re.compile(
    r"(cpf|cnpj|razao_social|propriet|requerente|titular|email|telefone)",
    re.IGNORECASE,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe_point(record: dict):
    lat = record.get("latitude")
    lon = record.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"type": "Point", "coordinates": [lon, lat]}


def ensure_safe(record: dict, manifest: dict) -> None:
    allowlist = set(manifest["field_allowlist"])
    if set(record) != allowlist:
        raise ValueError(
            "record field set differs from closed allowlist; "
            f"missing={sorted(allowlist - set(record))}, "
            f"extra={sorted(set(record) - allowlist)}"
        )
    forbidden = [key for key in record if FORBIDDEN_KEY.search(key)]
    if forbidden:
        raise ValueError(
            "person/business identity field rejected: "
            + ", ".join(sorted(forbidden))
        )


def base(record: dict, manifest: dict) -> dict:
    row_id = record.get("_id")
    if row_id is None:
        raise ValueError("CKAN _id is required for snapshot row lineage")
    return {
        "schema_version": "0.1.0",
        "source_id": manifest["source_id"],
        "connector_id": manifest["connector_id"],
        "dataset_key": manifest["dataset_key"],
        "resource_id": manifest["resource_id"],
        "upstream_key": f"{manifest['resource_id']}:{row_id}",
        "municipality_ibge": manifest["municipality_ibge"],
        "captured_at": manifest["captured_at"],
        "license": manifest["license"],
        "public_release_allowed": True,
        "location": safe_point(record),
    }


def normalize_iptu(record: dict, manifest: dict) -> dict:
    out = base(record, manifest)
    out.update(
        {
            "record_kind": "FISCAL_PROPERTY",
            "identity": {
                "municipal_tax_reference": record.get("Número do contribuinte"),
                "street_code": record.get("Código Logradouro"),
            },
            "tax_year": record.get("ano do exercício"),
            "registered_at": record.get("data do cadastramento"),
            "address": {
                "street": record.get("logradouro"),
                "number": record.get("numero"),
                "complement": record.get("complemento"),
                "neighborhood": record.get("bairro"),
                "city": record.get("cidade"),
                "state": record.get("estado"),
                "postal_code": record.get("CEP"),
            },
            "land": {
                "source_land_area_m2": record.get("AREA TERRENO"),
                "ideal_fraction": record.get("fração ideal"),
            },
            "building": {
                "source_built_area_m2": record.get("AREA CONSTRUIDA"),
                "occupied_area_m2": record.get("área ocupada"),
                "construction_year_corrected": record.get(
                    "ano da construção corrigido"
                ),
                "floors": record.get("quantidade de pavimentos"),
                "use": record.get("tipo de uso do imóvel"),
                "construction_standard": record.get(
                    "tipo de padrão da construção"
                ),
                "construction_type": record.get("Tipo de Construção"),
                "enterprise_type": record.get("Tipo de Empreendimento"),
                "structure_type": record.get("Tipo de Estrutura"),
                "obsolescence_factor": record.get("fator de obsolescência"),
            },
            "fiscal": {
                "land_unit_value_brl_m2": record.get(
                    "valor do m2 do terreno"
                ),
                "building_unit_value_brl_m2": record.get(
                    "valor do m2 de construção"
                ),
                "estimated_total_value_brl": record.get(
                    "valor total do imóvel estimado"
                ),
                "iptu_charged_brl": record.get("valor cobrado de IPTU"),
                "iptu_tax_regime": record.get(
                    "Regime de Tributação do iptu"
                ),
                "trsd_tax_regime": record.get(
                    "Regime de Tributação da trsd"
                ),
                "contribution_start_yyyymm": record.get(
                    "ano e mês de início da contribuição"
                ),
            },
            "raw_allowlisted_properties": record,
        }
    )
    return out


def normalize_itbi(record: dict, manifest: dict) -> dict:
    out = base(record, manifest)
    out.update(
        {
            "record_kind": "PROPERTY_TRANSACTION",
            "transaction": {
                "date": record.get("data_transacao"),
                "year": record.get("ano"),
                "assessed_value_brl": record.get("valor_avaliacao"),
                "sfh": record.get("sfh"),
            },
            "address": {
                "street_code": record.get("cod_logradouro"),
                "street": record.get("logradouro"),
                "number": record.get("numero"),
                "complement": record.get("complemento"),
                "neighborhood": record.get("bairro"),
                "city": record.get("cidade"),
                "state": record.get("uf"),
            },
            "property_attributes": {
                "construction_year": record.get("ano_construcao"),
                "land_area_m2": record.get("area_terreno"),
                "built_area_m2": record.get("area_construida"),
                "ideal_fraction": record.get("fracao_ideal"),
                "finish_standard": record.get("padrao_acabamento"),
                "construction_type": record.get("tipo_construcao"),
                "occupancy_type": record.get("tipo_ocupacao"),
                "conservation_state": record.get("estado_conservacao"),
                "property_type": record.get("tipo_imovel"),
            },
            "match": {
                "method": (
                    "OFFICIAL_ADDRESS_AND_COORDINATE"
                    if out["location"] is not None
                    else "OFFICIAL_ADDRESS"
                ),
                "confidence": "SUPPORTED",
                "notes": (
                    "Transaction does not carry a municipal parcel identifier "
                    "in the observed schema; property reconciliation must use "
                    "official address/coordinate context and remain probabilistic "
                    "until matched to an official parcel."
                ),
            },
            "raw_allowlisted_properties": record,
        }
    )
    return out


def normalize_licensing(record: dict, manifest: dict) -> dict:
    out = base(record, manifest)
    out.update(
        {
            "record_kind": "PERMIT_EVENT",
            "permit": {
                "license_number": record.get("num_licenca"),
                "process_number": record.get("num_processo"),
                "subject": record.get("assunto"),
                "process_type": record.get("tipo_processo"),
                "licensing_process_type": record.get(
                    "tipo_proc_licenciamento"
                ),
                "process_status": record.get("situacao_processo"),
                "automated_process": record.get("processo_automatizado"),
                "entry_date": record.get("data_entrada"),
                "license_issue_date": record.get("data_emissao_licenca"),
                "license_valid_until": record.get("data_validade_licenca"),
                "completion_date": record.get("data_conclusao"),
            },
            "project": {
                "address": record.get("endereco_empreendimento"),
                "neighborhood": record.get("bairro"),
                "fiscal_location_reference": record.get("dsqfl"),
                "total_built_area_m2": record.get("﻿areatotalconstruida"),
                "category": record.get("categoria_empreendimento"),
                "impact_project": record.get("empreendimento_de_impacto"),
                "size": record.get("porte_empreendimento"),
                "potential": record.get("potencial_empreendimento"),
                "property_use": record.get("uso_imovel"),
            },
            "parallel_licensing": {
                "urban": record.get("licenciamento_urbanistico"),
                "environmental": record.get("licenciamento_ambiental"),
                "sanitary": record.get("licenciamento_sanitario"),
            },
            "raw_allowlisted_properties": record,
        }
    )
    return out


NORMALIZERS = {
    "iptu_2026": normalize_iptu,
    "itbi_2026": normalize_itbi,
    "licenciamento": normalize_licensing,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest = load_json(args.snapshot_dir / "manifest.json")
    dataset_key = manifest.get("dataset_key")
    if dataset_key not in NORMALIZERS:
        raise SystemExit(f"unsupported Recife dataset_key={dataset_key!r}")
    if not manifest.get("complete"):
        raise SystemExit(
            "snapshot is incomplete; complete materialization is required "
            "before normalization"
        )

    normalize = NORMALIZERS[dataset_key]
    output_records = 0
    input_records = 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for page in manifest.get("pages", []):
            payload = load_json(args.snapshot_dir / page["raw_file"])
            records = payload.get("result", {}).get("records")
            if not isinstance(records, list):
                raise SystemExit(f"{page['raw_file']}: records array missing")
            for record in records:
                input_records += 1
                ensure_safe(record, manifest)
                normalized = normalize(record, manifest)
                handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
                output_records += 1

    if input_records != manifest.get("number_returned"):
        raise SystemExit(
            f"manifest number_returned={manifest.get('number_returned')} "
            f"but read {input_records} records"
        )

    print(
        json.dumps(
            {
                "dataset_key": dataset_key,
                "input_records": input_records,
                "normalized_records": output_records,
                "output": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
