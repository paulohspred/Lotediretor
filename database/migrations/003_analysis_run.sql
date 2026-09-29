-- LoteDiretor Brasil — immutable analysis runs
BEGIN;

CREATE SCHEMA IF NOT EXISTS ld_analysis;

CREATE TABLE IF NOT EXISTS ld_analysis.analysis_run (
    analysis_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id uuid NOT NULL REFERENCES ld_core.subject(subject_id),
    municipality_ibge char(7) NOT NULL,
    primary_namespace text NOT NULL,
    primary_identifier text NOT NULL,
    analysis_date date,
    engine_version text NOT NULL,
    contract_version text NOT NULL,
    lineage_status text NOT NULL CHECK (
        lineage_status IN (
            'AGGREGATED_RUNTIME_SNAPSHOT',
            'SOURCE_SNAPSHOTS_COMPLETE'
        )
    ),
    frozen_input jsonb NOT NULL,
    frozen_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
    frozen_calculations jsonb NOT NULL DEFAULT '{}'::jsonb,
    frozen_findings jsonb NOT NULL DEFAULT '[]'::jsonb,
    result_payload jsonb NOT NULL,
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    result_sha256 text NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
    run_fingerprint text NOT NULL UNIQUE CHECK (run_fingerprint ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'BUILDING' CHECK (
        status IN ('BUILDING', 'COMPLETED')
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (
        (status='BUILDING' AND completed_at IS NULL)
        OR
        (status='COMPLETED' AND completed_at IS NOT NULL
         AND completed_at >= created_at)
    )
);

CREATE INDEX IF NOT EXISTS analysis_run_subject_created_idx
    ON ld_analysis.analysis_run(subject_id, created_at DESC);
CREATE INDEX IF NOT EXISTS analysis_run_identifier_idx
    ON ld_analysis.analysis_run(
        municipality_ibge, primary_namespace, primary_identifier, created_at DESC
    );

CREATE TABLE IF NOT EXISTS ld_analysis.analysis_input (
    analysis_run_id uuid NOT NULL
        REFERENCES ld_analysis.analysis_run(analysis_run_id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
    normalized_record_id uuid
        REFERENCES ld_catalog.normalized_record(record_id),
    source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
    input_role text NOT NULL CHECK (
        input_role IN (
            'PRIMARY_PROPERTY_SNAPSHOT',
            'CONTEXT_SNAPSHOT',
            'LEGAL_SNAPSHOT',
            'DERIVED_INPUT'
        )
    ),
    PRIMARY KEY (analysis_run_id, snapshot_id, input_role)
);

CREATE INDEX IF NOT EXISTS analysis_input_snapshot_idx
    ON ld_analysis.analysis_input(snapshot_id);
CREATE INDEX IF NOT EXISTS analysis_input_record_idx
    ON ld_analysis.analysis_input(normalized_record_id);

CREATE TABLE IF NOT EXISTS ld_analysis.finding (
    finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id uuid NOT NULL
        REFERENCES ld_analysis.analysis_run(analysis_run_id) ON DELETE CASCADE,
    assertion_id uuid REFERENCES ld_evidence.assertion(assertion_id),
    section_id text NOT NULL,
    field_key text NOT NULL,
    value jsonb,
    unit text,
    confidence text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (analysis_run_id, assertion_id),
    CHECK (assertion_id IS NOT NULL OR value IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS finding_run_section_idx
    ON ld_analysis.finding(analysis_run_id, section_id);

CREATE TABLE IF NOT EXISTS ld_analysis.report_snapshot (
    report_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id uuid NOT NULL UNIQUE
        REFERENCES ld_analysis.analysis_run(analysis_run_id) ON DELETE CASCADE,
    report_payload jsonb NOT NULL,
    report_sha256 text NOT NULL CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION ld_analysis.protect_run()
RETURNS trigger
LANGUAGE plpgsql
AS $ld$
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'immutable analysis run cannot be deleted';
    END IF;

    IF OLD.status='BUILDING'
       AND NEW.status='COMPLETED'
       AND (to_jsonb(NEW) - ARRAY['status','completed_at'])
           = (to_jsonb(OLD) - ARRAY['status','completed_at'])
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'immutable analysis run can only be sealed once';
END;
$ld$;

CREATE OR REPLACE FUNCTION ld_analysis.protect_run_child()
RETURNS trigger
LANGUAGE plpgsql
AS $ld$
DECLARE
    run_status text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'immutable analysis artifact cannot be updated or deleted';
    END IF;

    SELECT status INTO run_status
    FROM ld_analysis.analysis_run
    WHERE analysis_run_id=NEW.analysis_run_id;

    IF run_status <> 'BUILDING' THEN
        RAISE EXCEPTION 'completed analysis run cannot receive new artifacts';
    END IF;
    RETURN NEW;
END;
$ld$;

DROP TRIGGER IF EXISTS analysis_run_immutable
    ON ld_analysis.analysis_run;
CREATE TRIGGER analysis_run_immutable
BEFORE UPDATE OR DELETE ON ld_analysis.analysis_run
FOR EACH ROW EXECUTE FUNCTION ld_analysis.protect_run();

DROP TRIGGER IF EXISTS analysis_input_immutable
    ON ld_analysis.analysis_input;
CREATE TRIGGER analysis_input_immutable
BEFORE INSERT OR UPDATE OR DELETE ON ld_analysis.analysis_input
FOR EACH ROW EXECUTE FUNCTION ld_analysis.protect_run_child();

DROP TRIGGER IF EXISTS finding_immutable
    ON ld_analysis.finding;
CREATE TRIGGER finding_immutable
BEFORE INSERT OR UPDATE OR DELETE ON ld_analysis.finding
FOR EACH ROW EXECUTE FUNCTION ld_analysis.protect_run_child();

DROP TRIGGER IF EXISTS report_snapshot_immutable
    ON ld_analysis.report_snapshot;
CREATE TRIGGER report_snapshot_immutable
BEFORE INSERT OR UPDATE OR DELETE ON ld_analysis.report_snapshot
FOR EACH ROW EXECUTE FUNCTION ld_analysis.protect_run_child();

CREATE OR REPLACE FUNCTION ld_analysis.complete_run(p_analysis_run_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, ld_analysis
AS $ld$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM ld_analysis.analysis_input
        WHERE analysis_run_id=p_analysis_run_id
    ) THEN
        RAISE EXCEPTION 'analysis run has no frozen input';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM ld_analysis.report_snapshot
        WHERE analysis_run_id=p_analysis_run_id
    ) THEN
        RAISE EXCEPTION 'analysis run has no report snapshot';
    END IF;

    UPDATE ld_analysis.analysis_run
    SET status='COMPLETED', completed_at=now()
    WHERE analysis_run_id=p_analysis_run_id
      AND status='BUILDING';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'analysis run not found or already completed';
    END IF;
END;
$ld$;

REVOKE ALL ON FUNCTION ld_analysis.complete_run(uuid) FROM PUBLIC;

-- Grants go to the runtime role only when it exists, so the migration also
-- applies on fresh databases (CI, new environments). The role name is
-- configurable with: SET lotediretor.app_role = '<role>';
DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT USAGE ON SCHEMA ld_analysis TO %I', app_role);
        EXECUTE format(
            'GRANT SELECT, INSERT ON ld_analysis.analysis_run, '
            'ld_analysis.analysis_input, ld_analysis.finding, '
            'ld_analysis.report_snapshot TO %I',
            app_role
        );
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION ld_analysis.complete_run(uuid) TO %I',
            app_role
        );
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMENT ON TABLE ld_analysis.analysis_run IS
    'Immutable completed analysis artifact. Freezes the input, engine state, rules/calculations/findings and privacy-filtered result used for a reproducible dossier.';
COMMENT ON COLUMN ld_analysis.analysis_run.lineage_status IS
    'AGGREGATED_RUNTIME_SNAPSHOT while the run is backed by the frozen aggregate public dossier snapshot; SOURCE_SNAPSHOTS_COMPLETE only when every upstream source snapshot is individually linked.';
COMMENT ON TABLE ld_analysis.analysis_input IS
    'Immutable links from an Analysis Run to source snapshots/normalized records.';
COMMENT ON TABLE ld_analysis.finding IS
    'Immutable findings frozen for an Analysis Run, preferably linked to the assertion that supports them.';
COMMENT ON TABLE ld_analysis.report_snapshot IS
    'Immutable report payload/hash associated with an Analysis Run.';

COMMIT;
