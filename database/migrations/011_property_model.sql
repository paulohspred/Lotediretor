-- LoteDiretor Brasil — Phase 7: CIB and richer property model
BEGIN;

ALTER TABLE ld_domain.municipal_parcel
    ADD COLUMN IF NOT EXISTS cib text,
    ADD COLUMN IF NOT EXISTS sector text,
    ADD COLUMN IF NOT EXISTS block text,
    ADD COLUMN IF NOT EXISTS lot text,
    ADD COLUMN IF NOT EXISTS unit text,
    ADD COLUMN IF NOT EXISTS postal_code text,
    ADD COLUMN IF NOT EXISTS built_area_m2 numeric(14,2),
    ADD COLUMN IF NOT EXISTS frontage_m numeric(12,2),
    ADD COLUMN IF NOT EXISTS cadastral_use text,
    ADD COLUMN IF NOT EXISTS cadastral_status text;

CREATE INDEX IF NOT EXISTS municipal_parcel_cib_idx
    ON ld_domain.municipal_parcel (ibge_code, cib)
    WHERE cib IS NOT NULL;
CREATE INDEX IF NOT EXISTS municipal_parcel_sector_block_lot_idx
    ON ld_domain.municipal_parcel (ibge_code, sector, block, lot);

CREATE TABLE IF NOT EXISTS ld_domain.municipal_parcel_field_provenance (
    parcel_id uuid NOT NULL REFERENCES ld_domain.municipal_parcel(parcel_id) ON DELETE CASCADE,
    field_name text NOT NULL,
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
    observed_at timestamptz NOT NULL,
    confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    upstream_field text NOT NULL,
    PRIMARY KEY (parcel_id, field_name)
);

CREATE INDEX IF NOT EXISTS municipal_parcel_field_provenance_snapshot_idx
    ON ld_domain.municipal_parcel_field_provenance(snapshot_id);

CREATE OR REPLACE FUNCTION ld_api.municipal_parcel_search(
    p_ibge char(7),
    p_query text,
    p_limit integer DEFAULT 10
)
RETURNS TABLE (
    parcel_id uuid,
    fiscal_reference text,
    cib text,
    street text,
    house_number text,
    lat double precision,
    lng double precision,
    matched_field text
)
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    WITH k AS (
        SELECT replace(replace(replace(ld_api.search_key(p_query),
               '\', '\\'), '%', '\%'), '_', '\_') AS key
    )
    SELECT p.parcel_id, p.fiscal_reference, p.cib, p.street, p.house_number,
           ST_Y(ST_PointOnSurface(p.geom)) AS lat,
           ST_X(ST_PointOnSurface(p.geom)) AS lng,
           CASE
             WHEN ld_api.search_key(coalesce(p.cib,'')) LIKE k.key || '%' THEN 'CIB'
             WHEN ld_api.search_key(coalesce(p.fiscal_reference,'')) LIKE k.key || '%' THEN 'INSCRICAO'
             ELSE 'ENDERECO'
           END AS matched_field
    FROM ld_domain.municipal_parcel p
    JOIN ld_catalog.municipal_layer_load l USING (load_id)
    CROSS JOIN k
    WHERE l.is_current
      AND p.ibge_code = p_ibge
      AND (
        ld_api.search_key(coalesce(p.cib,'')) LIKE k.key || '%'
        OR ld_api.search_key(coalesce(p.fiscal_reference,'')) LIKE k.key || '%'
        OR ld_api.search_key(coalesce(p.street,'') || ' ' || coalesce(p.house_number,''))
           LIKE '%' || k.key || '%'
      )
    ORDER BY
      CASE
        WHEN ld_api.search_key(coalesce(p.cib,'')) = k.key THEN 0
        WHEN ld_api.search_key(coalesce(p.fiscal_reference,'')) = k.key THEN 1
        ELSE 2
      END,
      p.fiscal_reference NULLS LAST
    LIMIT least(greatest(p_limit,1),50)
$fn$;

DO $grants$
DECLARE
    app_role text := coalesce(nullif(current_setting('lotediretor.app_role', true), ''), 'sentinelx');
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT SELECT ON ld_domain.municipal_parcel_field_provenance TO %I', app_role);
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION ld_api.municipal_parcel_search(char,text,integer) TO %I',
            app_role
        );
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMIT;
