#!/usr/bin/env python3
"""Validate normalized public-event NDJSON without external dependencies."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EVENT_TYPES = {
    "PROJECT_PLANNED","PROCUREMENT_PUBLISHED","CONTRACTED","LICENSED",
    "APPROVED","PROCESS_OPENED","PROCESS_MOVEMENT","LEGAL_ACT_PUBLISHED",
    "WORK_STARTED","WORK_PAUSED","WORK_RESUMED","WORK_COMPLETED",
    "CANCELLED","OTHER",
}
MATCH_METHODS = {
    "OFFICIAL_GEOMETRY","OFFICIAL_PROPERTY_IDENTIFIER","OFFICIAL_ADDRESS",
    "SPATIAL_PROXIMITY","DOCUMENT_REFERENCE","TEXT_ONLY","UNRESOLVED",
}
CONFIDENCE = {"CONFIRMED","SUPPORTED","INDICATIVE","UNKNOWN","CONFLICTING"}
ACCESS = {
    "OPEN_REUSABLE","PUBLIC_QUERY_ONLY","AUTHENTICATED_PUBLIC",
    "RESTRICTED_PERSONAL","PAID_ON_DEMAND","USER_PRIVATE","DERIVED",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    errors = []
    seen = set()
    count = 0

    with args.path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            count += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc}")
                continue

            prefix = f"line {line_number}"
            required = [
                "schema_version","event_id","event_type","source_id",
                "source_event_id","authority","access_class","captured_at",
                "match","provenance",
            ]
            missing = [key for key in required if not event.get(key)]
            if missing:
                errors.append(f"{prefix}: missing {', '.join(missing)}")

            event_id = event.get("event_id")
            if event_id in seen:
                errors.append(f"{prefix}: duplicate event_id={event_id}")
            seen.add(event_id)

            if event.get("schema_version") != "0.1.0":
                errors.append(f"{prefix}: unsupported schema_version")
            if event.get("event_type") not in EVENT_TYPES:
                errors.append(f"{prefix}: invalid event_type")
            if event.get("access_class") not in ACCESS:
                errors.append(f"{prefix}: invalid access_class")

            match = event.get("match")
            if not isinstance(match, dict):
                errors.append(f"{prefix}: match must be object")
            else:
                method = match.get("method")
                confidence = match.get("confidence")
                if method not in MATCH_METHODS:
                    errors.append(f"{prefix}: invalid match.method")
                if confidence not in CONFIDENCE:
                    errors.append(f"{prefix}: invalid match.confidence")
                if (
                    method in {"TEXT_ONLY","UNRESOLVED"}
                    and confidence == "CONFIRMED"
                ):
                    errors.append(
                        f"{prefix}: text/unresolved match cannot be CONFIRMED"
                    )
                if (
                    event.get("source_id") == "br-pncp-open-api"
                    and method not in {"UNRESOLVED","DOCUMENT_REFERENCE"}
                ):
                    errors.append(
                        f"{prefix}: PNCP publication cannot establish parcel "
                        "location without a separate official relationship"
                    )

            municipality = event.get("municipality_ibge")
            if municipality is not None and not re.fullmatch(
                r"\d{7}", str(municipality)
            ):
                errors.append(f"{prefix}: invalid municipality_ibge")

            provenance = event.get("provenance")
            if not isinstance(provenance, dict) or not provenance.get("source_url"):
                errors.append(f"{prefix}: provenance.source_url required")
            elif provenance.get("snapshot_sha256") not in {None, ""}:
                if not SHA256.fullmatch(provenance["snapshot_sha256"]):
                    errors.append(f"{prefix}: invalid snapshot_sha256")

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(
        json.dumps(
            {"ok": not errors, "events": count, "errors": len(errors)},
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
