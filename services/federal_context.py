#!/usr/bin/env python3
"""Small, read-only federal geospatial context for LoteDiretor parcels.

National layers complement, but never replace, higher-resolution municipal/state
sources. All calls use closed public-field allowlists and fail soft.
"""
from __future__ import annotations

import gzip
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform

ANA_BASE = "https://www.snirh.gov.br/arcgis/rest/services/INDE/Camadas/MapServer"
ICMBIO_WFS = "https://geoservicos.inde.gov.br/geoserver/ICMBio/ows"
IBGE_AGGREGATES = "https://servicodados.ibge.gov.br/api/v3/agregados"
SGB_SUSCET = "https://geoportal.sgb.gov.br/server/rest/services/Hosted/Base_Suscet_v2/FeatureServer/0"
DNIT_WFS = "https://geoservicos.inde.gov.br/geoserver/DNIT/ows"
FUNAI_WFS = "https://geoserver.funai.gov.br/geoserver/ows"

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


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_json(url: str, limit: int = 2_000_000) -> dict:
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
    try:
        text = raw.decode(charset)
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="strict")
    return json.loads(text)


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
    return {k: attrs.get(k) for k in fields if attrs.get(k) is not None}


def icmbio_at_point(lat: float, lng: float) -> list[dict]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "ICMBio:limiteucsfederais_a",
        "srsName": "EPSG:4326",
        "count": "20",
        "propertyName": ",".join(ICMBIO_FIELDS),
        "cql_filter": (
            f"INTERSECTS(the_geom,SRID=4326;POINT({lng} {lat}))"
        ),
        "outputFormat": "application/json",
    }
    data = _get_json(ICMBIO_WFS + "?" + urllib.parse.urlencode(params))
    out = []
    allowed = set(ICMBIO_FIELDS)
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if set(props) - allowed:
            raise RuntimeError("icmbio_unexpected_fields")
        out.append({
            k: props.get(k)
            for k in ICMBIO_FIELDS
            if props.get(k) is not None
        })
    return out


def _ibge_aggregate(table: str, variables: list[str], municipality_ibge: str) -> dict:
    variable_path = "|".join(variables)
    url = (
        f"{IBGE_AGGREGATES}/{table}/periodos/2022/variaveis/{variable_path}"
        f"?localidades=N6[{municipality_ibge}]"
    )
    data = _get_json(url)
    out = {}
    for row in data if isinstance(data, list) else []:
        var_id = str(row.get("id"))
        results = row.get("resultados") or []
        series = (results[0].get("series") or []) if results else []
        if not series:
            continue
        place = series[0].get("localidade") or {}
        value = (series[0].get("serie") or {}).get("2022")
        out[var_id] = {
            "name": row.get("variavel"),
            "unit": row.get("unidade"),
            "value": value,
            "municipality": place.get("nome"),
            "municipality_ibge": place.get("id"),
            "territorial_level": ((place.get("nivel") or {}).get("nome")),
        }
    return out


def ibge_municipality_context(municipality_ibge: str) -> dict:
    population = _ibge_aggregate("4714", ["93", "6318", "614"], municipality_ibge)
    households = _ibge_aggregate("4712", ["381", "382", "5930"], municipality_ibge)
    return {
        "year": 2022,
        "population": population,
        "households": households,
        "interpretation": (
            "Indicadores do Censo 2022 no nível do município. São contexto "
            "territorial e não descrevem diretamente o lote, a quadra ou o "
            "setor censitário do imóvel."
        ),
    }


def sgb_municipality_context(municipality_ibge: str) -> dict:
    fields = [
        "nm_municip", "cd_geocmu", "uf", "carta_suscet", "ano_execucao",
        "mes_public", "ano_public", "area_municipio", "area_mapeada",
        "mov_massa_alta", "mov_massa_media", "mov_massa_baixa",
        "inundacao_alta", "inundacao_media", "inundacao_baixa",
    ]
    params = {
        "f": "json",
        "where": f"cd_geocmu='{municipality_ibge}'",
        "outFields": ",".join(fields),
        "returnGeometry": "false",
        "resultRecordCount": "5",
    }
    data = _get_json(SGB_SUSCET + "/query?" + urllib.parse.urlencode(params))
    features = data.get("features") or []
    if not features:
        return {}
    attrs = features[0].get("attributes") or {}
    allowed = set(fields)
    if set(attrs) - allowed:
        raise RuntimeError("sgb_unexpected_fields")
    return {k: attrs.get(k) for k in fields if attrs.get(k) is not None}


def dnit_near_point(lat: float, lng: float, max_distance_m: float = 1000.0) -> list[dict]:
    fields = [
        "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr", "ds_local_i",
        "ds_local_f", "ds_sup_fed", "ds_obra", "ds_jurisdi",
        "ds_superfi", "versao_snv",
    ]
    delta = 0.02
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "DNIT:snv_202507a",
        "srsName": "EPSG:4326",
        "count": "80",
        "bbox": f"{lng-delta},{lat-delta},{lng+delta},{lat+delta},EPSG:4326",
        "propertyName": ",".join(["the_geom", *fields]),
        "outputFormat": "application/json",
    }
    data = _get_json(DNIT_WFS + "?" + urllib.parse.urlencode(params), 4_000_000)
    metric_transform = Transformer.from_crs(
        "EPSG:4326", "EPSG:3857", always_xy=True
    ).transform
    point_metric = shapely_transform(metric_transform, Point(lng, lat))
    out = []
    allowed = set(fields)
    for feature in data.get("features") or []:
        geom = feature.get("geometry")
        props = feature.get("properties") or {}
        props.pop("ogc_fid", None)
        if not geom:
            continue
        if set(props) - allowed:
            raise RuntimeError("dnit_unexpected_fields")
        try:
            geom_metric = shapely_transform(metric_transform, shape(geom))
            distance_m = float(point_metric.distance(geom_metric))
        except Exception:
            continue
        if distance_m <= max_distance_m:
            out.append({
                "distance_m": round(distance_m, 1),
                "properties": {
                    k: props.get(k)
                    for k in fields
                    if props.get(k) is not None
                },
            })
    return sorted(out, key=lambda x: x["distance_m"])[:8]


def funai_at_point(lat: float, lng: float) -> list[dict]:
    fields = [
        "terrai_codigo", "terrai_nome", "municipio_nome", "uf_sigla",
        "superficie_perimetro_ha", "fase_ti", "modalidade_ti",
        "reestudo_ti", "faixa_fronteira", "dominio_uniao",
        "data_atualizacao",
    ]
    delta = 0.00001
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": "Funai:tis_poligonais",
        "srsName": "EPSG:4326",
        "maxFeatures": "20",
        "bbox": f"{lng-delta},{lat-delta},{lng+delta},{lat+delta},EPSG:4326",
        "propertyName": ",".join(["the_geom", *fields]),
        "outputFormat": "application/json",
    }
    data = _get_json(FUNAI_WFS + "?" + urllib.parse.urlencode(params))
    allowed = set(fields)
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if set(props) - allowed:
            raise RuntimeError("funai_unexpected_fields")
        out.append({
            k: props.get(k)
            for k in fields
            if props.get(k) is not None
        })
    return out


def load(lat: float, lng: float, municipality_ibge: str | None = None) -> dict:
    result = {
        "hydrology": {},
        "federal_conservation_units": [],
        "municipality_demographics": {},
        "sgb_susceptibility": {},
        "nearby_federal_roads": [],
        "indigenous_territories": [],
        "query_errors": {},
        "queried_at": now(),
        "interpretation": (
            "Contexto federal complementar. Divisão hidrográfica não equivale "
            "a risco de inundação. Ausência de unidade de conservação federal "
            "no ponto não exclui proteção estadual, municipal, APP, tombamento "
            "ou outras restrições."
        ),
    }
    jobs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for level in ANA_LAYERS:
            jobs[pool.submit(ana_region, level, lat, lng)] = ("ana", level)
        jobs[pool.submit(icmbio_at_point, lat, lng)] = ("icmbio", "federal_uc")
        if municipality_ibge:
            jobs[
                pool.submit(ibge_municipality_context, municipality_ibge)
            ] = ("ibge", "municipality")
            jobs[
                pool.submit(sgb_municipality_context, municipality_ibge)
            ] = ("sgb", "susceptibility")
        jobs[pool.submit(dnit_near_point, lat, lng)] = ("dnit", "roads")
        jobs[pool.submit(funai_at_point, lat, lng)] = ("funai", "territories")
        for future in as_completed(jobs):
            group, key = jobs[future]
            try:
                value = future.result()
                if group == "ana":
                    result["hydrology"][key] = value
                elif group == "icmbio":
                    result["federal_conservation_units"] = value
                elif group == "ibge":
                    result["municipality_demographics"] = value
                elif group == "sgb":
                    result["sgb_susceptibility"] = value
                elif group == "dnit":
                    result["nearby_federal_roads"] = value
                elif group == "funai":
                    result["indigenous_territories"] = value
            except Exception as exc:
                result["query_errors"][f"{group}_{key}"] = type(exc).__name__
    return result


def territorial_report_values(context: dict) -> list[dict]:
    out = []
    hyd = (context or {}).get("hydrology") or {}
    labels = {
        "macro": "Macrorregião hidrográfica (ANA/IBGE)",
        "meso": "Mesorregião hidrográfica (ANA/IBGE)",
        "micro": "Microrregião hidrográfica (ANA/IBGE)",
    }
    name_keys = {"macro": "DMA_NM", "meso": "DME_NM", "micro": "DMI_NM"}
    code_keys = {"macro": "DMA_CD", "meso": "DME_CD", "micro": "DMI_CD"}
    for level in ("macro", "meso", "micro"):
        row = hyd.get(level) or {}
        if row.get(name_keys[level]):
            out.extend([
                {"label": labels[level], "value": row.get(name_keys[level])},
                {"label": labels[level] + " · código", "value": row.get(code_keys[level])},
            ])
    demo = (context or {}).get("municipality_demographics") or {}
    pop = demo.get("population") or {}
    hh = demo.get("households") or {}
    values = [
        ("Contexto municipal · população residente (Censo 2022)", (pop.get("93") or {}).get("value"), "pessoas"),
        ("Contexto municipal · densidade demográfica (Censo 2022)", (pop.get("614") or {}).get("value"), "hab./km²"),
        ("Contexto municipal · domicílios permanentes ocupados (Censo 2022)", (hh.get("381") or {}).get("value"), "domicílios"),
        ("Contexto municipal · média de moradores por domicílio (Censo 2022)", (hh.get("5930") or {}).get("value"), "pessoas"),
    ]
    for label, value, unit in values:
        if value is not None:
            out.append({"label": label, "value": value, "unit": unit})
    if demo.get("interpretation"):
        out.append({"label": "Limite do contexto demográfico", "value": demo.get("interpretation")})
    out.append({
        "label": "Limite da divisão hidrográfica",
        "value": "A divisão hidrográfica informa em qual região/bacia o terreno está inserido; não representa risco de inundação.",
    })
    return [x for x in out if x.get("value") not in (None, "")]


def environment_report_values(context: dict) -> list[dict]:
    out = []
    sgb = (context or {}).get("sgb_susceptibility") or {}
    if str(sgb.get("carta_suscet") or "").strip().lower() == "sim":
        out.extend([
            {"label": "Carta municipal de suscetibilidade (SGB)", "value": "Disponível"},
            {"label": "Ano de execução da carta do SGB", "value": sgb.get("ano_execucao")},
            {"label": "Ano de publicação da carta do SGB", "value": sgb.get("ano_public")},
            {"label": "Área municipal mapeada pelo SGB", "value": sgb.get("area_mapeada"), "unit": "km²"},
            {"label": "SGB · área de alta suscetibilidade a movimentos de massa", "value": sgb.get("mov_massa_alta"), "unit": "km²"},
            {"label": "SGB · área de alta suscetibilidade a inundação", "value": sgb.get("inundacao_alta"), "unit": "km²"},
            {"label": "Limite da carta do SGB", "value": "Os valores são síntese municipal da cartografia de suscetibilidade e não classificam este lote individualmente."},
        ])
    for ti in (context or {}).get("indigenous_territories") or []:
        out.extend([
            {"label": "Terra indígena federal", "value": ti.get("terrai_nome")},
            {"label": "Fase da terra indígena", "value": ti.get("fase_ti")},
            {"label": "Modalidade da terra indígena", "value": ti.get("modalidade_ti")},
            {"label": "Área publicada pela FUNAI", "value": ti.get("superficie_perimetro_ha"), "unit": "ha"},
            {"label": "Atualização FUNAI", "value": ti.get("data_atualizacao")},
        ])
    if (context or {}).get("indigenous_territories"):
        out.append({
            "label": "Limite da incidência FUNAI",
            "value": "A incidência territorial é baseada na geometria pública da FUNAI e requer leitura jurídica própria; não identifica titularidade privada do imóvel.",
        })
    for uc in (context or {}).get("federal_conservation_units") or []:
        out.extend([
            {"label": "Unidade de conservação federal", "value": uc.get("nomeuc")},
            {"label": "Categoria da unidade de conservação federal", "value": uc.get("categoria_") or uc.get("grupouc")},
            {"label": "Ato de criação da unidade federal", "value": uc.get("criacaoato")},
            {"label": "Bioma da unidade federal", "value": uc.get("bioma_pred") or uc.get("biomas")},
        ])
    if out:
        out.append({
            "label": "Limite do contexto ambiental federal",
            "value": "Ausência de incidência federal não exclui proteção estadual, municipal, APP, tombamento ou outras restrições.",
        })
    return [x for x in out if x.get("value") not in (None, "")]


def transport_report_values(context: dict) -> list[dict]:
    out = []
    for road in (context or {}).get("nearby_federal_roads") or []:
        p = road.get("properties") or {}
        br = p.get("vl_br")
        out.extend([
            {"label": "Rodovia do SNV próxima", "value": ("BR-" + str(br).zfill(3)) if br else p.get("nm_tipo_tr")},
            {"label": "Distância aproximada ao eixo do SNV", "value": road.get("distance_m"), "unit": "m"},
            {"label": "Jurisdição publicada no SNV", "value": p.get("ds_jurisdi")},
            {"label": "Trecho SNV", "value": " → ".join(x for x in [p.get("ds_local_i"), p.get("ds_local_f")] if x)},
            {"label": "Versão SNV", "value": p.get("versao_snv")},
        ])
    if (context or {}).get("nearby_federal_roads"):
        out.append({
            "label": "Limite do contexto rodoviário federal",
            "value": "Proximidade ao eixo do SNV não comprova acesso direto, alinhamento, faixa de domínio ou restrição específica no terreno.",
        })
    return [x for x in out if x.get("value") not in (None, "")]


def report_values(context: dict) -> list[dict]:
    return (
        territorial_report_values(context)
        + environment_report_values(context)
        + transport_report_values(context)
    )
