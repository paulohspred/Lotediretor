#!/usr/bin/env bash
set -euo pipefail

# Materialize the IBGE 2022 census-sector mesh for the five first-wave cities.
# Run as root because the import step uses the local postgres OS account.
#
# Required packages:
#   gdal-bin, postgresql-client, postgis
#
# Source:
# https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/
# Agregados_por_Setores_Censitarios/malha_com_atributos/setores/gpkg/UF/

CACHE_DIR="${CACHE_DIR:-/var/cache/lotediretor/ibge}"
DB_NAME="${DB_NAME:-lotediretor}"
APP_DB_USER="${APP_DB_USER:-sentinelx}"
BASE_URL="https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/malha_com_atributos/setores/gpkg/UF"

# Reuse the canonical municipality materializer. It streams the official
# state GeoPackage over /vsicurl and keeps only the five municipalities.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
bash "$REPO_ROOT/tools/data/materialize_ibge_2022_sectors.sh" "$CACHE_DIR"

runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
CREATE SCHEMA IF NOT EXISTS ld_stage;
DROP TABLE IF EXISTS ld_stage.ibge_censo2022_setores;
SQL

first=1
for code in 3550308 2611606 3304557 3106200 2507507; do
  city_file="$CACHE_DIR/${code}_setores_CD2022.gpkg"
  if [[ "$first" -eq 1 ]]; then
    runuser -u postgres -- ogr2ogr -f PostgreSQL       "PG:dbname=$DB_NAME user=postgres host=/var/run/postgresql"       "$city_file" setores       -nln ld_stage.ibge_censo2022_setores       -lco GEOMETRY_NAME=geom -lco FID=id       -nlt MULTIPOLYGON -t_srs EPSG:4674
    first=0
  else
    runuser -u postgres -- ogr2ogr -f PostgreSQL       "PG:dbname=$DB_NAME user=postgres host=/var/run/postgresql"       "$city_file" setores       -nln ld_stage.ibge_censo2022_setores       -append -nlt MULTIPOLYGON -t_srs EPSG:4674
  fi
done

runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
CREATE INDEX IF NOT EXISTS ibge_censo2022_setores_geom_gix
  ON ld_stage.ibge_censo2022_setores USING GIST (geom);
CREATE INDEX IF NOT EXISTS ibge_censo2022_setores_mun_idx
  ON ld_stage.ibge_censo2022_setores (cd_mun);
ANALYZE ld_stage.ibge_censo2022_setores;
GRANT USAGE ON SCHEMA ld_stage TO $APP_DB_USER;
GRANT SELECT ON ld_stage.ibge_censo2022_setores TO $APP_DB_USER;
SQL

runuser -u postgres -- psql -d "$DB_NAME" -P pager=off <<'SQL'
SELECT
  cd_mun,
  nm_mun,
  count(*) AS setores,
  sum(v0001) AS pessoas
FROM ld_stage.ibge_censo2022_setores
GROUP BY 1,2
ORDER BY 1;
SQL
