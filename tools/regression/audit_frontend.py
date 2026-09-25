#!/usr/bin/env python3
"""Static product-surface audit for the LoteDiretor single-page frontend."""
from __future__ import annotations

from pathlib import Path

HTML = Path("public/lotediretor/index.html")

REQUIRED = (
    'id="view2d"',
    'id="view3d"',
    'Buscar endereço, rua ou identificação do lote',
    'renderParcelDimensions',
    'selected-official-buildings-3d',
    'Leitura rápida do terreno',
    '/api/parcel/v1/geocode',
    'layerLabelsByCity',
)

FORBIDDEN_VISIBLE = (
    "Situação do município",
    "GeoSampa · lote_cidadao",
    ">READY<",
    ">PARTIAL<",
    ">QUERY<",
    ">PRIVATE<",
    "connector_status",
    "source_id",
)

def main() -> int:
    text = HTML.read_text(encoding="utf-8")
    before_script = text.split("<script", 1)[0]

    errors: list[str] = []

    for token in REQUIRED:
        if token not in text:
            errors.append(f"missing required frontend contract: {token}")

    for token in FORBIDDEN_VISIBLE:
        if token in before_script:
            errors.append(f"technical/internal token visible in HTML: {token}")

    # Literal backslash+n in static markup is almost always a patching error.
    if r"\n" in before_script:
        errors.append("literal \\n sequence found in visible markup")

    # City-specific map coverage expected in the first wave.
    for ibge in ("3550308", "2611606", "3304557", "3106200", "2507507"):
        if f'"{ibge}":{{' not in text:
            errors.append(f"missing city layer map: {ibge}")

    if errors:
        for error in errors:
            print("FAIL", error)
        return 1

    print("FRONTEND AUDIT PASSED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
