#!/usr/bin/env python3
"""Read-only parcel click API for the LoteDiretor public demo.

The endpoint accepts only a point inside the municipality of São Paulo and
queries the approved GeoSampa lote_cidadao WFS layer with a closed property
allowlist. It never requests owner/person fields.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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


THEMATIC_LAYERS = {
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


def build_context(lat: float, lng: float) -> dict:
    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(fetch_point_layer, key, lat, lng): key
            for key in THEMATIC_LAYERS
        }
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
        ]
        return values

    if section_id == "identity_location":
        return [
            {"label": "SQL", "value": p.get("sql_reference")},
            {"label": "CIB", "value": p.get("cib")},
            {"label": "Situação CIB", "value": p.get("cib_status")},
            {"label": "Setor", "value": p.get("fiscal_sector")},
            {"label": "Quadra", "value": p.get("fiscal_block")},
            {"label": "Lote", "value": p.get("fiscal_lot")},
            {"label": "Endereço", "value": address},
            {"label": "Complemento", "value": p.get("complement")},
            {"label": "Área do terreno", "value": p.get("land_area_m2"), "unit": "m²"},
        ]

    if section_id == "building_existing":
        return [
            {"label": "Área construída fiscal", "value": p.get("built_area_m2"), "unit": "m²"},
            {"label": "Uso cadastral", "value": p.get("use_description")},
            {"label": "Tipo de lote", "value": p.get("parcel_type")},
            {"label": "Situação do lote", "value": p.get("parcel_status")},
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
        if parsed.path != "/v1/sp/parcel":
            return self.send_json(404, {"error": "not_found"})

        params = urllib.parse.parse_qs(parsed.query)
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
            context = build_context(lat, lng)
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
