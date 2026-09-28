#!/usr/bin/env python3
"""Local resolver for IBGE 2022 census-sector mesh with basic attributes."""
from __future__ import annotations

from pathlib import Path
from threading import Lock

from osgeo import ogr

CACHE_DIR = Path("/var/cache/lotediretor/ibge")
SUPPORTED = {
    "3550308": "São Paulo",
    "2611606": "Recife",
    "3304557": "Rio de Janeiro",
    "3106200": "Belo Horizonte",
    "2507507": "João Pessoa",
}
FIELDS = [
    "CD_SETOR", "SITUACAO", "CD_SIT", "CD_TIPO", "AREA_KM2",
    "CD_MUN", "NM_MUN", "CD_DIST", "NM_DIST", "CD_SUBDIST", "NM_SUBDIST",
    "CD_BAIRRO", "NM_BAIRRO", "v0001", "v0002", "v0003", "v0004",
    "v0005", "v0006", "v0007",
]
_LOCK = Lock()


def _path(municipality_ibge: str) -> Path:
    return CACHE_DIR / f"{municipality_ibge}_setores_CD2022.gpkg"


def lookup(municipality_ibge: str, lat: float, lng: float) -> dict:
    if municipality_ibge not in SUPPORTED:
        return {"available": False, "reason": "unsupported_municipality"}
    path = _path(municipality_ibge)
    if not path.exists():
        return {
            "available": False,
            "reason": "sector_cache_not_materialized",
            "expected_path": str(path),
        }

    # OGR drivers are process-global. Keep the tiny point lookup serialized.
    with _LOCK:
        ds = ogr.Open(str(path), 0)
        if ds is None:
            return {"available": False, "reason": "sector_cache_open_failed"}
        layer = ds.GetLayerByName("setores")
        if layer is None:
            return {"available": False, "reason": "sector_layer_missing"}
        layer.SetAttributeFilter(f"CD_MUN='{municipality_ibge}'")
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint(float(lng), float(lat))
        layer.SetSpatialFilter(point)
        rows = []
        for feature in layer:
            rows.append({
                field: feature.GetField(field)
                for field in FIELDS
                if feature.GetFieldIndex(field) >= 0
                and feature.GetField(field) is not None
            })
        layer.SetSpatialFilter(None)
        layer.SetAttributeFilter(None)
        ds = None

    if not rows:
        return {"available": False, "reason": "sector_not_found_at_point"}
    # Boundaries may touch more than one sector. Prefer the first returned
    # polygon and preserve the ambiguity count rather than inventing certainty.
    row = rows[0]
    return {
        "available": True,
        "match_count": len(rows),
        "sector_code": row.get("CD_SETOR"),
        "situation": row.get("SITUACAO"),
        "sector_area_km2": row.get("AREA_KM2"),
        "municipality_ibge": row.get("CD_MUN"),
        "municipality_name": row.get("NM_MUN"),
        "district_code": row.get("CD_DIST"),
        "district_name": row.get("NM_DIST"),
        "subdistrict_code": row.get("CD_SUBDIST"),
        "subdistrict_name": row.get("NM_SUBDIST"),
        "neighborhood_code": row.get("CD_BAIRRO"),
        "neighborhood_name": row.get("NM_BAIRRO"),
        "population": row.get("v0001"),
        "households_total": row.get("v0002"),
        "private_households_total": row.get("v0003"),
        "collective_households_total": row.get("v0004"),
        "avg_residents_occupied_private_households": row.get("v0005"),
        "imputed_occupied_private_households_pct": row.get("v0006"),
        "occupied_private_households": row.get("v0007"),
        "source": "IBGE · Malha de Setores Censitários 2022 com atributos básicos",
        "interpretation": (
            "Indicadores do Censo 2022 no setor censitário que contém o ponto "
            "consultado. São contexto estatístico local e não atributos "
            "cadastrais, fiscais ou jurídicos do terreno."
        ),
    }


def report_values(context: dict) -> list[dict]:
    if not (context or {}).get("available"):
        return []
    values = [
        ("Setor censitário 2022", context.get("sector_code"), None),
        ("Situação do setor censitário", context.get("situation"), None),
        ("Bairro do setor censitário", context.get("neighborhood_name"), None),
        ("Distrito do setor censitário", context.get("district_name"), None),
        ("População do setor · Censo 2022", context.get("population"), "pessoas"),
        ("Domicílios no setor · Censo 2022", context.get("households_total"), "domicílios"),
        ("Domicílios particulares no setor · Censo 2022", context.get("private_households_total"), "domicílios"),
        ("Domicílios coletivos no setor · Censo 2022", context.get("collective_households_total"), "domicílios"),
        ("Domicílios particulares ocupados · Censo 2022", context.get("occupied_private_households"), "domicílios"),
        ("Média de moradores em domicílios particulares ocupados · Censo 2022", context.get("avg_residents_occupied_private_households"), "pessoas"),
        ("Percentual de domicílios particulares ocupados imputados · Censo 2022", context.get("imputed_occupied_private_households_pct"), "%"),
        ("Área do setor censitário", context.get("sector_area_km2"), "km²"),
    ]
    out = [
        {"label": label, "value": value, **({"unit": unit} if unit else {})}
        for label, value, unit in values
        if value not in (None, "")
    ]
    out.append({
        "label": "Limite do contexto censitário",
        "value": context.get("interpretation"),
    })
    if (context or {}).get("match_count", 1) > 1:
        out.append({
            "label": "Observação do setor censitário",
            "value": (
                "O ponto consultado toca mais de uma geometria setorial. "
                "A leitura deve ser confirmada quando a posição estiver sobre "
                "um limite de setor."
            ),
        })
    return out
