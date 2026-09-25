#!/usr/bin/env python3
"""Build a privacy-safe Recife property lookup index from complete CKAN snapshots."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NORMALIZER_PATH = ROOT / "tools/normalization/recife_property.py"

spec = importlib.util.spec_from_file_location("recife_norm", NORMALIZER_PATH)
norm = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(norm)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS metadata (
  dataset_key TEXT PRIMARY KEY,
  snapshot_dir TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  record_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS iptu (
  municipal_tax_reference TEXT PRIMARY KEY,
  normalized_json TEXT NOT NULL,
  latitude REAL,
  longitude REAL
);
CREATE TABLE IF NOT EXISTS itbi (
  upstream_key TEXT PRIMARY KEY,
  normalized_json TEXT NOT NULL,
  transaction_date TEXT,
  latitude REAL,
  longitude REAL
);
CREATE INDEX IF NOT EXISTS itbi_lat_lon_idx ON itbi(latitude,longitude);
CREATE TABLE IF NOT EXISTS licensing (
  upstream_key TEXT PRIMARY KEY,
  dsqfl TEXT,
  normalized_json TEXT NOT NULL,
  latitude REAL,
  longitude REAL
);
CREATE INDEX IF NOT EXISTS licensing_dsqfl_idx ON licensing(dsqfl);
CREATE INDEX IF NOT EXISTS licensing_lat_lon_idx ON licensing(latitude,longitude);
"""


def latest_complete(base: Path, dataset_key: str) -> Path | None:
    parent = base / dataset_key / f"recife-{dataset_key}"
    if not parent.exists():
        return None
    found = []
    for folder in parent.iterdir():
        if not folder.is_dir():
            continue
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("complete") is True:
            found.append((manifest.get("captured_at") or folder.name, folder))
    return sorted(found)[-1][1] if found else None


def load_snapshot(conn: sqlite3.Connection, snapshot: Path) -> int:
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    dataset_key = manifest["dataset_key"]
    normalize = norm.NORMALIZERS[dataset_key]
    count = 0
    if dataset_key == "iptu_2026":
        conn.execute("DELETE FROM iptu")
    elif dataset_key == "itbi_2026":
        conn.execute("DELETE FROM itbi")
    elif dataset_key == "licenciamento":
        conn.execute("DELETE FROM licensing")

    for page in manifest["pages"]:
        payload = json.loads((snapshot / page["raw_file"]).read_text(encoding="utf-8"))
        for record in payload["result"]["records"]:
            norm.ensure_safe(record, manifest)
            row = normalize(record, manifest)
            loc = row.get("location") or {}
            coords = loc.get("coordinates") or [None, None]
            lon, lat = coords if len(coords) == 2 else (None, None)
            raw = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            if dataset_key == "iptu_2026":
                ref = (row.get("identity") or {}).get("municipal_tax_reference")
                if ref is None:
                    continue
                conn.execute(
                    """INSERT INTO iptu(municipal_tax_reference,normalized_json,latitude,longitude)
                       VALUES(?,?,?,?)
                       ON CONFLICT(municipal_tax_reference) DO UPDATE SET
                         normalized_json=excluded.normalized_json,
                         latitude=excluded.latitude,longitude=excluded.longitude""",
                    (str(ref), raw, lat, lon),
                )
            elif dataset_key == "itbi_2026":
                conn.execute(
                    """INSERT INTO itbi(upstream_key,normalized_json,transaction_date,latitude,longitude)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(upstream_key) DO UPDATE SET
                         normalized_json=excluded.normalized_json,
                         transaction_date=excluded.transaction_date,
                         latitude=excluded.latitude,longitude=excluded.longitude""",
                    (row["upstream_key"], raw, (row.get("transaction") or {}).get("date"), lat, lon),
                )
            else:
                dsqfl = (row.get("project") or {}).get("fiscal_location_reference")
                conn.execute(
                    """INSERT INTO licensing(upstream_key,dsqfl,normalized_json,latitude,longitude)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(upstream_key) DO UPDATE SET
                         dsqfl=excluded.dsqfl,normalized_json=excluded.normalized_json,
                         latitude=excluded.latitude,longitude=excluded.longitude""",
                    (row["upstream_key"], None if dsqfl is None else str(dsqfl), raw, lat, lon),
                )
            count += 1

    conn.execute(
        """INSERT INTO metadata(dataset_key,snapshot_dir,captured_at,record_count)
           VALUES(?,?,?,?)
           ON CONFLICT(dataset_key) DO UPDATE SET
             snapshot_dir=excluded.snapshot_dir,
             captured_at=excluded.captured_at,
             record_count=excluded.record_count""",
        (dataset_key, str(snapshot), manifest["captured_at"], count),
    )
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-root", type=Path, default=Path("/srv/lotediretor/data/recife"))
    ap.add_argument("--out", type=Path, default=Path("/srv/lotediretor/data/recife/index/recife-property.sqlite3"))
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.out)
    try:
        conn.executescript(SCHEMA)
        results = {}
        for key in ("iptu_2026", "itbi_2026", "licenciamento"):
            snapshot = latest_complete(args.snapshot_root, key)
            if snapshot is None:
                results[key] = {"loaded": False, "reason": "no_complete_snapshot"}
                continue
            n = load_snapshot(conn, snapshot)
            conn.commit()
            results[key] = {"loaded": True, "records": n, "snapshot": str(snapshot)}
        conn.execute("PRAGMA optimize")
        conn.commit()
        counts = {
            "iptu": conn.execute("SELECT COUNT(*) FROM iptu").fetchone()[0],
            "itbi": conn.execute("SELECT COUNT(*) FROM itbi").fetchone()[0],
            "licensing": conn.execute("SELECT COUNT(*) FROM licensing").fetchone()[0],
        }
        print(json.dumps({"database": str(args.out), "datasets": results, "counts": counts}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
