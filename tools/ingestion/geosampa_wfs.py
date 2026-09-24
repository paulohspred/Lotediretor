#!/usr/bin/env python3
"""Bounded GeoSampa WFS materializer for approved, allowlisted layers.

Initial production use is intentionally narrow: the public fiscal parcel layer
(`geoportal:lote_cidadao`) partitioned by fiscal sector. The request sends an
explicit `propertyName` allowlist so new upstream fields do not silently enter
LoteDiretor snapshots.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from public_api import fetch_json, sha256, utc_now, write_json

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/connectors/geosampa-layers.json"
OUT = ROOT / "data/snapshots"
ALLOWED_HOSTS = {"wfs.geosampa.prefeitura.sp.gov.br"}


def validate_sector(value: str, layer: dict) -> str:
    rule = layer["partition"]["valid_values"]
    if not re.fullmatch(rf"\d{{{rule['width']}}}", value):
        raise argparse.ArgumentTypeError(
            f"sector must have exactly {rule['width']} digits"
        )
    number = int(value)
    if not rule["minimum"] <= number <= rule["maximum"]:
        raise argparse.ArgumentTypeError(
            f"sector must be between {rule['minimum']:03d} and "
            f"{rule['maximum']:03d}"
        )
    if value in set(rule.get("excluded", [])):
        raise argparse.ArgumentTypeError(f"sector {value} does not exist")
    return value


def build_url(config: dict, layer: dict, *, sector: str, start: int, count: int) -> str:
    fields = [layer["geometry_property"], *layer["field_allowlist"]]
    query = {
        "service": config["service"],
        "version": config["version"],
        "request": "GetFeature",
        "typeNames": layer["type_name"],
        "cql_filter": f"{layer['partition']['field']}='{sector}'",
        "startIndex": start,
        "count": count,
        "propertyName": ",".join(fields),
        "outputFormat": layer["materialization"]["output_format"],
    }
    return config["endpoint"] + "?" + urllib.parse.urlencode(query)


def validate_feature_collection(
    payload: object,
    *,
    layer: dict,
    sector: str,
    expected_start: int,
) -> tuple[list[dict], int | None]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("GeoSampa response is not a GeoJSON FeatureCollection")

    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoSampa response has no features array")

    allowed = set(layer["field_allowlist"])
    partition_field = layer["partition"]["field"]
    geometry_types = {
        layer["observed_geometry_type"],
        "Multi" + layer["observed_geometry_type"],
    }

    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"feature[{index}] is not a GeoJSON Feature")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"feature[{index}] properties must be an object")

        unexpected = set(properties) - allowed
        if unexpected:
            raise ValueError(
                "closed field allowlist rejected unexpected upstream field(s): "
                + ", ".join(sorted(unexpected))
            )

        if properties.get(partition_field) != sector:
            raise ValueError(
                f"feature[{index}] partition mismatch: "
                f"{properties.get(partition_field)!r} != {sector!r}"
            )

        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError(f"feature[{index}] has no geometry")
        if geometry.get("type") not in geometry_types:
            raise ValueError(
                f"feature[{index}] unexpected geometry type "
                f"{geometry.get('type')!r}"
            )

    reported_returned = payload.get("numberReturned")
    if isinstance(reported_returned, int) and reported_returned != len(features):
        raise ValueError(
            f"numberReturned={reported_returned} but features={len(features)}"
        )

    matched = payload.get("numberMatched")
    if not isinstance(matched, int):
        legacy = payload.get("totalFeatures")
        matched = legacy if isinstance(legacy, int) else None

    return features, matched


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    layer = config["layers"]["lote_cidadao"]

    parser = argparse.ArgumentParser()
    parser.add_argument("--sector", required=True)
    parser.add_argument(
        "--page-size",
        type=int,
        default=layer["materialization"]["default_page_size"],
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=layer["materialization"]["max_pages_per_run"],
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Return success even when the configured page cap truncates a sector.",
    )
    args = parser.parse_args()

    try:
        sector = validate_sector(args.sector, layer)
    except argparse.ArgumentTypeError as exc:
        raise SystemExit(str(exc)) from exc

    max_page_size = layer["materialization"]["max_page_size"]
    if not 1 <= args.page_size <= max_page_size:
        raise SystemExit(
            f"--page-size must be between 1 and {max_page_size}"
        )
    hard_page_cap = layer["materialization"]["max_pages_per_run"]
    if not 1 <= args.max_pages <= hard_page_cap:
        raise SystemExit(
            f"--max-pages must be between 1 and {hard_page_cap}"
        )
    if args.max_bytes <= 0:
        raise SystemExit("--max-bytes must be positive")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.out / "sp-geosampa-lote" / stamp / f"sector-{sector}"
    folder.mkdir(parents=True, exist_ok=False)

    pages: list[dict] = []
    total_matched: int | None = None
    total_returned = 0

    for page_index in range(args.max_pages):
        start = page_index * args.page_size
        url = build_url(
            config,
            layer,
            sector=sector,
            start=start,
            count=args.page_size,
        )
        result = fetch_json(
            url,
            allowed_hosts=ALLOWED_HOSTS,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        features, matched = validate_feature_collection(
            result["json"],
            layer=layer,
            sector=sector,
            expected_start=start,
        )

        if total_matched is None:
            total_matched = matched
        elif matched is not None and total_matched != matched:
            raise SystemExit(
                "numberMatched changed during one sector snapshot; "
                "rerun to obtain a consistent source view"
            )

        filename = f"page-{page_index + 1:05d}.geojson"
        (folder / filename).write_bytes(result["body"])
        total_returned += len(features)

        pages.append(
            {
                "page": page_index + 1,
                "start_index": start,
                "records": len(features),
                "requested_url": url,
                "final_url": result["final_url"],
                "http_status": result["status"],
                "sha256": sha256(result["body"]),
                "raw_file": filename,
            }
        )

        if not features:
            break
        if total_matched is not None and total_returned >= total_matched:
            break
        if len(features) < args.page_size:
            break

    complete = (
        total_matched is not None
        and total_returned >= total_matched
    )
    if total_matched == 0:
        complete = True

    manifest = {
        "schema_version": "0.1.0",
        "connector_id": config["connector_id"],
        "source_id": config["source_id"],
        "layer": layer["type_name"],
        "municipality_ibge": config["municipality_ibge"],
        "partition": {
            "field": layer["partition"]["field"],
            "value": sector,
        },
        "source_crs": layer["observed_crs"],
        "license": config["license"],
        "captured_at": utc_now(),
        "page_size": args.page_size,
        "max_pages": args.max_pages,
        "number_matched": total_matched,
        "number_returned": total_returned,
        "complete": complete,
        "field_allowlist": layer["field_allowlist"],
        "pages": pages,
        "notes": (
            "Requests use a closed WFS propertyName allowlist; geometry is "
            "returned separately by GeoJSON. No person-centric fields are "
            "approved for this layer."
        ),
    }
    write_json(folder / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    if not complete and not args.allow_incomplete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
