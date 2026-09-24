#!/usr/bin/env python3
"""Read-only parcel click API for the LoteDiretor public demo.

The endpoint accepts only a point inside the municipality of São Paulo and
queries the approved GeoSampa lote_cidadao WFS layer with a closed property
allowlist. It never requests owner/person fields.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import laspy
import numpy as np
from pyproj import Transformer
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform as shapely_transform

HOST = "127.0.0.1"
PORT = 8765
WFS = "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/ows"
TYPE_NAME = "geoportal:lote_cidadao"
FIELDS = [
    "ge_poligono",
    "cd_identificador",
    "cd_identificador_original_lote",
    "cd_setor_fiscal",
    "cd_tipo_quadra",
    "tx_tipo_quadra",
    "cd_quadra_fiscal",
    "cd_subquadra_fiscal",
    "cd_condominio",
    "cd_tipo_lote",
    "tx_tipo_lote",
    "cd_lote",
    "cd_situacao",
    "cd_digito_sql",
    "cd_logradouro",
    "nm_logradouro_completo",
    "cd_numero_porta",
    "tx_complemento_endereco",
    "tx_situ_lote",
    "cd_tipo_uso_imovel",
    "dc_tipo_uso_imovel",
    "cd_tipo_terreno_imovel",
    "qt_area_terreno",
    "qt_area_construida",
    "cd_cib",
    "tx_situacao_cib",
]
# Coarse municipality envelope. The API is not a general WFS relay.
SP_BOUNDS = (-46.95, -24.05, -46.20, -23.30)
DELTA = 0.00045
MAX_FEATURES = 120
ROOT = Path("/srv/lotediretor/app")
REPORT_SPEC_PATH = ROOT / "data/property-dossier/report-spec.json"
MATRIX_PATH = ROOT / "data/deployment/professional-completion-matrix.json"
UTILITY_RESOLVER_PATH = ROOT / "data/utilities/municipality-provider-resolver.json"
SOURCE_REGISTRY_PATH = ROOT / "data/source-registry/bootstrap.json"
PGV_INDEX_PATH = Path("/srv/lotediretor/data/pgv2026/pgv-terrain-values-2026.json")
ITBI_DB_PATH = Path("/srv/lotediretor/data/itbi-public/itbi-transactions.sqlite3")
IPTU_DB_PATH = Path("/srv/lotediretor/data/iptu-public/iptu-cadastre.sqlite3")
TERRAIN_CACHE_DIR = Path("/var/cache/lotediretor/terrain/mdt2020")
TERRAIN_DOWNLOAD = "https://download.geosampa.prefeitura.sp.gov.br/PaginasPublicas/downloadArquivo.aspx"
_TERRAIN_RESULT_CACHE = {}
_PGV_INDEX_CACHE = None

FIELD_LABELS = {
    "identity": "Identidade", "land": "Terreno", "building": "Edificação",
    "IPTU": "IPTU", "PGV": "PGV", "ITBI": "ITBI",
    "registry reference": "Registro imobiliário", "zoning": "Zoneamento",
    "urban parameters": "Parâmetros urbanísticos", "permits": "Licenciamento",
    "habite-se": "Habite-se", "environment": "Ambiental", "risk": "Risco",
    "heritage": "Patrimônio", "electricity": "Energia", "gas": "Gás",
    "water/sewer": "Água e esgoto", "drainage": "Drenagem",
    "telecom": "Telecom", "transport": "Sistema viário", "imagery": "Imagens",
    "terrain": "Terreno/topografia", "public works": "Obras públicas",
    "public processes": "Processos públicos", "official gazette": "Diário Oficial",
    "historical data": "Histórico",
}


BUILDING_LAYER = {
    "type_name": "geoportal:edificacao",
    "geometry": "ge_poligono",
    "fields": [
        "cd_identificador",
        "qt_area_projecao_beiral",
        "qt_altura_edificacao",
        "cd_identificador_lote",
        "tx_escala",
        "sg_fonte_original",
        "dt_criacao",
        "dt_atualizacao",
    ],
}

THEMATIC_LAYERS = {
    "terrain_tile": {
        "type_name": "geoportal:quadricula_folha_mdt_mds_2020",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador",
            "cd_levantamento",
            "cd_quadricula",
            "an_levantamento",
            "tx_situacao_quadricula",
            "tx_levantamento",
            "cd_escala_quadricula",
            "sg_fonte_original",
        ],
    },
    "zoning": {
        "type_name": "geoportal:perimetro_zona_lei_18177_24",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "tx_zoneamento_perimetro",
            "tx_observacao_perimetro", "cd_zoneamento_perimetro",
            "cd_tipo_legislacao_zoneamento",
            "cd_numero_legislacao_zoneamento",
            "an_legislacao_zoneamento", "dt_atualizacao",
        ],
    },
    "macroarea": {
        "type_name": "geoportal:pde_macroarea_lei_18209",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador_pde_macroarea_lei_18209",
            "nm_macroarea", "sg_macroarea", "dt_atualizacao",
        ],
    },
    "macrozone": {
        "type_name": "geoportal:pde2014_v_mcrz_01_map",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "sg_macro_divisao_pde",
            "nm_perimetro_divisao_pde", "nm_tema_divisao_pde",
            "tx_macro_divisao_pde", "cd_macro_divisao_pde",
        ],
    },
    "geological_risk": {
        "type_name": "geoportal:area_risco_geologico",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "nm_area_risco",
            "tx_grau_de_risco_geologico", "sg_area_risco",
            "sg_setor_risco", "tx_tipo_processo_geologico",
            "cd_grau_risco_geologico", "dt_atualizacao",
            "dt_vistoria", "sg_fonte_original",
        ],
    },
    "hydrological_risk": {
        "type_name": "geoportal:risco_hidrologico",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador_risco_hidrologico",
            "nm_area_risco_hidrologico",
            "tx_grau_risco_hidrologico",
            "sg_area_risco_hidrologico",
            "sg_setor_risco_hidrologico",
            "tx_tipo_processo", "dt_vistoria",
            "nm_subprefeitura", "nm_bacia_hidrografica",
        ],
    },
    "heritage_asset": {
        "type_name": "geoportal:patrimonio_cultural_bem_tombado",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "nm_area_tombada",
            "tx_resolucao_conpresp", "tx_resolucao_condephaat",
            "tx_resolucao_iphan", "nm_endereco", "tx_link_resolucao",
            "tx_zepec", "tx_nivel_tombamento",
            "tx_situacao_tombamento", "tx_tipo_categoria_zepec",
            "dt_carga",
        ],
    },
    "heritage_buffer_conpresp": {
        "type_name": "geoportal:patrimonio_cultural_area_envoltoria_CONPRESP",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "nm_area",
            "tx_resolucao_conpresp", "tx_link_resolucao",
            "sg_fonte_original", "dt_carga",
        ],
    },
    "heritage_buffer_condephaat": {
        "type_name": "geoportal:patrimonio_cultural_area_envoltoria_CONDEPHAAT",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "nm_area",
            "tx_resolucao_condephaat", "tx_link_resolucao",
            "dt_carga",
        ],
    },
    "impact_license": {
        "type_name": "geoportal:GEOSAMPA_licenca_obra",
        "geometry": "ge_multipoligono",
        "fields": [
            "cd_identificador_licenca_obra",
            "cd_processo_administrativo",
            "tx_endereco_empreendimento",
            "cd_parecer_cades",
            "cd_parecer_cla",
            "dt_publicacao_doc",
            "tx_link_doc",
            "st_licenca_empreendimento",
            "tx_categoria_ocupacao",
        ],
    },
    "environment_license": {
        "type_name": "geoportal:GEOSAMPA_licenca_expedida_multipoligono_internet",
        "geometry": "ge_multipoligono",
        "fields": [
            "cd_identificador_licenca_expedida_fme",
            "cd_licenca_ambiental_expedida",
            "sg_licenca_ambiental_expedida",
            "cd_numero_licenca_expedida",
            "nm_descricao_licenca",
            "dt_expedicao_licenca",
            "dt_validade_licenca_expedida",
            "cd_processo_administrativo_licenca",
            "nm_documento_licenca",
            "tx_categoria_empreendimento",
            "tp_estudo_licenca",
            "tx_link_estudo_publicado",
            "an_expedicao_licenca",
            "dt_atualizacao",
            "nm_completo_hiperlink",
            "tx_observacao",
        ],
    },
    "heritage_buffer_iphan": {
        "type_name": "geoportal:patrimonio_cultural_area_envoltoria_IPHAN",
        "geometry": "ge_poligono",
        "fields": [
            "cd_identificador", "nm_area",
            "tx_resolucao_iphan", "sg_fonte_original",
            "dt_carga",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def point_on_segment(px, py, ax, ay, bx, by, eps=1e-10):
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= eps


def point_in_ring(lng: float, lat: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if point_on_segment(lng, lat, xi, yi, xj, yj):
            return True
        crosses = ((yi > lat) != (yj > lat))
        if crosses:
            x_at_lat = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_at_lat:
                inside = not inside
        j = i
    return inside


def point_in_polygon(lng: float, lat: float, coordinates: list) -> bool:
    if not coordinates or not point_in_ring(lng, lat, coordinates[0]):
        return False
    return not any(point_in_ring(lng, lat, hole) for hole in coordinates[1:])


def contains_point(feature: dict, lng: float, lat: float) -> bool:
    geometry = feature.get("geometry") or {}
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        return point_in_polygon(lng, lat, coordinates)
    if kind == "MultiPolygon":
        return any(point_in_polygon(lng, lat, polygon) for polygon in coordinates)
    return False



def geometry_polygons(geometry: dict) -> list[list]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [coords]
    if kind == "MultiPolygon":
        return coords
    return []


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = []
    for polygon in geometry_polygons(geometry):
        for ring in polygon:
            for point in ring:
                if len(point) >= 2:
                    points.append((float(point[0]), float(point[1])))
    if not points:
        raise ValueError("geometry has no coordinates")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def orientation(ax, ay, bx, by, cx, cy, eps=1e-12):
    value = (by - ay) * (cx - bx) - (bx - ax) * (cy - by)
    if abs(value) <= eps:
        return 0
    return 1 if value > 0 else 2


def segments_intersect(a, b, c, d) -> bool:
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    cx, cy = c[0], c[1]
    dx, dy = d[0], d[1]
    o1 = orientation(ax, ay, bx, by, cx, cy)
    o2 = orientation(ax, ay, bx, by, dx, dy)
    o3 = orientation(cx, cy, dx, dy, ax, ay)
    o4 = orientation(cx, cy, dx, dy, bx, by)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and point_on_segment(cx, cy, ax, ay, bx, by))
        or (o2 == 0 and point_on_segment(dx, dy, ax, ay, bx, by))
        or (o3 == 0 and point_on_segment(ax, ay, cx, cy, dx, dy))
        or (o4 == 0 and point_on_segment(bx, by, cx, cy, dx, dy))
    )


def polygon_intersects_polygon(a: list, b: list) -> bool:
    if not a or not b or not a[0] or not b[0]:
        return False
    for point in a[0]:
        if point_in_polygon(point[0], point[1], b):
            return True
    for point in b[0]:
        if point_in_polygon(point[0], point[1], a):
            return True
    ring_a = a[0]
    ring_b = b[0]
    for i in range(len(ring_a) - 1):
        for j in range(len(ring_b) - 1):
            if segments_intersect(
                ring_a[i], ring_a[i + 1],
                ring_b[j], ring_b[j + 1],
            ):
                return True
    return False


def geometry_intersects(a: dict, b: dict) -> bool:
    for polygon_a in geometry_polygons(a):
        for polygon_b in geometry_polygons(b):
            if polygon_intersects_polygon(polygon_a, polygon_b):
                return True
    return False


def sql_reference(props: dict) -> str | None:
    sector = props.get("cd_setor_fiscal")
    block = props.get("cd_quadra_fiscal")
    lot = props.get("cd_lote")
    digit = props.get("cd_digito_sql")
    condominium = props.get("cd_condominio")
    if not all(isinstance(v, str) and v for v in (sector, block, lot, digit)):
        return None
    if lot == "0000" or condominium not in (None, "", "00"):
        return None
    return f"{sector}{block}{lot}{digit}"



def representative_point(geometry: dict) -> tuple[float, float]:
    polygons = geometry_polygons(geometry)
    if not polygons or not polygons[0] or not polygons[0][0]:
        raise ValueError("parcel geometry has no representative ring")
    ring = polygons[0][0]
    points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if points:
        lng = sum(float(point[0]) for point in points) / len(points)
        lat = sum(float(point[1]) for point in points) / len(points)
        if point_in_polygon(lng, lat, polygons[0]):
            return lat, lng
    min_lng, min_lat, max_lng, max_lat = geometry_bbox(geometry)
    lng = (min_lng + max_lng) / 2
    lat = (min_lat + max_lat) / 2
    if point_in_polygon(lng, lat, polygons[0]):
        return lat, lng
    first = ring[0]
    return float(first[1]), float(first[0])


def fetch_parcels_by_cql(cql_filter: str, count: int = 8) -> list[dict]:
    query = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": TYPE_NAME,
        "srsName": "EPSG:4326",
        "cql_filter": cql_filter,
        "count": str(count),
        "propertyName": ",".join(FIELDS),
        "outputFormat": "application/json",
    }
    url = WFS + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read(4 * 1024 * 1024 + 1)
        if response.status != 200:
            raise RuntimeError(f"GeoSampa search returned HTTP {response.status}")
        if len(body) > 4 * 1024 * 1024:
            raise RuntimeError("GeoSampa search exceeded safety limit")
    payload = json.loads(body)
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("GeoSampa search did not return FeatureCollection")
    return payload.get("features") or []


def search_parcel(query_text: str) -> list[dict]:
    compact = re.sub(r"[^A-Za-z0-9]", "", query_text or "").upper()
    if not compact:
        raise ValueError("empty_search")

    if compact.isdigit() and len(compact) == 11:
        sector = compact[0:3]
        block = compact[3:6]
        lot = compact[6:10]
        digit = compact[10:11]
        cql = (
            f"cd_setor_fiscal='{sector}' AND "
            f"cd_quadra_fiscal='{block}' AND "
            f"cd_lote='{lot}' AND "
            f"cd_digito_sql='{digit}'"
        )
    elif re.fullmatch(r"[A-Z0-9]{6,20}", compact):
        cql = f"cd_cib='{compact}'"
    else:
        raise ValueError("unsupported_search_format")

    features = fetch_parcels_by_cql(cql)
    output = []
    for feature in features:
        parcel = public_feature(feature)
        lat, lng = representative_point(parcel["geometry"])
        output.append({
            "feature": parcel,
            "representative_point": {"lat": lat, "lng": lng},
        })
    return output


def fetch_candidates(lat: float, lng: float) -> dict:
    bbox = f"{lng-DELTA},{lat-DELTA},{lng+DELTA},{lat+DELTA},EPSG:4326"
    query = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": TYPE_NAME,
        "srsName": "EPSG:4326",
        "bbox": bbox,
        "count": str(MAX_FEATURES),
        "propertyName": ",".join(FIELDS),
        "outputFormat": "application/json",
    }
    url = WFS + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f"GeoSampa returned HTTP {response.status}")
        body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise RuntimeError("GeoSampa response exceeded safety limit")
    payload = json.loads(body)
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("GeoSampa did not return a FeatureCollection")
    return payload




def fetch_buildings_for_parcel(parcel_geometry: dict) -> list[dict]:
    min_lng, min_lat, max_lng, max_lat = geometry_bbox(parcel_geometry)
    bbox = f"{min_lng},{min_lat},{max_lng},{max_lat},EPSG:4326"
    query = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": BUILDING_LAYER["type_name"],
        "srsName": "EPSG:4326",
        "bbox": bbox,
        "count": "300",
        "propertyName": ",".join(
            [BUILDING_LAYER["geometry"], *BUILDING_LAYER["fields"]]
        ),
        "outputFormat": "application/json",
    }
    url = WFS + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read(6 * 1024 * 1024 + 1)
        if response.status != 200:
            raise RuntimeError(
                f"GeoSampa {BUILDING_LAYER['type_name']} returned HTTP {response.status}"
            )
        if len(body) > 6 * 1024 * 1024:
            raise RuntimeError("GeoSampa building response exceeded safety limit")
    payload = json.loads(body)
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("GeoSampa building layer did not return FeatureCollection")

    output = []
    allowed = set(BUILDING_LAYER["fields"])
    for feature in payload.get("features") or []:
        geometry = feature.get("geometry") or {}
        if not geometry_intersects(parcel_geometry, geometry):
            continue
        props = feature.get("properties") or {}
        unexpected = set(props) - allowed
        if unexpected:
            raise RuntimeError(
                "GeoSampa building layer returned unexpected fields: "
                + ", ".join(sorted(unexpected))
            )
        output.append({
            "id": feature.get("id"),
            "geometry": geometry,
            "properties": props,
        })
    return output


def fetch_housing_permits(sql: str | None) -> list[dict]:
    if not sql or not re.fullmatch(r"\d{11}", sql):
        return []
    fields = [
        "cd_identificador_habitacao_popular",
        "cd_subcategoria_uso",
        "cd_sql_incra",
        "tx_grupo_endereco",
        "tx_assunto_alvara",
        "cd_numero_processo_execucao",
        "dt_autuacao_execucao",
        "cd_numero_documento_execucao",
        "dt_deferimento_execucao",
        "qt_area_total_terreno",
        "qt_area_construida_total",
        "qt_unidade_his",
        "qt_unidade_hmp",
        "dt_atualizacao",
    ]
    query = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "geoportal:habitacao_popular",
        "srsName": "EPSG:4326",
        "cql_filter": f"cd_sql_incra='{sql}'",
        "count": "50",
        "propertyName": ",".join(fields),
        "outputFormat": "application/json",
    }
    url = WFS + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        if response.status != 200:
            raise RuntimeError(
                f"GeoSampa habitacao_popular returned HTTP {response.status}"
            )
        if len(body) > 2 * 1024 * 1024:
            raise RuntimeError("GeoSampa habitacao_popular exceeded safety limit")
    payload = json.loads(body)
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("GeoSampa habitacao_popular did not return FeatureCollection")
    output = []
    allowed = set(fields)
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        unexpected = set(props) - allowed
        if unexpected:
            raise RuntimeError(
                "GeoSampa habitacao_popular returned unexpected fields: "
                + ", ".join(sorted(unexpected))
            )
        if props.get("cd_sql_incra") != sql:
            continue
        output.append({"id": feature.get("id"), "properties": props})
    return output


def terrain_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_mdt_2020_tile(tile_code: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{3}", tile_code or ""):
        raise ValueError("invalid_mdt_tile_code")

    TERRAIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    laz_path = TERRAIN_CACHE_DIR / f"MDT_{tile_code}_1000.laz"
    manifest_path = TERRAIN_CACHE_DIR / f"{tile_code}.json"

    if laz_path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("laz_sha256") == terrain_file_sha256(laz_path):
            return manifest

    archive_name = f"{tile_code}.zip"
    params = {
        "orig": "DownloadMapaArticulacao",
        "arq": f"MDT_2020\\{archive_name}",
        "arqTipo": "MAPA_ARTICULACAO",
    }
    url = TERRAIN_DOWNLOAD + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 LoteDiretor/0.1 (+https://lotediretor.com)",
            "Referer": "https://download.geosampa.prefeitura.sp.gov.br/PaginasPublicas/_SBC.aspx",
            "Accept": "application/zip,application/octet-stream,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(80 * 1024 * 1024 + 1)
        final_url = response.geturl()
    if len(raw) > 80 * 1024 * 1024:
        raise RuntimeError("MDT archive exceeded safety limit")
    if not raw.startswith(b"PK"):
        raise RuntimeError("GeoSampa MDT endpoint did not return ZIP")

    archive_sha = hashlib.sha256(raw).hexdigest()
    expected = f"MDT_{tile_code}_1000.laz"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if expected not in names:
            raise RuntimeError(f"expected {expected} not found in MDT archive")
        info = archive.getinfo(expected)
        if info.file_size > 150 * 1024 * 1024:
            raise RuntimeError("MDT LAZ exceeded safety limit")
        with archive.open(info) as source, laz_path.open("wb") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)

    laz_sha = terrain_file_sha256(laz_path)
    manifest = {
        "tile": tile_code,
        "year": 2020,
        "source_id": "sp-sao-paulo-lidar-terrain",
        "source_url": url,
        "final_url": final_url,
        "zip_sha256": archive_sha,
        "laz_sha256": laz_sha,
        "laz_file": laz_path.name,
        "captured_at": utc_now(),
    }
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(manifest_path)
    return manifest


def parcel_axis_line(parcel_utm, direction: np.ndarray) -> LineString:
    center = np.array([parcel_utm.centroid.x, parcel_utm.centroid.y], dtype=float)
    length = max(
        parcel_utm.bounds[2] - parcel_utm.bounds[0],
        parcel_utm.bounds[3] - parcel_utm.bounds[1],
        20.0,
    ) * 4
    segment = LineString([
        center - direction * length,
        center + direction * length,
    ])
    clipped = parcel_utm.intersection(segment)
    if clipped.geom_type == "MultiLineString":
        clipped = max(clipped.geoms, key=lambda geom: geom.length)
    if clipped.geom_type != "LineString":
        raise RuntimeError("unable to derive parcel profile axis")
    return clipped


def analyze_mdt_for_parcel(parcel_geometry: dict, laz_path: Path) -> dict:
    parcel_wgs84 = shape(parcel_geometry)
    transformer = Transformer.from_crs(4326, 31983, always_xy=True)
    parcel = shapely_transform(transformer.transform, parcel_wgs84)

    las = laspy.read(str(laz_path))
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z = np.asarray(las.z)
    if len(z) < 100:
        raise RuntimeError("MDT tile contains too few points")

    local_area = parcel.buffer(30)
    minx, miny, maxx, maxy = local_area.bounds
    mask = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    local_x = x[mask]
    local_y = y[mask]
    local_z = z[mask]
    if len(local_z) < 80:
        raise RuntimeError("insufficient local MDT points")

    local_points = np.column_stack((local_x, local_y))
    inside_buffer = np.array([
        local_area.contains(Point(float(px), float(py)))
        for px, py in local_points
    ])
    local_points = local_points[inside_buffer]
    local_z = local_z[inside_buffer]
    if len(local_z) < 80:
        raise RuntimeError("insufficient local MDT points after clipping")

    interpolator = LinearNDInterpolator(local_points, local_z, fill_value=np.nan)
    tree = cKDTree(local_points)

    rectangle = parcel.minimum_rotated_rectangle
    rect = list(rectangle.exterior.coords)[:-1]
    edges = []
    for index in range(4):
        start = np.array(rect[index], dtype=float)
        end = np.array(rect[(index + 1) % 4], dtype=float)
        edges.append((float(np.linalg.norm(end - start)), start, end))
    edges.sort(key=lambda item: item[0], reverse=True)
    direction_a = edges[0][2] - edges[0][1]
    direction_a = direction_a / np.linalg.norm(direction_a)
    direction_b = np.array([-direction_a[1], direction_a[0]])

    def profile(name: str, line: LineString) -> dict:
        count = 61
        distances = np.linspace(0, line.length, count)
        coordinates = np.array([
            [line.interpolate(float(distance)).x, line.interpolate(float(distance)).y]
            for distance in distances
        ])
        elevations = np.asarray(
            interpolator(coordinates[:, 0], coordinates[:, 1]),
            dtype=float,
        )
        nearest_distances, _ = tree.query(coordinates, k=1)
        if not np.all(np.isfinite(elevations)):
            raise RuntimeError(f"{name} profile extends outside MDT interpolation hull")
        start_z = float(elevations[0])
        end_z = float(elevations[-1])
        delta = end_z - start_z
        bearing = (
            math.degrees(math.atan2(direction_a[0], direction_a[1])) + 360
        ) % 180 if name == "A-A" else (
            math.degrees(math.atan2(direction_b[0], direction_b[1])) + 360
        ) % 180
        simplified_indexes = np.linspace(0, count - 1, 31).astype(int)
        return {
            "name": name,
            "length_m": round(float(line.length), 2),
            "bearing_deg": round(float(bearing), 1),
            "start_elevation_m": round(start_z, 3),
            "end_elevation_m": round(end_z, 3),
            "delta_elevation_m": round(delta, 3),
            "average_slope_pct": round(delta / float(line.length) * 100, 2),
            "min_elevation_m": round(float(np.min(elevations)), 3),
            "max_elevation_m": round(float(np.max(elevations)), 3),
            "amplitude_m": round(float(np.max(elevations) - np.min(elevations)), 3),
            "nearest_ground_point_p90_m": round(float(np.percentile(nearest_distances, 90)), 2),
            "nearest_ground_point_max_m": round(float(np.max(nearest_distances)), 2),
            "samples": [
                {
                    "distance_m": round(float(distances[index]), 2),
                    "elevation_m": round(float(elevations[index]), 3),
                    "nearest_ground_point_m": round(float(nearest_distances[index]), 2),
                }
                for index in simplified_indexes
            ],
        }

    axis_a = parcel_axis_line(parcel, direction_a)
    axis_b = parcel_axis_line(parcel, direction_b)
    profile_a = profile("A-A", axis_a)
    profile_b = profile("B-B", axis_b)

    spacing = 1.0
    grid_x = np.arange(parcel.bounds[0], parcel.bounds[2] + spacing / 2, spacing)
    grid_y = np.arange(parcel.bounds[1], parcel.bounds[3] + spacing / 2, spacing)
    grid = np.array([
        (gx, gy)
        for gy in grid_y
        for gx in grid_x
        if parcel.contains(Point(float(gx), float(gy)))
    ])
    grid_z = np.asarray(interpolator(grid[:, 0], grid[:, 1]), dtype=float)
    grid_nearest, _ = tree.query(grid, k=1)
    valid = np.isfinite(grid_z)
    if not np.any(valid):
        raise RuntimeError("no valid parcel terrain samples")

    p90 = float(np.percentile(grid_nearest[valid], 90))
    quality = (
        "INTERPOLATED_SPARSE_GROUND_RETURNS"
        if p90 > 10
        else "INTERPOLATED_FROM_LIDAR_GROUND_POINTS"
    )
    return {
        "available": True,
        "crs": "EPSG:31983",
        "horizontal_datum": "SIRGAS 2000",
        "vertical_datum": "Imbituba / MAPGEO2015",
        "method": (
            "GeoSampa MDT 2020 LAZ ground-point TIN interpolation; "
            "parcel grid 1 m; A-A longest oriented parcel axis; "
            "B-B perpendicular through centroid."
        ),
        "quality": quality,
        "parcel_area_geometry_m2": round(float(parcel.area), 2),
        "local_ground_points": int(len(local_z)),
        "grid_samples": int(np.sum(valid)),
        "min_elevation_m": round(float(np.min(grid_z[valid])), 3),
        "max_elevation_m": round(float(np.max(grid_z[valid])), 3),
        "mean_elevation_m": round(float(np.mean(grid_z[valid])), 3),
        "amplitude_m": round(float(np.max(grid_z[valid]) - np.min(grid_z[valid])), 3),
        "nearest_ground_point_median_m": round(float(np.percentile(grid_nearest[valid], 50)), 2),
        "nearest_ground_point_p90_m": round(p90, 2),
        "nearest_ground_point_max_m": round(float(np.max(grid_nearest[valid])), 2),
        "profiles": [profile_a, profile_b],
        "caveat": (
            "Produto derivado de MDT LiDAR oficial, não substitui levantamento "
            "topográfico de campo/RTK/estação total. Em áreas edificadas, o MDT "
            "pode exigir interpolação entre retornos de solo ao redor da construção."
        ),
    }


def resolve_terrain_context(lat: float, lng: float, parcel_geometry: dict) -> dict:
    cache_key = (
        round(lat, 6),
        round(lng, 6),
        json.dumps(parcel_geometry, sort_keys=True, separators=(",", ":")),
    )
    cached = _TERRAIN_RESULT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    tiles = fetch_point_layer("terrain_tile", lat, lng)
    if not tiles:
        result = {
            "available": False,
            "reason": "mdt_2020_tile_not_found",
        }
        _TERRAIN_RESULT_CACHE[cache_key] = result
        return result

    props = tiles[0].get("properties") or {}
    tile_code = props.get("cd_quadricula")
    manifest = ensure_mdt_2020_tile(tile_code)
    analysis = analyze_mdt_for_parcel(
        parcel_geometry,
        TERRAIN_CACHE_DIR / manifest["laz_file"],
    )
    analysis["tile"] = {
        "code": tile_code,
        "year": props.get("an_levantamento"),
        "survey": props.get("tx_levantamento"),
        "scale": props.get("cd_escala_quadricula"),
        "source": props.get("sg_fonte_original"),
        "zip_sha256": manifest.get("zip_sha256"),
        "laz_sha256": manifest.get("laz_sha256"),
        "captured_at": manifest.get("captured_at"),
    }
    _TERRAIN_RESULT_CACHE[cache_key] = analysis
    if len(_TERRAIN_RESULT_CACHE) > 128:
        first_key = next(iter(_TERRAIN_RESULT_CACHE))
        _TERRAIN_RESULT_CACHE.pop(first_key, None)
    return analysis


def fetch_point_layer(key: str, lat: float, lng: float) -> list[dict]:
    config = THEMATIC_LAYERS[key]
    delta = 0.0007
    bbox = f"{lng-delta},{lat-delta},{lng+delta},{lat+delta},EPSG:4326"
    query = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": config["type_name"],
        "srsName": "EPSG:4326",
        "bbox": bbox,
        "count": "60",
        "propertyName": ",".join([config["geometry"], *config["fields"]]),
        "outputFormat": "application/json",
    }
    url = WFS + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read(4 * 1024 * 1024 + 1)
        if response.status != 200:
            raise RuntimeError(
                f"GeoSampa {config['type_name']} returned HTTP {response.status}"
            )
        if len(body) > 4 * 1024 * 1024:
            raise RuntimeError(
                f"GeoSampa {config['type_name']} exceeded safety limit"
            )
    payload = json.loads(body)
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError(
            f"GeoSampa {config['type_name']} did not return FeatureCollection"
        )
    output = []
    for feature in payload.get("features") or []:
        if contains_point(feature, lng, lat):
            props = feature.get("properties") or {}
            unexpected = set(props) - set(config["fields"])
            if unexpected:
                raise RuntimeError(
                    f"GeoSampa {config['type_name']} returned unexpected fields: "
                    + ", ".join(sorted(unexpected))
                )
            output.append({
                "id": feature.get("id"),
                "properties": props,
            })
    return output



def load_pgv_index() -> dict:
    global _PGV_INDEX_CACHE
    if _PGV_INDEX_CACHE is None:
        payload = json.loads(PGV_INDEX_PATH.read_text(encoding="utf-8"))
        if payload.get("source_id") != "sp-sao-paulo-pgv-2026":
            raise ValueError("unexpected PGV source")
        if payload.get("annex") != "II":
            raise ValueError("PGV index is not Annex II")
        records = payload.get("records")
        if not isinstance(records, dict) or len(records) < 100_000:
            raise ValueError("PGV index failed record-count validation")
        _PGV_INDEX_CACHE = payload
    return _PGV_INDEX_CACHE


def resolve_pgv(parcel: dict) -> dict:
    props = parcel.get("properties") or {}
    codlog = props.get("street_code")
    sector = props.get("fiscal_sector")
    block = props.get("fiscal_block")
    if not all(isinstance(value, str) and value for value in (codlog, sector, block)):
        return {
            "found": False,
            "reason": "parcel_missing_codlog_or_sq",
        }
    sq = f"{sector}{block}"
    key = f"{codlog}:{sq}"
    index = load_pgv_index()
    value = index["records"].get(key)
    return {
        "found": value is not None,
        "codlog": codlog,
        "sq": sq,
        "key": key,
        "vm2t_brl_per_m2": value,
        "law": index.get("law"),
        "effective_from": index.get("effective_from"),
        "annex": index.get("annex"),
        "source_id": index.get("source_id"),
        "source_pdf_sha256": index.get("source_pdf_sha256"),
        "record_count": index.get("record_count"),
        "interpretation": (
            "Valor unitário de terreno da PGV. Não é, isoladamente, "
            "valor venal do imóvel nem valor do IPTU."
        ),
    }


def resolve_iptu_cadastre(parcel: dict, history_limit: int = 8) -> dict:
    sql = (parcel.get("properties") or {}).get("sql_reference")
    if not sql or not re.fullmatch(r"\d{11}", sql):
        return {
            "available": IPTU_DB_PATH.exists(),
            "found": False,
            "records": [],
            "reason": "parcel_without_sql",
        }
    if not IPTU_DB_PATH.exists():
        return {
            "available": False,
            "found": False,
            "records": [],
            "reason": "iptu_index_not_materialized",
        }

    uri = f"file:{IPTU_DB_PATH}?mode=ro&immutable=1"
    db = sqlite3.connect(uri, uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            """
            SELECT exercise, notice_number, registration_date, condominium,
                   street_code, street, number, complement, neighborhood,
                   reference, cep, corner_front_count, ideal_fraction,
                   land_area_m2, built_area_m2, occupied_area_m2,
                   land_unit_value_brl_m2,
                   construction_unit_value_brl_m2,
                   corrected_construction_year, floors, frontage_m,
                   use_description, construction_pattern, terrain_type,
                   obsolescence_factor, life_start_year, life_start_month,
                   contributor_phase, source_zip_sha256
            FROM cadastre
            WHERE sql = ?
            ORDER BY exercise DESC
            LIMIT ?
            """,
            (sql, history_limit),
        ).fetchall()
    finally:
        db.close()

    records = [dict(row) for row in rows]
    return {
        "available": True,
        "found": bool(records),
        "count": len(records),
        "records": records,
        "latest": records[0] if records else None,
        "source_id": "sp-sao-paulo-iptu-cadastro-fiscal",
        "interpretation": (
            "Cadastro fiscal IPTU da Emissão Geral do exercício. Campos "
            "cadastrais e valores unitários são inputs fiscais; não equivalem "
            "isoladamente ao valor final do IPTU nem a levantamento físico atual."
        ),
        "privacy": (
            "Consulta usa o arquivo bulk público IPTU_INTER. O LoteDiretor não "
            "materializa nem publica nome de proprietário/possuidor nesta ficha."
        ),
    }


def resolve_itbi_history(parcel: dict, limit: int = 12) -> dict:
    sql = (parcel.get("properties") or {}).get("sql_reference")
    if not sql or not re.fullmatch(r"\d{11}", sql):
        return {
            "available": ITBI_DB_PATH.exists(),
            "count": 0,
            "transactions": [],
            "registry_references": [],
            "reason": "parcel_without_sql",
        }
    if not ITBI_DB_PATH.exists():
        return {
            "available": False,
            "count": 0,
            "transactions": [],
            "registry_references": [],
            "reason": "itbi_index_not_materialized",
        }

    uri = f"file:{ITBI_DB_PATH}?mode=ro&immutable=1"
    db = sqlite3.connect(uri, uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        coverage_years = [
            row[0] for row in db.execute(
                "SELECT year FROM source_files ORDER BY year"
            ).fetchall()
        ]
        count = db.execute(
            "SELECT COUNT(*) FROM transactions WHERE sql = ?",
            (sql,),
        ).fetchone()[0]
        rows = db.execute(
            """
            SELECT source_year, source_sheet, transaction_date,
                   transaction_nature, transaction_value, vvr,
                   transmitted_pct, vvr_proportional, tax_base,
                   financing_type, financed_value,
                   registry_office, registry_number, sql_status,
                   land_area_m2, frontage_m, ideal_fraction,
                   built_area_m2, use_code, use_description,
                   pattern_code, pattern_description, construction_year,
                   street, number, complement, neighborhood, cep,
                   source_file_sha256
            FROM transactions
            WHERE sql = ?
            ORDER BY COALESCE(transaction_date, '') DESC,
                     source_year DESC, source_row DESC
            LIMIT ?
            """,
            (sql, limit),
        ).fetchall()
    finally:
        db.close()

    transactions = [dict(row) for row in rows]
    registry_refs = []
    seen = set()
    for tx in transactions:
        office = tx.get("registry_office")
        number = tx.get("registry_number")
        if not office or not number:
            continue
        key = (office, number)
        if key in seen:
            continue
        seen.add(key)
        registry_refs.append({
            "registry_office": office,
            "registry_number": number,
            "transaction_date": tx.get("transaction_date"),
            "source_year": tx.get("source_year"),
        })

    return {
        "available": True,
        "count": count,
        "coverage_years": coverage_years,
        "transactions": transactions,
        "registry_references": registry_refs,
        "source_id": "sp-sao-paulo-itbi-transactions",
        "interpretation": (
            "Cada registro é uma DTI com ITBI efetivamente pago no mês "
            "de referência. Matrícula/cartório são referências declaradas "
            "na DTI e não substituem certidão registral atualizada."
        ),
        "privacy": (
            "O índice público não materializa nomes de compradores/vendedores "
            "nem CPF/CNPJ."
        ),
    }


def load_utility_context() -> dict:
    resolver = json.loads(UTILITY_RESOLVER_PATH.read_text(encoding="utf-8"))
    registry = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    source_map = {item["id"]: item for item in registry["sources"]}
    city = next(
        item for item in resolver["municipalities"]
        if item.get("ibge") == "3550308"
    )
    output = {}
    for service_type, entries in city["services"].items():
        normalized = []
        for entry in entries:
            source_id = entry.get("provider_source_id")
            source = source_map.get(source_id) or {}
            normalized.append({
                "service_type": service_type,
                "provider_source_id": source_id,
                "provider_authority": source.get("authority"),
                "role": entry.get("role"),
                "evidence_level": entry.get("evidence_level"),
                "technical_source_ids": entry.get("technical_source_ids") or [],
                "missing": entry.get("missing") or [],
                "caveat": entry.get("caveat") or entry.get("note"),
            })
        output[service_type] = normalized
    return output


def build_context(lat: float, lng: float, parcel_geometry: dict, parcel: dict) -> dict:
    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(fetch_point_layer, key, lat, lng): key
            for key in THEMATIC_LAYERS
        }
        futures[pool.submit(fetch_buildings_for_parcel, parcel_geometry)] = "__buildings__"
        futures[
            pool.submit(
                fetch_housing_permits,
                (parcel.get("properties") or {}).get("sql_reference"),
            )
        ] = "__housing_permits__"
        futures[
            pool.submit(resolve_terrain_context, lat, lng, parcel_geometry)
        ] = "__terrain__"
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                errors[key] = type(exc).__name__
                results[key] = []

    zoning = (results.get("zoning") or [None])[0]
    macroarea = (results.get("macroarea") or [None])[0]
    macrozone = (results.get("macrozone") or [None])[0]

    return {
        "planning": {
            "zoning": zoning,
            "macroarea": macroarea,
            "macrozone": macrozone,
        },
        "buildings": results.get("__buildings__") or [],
        "terrain": results.get("__terrain__") or {
            "available": False,
            "reason": errors.get("__terrain__") or "not_available",
        },
        "licensing": {
            "housing_permits_exact_sql": results.get("__housing_permits__") or [],
            "impact_spatial_incidence": results.get("impact_license") or [],
            "environment_spatial_incidence": results.get("environment_license") or [],
            "interpretation": (
                "Exact SQL matches are property-linked. Polygon intersections "
                "are spatial incidence only and must not be described as a "
                "parcel-specific license without an official identifier link."
            ),
        },
        "risk": {
            "geological": results.get("geological_risk") or [],
            "hydrological": results.get("hydrological_risk") or [],
        },
        "heritage": {
            "assets": results.get("heritage_asset") or [],
            "buffers": {
                "CONPRESP": results.get("heritage_buffer_conpresp") or [],
                "CONDEPHAAT": results.get("heritage_buffer_condephaat") or [],
                "IPHAN": results.get("heritage_buffer_iphan") or [],
            },
        },
        "utilities": load_utility_context(),
        "fiscal": {
            "pgv": resolve_pgv(parcel),
            "iptu": resolve_iptu_cadastre(parcel),
            "itbi": resolve_itbi_history(parcel),
        },
        "query_errors": errors,
        "queried_at": utc_now(),
        "source": "Prefeitura de São Paulo / GeoSampa WFS",
    }


def public_feature(feature: dict) -> dict:
    props = feature.get("properties") or {}
    return {
        "type": "Feature",
        "id": feature.get("id"),
        "geometry": feature.get("geometry"),
        "properties": {
            "municipal_parcel_feature_id": props.get("cd_identificador"),
            "municipal_original_parcel_id": props.get("cd_identificador_original_lote"),
            "fiscal_sector": props.get("cd_setor_fiscal"),
            "fiscal_block": props.get("cd_quadra_fiscal"),
            "fiscal_subblock": props.get("cd_subquadra_fiscal"),
            "fiscal_lot": props.get("cd_lote"),
            "fiscal_digit": props.get("cd_digito_sql"),
            "condominium_code": props.get("cd_condominio"),
            "sql_reference": sql_reference(props),
            "cib": props.get("cd_cib"),
            "cib_status": props.get("tx_situacao_cib"),
            "street_code": props.get("cd_logradouro"),
            "street": props.get("nm_logradouro_completo"),
            "number": props.get("cd_numero_porta"),
            "complement": props.get("tx_complemento_endereco"),
            "land_area_m2": props.get("qt_area_terreno"),
            "built_area_m2": props.get("qt_area_construida"),
            "use_code": props.get("cd_tipo_uso_imovel"),
            "use_description": props.get("dc_tipo_uso_imovel"),
            "parcel_type": props.get("tx_tipo_lote"),
            "parcel_status": props.get("tx_situ_lote"),
        },
    }


def load_report_contract() -> tuple[dict, dict]:
    spec = json.loads(REPORT_SPEC_PATH.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    city = next(item for item in matrix["first_wave"] if item.get("ibge") == "3550308")
    return spec, {row["field"]: row for row in city["rows"]}


def actual_values_for_section(
    section_id: str,
    parcel: dict,
    context: dict,
) -> list[dict]:
    p = parcel["properties"]
    address = ", ".join(filter(None, [p.get("street"), p.get("number")])) or None
    planning = context.get("planning") or {}
    zoning = (planning.get("zoning") or {}).get("properties") or {}
    macroarea = (planning.get("macroarea") or {}).get("properties") or {}
    macrozone = (planning.get("macrozone") or {}).get("properties") or {}
    risk = context.get("risk") or {}
    heritage = context.get("heritage") or {}

    if section_id == "executive_summary":
        values = [
            {"label": "Endereço", "value": address},
            {"label": "SQL", "value": p.get("sql_reference")},
            {"label": "CIB", "value": p.get("cib")},
            {"label": "Área do terreno", "value": p.get("land_area_m2"), "unit": "m²"},
            {"label": "Área construída fiscal", "value": p.get("built_area_m2"), "unit": "m²"},
            {"label": "Uso cadastral", "value": p.get("use_description")},
            {"label": "Zona", "value": zoning.get("cd_zoneamento_perimetro")},
            {"label": "Macroárea", "value": macroarea.get("nm_macroarea")},
            {
                "label": "PGV 2026 · terreno",
                "value": (context.get("fiscal") or {}).get("pgv", {}).get("vm2t_brl_per_m2"),
                "unit": "BRL/m²",
            },
            {
                "label": "Pavimentos · IPTU",
                "value": ((context.get("fiscal") or {}).get("iptu") or {}).get("latest", {}).get("floors"),
            },
            {
                "label": "Ano construção · IPTU",
                "value": ((context.get("fiscal") or {}).get("iptu") or {}).get("latest", {}).get("corrected_construction_year"),
            },
        ]
        return values

    if section_id == "identity_location":
        iptu = ((context.get("fiscal") or {}).get("iptu") or {}).get("latest") or {}
        terrain = context.get("terrain") or {}
        values = [
            {"label": "SQL", "value": p.get("sql_reference")},
            {"label": "CIB", "value": p.get("cib")},
            {"label": "Situação CIB", "value": p.get("cib_status")},
            {"label": "Situação cartográfica do lote", "value": p.get("parcel_status")},
            {"label": "Setor", "value": p.get("fiscal_sector")},
            {"label": "Quadra", "value": p.get("fiscal_block")},
            {"label": "Lote", "value": p.get("fiscal_lot")},
            {"label": "Endereço", "value": address},
            {"label": "Complemento GeoSampa", "value": p.get("complement")},
            {"label": "Bairro · IPTU", "value": iptu.get("neighborhood")},
            {"label": "CEP · IPTU", "value": iptu.get("cep")},
            {"label": "Data do cadastramento · IPTU", "value": iptu.get("registration_date")},
            {"label": "Área terreno · cadastro fiscal", "value": iptu.get("land_area_m2") or p.get("land_area_m2"), "unit": "m²"},
            {"label": "Área geométrica calculada · lote", "value": terrain.get("parcel_area_geometry_m2"), "unit": "m²"},
            {"label": "Testada para cálculo · IPTU", "value": iptu.get("frontage_m"), "unit": "m"},
            {"label": "Frentes/esquinas · IPTU", "value": iptu.get("corner_front_count")},
            {"label": "Fração ideal · IPTU", "value": iptu.get("ideal_fraction")},
            {"label": "Condomínio · IPTU", "value": iptu.get("condominium")},
        ]
        cadastral_area = iptu.get("land_area_m2") or p.get("land_area_m2")
        geometry_area = terrain.get("parcel_area_geometry_m2")
        if isinstance(cadastral_area, (int, float)) and isinstance(geometry_area, (int, float)):
            values.append({
                "label": "Divergência área GIS x cadastro",
                "value": round(geometry_area - cadastral_area, 2),
                "unit": "m²",
            })
            if cadastral_area:
                values.append({
                    "label": "Divergência relativa área GIS x cadastro",
                    "value": round((geometry_area - cadastral_area) / cadastral_area * 100, 2),
                    "unit": "%",
                })
        return values

    if section_id == "building_existing":
        buildings = context.get("buildings") or []
        iptu = ((context.get("fiscal") or {}).get("iptu") or {}).get("latest") or {}
        heights = [
            item.get("properties", {}).get("qt_altura_edificacao")
            for item in buildings
            if isinstance(
                item.get("properties", {}).get("qt_altura_edificacao"),
                (int, float),
            )
        ]
        updates = [
            item.get("properties", {}).get("dt_atualizacao")
            for item in buildings
            if item.get("properties", {}).get("dt_atualizacao")
        ]
        return [
            {"label": "Área construída fiscal", "value": iptu.get("built_area_m2") or p.get("built_area_m2"), "unit": "m²"},
            {"label": "Área ocupada · IPTU", "value": iptu.get("occupied_area_m2"), "unit": "m²"},
            {"label": "Pavimentos · IPTU", "value": iptu.get("floors")},
            {"label": "Ano construção corrigido · IPTU", "value": iptu.get("corrected_construction_year")},
            {"label": "Uso cadastral · IPTU", "value": iptu.get("use_description") or p.get("use_description")},
            {"label": "Padrão construtivo · IPTU", "value": iptu.get("construction_pattern")},
            {"label": "Tipo de terreno · IPTU", "value": iptu.get("terrain_type")},
            {"label": "Fator de obsolescência · IPTU", "value": iptu.get("obsolescence_factor")},
            {"label": "Tipo de lote · GeoSampa", "value": p.get("parcel_type")},
            {"label": "Situação do lote · GeoSampa", "value": p.get("parcel_status")},
            {"label": "Footprints cartográficos no lote", "value": len(buildings)},
            {
                "label": "Maior altura cartográfica entre footprints intersectantes",
                "value": round(max(heights), 2) if heights else None,
                "unit": "m",
            },
            {
                "label": "Atualização mais recente do footprint",
                "value": max(updates) if updates else None,
            },
            {
                "label": "Ressalva temporal",
                "value": (
                    "Edificações 2D são cartografia histórica. Footprints são "
                    "mostrados por interseção espacial e não equivalem "
                    "automaticamente à geometria predial atual/licenciada nem "
                    "à área construída fiscal."
                ),
            },
        ]

    if section_id == "planning_buildability":
        law_no = zoning.get("cd_numero_legislacao_zoneamento")
        law_year = zoning.get("an_legislacao_zoneamento")
        law = f"Lei {int(law_no):,}/{int(law_year)}".replace(",", ".") if law_no and law_year else None
        return [
            {"label": "Zona vigente", "value": zoning.get("cd_zoneamento_perimetro")},
            {"label": "Descrição da zona", "value": zoning.get("tx_zoneamento_perimetro")},
            {"label": "Base legal", "value": law},
            {"label": "Atualização da camada", "value": zoning.get("dt_atualizacao")},
            {"label": "Macroárea", "value": macroarea.get("nm_macroarea")},
            {"label": "Sigla da macroárea", "value": macroarea.get("sg_macroarea")},
            {
                "label": "Macrozona",
                "value": macrozone.get("tx_macro_divisao_pde")
                or macrozone.get("nm_perimetro_divisao_pde"),
            },
        ]

    if section_id == "fiscal_market":
        fiscal = context.get("fiscal") or {}
        pgv = fiscal.get("pgv") or {}
        itbi = fiscal.get("itbi") or {}
        values = []
        iptu_data = fiscal.get("iptu") or {}
        iptu = iptu_data.get("latest") or {}
        if iptu:
            values.extend([
                {"label": "Cadastro IPTU 2026", "value": "Encontrado no bulk público IPTU_INTER"},
                {"label": "Valor unitário terreno · IPTU", "value": iptu.get("land_unit_value_brl_m2"), "unit": "BRL/m²"},
                {"label": "Valor unitário construção · IPTU", "value": iptu.get("construction_unit_value_brl_m2"), "unit": "BRL/m²"},
                {"label": "Área terreno · IPTU", "value": iptu.get("land_area_m2"), "unit": "m²"},
                {"label": "Área construída · IPTU", "value": iptu.get("built_area_m2"), "unit": "m²"},
                {"label": "Área ocupada · IPTU", "value": iptu.get("occupied_area_m2"), "unit": "m²"},
                {"label": "Testada · IPTU", "value": iptu.get("frontage_m"), "unit": "m"},
                {"label": "Pavimentos · IPTU", "value": iptu.get("floors")},
                {"label": "Ano construção corrigido · IPTU", "value": iptu.get("corrected_construction_year")},
                {"label": "Padrão construtivo · IPTU", "value": iptu.get("construction_pattern")},
                {"label": "Fator de obsolescência · IPTU", "value": iptu.get("obsolescence_factor")},
                {"label": "Observação IPTU", "value": iptu_data.get("interpretation")},
            ])
        else:
            values.append({"label": "Cadastro IPTU", "value": "SQL não localizado no índice fiscal materializado."})

        if pgv.get("found"):
            values.extend([
                {
                    "label": "PGV 2026 · valor unitário de terreno",
                    "value": pgv.get("vm2t_brl_per_m2"),
                    "unit": "BRL/m²",
                },
                {
                    "label": "Chave PGV · Codlog / SQ",
                    "value": f"{pgv.get('codlog')} / {pgv.get('sq')}",
                },
                {"label": "Base legal PGV", "value": pgv.get("law")},
                {"label": "Vigência PGV", "value": pgv.get("effective_from")},
            ])
        else:
            values.append({
                "label": "PGV 2026",
                "value": "Valor unitário não localizado para a chave cadastral do lote.",
            })

        txs = itbi.get("transactions") or []
        coverage_years = itbi.get("coverage_years") or []
        if coverage_years:
            coverage_label = (
                f"{min(coverage_years)}–{max(coverage_years)}"
                if len(coverage_years) > 1
                else str(coverage_years[0])
            )
        else:
            coverage_label = "sem índice"
        values.append({
            "label": f"DTIs/ITBI encontradas · {coverage_label}",
            "value": itbi.get("count", 0),
        })
        if not txs:
            values.append({
                "label": "Histórico ITBI",
                "value": (
                    "Nenhuma DTI paga encontrada para este SQL no índice "
                    f"público materializado de {coverage_label}."
                ),
            })
        for idx, tx in enumerate(txs[:5], start=1):
            prefix = f"ITBI #{idx}"
            values.extend([
                {"label": f"{prefix} · data da transação", "value": tx.get("transaction_date")},
                {"label": f"{prefix} · natureza", "value": tx.get("transaction_nature")},
                {"label": f"{prefix} · valor declarado", "value": tx.get("transaction_value"), "unit": "BRL"},
                {"label": f"{prefix} · VVR", "value": tx.get("vvr"), "unit": "BRL"},
                {"label": f"{prefix} · base de cálculo", "value": tx.get("tax_base"), "unit": "BRL"},
                {"label": f"{prefix} · proporção transmitida", "value": tx.get("transmitted_pct"), "unit": "%"},
                {"label": f"{prefix} · financiamento", "value": tx.get("financing_type")},
                {"label": f"{prefix} · valor financiado", "value": tx.get("financed_value"), "unit": "BRL"},
                {"label": f"{prefix} · cartório", "value": tx.get("registry_office")},
                {"label": f"{prefix} · matrícula", "value": tx.get("registry_number")},
            ])

        if txs:
            latest = txs[0]
            values.extend([
                {"label": "Situação do SQL · snapshot IPTU/DTI mais recente", "value": latest.get("sql_status")},
                {"label": "Testada · snapshot IPTU/DTI", "value": latest.get("frontage_m"), "unit": "m"},
                {"label": "Fração ideal · snapshot IPTU/DTI", "value": latest.get("ideal_fraction")},
                {"label": "Área terreno · snapshot IPTU/DTI", "value": latest.get("land_area_m2"), "unit": "m²"},
                {"label": "Área construída · snapshot IPTU/DTI", "value": latest.get("built_area_m2"), "unit": "m²"},
                {"label": "Uso IPTU · snapshot DTI", "value": latest.get("use_description")},
                {"label": "Padrão IPTU · snapshot DTI", "value": latest.get("pattern_description")},
                {"label": "ACC / ano construção · snapshot DTI", "value": latest.get("construction_year")},
            ])

        values.extend([
            {"label": "Interpretação ITBI", "value": itbi.get("interpretation")},
            {"label": "Privacidade", "value": itbi.get("privacy")},
        ])
        return values

    if section_id == "licensing_history":
        licensing = context.get("licensing") or {}
        values = []
        exact = licensing.get("housing_permits_exact_sql") or []
        for item in exact:
            props = item.get("properties") or {}
            values.extend([
                {"label": "Alvará HIS/HMP · assunto", "value": props.get("tx_assunto_alvara")},
                {"label": "Processo de execução", "value": props.get("cd_numero_processo_execucao")},
                {"label": "Documento", "value": props.get("cd_numero_documento_execucao")},
                {"label": "Data de deferimento", "value": props.get("dt_deferimento_execucao")},
                {"label": "Área construída licenciada", "value": props.get("qt_area_construida_total"), "unit": "m²"},
                {"label": "Unidades HIS", "value": props.get("qt_unidade_his")},
                {"label": "Unidades HMP", "value": props.get("qt_unidade_hmp")},
            ])
        impact = licensing.get("impact_spatial_incidence") or []
        for item in impact:
            props = item.get("properties") or {}
            values.extend([
                {"label": "Incidência espacial · processo EIV/impacto", "value": props.get("cd_processo_administrativo")},
                {"label": "Status publicado", "value": props.get("st_licenca_empreendimento")},
                {"label": "Categoria", "value": props.get("tx_categoria_ocupacao")},
                {"label": "Publicação", "value": props.get("dt_publicacao_doc")},
            ])
        environmental = licensing.get("environment_spatial_incidence") or []
        for item in environmental:
            props = item.get("properties") or {}
            values.extend([
                {"label": "Incidência espacial · licença ambiental", "value": props.get("cd_numero_licenca_expedida") or props.get("cd_licenca_ambiental_expedida")},
                {"label": "Descrição publicada", "value": props.get("nm_descricao_licenca")},
                {"label": "Processo ambiental", "value": props.get("cd_processo_administrativo_licenca")},
                {"label": "Expedição", "value": props.get("dt_expedicao_licenca")},
                {"label": "Validade publicada", "value": props.get("dt_validade_licenca_expedida")},
                {"label": "Tipo de estudo", "value": props.get("tp_estudo_licenca")},
            ])
        if not exact:
            values.append({
                "label": "Alvará HIS/HMP por SQL",
                "value": "Nenhum registro exato encontrado na camada pública consultada.",
            })
        values.append({
            "label": "Limite da consulta",
            "value": licensing.get("interpretation"),
        })
        return values

    if section_id == "infrastructure_utilities":
        labels = {
            "electricity": "Energia elétrica",
            "gas": "Gás canalizado",
            "water_sewer": "Água e esgoto",
            "telecom": "Telecom",
            "drainage": "Drenagem",
        }
        values = []
        utilities = context.get("utilities") or {}
        for service_type in [
            "electricity", "gas", "water_sewer", "telecom", "drainage"
        ]:
            for entry in utilities.get(service_type) or []:
                provider = entry.get("provider_authority") or entry.get("provider_source_id")
                evidence = entry.get("evidence_level")
                values.append({
                    "label": f"{labels[service_type]} · referência",
                    "value": provider,
                })
                values.append({
                    "label": f"{labels[service_type]} · evidência",
                    "value": evidence,
                })
        values.append({
            "label": "Limite de interpretação",
            "value": (
                "Prestador/território ou contexto de rede não comprovam "
                "ligação, disponibilidade ou capacidade técnica no lote."
            ),
        })
        return values

    if section_id == "terrain_visual":
        terrain = context.get("terrain") or {}
        if not terrain.get("available"):
            return [{
                "label": "MDT/LiDAR 2020",
                "value": "Análise altimétrica não disponível para este lote nesta consulta.",
            }]
        tile = terrain.get("tile") or {}
        profiles = terrain.get("profiles") or []
        values = [
            {"label": "Folha MDT 2020", "value": tile.get("code")},
            {"label": "Levantamento", "value": tile.get("survey")},
            {"label": "Datum vertical", "value": terrain.get("vertical_datum")},
            {"label": "Cota mínima derivada", "value": terrain.get("min_elevation_m"), "unit": "m"},
            {"label": "Cota máxima derivada", "value": terrain.get("max_elevation_m"), "unit": "m"},
            {"label": "Cota média derivada", "value": terrain.get("mean_elevation_m"), "unit": "m"},
            {"label": "Amplitude altimétrica derivada", "value": terrain.get("amplitude_m"), "unit": "m"},
            {"label": "Qualidade da interpolação", "value": terrain.get("quality")},
            {"label": "Distância P90 ao retorno de solo", "value": terrain.get("nearest_ground_point_p90_m"), "unit": "m"},
        ]
        for profile in profiles:
            name = profile.get("name")
            values.extend([
                {"label": f"Corte {name} · comprimento", "value": profile.get("length_m"), "unit": "m"},
                {"label": f"Corte {name} · rumo", "value": profile.get("bearing_deg"), "unit": "°"},
                {"label": f"Corte {name} · desnível início→fim", "value": profile.get("delta_elevation_m"), "unit": "m"},
                {"label": f"Corte {name} · inclinação média", "value": profile.get("average_slope_pct"), "unit": "%"},
            ])
        values.append({"label": "Limite topográfico", "value": terrain.get("caveat")})
        return values

    if section_id == "registry_due_diligence":
        itbi = (context.get("fiscal") or {}).get("itbi") or {}
        refs = itbi.get("registry_references") or []
        registry_years = itbi.get("coverage_years") or []
        registry_coverage_label = (
            f"{min(registry_years)}–{max(registry_years)}"
            if len(registry_years) > 1
            else (str(registry_years[0]) if registry_years else "sem índice")
        )
        values = []
        for idx, ref in enumerate(refs[:8], start=1):
            values.extend([
                {
                    "label": f"Referência registral pública #{idx} · cartório",
                    "value": ref.get("registry_office"),
                },
                {
                    "label": f"Referência registral pública #{idx} · matrícula",
                    "value": ref.get("registry_number"),
                },
                {
                    "label": f"Referência registral pública #{idx} · transação",
                    "value": ref.get("transaction_date"),
                },
            ])
        if not refs:
            values.append({
                "label": "Referência matrícula/cartório via ITBI",
                "value": (
                    "Nenhuma referência encontrada para este SQL no índice "
                    f"ITBI público de {registry_coverage_label}."
                ),
            })
        values.append({
            "label": "Titular / proprietário atual",
            "value": (
                "Não publicado na ficha pública. Obter somente por certidão/"
                "matrícula atualizada ou documento fornecido pelo usuário em "
                "fluxo privado/autorizado."
            ),
        })
        values.append({
            "label": "Limite registral",
            "value": (
                "A matrícula informada em DTI é uma referência histórica "
                "pública. Certidão/matrícula atualizada, titularidade, ônus e "
                "averbações permanecem no fluxo privado sob demanda."
            ),
        })
        return values

    if section_id == "environment_risk_heritage":
        values = []
        for item in risk.get("geological") or []:
            props = item.get("properties") or {}
            values.extend([
                {"label": "Risco geológico", "value": props.get("tx_grau_de_risco_geologico")},
                {"label": "Processo geológico", "value": props.get("tx_tipo_processo_geologico")},
                {"label": "Data de vistoria (risco geo.)", "value": props.get("dt_vistoria")},
            ])
        for item in risk.get("hydrological") or []:
            props = item.get("properties") or {}
            values.extend([
                {"label": "Risco hidrológico", "value": props.get("tx_grau_risco_hidrologico")},
                {"label": "Processo hidrológico", "value": props.get("tx_tipo_processo")},
                {"label": "Bacia hidrográfica", "value": props.get("nm_bacia_hidrografica")},
            ])
        for item in heritage.get("assets") or []:
            props = item.get("properties") or {}
            values.extend([
                {"label": "Bem tombado", "value": props.get("nm_area_tombada")},
                {"label": "Situação do tombamento", "value": props.get("tx_situacao_tombamento")},
                {"label": "ZEPEC", "value": props.get("tx_zepec")},
            ])
        for authority, items in (heritage.get("buffers") or {}).items():
            for item in items:
                props = item.get("properties") or {}
                values.append({
                    "label": f"Área envoltória {authority}",
                    "value": props.get("nm_area") or "Incidência identificada",
                })
        if not values:
            values.append({
                "label": "Triagem espacial",
                "value": "Sem incidência nas camadas consultadas neste ponto",
            })
        return values

    return []


def build_report(parcel: dict, context: dict) -> dict:
    spec, rows = load_report_contract()
    sections = []
    for section in sorted(spec["sections"], key=lambda item: item["order"]):
        field_states = []
        for field in section.get("source_matrix_fields", []):
            row = rows.get(field)
            if not row:
                continue
            field_states.append({
                "field": field,
                "label": FIELD_LABELS.get(field, field),
                "status": row.get("status"),
                "source_id": row.get("source_id"),
                "connector_status": row.get("connector_status"),
                "access_class": row.get("access_class"),
                "missing_fields": row.get("missing_fields") or [],
            })
        values = [
            item for item in actual_values_for_section(section["id"], parcel, context)
            if item.get("value") not in (None, "")
        ]
        sections.append({
            "id": section["id"],
            "title": section["title"],
            "order": section["order"],
            "section_type": section.get("section_type"),
            "actual_values": values,
            "fields": field_states,
        })
    return {
        "title": spec["title"],
        "target_completion_level": spec["target_completion_level"],
        "principle": spec["principle"],
        "mode": "PUBLIC_PROPERTY_REPORT",
        "sections": sections,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "LoteDiretorParcelAPI/0.1"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/healthz":
            return self.send_json(200, {"ok": True, "service": "parcel-click"})

        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/v1/sp/search":
            query_text = params.get("q", [""])[0]
            try:
                matches = search_parcel(query_text)
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                print(f"search upstream error: {exc!r}", flush=True)
                return self.send_json(502, {"error": "upstream_unavailable"})
            return self.send_json(200, {
                "query": query_text,
                "count": len(matches),
                "matches": matches,
                "source": {
                    "id": "sp-sao-paulo-geosampa-wfs",
                    "layer": TYPE_NAME,
                    "authority": "Prefeitura de São Paulo / GeoSampa",
                },
            })

        if parsed.path != "/v1/sp/parcel":
            return self.send_json(404, {"error": "not_found"})

        try:
            lat = float(params.get("lat", [""])[0])
            lng = float(params.get("lng", [""])[0])
        except ValueError:
            return self.send_json(400, {"error": "invalid_coordinates"})

        if not (math.isfinite(lat) and math.isfinite(lng)):
            return self.send_json(400, {"error": "invalid_coordinates"})

        min_lng, min_lat, max_lng, max_lat = SP_BOUNDS
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            return self.send_json(400, {"error": "outside_sao_paulo_demo_bounds"})

        try:
            collection = fetch_candidates(lat, lng)
            features = collection.get("features") or []
            selected = next((f for f in features if contains_point(f, lng, lat)), None)
            if selected is None:
                return self.send_json(404, {
                    "error": "parcel_not_found",
                    "candidate_count": len(features),
                    "source": "GeoSampa lote_cidadao",
                })
            parcel = public_feature(selected)
            context = build_context(lat, lng, parcel["geometry"], parcel)
            return self.send_json(200, {
                "found": True,
                "clicked": {"lat": lat, "lng": lng},
                "feature": parcel,
                "context": context,
                "source": {
                    "id": "sp-sao-paulo-geosampa-wfs",
                    "authority": "Prefeitura de São Paulo / GeoSampa",
                    "layer": TYPE_NAME,
                    "license": "CC BY-SA 4.0",
                    "queried_at": utc_now(),
                    "method": "WFS 2.0 bbox candidate query + server-side point-in-polygon",
                },
                "report": build_report(parcel, context),
            })
        except Exception as exc:
            print(f"upstream error: {exc!r}", flush=True)
            return self.send_json(502, {"error": "upstream_unavailable"})


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LoteDiretor parcel API listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()
