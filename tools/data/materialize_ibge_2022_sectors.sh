#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-/var/cache/lotediretor/ibge}"
mkdir -p "$OUT_DIR"

if ! command -v ogr2ogr >/dev/null 2>&1; then
  echo "ogr2ogr is required (Ubuntu package: gdal-bin)" >&2
  exit 2
fi

BASE="https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/malha_com_atributos/setores/gpkg/UF"
export CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.gpkg

materialize() {
  local ibge="$1" uf="$2"
  local src="/vsicurl/${BASE}/${uf}/${uf}_setores_CD2022.gpkg"
  local layer="${uf}_setores_CD2022"
  local dest="${OUT_DIR}/${ibge}_setores_CD2022.gpkg"
  local tmp="${dest}.tmp.gpkg"

  echo "IBGE 2022 sectors: ${ibge} (${uf})"
  rm -f "$tmp"
  ogr2ogr -f GPKG "$tmp" "$src" "$layer" \
    -where "CD_MUN='${ibge}'" \
    -nln setores \
    -t_srs EPSG:4326 \
    -lco SPATIAL_INDEX=YES

  count="$(ogrinfo -ro -so "$tmp" setores | awk -F': ' '/Feature Count:/ {print $2; exit}')"
  if [[ -z "$count" || "$count" -lt 1 ]]; then
    echo "No census sectors extracted for ${ibge}" >&2
    rm -f "$tmp"
    exit 3
  fi

  mv -f "$tmp" "$dest"
  chmod 0644 "$dest"
  echo "  ${count} sectors -> ${dest}"
}

materialize 3550308 SP
materialize 2611606 PE
materialize 3304557 RJ
materialize 3106200 MG
materialize 2507507 PB

echo "IBGE census-sector materialization complete."
