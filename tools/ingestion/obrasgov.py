#!/usr/bin/env python3
"""Read-only client for the current ObrasGov Open Data API."""
from __future__ import annotations

import argparse
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from public_api import fetch_json, sha256, utc_now, write_json

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/public-events/obrasgov-api.json"
OUT = ROOT / "data/snapshots"
ALLOWED_HOSTS = {"api-publica.obrasgov.gestao.gov.br"}
MAX_PAGES = 20


def parse_filter(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("filters must be NAME=VALUE")
    name, raw = value.split("=", 1)
    if not name or raw == "":
        raise argparse.ArgumentTypeError("filters must be NAME=VALUE")
    return name, raw


def build_url(base: str, endpoint: str, query: dict[str, object]) -> str:
    return (
        base.rstrip("/")
        + "/"
        + endpoint.lstrip("/")
        + "?"
        + urllib.parse.urlencode(query)
    )


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    resources = config["resources"]

    parser = argparse.ArgumentParser()
    parser.add_argument("resource", choices=sorted(resources))
    parser.add_argument("--filter", action="append", default=[], type=parse_filter)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    if args.page < 1:
        raise SystemExit("--page must be >= 1")
    if not 1 <= args.pages <= MAX_PAGES:
        raise SystemExit(f"--pages must be between 1 and {MAX_PAGES}")
    if not 1 <= args.page_size <= config["pagination"]["max_page_size"]:
        raise SystemExit(
            "--page-size must be between 1 and "
            f"{config['pagination']['max_page_size']}"
        )

    metadata = resources[args.resource]
    allowed_filters = set(metadata.get("filters", []))
    filters = dict(args.filter)
    unknown = sorted(set(filters) - allowed_filters)
    if unknown:
        raise SystemExit(
            "unknown filter(s): "
            + ", ".join(unknown)
            + "; allowed: "
            + ", ".join(sorted(allowed_filters))
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.out / f"obrasgov-{args.resource}" / stamp
    folder.mkdir(parents=True, exist_ok=False)

    if metadata.get("paginated", True) is False:
        url = config["base_url"].rstrip("/") + "/" + metadata["endpoint"]
        result = fetch_json(
            url,
            allowed_hosts=ALLOWED_HOSTS,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        raw = folder / "raw.json"
        raw.write_bytes(result["body"])
        manifest = {
            "schema_version": "0.1.0",
            "source_id": config["source_id"],
            "resource": args.resource,
            "captured_at": utc_now(),
            "requested_url": url,
            "final_url": result["final_url"],
            "http_status": result["status"],
            "sha256": sha256(result["body"]),
            "raw_file": raw.name,
        }
        write_json(folder / "manifest.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    pages = []
    total_pages = None
    total_items = None

    for offset in range(args.pages):
        page = args.page + offset
        query: dict[str, object] = dict(filters)
        query[config["pagination"]["page_param"]] = page
        query[config["pagination"]["page_size_param"]] = args.page_size
        url = build_url(config["base_url"], metadata["endpoint"], query)

        result = fetch_json(
            url,
            allowed_hosts=ALLOWED_HOSTS,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        payload = result["json"]
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SystemExit("unexpected ObrasGov response: missing data array")

        returned_page = payload.get("page_number")
        if returned_page is not None and returned_page != page:
            raise SystemExit(
                f"ObrasGov returned page_number={returned_page}, expected {page}"
            )

        if total_pages is None:
            total_pages = payload.get("total_pages")
            total_items = payload.get("total_items")

        filename = f"page-{page:05d}.json"
        (folder / filename).write_bytes(result["body"])
        pages.append(
            {
                "page": page,
                "records": len(payload["data"]),
                "requested_url": url,
                "final_url": result["final_url"],
                "http_status": result["status"],
                "sha256": sha256(result["body"]),
                "raw_file": filename,
            }
        )

        if not payload["data"]:
            break
        if isinstance(total_pages, int) and page >= total_pages:
            break

    update_url = config["base_url"].rstrip("/") + "/" + resources["last_update"]["endpoint"]
    update = fetch_json(
        update_url,
        allowed_hosts=ALLOWED_HOSTS,
        timeout=args.timeout,
        max_bytes=min(args.max_bytes, 1024 * 1024),
    )
    update_value = (
        update["json"].get("data_ultima_atualizacao")
        if isinstance(update["json"], dict)
        else None
    )

    manifest = {
        "schema_version": "0.1.0",
        "source_id": config["source_id"],
        "resource": args.resource,
        "filters": filters,
        "first_page": args.page,
        "requested_pages": args.pages,
        "page_size": args.page_size,
        "captured_at": utc_now(),
        "source_updated_at": update_value,
        "total_pages_reported": total_pages,
        "total_items_reported": total_items,
        "pages": pages,
    }
    write_json(folder / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
