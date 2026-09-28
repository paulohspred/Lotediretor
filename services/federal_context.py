#!/usr/bin/env python3
"""Read-only national/federal context for LoteDiretor parcels.

National layers complement, but never replace, higher-resolution municipal/state
sources. Calls use closed public-field allowlists and fail soft.
"""
from __future__ import annotations

import gzip
import json
import threading
import time
import urllib.parse
import urllib.request

import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform


DB_DSN = "dbname=lotediretor user=sentinelx host=/var/run/postgresql"
ANA_BASE = "https://www.snirh.gov.br/arcgis/rest/services/INDE/Camadas/MapServer"
ICMBIO_WFS = "https://geoservicos.inde.gov.br/geoserver/ICMBio/ows"
IBGE_AGGREGATES = "https://servicodados.ibge.gov.br/api/v3/agregados"
SICONFI_RREO = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"
SICONFI_ENTES = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes"
TRANSFERE_ESPECIAIS = "https://api-publica.transferegov.gestao.gov.br/especiais"
MAPBIOMAS_TIF = (
    "https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/"
    "collection11/lulc/coverage/brazil_coverage/"
    "brazil_coverage-col11_{year}.tif"
)
MAPBIOMAS_YEARS = (1985, 2000, 2010, 2020, 2025)
_MAPBIOMAS_CACHE = {}
_MAPBIOMAS_CACHE_TTL = 24 * 3600
_TRANSFERE_CACHE = {}
_SICONFI_CACHE = {}
_SICONFI_LOCK = threading.Lock()
_SICONFI_LAST_REQUEST = 0.0
DNIT_WFS = "https://geoservicos.inde.gov.br/geoserver/DNIT/ows"
FUNAI_WFS = "https://geoserver.funai.gov.br/geoserver/ows"
INCRA_WFS = "https://geoportal.incra.gov.br/geoserver/wfs"
SGB_RISK = (
    "https://geoportal.sgb.gov.br/server/rest/services/"
    "gestaoterritorial/risco/FeatureServer/0"
)
SGB_FLOOD = (
    "https://geoportal.sgb.gov.br/server/rest/services/"
    "gestaoterritorial/inundacao/FeatureServer/0"
)
SGB_SUSCET = (
    "https://geoportal.sgb.gov.br/server/rest/services/"
    "Hosted/Base_Suscet_v2/FeatureServer/0"
)

ANA_LAYERS = {
    "macro": (102, ["DMA_CD", "DMA_NM", "DMA_AR_KM2"]),
    "meso": (103, ["DME_CD", "DME_NM", "DME_DMA_CD", "DME_AR_KM2"]),
    "micro": (104, ["DMI_CD", "DMI_NM", "DMI_DME_CD", "DMI_DMA_CD", "DMI_AR_KM2"]),
}
ICMBIO_FIELDS = [
    "nomeuc", "cnuc", "criacaoano", "criacaoato", "esferaadm",
    "grupouc", "biomas", "bioma_pred", "categoria_", "sigla_cate",
    "demarcacao", "escalauc", "uf",
]
INCRA_FIELDS = [
    "status", "rt", "data_aprovacao", "data_submissao", "parcela_codigo",
    "situacao_informada", "registro_cns", "registro_matricula", "data_registro",
    "transcricao", "natureza", "codigo_imovel", "municipio_id", "uf_id",
    "area_hectares", "nome_area", "tipo_envio",
]
FUNAI_FIELDS = [
    "terrai_codigo", "terrai_nome", "municipio_nome", "uf_sigla",
    "superficie_perimetro_ha", "fase_ti", "modalidade_ti", "reestudo_ti",
    "faixa_fronteira", "dominio_uniao", "data_atualizacao",
]
DNIT_FIELDS = [
    "ogc_fid", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr",
    "ds_local_i", "ds_local_f", "vl_km_inic", "vl_km_fina", "vl_extensa",
    "ds_sup_fed", "ds_obra", "ds_tipo_ad", "ds_ato_leg", "ds_jurisdi",
    "ds_superfi", "ds_legenda", "sg_legenda", "versao_snv",
]
SGB_RISK_FIELDS = [
    "objectid", "uf", "munic", "cd_geocmu", "num_setor", "data_setor",
    "local", "tipolo_g1", "tipolo_e1", "grau_vulne", "grau_risco",
    "orgao_exec",
]
SGB_FLOOD_FIELDS = [
    "objectid", "uf", "municipio", "processo", "classe", "fonte",
    "execucao", "projeto", "ano", "executor",
]
MAPBIOMAS_NAMES_OFFICIAL = {
    0: "Not Observed",
    1: "Forest",
    3: "Forest Formation",
    4: "Savanna Formation",
    5: "Mangrove",
    6: "Floodable Forest",
    7: "Flooded Savanna",
    9: "Forest Plantation",
    10: "Herbaceous and Shrubby Vegetation",
    11: "Wetland",
    12: "Grassland Formation",
    13: "Other non-forest natural formation",
    14: "Farming",
    15: "Pasture",
    18: "Agriculture",
    19: "Temporary Crop",
    20: "Sugar cane",
    21: "Mosaic of Uses",
    22: "Non vegetated area",
    23: "Beach, Dune and Sand Spot",
    24: "Urban Area",
    25: "Other non Vegetated Areas",
    26: "Water",
    27: "Not Observed",
    29: "Rocky Outcrop",
    30: "Mining",
    31: "Aquaculture",
    32: "Hypersaline Tidal Flat",
    33: "River, Lake and Ocean",
    34: "Glacier",
    35: "Palm Oil",
    36: "Perennial Crop",
    39: "Soybean",
    40: "Rice",
    41: "Other Temporary Crops",
    42: "Open Grassland",
    43: "Closed Grassland",
    44: "Sparse Grassland",
    45: "Sparse woodland",
    46: "Coffee",
    47: "Citrus",
    48: "Other Perennial Crops",
    49: "Wooded Sandbank Vegetation",
    50: "Herbaceous Sandbank Vegetation",
    51: "Lowland Flooded Grassland",
    52: "Coastal salt flat surface",
    57: "Single crop",
    58: "Multiple crop",
    59: "Primary Forest",
    60: "Secondary Forest",
    61: "Salt flat",
    62: "Cotton (beta)",
    63: "Shrub and herbaceous mosaics",
    65: "Tea",
    66: "Closed shrublands",
    67: "Dwarf Forest",
    68: "Other natural non-vegetated area",
    70: "Coastal Lomas (beta)",
    72: "Other crops",
    73: "Peatlands",
    74: "Banana",
    75: "Photovoltaic Power Plant (beta)",
    76: "Peat Swamp Forest",
    77: "Herbaceous-Shrub Mosaic",
    79: "Pinus plantation",
    80: "Eucalyptus plantation",
    81: "Andean grassland and shrubland",
    82: "Flooded Andean grassland and shrubland",
    83: "Other forestry uses",
    84: "Marisma",
    88: "Temperate forest",
    89: "Tropical dry forest",
    91: "Wind Farm",
    92: "Rocky surface",
}
MAPBIOMAS_NAMES_PT = {
    0: "Não observado",
    1: "Floresta",
    3: "Formação florestal",
    4: "Formação savânica",
    5: "Mangue",
    6: "Floresta alagável",
    7: "Savana alagável",
    9: "Silvicultura",
    10: "Vegetação herbácea e arbustiva",
    11: "Área úmida",
    12: "Formação campestre",
    13: "Outra formação natural não florestal",
    14: "Agropecuária",
    15: "Pastagem",
    18: "Agricultura",
    19: "Lavoura temporária",
    20: "Cana-de-açúcar",
    21: "Mosaico de usos",
    22: "Área não vegetada",
    23: "Praia, duna e areal",
    24: "Área urbana",
    25: "Outra área não vegetada",
    26: "Água",
    27: "Não observado",
    29: "Afloramento rochoso",
    30: "Mineração",
    31: "Aquicultura",
    32: "Apicum",
    33: "Rio, lago e oceano",
    34: "Geleira",
    35: "Dendê",
    36: "Lavoura perene",
    39: "Soja",
    40: "Arroz",
    41: "Outras lavouras temporárias",
    42: "Campo aberto",
    43: "Campo fechado",
    44: "Campo esparso",
    45: "Formação lenhosa esparsa",
    46: "Café",
    47: "Cítricos",
    48: "Outras lavouras perenes",
    49: "Restinga arbórea",
    50: "Restinga herbácea",
    51: "Campo alagado de baixada",
    52: "Superfície salina costeira",
    57: "Cultivo único",
    58: "Cultivo múltiplo",
    59: "Floresta primária",
    60: "Floresta secundária",
    61: "Salina",
    62: "Algodão (beta)",
    63: "Mosaico arbustivo e herbáceo",
    65: "Chá",
    66: "Arbustal fechado",
    67: "Floresta anã",
    68: "Outra área natural não vegetada",
    70: "Lomas costeiras (beta)",
    72: "Outras culturas",
    73: "Turfeiras",
    74: "Banana",
    75: "Usina fotovoltaica (beta)",
    76: "Floresta pantanosa turfosa",
    77: "Mosaico herbáceo-arbustivo",
    79: "Plantação de pinus",
    80: "Plantação de eucalipto",
    81: "Campo e arbustal andino",
    82: "Campo e arbustal andino alagado",
    83: "Outros usos florestais",
    84: "Marisma",
    88: "Floresta temperada",
    89: "Floresta tropical seca",
    91: "Parque eólico",
    92: "Superfície rochosa",
}

SGB_SUSCET_FIELDS = [
    "nm_municip", "cd_geocmu", "uf", "carta_suscet", "ano_execucao",
    "mes_public", "ano_public", "area_municipio", "area_mapeada",
    "mov_massa_alta", "mov_massa_media", "mov_massa_baixa",
    "inundacao_alta", "inundacao_media", "inundacao_baixa",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_text(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
    return str(value)


def _get_json(url: str, limit: int = 2_000_000):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LoteDiretor/1.0 (+https://lotediretor.com)",
            "Accept": "application/json, application/geo+json",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(limit + 1)
        encoding = (response.headers.get("Content-Encoding") or "").lower()
        charset = response.headers.get_content_charset() or "utf-8"
    if len(raw) > limit:
        raise RuntimeError("federal_context_response_too_large")
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode(charset))


def _arcgis_point_query(
    url: str, fields: list[str], lat: float, lng: float
) -> list[dict]:
    params = {
        "f": "json",
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(fields),
        "returnGeometry": "false",
        "resultRecordCount": "50",
    }
    data = _get_json(url + "/query?" + urllib.parse.urlencode(params))
    allowed = set(fields)
    out = []
    for feature in data.get("features") or []:
        attrs = feature.get("attributes") or {}
        if set(attrs) - allowed:
            raise RuntimeError("federal_arcgis_unexpected_fields")
        out.append({
            key: attrs.get(key)
            for key in fields
            if attrs.get(key) is not None
        })
    return out


def ana_region(level: str, lat: float, lng: float) -> dict:
    layer, fields = ANA_LAYERS[level]
    params = {
        "f": "json",
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(fields),
        "returnGeometry": "false",
    }
    data = _get_json(
        f"{ANA_BASE}/{layer}/query?" + urllib.parse.urlencode(params)
    )
    features = data.get("features") or []
    if not features:
        return {}
    attrs = features[0].get("attributes") or {}
    allowed = set(fields)
    if set(attrs) - allowed:
        raise RuntimeError("ana_unexpected_fields")
    return {
        key: attrs.get(key)
        for key in fields
        if attrs.get(key) is not None
    }


def icmbio_at_point(lat: float, lng: float) -> list[dict]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "ICMBio:limiteucsfederais_a",
        "srsName": "EPSG:4326",
        "count": "20",
        "propertyName": ",".join(ICMBIO_FIELDS),
        "cql_filter": f"INTERSECTS(the_geom,SRID=4326;POINT({lng} {lat}))",
        "outputFormat": "application/json",
    }
    data = _get_json(ICMBIO_WFS + "?" + urllib.parse.urlencode(params))
    allowed = set(ICMBIO_FIELDS)
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if set(props) - allowed:
            raise RuntimeError("icmbio_unexpected_fields")
        out.append({
            key: props.get(key)
            for key in ICMBIO_FIELDS
            if props.get(key) is not None
        })
    return out


def incra_sigef_at_point(lat: float, lng: float) -> list[dict]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "geonode:sigef_geo",
        "srsName": "EPSG:4326",
        "count": "20",
        "propertyName": ",".join(INCRA_FIELDS),
        "cql_filter": (
            f"INTERSECTS(geometry,SRID=4326;POINT({lng} {lat}))"
        ),
        "outputFormat": "application/json",
    }
    data = _get_json(INCRA_WFS + "?" + urllib.parse.urlencode(params), 4_000_000)
    out = []
    allowed = set(INCRA_FIELDS)
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if set(props) - allowed:
            raise RuntimeError("incra_unexpected_fields")
        out.append({
            k: props.get(k)
            for k in INCRA_FIELDS
            if props.get(k) is not None
        })
    return out


def funai_at_point(lat: float, lng: float) -> list[dict]:
    span = 0.00025
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": "Funai:tis_poligonais",
        "srsName": "EPSG:4326",
        "maxFeatures": "20",
        "bbox": f"{lng-span},{lat-span},{lng+span},{lat+span},EPSG:4326",
        "propertyName": ",".join(["the_geom", *FUNAI_FIELDS]),
        "outputFormat": "application/json",
    }
    data = _get_json(FUNAI_WFS + "?" + urllib.parse.urlencode(params))
    allowed = set(FUNAI_FIELDS)
    point = Point(lng, lat)
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if set(props) - allowed:
            raise RuntimeError("funai_unexpected_fields")
        geom = feature.get("geometry")
        if not geom:
            continue
        try:
            if not shape(geom).covers(point):
                continue
        except Exception:
            continue
        out.append({
            key: props.get(key)
            for key in FUNAI_FIELDS
            if props.get(key) is not None
        })
    return out


def _ibge_aggregate(
    table: str, variables: list[str], municipality_ibge: str
) -> dict:
    variable_path = "|".join(variables)
    url = (
        f"{IBGE_AGGREGATES}/{table}/periodos/2022/variaveis/{variable_path}"
        f"?localidades=N6[{municipality_ibge}]"
    )
    data = _get_json(url)
    out = {}
    for row in data if isinstance(data, list) else []:
        variable_id = str(row.get("id"))
        results = row.get("resultados") or []
        series = (results[0].get("series") or []) if results else []
        if not series:
            continue
        place = series[0].get("localidade") or {}
        value = (series[0].get("serie") or {}).get("2022")
        out[variable_id] = {
            "name": row.get("variavel"),
            "unit": row.get("unidade"),
            "value": value,
            "municipality": place.get("nome"),
            "municipality_ibge": place.get("id"),
            "territorial_level": (place.get("nivel") or {}).get("nome"),
        }
    return out


def ibge_census_sector_at_point(
    municipality_ibge: str,
    lat: float,
    lng: float,
) -> dict:
    with psycopg2.connect(DB_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                cd_setor, situacao, area_km2,
                cd_dist, nm_dist, cd_subdist, nm_subdist,
                cd_bairro, nm_bairro,
                v0001, v0002, v0003, v0004, v0005, v0006, v0007
            FROM ld_stage.ibge_censo2022_setores
            WHERE cd_mun=%s
              AND ST_Covers(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s,%s),4674)
                  )
            ORDER BY ST_Area(geom)
            LIMIT 1
            """,
            (municipality_ibge, lng, lat),
        )
        row = cur.fetchone()
        if not row:
            return {}
        cols = [d.name for d in cur.description]
    data = dict(zip(cols, row))
    return {
        "census_year": 2022,
        "sector_code": data.get("cd_setor"),
        "situation": data.get("situacao"),
        "area_km2": data.get("area_km2"),
        "district_code": data.get("cd_dist"),
        "district_name": data.get("nm_dist"),
        "subdistrict_code": data.get("cd_subdist"),
        "subdistrict_name": data.get("nm_subdist"),
        "neighborhood_code": data.get("cd_bairro"),
        "neighborhood_name": data.get("nm_bairro"),
        "population": data.get("v0001"),
        "households_total": data.get("v0002"),
        "private_households_total": data.get("v0003"),
        "collective_households_total": data.get("v0004"),
        "average_residents_occupied_private_household": data.get("v0005"),
        "imputed_occupied_private_households_pct": data.get("v0006"),
        "occupied_private_households": data.get("v0007"),
        "source": (
            "IBGE Censo Demográfico 2022 · malha de setores censitários "
            "com atributos"
        ),
        "interpretation": (
            "Os indicadores descrevem o setor censitário que contém o ponto "
            "do terreno. Não são atributos exclusivos do lote e não devem ser "
            "interpretados como renda, composição familiar ou condição dos "
            "ocupantes deste imóvel."
        ),
    }


def ibge_municipality_context(municipality_ibge: str) -> dict:
    return {
        "year": 2022,
        "population": _ibge_aggregate(
            "4714", ["93", "6318", "614"], municipality_ibge
        ),
        "households": _ibge_aggregate(
            "4712", ["381", "382", "5930"], municipality_ibge
        ),
        "interpretation": (
            "Indicadores do Censo 2022 no nível do município. São contexto "
            "territorial e não descrevem diretamente o lote, a quadra ou o "
            "setor censitário do imóvel."
        ),
    }


def _siconfi_request(url: str):
    global _SICONFI_LAST_REQUEST
    with _SICONFI_LOCK:
        wait = 1.05 - (time.monotonic() - _SICONFI_LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        data = _get_json(url, 4_000_000)
        _SICONFI_LAST_REQUEST = time.monotonic()
        return data


def siconfi_municipality_context(municipality_ibge: str) -> dict:
    cache_key = ("2025", municipality_ibge)
    cached = _SICONFI_CACHE.get(cache_key)
    if cached and time.time() - cached["cached_at"] < 12 * 3600:
        return cached["value"]

    ente_params = urllib.parse.urlencode({"cod_ibge": municipality_ibge})
    ente_data = _siconfi_request(SICONFI_ENTES + "?" + ente_params)
    ente_rows = [
        item for item in (ente_data.get("items") or [])
        if str(item.get("cod_ibge")) == str(municipality_ibge)
    ]
    ente = ente_rows[0] if ente_rows else {}

    params = {
        "an_exercicio": "2025",
        "nr_periodo": "6",
        "co_tipo_demonstrativo": "RREO",
        "id_ente": municipality_ibge,
    }
    data = _siconfi_request(
        SICONFI_RREO + "?" + urllib.parse.urlencode(params)
    )

    items = data.get("items") or []
    exact = {}
    wanted = {
        ("RREO6IPTU", "RECEITAS REALIZADAS (a)"): "iptu_revenue_brl",
        ("RREO6ITBI", "RECEITAS REALIZADAS (a)"): "itbi_revenue_brl",
        (
            "ReceitaCorrenteLiquidaDemonstrativoSimplificado",
            "Até o Bimestre",
        ): "rcl_brl",
        (
            "ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamentoDemonstrativoSimplificado",
            "Até o Bimestre",
        ): "rcl_adjusted_debt_limit_brl",
    }
    institution = None
    for item in items:
        key = (item.get("cod_conta"), item.get("coluna"))
        name = wanted.get(key)
        if name and item.get("valor") is not None:
            exact[name] = item.get("valor")
        if institution is None and item.get("instituicao"):
            institution = item.get("instituicao")

    value = {
        "year": 2025,
        "period": 6,
        "institution": institution,
        "municipality_name": ente.get("ente"),
        "municipality_uf": ente.get("uf"),
        "municipality_cnpj": ente.get("cnpj"),
        **exact,
        "interpretation": (
            "Valores do RREO/SICONFI são contexto fiscal do município e não "
            "representam valor, imposto ou capacidade financeira do terreno."
        ),
    }
    _SICONFI_CACHE[cache_key] = {
        "cached_at": time.time(),
        "value": value,
    }
    return value


def transferegov_municipality_context(cnpj: str | None) -> dict:
    if not cnpj:
        return {}
    cached = _TRANSFERE_CACHE.get(cnpj)
    if cached and time.time() - cached["cached_at"] < 12 * 3600:
        return cached["value"]

    beneficiary_params = urllib.parse.urlencode({
        "cnpj_beneficiario": cnpj,
        "pagina": 1,
        "tamanho_da_pagina": 20,
    })
    beneficiary_data = _get_json(
        TRANSFERE_ESPECIAIS
        + "/beneficiarios-especiais?"
        + beneficiary_params,
        1_000_000,
    )
    beneficiary_rows = [
        item for item in (beneficiary_data.get("data") or [])
        if str(item.get("cnpj_beneficiario") or "") == str(cnpj)
    ]
    if not beneficiary_rows:
        value = {
            "year": 2026,
            "plan_count": 0,
            "investment_brl": 0.0,
            "operating_brl": 0.0,
            "plans": [],
            "interpretation": (
                "Nenhum beneficiário municipal correspondente foi localizado "
                "na API de Transferências Especiais para este CNPJ."
            ),
        }
        _TRANSFERE_CACHE[cnpj] = {
            "cached_at": time.time(),
            "value": value,
        }
        return value

    beneficiary = beneficiary_rows[0]
    beneficiary_id = beneficiary.get("id_beneficiario")
    plan_params = urllib.parse.urlencode({
        "id_beneficiario": beneficiary_id,
        "ano_plano_acao": 2026,
        "pagina": 1,
        "tamanho_da_pagina": 100,
    })
    plan_data = _get_json(
        TRANSFERE_ESPECIAIS
        + "/planos-acao-especiais?"
        + plan_params,
        3_000_000,
    )
    plans = []
    investment = 0.0
    operating = 0.0
    for item in plan_data.get("data") or []:
        inv = float(item.get("valor_investimento_plano_acao") or 0)
        cust = float(item.get("valor_custeio_plano_acao") or 0)
        investment += inv
        operating += cust
        plans.append({
            "code": item.get("codigo_plano_acao"),
            "status": item.get("situacao_plano_acao"),
            "object": item.get("nome_objeto"),
            "category": item.get("categoria_despesa_plano_acao"),
            "investment_brl": inv,
            "operating_brl": cust,
        })

    value = {
        "year": 2026,
        "beneficiary_id": beneficiary_id,
        "beneficiary_name": beneficiary.get("nome_beneficiario"),
        "plan_count": len(plans),
        "investment_brl": round(investment, 2),
        "operating_brl": round(operating, 2),
        "plans": plans[:20],
        "interpretation": (
            "Transferências Especiais são contexto de recursos federais do "
            "município. Objeto, plano ou valor não é vinculado ao lote e não "
            "deve ser apresentado como obra próxima sem geometria oficial."
        ),
    }
    _TRANSFERE_CACHE[cnpj] = {
        "cached_at": time.time(),
        "value": value,
    }
    return value


def _mapbiomas_sample(year: int, lat: float, lng: float) -> dict:
    try:
        import rasterio
        from rasterio.warp import transform as raster_transform
    except ImportError as exc:
        raise RuntimeError("mapbiomas_rasterio_not_installed") from exc

    url = MAPBIOMAS_TIF.format(year=year)
    with rasterio.Env(
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    ):
        with rasterio.open(url) as ds:
            xs, ys = raster_transform(
                "EPSG:4326",
                ds.crs,
                [lng],
                [lat],
            )
            row, col = ds.index(xs[0], ys[0])
            if row < 0 or col < 0 or row >= ds.height or col >= ds.width:
                return {
                    "year": year,
                    "available": False,
                    "reason": "outside_raster_extent",
                }
            value = int(
                ds.read(
                    1,
                    window=((row, row + 1), (col, col + 1)),
                )[0, 0]
            )
    return {
        "year": year,
        "available": True,
        "class_id": value,
        "class_name": MAPBIOMAS_NAMES_PT.get(
            value,
            f"Classe {value}",
        ),
        "official_class_name": MAPBIOMAS_NAMES_OFFICIAL.get(value),
    }


def mapbiomas_history(
    parcel_geometry: dict | None,
    lat: float,
    lng: float,
) -> dict:
    sample_lat = lat
    sample_lng = lng
    if parcel_geometry:
        try:
            p = shape(parcel_geometry).representative_point()
            sample_lng, sample_lat = p.x, p.y
        except Exception:
            pass
    cache_key = (
        round(sample_lat, 5),
        round(sample_lng, 5),
        MAPBIOMAS_YEARS,
    )
    cached = _MAPBIOMAS_CACHE.get(cache_key)
    if cached and time.time() - cached["cached_at"] < _MAPBIOMAS_CACHE_TTL:
        return cached["value"]

    with ThreadPoolExecutor(max_workers=len(MAPBIOMAS_YEARS)) as pool:
        samples = list(
            pool.map(
                lambda year: _mapbiomas_sample(
                    year,
                    sample_lat,
                    sample_lng,
                ),
                MAPBIOMAS_YEARS,
            )
        )
    samples.sort(key=lambda item: item["year"])
    transitions = []
    previous = None
    for item in samples:
        if not item.get("available"):
            continue
        current = item.get("class_id")
        if previous and current != previous.get("class_id"):
            transitions.append({
                "from_year": previous.get("year"),
                "from_class_id": previous.get("class_id"),
                "from_class_name": previous.get("class_name"),
                "to_year": item.get("year"),
                "to_class_id": current,
                "to_class_name": item.get("class_name"),
            })
        previous = item
    value = {
        "available": any(item.get("available") for item in samples),
        "collection": 11,
        "resolution_m": 30,
        "sample_point": {
            "lat": round(sample_lat, 7),
            "lng": round(sample_lng, 7),
        },
        "years": list(MAPBIOMAS_YEARS),
        "samples": samples,
        "transitions_between_sampled_years": transitions,
        "source": (
            "MapBiomas Brasil · Coleção 11 · cobertura e uso da terra 30 m"
        ),
        "interpretation": (
            "A classificação representa o pixel de 30 m no ponto "
            "representativo do terreno em marcos históricos selecionados. "
            "Não equivale a levantamento do lote inteiro nem comprova uso "
            "jurídico/licenciado em cada ano."
        ),
    }
    _MAPBIOMAS_CACHE[cache_key] = {
        "cached_at": time.time(),
        "value": value,
    }
    return value


def sgb_municipality_context(municipality_ibge: str) -> dict:
    params = {
        "f": "json",
        "where": f"cd_geocmu='{municipality_ibge}'",
        "outFields": ",".join(SGB_SUSCET_FIELDS),
        "returnGeometry": "false",
        "resultRecordCount": "5",
    }
    data = _get_json(SGB_SUSCET + "/query?" + urllib.parse.urlencode(params))
    features = data.get("features") or []
    if not features:
        return {}
    attrs = features[0].get("attributes") or {}
    allowed = set(SGB_SUSCET_FIELDS)
    if set(attrs) - allowed:
        raise RuntimeError("sgb_susceptibility_unexpected_fields")
    return {
        key: attrs.get(key)
        for key in SGB_SUSCET_FIELDS
        if attrs.get(key) is not None
    }


def sgb_risk_at_point(lat: float, lng: float) -> dict:
    return {
        "risk_sectors": _arcgis_point_query(
            SGB_RISK, SGB_RISK_FIELDS, lat, lng
        ),
        "flood_susceptibility": _arcgis_point_query(
            SGB_FLOOD, SGB_FLOOD_FIELDS, lat, lng
        ),
    }


def dnit_near_parcel(
    parcel_geometry: dict | None,
    lat: float,
    lng: float,
    max_distance_m: float = 80.0,
) -> list[dict]:
    if not parcel_geometry:
        return []
    parcel = shape(parcel_geometry)
    if parcel.is_empty:
        return []
    minx, miny, maxx, maxy = parcel.bounds
    pad = 0.0012
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "DNIT:snv_202507a",
        "srsName": "EPSG:4326",
        "bbox": f"{minx-pad},{miny-pad},{maxx+pad},{maxy+pad},EPSG:4326",
        "count": "100",
        "propertyName": ",".join(["the_geom", *DNIT_FIELDS]),
        "outputFormat": "application/json",
    }
    data = _get_json(
        DNIT_WFS + "?" + urllib.parse.urlencode(params),
        4_000_000,
    )
    transformer = Transformer.from_crs(
        "EPSG:4326", "EPSG:3857", always_xy=True
    )
    parcel_metric = shapely_transform(transformer.transform, parcel)
    allowed = set(DNIT_FIELDS)
    out = []
    for feature in data.get("features") or []:
        geom = feature.get("geometry")
        props = feature.get("properties") or {}
        if set(props) - allowed:
            raise RuntimeError("dnit_unexpected_fields")
        if not geom:
            continue
        try:
            road_metric = shapely_transform(
                transformer.transform, shape(geom)
            )
            distance_m = float(parcel_metric.distance(road_metric))
        except Exception:
            continue
        if distance_m <= max_distance_m:
            out.append({
                "distance_to_parcel_m": round(distance_m, 1),
                "properties": {
                    key: props.get(key)
                    for key in DNIT_FIELDS
                    if props.get(key) is not None
                },
            })
    out.sort(key=lambda item: item["distance_to_parcel_m"])
    return out[:8]


def load(
    lat: float,
    lng: float,
    municipality_ibge: str | None = None,
    parcel_geometry: dict | None = None,
) -> dict:
    result = {
        "hydrology": {},
        "federal_conservation_units": [],
        "indigenous_lands": [],
        "sigef_parcels": [],
        "indigenous_territories": [],
        "municipality_demographics": {},
        "census_sector": {},
        "municipality_finance": {},
        "municipality_transfers": {},
        "sgb_susceptibility": {},
        "sgb": {
            "risk_sectors": [],
            "flood_susceptibility": [],
        },
        "federal_roads": [],
        "land_cover_history": {},
        "query_errors": {},
        "queried_at": now(),
        "interpretation": (
            "Contexto federal complementar. Divisão hidrográfica não equivale "
            "a risco de inundação. Ausência de incidência federal não exclui "
            "proteção estadual, municipal, APP, tombamento, faixa de domínio "
            "ou outras restrições."
        ),
    }
    jobs = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for level in ANA_LAYERS:
            jobs[pool.submit(ana_region, level, lat, lng)] = ("ana", level)
        jobs[pool.submit(icmbio_at_point, lat, lng)] = (
            "icmbio", "federal_uc"
        )
        jobs[pool.submit(funai_at_point, lat, lng)] = (
            "funai", "territories"
        )
        jobs[pool.submit(incra_sigef_at_point, lat, lng)] = (
            "incra", "sigef"
        )
        jobs[pool.submit(sgb_risk_at_point, lat, lng)] = (
            "sgb", "risk"
        )
        if parcel_geometry:
            jobs[
                pool.submit(
                    dnit_near_parcel,
                    parcel_geometry,
                    lat,
                    lng,
                )
            ] = ("dnit", "roads")
            jobs[
                pool.submit(
                    mapbiomas_history,
                    parcel_geometry,
                    lat,
                    lng,
                )
            ] = ("mapbiomas", "land_cover")
        if municipality_ibge:
            jobs[
                pool.submit(
                    ibge_municipality_context,
                    municipality_ibge,
                )
            ] = ("ibge", "municipality")
            jobs[
                pool.submit(
                    ibge_census_sector_at_point,
                    municipality_ibge,
                    lat,
                    lng,
                )
            ] = ("ibge", "sector")
            jobs[
                pool.submit(
                    siconfi_municipality_context,
                    municipality_ibge,
                )
            ] = ("siconfi", "municipality_finance")
            jobs[
                pool.submit(
                    sgb_municipality_context,
                    municipality_ibge,
                )
            ] = ("sgb", "susceptibility")
        for future in as_completed(jobs):
            group, key = jobs[future]
            try:
                value = future.result()
                if group == "ana":
                    result["hydrology"][key] = value
                elif group == "icmbio":
                    result["federal_conservation_units"] = value
                elif group == "funai":
                    result["indigenous_territories"] = value
                elif group == "incra":
                    result["sigef_parcels"] = value
                elif group == "ibge" and key == "municipality":
                    result["municipality_demographics"] = value
                elif group == "ibge" and key == "sector":
                    result["census_sector"] = value
                elif group == "siconfi":
                    result["municipality_finance"] = value
                elif group == "dnit":
                    result["federal_roads"] = value
                elif group == "mapbiomas":
                    result["land_cover_history"] = value
                elif group == "sgb" and key == "risk":
                    result["sgb"] = value
                elif group == "sgb" and key == "susceptibility":
                    result["sgb_susceptibility"] = value
            except Exception as exc:
                result["query_errors"][f"{group}_{key}"] = type(exc).__name__
    finance = result.get("municipality_finance") or {}
    try:
        result["municipality_transfers"] = transferegov_municipality_context(
            finance.get("municipality_cnpj")
        )
    except Exception as exc:
        result["query_errors"]["transferegov_municipality"] = type(exc).__name__
    return result


def territorial_report_values(context: dict) -> list[dict]:
    out = []
    hyd = (context or {}).get("hydrology") or {}
    labels = {
        "macro": "Macrorregião hidrográfica (ANA/IBGE)",
        "meso": "Mesorregião hidrográfica (ANA/IBGE)",
        "micro": "Microrregião hidrográfica (ANA/IBGE)",
    }
    name_keys = {
        "macro": "DMA_NM",
        "meso": "DME_NM",
        "micro": "DMI_NM",
    }
    code_keys = {
        "macro": "DMA_CD",
        "meso": "DME_CD",
        "micro": "DMI_CD",
    }
    for level in ("macro", "meso", "micro"):
        row = hyd.get(level) or {}
        if row.get(name_keys[level]):
            out.extend([
                {
                    "label": labels[level],
                    "value": row.get(name_keys[level]),
                },
                {
                    "label": labels[level] + " · código",
                    "value": row.get(code_keys[level]),
                },
            ])

    sector = (context or {}).get("census_sector") or {}
    if sector.get("sector_code"):
        out.extend([
            {
                "label": "Setor censitário 2022",
                "value": sector.get("sector_code"),
            },
            {
                "label": "Situação do setor censitário",
                "value": sector.get("situation"),
            },
            {
                "label": "Distrito do setor censitário",
                "value": sector.get("district_name"),
            },
            {
                "label": "Subdistrito do setor censitário",
                "value": sector.get("subdistrict_name"),
            },
            {
                "label": "Bairro do setor censitário",
                "value": sector.get("neighborhood_name"),
            },
            {
                "label": "População do setor censitário (Censo 2022)",
                "value": sector.get("population"),
                "unit": "pessoas",
            },
            {
                "label": "Domicílios no setor censitário (Censo 2022)",
                "value": sector.get("households_total"),
                "unit": "domicílios",
            },
            {
                "label": (
                    "Domicílios particulares ocupados no setor "
                    "(Censo 2022)"
                ),
                "value": sector.get("occupied_private_households"),
                "unit": "domicílios",
            },
            {
                "label": (
                    "Média de moradores por domicílio particular ocupado "
                    "no setor"
                ),
                "value": sector.get(
                    "average_residents_occupied_private_household"
                ),
                "unit": "pessoas",
            },
            {
                "label": "Limite do contexto censitário",
                "value": sector.get("interpretation"),
            },
        ])

    demo = (context or {}).get("municipality_demographics") or {}
    pop = demo.get("population") or {}
    households = demo.get("households") or {}
    values = [
        (
            "Contexto municipal · população residente (Censo 2022)",
            (pop.get("93") or {}).get("value"),
            "pessoas",
        ),
        (
            "Contexto municipal · densidade demográfica (Censo 2022)",
            (pop.get("614") or {}).get("value"),
            "hab./km²",
        ),
        (
            "Contexto municipal · domicílios permanentes ocupados (Censo 2022)",
            (households.get("381") or {}).get("value"),
            "domicílios",
        ),
        (
            "Contexto municipal · média de moradores por domicílio (Censo 2022)",
            (households.get("5930") or {}).get("value"),
            "pessoas",
        ),
    ]
    for label, value, unit in values:
        if value is not None:
            out.append({
                "label": label,
                "value": value,
                "unit": unit,
            })
    if demo.get("interpretation"):
        out.append({
            "label": "Limite do contexto demográfico",
            "value": demo.get("interpretation"),
        })
    finance = (context or {}).get("municipality_finance") or {}
    if finance.get("iptu_revenue_brl") is not None:
        out.append({
            "label": "Arrecadação municipal de IPTU · RREO 2025",
            "value": finance.get("iptu_revenue_brl"),
            "unit": "BRL",
        })
    if finance.get("itbi_revenue_brl") is not None:
        out.append({
            "label": "Arrecadação municipal de ITBI · RREO 2025",
            "value": finance.get("itbi_revenue_brl"),
            "unit": "BRL",
        })
    if finance.get("rcl_brl") is not None:
        out.append({
            "label": "Receita Corrente Líquida municipal · RREO 2025",
            "value": finance.get("rcl_brl"),
            "unit": "BRL",
        })
    if finance.get("rcl_adjusted_debt_limit_brl") is not None:
        out.append({
            "label": "RCL ajustada para limites de endividamento · RREO 2025",
            "value": finance.get("rcl_adjusted_debt_limit_brl"),
            "unit": "BRL",
        })
    if finance.get("interpretation"):
        out.append({
            "label": "Limite do contexto fiscal municipal",
            "value": finance.get("interpretation"),
        })
    transfers = (context or {}).get("municipality_transfers") or {}
    if transfers.get("plan_count") is not None:
        out.extend([
            {
                "label": "Transferências especiais federais · planos 2026",
                "value": transfers.get("plan_count"),
            },
            {
                "label": "Transferências especiais · investimento 2026",
                "value": transfers.get("investment_brl"),
                "unit": "BRL",
            },
            {
                "label": "Transferências especiais · custeio 2026",
                "value": transfers.get("operating_brl"),
                "unit": "BRL",
            },
        ])
    if transfers.get("interpretation"):
        out.append({
            "label": "Limite do contexto de transferências",
            "value": transfers.get("interpretation"),
        })
    out.append({
        "label": "Limite da divisão hidrográfica",
        "value": (
            "A divisão hidrográfica informa a região em que o terreno está "
            "inserido; não representa risco de inundação."
        ),
    })
    return [
        item
        for item in out
        if item.get("value") not in (None, "")
    ]


def environment_report_values(context: dict) -> list[dict]:
    out = []
    sgb_summary = (context or {}).get("sgb_susceptibility") or {}
    if str(sgb_summary.get("carta_suscet") or "").strip().lower() == "sim":
        out.extend([
            {
                "label": "Carta municipal de suscetibilidade (SGB)",
                "value": "Disponível",
            },
            {
                "label": "Ano de execução da carta do SGB",
                "value": sgb_summary.get("ano_execucao"),
            },
            {
                "label": "Ano de publicação da carta do SGB",
                "value": sgb_summary.get("ano_public"),
            },
            {
                "label": "Área municipal mapeada pelo SGB",
                "value": sgb_summary.get("area_mapeada"),
                "unit": "km²",
            },
            {
                "label": (
                    "SGB · área municipal de alta suscetibilidade "
                    "a movimentos de massa"
                ),
                "value": sgb_summary.get("mov_massa_alta"),
                "unit": "km²",
            },
            {
                "label": (
                    "SGB · área municipal de alta suscetibilidade "
                    "a inundação"
                ),
                "value": sgb_summary.get("inundacao_alta"),
                "unit": "km²",
            },
            {
                "label": "Limite da carta do SGB",
                "value": (
                    "Os valores são síntese municipal da cartografia de "
                    "suscetibilidade e não classificam este lote "
                    "individualmente."
                ),
            },
        ])

    for item in ((context or {}).get("sgb") or {}).get("risk_sectors") or []:
        out.extend([
            {
                "label": "Setor de risco federal (SGB)",
                "value": item.get("num_setor") or item.get("local"),
            },
            {
                "label": "Grau de risco informado pelo SGB",
                "value": item.get("grau_risco"),
            },
            {
                "label": "Tipologia do risco (SGB)",
                "value": item.get("tipolo_e1") or item.get("tipolo_g1"),
            },
            {
                "label": "Data da setorização do SGB",
                "value": _date_text(item.get("data_setor")),
            },
        ])

    for item in (
        ((context or {}).get("sgb") or {}).get("flood_susceptibility")
        or []
    ):
        out.extend([
            {
                "label": "Suscetibilidade a inundação (SGB)",
                "value": item.get("classe"),
            },
            {
                "label": "Processo de inundação (SGB)",
                "value": item.get("processo"),
            },
            {
                "label": "Ano da cartografia de inundação (SGB)",
                "value": item.get("ano"),
            },
        ])

    for territory in (context or {}).get("indigenous_territories") or []:
        out.extend([
            {
                "label": "Terra indígena federal",
                "value": territory.get("terrai_nome"),
            },
            {
                "label": "Fase da terra indígena",
                "value": territory.get("fase_ti"),
            },
            {
                "label": "Modalidade da terra indígena",
                "value": territory.get("modalidade_ti"),
            },
            {
                "label": "Área publicada pela FUNAI",
                "value": territory.get("superficie_perimetro_ha"),
                "unit": "ha",
            },
            {
                "label": "Atualização da base FUNAI",
                "value": territory.get("data_atualizacao"),
            },
        ])

    for unit in (context or {}).get("federal_conservation_units") or []:
        out.extend([
            {
                "label": "Unidade de conservação federal",
                "value": unit.get("nomeuc"),
            },
            {
                "label": "Categoria da unidade de conservação federal",
                "value": unit.get("categoria_") or unit.get("grupouc"),
            },
            {
                "label": "Ato de criação da unidade federal",
                "value": unit.get("criacaoato"),
            },
            {
                "label": "Bioma da unidade federal",
                "value": unit.get("bioma_pred") or unit.get("biomas"),
            },
        ])

    if (
        (context or {}).get("indigenous_territories")
        or (context or {}).get("federal_conservation_units")
        or ((context or {}).get("sgb") or {}).get("risk_sectors")
        or ((context or {}).get("sgb") or {}).get("flood_susceptibility")
    ):
        out.append({
            "label": "Limite do contexto ambiental federal",
            "value": (
                "A incidência territorial é baseada nas geometrias públicas "
                "federais e requer interpretação jurídica/técnica própria. "
                "Ausência federal não exclui proteção estadual ou municipal."
            ),
        })
    return [
        item
        for item in out
        if item.get("value") not in (None, "")
    ]


def historical_report_values(context: dict) -> list[dict]:
    history = (context or {}).get("land_cover_history") or {}
    if not history.get("available"):
        return []
    out = []
    for item in history.get("samples") or []:
        if not item.get("available"):
            continue
        out.append({
            "label": f"MapBiomas · uso/cobertura {item.get('year')}",
            "value": item.get("class_name"),
        })
    transitions = history.get("transitions_between_sampled_years") or []
    for index, item in enumerate(transitions, start=1):
        out.append({
            "label": f"MapBiomas · mudança observada #{index}",
            "value": (
                f"{item.get('from_year')}: {item.get('from_class_name')} → "
                f"{item.get('to_year')}: {item.get('to_class_name')}"
            ),
        })
    out.extend([
        {
            "label": "MapBiomas · resolução espacial",
            "value": history.get("resolution_m"),
            "unit": "m",
        },
        {
            "label": "Limite do histórico MapBiomas",
            "value": history.get("interpretation"),
        },
    ])
    return [
        item
        for item in out
        if item.get("value") not in (None, "")
    ]


def registry_report_values(context: dict) -> list[dict]:
    out = []
    for item in (context or {}).get("sigef_parcels") or []:
        out.extend([
            {
                "label": "Parcela certificada no SIGEF",
                "value": item.get("parcela_codigo") or item.get("codigo_imovel"),
            },
            {
                "label": "Situação informada no SIGEF",
                "value": item.get("situacao_informada") or item.get("status"),
            },
            {
                "label": "Área informada no SIGEF",
                "value": item.get("area_hectares"),
                "unit": "ha",
            },
            {
                "label": "Natureza da parcela SIGEF",
                "value": item.get("natureza"),
            },
            {
                "label": "CNS informado no SIGEF",
                "value": item.get("registro_cns"),
            },
            {
                "label": "Matrícula informada no SIGEF",
                "value": item.get("registro_matricula"),
            },
            {
                "label": "Data de aprovação no SIGEF",
                "value": _date_text(item.get("data_aprovacao")),
            },
        ])
    if (context or {}).get("sigef_parcels"):
        out.append({
            "label": "Limite da referência SIGEF",
            "value": (
                "A certificação SIGEF é referência fundiária rural e não "
                "substitui certidão registral atual, pesquisa de ônus, cadeia "
                "dominial ou confirmação de titularidade."
            ),
        })
    return [
        item for item in out
        if item.get("value") not in (None, "")
    ]


def transport_report_values(context: dict) -> list[dict]:
    out = []
    for road in (context or {}).get("federal_roads") or []:
        props = road.get("properties") or {}
        br = props.get("vl_br")
        out.extend([
            {
                "label": "Rodovia federal próxima",
                "value": (
                    "BR-" + str(br).zfill(3)
                    if br
                    else props.get("ds_legenda")
                ),
            },
            {
                "label": "Distância aproximada da rodovia ao terreno",
                "value": road.get("distance_to_parcel_m"),
                "unit": "m",
            },
            {
                "label": "Jurisdição publicada no SNV",
                "value": props.get("ds_jurisdi"),
            },
            {
                "label": "Condição publicada do trecho",
                "value": props.get("ds_legenda"),
            },
            {
                "label": "Superfície publicada do trecho",
                "value": props.get("ds_superfi"),
            },
            {
                "label": "Versão do Sistema Nacional de Viação",
                "value": props.get("versao_snv"),
            },
        ])
    if (context or {}).get("federal_roads"):
        out.append({
            "label": "Limite do contexto rodoviário federal",
            "value": (
                "Proximidade ao eixo do SNV não comprova acesso direto, "
                "alinhamento, faixa de domínio ou restrição específica "
                "no terreno."
            ),
        })
    return [
        item
        for item in out
        if item.get("value") not in (None, "")
    ]


def report_values(context: dict) -> list[dict]:
    return (
        territorial_report_values(context)
        + environment_report_values(context)
        + transport_report_values(context)
    )
