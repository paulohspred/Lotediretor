#!/usr/bin/env python3
"""Human review of extracted urban rules (until the admin UI exists).

    python3 tools/legal/review_rules.py list --ibge 3505708 --zone SER
    python3 tools/legal/review_rules.py confirm <rule_id> --reviewer "Nome (CAU/CREA)" \
        --note "Conferido com o art. 35 do PDF oficial, p. 16"
    python3 tools/legal/review_rules.py reject <rule_id> --reviewer ... --note ...
    python3 tools/legal/review_rules.py conflict <rule_id> --reviewer ... --note ...

Every decision is recorded in ld_legal.rule_review_event. A note is required:
it is the evidence of what the reviewer checked.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2

STATUS = {"confirm": "CONFIRMED", "reject": "REJECTED", "conflict": "CONFLICTING"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--ibge", required=True)
    ls.add_argument("--zone")
    ls.add_argument("--status", default="CANDIDATE")
    for name in STATUS:
        p = sub.add_parser(name)
        p.add_argument("rule_id")
        p.add_argument("--reviewer", required=True)
        p.add_argument("--note", required=True)
    args = ap.parse_args()
    if not args.dsn:
        ap.error("--dsn or LOTEDIRETOR_DB_DSN is required")

    with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
        if args.cmd == "list":
            cur.execute(
                """SELECT r.rule_id, r.zone_code, r.parameter, r.use_condition,
                          coalesce(r.value::text, 'sem restrição'), r.unit, p.path,
                          r.evidence_excerpt
                   FROM ld_legal.urban_rule r JOIN ld_legal.provision p USING (provision_id)
                   WHERE r.ibge_code = %s AND r.status = %s AND r.superseded_at IS NULL
                     AND (%s::text IS NULL OR r.zone_code = %s)
                   ORDER BY r.zone_code, r.parameter, r.use_condition""",
                (args.ibge, args.status, args.zone, args.zone),
            )
            for row in cur.fetchall():
                print(" | ".join(str(c) for c in row[:7]))
                print(f"    «{row[7]}»")
            return 0

        if len(args.note.strip()) < 10:
            ap.error("--note deve descrever o que foi conferido (mín. 10 caracteres)")
        new_status = STATUS[args.cmd]
        cur.execute(
            "SELECT status FROM ld_legal.urban_rule WHERE rule_id = %s FOR UPDATE",
            (args.rule_id,),
        )
        row = cur.fetchone()
        if not row:
            print("regra não encontrada", file=sys.stderr)
            return 1
        cur.execute(
            """UPDATE ld_legal.urban_rule
               SET status = %s, reviewed_by = %s, reviewed_at = now(), review_note = %s
               WHERE rule_id = %s""",
            (new_status, args.reviewer, args.note, args.rule_id),
        )
        cur.execute(
            """INSERT INTO ld_legal.rule_review_event
                   (rule_id, from_status, to_status, reviewer, note)
               VALUES (%s, %s, %s, %s, %s)""",
            (args.rule_id, row[0], new_status, args.reviewer, args.note),
        )
    print(f"{args.rule_id}: {row[0]} → {new_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
