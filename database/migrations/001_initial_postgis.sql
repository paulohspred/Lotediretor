-- LoteDiretor Brasil — initial normalized PostGIS schema
-- Phase G: data model only. No deployment is performed by this migration file.

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS ld_catalog;
CREATE SCHEMA IF NOT EXISTS ld_core;
CREATE SCHEMA IF NOT EXISTS ld_domain;
CREATE SCHEMA IF NOT EXISTS ld_evidence;
CREATE SCHEMA IF NOT EXISTS ld_api;

-- ---------------------------------------------------------------------------
-- Catalog, immutable snapshots and normalized source records
-- ---------------------------------------------------------------------------

CREATE TABLE ld_catalog.source (
    source_id text PRIMARY KEY,
    authority text NOT NULL,
    scope text NOT NULL,
    source_type text NOT NULL,
    access_class text NOT NULL CHECK (
        access_class IN (
            'OPEN_REUSABLE',
            'PUBLIC_QUERY_ONLY',
            'AUTHENTICATED_PUBLIC',
            'RESTRICTED_PERSONAL',
            'PAID_ON_DEMAND',
            'USER_PRIVATE',
            'DERIVED'
        )
    ),
    license text,
    verification_status text NOT NULL,
    canonical_url text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    registered_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz
);

CREATE TABLE ld_catalog.connector (
    connector_id text PRIMARY KEY,
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    kind text NOT NULL,
    mode text NOT NULL,
    approved boolean NOT NULL DEFAULT false,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ld_catalog.snapshot (
    snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    connector_id text REFERENCES ld_catalog.connector(connector_id),
    captured_at timestamptz NOT NULL,
    requested_url text NOT NULL,
    final_url text NOT NULL,
    http_status integer,
    content_type text,
    content_length bigint CHECK (content_length IS NULL OR content_length >= 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    object_key text,
    source_updated_at timestamptz,
    manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, sha256)
);

CREATE INDEX snapshot_source_captured_idx
    ON ld_catalog.snapshot (source_id, captured_at DESC);

CREATE TABLE ld_catalog.normalized_record (
    record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
    upstream_key text NOT NULL,
    record_kind text NOT NULL,
    valid_from timestamptz,
    valid_to timestamptz,
    observed_at timestamptz,
    captured_at timestamptz NOT NULL,
    payload_sha256 text CHECK (
        payload_sha256 IS NULL OR payload_sha256 ~ '^[0-9a-f]{64}$'
    ),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_id, upstream_key, snapshot_id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE INDEX normalized_record_source_kind_idx
    ON ld_catalog.normalized_record (source_id, record_kind);
CREATE INDEX normalized_record_validity_idx
    ON ld_catalog.normalized_record (valid_from, valid_to);

-- ---------------------------------------------------------------------------
-- Property identity: parcel, fiscal unit, building, registry reference, etc.
-- These identities must never be flattened into one identifier.
-- ---------------------------------------------------------------------------

CREATE TABLE ld_core.subject (
    subject_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type text NOT NULL CHECK (
        subject_type IN (
            'URBAN_PARCEL',
            'RURAL_PARCEL',
            'FISCAL_UNIT',
            'BUILDING',
            'CONDOMINIUM_UNIT',
            'PROPERTY_RECORD_REFERENCE',
            'UNRESOLVED_PROPERTY'
        )
    ),
    municipality_ibge char(7),
    canonical_geom geometry(Geometry, 4674),
    canonical_point geometry(Point, 4674),
    geom_method text,
    geom_confidence text CHECK (
        geom_confidence IS NULL OR
        geom_confidence IN (
            'CONFIRMED','SUPPORTED','INDICATIVE','UNKNOWN','CONFLICTING'
        )
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    CHECK (municipality_ibge IS NULL OR municipality_ibge ~ '^[0-9]{7}$'),
    CHECK (canonical_geom IS NULL OR ST_IsValid(canonical_geom))
);

CREATE INDEX subject_geom_gix
    ON ld_core.subject USING gist (canonical_geom);
CREATE INDEX subject_point_gix
    ON ld_core.subject USING gist (canonical_point);
CREATE INDEX subject_municipality_idx
    ON ld_core.subject (municipality_ibge, subject_type);

CREATE TABLE ld_core.subject_identifier (
    identifier_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    namespace text NOT NULL,
    identifier_value text NOT NULL,
    issuer text,
    access_class text NOT NULL DEFAULT 'PUBLIC_QUERY_ONLY',
    valid_from timestamptz,
    valid_to timestamptz,
    source_record_id uuid REFERENCES ld_catalog.normalized_record(record_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (namespace, identifier_value, subject_id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE INDEX subject_identifier_lookup_idx
    ON ld_core.subject_identifier (namespace, identifier_value);

CREATE TABLE ld_core.subject_relation (
    relation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    to_subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    relation_type text NOT NULL CHECK (
        relation_type IN (
            'REPRESENTS_SAME_REAL_WORLD_PROPERTY',
            'FISCAL_UNIT_OF',
            'BUILDING_ON',
            'CONDOMINIUM_UNIT_OF',
            'REGISTRY_REFERENCE_FOR',
            'DERIVED_FROM',
            'SUPERSEDES',
            'OTHER'
        )
    ),
    confidence text NOT NULL CHECK (
        confidence IN (
            'CONFIRMED','SUPPORTED','INDICATIVE','UNKNOWN','CONFLICTING'
        )
    ),
    source_record_id uuid REFERENCES ld_catalog.normalized_record(record_id),
    valid_from timestamptz,
    valid_to timestamptz,
    notes text,
    CHECK (from_subject_id <> to_subject_id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE INDEX subject_relation_from_idx
    ON ld_core.subject_relation (from_subject_id, relation_type);
CREATE INDEX subject_relation_to_idx
    ON ld_core.subject_relation (to_subject_id, relation_type);

CREATE TABLE ld_core.address (
    address_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id),
    source_record_id uuid REFERENCES ld_catalog.normalized_record(record_id),
    address_role text NOT NULL DEFAULT 'PROPERTY',
    street text,
    number text,
    complement text,
    neighborhood text,
    postal_code text,
    municipality_ibge char(7),
    normalized_text text,
    geom geometry(Point, 4674),
    confidence text CHECK (
        confidence IS NULL OR
        confidence IN (
            'CONFIRMED','SUPPORTED','INDICATIVE','UNKNOWN','CONFLICTING'
        )
    ),
    valid_from timestamptz,
    valid_to timestamptz,
    CHECK (geom IS NULL OR ST_IsValid(geom))
);

CREATE INDEX address_geom_gix ON ld_core.address USING gist (geom);
CREATE INDEX address_subject_idx ON ld_core.address (subject_id);

CREATE TABLE ld_core.parcel_geometry_version (
    parcel_geometry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    geom geometry(MultiPolygon, 4674) NOT NULL,
    source_crs text,
    area_source_m2 numeric,
    area_calculated_m2 numeric,
    perimeter_calculated_m numeric,
    geometry_role text NOT NULL DEFAULT 'CADASTRAL',
    valid_from timestamptz,
    valid_to timestamptz,
    CHECK (ST_IsValid(geom)),
    CHECK (area_source_m2 IS NULL OR area_source_m2 >= 0),
    CHECK (area_calculated_m2 IS NULL OR area_calculated_m2 >= 0),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE INDEX parcel_geometry_gix
    ON ld_core.parcel_geometry_version USING gist (geom);
CREATE INDEX parcel_geometry_subject_idx
    ON ld_core.parcel_geometry_version (subject_id, valid_from DESC);

CREATE TABLE ld_core.building (
    building_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id),
    parcel_subject_id uuid REFERENCES ld_core.subject(subject_id),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    geom geometry(MultiPolygon, 4674),
    footprint_area_m2 numeric,
    built_area_m2 numeric,
    floors numeric,
    height_m numeric,
    construction_year integer,
    use_class text,
    status text,
    valid_from timestamptz,
    valid_to timestamptz,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (geom IS NULL OR ST_IsValid(geom)),
    CHECK (footprint_area_m2 IS NULL OR footprint_area_m2 >= 0),
    CHECK (built_area_m2 IS NULL OR built_area_m2 >= 0)
);

CREATE INDEX building_geom_gix ON ld_core.building USING gist (geom);
CREATE INDEX building_parcel_idx ON ld_core.building (parcel_subject_id);

-- ---------------------------------------------------------------------------
-- Generic assertions and evidence. This is the report-level truth layer.
-- ---------------------------------------------------------------------------

CREATE TABLE ld_evidence.assertion (
    assertion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    section_id text NOT NULL,
    field_key text NOT NULL,
    assertion_status text NOT NULL CHECK (
        assertion_status IN (
            'AVAILABLE',
            'NOT_AVAILABLE',
            'NOT_PUBLICLY_AVAILABLE',
            'QUERY_ONLY',
            'REQUIRES_USER_DOCUMENT',
            'RESTRICTED',
            'NOT_APPLICABLE',
            'UNKNOWN',
            'CONFLICTING_EVIDENCE'
        )
    ),
    assertion_class text NOT NULL CHECK (
        assertion_class IN (
            'OFFICIAL_FACT',
            'OFFICIAL_QUERY_RESULT',
            'USER_DOCUMENT_FACT',
            'DERIVED_ANALYSIS',
            'INDICATIVE_CONTEXT',
            'UNKNOWN'
        )
    ),
    value jsonb,
    unit text,
    confidence text NOT NULL CHECK (
        confidence IN (
            'CONFIRMED','SUPPORTED','INDICATIVE','UNKNOWN','CONFLICTING'
        )
    ),
    access_class text NOT NULL CHECK (
        access_class IN (
            'OPEN_REUSABLE',
            'PUBLIC_QUERY_ONLY',
            'AUTHENTICATED_PUBLIC',
            'USER_PRIVATE',
            'RESTRICTED',
            'DERIVED'
        )
    ),
    source_record_id uuid REFERENCES ld_catalog.normalized_record(record_id),
    applicable_geom geometry(Geometry, 4674),
    method text,
    observed_at timestamptz,
    valid_from timestamptz,
    valid_to timestamptz,
    captured_at timestamptz NOT NULL,
    public_release_allowed boolean NOT NULL DEFAULT false,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    CHECK (applicable_geom IS NULL OR ST_IsValid(applicable_geom)),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK (
        assertion_class <> 'DERIVED_ANALYSIS'
        OR (method IS NOT NULL AND access_class = 'DERIVED')
    ),
    CHECK (
        assertion_status <> 'AVAILABLE'
        OR value IS NOT NULL
    )
);

CREATE INDEX assertion_subject_section_idx
    ON ld_evidence.assertion (subject_id, section_id, field_key);
CREATE INDEX assertion_geom_gix
    ON ld_evidence.assertion USING gist (applicable_geom);
CREATE INDEX assertion_source_record_idx
    ON ld_evidence.assertion (source_record_id);

CREATE TABLE ld_evidence.assertion_lineage (
    assertion_id uuid NOT NULL REFERENCES ld_evidence.assertion(assertion_id) ON DELETE CASCADE,
    upstream_assertion_id uuid NOT NULL REFERENCES ld_evidence.assertion(assertion_id),
    relation_type text NOT NULL DEFAULT 'DERIVED_FROM',
    PRIMARY KEY (assertion_id, upstream_assertion_id),
    CHECK (assertion_id <> upstream_assertion_id)
);

CREATE TABLE ld_evidence.unknown (
    unknown_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    section_id text NOT NULL,
    field_key text NOT NULL,
    reason text NOT NULL CHECK (
        reason IN (
            'SOURCE_NOT_FOUND',
            'NOT_PUBLIC',
            'AUTH_REQUIRED',
            'CAPTCHA_OR_MANUAL_QUERY',
            'LICENSE_UNCLEAR',
            'SCHEMA_UNMAPPED',
            'GEOMETRY_UNRESOLVED',
            'CONFLICTING_SOURCES',
            'OUTDATED_SOURCE',
            'USER_DOCUMENT_NEEDED',
            'TECHNICAL_CONFIRMATION_REQUIRED',
            'OTHER'
        )
    ),
    next_action text NOT NULL,
    source_id text REFERENCES ld_catalog.source(source_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE INDEX unknown_subject_idx
    ON ld_evidence.unknown (subject_id, section_id, resolved_at);

-- ---------------------------------------------------------------------------
-- Typed normalized domains. Each row retains a normalized_record provenance FK.
-- ---------------------------------------------------------------------------

CREATE TABLE ld_domain.planning_area (
    planning_area_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    municipality_ibge char(7) NOT NULL,
    area_type text NOT NULL,
    code text,
    name text,
    legal_act text,
    geom geometry(MultiPolygon, 4674) NOT NULL,
    valid_from timestamptz,
    valid_to timestamptz,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (ST_IsValid(geom))
);

CREATE INDEX planning_area_gix
    ON ld_domain.planning_area USING gist (geom);
CREATE INDEX planning_area_city_type_idx
    ON ld_domain.planning_area (municipality_ibge, area_type);

CREATE TABLE ld_domain.planning_parameter (
    planning_parameter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    planning_area_id uuid NOT NULL REFERENCES ld_domain.planning_area(planning_area_id) ON DELETE CASCADE,
    parameter_key text NOT NULL,
    numeric_value numeric,
    text_value text,
    unit text,
    condition_text text,
    legal_citation text,
    valid_from timestamptz,
    valid_to timestamptz,
    CHECK (numeric_value IS NOT NULL OR text_value IS NOT NULL)
);

CREATE INDEX planning_parameter_area_key_idx
    ON ld_domain.planning_parameter (planning_area_id, parameter_key);

CREATE TABLE ld_domain.fiscal_record (
    fiscal_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    tax_year integer,
    fiscal_identifier text,
    land_area_m2 numeric,
    built_area_m2 numeric,
    land_assessed_value_brl numeric,
    building_assessed_value_brl numeric,
    total_assessed_value_brl numeric,
    tax_assessed_brl numeric,
    tax_rate numeric,
    pgv_land_unit_value_brl_m2 numeric,
    pgv_building_unit_value_brl_m2 numeric,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX fiscal_record_subject_year_idx
    ON ld_domain.fiscal_record (subject_id, tax_year DESC);

CREATE TABLE ld_domain.transaction_record (
    transaction_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    transaction_date date,
    transaction_type text,
    transmitted_share numeric,
    declared_value_brl numeric,
    assessed_value_brl numeric,
    tax_paid_brl numeric,
    location_geom geometry(Point, 4674),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (location_geom IS NULL OR ST_IsValid(location_geom))
);

CREATE INDEX transaction_subject_date_idx
    ON ld_domain.transaction_record (subject_id, transaction_date DESC);
CREATE INDEX transaction_geom_gix
    ON ld_domain.transaction_record USING gist (location_geom);

CREATE TABLE ld_domain.permit_event (
    permit_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    permit_number text,
    process_number text,
    permit_type text NOT NULL,
    status text,
    issue_date date,
    completion_date date,
    licensed_area_m2 numeric,
    geom geometry(Geometry, 4674),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (geom IS NULL OR ST_IsValid(geom))
);

CREATE INDEX permit_subject_date_idx
    ON ld_domain.permit_event (subject_id, issue_date DESC);
CREATE INDEX permit_geom_gix ON ld_domain.permit_event USING gist (geom);

CREATE TABLE ld_domain.spatial_constraint (
    constraint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    municipality_ibge char(7),
    category text NOT NULL CHECK (
        category IN ('ENVIRONMENT','RISK','TRANSPORT','OTHER')
    ),
    constraint_type text NOT NULL,
    name text,
    legal_act text,
    severity text,
    geom geometry(Geometry, 4674) NOT NULL,
    valid_from timestamptz,
    valid_to timestamptz,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (ST_IsValid(geom))
);

CREATE INDEX spatial_constraint_gix
    ON ld_domain.spatial_constraint USING gist (geom);
CREATE INDEX spatial_constraint_category_idx
    ON ld_domain.spatial_constraint (category, constraint_type);

CREATE TABLE ld_domain.heritage_feature (
    heritage_feature_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    municipality_ibge char(7),
    protection_level text NOT NULL CHECK (
        protection_level IN ('FEDERAL','STATE','MUNICIPAL','MULTI_LEVEL')
    ),
    protection_status text NOT NULL CHECK (
        protection_status IN (
            'TOMBED',
            'PENDING_PROTECTION',
            'SURROUNDING_AREA',
            'PROTECTED_AREA',
            'ARCHAEOLOGICAL',
            'REGISTERED',
            'OTHER'
        )
    ),
    authority text NOT NULL,
    name text,
    process_number text,
    legal_act text,
    publication_date date,
    approval_authority text,
    geom geometry(Geometry, 4674),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (geom IS NULL OR ST_IsValid(geom))
);

CREATE INDEX heritage_feature_gix
    ON ld_domain.heritage_feature USING gist (geom);
CREATE INDEX heritage_city_status_idx
    ON ld_domain.heritage_feature (municipality_ibge, protection_level, protection_status);

CREATE TABLE ld_domain.utility_context (
    utility_context_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid REFERENCES ld_core.subject(subject_id),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    service_type text NOT NULL CHECK (
        service_type IN (
            'ELECTRICITY','GAS','WATER','SEWER','DRAINAGE',
            'TELECOM','PUBLIC_LIGHTING'
        )
    ),
    provider_source_id text REFERENCES ld_catalog.source(source_id),
    status text NOT NULL CHECK (
        status IN (
            'UNKNOWN',
            'PROVIDER_IDENTIFIED',
            'CONCESSION_AREA',
            'NETWORK_OBSERVED_NEARBY',
            'SERVICE_REPORTED_IN_AREA',
            'TECHNICAL_AVAILABILITY_CONFIRMED',
            'CONNECTION_REQUEST_REQUIRED',
            'TECHNICAL_DRAWING_REQUIRED',
            'NOT_AVAILABLE',
            'RESTRICTED_INFORMATION'
        )
    ),
    distance_m numeric,
    network_geom geometry(Geometry, 4674),
    valid_from timestamptz,
    valid_to timestamptz,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (distance_m IS NULL OR distance_m >= 0),
    CHECK (network_geom IS NULL OR ST_IsValid(network_geom))
);

CREATE INDEX utility_context_subject_idx
    ON ld_domain.utility_context (subject_id, service_type);
CREATE INDEX utility_network_gix
    ON ld_domain.utility_context USING gist (network_geom);

CREATE TABLE ld_domain.public_event (
    public_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    event_type text NOT NULL,
    lifecycle_stage text,
    municipality_ibge char(7),
    title text,
    event_date date,
    responsible_organization text,
    planned_value_brl numeric,
    executed_value_brl numeric,
    progress_percent numeric,
    geom geometry(Geometry, 4674),
    address_text text,
    match_method text,
    match_confidence text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100),
    CHECK (geom IS NULL OR ST_IsValid(geom))
);

CREATE INDEX public_event_gix
    ON ld_domain.public_event USING gist (geom);
CREATE INDEX public_event_city_date_idx
    ON ld_domain.public_event (municipality_ibge, event_date DESC);

CREATE TABLE ld_domain.imagery_asset (
    imagery_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    imagery_type text NOT NULL,
    acquisition_date date,
    resolution_m numeric,
    crs text,
    footprint geometry(Geometry, 4674),
    object_key text,
    external_url text,
    license text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (resolution_m IS NULL OR resolution_m > 0),
    CHECK (footprint IS NULL OR ST_IsValid(footprint))
);

CREATE INDEX imagery_footprint_gix
    ON ld_domain.imagery_asset USING gist (footprint);

CREATE TABLE ld_domain.terrain_asset (
    terrain_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES ld_catalog.normalized_record(record_id),
    terrain_type text NOT NULL CHECK (
        terrain_type IN ('DTM','DSM','LIDAR','DEM','CONTOURS','SURVEY','OTHER')
    ),
    quality_level text NOT NULL CHECK (
        quality_level IN ('T0','T1','T2','T3','T4')
    ),
    resolution_m numeric,
    horizontal_crs text,
    vertical_datum text,
    footprint geometry(Geometry, 4674),
    object_key text,
    external_url text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (resolution_m IS NULL OR resolution_m > 0),
    CHECK (footprint IS NULL OR ST_IsValid(footprint))
);

CREATE INDEX terrain_footprint_gix
    ON ld_domain.terrain_asset USING gist (footprint);

-- ---------------------------------------------------------------------------
-- Public-safe read model foundation. API implementation comes later.
-- ---------------------------------------------------------------------------

CREATE VIEW ld_api.public_assertion AS
SELECT
    a.assertion_id,
    a.subject_id,
    a.section_id,
    a.field_key,
    a.assertion_status,
    a.assertion_class,
    a.value,
    a.unit,
    a.confidence,
    a.access_class,
    a.applicable_geom,
    a.method,
    a.observed_at,
    a.valid_from,
    a.valid_to,
    a.captured_at,
    a.warnings
FROM ld_evidence.assertion a
WHERE
    a.public_release_allowed = true
    AND a.access_class IN ('OPEN_REUSABLE','PUBLIC_QUERY_ONLY','DERIVED');

COMMENT ON SCHEMA ld_catalog IS
    'Source registry, connectors, immutable snapshots and normalized upstream records.';
COMMENT ON SCHEMA ld_core IS
    'Property subjects and identity reconciliation without flattening fiscal/parcel/registry/building identities.';
COMMENT ON SCHEMA ld_domain IS
    'Typed normalized geospatial/fiscal/legal/infrastructure datasets with source-record provenance.';
COMMENT ON SCHEMA ld_evidence IS
    'Property-level assertions, lineage and explicit unknowns used by professional reports.';
COMMENT ON SCHEMA ld_api IS
    'Public-safe read-model foundation; not the final API implementation.';

COMMENT ON VIEW ld_api.public_assertion IS
    'Only assertions explicitly approved for public release; L4/private data is excluded by construction.';

COMMIT;
