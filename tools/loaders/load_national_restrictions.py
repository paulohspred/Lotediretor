#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data" / "restrictions" / "layers.json"
CACHE = Path(os.environ.get("LOTEDIRETOR_RESTRICTION_CACHE", "/var/cache/lotediretor/restrictions"))

def cache_dir() -> Path:
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        return CACHE
    except PermissionError:
        fallback = Path(tempfile.gettempdir()) / "lotediretor-restrictions"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
PII_KEY_FRAGMENT = ("cpf", "cnpj", "propriet", "titular", "owner")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, headers: dict[str, str] | None = None) -> tuple[int, str | None, str]:
    request_headers = {"User-Agent": "LoteDiretor/1.0 (+https://lotediretor.com)"}
    request_headers.update(headers or {})
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=180) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)
        return response.status, response.headers.get("Content-Type"), response.geturl()


def download_arcgis(
    layer_url: str,
    raw_dest: Path,
    normalized_dest: Path,
    fields: list[str],
) -> tuple[int, str, str, dict]:
    query_url = layer_url.rstrip("/") + "/query"
    offset = 0
    page = 1000
    page_hashes: list[str] = []
    total = 0
    first_feature = True
    with raw_dest.open("wb") as raw_out, normalized_dest.open("w", encoding="utf-8") as normalized:
        normalized.write('{"type":"FeatureCollection","features":[')
        while True:
            params = urllib.parse.urlencode({
                "where": "1=1",
                "outFields": ",".join(fields),
                "returnGeometry": "true",
                "outSR": "4674",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page,
            })
            req = urllib.request.Request(
                query_url + "?" + params,
                headers={"User-Agent": "LoteDiretor/1.0 (+https://lotediretor.com)"},
            )
            with urllib.request.urlopen(req, timeout=180) as response:
                raw = response.read()
            page_hashes.append(hashlib.sha256(raw).hexdigest())
            raw_out.write(raw)
            raw_out.write(b"\n")
            body = json.loads(raw)
            rows = body.get("features") or []
            for feature in rows:
                if not first_feature:
                    normalized.write(",")
                json.dump(feature, normalized, ensure_ascii=False, separators=(",", ":"))
                first_feature = False
            total += len(rows)
            if len(rows) < page:
                break
            offset += len(rows)
            if offset > 5_000_000:
                raise RuntimeError("arcgis_page_safety_limit")
        normalized.write("]}")
    return 200, "application/jsonl", query_url, {
        "page_sha256": page_hashes,
        "page_count": len(page_hashes),
        "feature_count_raw": total,
        "raw_bundle_format": "newline-separated exact ArcGIS page responses",
    }


def layer_config(key: str, path: Path = CONFIG) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for item in doc["layers"]:
        if item["layer_key"] == key:
            return item
    raise SystemExit(f"unknown layer: {key}")


def ensure_layer_row(cur, cfg: dict) -> None:
    cur.execute("SELECT 1 FROM ld_catalog.source WHERE source_id=%s AND retired_at IS NULL", (cfg["source_id"],))
    if cur.fetchone() is None:
        raise RuntimeError(f"source not published in registry: {cfg['source_id']}")
    cur.execute(
        """INSERT INTO ld_core.restriction_layer
           (layer_key,source_id,theme,authority,source_url,source_format,license,status,notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'NOT_LOADED',%s)
           ON CONFLICT (layer_key) DO UPDATE SET
             source_id=EXCLUDED.source_id, theme=EXCLUDED.theme, authority=EXCLUDED.authority,
             source_url=EXCLUDED.source_url, source_format=EXCLUDED.source_format,
             license=EXCLUDED.license, notes=EXCLUDED.notes, updated_at=now()""",
        (cfg["layer_key"], cfg["source_id"], cfg["theme"], cfg["authority"], cfg["source_url"],
         cfg["source_format"], cfg.get("license"), cfg.get("notes")),
    )


def record_snapshot(cur, cfg: dict, path: Path, requested: str, final_url: str,
                    http_status: int | None, content_type: str | None, manifest: dict) -> str:
    digest = sha256_file(path)
    object_key = str(path) if cfg.get("retain_raw", True) else None
    cur.execute(
        """INSERT INTO ld_catalog.snapshot
             (source_id,captured_at,requested_url,final_url,http_status,content_type,
              content_length,sha256,object_key,source_updated_at,manifest)
           VALUES (%s,now(),%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (source_id,sha256) DO UPDATE SET
             source_updated_at=coalesce(EXCLUDED.source_updated_at, ld_catalog.snapshot.source_updated_at),
             manifest=EXCLUDED.manifest
           RETURNING snapshot_id""",
        (cfg["source_id"], requested, final_url, http_status, content_type, path.stat().st_size,
         digest, object_key, cfg.get("source_updated_at"), json.dumps(manifest)),
    )
    return str(cur.fetchone()[0])


def pg_ogr_dsn(dsn: str) -> str:
    if "://" not in dsn:
        return "PG:" + dsn
    parsed = urllib.parse.urlsplit(dsn)
    query = dict(urllib.parse.parse_qsl(parsed.query))
    values = {
        "dbname": parsed.path.lstrip("/") or None,
        "host": query.get("host") or parsed.hostname,
        "port": query.get("port") or parsed.port,
        "user": query.get("user") or parsed.username,
        "password": parsed.password,
        "sslmode": query.get("sslmode"),
    }
    def quote(value: object) -> str:
        text = str(value).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{text}'"
    return "PG:" + " ".join(
        f"{key}={quote(value)}" for key, value in values.items() if value is not None
    )


def stage_file(dsn: str, cfg: dict, source: Path, table: str) -> None:
    src = str(source)
    if source.suffix.lower() == ".zip":
        src = "/vsizip/" + str(source)
    cmd = ["ogr2ogr"]
    if cfg.get("source_encoding"):
        cmd += ["--config", "SHAPE_ENCODING", cfg["source_encoding"]]
    cmd += ["-f", "PostgreSQL", pg_ogr_dsn(dsn), src]
    if cfg.get("layer_name"):
        cmd.append(cfg["layer_name"])
    allow = cfg.get("attribute_allowlist") or []
    if allow:
        cmd += ["-select", ",".join(allow)]
    cmd += [
        "-nln", f"ld_stage.{table}", "-overwrite",
        "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NONE",
        "-t_srs", "EPSG:4674", "-nlt", "PROMOTE_TO_MULTI",
    ]
    subprocess.run(cmd, check=True)


def first_value_expr(fields: list[str]) -> sql.Composable:
    if not fields:
        return sql.SQL("NULL")
    return sql.SQL("coalesce({})").format(sql.SQL(",").join(
        sql.SQL("nullif(to_jsonb(s)->>{}, '')").format(sql.Literal(f)) for f in fields
    ))


def promote(cur, cfg: dict, table: str, snapshot_id: str, captured_at: datetime) -> int:
    staged = sql.Identifier("ld_stage", table)
    label_expr = first_value_expr(cfg.get("label_fields", []))
    cat_expr = first_value_expr(cfg.get("category_fields", []))
    key_parts = [
        sql.SQL("nullif(to_jsonb(s)->>{}, '')").format(sql.Literal(f))
        for f in cfg.get("key_fields", [])
    ]
    key_parts.append(
        sql.SQL("md5(ST_AsEWKB(ST_Force2D(s.geom))::text || to_jsonb(s)::text)")
    )
    upstream_key_expr = sql.SQL("coalesce({})").format(sql.SQL(",").join(key_parts))
    cur.execute(sql.SQL("SELECT count(*) FROM {} WHERE geom IS NOT NULL").format(staged))
    count = int(cur.fetchone()[0])
    if count < int(cfg.get("min_features", 1)):
        raise RuntimeError(f"{cfg['layer_key']}: only {count} features")

    cur.execute(sql.SQL("""
      SELECT count(*) FROM {staged}
      WHERE geom IS NOT NULL AND (
        ST_SRID(geom) <> 4674 OR NOT ST_IsValid(ST_MakeValid(geom))
      )
    """).format(staged=staged))
    if int(cur.fetchone()[0]) != 0:
        raise RuntimeError("invalid_geometry_or_srid")

    cur.execute(
        sql.SQL("""
          INSERT INTO ld_core.restriction_feature
            (layer_key,snapshot_id,upstream_key,label,category,attributes,geom,captured_at)
          SELECT %s,%s,
                 {upstream_key},
                 {label}, {category},
                 coalesce((
                   SELECT jsonb_object_agg(e.key,e.value)
                   FROM jsonb_each(to_jsonb(s) - 'geom') e
                   WHERE lower(e.key) !~ '(cpf|cnpj|propriet|titular|owner)'
                 ), '{{}}'::jsonb),
                 ST_Force2D(ST_MakeValid(s.geom))::geometry(Geometry,4674),
                 %s
          FROM {staged} s
          WHERE s.geom IS NOT NULL
          ON CONFLICT (layer_key,snapshot_id,upstream_key) DO NOTHING
        """).format(
            staged=staged,
            label=label_expr,
            category=cat_expr,
            upstream_key=upstream_key_expr,
        ),
        (cfg["layer_key"], snapshot_id, captured_at),
    )
    cur.execute(
        """UPDATE ld_core.restriction_layer
           SET status='ACTIVE', current_snapshot_id=%s, feature_count=%s,
               source_updated_at=%s, loaded_at=%s, updated_at=now()
           WHERE layer_key=%s""",
        (snapshot_id, count, cfg.get("source_updated_at"), captured_at, cfg["layer_key"]),
    )
    return count


def load_one(dsn: str, cfg: dict, supplied_file: Path | None = None) -> dict:
    cache = cache_dir()
    stamp = datetime.now(timezone.utc)
    ext = ".bin"
    fmt = cfg["source_format"].lower()
    if "zip" in fmt:
        ext = ".zip"
    elif "geojson" in fmt or cfg["mode"] == "arcgis":
        ext = ".geojson"
    elif "csv" in fmt:
        ext = ".csv"
    raw = cache / f"{cfg['layer_key']}-{stamp.strftime('%Y%m%dT%H%M%SZ')}{ext}"
    import_file = raw

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        ensure_layer_row(cur, cfg)

    if cfg["mode"] == "manual_official_file" and supplied_file is None:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("UPDATE ld_core.restriction_layer SET status='NOT_LOADED', updated_at=now() WHERE layer_key=%s",
                        (cfg["layer_key"],))
        return {"layer_key": cfg["layer_key"], "status": "FILE_REQUIRED", "source_url": cfg["source_url"]}

    requested = cfg["source_url"]
    try:
        if supplied_file:
            shutil.copy2(supplied_file, raw)
            status, content_type, final_url = None, None, requested
        elif cfg["mode"] == "arcgis":
            raw = cache / f"{cfg['layer_key']}-{stamp.strftime('%Y%m%dT%H%M%SZ')}.arcgis-pages.jsonl"
            import_file = cache / f"{cfg['layer_key']}-{stamp.strftime('%Y%m%dT%H%M%SZ')}.geojson"
            fields = cfg.get("attribute_allowlist") or []
            if not fields:
                raise RuntimeError("arcgis_attribute_allowlist_required")
            status, content_type, final_url, arcgis_manifest = download_arcgis(
                requested, raw, import_file, fields
            )
        else:
            headers = {"Referer": cfg["referer"]} if cfg.get("referer") else None
            status, content_type, final_url = download(requested, raw, headers=headers)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE ld_core.restriction_layer
                   SET status='SOURCE_UNAVAILABLE', updated_at=now()
                   WHERE layer_key=%s""",
                (cfg["layer_key"],),
            )
        return {
            "layer_key": cfg["layer_key"],
            "status": "SOURCE_UNAVAILABLE",
            "source_url": requested,
            "error": type(exc).__name__,
        }

    manifest = {
        "layer_key": cfg["layer_key"], "authority": cfg["authority"],
        "license": cfg.get("license"), "source_format": cfg["source_format"],
        "source_url": requested, "captured_at": stamp.isoformat(),
        "source_updated_at": cfg.get("source_updated_at"),
        "lgpd_filter": "cpf/cnpj/proprietario/titular/owner attribute keys removed from normalized features",
    }
    if cfg["mode"] == "arcgis":
        manifest.update(arcgis_manifest)

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        snapshot_id = record_snapshot(cur, cfg, raw, requested, final_url, status, content_type, manifest)
        if cfg["mode"] == "metadata_only":
            cur.execute(
                """UPDATE ld_core.restriction_layer
                   SET status='NOT_AVAILABLE_SPATIAL', current_snapshot_id=%s, feature_count=0,
                       source_updated_at=%s, loaded_at=%s, updated_at=now()
                   WHERE layer_key=%s""",
                (snapshot_id, cfg.get("source_updated_at"), stamp, cfg["layer_key"]),
            )
            return {"layer_key": cfg["layer_key"], "status": "NOT_AVAILABLE_SPATIAL",
                    "snapshot_id": snapshot_id, "sha256": sha256_file(raw)}

    table = "nr_" + "".join(c if c.isalnum() else "_" for c in cfg["layer_key"])[:48]
    try:
        stage_file(dsn, cfg, import_file, table)
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            count = promote(cur, cfg, table, snapshot_id, stamp)
        return {"layer_key": cfg["layer_key"], "status": "ACTIVE", "features": count,
                "snapshot_id": snapshot_id, "sha256": sha256_file(raw)}
    except Exception:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE ld_core.restriction_layer SET status='FAILED_VALIDATION', updated_at=now() WHERE layer_key=%s",
                (cfg["layer_key"],),
            )
        raise
    finally:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier("ld_stage", table)))
        if cfg.get("mode") == "arcgis" and import_file != raw:
            import_file.unlink(missing_ok=True)
        if not cfg.get("retain_raw", True):
            raw.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer", nargs="?", help="layer_key; omit with --all")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--register-only", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or LOTEDIRETOR_DB_DSN is required")
    doc = json.loads(args.config.read_text(encoding="utf-8"))
    selected = doc["layers"] if args.all else [layer_config(args.layer, args.config)]
    if args.file and len(selected) != 1:
        parser.error("--file requires exactly one layer")
    if args.register_only:
        with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
            for cfg in selected:
                ensure_layer_row(cur, cfg)
        for cfg in selected:
            print(json.dumps({"layer_key": cfg["layer_key"], "status": "REGISTERED"}, ensure_ascii=False))
        return 0
    failures = 0
    for cfg in selected:
        try:
            print(json.dumps(load_one(args.dsn, cfg, args.file), ensure_ascii=False), flush=True)
        except Exception as exc:
            failures += 1
            print(json.dumps({"layer_key": cfg["layer_key"], "status": "ERROR", "error": str(exc)},
                             ensure_ascii=False), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
