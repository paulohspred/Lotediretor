#!/usr/bin/env python3
"""
LoteDiretor source catalog discovery helper.

Discovers metadata from public, documented geospatial/open-data interfaces.
It deliberately does NOT bypass authentication, CAPTCHAs, robots controls,
paywalls, or scrape Google Maps/Street View.

Examples:
  python tools/discovery/harvest.py ckan https://dados.recife.pe.gov.br --query IPTU
  python tools/discovery/harvest.py arcgis https://example.gov.br/arcgis/rest/services
  python tools/discovery/harvest.py wfs https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


USER_AGENT = "LoteDiretor-SourceDiscovery/0.1 (+https://github.com/paulohspred/Lotediretor)"


def fetch(url: str, timeout: int = 30) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), dict(response.headers.items())


def fetch_json(url: str) -> dict:
    body, _ = fetch(url)
    return json.loads(body.decode("utf-8"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_ckan(base_url: str, query: str, rows: int) -> dict:
    api = base_url.rstrip("/") + "/api/3/action/package_search"
    params = urllib.parse.urlencode({"q": query, "rows": rows})
    payload = fetch_json(f"{api}?{params}")
    if not payload.get("success"):
        raise RuntimeError("CKAN API returned success=false")

    datasets = []
    for item in payload["result"]["results"]:
        datasets.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "title": item.get("title"),
                "organization": (item.get("organization") or {}).get("title"),
                "license_id": item.get("license_id"),
                "license_title": item.get("license_title"),
                "metadata_modified": item.get("metadata_modified"),
                "tags": [tag.get("name") for tag in item.get("tags", [])],
                "resources": [
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "format": r.get("format"),
                        "url": r.get("url"),
                        "last_modified": r.get("last_modified"),
                    }
                    for r in item.get("resources", [])
                ],
            }
        )
    return {
        "kind": "ckan",
        "source": base_url,
        "query": query,
        "discovered_at": now(),
        "count": len(datasets),
        "datasets": datasets,
    }


def arcgis_services_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    query["f"] = ["pjson"]
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
    )


def discover_arcgis(url: str) -> dict:
    payload = fetch_json(arcgis_services_url(url))
    out = {
        "kind": "arcgis",
        "source": url,
        "discovered_at": now(),
        "currentVersion": payload.get("currentVersion"),
        "folders": payload.get("folders", []),
        "services": payload.get("services", []),
    }
    if "layers" in payload:
        out["layers"] = payload.get("layers", [])
        out["tables"] = payload.get("tables", [])
        out["serviceDescription"] = payload.get("serviceDescription")
        out["spatialReference"] = payload.get("spatialReference")
    return out


def discover_wfs(url: str) -> dict:
    params = urllib.parse.urlencode(
        {"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"}
    )
    joiner = "&" if "?" in url else "?"
    body, headers = fetch(f"{url}{joiner}{params}")
    root = ET.fromstring(body)

    feature_types = []
    for elem in root.iter():
        if elem.tag.endswith("FeatureType"):
            name = title = default_crs = None
            for child in elem:
                if child.tag.endswith("Name"):
                    name = child.text
                elif child.tag.endswith("Title"):
                    title = child.text
                elif child.tag.endswith("DefaultCRS") or child.tag.endswith("DefaultSRS"):
                    default_crs = child.text
            if name:
                feature_types.append(
                    {"name": name, "title": title, "default_crs": default_crs}
                )

    return {
        "kind": "wfs",
        "source": url,
        "discovered_at": now(),
        "content_type": headers.get("Content-Type"),
        "count": len(feature_types),
        "feature_types": feature_types,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    ckan = sub.add_parser("ckan")
    ckan.add_argument("url")
    ckan.add_argument("--query", default="")
    ckan.add_argument("--rows", type=int, default=100)

    arcgis = sub.add_parser("arcgis")
    arcgis.add_argument("url")

    wfs = sub.add_parser("wfs")
    wfs.add_argument("url")

    args = parser.parse_args()

    if args.command == "ckan":
        result = discover_ckan(args.url, args.query, args.rows)
    elif args.command == "arcgis":
        result = discover_arcgis(args.url)
    elif args.command == "wfs":
        result = discover_wfs(args.url)
    else:
        parser.error("unsupported command")

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
