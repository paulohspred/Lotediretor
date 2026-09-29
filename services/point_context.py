"""Federal/state context for any point in Brazil, without a municipal parcel.

Used when the municipality has no parcel engine yet (most of the ~5,570).
The analysis area is an explicit square buffer around the clicked point; it is
never presented as a lot boundary.
"""
from __future__ import annotations

import math
import re

import federal_context
import restriction_context

BUFFER_HALF_SIDE_M = 25.0
# Brazil's extent with margin (continental + oceanic islands).
BRAZIL_BOUNDS = (-74.5, -34.5, -28.0, 6.0)  # min_lng, min_lat, max_lng, max_lat
_IBGE = re.compile(r"^[0-9]{7}$")

SECTIONS = (
    ("restrictions", "Restrições nacionais",
     restriction_context.report_values),
    ("territorial", "Contexto territorial e socioeconômico",
     federal_context.territorial_report_values),
    ("environment", "Meio ambiente, rural e risco",
     federal_context.environment_report_values),
    ("mobility", "Mobilidade e infraestrutura federal",
     federal_context.transport_report_values),
)

SOURCE_LABELS = {
    "ana_macro": "ANA · divisão hidrográfica (macro)",
    "ana_meso": "ANA · divisão hidrográfica (meso)",
    "ana_micro": "ANA · divisão hidrográfica (micro)",
    "icmbio_federal_uc": "ICMBio · unidades de conservação",
    "funai_territories": "FUNAI · terras indígenas",
    "incra_sigef": "INCRA · SIGEF",
    "sicar_properties": "SICAR · imóveis rurais (CAR)",
    "sgb_risk": "SGB · setores de risco",
    "sgb_susceptibility": "SGB · suscetibilidade",
    "dnit_roads": "DNIT · rodovias federais",
    "overpass_mobility": "OpenStreetMap · mobilidade",
    "mapbiomas_land_cover": "MapBiomas · uso do solo",
    "ibge_municipality": "IBGE · Censo 2022 (município)",
    "ibge_sector": "IBGE · setor censitário",
    "siconfi_municipality_finance": "Tesouro · SICONFI",
    "transferegov_municipality": "Transferegov",
}


def validate(lat: float, lng: float, municipality_ibge: str) -> None:
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise ValueError("invalid_coordinates")
    min_lng, min_lat, max_lng, max_lat = BRAZIL_BOUNDS
    if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
        raise ValueError("outside_brazil")
    if not _IBGE.match(municipality_ibge or ""):
        raise ValueError("invalid_municipality_ibge")


def analysis_square(lat: float, lng: float, half_side_m: float = BUFFER_HALF_SIDE_M) -> dict:
    dlat = half_side_m / 111_320.0
    dlng = half_side_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    ring = [
        [lng - dlng, lat - dlat],
        [lng + dlng, lat - dlat],
        [lng + dlng, lat + dlat],
        [lng - dlng, lat + dlat],
        [lng - dlng, lat - dlat],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def build(lat: float, lng: float, municipality_ibge: str) -> dict:
    validate(lat, lng, municipality_ibge)
    area = analysis_square(lat, lng)
    context = federal_context.load(lat, lng, municipality_ibge, area)
    try:
        restrictions = restriction_context.query_geometry(area)
    except Exception:
        restrictions = {"hits": [], "unavailable": [{"layer_key": "national_restrictions", "status": "SOURCE_UNAVAILABLE"}]}
    sections = []
    for section_id, title, fn in SECTIONS:
        items = fn(restrictions if section_id == "restrictions" else context)
        if items:
            sections.append({"id": section_id, "title": title, "items": items})
    errors = context.get("query_errors") or {}
    restriction_unavailable = restriction_context.unavailable_labels(restrictions)
    return {
        "found": True,
        "mode": "POINT_CONTEXT",
        "municipality_ibge": municipality_ibge,
        "point": {"lat": lat, "lng": lng},
        "analysis_area": {
            "kind": "POINT_BUFFER",
            "half_side_m": BUFFER_HALF_SIDE_M,
            "geometry": area,
            "note": (
                "Área de análise de 50 m × 50 m centrada no ponto clicado. "
                "Não é o limite do lote."
            ),
        },
        "sections": sections,
        "unavailable_sources": sorted(
            [SOURCE_LABELS.get(key, key) for key in errors] + restriction_unavailable
        ),
        "queried_at": context.get("queried_at"),
        "interpretation": context.get("interpretation"),
    }
