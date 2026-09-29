#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/legal/barueri-lc565-sector-rules.json"
TARGET = "ld_stage.barueri_zoning_sector_rules"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, text=True)


def main() -> int:
    data = json.loads(SOURCE.read_text())
    sector_to_group = data["sector_to_group"]
    groups = data["groups"]

    if len(sector_to_group) != 100 or len(groups) != 17:
        raise SystemExit(
            f"catálogo jurídico inesperado: setores={len(sector_to_group)} grupos={len(groups)}"
        )

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", suffix=".csv", delete=False
    ) as handle:
        csv_path = pathlib.Path(handle.name)
        writer = csv.writer(handle)
        writer.writerow(
            ["sector_code", "use_group", "article", "rule_text", "source_url"]
        )
        for sector, group in sorted(sector_to_group.items()):
            rule = groups[group]
            if not rule.get("rule_text"):
                raise SystemExit(f"regra vazia para {group}")
            writer.writerow(
                [sector, group, rule["article"], rule["rule_text"], data["source_url"]]
            )

    csv_path.chmod(0o644)

    try:
        ddl = f"""
BEGIN;
CREATE SCHEMA IF NOT EXISTS ld_stage;
DROP TABLE IF EXISTS {TARGET};
CREATE TABLE {TARGET}(
  sector_code text PRIMARY KEY,
  use_group text NOT NULL,
  article integer NOT NULL,
  rule_text text NOT NULL,
  source_url text NOT NULL,
  source_scope text NOT NULL DEFAULT 'LEGAL_RULE_REQUIRES_VALIDATED_SPATIAL_SECTOR'
);
COMMIT;
"""
        run(["sudo", "-u", "postgres", "psql", "-d", "lotediretor",
             "-v", "ON_ERROR_STOP=1", "-c", ddl])
        copy_sql = (
            rf"\copy {TARGET}(sector_code,use_group,article,rule_text,source_url) "
            rf"FROM '{csv_path}' CSV HEADER"
        )
        run(["sudo", "-u", "postgres", "psql", "-d", "lotediretor",
             "-v", "ON_ERROR_STOP=1", "-c", copy_sql])
        finish = f"""
BEGIN;
CREATE INDEX barueri_zoning_sector_rules_group_idx ON {TARGET}(use_group);
GRANT SELECT ON {TARGET} TO sentinelx;
ANALYZE {TARGET};
DO $$
DECLARE c integer; g integer;
BEGIN
  SELECT count(*), count(DISTINCT use_group) INTO c, g FROM {TARGET};
  IF c <> 100 OR g <> 17 THEN
    RAISE EXCEPTION 'catálogo jurídico inválido: setores %, grupos %', c, g;
  END IF;
END $$;
COMMIT;
"""
        run(["sudo", "-u", "postgres", "psql", "-d", "lotediretor",
             "-v", "ON_ERROR_STOP=1", "-c", finish])
    finally:
        csv_path.unlink(missing_ok=True)

    print(f"OK {TARGET}: 100 setores / 17 classes; catálogo legal sem resolução espacial")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
