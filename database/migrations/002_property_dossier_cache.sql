-- LoteDiretor Brasil — operational public dossier cache
BEGIN;

CREATE TABLE IF NOT EXISTS ld_api.property_dossier_cache (
    cache_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id) ON DELETE CASCADE,
    municipality_ibge char(7) NOT NULL,
    primary_namespace text NOT NULL,
    primary_identifier text NOT NULL,
    parcel_geom geometry(Geometry, 4674) NOT NULL,
    dossier jsonb NOT NULL,
    dossier_sha256 text NOT NULL CHECK (dossier_sha256 ~ '^[0-9a-f]{64}$'),
    generated_at timestamptz NOT NULL,
    expires_at timestamptz,
    source_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (ST_IsValid(parcel_geom)),
    CHECK (expires_at IS NULL OR expires_at >= generated_at),
    UNIQUE (municipality_ibge, primary_namespace, primary_identifier)
);

CREATE INDEX IF NOT EXISTS property_dossier_cache_geom_gix
    ON ld_api.property_dossier_cache USING gist (parcel_geom);
CREATE INDEX IF NOT EXISTS property_dossier_cache_subject_idx
    ON ld_api.property_dossier_cache (subject_id);
CREATE INDEX IF NOT EXISTS property_dossier_cache_generated_idx
    ON ld_api.property_dossier_cache (municipality_ibge, generated_at DESC);

COMMENT ON TABLE ld_api.property_dossier_cache IS
    'Public-safe property dossier cache. Stores only the already privacy-filtered API response plus parcel geometry and a content hash.';

COMMIT;
