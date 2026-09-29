#!/usr/bin/env python3
"""Ingest a legal document file (PDF, HTML or TXT) as a new versioned text.

    LOTEDIRETOR_DB_DSN=... python3 tools/legal/ingest.py lei.pdf \
        --jurisdiction MUNICIPAL --ibge 3505708 --kind LEI_COMPLEMENTAR \
        --number 565/2023 --title "LC 565/2023 — Uso e Ocupação do Solo" \
        --valid-from 2023-12-11 --source-id sp-barueri-lpuos-lc565-2023 \
        --url https://... [--close-previous] [--zone-article SER=35 ...]

Scanned PDFs (no text layer) are refused: OCR must be a separate, reviewed
step and is never marked as confirmed automatically (Blueprint §8/§22).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segment import segment  # noqa: E402
from store import DocumentMeta, add_candidate_rules, add_version, upsert_document  # noqa: E402

MIN_CHARS_PER_PAGE = 200


def read_pages(path: Path) -> tuple[list[str], str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            check=True, capture_output=True, text=True,
        ).stdout
        pages = text.split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        avg = sum(len(p.strip()) for p in pages) / max(len(pages), 1)
        if avg < MIN_CHARS_PER_PAGE:
            raise SystemExit(
                f"{path.name}: sem camada de texto (média {avg:.0f} caracteres/página). "
                "Faça OCR em etapa separada e revise antes de ingerir."
            )
        return pages, "NATIVE_TEXT"
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", raw)
        raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        return raw.split("\f"), "HTML"
    return raw.split("\f"), "MANUAL_TRANSCRIPTION"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    ap.add_argument("--jurisdiction", required=True, choices=["FEDERAL", "STATE", "MUNICIPAL"])
    ap.add_argument("--uf")
    ap.add_argument("--ibge")
    ap.add_argument("--kind", required=True)
    ap.add_argument("--number")
    ap.add_argument("--title", required=True)
    ap.add_argument("--publication-date")
    ap.add_argument("--valid-from")
    ap.add_argument("--label", default=None)
    ap.add_argument("--source-id")
    ap.add_argument("--url")
    ap.add_argument("--subject", action="append", default=[])
    ap.add_argument("--close-previous", action="store_true")
    ap.add_argument("--zone-article", action="append", default=[],
                    metavar="ZONE=ARTICLE",
                    help="extract CANDIDATE rules for ZONE from art. ARTICLE")
    args = ap.parse_args()
    if not args.dsn:
        ap.error("--dsn or LOTEDIRETOR_DB_DSN is required")

    pages, method = read_pages(args.file)
    provisions = segment(pages)
    if not provisions:
        raise SystemExit("nenhum dispositivo reconhecido no texto")
    file_sha = hashlib.sha256(args.file.read_bytes()).hexdigest()

    meta = DocumentMeta(
        jurisdiction_level=args.jurisdiction, kind=args.kind, title=args.title,
        number=args.number, uf=args.uf, ibge_code=args.ibge,
        publication_date=args.publication_date, source_id=args.source_id,
        canonical_url=args.url, subject=tuple(args.subject),
    )
    with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
        snapshot_id = None
        if args.source_id:
            cur.execute(
                """INSERT INTO ld_catalog.snapshot
                       (source_id, captured_at, requested_url, final_url, sha256,
                        content_length, manifest)
                   VALUES (%s, now(), %s, %s, %s, %s,
                           jsonb_build_object('file', %s::text, 'kind', 'legal_text'))
                   ON CONFLICT (source_id, sha256) DO UPDATE SET manifest = EXCLUDED.manifest
                   RETURNING snapshot_id""",
                (args.source_id, args.url or "", args.url or "", file_sha,
                 args.file.stat().st_size, args.file.name),
            )
            snapshot_id = cur.fetchone()[0]
        document_id = upsert_document(cur, meta)
        version_id, created = add_version(
            cur, document_id, args.label or f"Texto de {args.file.name}", provisions,
            method, args.valid_from, snapshot_id, args.close_previous,
        )
        rules = 0
        if created and args.zone_article:
            for pair in args.zone_article:
                zone, _, article = pair.partition("=")
                cur.execute(
                    """SELECT provision_id, text FROM ld_legal.provision
                       WHERE version_id = %s AND path = %s""",
                    (version_id, f"art. {article}º" if int(article) < 10 else f"art. {article}"),
                )
                row = cur.fetchone()
                if not row:
                    print(f"aviso: art. {article} não encontrado para {zone}", file=sys.stderr)
                    continue
                # Include the article's children (incisos, alíneas, parágrafos).
                cur.execute(
                    """WITH RECURSIVE tree AS (
                           SELECT provision_id, text, ordinal FROM ld_legal.provision
                           WHERE provision_id = %s
                           UNION ALL
                           SELECT p.provision_id, p.text, p.ordinal
                           FROM ld_legal.provision p JOIN tree t ON p.parent_id = t.provision_id)
                       SELECT string_agg(text, ' ' ORDER BY ordinal) FROM tree""",
                    (row[0],),
                )
                full = cur.fetchone()[0]
                rules += add_candidate_rules(cur, args.ibge, zone, row[0], full, args.valid_from)
    state = "nova versão" if created else "conteúdo idêntico já registrado"
    print(f"{args.title}: {len(provisions)} dispositivos, {state}, {rules} regras candidatas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
