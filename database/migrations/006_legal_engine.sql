-- LoteDiretor Brasil — legal engine (Phase 4)
--
-- Laws are never overwritten (Blueprint §8, §22): each document has versions
-- with a legal validity interval (valid_from/valid_to) and a system interval
-- (recorded_at/superseded_at). Provisions (articles, paragraphs, annexes) are
-- searchable; urban parameters are structured rules that always point back to
-- the provision that supports them, and only CONFIRMED rules — reviewed by a
-- person — are presented as confirmed.

BEGIN;

CREATE SCHEMA IF NOT EXISTS ld_legal;

CREATE TABLE ld_legal.document (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_level text NOT NULL
        CHECK (jurisdiction_level IN ('FEDERAL', 'STATE', 'MUNICIPAL')),
    uf char(2) CHECK (uf IS NULL OR uf ~ '^[A-Z]{2}$'),
    ibge_code char(7) REFERENCES ld_core.municipality(ibge_code),
    kind text NOT NULL CHECK (kind IN (
        'CONSTITUICAO', 'LEI', 'LEI_COMPLEMENTAR', 'DECRETO', 'PORTARIA',
        'RESOLUCAO', 'INSTRUCAO_NORMATIVA', 'DECISAO_JUDICIAL', 'OUTRO')),
    subject text[] NOT NULL DEFAULT '{}',
    number text,
    title text NOT NULL,
    publication_date date,
    source_id text REFERENCES ld_catalog.source(source_id),
    canonical_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jurisdiction_level <> 'MUNICIPAL' OR ibge_code IS NOT NULL),
    CHECK (jurisdiction_level <> 'STATE' OR uf IS NOT NULL),
    UNIQUE NULLS NOT DISTINCT (jurisdiction_level, uf, ibge_code, kind, number)
);

CREATE TABLE ld_legal.document_version (
    version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES ld_legal.document(document_id),
    label text NOT NULL,
    valid_from date,
    valid_to date,
    text_available boolean NOT NULL DEFAULT false,
    extraction_method text
        CHECK (extraction_method IS NULL OR extraction_method IN
            ('NATIVE_TEXT', 'HTML', 'OCR', 'MANUAL_TRANSCRIPTION')),
    content_sha256 text CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'),
    snapshot_id uuid REFERENCES ld_catalog.snapshot(snapshot_id),
    review_status text NOT NULL DEFAULT 'PENDING_REVIEW'
        CHECK (review_status IN ('PENDING_REVIEW', 'REVIEWED', 'REJECTED')),
    reviewed_by text,
    reviewed_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK (review_status <> 'REVIEWED' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    -- OCR text is never considered reviewed automatically (Blueprint §22).
    CHECK (extraction_method IS DISTINCT FROM 'OCR' OR review_status <> 'REVIEWED'
           OR reviewed_by IS NOT NULL)
);

CREATE INDEX document_version_validity_idx
    ON ld_legal.document_version (document_id, valid_from, valid_to)
    WHERE superseded_at IS NULL;

CREATE TABLE ld_legal.relation (
    relation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_document_id uuid NOT NULL REFERENCES ld_legal.document(document_id),
    to_document_id uuid NOT NULL REFERENCES ld_legal.document(document_id),
    relation text NOT NULL CHECK (relation IN (
        'ALTERA', 'REVOGA', 'REVOGA_PARCIALMENTE', 'REGULAMENTA',
        'CONSOLIDA', 'SUSPENDE', 'SUSPENDE_PARCIALMENTE')),
    effective_date date,
    target_path text,
    note text,
    CHECK (from_document_id <> to_document_id)
);

CREATE TABLE ld_legal.provision (
    provision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id uuid NOT NULL REFERENCES ld_legal.document_version(version_id)
        ON DELETE CASCADE,
    parent_id uuid REFERENCES ld_legal.provision(provision_id),
    kind text NOT NULL CHECK (kind IN (
        'PREAMBULO', 'TITULO', 'CAPITULO', 'SECAO', 'ARTIGO', 'PARAGRAFO',
        'INCISO', 'ALINEA', 'ANEXO', 'QUADRO', 'TRECHO')),
    path text NOT NULL,
    ordinal integer NOT NULL,
    page_start integer,
    page_end integer,
    text text NOT NULL,
    tsv tsvector,
    UNIQUE (version_id, ordinal)
);

CREATE INDEX provision_tsv_idx ON ld_legal.provision USING gin (tsv);
CREATE INDEX provision_version_path_idx ON ld_legal.provision (version_id, path);

CREATE OR REPLACE FUNCTION ld_legal.provision_tsv_trigger()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    NEW.tsv := setweight(to_tsvector('portuguese', unaccent(NEW.path)), 'A')
            || setweight(to_tsvector('portuguese', unaccent(NEW.text)), 'B');
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER provision_tsv
    BEFORE INSERT OR UPDATE OF text, path ON ld_legal.provision
    FOR EACH ROW EXECUTE FUNCTION ld_legal.provision_tsv_trigger();

-- Structured, computable urban parameters with mandatory evidence.
CREATE TABLE ld_legal.urban_rule (
    rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ibge_code char(7) NOT NULL REFERENCES ld_core.municipality(ibge_code),
    zone_code text NOT NULL,
    parameter text NOT NULL CHECK (parameter IN (
        'CA_MINIMO', 'CA_BASICO', 'CA_MAXIMO', 'TO_MAXIMA', 'TP_MINIMA',
        'GABARITO_M', 'PAVIMENTOS_MAX', 'RECUO_FRONTAL_M', 'RECUO_LATERAL_M',
        'RECUO_FUNDOS_M', 'LOTE_MINIMO_M2', 'TESTADA_MINIMA_M')),
    use_condition text NOT NULL DEFAULT 'GERAL',
    condition jsonb NOT NULL DEFAULT '{}'::jsonb,
    value numeric,
    unit text NOT NULL CHECK (unit IN ('ratio', 'percent', 'm', 'm2', 'count')),
    no_restriction boolean NOT NULL DEFAULT false,
    valid_from date,
    valid_to date,
    provision_id uuid NOT NULL REFERENCES ld_legal.provision(provision_id),
    evidence_excerpt text NOT NULL,
    status text NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE', 'CONFIRMED', 'CONFLICTING', 'REJECTED')),
    extracted_by text NOT NULL,
    reviewed_by text,
    reviewed_at timestamptz,
    review_note text,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz,
    CHECK (value IS NOT NULL OR no_restriction),
    CHECK (status NOT IN ('CONFIRMED', 'REJECTED')
           OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE INDEX urban_rule_lookup_idx
    ON ld_legal.urban_rule (ibge_code, zone_code, parameter)
    WHERE superseded_at IS NULL;

-- Map-layer codes (e.g. sector "A-04") to the legal zone they belong to
-- (e.g. "SER"), with the provision that establishes the mapping.
CREATE TABLE ld_legal.zone_alias (
    ibge_code char(7) NOT NULL REFERENCES ld_core.municipality(ibge_code),
    alias text NOT NULL,
    zone_code text NOT NULL,
    provision_id uuid REFERENCES ld_legal.provision(provision_id),
    PRIMARY KEY (ibge_code, alias)
);

-- Human review is an audited event, not an overwrite.
CREATE TABLE ld_legal.rule_review_event (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id uuid NOT NULL REFERENCES ld_legal.urban_rule(rule_id),
    from_status text NOT NULL,
    to_status text NOT NULL,
    reviewer text NOT NULL,
    note text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Rules in force at a date. CANDIDATE and REJECTED are excluded unless
-- explicitly requested, so unreviewed extractions never look confirmed.
CREATE OR REPLACE FUNCTION ld_api.effective_urban_rules(
    p_ibge char(7),
    p_zone text,
    p_date date DEFAULT current_date,
    p_include_candidates boolean DEFAULT false
)
RETURNS TABLE (
    rule_id uuid, parameter text, use_condition text, value numeric,
    unit text, no_restriction boolean, status text, valid_from date,
    valid_to date, document_title text, provision_path text,
    page_start integer, evidence_excerpt text, canonical_url text
)
LANGUAGE sql STABLE
AS $fn$
    SELECT r.rule_id, r.parameter, r.use_condition, r.value, r.unit,
           r.no_restriction, r.status, r.valid_from, r.valid_to,
           d.title, p.path, p.page_start, r.evidence_excerpt, d.canonical_url
    FROM ld_legal.urban_rule r
    JOIN ld_legal.provision p USING (provision_id)
    JOIN ld_legal.document_version v USING (version_id)
    JOIN ld_legal.document d USING (document_id)
    WHERE r.ibge_code = p_ibge
      AND r.zone_code = coalesce(
            (SELECT a.zone_code FROM ld_legal.zone_alias a
             WHERE a.ibge_code = p_ibge AND a.alias = p_zone),
            p_zone)
      AND r.superseded_at IS NULL
      AND (r.valid_from IS NULL OR r.valid_from <= p_date)
      AND (r.valid_to IS NULL OR r.valid_to >= p_date)
      AND (r.status IN ('CONFIRMED', 'CONFLICTING')
           OR (p_include_candidates AND r.status = 'CANDIDATE'))
    ORDER BY r.parameter, r.use_condition, r.status
$fn$;

-- Full-text legal search restricted to a jurisdiction and a date.
CREATE OR REPLACE FUNCTION ld_api.search_provisions(
    p_query text,
    p_ibge char(7),
    p_date date DEFAULT current_date,
    p_limit integer DEFAULT 10
)
RETURNS TABLE (
    provision_id uuid, document_title text, document_kind text,
    jurisdiction_level text, version_label text, path text,
    page_start integer, excerpt text, rank real, canonical_url text,
    review_status text
)
LANGUAGE sql STABLE
AS $fn$
    WITH q AS (SELECT websearch_to_tsquery('portuguese', unaccent(p_query)) AS tsq),
         mun AS (SELECT s.uf FROM ld_core.municipality m
                 JOIN ld_core.state s USING (uf_code) WHERE m.ibge_code = p_ibge)
    SELECT p.provision_id, d.title, d.kind, d.jurisdiction_level, v.label,
           p.path, p.page_start,
           ts_headline('portuguese', p.text, q.tsq,
                       'MaxWords=45, MinWords=15, ShortWord=2, MaxFragments=2,'
                       ' StartSel=«, StopSel=»') AS excerpt,
           ts_rank_cd(p.tsv, q.tsq) AS rank,
           d.canonical_url, v.review_status
    FROM ld_legal.provision p
    JOIN ld_legal.document_version v USING (version_id)
    JOIN ld_legal.document d USING (document_id)
    CROSS JOIN q
    WHERE p.tsv @@ q.tsq
      AND v.superseded_at IS NULL
      AND v.review_status <> 'REJECTED'
      AND (v.valid_from IS NULL OR v.valid_from <= p_date)
      AND (v.valid_to IS NULL OR v.valid_to >= p_date)
      AND (d.jurisdiction_level = 'FEDERAL'
           OR (d.jurisdiction_level = 'STATE' AND d.uf = (SELECT uf FROM mun))
           OR (d.jurisdiction_level = 'MUNICIPAL' AND d.ibge_code = p_ibge))
    ORDER BY rank DESC, d.title, p.ordinal
    LIMIT least(greatest(p_limit, 1), 50)
$fn$;

DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT USAGE ON SCHEMA ld_legal TO %I', app_role);
        EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA ld_legal TO %I', app_role);
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION '
            'ld_api.effective_urban_rules(char, text, date, boolean), '
            'ld_api.search_provisions(text, char, date, integer) TO %I',
            app_role
        );
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMIT;
