-- LoteDiretor Brasil — AI core traces and retrieval helpers (Phase 5)
--
-- Every AI answer is traceable (Blueprint §30.19): which sources and rules
-- were retrieved, which were cited, model, tokens, latency and validator
-- outcome. Questions are stored as a hash by default (they may contain
-- personal data); the answer status and citations are kept for audit/evals.

BEGIN;

CREATE SCHEMA IF NOT EXISTS ld_ai;

CREATE TABLE ld_ai.trace (
    trace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    assistant text NOT NULL CHECK (assistant IN ('cidades', 'condominio', 'tec')),
    org_id uuid REFERENCES ld_app.organization(org_id),
    user_id uuid REFERENCES ld_app.app_user(user_id),
    ibge_code char(7),
    question_sha256 text NOT NULL CHECK (question_sha256 ~ '^[0-9a-f]{64}$'),
    question_chars integer NOT NULL,
    mode text NOT NULL CHECK (mode IN ('LLM', 'RETRIEVAL_ONLY', 'NO_SOURCES')),
    status text NOT NULL,
    retrieved_provisions uuid[] NOT NULL DEFAULT '{}',
    retrieved_rules uuid[] NOT NULL DEFAULT '{}',
    cited_provisions uuid[] NOT NULL DEFAULT '{}',
    cited_rules uuid[] NOT NULL DEFAULT '{}',
    validator_flags text[] NOT NULL DEFAULT '{}',
    model text,
    prompt_version text NOT NULL,
    input_tokens integer,
    output_tokens integer,
    latency_ms integer NOT NULL,
    feedback smallint CHECK (feedback IS NULL OR feedback IN (-1, 1)),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX trace_user_time_idx ON ld_ai.trace (user_id, created_at DESC);
CREATE INDEX trace_org_time_idx ON ld_ai.trace (org_id, created_at DESC);

-- Natural-language questions: OR over the question's stemmed lexemes, so a
-- long question still finds provisions sharing some of its key terms.
CREATE OR REPLACE FUNCTION ld_api.search_provisions_any(
    p_question text,
    p_ibge char(7),
    p_date date DEFAULT current_date,
    p_limit integer DEFAULT 8
)
RETURNS TABLE (
    provision_id uuid, document_title text, document_kind text,
    jurisdiction_level text, version_label text, path text,
    page_start integer, text text, rank real, canonical_url text,
    review_status text
)
LANGUAGE sql STABLE
AS $fn$
    WITH lex AS (
        SELECT array_to_string(
                   tsvector_to_array(to_tsvector('portuguese', unaccent(p_question))),
                   ' | ') AS q
    ),
    q AS (
        SELECT CASE WHEN lex.q = '' THEN NULL ELSE to_tsquery('simple', lex.q) END AS tsq
        FROM lex
    ),
    mun AS (SELECT s.uf FROM ld_core.municipality m
            JOIN ld_core.state s USING (uf_code) WHERE m.ibge_code = p_ibge)
    SELECT p.provision_id, d.title, d.kind, d.jurisdiction_level, v.label,
           p.path, p.page_start, p.text,
           ts_rank_cd(p.tsv, q.tsq, 32) AS rank,
           d.canonical_url, v.review_status
    FROM ld_legal.provision p
    JOIN ld_legal.document_version v USING (version_id)
    JOIN ld_legal.document d USING (document_id)
    CROSS JOIN q
    WHERE q.tsq IS NOT NULL
      AND p.tsv @@ q.tsq
      AND v.superseded_at IS NULL
      AND v.review_status <> 'REJECTED'
      AND (v.valid_from IS NULL OR v.valid_from <= p_date)
      AND (v.valid_to IS NULL OR v.valid_to >= p_date)
      AND (d.jurisdiction_level = 'FEDERAL'
           OR (d.jurisdiction_level = 'STATE' AND d.uf = (SELECT uf FROM mun))
           OR (d.jurisdiction_level = 'MUNICIPAL' AND d.ibge_code = p_ibge))
    ORDER BY rank DESC, p.ordinal
    LIMIT least(greatest(p_limit, 1), 20)
$fn$;

DO $grants$
DECLARE
    app_role text := coalesce(
        nullif(current_setting('lotediretor.app_role', true), ''),
        'sentinelx'
    );
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('GRANT USAGE ON SCHEMA ld_ai TO %I', app_role);
        EXECUTE format('GRANT SELECT, INSERT ON ld_ai.trace TO %I', app_role);
        EXECUTE format('GRANT UPDATE (feedback) ON ld_ai.trace TO %I', app_role);
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION ld_api.search_provisions_any(text, char, date, integer) TO %I',
            app_role);
    ELSE
        RAISE NOTICE 'role % does not exist; skipping runtime grants', app_role;
    END IF;
END;
$grants$;

COMMIT;
