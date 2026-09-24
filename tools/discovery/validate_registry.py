#!/usr/bin/env python3
"""Validate LoteDiretor source registry files without performing network requests."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ACCESS_CLASSES = {
    "OPEN_REUSABLE",
    "PUBLIC_QUERY_ONLY",
    "AUTHENTICATED_PUBLIC",
    "RESTRICTED_PERSONAL",
    "PAID_ON_DEMAND",
    "USER_PRIVATE",
    "DERIVED",
}
REQUIRED_SOURCE_FIELDS = {
    "id", "authority", "scope", "domain", "source_type",
    "access_class", "verification_status",
}
URL_KEY_RE = re.compile(
    r"(?:^|_)(?:url|uri)$|^base_url$|^catalog_url$|^service_url$|"
    r"^metadata_url$|^resource_url$|^portal_url$|^wfs_url$|^wms_url$|"
    r"^geonode_url$|^developer_url$|^csw_url$|^urn_resolver$|^image_url$|"
    r"^arcgis_url$"
)


def valid_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    p = urlparse(value)
    return p.scheme in {"http", "https"} and bool(p.netloc)


def validate_source_registry(path: Path) -> tuple[list[str], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data.get("sources"), list):
        return [f"{path}: top-level 'sources' must be a list"], warnings

    seen: set[str] = set()
    for i, source in enumerate(data["sources"]):
        sid = source.get("id", "?")
        prefix = f"{path}: sources[{i}]({sid})"

        missing = sorted(
            field for field in REQUIRED_SOURCE_FIELDS
            if source.get(field) in (None, "", [])
        )
        if missing:
            errors.append(f"{prefix}: missing required fields: {', '.join(missing)}")

        if sid in seen:
            errors.append(f"{prefix}: duplicate source id")
        seen.add(sid)

        if source.get("access_class") not in ACCESS_CLASSES:
            errors.append(
                f"{prefix}: invalid access_class={source.get('access_class')!r}"
            )

        if not isinstance(source.get("domain"), list):
            errors.append(f"{prefix}: domain must be an array")

        url_fields = []
        for key, value in source.items():
            if URL_KEY_RE.search(key):
                url_fields.append(key)
                if not valid_http_url(value):
                    errors.append(f"{prefix}: invalid HTTP(S) URL in {key}: {value!r}")

        if not url_fields:
            warnings.append(f"{prefix}: no URL-like field found")

        if source.get("access_class") == "OPEN_REUSABLE" and not (
            source.get("license")
            or "license" in str(source.get("verification_status", "")).lower()
            or "open" in str(source.get("verification_status", "")).lower()
            or source.get("notes")
        ):
            warnings.append(
                f"{prefix}: OPEN_REUSABLE without explicit license/notes; review"
            )

        if "municipality_ibge" in source:
            code = str(source["municipality_ibge"])
            if not re.fullmatch(r"\d{7}", code):
                errors.append(f"{prefix}: municipality_ibge must have 7 digits")

    return errors, warnings


def validate_public_directories(path: Path) -> tuple[list[str], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for i, source in enumerate(data.get("sources", [])):
        sid = source.get("id", "?")
        prefix = f"{path}: sources[{i}]({sid})"
        if sid in seen:
            errors.append(f"{prefix}: duplicate id")
        seen.add(sid)
        if not valid_http_url(source.get("root")):
            errors.append(f"{prefix}: invalid root URL")
        for url in source.get("useful_roots", []):
            if not valid_http_url(url):
                errors.append(f"{prefix}: invalid useful_root URL {url!r}")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", default=".",
        help="Repository root (default: current directory)"
    )
    args = parser.parse_args()
    root = Path(args.root)

    checks = [
        (root / "data/source-registry/bootstrap.json", validate_source_registry),
        (root / "data/source-registry/public-directories.json", validate_public_directories),
    ]

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for path, validator in checks:
        if not path.exists():
            all_errors.append(f"missing registry file: {path}")
            continue
        errors, warnings = validator(path)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    for warning in all_warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in all_errors:
        print(f"ERROR: {error}", file=sys.stderr)

    print(json.dumps({
        "ok": not all_errors,
        "errors": len(all_errors),
        "warnings": len(all_warnings),
    }, ensure_ascii=False))

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
