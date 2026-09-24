#!/usr/bin/env python3
"""Discover metadata from public open-data/geospatial interfaces.

No authentication bypass, CAPTCHA/paywall circumvention, Google Maps/Street
View scraping, or cross-origin directory crawling. Directory mode records
links only; it does not download target files.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser

USER_AGENT = "LoteDiretor-SourceDiscovery/0.3 (+https://github.com/paulohspred/Lotediretor)"

SENSITIVE_FIELD_TOKENS = {
    "cpf", "cnpj", "proprietario", "proprietário", "owner", "titular",
    "requerente", "documento", "doc_requerente", "nome_pessoa", "nom_pessoa",
    "telefone", "celular", "email", "e_mail", "rg", "cnh", "passaporte",
}


def privacy_flags(fields: list[dict]) -> dict:
    flagged = []
    for field in fields or []:
        name = str(field.get("name") or "").lower()
        alias = str(field.get("alias") or "").lower()
        haystack = f"{name} {alias}"
        hits = sorted(token for token in SENSITIVE_FIELD_TOKENS if token in haystack)
        if hits:
            flagged.append({
                "name": field.get("name"),
                "alias": field.get("alias"),
                "matched_tokens": hits,
            })
    return {
        "privacy_review_required": bool(flagged),
        "potentially_sensitive_fields": flagged,
        "warning": (
            "Heuristic only. Public endpoint exposure does not authorize republication; "
            "review LGPD, purpose, source terms and minimization before ingestion."
            if flagged else None
        ),
    }


def validate_http_url(url: str) -> urllib.parse.ParseResult:
    p = urllib.parse.urlparse(url)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValueError("only absolute http/https URLs are supported")
    return p


def fetch(url: str, timeout: int = 30) -> tuple[bytes, dict[str, str]]:
    validate_http_url(url)
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
        datasets.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "title": item.get("title"),
            "organization": (item.get("organization") or {}).get("title"),
            "license_id": item.get("license_id"),
            "license_title": item.get("license_title"),
            "metadata_modified": item.get("metadata_modified"),
            "tags": [tag.get("name") for tag in item.get("tags", [])],
            "resources": [{
                "id": r.get("id"),
                "name": r.get("name"),
                "format": r.get("format"),
                "url": r.get("url"),
                "last_modified": r.get("last_modified"),
            } for r in item.get("resources", [])],
        })
    return {
        "kind": "ckan", "source": base_url, "query": query,
        "discovered_at": now(), "count": len(datasets), "datasets": datasets,
    }


def arcgis_json_url(url: str) -> str:
    p = validate_http_url(url)
    q = urllib.parse.parse_qs(p.query)
    q["f"] = ["pjson"]
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q, doseq=True)))


def discover_arcgis(url: str) -> dict:
    payload = fetch_json(arcgis_json_url(url))
    out = {
        "kind": "arcgis", "source": url, "discovered_at": now(),
        "currentVersion": payload.get("currentVersion"),
        "folders": payload.get("folders", []),
        "services": payload.get("services", []),
    }
    if "layers" in payload:
        out.update({
            "layers": payload.get("layers", []),
            "tables": payload.get("tables", []),
            "serviceDescription": payload.get("serviceDescription"),
            "spatialReference": payload.get("spatialReference"),
            "copyrightText": payload.get("copyrightText"),
            "supportedQueryFormats": payload.get("supportedQueryFormats"),
        })
    if "fields" in payload:
        fields = payload.get("fields", [])
        out["fields"] = fields
        out.update(privacy_flags(fields))
    return out


def discover_arcgis_tree(url: str, max_depth: int, max_nodes: int) -> dict:
    root = url.rstrip("/")
    queue = deque([(root, 0)])
    visited: set[str] = set()
    nodes = []
    while queue and len(nodes) < max_nodes:
        current, depth = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        try:
            payload = fetch_json(arcgis_json_url(current))
        except Exception as exc:
            nodes.append({"url": current, "depth": depth, "error": f"{type(exc).__name__}: {exc}"})
            continue
        nodes.append({
            "url": current, "depth": depth,
            "currentVersion": payload.get("currentVersion"),
            "folders": payload.get("folders", []),
            "services": payload.get("services", []),
        })
        if depth < max_depth:
            for folder in payload.get("folders", []):
                if folder not in {"Utilities", "System"}:
                    queue.append((f"{current}/{urllib.parse.quote(folder, safe='')}", depth + 1))
    return {
        "kind": "arcgis-tree", "source": url, "discovered_at": now(),
        "max_depth": max_depth, "max_nodes": max_nodes,
        "truncated": bool(queue), "count": len(nodes), "nodes": nodes,
    }


def discover_wfs(url: str) -> dict:
    params = urllib.parse.urlencode({"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"})
    body, headers = fetch(f"{url}{'&' if '?' in url else '?'}{params}")
    root = ET.fromstring(body)
    features = []
    for elem in root.iter():
        if not elem.tag.endswith("FeatureType"):
            continue
        item = {"name": None, "title": None, "default_crs": None}
        for child in elem:
            if child.tag.endswith("Name"):
                item["name"] = child.text
            elif child.tag.endswith("Title"):
                item["title"] = child.text
            elif child.tag.endswith("DefaultCRS") or child.tag.endswith("DefaultSRS"):
                item["default_crs"] = child.text
        if item["name"]:
            features.append(item)
    return {
        "kind": "wfs", "source": url, "discovered_at": now(),
        "content_type": headers.get("Content-Type"),
        "count": len(features), "feature_types": features,
    }


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str | None]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self._href, self._text = href, []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip() or None))
            self._href, self._text = None, []


def same_origin(a: urllib.parse.ParseResult, b: urllib.parse.ParseResult) -> bool:
    return (a.scheme.lower(), a.netloc.lower()) == (b.scheme.lower(), b.netloc.lower())


def discover_directory(url: str, max_depth: int, max_items: int) -> dict:
    root = validate_http_url(url)
    start = urllib.parse.urlunparse(root)
    queue = deque([(start, 0)])
    visited: set[str] = set()
    pages, item_count = [], 0
    while queue and item_count < max_items:
        current, depth = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        try:
            body, headers = fetch(current)
            text = body.decode("utf-8", errors="replace")
        except Exception as exc:
            pages.append({"url": current, "depth": depth, "error": f"{type(exc).__name__}: {exc}"})
            continue
        parser = LinkParser()
        parser.feed(text)
        entries = []
        for href, label in parser.links:
            absolute = urllib.parse.urljoin(current, href)
            p = urllib.parse.urlparse(absolute)._replace(fragment="")
            absolute = urllib.parse.urlunparse(p)
            if not same_origin(root, p) or href in {"../", "./", "/"}:
                continue
            is_dir = p.path.endswith("/")
            entries.append({"name": label, "href": href, "url": absolute, "directory": is_dir})
            item_count += 1
            if is_dir and depth < max_depth and item_count < max_items and absolute not in visited:
                queue.append((absolute, depth + 1))
            if item_count >= max_items:
                break
        pages.append({
            "url": current, "depth": depth,
            "content_type": headers.get("Content-Type"), "entries": entries,
        })
    return {
        "kind": "directory", "source": url, "discovered_at": now(),
        "max_depth": max_depth, "max_items": max_items,
        "truncated": bool(queue) or item_count >= max_items,
        "page_count": len(pages), "item_count": item_count, "pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ckan")
    p.add_argument("url"); p.add_argument("--query", default=""); p.add_argument("--rows", type=int, default=100)

    p = sub.add_parser("arcgis")
    p.add_argument("url")

    p = sub.add_parser("arcgis-tree")
    p.add_argument("url"); p.add_argument("--max-depth", type=int, default=2); p.add_argument("--max-nodes", type=int, default=200)

    p = sub.add_parser("wfs")
    p.add_argument("url")

    p = sub.add_parser("directory")
    p.add_argument("url"); p.add_argument("--max-depth", type=int, default=1); p.add_argument("--max-items", type=int, default=1000)

    args = parser.parse_args()
    if args.command == "ckan":
        result = discover_ckan(args.url, args.query, args.rows)
    elif args.command == "arcgis":
        result = discover_arcgis(args.url)
    elif args.command == "arcgis-tree":
        result = discover_arcgis_tree(args.url, args.max_depth, args.max_nodes)
    elif args.command == "wfs":
        result = discover_wfs(args.url)
    elif args.command == "directory":
        result = discover_directory(args.url, args.max_depth, args.max_items)
    else:
        parser.error("unsupported command")

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
