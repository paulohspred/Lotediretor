#!/usr/bin/env python3
"""Discover parcel/zoning layers in a municipal GIS and draft a connector spec.

Supports ArcGIS REST (…/rest/services, a folder, a MapServer/FeatureServer or
a single layer) and OGC WFS (GetCapabilities + DescribeFeatureType).

The output is a DRAFT spec: a person must confirm the layer, the field
mapping and the license before setting status=APPROVED (Blueprint §19).

Usage:
    python3 tools/factory/discover.py --ibge 4209102 \
        --source-id sc-joinville-simgeo-arcgis \
        https://geo.joinville.sc.gov.br/server/rest/services
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec import PERSONAL_FIELD, SPEC_DIR  # noqa: E402

USER_AGENT = "LoteDiretor-discovery/1.0 (+https://lotediretor.com)"
MAX_SERVICES = 200

ROLE_NAME_HINTS = {
    "parcels": re.compile(r"\b(lote|lotes|parcela|cadastr|imovel|imoveis|terreno)", re.I),
    "zoning": re.compile(r"(zonea|zona|zoning|macrozon|uso_do_solo|luos|lpuos)", re.I),
}
FIELD_HINTS = {
    "upstream_key": re.compile(r"^(objectid|fid|gid|id)$", re.I),
    "fiscal_reference": re.compile(r"(inscri|insc_|sql|cod_?imov|cadastr|indic_fiscal|ctm)", re.I),
    "street": re.compile(r"(logradouro|endereco|rua|nm_log)", re.I),
    "house_number": re.compile(r"^(numero|num|nr|n_porta|numero_predial)$", re.I),
    "neighborhood": re.compile(r"(bairro)", re.I),
    "land_area_m2": re.compile(r"(area_?terr|area_?lote|area_m2|shape_area)", re.I),
    "zone_code": re.compile(r"^(sigla|zona|cod_?zona|zoneamento|zone)$", re.I),
    "zone_name": re.compile(r"(nome|descri|nm_zona)", re.I),
}


def get(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(20_000_000)


def get_json(url: str) -> dict:
    sep = "&" if "?" in url else "?"
    return json.loads(get(f"{url}{sep}f=json"))


# --------------------------------------------------------------------------
# ArcGIS REST
# --------------------------------------------------------------------------

def arcgis_layers(url: str) -> list[dict]:
    url = url.rstrip("/")
    doc = get_json(url)
    if "fields" in doc and "geometryType" in doc:  # a single layer
        return [{"url": url, "name": doc.get("name", ""), "geometry": doc["geometryType"],
                 "fields": [f["name"] for f in doc.get("fields") or []]}]
    out: list[dict] = []
    if "layers" in doc:  # MapServer / FeatureServer
        for layer in doc["layers"]:
            if layer.get("subLayerIds"):
                continue
            out.extend(arcgis_layers(f"{url}/{layer['id']}"))
        return out
    root = url.split("/rest/services")[0] + "/rest/services"
    services = list(doc.get("services") or [])
    for folder in doc.get("folders") or []:
        services += get_json(f"{root}/{folder}").get("services") or []
    for service in services[:MAX_SERVICES]:
        if service.get("type") not in {"MapServer", "FeatureServer"}:
            continue
        try:
            out.extend(arcgis_layers(f"{root}/{service['name']}/{service['type']}"))
        except Exception as exc:  # keep discovering other services
            print(f"skip {service['name']}: {exc}", file=sys.stderr)
    return out


# --------------------------------------------------------------------------
# OGC WFS
# --------------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def wfs_layers(url: str) -> list[dict]:
    base = url.split("?")[0]
    caps = ET.fromstring(get(f"{base}?service=WFS&request=GetCapabilities&version=2.0.0"))
    names = [el.text for el in caps.iter() if _local(el.tag) == "Name"
             and el.text and ":" in el.text]
    out = []
    for name in dict.fromkeys(names):
        try:
            schema = ET.fromstring(get(
                f"{base}?service=WFS&request=DescribeFeatureType&version=2.0.0&"
                + urllib.parse.urlencode({"typeNames": name})))
        except Exception as exc:
            print(f"skip {name}: {exc}", file=sys.stderr)
            continue
        fields = [el.get("name") for el in schema.iter()
                  if _local(el.tag) == "element" and el.get("name")]
        geometry = next((el.get("type") for el in schema.iter()
                         if _local(el.tag) == "element"
                         and "gml:" in (el.get("type") or "")), "")
        out.append({"url": base, "type_name": name, "name": name,
                    "geometry": geometry, "fields": fields})
    return out


# --------------------------------------------------------------------------
# Drafting
# --------------------------------------------------------------------------

def is_polygon(layer: dict) -> bool:
    return bool(re.search(r"polygon|surface", layer.get("geometry", ""), re.I))


def score(layer: dict, role: str) -> int:
    s = 5 if ROLE_NAME_HINTS[role].search(layer["name"]) else 0
    wanted = ["fiscal_reference", "street"] if role == "parcels" else ["zone_code"]
    s += sum(2 for key in wanted
             if any(FIELD_HINTS[key].search(f) for f in layer["fields"]))
    return s if is_polygon(layer) else 0


def guess_fields(layer: dict, role: str) -> dict:
    keys = (["upstream_key", "fiscal_reference", "street", "house_number",
             "neighborhood", "land_area_m2"] if role == "parcels"
            else ["upstream_key", "zone_code", "zone_name"])
    mapping = {}
    for key in keys:
        match = next((f for f in layer["fields"]
                      if FIELD_HINTS[key].search(f) and not PERSONAL_FIELD.search(f)
                      and f not in mapping.values()), None)
        if match:
            mapping[key] = match
    return mapping


def draft(ibge: str, source_id: str, kind: str, layers: list[dict]) -> dict:
    spec = {"municipality_ibge": ibge, "status": "DRAFT",
            "notes": "Gerado por discover.py. Revise camada, campos e licença.",
            "layers": []}
    for role in ("parcels", "zoning"):
        ranked = sorted(layers, key=lambda l: score(l, role), reverse=True)
        if not ranked or score(ranked[0], role) == 0:
            continue
        best = ranked[0]
        entry = {"role": role, "source_id": source_id, "kind": kind,
                 "url": best["url"], "license": "",
                 "fields": guess_fields(best, role),
                 "min_features": 100 if role == "parcels" else 1,
                 "candidates": [f"{l['name']} ({l['url']})" for l in ranked[:5]
                                if score(l, role) > 0],
                 "personal_fields_excluded": [f for f in best["fields"]
                                              if PERSONAL_FIELD.search(f)]}
        if kind == "ogc_wfs":
            entry["type_name"] = best["type_name"]
        spec["layers"].append(entry)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--ibge", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--kind", choices=["arcgis", "wfs"], default=None)
    parser.add_argument("--write", action="store_true",
                        help=f"write the draft to {SPEC_DIR}/<ibge>.json")
    args = parser.parse_args()

    kind = args.kind or ("arcgis" if "/rest/services" in args.url else "wfs")
    layers = arcgis_layers(args.url) if kind == "arcgis" else wfs_layers(args.url)
    spec = draft(args.ibge, args.source_id,
                 "arcgis_feature_layer" if kind == "arcgis" else "ogc_wfs", layers)
    text = json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        target = SPEC_DIR / f"{args.ibge}.json"
        if target.exists():
            parser.error(f"{target} exists; not overwriting a reviewed spec")
        target.write_text(text, encoding="utf-8")
        print(f"draft written to {target}")
    else:
        sys.stdout.write(text)
    print(f"{len(layers)} layers inspected", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
