"""PostGIS-backed national restriction context (Phase 6)."""
from __future__ import annotations

import json
import os
from datetime import datetime

import psycopg2

DB_DSN = os.environ.get(
    "LOTEDIRETOR_DB_DSN",
    "dbname=lotediretor user=sentinelx host=/var/run/postgresql",
)
MAX_DISTANCE_M = float(os.environ.get("LOTEDIRETOR_RESTRICTION_DISTANCE_M", "5000"))

THEME_LABELS = {
    "INDIGENOUS_LAND": "Terra indígena",
    "CONSERVATION_UNIT": "Unidade de conservação",
    "MINING_PROCESS": "Processo minerário",
    "HYDROGRAPHY": "Hidrografia",
    "HYDROGRAPHIC_BASIN": "Bacia hidrográfica",
    "DEFORESTATION": "PRODES/DETER",
    "TRANSMISSION_LINE": "Linha de transmissão",
    "SUBSTATION": "Subestação",
    "CULTURAL_HERITAGE": "Patrimônio cultural",
    "GEOLOGY": "Geologia",
    "GEOLOGICAL_RISK": "Risco geológico",
}

STATUS_LABELS = {
    "NOT_LOADED": "não carregada",
    "NOT_AVAILABLE_SPATIAL": "sem geometria reutilizável",
    "SOURCE_UNAVAILABLE": "fonte indisponível",
    "FAILED_VALIDATION": "falhou na validação",
}


def unavailable_labels(context: dict) -> list[str]:
    out = []
    for item in context.get("unavailable") or []:
        theme = THEME_LABELS.get(item.get("theme"), item.get("layer_key", "Camada nacional"))
        status = STATUS_LABELS.get(item.get("status"), str(item.get("status") or "indisponível").lower())
        authority = item.get("authority")
        out.append(f"{theme} · {authority} ({status})" if authority else f"{theme} ({status})")
    return out


def _date(value) -> str:
    if value is None:
        return "data não informada"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def query_geometry(geometry: dict, max_distance_m: float = MAX_DISTANCE_M) -> dict:
    with psycopg2.connect(DB_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT layer_key, theme, authority, source_url, license,
                      source_updated_at, loaded_at, upstream_key, label, category,
                      intersects, distance_m, attributes
               FROM ld_api.restrictions_for_geometry(
                    ST_SetSRID(ST_GeomFromGeoJSON(%s), 4674), %s
               )""",
            (json.dumps(geometry, ensure_ascii=False), max_distance_m),
        )
        rows = cur.fetchall()
        cur.execute(
            """SELECT layer_key, theme, authority, source_url, status, loaded_at, notes
               FROM ld_core.restriction_layer
               ORDER BY theme, layer_key"""
        )
        layers = cur.fetchall()

    hits = [
        {
            "layer_key": row[0],
            "theme": row[1],
            "authority": row[2],
            "source_url": row[3],
            "license": row[4],
            "source_updated_at": _date(row[5]),
            "loaded_at": _date(row[6]),
            "upstream_key": row[7],
            "label": row[8],
            "category": row[9],
            "intersects": bool(row[10]),
            "distance_m": round(float(row[11]), 1),
            "attributes": row[12] or {},
        }
        for row in rows
    ]
    unavailable = [
        {
            "layer_key": row[0],
            "theme": row[1],
            "authority": row[2],
            "source_url": row[3],
            "status": row[4],
            "loaded_at": _date(row[5]),
            "notes": row[6],
        }
        for row in layers
        if row[4] != "ACTIVE"
    ]
    return {"hits": hits, "unavailable": unavailable}


def report_values(context: dict) -> list[dict]:
    out: list[dict] = []
    for item in context.get("hits") or []:
        theme = THEME_LABELS.get(item["theme"], item["theme"])
        relation = (
            "intersecta a área analisada"
            if item["intersects"]
            else f"a {item['distance_m']:.1f} m da área analisada"
        )
        name = item.get("label") or item.get("upstream_key")
        category = f" · {item['category']}" if item.get("category") else ""
        out.append(
            {
                "label": f"{theme} · {name}{category}",
                "value": (
                    f"{relation}. Fonte: {item['authority']}. "
                    f"Carga: {item['loaded_at']}. "
                    f"Atualização da fonte: {item['source_updated_at']}."
                ),
            }
        )
    if not out:
        unavailable = context.get("unavailable") or []
        if unavailable:
            out.append(
                {
                    "label": "Restrições nacionais",
                    "value": (
                        "Sem conclusão completa: há camadas nacionais ainda não carregadas "
                        "ou indisponíveis nesta consulta."
                    ),
                }
            )
        else:
            out.append(
                {
                    "label": "Restrições nacionais",
                    "value": (
                        "Nenhuma feição das camadas nacionais ativas foi encontrada "
                        f"até {MAX_DISTANCE_M:.0f} m da área analisada."
                    ),
                }
            )
    return out
