#!/usr/bin/env python3
"""Small, read-only federal geospatial context for LoteDiretor parcels.

National layers complement, but never replace, higher-resolution municipal/state
sources. All calls use closed public-field allowlists and fail soft.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

ANA_BASE = "https://www.snirh.gov.br/arcgis/rest/services/INDE/Camadas/MapServer"
ICMBIO_WFS = "https://geoservicos.inde.gov.br/geoserver/ICMBio/ows"
IBGE_AGGREGATES = "https://servicodados.ibge.gov.br/api/v3/agregados"

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
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise RuntimeError("federal_context_response_too_large")
    return json.loads(raw)


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


def load(lat: float, lng: float, municipality_ibge: str | None = None) -> dict:
    result = {
        "hydrology": {},
        "federal_conservation_units": [],
        "municipality_demographics": {},
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
            except Exception as exc:
                result["query_errors"][f"{group}_{key}"] = type(exc).__name__
    return result


def report_values(context: dict) -> list[dict]:
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
            out.append({
                "label": labels[level],
                "value": row.get(name_keys[level]),
            })
            out.append({
                "label": labels[level] + " · código",
                "value": row.get(code_keys[level]),
            })
    demo=(context or {}).get("municipality_demographics") or {}
    pop=demo.get("population") or {}
    hh=demo.get("households") or {}
    if (pop.get("93") or {}).get("value") is not None:
        out.append({
            "label":"Contexto municipal · população residente (Censo 2022)",
            "value":(pop.get("93") or {}).get("value"),
            "unit":"pessoas",
        })
    if (pop.get("614") or {}).get("value") is not None:
        out.append({
            "label":"Contexto municipal · densidade demográfica (Censo 2022)",
            "value":(pop.get("614") or {}).get("value"),
            "unit":"hab./km²",
        })
    if (hh.get("381") or {}).get("value") is not None:
        out.append({
            "label":"Contexto municipal · domicílios permanentes ocupados (Censo 2022)",
            "value":(hh.get("381") or {}).get("value"),
            "unit":"domicílios",
        })
    if (hh.get("5930") or {}).get("value") is not None:
        out.append({
            "label":"Contexto municipal · média de moradores por domicílio (Censo 2022)",
            "value":(hh.get("5930") or {}).get("value"),
            "unit":"pessoas",
        })
    if demo.get("interpretation"):
        out.append({
            "label":"Limite do contexto demográfico",
            "value":demo.get("interpretation"),
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
            "label": "Limite do contexto federal",
            "value": (context or {}).get("interpretation"),
        })
    return [x for x in out if x.get("value") not in (None, "")]
