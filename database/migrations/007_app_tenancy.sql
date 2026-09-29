-- LoteDiretor Brasil — application tenancy, sessions and audit (Phase 5)
--
-- Identity comes from the IdP (Keycloak OIDC); this schema stores only what
-- the product needs: users by IdP subject, organizations (tenants),
-- memberships, per-tenant data protected by row-level security, browser
-- sessions for the BFF (tokens encrypted by the application), contact leads
-- and an append-only audit log.

BEGIN;

CREATE SCHEMA IF NOT EXISTS ld_app;

CREATE TABLE ld_app.organization (
    org_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(name) BETWEEN 2 AND 160),
    kind text NOT NULL DEFAULT 'COMPANY'
        CHECK (kind IN ('PERSONAL', 'COMPANY', 'CONDOMINIUM', 'MUNICIPALITY')),
    status text NOT NULL DEFAULT 'TRIAL'
        CHECK (status IN ('TRIAL', 'ACTIVE', 'PAST_DUE', 'RESTRICTED', 'SUSPENDED', 'CANCELLED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ld_app.app_user (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idp_issuer text NOT NULL,
    idp_subject text NOT NULL,
    email text,
    display_name text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'BLOCKED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    UNIQUE (idp_issuer, idp_subject)
);

CREATE TABLE ld_app.membership (
    org_id uuid NOT NULL REFERENCES ld_app.organization(org_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES ld_app.app_user(user_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'MEMBER', 'VIEWER')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);

CREATE INDEX membership_user_idx ON ld_app.membership (user_id);

-- Browser sessions of the BFF. The cookie carries a random id; only its
-- SHA-256 is stored. Tokens are AES-GCM encrypted by the BFF before storage.
CREATE TABLE ld_app.web_session (
    session_hash text PRIMARY KEY CHECK (session_hash ~ '^[0-9a-f]{64}$'),
    app text NOT NULL CHECK (app IN ('client', 'admin')),
    user_id uuid REFERENCES ld_app.app_user(user_id) ON DELETE CASCADE,
    token_ciphertext bytea NOT NULL,
    access_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE INDEX web_session_user_idx ON ld_app.web_session (user_id) WHERE revoked_at IS NULL;

-- "Meus imóveis": per-organization, protected by RLS.
CREATE TABLE ld_app.saved_property (
    saved_property_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES ld_app.organization(org_id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES ld_app.app_user(user_id),
    ibge_code char(7) NOT NULL REFERENCES ld_core.municipality(ibge_code),
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 200),
    lat double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng double precision NOT NULL CHECK (lng BETWEEN -180 AND 180),
    parcel_reference text,
    analysis_run_id uuid,
    notes text CHECK (notes IS NULL OR length(notes) <= 4000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX saved_property_org_idx ON ld_app.saved_property (org_id, created_at DESC);

CREATE TABLE ld_app.activity_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id uuid NOT NULL REFERENCES ld_app.organization(org_id) ON DELETE CASCADE,
    user_id uuid REFERENCES ld_app.app_user(user_id),
    kind text NOT NULL,
    summary text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX activity_event_org_idx ON ld_app.activity_event (org_id, created_at DESC);

-- Row-level security: the API sets ld.org_id per transaction.
ALTER TABLE ld_app.saved_property ENABLE ROW LEVEL SECURITY;
ALTER TABLE ld_app.saved_property FORCE ROW LEVEL SECURITY;
ALTER TABLE ld_app.activity_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE ld_app.activity_event FORCE ROW LEVEL SECURITY;

CREATE POLICY saved_property_tenant ON ld_app.saved_property
    USING (org_id = nullif(current_setting('ld.org_id', true), '')::uuid)
    WITH CHECK (org_id = nullif(current_setting('ld.org_id', true), '')::uuid);

CREATE POLICY activity_event_tenant ON ld_app.activity_event
    USING (org_id = nullif(current_setting('ld.org_id', true), '')::uuid)
    WITH CHECK (org_id = nullif(current_setting('ld.org_id', true), '')::uuid);

-- Contact / demo requests from the public site.
CREATE TABLE ld_app.lead (
    lead_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
    email text NOT NULL CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' AND length(email) <= 200),
    organization text CHECK (organization IS NULL OR length(organization) <= 160),
    segment text CHECK (segment IS NULL OR length(segment) <= 60),
    message text NOT NULL CHECK (length(message) BETWEEN 5 AND 4000),
    consent_privacy boolean NOT NULL CHECK (consent_privacy),
    source_page text,
    client_hash text,
    status text NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW', 'CONTACTED', 'QUALIFIED', 'DISCARDED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX lead_created_idx ON ld_app.lead (created_at DESC);

-- Append-only audit of privileged actions (Blueprint §31.31).
CREATE TABLE ld_app.audit_log (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id uuid REFERENCES ld_app.app_user(user_id),
    actor_label text NOT NULL,
    action text NOT NULL,
    object_type text NOT NULL,
    object_id text,
    reason text,
    before_state jsonb,
    after_state jsonb,
    request_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION ld_app.audit_log_immutable()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$fn$;

CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE OR DELETE ON ld_app.audit_log
    FOR EACH ROW EXECUTE FUNCTION ld_app.audit_log_immutable();

DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT USAGE ON SCHEMA ld_app TO %I', app_role);
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE ON ld_app.organization, ld_app.app_user, '
            'ld_app.membership, ld_app.web_session TO %I', app_role);
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON ld_app.saved_property TO %I', app_role);
        EXECUTE format(
            'GRANT SELECT, INSERT ON ld_app.activity_event, ld_app.lead, ld_app.audit_log TO %I',
            app_role);
        EXECUTE format('GRANT UPDATE (status) ON ld_app.lead TO %I', app_role);
        EXECUTE format(
            'GRANT UPDATE (status, reviewed_by, reviewed_at, review_note) '
            'ON ld_legal.urban_rule TO %I', app_role);
        EXECUTE format('GRANT INSERT ON ld_legal.rule_review_event TO %I', app_role);
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMIT;
