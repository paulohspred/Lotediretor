#!/usr/bin/env python3
"""First-wave production smoke tests for LoteDiretor.

Runs against the local parcel API by default. No writes, no bulk downloads.
Validates representative real parcels, same-origin geocoding contract and
user-facing report hygiene.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8765"

PARCEL_CASES = [
    ("sp", "/v1/sp/parcel", -23.611284118235293, -46.72245915764705),
    ("recife", "/v1/recife/parcel", -8.09162, -34.88415),
    ("rio", "/v1/rio/parcel", -22.9558162586, -43.1835534124),
    ("bh", "/v1/bh/parcel", -19.82495629, -43.9987863521),
    ("jp", "/v1/jp/parcel", -7.0585194646808365, -34.847229023894556),
]

FORBIDDEN_REPORT_TOKENS = (
    "PROVIDER_TERRITORY_ONLY",
    "NETWORK_CONTEXT",
    "SUBMUNICIPAL_REQUIRED",
    "GetFeatureInfo",
    "ZONEAMENTO_11181",
    "bulk público IPTU_INTER",
    "Exact SQL matches",
)

def get_json(url: str, timeout: int = 180):
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "LoteDiretor-Smoke/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.load(response)

def fail(errors: list[str], message: str):
    errors.append(message)
    print("FAIL", message)

def ok(message: str):
    print("OK  ", message)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()
    base = args.base.rstrip("/")
    errors: list[str] = []
    payloads = {}

    status, health = get_json(base + "/healthz", 20)
    if status != 200 or not health.get("ok"):
        fail(errors, "healthz")
    else:
        ok("healthz")

    for name, path, lat, lng in PARCEL_CASES:
        url = base + path + "?" + urllib.parse.urlencode({"lat": lat, "lng": lng})
        try:
            status, payload = get_json(url)
        except Exception as exc:
            fail(errors, f"{name}: request failed: {type(exc).__name__}")
            continue

        if status != 200 or not payload.get("found"):
            fail(errors, f"{name}: parcel not found")
            continue

        payloads[name] = payload
        ctx = payload.get("context") or {}
        query_errors = ctx.get("query_errors") or {}
        if query_errors:
            fail(errors, f"{name}: query_errors={query_errors}")
        else:
            ok(f"{name}: parcel + sources")

        report_text = json.dumps(
            (payload.get("report") or {}).get("sections") or [],
            ensure_ascii=False,
        )
        leaked = [token for token in FORBIDDEN_REPORT_TOKENS if token in report_text]
        if leaked:
            fail(errors, f"{name}: technical labels leaked: {leaked}")
        else:
            ok(f"{name}: report language")

    # Search contract used by the UI.
    try:
        status, search = get_json(base + "/v1/sp/search?q=12318300101")
        if status == 200 and search.get("count") == 1:
            ok("sp: SQL search")
        else:
            fail(errors, "sp: SQL search")
    except Exception as exc:
        fail(errors, f"sp: SQL search failed: {type(exc).__name__}")

    # Same-origin geocode endpoint; browser does not depend on third-party CORS.
    params = urllib.parse.urlencode(
        {"q": "Avenida Paulista", "city": "São Paulo", "uf": "SP"}
    )
    try:
        status, geocode = get_json(base + "/v1/geocode?" + params, 60)
        if status == 200 and geocode.get("count", 0) > 0:
            ok("geocode: address search")
        else:
            fail(errors, "geocode: no address result")
    except Exception as exc:
        fail(errors, f"geocode: request failed: {type(exc).__name__}")

    # Evidence-specific checks.
    rio = (payloads.get("rio") or {}).get("context", {}).get("terrain", {})
    rio_profiles = {p.get("name") for p in rio.get("profiles") or []}
    if {"A-A", "B-B"} <= rio_profiles:
        ok("rio: A-A/B-B MDT profiles")
    else:
        fail(errors, f"rio: missing profiles {sorted({'A-A','B-B'} - rio_profiles)}")

    jp_ctx = (payloads.get("jp") or {}).get("context", {})
    jp_planning = jp_ctx.get("planning") or {}
    jp_zone = ((jp_planning.get("zoning") or {}).get("properties") or {}).get("sigla")
    jp_params = jp_planning.get("parameters") or {}
    if jp_zone == "ZEPA2" and jp_params.get("ia_basic") == 1.0 and jp_params.get("ia_max") == 1.0:
        ok("jp: zoning + IA resolver")
    else:
        fail(errors, f"jp: planning resolver unexpected ({jp_zone}, {jp_params.get('ia_basic')}, {jp_params.get('ia_max')})")

    jp_profiles = {
        p.get("name")
        for p in (jp_ctx.get("terrain") or {}).get("profiles") or []
    }
    if {"A-A", "B-B"} <= jp_profiles:
        ok("jp: contour A-A/B-B profiles")
    else:
        fail(errors, "jp: contour profiles")

    recife_ctx = (payloads.get("recife") or {}).get("context", {})
    if len(recife_ctx.get("buildings") or []) >= 1:
        ok("recife: official 3D building resolver")
    else:
        fail(errors, "recife: official 3D building resolver")
    classes = {
        (x.get("properties") or {}).get("CATEGORIA_FUNCIONAL")
        for x in (recife_ctx.get("transport") or {}).get("functional_class") or []
    }
    if "Coletora" in classes:
        ok("recife: road functional class")
    else:
        fail(errors, f"recife: road class {sorted(x for x in classes if x)}")

    bh = (payloads.get("bh") or {}).get("context", {}).get("terrain", {})
    if bh.get("available") and (bh.get("profiles") or []):
        ok("bh: official contour profile")
    else:
        fail(errors, "bh: contour profile unavailable")

    if errors:
        print("\nSMOKE FAILED:", len(errors), "error(s)")
        return 1

    print("\nSMOKE PASSED: first-wave parcel workflow is healthy")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
