#!/usr/bin/env bash
# Load the official IBGE municipal mesh (all ~5,570 municipalities) into
# ld_core.municipality, recording an immutable snapshot with its SHA-256.
#
# Usage:
#   LOTEDIRETOR_DB_DSN="postgresql:///lotediretor?host=/var/run/postgresql" \
#     tools/loaders/load_ibge_municipal_mesh.sh [EDITION]
#
#   EDITION defaults to 2024. Set MESH_FILE=/path/BR_Municipios_2024.zip to
#   load a file already downloaded (air-gapped hosts, reproducible reloads).
#
# Requires: curl, sha256sum, ogr2ogr (gdal-bin), psql.
# Source: IBGE — Malha Municipal Digital (Blueprint ref. R7).
set -euo pipefail

EDITION="${1:-2024}"
DSN="${LOTEDIRETOR_DB_DSN:?set LOTEDIRETOR_DB_DSN}"
CACHE_DIR="${CACHE_DIR:-/var/cache/lotediretor/ibge-mesh}"
MIN_COUNT="${MIN_COUNT:-5560}"
SOURCE_ID="br-ibge-malha-municipal"
URL="https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_${EDITION}/Brasil/BR_Municipios_${EDITION}.zip"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for bin in curl sha256sum ogr2ogr psql; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin" >&2; exit 1; }
done

mkdir -p "$CACHE_DIR"
FILE="${MESH_FILE:-$CACHE_DIR/BR_Municipios_${EDITION}.zip}"
if [[ ! -s "$FILE" ]]; then
  echo "downloading $URL"
  curl -fL --retry 3 --retry-delay 5 -o "$FILE.part" "$URL"
  mv "$FILE.part" "$FILE"
fi
SHA="$(sha256sum "$FILE" | cut -d' ' -f1)"
SIZE="$(stat -c %s "$FILE")"
echo "mesh file sha256=$SHA size=$SIZE"

# The shapefile inside the zip is named BR_Municipios_<EDITION>.shp.
LAYER_PATH="/vsizip/${FILE}/BR_Municipios_${EDITION}.shp"

PG_CONN="$(python3 - "$DSN" <<'PY'
import sys, urllib.parse as u
dsn = sys.argv[1]
if "://" not in dsn:
    print("PG:" + dsn); raise SystemExit
p = u.urlsplit(dsn); q = dict(u.parse_qsl(p.query))
parts = {"dbname": p.path.lstrip("/") or None, "host": q.get("host") or p.hostname,
         "port": q.get("port") or p.port, "user": q.get("user") or p.username,
         "password": p.password}
print("PG:" + " ".join(f"{k}={v}" for k, v in parts.items() if v))
PY
)"

psql "$DSN" -v ON_ERROR_STOP=1 -q -c "CREATE SCHEMA IF NOT EXISTS ld_stage"
ogr2ogr -f PostgreSQL "$PG_CONN" "$LAYER_PATH" \
  -nln ld_stage.ibge_municipios_raw -overwrite \
  -lco GEOMETRY_NAME=geom -lco LAUNDER=YES -lco SPATIAL_INDEX=NONE \
  -nlt PROMOTE_TO_MULTI -t_srs EPSG:4674

# Register the source (idempotent) and the immutable snapshot of this file.
SNAPSHOT_ID="$(psql "$DSN" -v ON_ERROR_STOP=1 -X -A -t -q \
  -v source_id="$SOURCE_ID" -v url="$URL" -v sha="$SHA" -v size="$SIZE" \
  -v edition="$EDITION" <<'SQL'
INSERT INTO ld_catalog.source
    (source_id, authority, scope, source_type, access_class, license,
     verification_status, canonical_url, coverage_level, domains)
VALUES
    (:'source_id', 'IBGE', 'BR', 'SHAPEFILE_ZIP', 'OPEN_REUSABLE',
     'Dados públicos IBGE', 'VERIFIED', :'url', 'NATIONAL',
     ARRAY['territory', 'municipal_boundaries'])
ON CONFLICT (source_id) DO NOTHING;

INSERT INTO ld_catalog.snapshot
    (source_id, captured_at, requested_url, final_url, http_status,
     content_type, content_length, sha256, manifest)
VALUES
    (:'source_id', now(), :'url', :'url', 200, 'application/zip',
     :size, :'sha', jsonb_build_object('edition', :'edition'))
ON CONFLICT (source_id, sha256) DO UPDATE SET manifest = EXCLUDED.manifest
RETURNING snapshot_id;
SQL
)"

psql "$DSN" -v ON_ERROR_STOP=1 -q \
  -v mesh_edition="$EDITION" -v snapshot_id="$SNAPSHOT_ID" \
  -v min_count="$MIN_COUNT" \
  -f "$REPO_ROOT/database/loaders/promote_ibge_municipalities.sql"

psql "$DSN" -q -c "DROP TABLE IF EXISTS ld_stage.ibge_municipios_raw"
echo "IBGE mesh $EDITION loaded (snapshot $SNAPSHOT_ID)"
