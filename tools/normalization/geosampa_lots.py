#!/usr/bin/env python3
"""Normalize allowlisted GeoSampa parcel snapshots into parcel NDJSON.

The output is an intermediate import contract for Phase H/I. It preserves the
source CRS and does not flatten parcel geometry into a condominium/fiscal unit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FORBIDDEN_KEY = re.compile(
    r"(propriet|cpf|cnpj|requerente|titular|email|telefone)",
    re.IGNORECASE,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sql_reference(props: dict) -> str | None:
    sector = props.get("cd_setor_fiscal")
    block = props.get("cd_quadra_fiscal")
    lot = props.get("cd_lote")
    digit = props.get("cd_digito_sql")
    condominium = props.get("cd_condominio")

    # The official lot layer documents lote 0000 as condominium records. In
    # those cases one polygon can relate to multiple fiscal units, so a unit SQL
    # must not be fabricated from the parcel row.
    if not all(isinstance(value, str) and value for value in [sector, block, lot, digit]):
        return None
    if lot == "0000":
        return None
    if condominium not in {None, "", "00"}:
        return None
    return f"{sector}{block}{lot}{digit}"


def sqcd_reference(props: dict) -> str | None:
    sector = props.get("cd_setor_fiscal")
    block = props.get("cd_quadra_fiscal")
    condominium = props.get("cd_condominio")
    if not all(
        isinstance(value, str) and value
        for value in [sector, block, condominium]
    ):
        return None
    if condominium == "00":
        return None
    return f"{sector}{block}{condominium}"


def ensure_safe_properties(props: dict, allowlist: set[str]) -> None:
    unexpected = set(props) - allowlist
    if unexpected:
        raise ValueError(
            "unexpected field(s) outside materialization allowlist: "
            + ", ".join(sorted(unexpected))
        )
    forbidden = [key for key in props if FORBIDDEN_KEY.search(key)]
    if forbidden:
        raise ValueError(
            "person-centric field rejected by normalization policy: "
            + ", ".join(sorted(forbidden))
        )


def normalize(feature: dict, manifest: dict) -> dict:
    props = feature.get("properties") or {}
    allowlist = set(manifest["field_allowlist"])
    ensure_safe_properties(props, allowlist)

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise ValueError("parcel feature must contain Polygon/MultiPolygon geometry")

    upstream_key = feature.get("id")
    if not isinstance(upstream_key, str) or not upstream_key:
        raise ValueError("parcel feature id is required")

    sector = props.get("cd_setor_fiscal")
    expected_sector = manifest["partition"]["value"]
    if sector != expected_sector:
        raise ValueError(
            f"feature sector {sector!r} does not match manifest {expected_sector!r}"
        )

    sql = sql_reference(props)
    sqcd = sqcd_reference(props)

    identifiers = {
        "municipal_parcel_feature_id": str(props.get("cd_identificador"))
        if props.get("cd_identificador") is not None
        else None,
        "municipal_original_parcel_id": str(
            props.get("cd_identificador_original_lote")
        )
        if props.get("cd_identificador_original_lote") is not None
        else None,
        "fiscal_sector": props.get("cd_setor_fiscal"),
        "fiscal_block": props.get("cd_quadra_fiscal"),
        "fiscal_subblock": props.get("cd_subquadra_fiscal"),
        "fiscal_lot": props.get("cd_lote"),
        "fiscal_sql_digit": props.get("cd_digito_sql"),
        "condominium_code": props.get("cd_condominio"),
        "sql_reference": sql,
        "sqcd_reference": sqcd,
        "cib": props.get("cd_cib"),
        "cib_status": props.get("tx_situacao_cib"),
    }

    return {
        "schema_version": "0.1.0",
        "record_kind": "URBAN_PARCEL",
        "source_id": manifest["source_id"],
        "connector_id": manifest["connector_id"],
        "upstream_key": upstream_key,
        "municipality_ibge": manifest["municipality_ibge"],
        "captured_at": manifest["captured_at"],
        "source_crs": manifest["source_crs"],
        "public_release_allowed": True,
        "identity": identifiers,
        "address": {
            "street_code": props.get("cd_logradouro"),
            "street": props.get("nm_logradouro_completo"),
            "number": props.get("cd_numero_porta"),
            "complement": props.get("tx_complemento_endereco"),
        },
        "land": {
            "source_land_area_m2": props.get("qt_area_terreno"),
            "parcel_type_code": props.get("cd_tipo_lote"),
            "parcel_type": props.get("tx_tipo_lote"),
            "block_type_code": props.get("cd_tipo_quadra"),
            "block_type": props.get("tx_tipo_quadra"),
            "parcel_status_code": props.get("cd_situacao"),
            "parcel_status": props.get("tx_situ_lote"),
            "terrain_type_code": props.get("cd_tipo_terreno_imovel"),
        },
        "building_context": {
            "fiscal_built_area_m2": props.get("qt_area_construida"),
            "use_code": props.get("cd_tipo_uso_imovel"),
            "use_description": props.get("dc_tipo_uso_imovel"),
            "note": (
                "Fiscal cadastral building context attached to the parcel row; "
                "it is not a building-footprint geometry."
            ),
        },
        "geometry": geometry,
        "raw_allowlisted_properties": props,
        "warnings": (
            [
                "Condominium parcel geometry does not identify an individual fiscal unit; SQL unit reference was intentionally not generated."
            ]
            if sql is None
            and (
                props.get("cd_lote") == "0000"
                or props.get("cd_condominio") not in {None, "", "00"}
            )
            else []
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.snapshot_dir / "manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("source_id") != "sp-sao-paulo-geosampa-wfs":
        raise SystemExit("snapshot source is not the approved GeoSampa WFS source")
    if manifest.get("layer") != "geoportal:lote_cidadao":
        raise SystemExit("snapshot layer is not geoportal:lote_cidadao")
    if not manifest.get("complete"):
        raise SystemExit(
            "snapshot is incomplete; rerun materialization before normalization"
        )

    events = []
    input_features = 0
    for page in manifest.get("pages", []):
        raw_path = args.snapshot_dir / page["raw_file"]
        payload = load_json(raw_path)
        features = payload.get("features")
        if not isinstance(features, list):
            raise SystemExit(f"{raw_path}: features array missing")
        input_features += len(features)
        for feature in features:
            events.append(normalize(feature, manifest))

    if input_features != manifest.get("number_returned"):
        raise SystemExit(
            f"manifest number_returned={manifest.get('number_returned')} "
            f"but read {input_features} features"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "source_id": manifest["source_id"],
                "sector": manifest["partition"]["value"],
                "input_features": input_features,
                "normalized_records": len(events),
                "output": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
