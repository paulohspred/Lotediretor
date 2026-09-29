#!/usr/bin/env python3
"""Materializa lotes de Barueri somente quando a geometria e o CRS são verificáveis.

Não adivinha CRS, nomes de campos ou georreferenciamento. Formatos vetoriais são
abertos pelo GDAL/OGR. CSV/XLSX só passam se o OGR expuser geometria. PDF exige
--source-srs explícito e documentalmente verificável.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import subprocess

TARGET = "ld_stage.barueri_lotes"
ALLOWED = {".shp", ".gpkg", ".geojson", ".json", ".gdb", ".kml", ".kmz", ".dxf", ".dwg", ".csv", ".xlsx", ".xls", ".pdf"}
STANDARD_FIELDS = {"inscricao","setor","quadra","lote","endereco","area_terreno","area_construida","uso","status","official_id"}

def run(cmd, capture=False):
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)

def ident(name):
    return '"' + str(name).replace('"', '""') + '"'

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--layer")
    p.add_argument("--source-srs", help="CRS verificável, ex. EPSG:31983")
    p.add_argument("--db", default="lotediretor")
    p.add_argument("--db-user", default="postgres")
    p.add_argument("--field-map-json", required=True, help="JSON: campo padronizado -> nome exato na fonte")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    src = pathlib.Path(a.input)
    if not src.exists():
        raise SystemExit(f"arquivo não encontrado: {src}")
    ext = src.suffix.lower()
    if ext not in ALLOWED and not src.name.lower().endswith(".gdb"):
        raise SystemExit(f"formato não permitido: {ext or src.name}")

    mapping = json.loads(pathlib.Path(a.field_map_json).read_text())
    unknown = set(mapping) - STANDARD_FIELDS
    if unknown:
        raise SystemExit(f"chaves de mapeamento não suportadas: {sorted(unknown)}")
    if ext == ".pdf" and not a.source_srs:
        raise SystemExit("PDF exige --source-srs verificável; georreferenciamento visual é proibido")

    info = run(["ogrinfo", "-ro", "-so", "-al", str(src)], capture=True).stdout
    if "Geometry:" not in info and "Geometry Column" not in info:
        raise SystemExit("OGR não reportou geometria; não materializar como lote")
    if not a.source_srs and not any(token in info for token in ("EPSG", "AUTHORITY[", "Layer SRS WKT")):
        raise SystemExit("CRS ausente/não verificável; informe --source-srs somente com base documental")

    pg = f"PG:dbname={a.db} user={a.db_user} host=/var/run/postgresql"
    tmp = "ld_stage._barueri_lotes_import"
    ogr = ["ogr2ogr", "-overwrite", "-f", "PostgreSQL", pg, str(src)]
    if a.layer:
        ogr.append(a.layer)
    ogr += ["-nln", tmp, "-nlt", "PROMOTE_TO_MULTI", "-t_srs", "EPSG:4674",
            "-lco", "GEOMETRY_NAME=geom", "-lco", "FID=ogr_fid"]
    if a.source_srs:
        ogr += ["-s_srs", a.source_srs]

    if a.dry_run:
        print(json.dumps({"ogr2ogr": ogr, "target": TARGET, "field_map": mapping}, ensure_ascii=False, indent=2))
        return 0

    run(["psql", "-d", a.db, "-v", "ON_ERROR_STOP=1", "-c", "CREATE SCHEMA IF NOT EXISTS ld_stage;"])
    run(ogr)

    def expr(key, cast="text"):
        col = mapping.get(key)
        return f"{ident(col)}::{cast}" if col else f"NULL::{cast}"

    sql = f"""
BEGIN;
DROP TABLE IF EXISTS {TARGET};
CREATE TABLE {TARGET} AS
SELECT
  ogr_fid::bigint AS source_row_id,
  {expr('inscricao')} AS inscricao,
  {expr('setor')} AS setor,
  {expr('quadra')} AS quadra,
  {expr('lote')} AS lote,
  {expr('endereco')} AS endereco,
  {expr('area_terreno','double precision')} AS area_terreno,
  {expr('area_construida','double precision')} AS area_construida,
  {expr('uso')} AS uso,
  {expr('status')} AS status,
  {expr('official_id')} AS official_id,
  ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3))::geometry(MultiPolygon,4674) AS geom
FROM {tmp}
WHERE geom IS NOT NULL;
DELETE FROM {TARGET} WHERE geom IS NULL OR ST_IsEmpty(geom);
ALTER TABLE {TARGET} ADD PRIMARY KEY (source_row_id);
CREATE INDEX barueri_lotes_geom_gix ON {TARGET} USING GIST (geom);
CREATE INDEX barueri_lotes_inscricao_idx ON {TARGET} (inscricao) WHERE inscricao IS NOT NULL;
CREATE INDEX barueri_lotes_sql_idx ON {TARGET} (setor, quadra, lote) WHERE setor IS NOT NULL OR quadra IS NOT NULL OR lote IS NOT NULL;
CREATE INDEX barueri_lotes_official_id_idx ON {TARGET} (official_id) WHERE official_id IS NOT NULL;
ANALYZE {TARGET};
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM {TARGET} WHERE ST_SRID(geom) <> 4674 OR NOT ST_IsValid(geom)) THEN
    RAISE EXCEPTION 'geometria inválida ou SRID diferente de EPSG:4674';
  END IF;
END $$;
DROP TABLE IF EXISTS {tmp};
COMMIT;
"""
    run(["psql", "-d", a.db, "-v", "ON_ERROR_STOP=1", "-c", sql])
    print(f"materializado {TARGET}; revisar contagem, bbox, amostra e proveniência antes de habilitar Martin/Resolver")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
