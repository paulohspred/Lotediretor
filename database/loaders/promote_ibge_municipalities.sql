-- Promote the staged IBGE municipal mesh into ld_core.municipality.
--
-- Input:  ld_stage.ibge_municipios_raw (loaded by ogr2ogr, any column case)
--         with columns cd_mun, nm_mun, cd_uf, area_km2 and geometry "geom".
-- Vars:   :mesh_edition   e.g. '2024'
--         :snapshot_id    uuid of the ld_catalog.snapshot row, or '' for none
--         :min_count      minimum number of municipalities expected (5560 in
--                         production; small in tests)
--
-- Everything runs in one transaction and aborts, leaving the current mesh
-- untouched, if any sanity check fails.

\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE mesh_in ON COMMIT DROP AS
SELECT
    lpad(trim(cd_mun::text), 7, '0')::char(7) AS ibge_code,
    trim(nm_mun::text) AS name,
    trim(cd_uf::text)::smallint AS uf_code,
    nullif(area_km2::text, '')::numeric(12, 3) AS area_km2,
    ST_Multi(
        ST_CollectionExtract(ST_MakeValid(ST_Transform(geom, 4674)), 3)
    )::geometry(MultiPolygon, 4674) AS geom
FROM ld_stage.ibge_municipios_raw;

-- psql does not interpolate variables inside dollar-quoted bodies.
SELECT set_config('ld.min_count', :'min_count', true) \g /dev/null

DO $checks$
DECLARE
    n integer;
    bad integer;
    min_count integer := current_setting('ld.min_count')::integer;
BEGIN
    SELECT count(*) INTO n FROM mesh_in;
    IF n < min_count THEN
        RAISE EXCEPTION 'mesh has % municipalities, expected at least %', n, min_count;
    END IF;

    SELECT count(*) INTO bad FROM mesh_in
    WHERE ibge_code !~ '^[0-9]{7}$' OR name = '' OR geom IS NULL OR ST_IsEmpty(geom);
    IF bad > 0 THEN
        RAISE EXCEPTION '% rows with invalid code, empty name or empty geometry', bad;
    END IF;

    SELECT count(*) - count(DISTINCT ibge_code) INTO bad FROM mesh_in;
    IF bad > 0 THEN
        RAISE EXCEPTION '% duplicated IBGE codes', bad;
    END IF;

    SELECT count(*) INTO bad FROM mesh_in
    WHERE substr(ibge_code, 1, 2)::smallint <> uf_code
       OR uf_code NOT IN (SELECT uf_code FROM ld_core.state);
    IF bad > 0 THEN
        RAISE EXCEPTION '% rows whose UF does not match the IBGE code', bad;
    END IF;

    -- A national mesh must cover all 27 federative units.
    IF min_count >= 5000 AND (SELECT count(DISTINCT uf_code) FROM mesh_in) <> 27 THEN
        RAISE EXCEPTION 'national mesh does not cover the 27 UFs';
    END IF;
END;
$checks$;

-- Swap: municipalities absent from the new edition are removed (e.g. merged),
-- existing ones are updated, new ones inserted.
DELETE FROM ld_core.municipality
WHERE ibge_code NOT IN (SELECT ibge_code FROM mesh_in);

INSERT INTO ld_core.municipality AS m
    (ibge_code, name, name_search, uf_code, area_km2, geom, mesh_edition,
     snapshot_id, loaded_at)
SELECT
    ibge_code, name, ld_api.search_key(name), uf_code, area_km2, geom,
    :'mesh_edition', nullif(:'snapshot_id', '')::uuid, now()
FROM mesh_in
ON CONFLICT (ibge_code) DO UPDATE SET
    name = EXCLUDED.name,
    name_search = EXCLUDED.name_search,
    uf_code = EXCLUDED.uf_code,
    area_km2 = EXCLUDED.area_km2,
    geom = EXCLUDED.geom,
    mesh_edition = EXCLUDED.mesh_edition,
    snapshot_id = EXCLUDED.snapshot_id,
    loaded_at = EXCLUDED.loaded_at;

COMMIT;

ANALYZE ld_core.municipality;
SELECT count(*) AS municipalities, count(DISTINCT uf_code) AS ufs
FROM ld_core.municipality;
