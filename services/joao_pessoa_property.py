#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import municipality_utilities
from psycopg2.extras import RealDictCursor
from shapely.geometry import shape

ROOT = Path("/srv/lotediretor/app")
DB_DSN = "dbname=lotediretor user=sentinelx host=/var/run/postgresql"
BOUNDS = (-34.98, -7.25, -34.78, -7.04)
FILIPEIA_WMS = "https://filipeia.joaopessoa.pb.gov.br/geoserver/wms"
FILIPEIA_WFS = "https://filipeia.joaopessoa.pb.gov.br/geoserver/wfs"
SPATIAL_LAYERS = {
    "buildings": ("digeoc:EDIFICACOES", ["OBJECTID_1","N_PAVIM","BAIRRO","EDIFICACAO","AREA","Shape_Area"]),
    "conservation": ("digeoc:UC", ["NOME","DECRETO"]),
    "susceptibility": ("digeoc:Suscetibilidade", ["OBJECTID","classe","tipo","Shape_Area"]),
    "heritage_iphan": ("digeoc:Tombamento_IPHAN", ["OBJECTID","codcart","nome","protecao_e","data_publi"]),
    "heritage_iphaep": ("digeoc:TOMBAMENTO_IPHAEP", ["Id","CODCART","NOME","PROTECAO_E","DATAPUBLIC"]),
    "historic_center": ("digeoc:centrohistorico", ["OBJECTID","ENTITY","LAYER","Area","Hectares"]),
    "zeis": ("digeoc:ZEIS", ["OBJECTID","nome","lei","processo"]),
}
PLANNING_LAYERS = {
    "zoning": "digeoc:zoneamento2024",
    "macrozone": "digeoc:zoneamento_pmjp_macrozoneamento_CAM",
}
PLANNING_FIELDS = {"sigla", "nome", "tipo"}
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
        "method":"Curvas de nível oficiais de 2022 que cruzam o terreno",
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



def spatial_layer_for_parcel(key: str, parcel: dict, count: int = 250) -> list[dict]:
    layer, fields = SPATIAL_LAYERS[key]
    parcel_geom = shape(parcel.get("geometry") or {})
    if parcel_geom.is_empty:
        return []
    minx, miny, maxx, maxy = parcel_geom.bounds
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer,
        "srsName": "EPSG:4326",
        "count": str(count),
        "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
        "propertyName": ",".join(["the_geom"] + fields),
        "outputFormat": "application/json",
    }
    req = urllib.request.Request(
        FILIPEIA_WFS + "?" + urllib.parse.urlencode(params),
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read(5000000))
    allowed = set(fields)
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        clean = {k: props.get(k) for k in fields if props.get(k) is not None}
        if set(clean) - allowed:
            raise RuntimeError("jp_unexpected_fields")
        geom = feature.get("geometry")
        if geom and shape(geom).intersects(parcel_geom):
            out.append({
                "type": "Feature",
                "id": feature.get("id"),
                "geometry": geom,
                "properties": clean,
            })
    return out


def planning_at_point(lat: float, lng: float) -> tuple[dict, dict]:
    out = {}
    errors = {}
    for key, layer in PLANNING_LAYERS.items():
        span = 0.002
        params = {
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetFeatureInfo",
            "layers": layer,
            "query_layers": layer,
            "styles": "",
            "srs": "EPSG:4326",
            "bbox": f"{lng-span},{lat-span},{lng+span},{lat+span}",
            "width": "256",
            "height": "256",
            "x": "128",
            "y": "128",
            "info_format": "application/json",
            "feature_count": "5",
        }
        try:
            req = urllib.request.Request(
                FILIPEIA_WMS + "?" + urllib.parse.urlencode(params),
                headers={
                    "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read(2000000))
            features = data.get("features") or []
            props = (features[0].get("properties") or {}) if features else {}
            out[key] = {k: props.get(k) for k in PLANNING_FIELDS if props.get(k) is not None}
        except Exception as exc:
            out[key] = {}
            errors[key] = type(exc).__name__
    return out, errors

def context(parcel: dict, lat: float, lng: float) -> dict:
    planning, planning_errors = planning_at_point(lat, lng)
    spatial = {}
    spatial_errors = {}
    with ThreadPoolExecutor(max_workers=len(SPATIAL_LAYERS)) as pool:
        jobs = {
            pool.submit(spatial_layer_for_parcel, key, parcel): key
            for key in SPATIAL_LAYERS
        }
        for future in as_completed(jobs):
            key = jobs[future]
            try:
                spatial[key] = future.result()
            except Exception as exc:
                spatial[key] = []
                spatial_errors[key] = type(exc).__name__
    heritage_assets = (spatial.get("heritage_iphan") or []) + (spatial.get("heritage_iphaep") or [])
    heritage_buffers = {
        "Centro Histórico": spatial.get("historic_center") or [],
    }
    return {
        "planning": {
            "zoning": {"properties": planning.get("zoning") or {}},
            "macrozone": {"properties": planning.get("macrozone") or {}},
            "special_regimes": {},
            "note": (
                "Zoneamento e macrozoneamento 2024 consultados pontualmente no GeoServer "
                "oficial do Filipeia; a base não é espelhada."
            ),
        },
        "buildings": spatial.get("buildings") or [],
        "terrain": terrain_for_parcel(parcel),
        "environment": {
            "conservation_units": spatial.get("conservation") or [],
            "zeis": spatial.get("zeis") or [],
        },
        "risk": {
            "geological": [
                item for item in (spatial.get("susceptibility") or [])
                if "inund" not in " ".join(str(v) for v in (item.get("properties") or {}).values()).lower()
            ],
            "hydrological": [
                item for item in (spatial.get("susceptibility") or [])
                if "inund" in " ".join(str(v) for v in (item.get("properties") or {}).values()).lower()
            ],
        },
        "heritage": {"assets": heritage_assets, "buffers": heritage_buffers},
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
        "query_errors": {
            **{f"planning_{k}": v for k, v in planning_errors.items()},
            **{f"spatial_{k}": v for k, v in spatial_errors.items()},
        },
        "queried_at": now(),
        "source": "Prefeitura de João Pessoa / SEPLAN",
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
    if section_id == "building_existing":
        buildings=ctx.get("buildings") or []
        areas=[]
        floors=[]
        types=[]
        for item in buildings:
            p0=item.get("properties") or {}
            try:
                if p0.get("Shape_Area") is not None:areas.append(float(p0.get("Shape_Area")))
                elif p0.get("AREA") is not None:areas.append(float(str(p0.get("AREA")).replace(",", ".")))
            except (TypeError,ValueError):
                pass
            if p0.get("N_PAVIM"):floors.append(str(p0.get("N_PAVIM")))
            if p0.get("EDIFICACAO"):types.append(str(p0.get("EDIFICACAO")))
        return [
            {"label":"Edificações mapeadas que intersectam o terreno","value":len(buildings)},
            {"label":"Área cartográfica somada das edificações","value":round(sum(areas),2) if areas else None,"unit":"m²"},
            {"label":"Pavimentos informados na cartografia","value":", ".join(sorted(set(floors))) if floors else None},
            {"label":"Tipos de edificação informados","value":", ".join(sorted(set(types))) if types else None},
            {"label":"Ressalva","value":"As edificações são contexto cartográfico municipal e não substituem cadastro fiscal, projeto aprovado ou levantamento atual."},
        ]
    if section_id == "environment_risk_heritage":
        out=[]
        for item in (ctx.get("environment") or {}).get("conservation_units") or []:
            p0=item.get("properties") or {}
            out.extend([
                {"label":"Unidade de conservação","value":p0.get("NOME")},
                {"label":"Norma da unidade de conservação","value":p0.get("DECRETO")},
            ])
        for item in (ctx.get("environment") or {}).get("zeis") or []:
            p0=item.get("properties") or {}
            out.extend([
                {"label":"ZEIS que intersecta o terreno","value":p0.get("nome")},
                {"label":"Base legal da ZEIS","value":p0.get("lei")},
            ])
        for risk_key, label in [("geological","Suscetibilidade geológica"),("hydrological","Suscetibilidade a inundação")]:
            for item in (ctx.get("risk") or {}).get(risk_key) or []:
                p0=item.get("properties") or {}
                parts=[str(x).strip() for x in [p0.get("tipo"),p0.get("classe")] if x and str(x).strip() not in {"-","—"}]
                out.append({"label":label,"value":" · ".join(parts) if parts else "Incidência na camada oficial"})
        for item in (ctx.get("heritage") or {}).get("assets") or []:
            p0=item.get("properties") or {}
            out.extend([
                {"label":"Bem protegido","value":p0.get("nome") or p0.get("NOME")},
                {"label":"Proteção cultural","value":p0.get("protecao_e") or p0.get("PROTECAO_E")},
            ])
        for item in ((ctx.get("heritage") or {}).get("buffers") or {}).get("Centro Histórico") or []:
            out.append({"label":"Centro Histórico","value":"Terreno intersecta a poligonal publicada."})
        return out or [{"label":"Incidências ambientais, de suscetibilidade e patrimônio","value":"Nenhuma incidência nas camadas oficiais consultadas para este terreno."}]
    if section_id == "planning_buildability":
        zoning=((ctx.get("planning") or {}).get("zoning") or {}).get("properties") or {}
        macro=((ctx.get("planning") or {}).get("macrozone") or {}).get("properties") or {}
        return [
            {"label":"Zoneamento 2024","value":zoning.get("sigla")},
            {"label":"Descrição do zoneamento","value":zoning.get("nome")},
            {"label":"Tipo de zoneamento","value":zoning.get("tipo")},
            {"label":"Macrozona 2024","value":macro.get("sigla")},
            {"label":"Descrição da macrozona","value":macro.get("nome")},
            {"label":"Tipo de macrozona","value":macro.get("tipo")},
            {"label":"Método","value":"Consulta espacial ao mapa oficial de zoneamento da Prefeitura de João Pessoa."}
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
    if section_id == "infrastructure_utilities":
        return municipality_utilities.report_values(ctx.get("utilities") or {})
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
    ctx = context(parcel, lat, lng)
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
