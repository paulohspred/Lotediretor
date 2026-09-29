#!/usr/bin/env python3
"""Publish data/source-registry/bootstrap.json into ld_catalog.source.

The JSON registry stays the reviewed source of truth (it is validated in CI);
this loader makes it queryable so the API can answer "which sources cover
municipality X" (Blueprint §7, GET /municipalities/{ibge}/coverage).

Idempotent upsert. Sources removed from the JSON are retired (retired_at set),
never deleted, so historical snapshots keep their foreign keys.

Usage:
    LOTEDIRETOR_DB_DSN=... python3 tools/loaders/load_source_registry.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "discovery"))
from registry_coverage import derive_coverage  # noqa: E402

REGISTRY = ROOT / "data" / "source-registry" / "bootstrap.json"
URL_KEYS = ("base_url", "service_url", "portal_url", "catalog_url", "url")

UPSERT_SQL = r"""
\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE incoming (doc jsonb) ON COMMIT DROP;
\copy incoming (doc) FROM pstdin WITH (FORMAT text)

INSERT INTO ld_catalog.source AS s (
    source_id, authority, scope, source_type, access_class, license,
    verification_status, canonical_url, metadata, coverage_level, uf,
    municipality_ibge, domains, retired_at
)
SELECT
    doc->>'source_id', doc->>'authority', doc->>'scope', doc->>'source_type',
    doc->>'access_class', doc->>'license', doc->>'verification_status',
    doc->>'canonical_url', doc->'metadata', doc->>'coverage_level',
    doc->>'uf', doc->>'municipality_ibge',
    ARRAY(SELECT jsonb_array_elements_text(doc->'domains')), NULL
FROM incoming
ON CONFLICT (source_id) DO UPDATE SET
    authority = EXCLUDED.authority,
    scope = EXCLUDED.scope,
    source_type = EXCLUDED.source_type,
    access_class = EXCLUDED.access_class,
    license = EXCLUDED.license,
    verification_status = EXCLUDED.verification_status,
    canonical_url = EXCLUDED.canonical_url,
    metadata = EXCLUDED.metadata,
    coverage_level = EXCLUDED.coverage_level,
    uf = EXCLUDED.uf,
    municipality_ibge = EXCLUDED.municipality_ibge,
    domains = EXCLUDED.domains,
    retired_at = NULL;

-- Registry-managed sources that disappeared from the JSON are retired.
UPDATE ld_catalog.source
SET retired_at = now()
WHERE retired_at IS NULL
  AND metadata->>'managed_by' = 'bootstrap.json'
  AND source_id NOT IN (SELECT doc->>'source_id' FROM incoming);
COMMIT;
SELECT coverage_level, count(*) FROM ld_catalog.source
WHERE retired_at IS NULL GROUP BY 1 ORDER BY 1;
"""


def rows(registry: dict) -> list[dict]:
    out = []
    for source in registry["sources"]:
        coverage = derive_coverage(source)
        url = next((source[k] for k in URL_KEYS if source.get(k)), None)
        metadata = {k: v for k, v in source.items() if k not in {"id"}}
        metadata["managed_by"] = "bootstrap.json"
        out.append(
            {
                "source_id": source["id"],
                "authority": source["authority"],
                "scope": str(source["scope"]),
                "source_type": source["source_type"],
                "access_class": source["access_class"],
                "license": source.get("license"),
                "verification_status": source["verification_status"],
                "canonical_url": url,
                "metadata": metadata,
                **coverage,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or LOTEDIRETOR_DB_DSN is required")

    data = rows(json.loads(args.registry.read_text(encoding="utf-8")))
    # COPY text format: one JSON document per line; escape backslashes.
    payload = "".join(
        json.dumps(row, ensure_ascii=False).replace("\\", "\\\\") + "\n"
        for row in data
    )
    script = UPSERT_SQL
    # psql reads the script from -c/-f and the COPY data from stdin.
    script_path = Path(os.environ.get("TMPDIR", "/tmp")) / "ld_registry_upsert.sql"
    script_path.write_text(script, encoding="utf-8")
    try:
        result = subprocess.run(
            ["psql", args.dsn, "-X", "-q", "-f", str(script_path)],
            input=payload,
            text=True,
            capture_output=True,
        )
    finally:
        script_path.unlink(missing_ok=True)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    print(f"published {len(data)} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
