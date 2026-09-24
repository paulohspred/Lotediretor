#!/usr/bin/env python3
"""Read-only snapshot helper for approved public LoteDiretor sources.

It captures raw metadata responses with timestamp, headers, SHA-256 and a
manifest. It does not bypass authentication, follow redirects to private
addresses, or infer permission from technical reachability.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT = "LoteDiretor-Ingestion/0.2 (+https://github.com/paulohspred/Lotediretor)"
CONFIG = Path("data/connectors/priority.json")
REGISTRY = Path("data/source-registry/bootstrap.json")
OUT = Path("data/snapshots")
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_public_url(url: str) -> None:
    p = urllib.parse.urlparse(url)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValueError("only public HTTP(S) URLs are supported")
    if p.username or p.password:
        raise ValueError("credentials in URLs are not supported")

    host = p.hostname
    if not host:
        raise ValueError("URL hostname is required")

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80))
        }
    except socket.gaierror as exc:
        raise ValueError(f"hostname resolution failed for {host}: {exc}") from exc

    if not addresses:
        raise ValueError(f"hostname resolved to no addresses: {host}")

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(f"refusing non-public destination {host} -> {address}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        validate_public_url(absolute)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def fetch(url: str, timeout: int = 60, max_bytes: int = DEFAULT_MAX_BYTES):
    validate_public_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(SafeRedirectHandler())
    with opener.open(req, timeout=timeout) as response:
        final_url = response.geturl()
        validate_public_url(final_url)
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"response exceeds max_bytes={max_bytes}")
        return (
            body,
            dict(response.headers.items()),
            final_url,
            getattr(response, "status", None),
        )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(p.query)
    q["f"] = ["pjson"]
    return urllib.parse.urlunparse(
        p._replace(query=urllib.parse.urlencode(q, doseq=True))
    )


def ogc_capabilities_url(url: str, service: str) -> str:
    p = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(p.query)
    q.update({"service": [service], "request": ["GetCapabilities"]})
    if service == "WFS":
        q["version"] = ["2.0.0"]
    elif service == "WMS":
        q["version"] = ["1.3.0"]
    return urllib.parse.urlunparse(
        p._replace(query=urllib.parse.urlencode(q, doseq=True))
    )


def ckan_url(base: str) -> str:
    return base.rstrip("/") + "/api/3/action/package_search?rows=1000"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def directory_index(url: str, body: bytes):
    root = urllib.parse.urlparse(url)
    parser = Links()
    parser.feed(body.decode("utf-8", errors="replace"))
    out = []
    for href in parser.links:
        absolute = urllib.parse.urljoin(url, href)
        p = urllib.parse.urlparse(absolute)
        if (p.scheme, p.netloc) != (root.scheme, root.netloc):
            continue
        if href in {"../", "./", "/"}:
            continue
        out.append(
            {
                "href": href,
                "url": absolute,
                "directory": p.path.endswith("/"),
            }
        )
    return out


def choose_url(item: dict) -> str:
    kind = item["kind"]
    url = item["url"]
    if kind == "arcgis_service":
        return json_url(url)
    if kind == "wfs_capabilities":
        return ogc_capabilities_url(url, "WFS")
    if kind == "wms_capabilities":
        return ogc_capabilities_url(url, "WMS")
    if kind == "ckan_catalog":
        return ckan_url(url)
    if kind in {
        "json_api",
        "frictionless_datapackage",
        "public_directory",
        "public_page",
    }:
        return url
    raise ValueError(f"unsupported connector kind: {kind}")


def load_source(source_id: str) -> dict:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    source = next(
        (item for item in registry.get("sources", []) if item.get("id") == source_id),
        None,
    )
    if not source:
        raise ValueError(f"source_id not found in registry: {source_id}")
    return source


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("connector_id")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = ap.parse_args()

    if args.max_bytes <= 0:
        raise SystemExit("--max-bytes must be positive")

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    item = next(
        (x for x in cfg["connectors"] if x["id"] == args.connector_id),
        None,
    )
    if not item:
        raise SystemExit("unknown connector")
    if not item.get("approved"):
        raise SystemExit("connector is not approved")

    source = load_source(item["source_id"])
    if source.get("access_class") in {"RESTRICTED_PERSONAL", "USER_PRIVATE"}:
        raise SystemExit("restricted/private sources cannot be snapshotted by this tool")

    target = choose_url(item)
    body, headers, final_url, status = fetch(
        target,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.out / item["id"] / stamp
    folder.mkdir(parents=True, exist_ok=False)

    ext = ".bin"
    ctype = (headers.get("Content-Type") or "").lower()
    if "json" in ctype or item["kind"] in {
        "arcgis_service",
        "ckan_catalog",
        "json_api",
        "frictionless_datapackage",
    }:
        ext = ".json"
    elif "xml" in ctype or item["kind"] in {
        "wfs_capabilities",
        "wms_capabilities",
    }:
        ext = ".xml"
    elif "html" in ctype or item["kind"] in {
        "public_directory",
        "public_page",
    }:
        ext = ".html"

    raw = folder / f"raw{ext}"
    raw.write_bytes(body)

    if item["kind"] == "public_directory":
        extra = {"entries": directory_index(final_url, body)}
        (folder / "index.json").write_text(
            json.dumps(extra, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "schema_version": "0.2.0",
        "connector_id": item["id"],
        "source_id": item["source_id"],
        "authority": source.get("authority"),
        "access_class": source.get("access_class"),
        "license": source.get("license"),
        "verification_status": source.get("verification_status"),
        "kind": item["kind"],
        "requested_url": target,
        "final_url": final_url,
        "http_status": status,
        "captured_at": now(),
        "content_type": headers.get("Content-Type"),
        "content_length": len(body),
        "sha256": sha256(body),
        "headers": {
            k: v
            for k, v in headers.items()
            if k.lower()
            in {
                "content-type",
                "content-length",
                "etag",
                "last-modified",
                "cache-control",
            }
        },
        "raw_file": raw.name,
        "mode": item.get("mode"),
        "notes": item.get("notes"),
    }
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
