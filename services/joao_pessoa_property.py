#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import municipality_utilities
from psycopg2.extras import RealDictCursor

ROOT = Path("/srv/lotediretor/app")
DB_DSN = "dbname=lotediretor user=sentinelx host=/var/run/postgresql"
BOUNDS = (-34.98, -7.25, -34.78, -7.04)
LABEL = {
    "identity": "Identidade",
    "land": "Terreno",
    "building": "Edificação",
    "IPTU": "IPTU",
    "PGV": "PGV",
    "ITBI": "ITBI",
    "registry reference": "Registro imobiliário",
    "zoning": "Zoneamento",
    "urban parameters": "Parâmetros urbanísticos",
    "permits": "Licenciamento",
    "habite-se": "Habite-se",
    "environment": "Ambiental",
    "risk": "Risco",
    "heritage": "Patrimônio",
    "electricity": "Energia",
    "gas": "Gás",
    "water/sewer": "Água e esgoto",
    "drainage": "Drenagem",
    "telecom": "Telecom",
    "transport": "Sistema viário",
    "imagery": "Imagens",
    "terrain": "Terreno/topografia",
    "public works": "Obras públicas",
    "public processes": "Processos públicos",
    "official gazette": "Diário Oficial",
    "historical data": "Histórico",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def db():
    return psycopg2.connect(DB_DSN)


def row_feature(row: dict) -> dict:
    props = {
        "municipal_parcel_feature_id": row.get("gid"),
        "sql_reference": row.get("codi_cart"),
        "cartographic_code": row.get("codi_cart"),
        "fiscal_sector": row.get("codi_seto"),
        "fiscal_block": row.get("codi_quad"),
        "fiscal_lot": row.get("codi_lote"),
        "street": row.get("desc_logr"),
        "number": None,
        "land_area_m2": float(row["area_m2"]) if row.get("area_m2") is not None else None,
        "built_area_m2": None,
        "use_description": row.get("tipo_imove"),
        "parcel_type": row.get("tipo_imove"),
        "parcel_status": "CADASTRADO",
        "cib": None,
        "cib_status": None,
        "complement": None,
    }
    return {
        "type": "Feature",
        "id": f"jp-{row.get('gid')}",
        "geometry": json.loads(row["geojson"]),
        "properties": props,
    }


def point(lat: float, lng: float) -> dict | None:
    min_lng, min_lat, max_lng, max_lat = BOUNDS
    if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
        raise ValueError("outside_joao_pessoa_bounds")
    sql = """
        SELECT gid,codi_cart,codi_seto,codi_quad,codi_lote,desc_logr,tipo_imove,
               ST_Area(ST_Transform(ST_Force2D(geom),31985)) AS area_m2,
               ST_AsGeoJSON(ST_Force2D(geom),7) AS geojson
        FROM ld_stage.jp_lotes
        WHERE ST_Covers(
            ST_Force2D(geom),
            ST_SetSRID(ST_Point(%s,%s),4674)
        )
        ORDER BY ST_Area(ST_Transform(ST_Force2D(geom),31985))
        LIMIT 1
    """
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (lng, lat))
        row = cur.fetchone()
    return row_feature(dict(row)) if row else None


def representative_point(geom: dict) -> dict:
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ST_Y(p),ST_X(p)
            FROM (
              SELECT ST_PointOnSurface(
                ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326)
              ) AS p
            ) q
            """,
            (json.dumps(geom),),
        )
        lat, lng = cur.fetchone()
    return {"lat": float(lat), "lng": float(lng)}


def search(query_text: str) -> list[dict]:
    code = re.sub(r"\D", "", query_text or "")
    if not re.fullmatch(r"\d{9}", code):
        raise ValueError("unsupported_search_format")
    sql = """
        SELECT gid,codi_cart,codi_seto,codi_quad,codi_lote,desc_logr,tipo_imove,
               ST_Area(ST_Transform(ST_Force2D(geom),31985)) AS area_m2,
               ST_AsGeoJSON(ST_Force2D(geom),7) AS geojson
        FROM ld_stage.jp_lotes
        WHERE codi_cart=%s
        LIMIT 10
    """
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (code,))
        rows = [dict(r) for r in cur.fetchall()]
    out = []
    for row in rows:
        feature = row_feature(row)
        out.append(
            {
                "feature": feature,
                "representative_point": representative_point(feature["geometry"]),
            }
        )
    return out


def terrain_for_parcel(parcel: dict) -> dict:
    code=(parcel.get("properties") or {}).get("cartographic_code")
    if not code:
        return {"available":False,"reason":"missing_cartographic_code"}
    sql="""
        SELECT count(*) AS contour_count,
               min(c.cota)::float8 AS min_elevation_m,
               max(c.cota)::float8 AS max_elevation_m,
               array_agg(DISTINCT c.cota ORDER BY c.cota) AS elevations
        FROM ld_stage.jp_lotes l
        JOIN ld_stage.jp_curvas_nivel_2022 c
          ON ST_Intersects(ST_Force2D(l.geom), c.geom)
        WHERE l.codi_cart=%s
    """
    with db() as conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql,(code,))
        row=dict(cur.fetchone())
    vals=[float(v) for v in (row.get("elevations") or [])]
    return {
        "available":bool(row.get("contour_count")),
        "method":"Filipeia curvas de nível 2022 intersectando o polígono cadastral do lote",
        "quality":"OFFICIAL_CONTOUR_INTERSECTION",
        "contour_count":int(row.get("contour_count") or 0),
        "min_elevation_m":row.get("min_elevation_m"),
        "max_elevation_m":row.get("max_elevation_m"),
        "amplitude_m":(
            round(row["max_elevation_m"]-row["min_elevation_m"],3)
            if row.get("min_elevation_m") is not None and row.get("max_elevation_m") is not None
            else None
        ),
        "contour_elevations_m":vals,
        "source_sha256":"3b29f856cfef6b0e20a76120ecdfdedcdb43a18a538c14362b1b1439331d1fbb",
        "caveat":"Faixa baseada nas curvas oficiais que cruzam o lote; não substitui MDT contínuo ou levantamento topográfico de campo."
    }


def context(parcel: dict) -> dict:
    return {
        "planning": {
            "zoning": {"properties": {}},
            "special_regimes": {},
            "note": (
                "Plano Diretor 2024 e mapas oficiais estão registrados no Filipeia, "
                "mas o zoneamento vetorial por lote ainda não foi materializado."
            ),
        },
        "buildings": [],
        "terrain": terrain_for_parcel(parcel),
        "risk": {"geological": [], "hydrological": []},
        "heritage": {"assets": [], "buffers": {}},
        "utilities": municipality_utilities.load("2507507"),
        "licensing": {
            "housing_permits_exact_sql": [],
            "impact_spatial_incidence": [],
            "environment_spatial_incidence": [],
            "interpretation": (
                "Licenciamento/habite-se municipal permanece em fluxo autenticado "
                "ou documental e não foi automatizado."
            ),
        },
        "fiscal": {
            "pgv": {"found": False},
            "iptu": {"found": False, "latest": {}},
            "itbi": {
                "available": False,
                "count": 0,
                "registry_references": [],
                "transactions": [],
            },
        },
        "query_errors": {},
        "queried_at": now(),
        "source": "Filipeia / SEPLAN / PMJP",
    }


def vals(section_id: str, parcel: dict, ctx: dict) -> list[dict]:
    p = parcel["properties"]
    if section_id == "executive_summary":
        return [
            {"label": "Código cartográfico", "value": p.get("cartographic_code")},
            {"label": "Logradouro", "value": p.get("street")},
            {"label": "Setor", "value": p.get("fiscal_sector")},
            {"label": "Quadra", "value": p.get("fiscal_block")},
            {"label": "Lote", "value": p.get("fiscal_lot")},
            {"label": "Área geométrica", "value": p.get("land_area_m2"), "unit": "m²"},
            {"label": "Tipo cadastral", "value": p.get("parcel_type")},
        ]
    if section_id == "identity_location":
        return [
            {"label": "Código cartográfico", "value": p.get("cartographic_code")},
            {"label": "Setor cartográfico", "value": p.get("fiscal_sector")},
            {"label": "Quadra", "value": p.get("fiscal_block")},
            {"label": "Lote", "value": p.get("fiscal_lot")},
            {"label": "Logradouro", "value": p.get("street")},
            {"label": "Tipo do imóvel", "value": p.get("parcel_type")},
            {"label": "Área geométrica calculada", "value": p.get("land_area_m2"), "unit": "m²"},
        ]
    if section_id == "planning_buildability":
        return [
            {
                "label": "Plano Diretor / zoneamento",
                "value": (
                    "Mapas oficiais 2024 disponíveis no Filipeia; vínculo vetorial "
                    "por lote permanece em materialização."
                ),
            }
        ]
    if section_id == "terrain_visual":
        t=ctx.get("terrain") or {}
        if not t.get("available"):
            return [{"label":"Topografia","value":"Nenhuma curva de nível oficial intersecta o lote nesta consulta."}]
        return [
            {"label":"Curvas de nível 2022 intersectantes","value":t.get("contour_count")},
            {"label":"Menor cota no lote","value":t.get("min_elevation_m"),"unit":"m"},
            {"label":"Maior cota no lote","value":t.get("max_elevation_m"),"unit":"m"},
            {"label":"Amplitude entre curvas","value":t.get("amplitude_m"),"unit":"m"},
            {"label":"Cotas intersectantes","value":", ".join(str(v) for v in t.get("contour_elevations_m") or [])},
            {"label":"Método","value":t.get("method")},
            {"label":"Limite topográfico","value":t.get("caveat")}
        ]
    if section_id == "infrastructure_utilities":
        return [
            {"label": "Energia · prestador", "value": "Energisa Paraíba"},
            {"label": "Água e esgoto · prestador", "value": "CAGEPA"},
            {"label": "Drenagem · autoridade", "value": "Prefeitura de João Pessoa / SEINFRA"},
            {
                "label": "Limite de interpretação",
                "value": (
                    "Prestador/território não comprovam ligação, disponibilidade "
                    "ou capacidade técnica no lote."
                ),
            },
        ]
    if section_id == "licensing_history":
        return [
            {
                "label": "Licenciamento/habite-se",
                "value": (
                    "Serviço municipal identificado, mas consulta depende de fluxo "
                    "autenticado/documental; não automatizado."
                ),
            }
        ]
    if section_id=="infrastructure_utilities":
        return municipality_utilities.report_values(c.get("utilities") or {})
    return []


def report(parcel: dict, ctx: dict) -> dict:
    spec = json.loads((ROOT / "data/property-dossier/report-spec.json").read_text())
    matrix = json.loads(
        (ROOT / "data/deployment/professional-completion-matrix.json").read_text()
    )
    city = next(x for x in matrix["first_wave"] if x.get("ibge") == "2507507")
    rows = {r["field"]: r for r in city["rows"]}
    sections = []
    for section in sorted(spec["sections"], key=lambda x: x["order"]):
        field_states = [
            {
                "field": field,
                "label": LABEL.get(field, field),
                "status": rows[field].get("status"),
                "source_id": rows[field].get("source_id"),
                "connector_status": rows[field].get("connector_status"),
                "access_class": rows[field].get("access_class"),
                "missing_fields": rows[field].get("missing_fields") or [],
            }
            for field in section.get("source_matrix_fields", [])
            if field in rows
        ]
        actual = [
            item
            for item in vals(section["id"], parcel, ctx)
            if item.get("value") not in (None, "")
        ]
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "order": section["order"],
                "section_type": section.get("section_type"),
                "actual_values": actual,
                "fields": field_states,
            }
        )
    return {
        "title": spec["title"],
        "target_completion_level": spec["target_completion_level"],
        "principle": spec["principle"],
        "mode": "PUBLIC_PROPERTY_REPORT",
        "sections": sections,
    }


def response_for_point(lat: float, lng: float) -> dict | None:
    parcel = point(lat, lng)
    if not parcel:
        return None
    ctx = context(parcel)
    return {
        "found": True,
        "clicked": {"lat": lat, "lng": lng},
        "feature": parcel,
        "context": ctx,
        "source": {
            "id": "pb-joao-pessoa-filipeia",
            "authority": "Filipeia / SEPLAN / PMJP",
            "layer": "Lotes.zip",
            "license": (
                "Consulta individual com atribuição. Termos do Filipeia vedam "
                "uso comercial/alienação onerosa dos arquivos ou informações."
            ),
            "queried_at": now(),
            "method": "PostGIS point-in-polygon over official Filipeia lot file",
        },
        "report": report(parcel, ctx),
    }
