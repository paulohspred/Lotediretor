-- LoteDiretor Brasil — Phase 6: national restriction layers
BEGIN;

CREATE SCHEMA IF NOT EXISTS ld_stage;

CREATE TABLE IF NOT EXISTS ld_core.restriction_layer (
    layer_key text PRIMARY KEY,
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    theme text NOT NULL CHECK (theme IN (
        'INDIGENOUS_LAND','CONSERVATION_UNIT','MINING_PROCESS',
        'HYDROGRAPHY','HYDROGRAPHIC_BASIN','DEFORESTATION',
        'TRANSMISSION_LINE','SUBSTATION','CULTURAL_HERITAGE',
        'GEOLOGY','GEOLOGICAL_RISK'
    )),
    authority text NOT NULL,
    source_url text NOT NULL,
    source_format text NOT NULL,
    license text,
    status text NOT NULL DEFAULT 'NOT_LOADED' CHECK (status IN (
        'NOT_LOADED','ACTIVE','NOT_AVAILABLE_SPATIAL','SOURCE_UNAVAILABLE','FAILED_VALIDATION'
    )),
    current_snapshot_id uuid REFERENCES ld_catalog.snapshot(snapshot_id),
    feature_count bigint NOT NULL DEFAULT 0 CHECK (feature_count >= 0),
    source_updated_at timestamptz,
    loaded_at timestamptz,
    notes text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ld_core.restriction_feature (
    restriction_feature_id bigserial PRIMARY KEY,
    layer_key text NOT NULL REFERENCES ld_core.restriction_layer(layer_key),
    snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
    upstream_key text NOT NULL,
    label text,
    category text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    geom geometry(Geometry, 4674) NOT NULL,
    captured_at timestamptz NOT NULL,
    UNIQUE (layer_key, snapshot_id, upstream_key),
    CHECK (ST_IsValid(geom))
);

CREATE INDEX IF NOT EXISTS restriction_feature_geom_gix
    ON ld_core.restriction_feature USING gist (geom);
CREATE INDEX IF NOT EXISTS restriction_feature_layer_snapshot_idx
    ON ld_core.restriction_feature (layer_key, snapshot_id);
CREATE INDEX IF NOT EXISTS restriction_layer_status_idx
    ON ld_core.restriction_layer (status, theme);

CREATE OR REPLACE VIEW ld_api.current_restriction_feature AS
SELECT f.restriction_feature_id, f.layer_key, l.theme, l.authority,
       l.source_url, l.license, l.source_updated_at, l.loaded_at,
       f.upstream_key, f.label, f.category, f.attributes, f.geom,
       f.captured_at, f.snapshot_id
FROM ld_core.restriction_feature f
JOIN ld_core.restriction_layer l
  ON l.layer_key = f.layer_key
 AND l.current_snapshot_id = f.snapshot_id
WHERE l.status = 'ACTIVE';

CREATE OR REPLACE FUNCTION ld_api.restrictions_for_geometry(
    p_geom geometry,
    p_max_distance_m double precision DEFAULT 5000
)
RETURNS TABLE (
    layer_key text,
    theme text,
    authority text,
    source_url text,
    license text,
    source_updated_at timestamptz,
    loaded_at timestamptz,
    upstream_key text,
    label text,
    category text,
    intersects boolean,
    distance_m double precision,
    attributes jsonb
)
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    WITH g AS (
        SELECT ST_CollectionExtract(ST_MakeValid(ST_Force2D(p_geom)), 3) AS polygon_geom,
               ST_PointOnSurface(ST_MakeValid(ST_Force2D(p_geom))) AS point_geom
    ),
    candidates AS (
        SELECT f.*, g.polygon_geom, g.point_geom,
               CASE
                 WHEN NOT ST_IsEmpty(g.polygon_geom)
                   THEN ST_Intersects(f.geom, g.polygon_geom)
                 ELSE ST_Intersects(f.geom, g.point_geom)
               END AS hit,
               ST_Distance(
                 f.geom::geography,
                 CASE
                   WHEN NOT ST_IsEmpty(g.polygon_geom) THEN g.polygon_geom::geography
                   ELSE g.point_geom::geography
                 END
               ) AS dist
        FROM ld_api.current_restriction_feature f
        CROSS JOIN g
        WHERE ST_DWithin(
            f.geom::geography,
            CASE
              WHEN NOT ST_IsEmpty(g.polygon_geom) THEN g.polygon_geom::geography
              ELSE g.point_geom::geography
            END,
            greatest(p_max_distance_m, 0)
        )
    ),
    ranked AS (
        SELECT c.*,
               row_number() OVER (
                 PARTITION BY c.layer_key
                 ORDER BY c.hit DESC, c.dist, c.upstream_key
               ) AS rn
        FROM candidates c
    )
    SELECT layer_key, theme, authority, source_url, license,
           source_updated_at, loaded_at, upstream_key, label, category,
           hit, dist, attributes
    FROM ranked
    WHERE rn = 1
    ORDER BY theme, layer_key
$fn$;

CREATE OR REPLACE FUNCTION ld_api.restrictions_for_point(
    p_lng double precision,
    p_lat double precision,
    p_max_distance_m double precision DEFAULT 5000
)
RETURNS TABLE (
    layer_key text,
    theme text,
    authority text,
    source_url text,
    license text,
    source_updated_at timestamptz,
    loaded_at timestamptz,
    upstream_key text,
    label text,
    category text,
    intersects boolean,
    distance_m double precision,
    attributes jsonb
)
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    SELECT *
    FROM ld_api.restrictions_for_geometry(
        ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4674),
        p_max_distance_m
    )
$fn$;

DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT SELECT ON ld_core.restriction_layer, ld_core.restriction_feature TO %I', app_role);
        EXECUTE format('GRANT SELECT ON ld_api.current_restriction_feature TO %I', app_role);
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE ld_core.restriction_feature_restriction_feature_id_seq TO %I', app_role);
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION ld_api.restrictions_for_geometry(geometry, double precision), ld_api.restrictions_for_point(double precision, double precision, double precision) TO %I',
            app_role
        );
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMIT;