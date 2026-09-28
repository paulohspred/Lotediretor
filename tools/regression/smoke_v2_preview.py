#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

WEB = "http://127.0.0.1:3001"
API = "http://127.0.0.1:3000"
MARTIN = "http://127.0.0.1:3002"

PARCELS = {
    "sp": ("3550308", -23.611284118235293, -46.72245915764705),
    "recife": ("2611606", -8.09162, -34.88415),
    "rio": ("3304557", -22.9558162586, -43.1835534124),
    "bh": ("3106200", -19.82495629, -43.9987863521),
    "jp": ("2507507", -7.0585194646808365, -34.847229023894556),
}

FORBIDDEN_PUBLIC_KEYS = {
    "source_id",
    "connector_status",
    "missing_fields",
    "query_errors",
    "context",
}


def get_json(url: str, timeout: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "LoteDiretor-v2-smoke"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.load(response)


def post_json(url: str, payload: dict, timeout: int = 180) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "LoteDiretor-v2-smoke",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.load(response)


def collect_keys(value) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            out.add(str(key))
            out.update(collect_keys(child))
    elif isinstance(value, list):
        for child in value:
            out.update(collect_keys(child))
    return out


def norm(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(char) != "Mn"
    ).strip().lower()


def tile_xy(lat: float, lng: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lng + 180) / 360 * n)
    latr = math.radians(lat)
    y = int((1 - math.asinh(math.tan(latr)) / math.pi) / 2 * n)
    return x, y


def ok(message: str) -> None:
    print(f"OK {message}")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"ERROR {message}")


def main() -> int:
    errors: list[str] = []

    status, health = get_json(API + "/healthz")
    if status == 200 and health.get("ok") is True:
        ok("Platform API health")
    else:
        fail(errors, "Platform API health")

    with urllib.request.urlopen(WEB + "/", timeout=30) as response:
        html = response.read().decode("utf-8", "ignore")
    if response.status == 200 and "Explorer" in html and "3D urbano" in html:
        ok("Client Web Explorer shell")
    else:
        fail(errors, "Client Web Explorer shell")

    for name, (ibge, lat, lng) in PARCELS.items():
        try:
            status, body = post_json(
                WEB + "/api/parcel/resolve",
                {"municipality_ibge": ibge, "lat": lat, "lng": lng},
            )
        except Exception as exc:
            fail(errors, f"{name}: resolver request failed {type(exc).__name__}")
            continue

        parcel = body.get("parcel") or {}
        dossier = body.get("dossier") or {}
        sections = dossier.get("sections") or []
        keys = collect_keys(body)

        if status != 200 or not body.get("found") or not parcel.get("geometry"):
            fail(errors, f"{name}: normalized parcel contract")
            continue
        if not sections or not any(section.get("items") for section in sections):
            fail(errors, f"{name}: human dossier sections")
        else:
            ok(f"{name}: normalized parcel + human dossier")

        leaked = sorted(keys & FORBIDDEN_PUBLIC_KEYS)
        if leaked:
            fail(errors, f"{name}: public contract leaked technical keys {leaked}")
        else:
            ok(f"{name}: no technical-key leakage")

    params = urllib.parse.urlencode(
        {
            "q": "Rua Senador Otavio Mangabeira 71",
            "ibge": "3550308",
        }
    )
    status, search = get_json(WEB + "/api/search/address?" + params, 30)
    results = search.get("results") or []
    bad_city = []
    for item in results:
        address = item.get("address") or {}
        locality = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or ""
        )
        if norm(locality) != "sao paulo":
            bad_city.append(locality)
    if status == 200 and results and not bad_city:
        ok("address search constrained to São Paulo municipality")
    else:
        fail(errors, f"address search municipality constraint {bad_city!r}")

    status, catalog = get_json(MARTIN + "/catalog", 30)
    tile_sources = set((catalog.get("tiles") or {}).keys())
    expected_sources = {
        "ibge_censo2022_setores",
        "jp_lotes",
        "jp_curvas_nivel_2022",
    }
    if status == 200 and tile_sources == expected_sources:
        ok("Martin source allowlist")
    else:
        fail(
            errors,
            f"Martin source allowlist expected={sorted(expected_sources)} got={sorted(tile_sources)}",
        )

    jp_lat = PARCELS["jp"][1]
    jp_lng = PARCELS["jp"][2]
    z = 18
    x, y = tile_xy(jp_lat, jp_lng, z)
    tile_url = f"{WEB}/api/tiles/jp_lotes/{z}/{x}/{y}"
    try:
        with urllib.request.urlopen(tile_url, timeout=30) as response:
            data = response.read()
            ctype = response.headers.get("content-type", "")
        if response.status == 200 and "protobuf" in ctype and data:
            ok("same-origin Martin MVT proxy")
        else:
            fail(errors, "same-origin Martin MVT proxy")
    except Exception as exc:
        fail(errors, f"same-origin Martin MVT proxy {type(exc).__name__}")

    try:
        urllib.request.urlopen(WEB + "/api/tiles/not_allowed/1/1/1", timeout=10)
        fail(errors, "tile proxy rejected unknown source")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            ok("tile proxy rejects unknown source")
        else:
            fail(errors, f"tile proxy unknown source returned {exc.code}")

    if errors:
        print(f"\nFAIL {len(errors)} v2 smoke checks")
        return 1

    print("\nPASS LoteDiretor v2 preview smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
