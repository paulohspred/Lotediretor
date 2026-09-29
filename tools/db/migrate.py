#!/usr/bin/env python3
"""Apply database/migrations/*.sql exactly once, in order, with a ledger.

Each file runs in its own transaction (files may also contain BEGIN/COMMIT;
psql handles that). Applied files are recorded in ld_meta.schema_migration with
their SHA-256. Editing an already-applied migration is an error: create a new
migration instead.

Usage:
    python3 tools/db/migrate.py --dsn "postgresql://..."        # apply pending
    python3 tools/db/migrate.py --dsn ... --status              # list state
    python3 tools/db/migrate.py --dsn ... --baseline 003        # adopt existing
                                                                  DB applied by hand

The DSN can also come from LOTEDIRETOR_DB_DSN. Requires psql on PATH.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "database" / "migrations"

LEDGER_DDL = """
CREATE SCHEMA IF NOT EXISTS ld_meta;
CREATE TABLE IF NOT EXISTS ld_meta.schema_migration (
    version     text PRIMARY KEY,
    filename    text NOT NULL,
    sha256      text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    baselined   boolean NOT NULL DEFAULT false
);
"""


def psql(dsn: str, *args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-A", "-t", *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def migrations() -> list[tuple[str, Path, str]]:
    out = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        version = path.name.split("_", 1)[0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out.append((version, path, digest))
    versions = [v for v, _, _ in out]
    if len(versions) != len(set(versions)):
        raise SystemExit("duplicate migration version prefix")
    return out


def applied(dsn: str) -> dict[str, str]:
    psql(dsn, "-c", LEDGER_DDL)
    rows = psql(dsn, "-c", "SELECT version, sha256 FROM ld_meta.schema_migration")
    return dict(line.split("|", 1) for line in rows.splitlines() if line)


def record(dsn: str, version: str, path: Path, digest: str, baselined: bool) -> None:
    psql(
        dsn,
        "-v", f"version={version}",
        "-v", f"filename={path.name}",
        "-v", f"sha={digest}",
        "-v", f"baselined={'true' if baselined else 'false'}",
        stdin=(
            "INSERT INTO ld_meta.schema_migration"
            "(version, filename, sha256, baselined) "
            "VALUES (:'version', :'filename', :'sha', :baselined);\n"
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--baseline",
        metavar="VERSION",
        help="mark migrations up to VERSION as applied without running them",
    )
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or LOTEDIRETOR_DB_DSN is required")

    done = applied(args.dsn)
    plan = migrations()

    for version, path, digest in plan:
        if version in done and done[version] != digest:
            print(
                f"ERROR: {path.name} changed after being applied "
                f"(ledger {done[version][:12]}, file {digest[:12]}). "
                "Write a new migration instead of editing an applied one.",
                file=sys.stderr,
            )
            return 2

    if args.status:
        for version, path, _ in plan:
            print(f"{'applied' if version in done else 'pending'}\t{path.name}")
        return 0

    if args.baseline:
        for version, path, digest in plan:
            if version <= args.baseline and version not in done:
                record(args.dsn, version, path, digest, baselined=True)
                print(f"baselined {path.name}")
        return 0

    for version, path, digest in plan:
        if version in done:
            continue
        print(f"applying {path.name}", flush=True)
        psql(args.dsn, "-f", str(path))
        record(args.dsn, version, path, digest, baselined=False)
    print("database up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
