#!/usr/bin/env python3
"""Bounded Recife CKAN DataStore materializer with closed field projections."""
from __future__ import annotations

import argparse
import json
import math
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from public_api import fetch_json, sha256, utc_now, write_json

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/connectors/recife-datasets.json"
OUT = ROOT / "data/snapshots"
ALLOWED_HOSTS = {"dados.recife.pe.gov.br"}


def build_url(config: dict, dataset: dict, *, offset: int, limit: int) -> str:
    query = {
        "resource_id": dataset["resource_id"],
        "limit": limit,
        "offset": offset,
        "fields": ",".join(dataset["field_allowlist"]),
    }
    return (
        config["api_base"].rstrip("/")
        + "/datastore_search?"
        + urllib.parse.urlencode(query)
    )


def validate_payload(payload: object, dataset: dict) -> tuple[list[dict], int]:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("CKAN response is not a successful action result")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("CKAN response has no result object")

    total = result.get("total")
    if not isinstance(total, int) or total < 0:
        raise ValueError("CKAN result.total must be a non-negative integer")

    records = result.get("records")
    if not isinstance(records, list):
        raise ValueError("CKAN result.records must be an array")

    allowed = set(dataset["field_allowlist"])
    returned_fields = [
        field.get("id")
        for field in result.get("fields", [])
        if isinstance(field, dict)
    ]
    if set(returned_fields) != allowed:
        missing = sorted(allowed - set(returned_fields))
        extra = sorted(set(returned_fields) - allowed)
        raise ValueError(
            f"CKAN field projection mismatch; missing={missing}, extra={extra}"
        )

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record[{index}] must be an object")
        unexpected = set(record) - allowed
        missing = allowed - set(record)
        if unexpected or missing:
            raise ValueError(
                f"record[{index}] projection mismatch; "
                f"missing={sorted(missing)}, extra={sorted(unexpected)}"
            )

    return records, total


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=sorted(config["datasets"]))
    parser.add_argument("--page-size", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Return success when the page cap intentionally truncates a dataset.",
    )
    args = parser.parse_args()

    dataset = config["datasets"][args.dataset]
    page_size = args.page_size or dataset["page_size"]
    max_pages = args.max_pages or dataset["max_pages"]

    if not 1 <= page_size <= dataset["max_page_size"]:
        raise SystemExit(
            f"--page-size must be between 1 and {dataset['max_page_size']}"
        )
    if not 1 <= max_pages <= dataset["max_pages"]:
        raise SystemExit(
            f"--max-pages must be between 1 and {dataset['max_pages']}"
        )
    if args.max_bytes <= 0:
        raise SystemExit("--max-bytes must be positive")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.out / f"recife-{args.dataset}" / stamp
    folder.mkdir(parents=True, exist_ok=False)

    pages: list[dict] = []
    total_reported: int | None = None
    total_returned = 0

    offset = 0
    for page_index in range(max_pages):
        url = build_url(config, dataset, offset=offset, limit=page_size)
        response = fetch_json(
            url,
            allowed_hosts=ALLOWED_HOSTS,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        records, total = validate_payload(response["json"], dataset)

        if total_reported is None:
            total_reported = total
        elif total_reported != total:
            raise SystemExit(
                "CKAN total changed during one snapshot; rerun for a "
                "temporally consistent materialization"
            )

        filename = f"page-{page_index + 1:05d}.json"
        (folder / filename).write_bytes(response["body"])
        total_returned += len(records)

        pages.append(
            {
                "page": page_index + 1,
                "offset": offset,
                "records": len(records),
                "requested_url": url,
                "final_url": response["final_url"],
                "http_status": response["status"],
                "sha256": sha256(response["body"]),
                "raw_file": filename,
            }
        )

        if not records:
            break
        if total_returned >= total:
            break

        # Recife currently caps DataStore responses at 500 rows. Advance by
        # what was actually returned so a server-side cap cannot skip rows.
        offset += len(records)

    complete = (
        total_reported is not None
        and total_returned >= total_reported
    )
    if total_reported == 0:
        complete = True

    manifest = {
        "schema_version": "0.1.0",
        "connector_id": "recife-ckan",
        "dataset_key": args.dataset,
        "dataset_slug": dataset["dataset_slug"],
        "resource_id": dataset["resource_id"],
        "resource_name": dataset["resource_name"],
        "source_id": dataset["source_id"],
        "record_kind": dataset["record_kind"],
        "municipality_ibge": config["municipality_ibge"],
        "license": config["license"],
        "captured_at": utc_now(),
        "page_size": page_size,
        "max_pages": max_pages,
        "total_reported": total_reported,
        "number_returned": total_returned,
        "complete": complete,
        "field_allowlist": dataset["field_allowlist"],
        "excluded_fields": dataset["excluded_fields"],
        "pages": pages,
        "notes": dataset["notes"],
    }
    write_json(folder / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    if not complete and not args.allow_incomplete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
