-- LoteDiretor Brasil — Phase 6 hardening without rewriting migration 009.
BEGIN;

CREATE INDEX IF NOT EXISTS restriction_feature_geog_gix
    ON ld_core.restriction_feature USING gist ((geom::geography));

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
    WHERE (hit AND rn <= 20) OR (NOT hit AND rn = 1)
    ORDER BY theme, layer_key, hit DESC, dist, upstream_key
$fn$;

DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format(
            'REVOKE USAGE, SELECT ON SEQUENCE ld_core.restriction_feature_restriction_feature_id_seq FROM %I',
            app_role
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION ld_api.restrictions_for_geometry(geometry, double precision) TO %I',
            app_role
        );
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grant hardening', app_role;
    END IF;
END;
$grants$;

COMMIT;
