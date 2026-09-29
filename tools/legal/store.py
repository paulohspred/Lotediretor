"""Write legal documents, versions, provisions and candidate rules to PostGIS.

Shared by ingest.py (files) and seed_catalog.py (repository data).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from psycopg2.extras import Json

import rules as rules_mod
from segment import Provision


@dataclass
class DocumentMeta:
    jurisdiction_level: str
    kind: str
    title: str
    number: str | None = None
    uf: str | None = None
    ibge_code: str | None = None
    publication_date: str | None = None
    source_id: str | None = None
    canonical_url: str | None = None
    subject: tuple[str, ...] = ()


def upsert_document(cur, meta: DocumentMeta) -> str:
    cur.execute(
        """INSERT INTO ld_legal.document
               (jurisdiction_level, uf, ibge_code, kind, subject, number, title,
                publication_date, source_id, canonical_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (jurisdiction_level, uf, ibge_code, kind, number) DO UPDATE
               SET title = EXCLUDED.title,
                   subject = EXCLUDED.subject,
                   publication_date = coalesce(EXCLUDED.publication_date,
                                               ld_legal.document.publication_date),
                   source_id = coalesce(EXCLUDED.source_id, ld_legal.document.source_id),
                   canonical_url = coalesce(EXCLUDED.canonical_url,
                                            ld_legal.document.canonical_url)
           RETURNING document_id""",
        (meta.jurisdiction_level, meta.uf, meta.ibge_code, meta.kind,
         list(meta.subject), meta.number, meta.title, meta.publication_date,
         meta.source_id, meta.canonical_url),
    )
    return cur.fetchone()[0]


def content_sha(provisions: list[Provision]) -> str:
    payload = json.dumps([(p.kind, p.path, p.text) for p in provisions], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def add_version(
    cur,
    document_id: str,
    label: str,
    provisions: list[Provision],
    extraction_method: str,
    valid_from: str | None = None,
    snapshot_id: str | None = None,
    close_previous: bool = False,
) -> tuple[str, bool]:
    """Insert a version unless identical content is already current.

    Returns (version_id, created).
    """
    sha = content_sha(provisions)
    cur.execute(
        """SELECT version_id FROM ld_legal.document_version
           WHERE document_id = %s AND content_sha256 = %s AND superseded_at IS NULL""",
        (document_id, sha),
    )
    row = cur.fetchone()
    if row:
        return row[0], False

    if close_previous and valid_from:
        cur.execute(
            """UPDATE ld_legal.document_version
               SET valid_to = (%s::date - 1)
               WHERE document_id = %s AND superseded_at IS NULL AND valid_to IS NULL
                 AND (valid_from IS NULL OR valid_from < %s::date)""",
            (valid_from, document_id, valid_from),
        )
    cur.execute(
        """INSERT INTO ld_legal.document_version
               (document_id, label, valid_from, text_available, extraction_method,
                content_sha256, snapshot_id)
           VALUES (%s, %s, %s, true, %s, %s, %s) RETURNING version_id""",
        (document_id, label, valid_from, extraction_method, sha, snapshot_id),
    )
    version_id = cur.fetchone()[0]

    ids: list[str] = []
    for ordinal, p in enumerate(provisions):
        parent = ids[p.parent_index] if p.parent_index is not None else None
        cur.execute(
            """INSERT INTO ld_legal.provision
                   (version_id, parent_id, kind, path, ordinal, page_start, page_end, text)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING provision_id""",
            (version_id, parent, p.kind, p.path, ordinal, p.page_start, p.page_end, p.text),
        )
        ids.append(cur.fetchone()[0])
    return version_id, True


def add_candidate_rules(cur, ibge: str, zone_code: str, provision_id: str,
                        text: str, valid_from: str | None) -> int:
    count = 0
    for c in rules_mod.extract(text):
        cur.execute(
            """INSERT INTO ld_legal.urban_rule
                   (ibge_code, zone_code, parameter, use_condition, value, unit,
                    no_restriction, valid_from, provision_id, evidence_excerpt,
                    status, extracted_by, condition)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CANDIDATE', %s, %s)""",
            (ibge, zone_code, c.parameter, c.use_condition, c.value, c.unit,
             c.no_restriction, valid_from, provision_id, c.excerpt,
             rules_mod.EXTRACTOR_VERSION, Json({})),
        )
        count += 1
    return count
