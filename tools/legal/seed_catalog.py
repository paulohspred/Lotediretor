#!/usr/bin/env python3
"""Seed the legal catalog from data already curated in this repository.

1. data/legal-registry/capital-plans.json → Plano Diretor metadata for the
   27 capitals (text not yet ingested; the catalog says so).
2. data/legal/barueri-lc565-sector-rules.json → transcribed articles of
   Barueri's LC 565/2023 per sector group, sector→group aliases and CANDIDATE
   urban rules awaiting human review.

Idempotent. Usage: LOTEDIRETOR_DB_DSN=... python3 tools/legal/seed_catalog.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segment import Provision  # noqa: E402
from store import DocumentMeta, add_candidate_rules, add_version, upsert_document  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def plan_kind(law: str) -> str:
    return "LEI_COMPLEMENTAR" if re.match(r"\s*(LC|Lei Complementar)\b", law, re.I) else "LEI"


def seed_capitals(cur) -> int:
    data = json.loads((ROOT / "data/legal-registry/capital-plans.json").read_text("utf-8"))
    cur.execute("SELECT ibge_code FROM ld_core.municipality")
    known = {r[0] for r in cur.fetchall()}
    n = 0
    for cap in data["capitals"]:
        if cap["ibge"] not in known:
            continue  # mesh not loaded yet (e.g. tests with a sample mesh)
        upsert_document(cur, DocumentMeta(
            jurisdiction_level="MUNICIPAL", kind=plan_kind(cap["plan_law"]),
            title=f"Plano Diretor de {cap['capital']} — {cap['plan_law']}",
            number=cap["plan_law"], uf=cap["uf"], ibge_code=cap["ibge"],
            canonical_url=cap.get("official_url"), subject=("plano_diretor",),
        ))
        n += 1
    return n


def seed_barueri(cur) -> tuple[int, int]:
    path = ROOT / "data/legal/barueri-lc565-sector-rules.json"
    data = json.loads(path.read_text("utf-8"))
    ibge = "3505708"
    cur.execute("SELECT 1 FROM ld_core.municipality WHERE ibge_code = %s", (ibge,))
    if not cur.fetchone():
        return 0, 0
    doc = upsert_document(cur, DocumentMeta(
        jurisdiction_level="MUNICIPAL", kind="LEI_COMPLEMENTAR",
        title="Lei Complementar nº 565/2023 — Uso e ocupação do solo de Barueri",
        number="565/2023", uf="SP", ibge_code=ibge, publication_date="2023-12-11",
        source_id="sp-barueri-lpuos-lc565-2023", canonical_url=data["source_url"],
        subject=("zoneamento", "uso_e_ocupacao"),
    ))
    groups = sorted(data["groups"].items(), key=lambda kv: kv[1]["article"])
    # The transcription carries PDF page numbers ("; 16 16 3.") — drop them.
    clean = {code: re.sub(r"(?<=[;.])\s\d{1,3}\s\d{1,3}(?=\s)", "", g["rule_text"])
             for code, g in groups}
    provisions = [
        # Transcription has no page mapping.
        Provision("ARTIGO", f"art. {g['article']}", None, None, [clean[code]])
        for code, g in groups
    ]
    version_id, created = add_version(
        cur, doc, "Transcrição dos artigos por setor (repositório, 2026-09-28)",
        provisions, "MANUAL_TRANSCRIPTION", valid_from="2023-12-11",
    )
    rules = 0
    for (code, group) in groups:
        cur.execute(
            "SELECT provision_id FROM ld_legal.provision WHERE version_id=%s AND path=%s",
            (version_id, f"art. {group['article']}"),
        )
        provision_id = cur.fetchone()[0]
        for sector in group["sectors"]:
            cur.execute(
                """INSERT INTO ld_legal.zone_alias (ibge_code, alias, zone_code, provision_id)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (ibge_code, alias) DO UPDATE
                       SET zone_code = EXCLUDED.zone_code, provision_id = EXCLUDED.provision_id""",
                (ibge, sector, code, provision_id),
            )
        if created:
            rules += add_candidate_rules(cur, ibge, code, provision_id,
                                         clean[code], "2023-12-11")
    return len(provisions), rules


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    args = ap.parse_args()
    if not args.dsn:
        ap.error("--dsn or LOTEDIRETOR_DB_DSN is required")
    with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
        capitals = seed_capitals(cur)
        articles, rules = seed_barueri(cur)
    print(f"planos diretores de capitais: {capitals}; Barueri: {articles} artigos, "
          f"{rules} regras candidatas novas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
