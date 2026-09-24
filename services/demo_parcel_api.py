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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
            return self.send_json(200, {
                "found": True,
                "clicked": {"lat": lat, "lng": lng},
                "feature": public_feature(selected),
                "source": {
                    "id": "sp-sao-paulo-geosampa-wfs",
                    "authority": "Prefeitura de São Paulo / GeoSampa",
                    "layer": TYPE_NAME,
                    "license": "CC BY-SA 4.0",
                    "queried_at": utc_now(),
                    "method": "WFS 2.0 bbox candidate query + server-side point-in-polygon",
                },
            })
        except Exception as exc:
            print(f"upstream error: {exc!r}", flush=True)
            return self.send_json(502, {"error": "upstream_unavailable"})


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LoteDiretor parcel API listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()
