#!/usr/bin/env python3
"""Harvest a municipality's layers from an approved connector spec.

For each layer: fetch with GDAL (ArcGIS REST, OGC WFS or file) into a staging
table, requesting only mapped/allowlisted fields; check that the data really
belongs to the municipality; record an immutable snapshot; and switch the
current load atomically. Nothing is promoted if any check fails.

Usage:
    LOTEDIRETOR_DB_DSN=... python3 tools/factory/harvest.py 4209102
    LOTEDIRETOR_DB_DSN=... python3 tools/factory/harvest.py --spec path.json --allow-draft

Requires ogr2ogr (gdal-bin) and psycopg2.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import psycopg2
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec import SPEC_DIR, load, requested_fields, spec_sha256  # noqa: E402

MIN_INSIDE_RATIO = 0.95


def pg_conn_string(dsn: str) -> str:
    """libpq DSN/URL -> GDAL 'PG:' connection string."""
    if "://" not in dsn:
        return "PG:" + dsn
    p = urllib.parse.urlsplit(dsn)
    q = dict(urllib.parse.parse_qsl(p.query))
    parts = {
        "dbname": p.path.lstrip("/") or None,
        "host": q.get("host") or p.hostname,
        "port": q.get("port") or p.port,
        "user": q.get("user") or p.username,
        "password": p.password,
    }
    return "PG:" + " ".join(f"{k}={v}" for k, v in parts.items() if v)


def gdal_source(layer: dict, spec_path: Path) -> tuple[list[str], str | None]:
    """Return (ogr2ogr source args, requested url for provenance)."""
    fields = requested_fields(layer)
    kind = layer["kind"]
    if kind == "arcgis_feature_layer":
        query = urllib.parse.urlencode(
            {
                "where": layer.get("where", "1=1"),
                "outFields": ",".join(fields),
                "returnGeometry": "true",
                "outSR": "4674",
                "f": "json",
            }
        )
        url = f"{layer['url'].rstrip('/')}/query?{query}"
        return (["-oo", "FEATURE_SERVER_PAGING=YES", url], url)
    if kind == "ogc_wfs":
        url = layer["url"]
        return (
            ["-oo", "PAGING_ALLOWED=ON", "-oo", "PAGE_SIZE=1000",
             f"WFS:{url}", layer["type_name"], "-select", ",".join(fields)],
            url,
        )
    # file: path relative to the spec, absolute path, or https URL (vsicurl)
    location = layer["url"]
    if location.startswith("https://"):
        source = f"/vsicurl/{location}"
    else:
        source = str((spec_path.parent / location).resolve())
    args = [source]
    if layer.get("layer_name"):
        args.append(layer["layer_name"])
    args += ["-select", ",".join(fields)]
    return (args, location)


def stage(dsn: str, layer: dict, spec_path: Path, table: str) -> str | None:
    source_args, url = gdal_source(layer, spec_path)
    cmd = [
        "ogr2ogr", "-f", "PostgreSQL", pg_conn_string(dsn),
        *source_args,
        "-nln", f"ld_stage.{table}", "-overwrite",
        "-lco", "GEOMETRY_NAME=geom", "-lco", "LAUNDER=NO",
        "-lco", "SPATIAL_INDEX=NONE", "-lco", "FID=ld_fid",
        "-nlt", "PROMOTE_TO_MULTI", "-t_srs", "EPSG:4674",
    ]
    if layer.get("source_srid"):
        cmd += ["-s_srs", f"EPSG:{layer['source_srid']}"]
    subprocess.run(cmd, check=True)
    return url


def promote(cur, spec: dict, layer: dict, table: str, spec_sha: str, url: str | None) -> dict:
    ibge = spec["municipality_ibge"]
    role = layer["role"]
    f = layer["fields"]
    staged = sql.Identifier("ld_stage", table)

    def col(name: str) -> sql.Composable:
        return sql.Identifier(name)

    # Normalized view of the staged data (valid multipolygons in 4674).
    cur.execute(
        sql.SQL(
            """CREATE TEMP TABLE fx_norm ON COMMIT DROP AS
               SELECT {key}::text AS upstream_key, s.*,
                      ST_Multi(ST_CollectionExtract(ST_MakeValid(s.geom), 3))
                          ::geometry(MultiPolygon, 4674) AS norm_geom
               FROM {staged} s
               WHERE s.geom IS NOT NULL"""
        ).format(key=col(f["upstream_key"]), staged=staged)
    )
    cur.execute("DELETE FROM fx_norm WHERE ST_IsEmpty(norm_geom)")
    cur.execute("SELECT count(*) FROM fx_norm")
    count = cur.fetchone()[0]
    if count < layer["min_features"]:
        raise RuntimeError(
            f"{role}: {count} features, expected at least {layer['min_features']}"
        )

    # Wrong layer or wrong CRS shows up as features outside the municipality.
    cur.execute(
        """SELECT avg((ST_Intersects(ST_PointOnSurface(n.norm_geom), m.geom))::int)
           FROM fx_norm n, ld_core.municipality m WHERE m.ibge_code = %s""",
        (ibge,),
    )
    inside = float(cur.fetchone()[0] or 0)
    if inside < MIN_INSIDE_RATIO:
        raise RuntimeError(
            f"{role}: only {inside:.1%} of features fall inside municipality {ibge}"
        )

    cur.execute(
        """SELECT encode(sha256(convert_to(string_agg(
                  upstream_key || ':' || md5(ST_AsEWKB(norm_geom)::text), ','
                  ORDER BY upstream_key), 'UTF8')), 'hex') FROM fx_norm"""
    )
    content_sha = cur.fetchone()[0]

    cur.execute(
        """INSERT INTO ld_catalog.snapshot
               (source_id, captured_at, requested_url, final_url, sha256, manifest)
           VALUES (%s, now(), %s, %s, %s,
                   jsonb_build_object('role', %s, 'municipality_ibge', %s,
                                      'spec_sha256', %s, 'feature_count', %s,
                                      'hash_method', 'sorted key+EWKB md5, sha256'))
           ON CONFLICT (source_id, sha256) DO UPDATE SET manifest = EXCLUDED.manifest
           RETURNING snapshot_id""",
        (layer["source_id"], url or "", url or "", content_sha, role, ibge,
         spec_sha, count),
    )
    snapshot_id = cur.fetchone()[0]

    cur.execute(
        """UPDATE ld_catalog.municipal_layer_load SET is_current = false
           WHERE ibge_code = %s AND role = %s AND is_current""",
        (ibge, role),
    )
    cur.execute(
        """INSERT INTO ld_catalog.municipal_layer_load
               (ibge_code, role, source_id, snapshot_id, spec_sha256,
                feature_count, inside_municipality_ratio)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING load_id""",
        (ibge, role, layer["source_id"], snapshot_id, spec_sha, count, inside),
    )
    load_id = cur.fetchone()[0]

    allow = layer.get("attribute_allowlist", [])
    attrs = sql.SQL("jsonb_strip_nulls(jsonb_build_object({}))").format(
        sql.SQL(", ").join(
            sql.SQL("{}, {}").format(sql.Literal(a), col(a)) for a in allow
        )
    ) if allow else sql.SQL("'{}'::jsonb")

    def opt(name: str, cast: str = "text") -> sql.Composable:
        if name not in f:
            return sql.SQL("NULL")
        expr = sql.SQL("nullif(trim({}::text), '')").format(col(f[name]))
        if cast == "numeric":
            return sql.SQL("CASE WHEN {e} ~ '^-?[0-9]+([.,][0-9]+)?$' "
                           "THEN replace({e}, ',', '.')::numeric END").format(e=expr)
        return expr

    if role == "parcels":
        cur.execute(
            sql.SQL(
                """INSERT INTO ld_domain.municipal_parcel
                       (load_id, ibge_code, upstream_key, fiscal_reference, street,
                        house_number, neighborhood, land_area_m2, attributes, geom)
                   SELECT %s, %s, upstream_key, {fr}, {st}, {hn}, {nb}, {la},
                          {attrs}, norm_geom
                   FROM fx_norm"""
            ).format(fr=opt("fiscal_reference"), st=opt("street"),
                     hn=opt("house_number"), nb=opt("neighborhood"),
                     la=opt("land_area_m2", "numeric"), attrs=attrs),
            (load_id, ibge),
        )
    else:
        cur.execute(
            sql.SQL(
                """INSERT INTO ld_domain.municipal_zone
                       (load_id, ibge_code, upstream_key, zone_code, zone_name,
                        attributes, geom)
                   SELECT %s, %s, upstream_key, {zc}, {zn}, {attrs}, norm_geom
                   FROM fx_norm WHERE {zc} IS NOT NULL"""
            ).format(zc=opt("zone_code"), zn=opt("zone_name"), attrs=attrs),
            (load_id, ibge),
        )
    return {"role": role, "features": count, "inside_ratio": round(inside, 4),
            "load_id": str(load_id), "snapshot_id": str(snapshot_id)}


def harvest(dsn: str, spec_path: Path, allow_draft: bool, roles: set[str] | None) -> list[dict]:
    # At runtime the database catalog is the authority for source ids (the
    # registry JSON is published there by load_source_registry.py).
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT source_id FROM ld_catalog.source WHERE retired_at IS NULL")
        known = {row[0] for row in cur.fetchall()}
    spec = load(spec_path, known)
    if spec["status"] != "APPROVED" and not allow_draft:
        raise SystemExit(f"{spec_path.name} is {spec['status']}; review it or pass --allow-draft")
    spec_sha = spec_sha256(spec_path)
    results = []
    for layer in spec["layers"]:
        if roles and layer["role"] not in roles:
            continue
        table = f"fx_{spec['municipality_ibge']}_{layer['role']}"
        try:
            url = stage(dsn, layer, spec_path, table)
            with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
                results.append(promote(cur, spec, layer, table, spec_sha, url))
        finally:
            # Never leave partially fetched municipal data behind.
            with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(
                    sql.Identifier("ld_stage", table)))
        print(f"{spec['municipality_ibge']} {layer['role']}: {results[-1]}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ibge", nargs="?")
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--role", action="append", choices=["parcels", "zoning"])
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or LOTEDIRETOR_DB_DSN is required")
    spec_path = args.spec or (SPEC_DIR / f"{args.ibge}.json")
    if not spec_path.exists():
        parser.error(f"spec not found: {spec_path}")
    harvest(args.dsn, spec_path, args.allow_draft, set(args.role or []) or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
