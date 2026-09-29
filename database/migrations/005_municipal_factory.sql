-- LoteDiretor Brasil — municipal factory (Phase 3)
--
-- Municipal layers (parcels, zoning) harvested by tools/factory/harvest.py
-- from each municipality's own GIS (ArcGIS REST / OGC WFS / downloads),
-- normalized to one national schema. Onboarding a city is a reviewed JSON
-- spec in data/connectors/municipal/, not new code (Blueprint §7, §19).

BEGIN;

CREATE TABLE IF NOT EXISTS ld_catalog.municipal_layer_load (
    load_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ibge_code char(7) NOT NULL REFERENCES ld_core.municipality(ibge_code),
    role text NOT NULL CHECK (role IN ('parcels', 'zoning')),
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
    spec_sha256 text NOT NULL CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),
    feature_count integer NOT NULL CHECK (feature_count >= 0),
    inside_municipality_ratio numeric(5, 4) NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    is_current boolean NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX IF NOT EXISTS municipal_layer_load_current_idx
    ON ld_catalog.municipal_layer_load (ibge_code, role)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS ld_domain.municipal_parcel (
    parcel_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    load_id uuid NOT NULL REFERENCES ld_catalog.municipal_layer_load(load_id)
        ON DELETE CASCADE,
    ibge_code char(7) NOT NULL,
    upstream_key text NOT NULL,
    fiscal_reference text,
    street text,
    house_number text,
    neighborhood text,
    land_area_m2 numeric(14, 2),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    geom geometry(MultiPolygon, 4674) NOT NULL,
    CHECK (ST_IsValid(geom))
);

CREATE INDEX IF NOT EXISTS municipal_parcel_geom_gix
    ON ld_domain.municipal_parcel USING gist (geom);
CREATE INDEX IF NOT EXISTS municipal_parcel_ref_idx
    ON ld_domain.municipal_parcel (ibge_code, fiscal_reference);

CREATE TABLE IF NOT EXISTS ld_domain.municipal_zone (
    zone_feature_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    load_id uuid NOT NULL REFERENCES ld_catalog.municipal_layer_load(load_id)
        ON DELETE CASCADE,
    ibge_code char(7) NOT NULL,
    upstream_key text NOT NULL,
    zone_code text NOT NULL,
    zone_name text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    geom geometry(MultiPolygon, 4674) NOT NULL,
    CHECK (ST_IsValid(geom))
);

CREATE INDEX IF NOT EXISTS municipal_zone_geom_gix
    ON ld_domain.municipal_zone USING gist (geom);

-- Current parcel containing a point, from the current load only.
CREATE OR REPLACE FUNCTION ld_api.municipal_parcel_at(
    p_ibge char(7),
    p_lng double precision,
    p_lat double precision
)
RETURNS SETOF ld_domain.municipal_parcel
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    SELECT p.*
    FROM ld_domain.municipal_parcel p
    JOIN ld_catalog.municipal_layer_load l USING (load_id)
    WHERE l.is_current
      AND p.ibge_code = p_ibge
      AND ST_Intersects(p.geom, ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4674))
    ORDER BY ST_Area(p.geom)
    LIMIT 1
$fn$;

-- Zones overlapping a geometry, with the share of the geometry they cover.
CREATE OR REPLACE FUNCTION ld_api.municipal_zones_for(
    p_ibge char(7),
    p_geom geometry
)
RETURNS TABLE (
    zone_code text,
    zone_name text,
    overlap_ratio double precision,
    load_id uuid
)
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    SELECT z.zone_code, z.zone_name,
           CASE WHEN ST_Area(p_geom::geography) > 0
                THEN ST_Area(ST_Intersection(z.geom, p_geom)::geography)
                     / ST_Area(p_geom::geography)
                ELSE 1 END AS overlap_ratio,
           z.load_id
    FROM ld_domain.municipal_zone z
    JOIN ld_catalog.municipal_layer_load l USING (load_id)
    WHERE l.is_current
      AND z.ibge_code = p_ibge
      AND ST_Intersects(z.geom, p_geom)
    ORDER BY overlap_ratio DESC
$fn$;

DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT USAGE ON SCHEMA ld_domain TO %I', app_role);
        EXECUTE format(
            'GRANT SELECT ON ld_catalog.municipal_layer_load, ld_catalog.snapshot, '
            'ld_domain.municipal_parcel, ld_domain.municipal_zone TO %I',
            app_role
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION '
            'ld_api.municipal_parcel_at(char, double precision, double precision), '
            'ld_api.municipal_zones_for(char, geometry) TO %I',
            app_role
        );
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMIT;
