-- LoteDiretor Brasil — national territorial base (Phase 2)
--
-- Every point in Brazil must resolve to exactly one municipality using the
-- official IBGE mesh (geocódigo is the canonical key, Blueprint §1). The mesh
-- is loaded by tools/loaders/load_ibge_municipal_mesh.sh and promoted with
-- database/loaders/promote_ibge_municipalities.sql; this migration only
-- creates the structure.

BEGIN;

CREATE EXTENSION IF NOT EXISTS unaccent;

-- Blueprint access class C (authenticated/institutional) was missing.
ALTER TABLE ld_catalog.source DROP CONSTRAINT source_access_class_check;
ALTER TABLE ld_catalog.source ADD CONSTRAINT source_access_class_check CHECK (
    access_class IN (
        'OPEN_REUSABLE',
        'PUBLIC_QUERY_ONLY',
        'AUTHENTICATED_PUBLIC',
        'AUTHENTICATED_INSTITUTIONAL',
        'RESTRICTED_PERSONAL',
        'PAID_ON_DEMAND',
        'USER_PRIVATE',
        'DERIVED'
    )
);

-- Structured coverage keys so "what exists for municipality X" is a query,
-- not a scan of free-text scope fields.
ALTER TABLE ld_catalog.source
    ADD COLUMN IF NOT EXISTS coverage_level text
        CHECK (coverage_level IS NULL OR coverage_level IN
            ('GLOBAL', 'NATIONAL', 'STATE', 'MUNICIPAL', 'SUBMUNICIPAL')),
    ADD COLUMN IF NOT EXISTS uf char(2)
        CHECK (uf IS NULL OR uf ~ '^[A-Z]{2}$'),
    ADD COLUMN IF NOT EXISTS municipality_ibge char(7)
        CHECK (municipality_ibge IS NULL OR municipality_ibge ~ '^[0-9]{7}$'),
    ADD COLUMN IF NOT EXISTS domains text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS source_coverage_idx
    ON ld_catalog.source (coverage_level, uf, municipality_ibge)
    WHERE retired_at IS NULL;

CREATE TABLE IF NOT EXISTS ld_core.state (
    uf_code smallint PRIMARY KEY CHECK (uf_code BETWEEN 11 AND 53),
    uf char(2) NOT NULL UNIQUE CHECK (uf ~ '^[A-Z]{2}$'),
    name text NOT NULL
);

-- IBGE UF codes are stable reference data.
INSERT INTO ld_core.state (uf_code, uf, name) VALUES
    (11, 'RO', 'Rondônia'),
    (12, 'AC', 'Acre'),
    (13, 'AM', 'Amazonas'),
    (14, 'RR', 'Roraima'),
    (15, 'PA', 'Pará'),
    (16, 'AP', 'Amapá'),
    (17, 'TO', 'Tocantins'),
    (21, 'MA', 'Maranhão'),
    (22, 'PI', 'Piauí'),
    (23, 'CE', 'Ceará'),
    (24, 'RN', 'Rio Grande do Norte'),
    (25, 'PB', 'Paraíba'),
    (26, 'PE', 'Pernambuco'),
    (27, 'AL', 'Alagoas'),
    (28, 'SE', 'Sergipe'),
    (29, 'BA', 'Bahia'),
    (31, 'MG', 'Minas Gerais'),
    (32, 'ES', 'Espírito Santo'),
    (33, 'RJ', 'Rio de Janeiro'),
    (35, 'SP', 'São Paulo'),
    (41, 'PR', 'Paraná'),
    (42, 'SC', 'Santa Catarina'),
    (43, 'RS', 'Rio Grande do Sul'),
    (50, 'MS', 'Mato Grosso do Sul'),
    (51, 'MT', 'Mato Grosso'),
    (52, 'GO', 'Goiás'),
    (53, 'DF', 'Distrito Federal')
ON CONFLICT (uf_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS ld_core.municipality (
    ibge_code char(7) PRIMARY KEY CHECK (ibge_code ~ '^[0-9]{7}$'),
    name text NOT NULL,
    name_search text NOT NULL,
    uf_code smallint NOT NULL REFERENCES ld_core.state(uf_code),
    area_km2 numeric(12, 3),
    geom geometry(MultiPolygon, 4674) NOT NULL,
    mesh_edition text NOT NULL,
    snapshot_id uuid REFERENCES ld_catalog.snapshot(snapshot_id),
    loaded_at timestamptz NOT NULL DEFAULT now(),
    CHECK (substr(ibge_code, 1, 2)::smallint = uf_code),
    CHECK (ST_IsValid(geom))
);

CREATE INDEX IF NOT EXISTS municipality_geom_gix
    ON ld_core.municipality USING gist (geom);
CREATE INDEX IF NOT EXISTS municipality_name_search_idx
    ON ld_core.municipality (name_search text_pattern_ops);

-- Point → municipality. ST_Intersects (not Contains) so points exactly on a
-- boundary still resolve; ties are broken deterministically by code.
CREATE OR REPLACE FUNCTION ld_api.resolve_municipality(
    p_lng double precision,
    p_lat double precision
)
RETURNS TABLE (ibge_code char(7), name text, uf char(2))
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    SELECT m.ibge_code, m.name, s.uf
    FROM ld_core.municipality m
    JOIN ld_core.state s USING (uf_code)
    WHERE ST_Intersects(m.geom, ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4674))
    ORDER BY m.ibge_code
    LIMIT 1
$fn$;

-- Normalization used both by the loader and by search queries.
CREATE OR REPLACE FUNCTION ld_api.search_key(p_text text)
RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE
AS $fn$
    SELECT btrim(regexp_replace(lower(unaccent(coalesce(p_text, ''))), '\s+', ' ', 'g'))
$fn$;

-- Which catalogued sources apply to a municipality, by level.
CREATE OR REPLACE VIEW ld_api.municipality_source AS
SELECT
    m.ibge_code,
    src.source_id,
    src.coverage_level,
    src.authority,
    src.source_type,
    src.access_class,
    src.verification_status,
    src.canonical_url,
    src.domains
FROM ld_core.municipality m
JOIN ld_core.state st USING (uf_code)
JOIN ld_catalog.source src
    ON src.retired_at IS NULL
   AND (
        src.coverage_level = 'NATIONAL'
        OR (src.coverage_level = 'STATE' AND src.uf = st.uf)
        OR (src.coverage_level IN ('MUNICIPAL', 'SUBMUNICIPAL')
            AND src.municipality_ibge = m.ibge_code)
   );

COMMENT ON TABLE ld_core.municipality IS
    'Official IBGE municipal mesh in SIRGAS 2000 (EPSG:4674). Loaded as a versioned snapshot; never hand-edited.';
COMMENT ON COLUMN ld_catalog.source.coverage_level IS
    'Territorial reach of the source: NATIONAL applies to every municipality, STATE to its UF, MUNICIPAL/SUBMUNICIPAL to municipality_ibge.';

COMMIT;
