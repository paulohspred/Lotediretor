#!/usr/bin/env bash
# Runs once on an empty data directory (postgis image entrypoint).
# Creates the runtime role used by the API/BFFs (least privilege: grants are
# applied by the migrations to this role) and a separate Keycloak database.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}';
CREATE ROLE keycloak LOGIN PASSWORD '${KEYCLOAK_DB_PASSWORD}';
CREATE DATABASE keycloak OWNER keycloak;
ALTER DATABASE ${POSTGRES_DB} SET lotediretor.app_role = '${APP_DB_USER}';
SQL
