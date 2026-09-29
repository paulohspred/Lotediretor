-- Tiny synthetic stand-in for the IBGE mesh, used by CI and tests.
-- Real codes/names, simplified rectangular geometries (NOT official limits).
CREATE SCHEMA IF NOT EXISTS ld_stage;
DROP TABLE IF EXISTS ld_stage.ibge_municipios_raw;
CREATE TABLE ld_stage.ibge_municipios_raw (
    cd_mun text, nm_mun text, cd_uf text, area_km2 text,
    geom geometry(MultiPolygon, 4674)
);
INSERT INTO ld_stage.ibge_municipios_raw VALUES
 ('3550308', 'São Paulo', '35', '1521.202',
  ST_Multi(ST_MakeEnvelope(-46.83, -24.01, -46.36, -23.36, 4674))),
 ('3505708', 'Barueri', '35', '65.701',
  ST_Multi(ST_MakeEnvelope(-46.95, -23.56, -46.83, -23.46, 4674))),
 ('3159605', 'Santa Rita do Sapucaí', '31', '352.967',
  ST_Multi(ST_MakeEnvelope(-45.80, -22.35, -45.60, -22.15, 4674))),
 ('5300108', 'Brasília', '53', '5760.784',
  ST_Multi(ST_MakeEnvelope(-48.29, -16.05, -47.31, -15.50, 4674)));
