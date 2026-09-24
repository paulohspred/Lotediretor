#!/usr/bin/env python3
"""Conservative read-only client for the PNCP public consultation API."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from public_api import fetch_json, sha256, utc_now, write_json

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/public-events/pncp-api.json"
OUT = ROOT / "data/snapshots"
ALLOWED_HOSTS = {"pncp.gov.br"}
MAX_PAGES = 20
MAX_WINDOW_DAYS = 365


def yyyymmdd(value: str) -> str:
    if not re.fullmatch(r"\d{8}", value):
        raise argparse.ArgumentTypeError("date must be YYYYMMDD")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def cnpj(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 14:
        raise argparse.ArgumentTypeError("CNPJ must have 14 digits")
    return digits


def ibge(value: str) -> str:
    if not re.fullmatch(r"\d{7}", value):
        raise argparse.ArgumentTypeError("municipality IBGE code must have 7 digits")
    return value


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", required=True, type=yyyymmdd)
    parser.add_argument("--end", required=True, type=yyyymmdd)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024)
    parser.add_argument("--out", type=Path, default=OUT)


def validate_common(args) -> None:
    start = datetime.strptime(args.start, "%Y%m%d").date()
    end = datetime.strptime(args.end, "%Y%m%d").date()
    if end < start:
        raise SystemExit("--end must be >= --start")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise SystemExit(
            f"date window cannot exceed {MAX_WINDOW_DAYS} days"
        )
    if args.page < 1:
        raise SystemExit("--page must be >= 1")
    if not 1 <= args.pages <= MAX_PAGES:
        raise SystemExit(f"--pages must be between 1 and {MAX_PAGES}")
    if not 1 <= args.page_size <= 50:
        raise SystemExit("--page-size must be between 1 and 50")


def build_url(base: str, path: str, query: dict[str, object]) -> str:
    return base.rstrip("/") + path + "?" + urllib.parse.urlencode(query)


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    publications = sub.add_parser("publications")
    add_common(publications)
    publications.add_argument("--modality", required=True, type=int)
    publications.add_argument("--municipality", type=ibge)
    publications.add_argument("--uf")
    publications.add_argument("--cnpj", type=cnpj)
    publications.add_argument("--unit")
    publications.add_argument("--dispute-mode", type=int)

    contracts = sub.add_parser("contracts")
    add_common(contracts)
    contracts.add_argument("--cnpj", type=cnpj)
    contracts.add_argument("--unit")

    args = parser.parse_args()
    validate_common(args)

    endpoint = config["endpoints"][args.command]
    query: dict[str, object] = {
        "dataInicial": args.start,
        "dataFinal": args.end,
        "pagina": args.page,
        "tamanhoPagina": args.page_size,
    }
    if args.command == "publications":
        query["codigoModalidadeContratacao"] = args.modality
        if args.municipality:
            query["codigoMunicipioIbge"] = args.municipality
        if args.uf:
            query["uf"] = args.uf.upper()
        if args.cnpj:
            query["cnpj"] = args.cnpj
        if args.unit:
            query["codigoUnidadeAdministrativa"] = args.unit
        if args.dispute_mode is not None:
            query["codigoModoDisputa"] = args.dispute_mode
    else:
        if args.cnpj:
            query["cnpjOrgao"] = args.cnpj
        if args.unit:
            query["codigoUnidadeAdministrativa"] = args.unit

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.out / f"pncp-{args.command}" / stamp
    folder.mkdir(parents=True, exist_ok=False)

    page_records = []
    total_pages = None
    for offset in range(args.pages):
        page = args.page + offset
        query["pagina"] = page
        url = build_url(config["discovery_base_url"], endpoint["path"], query)
        result = fetch_json(
            url,
            allowed_hosts=ALLOWED_HOSTS,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
        )
        payload = result["json"]
        if not isinstance(payload, dict):
            raise SystemExit("unexpected PNCP response: object expected")

        data = payload.get("data")
        if data is None:
            data = []
        if not isinstance(data, list):
            raise SystemExit("unexpected PNCP response: data must be an array")

        if total_pages is None:
            reported = payload.get("totalPaginas")
            if isinstance(reported, int):
                total_pages = reported

        returned_page = payload.get("numeroPagina")
        if returned_page is not None and returned_page != page:
            raise SystemExit(
                f"PNCP returned numeroPagina={returned_page}, expected {page}"
            )

        filename = f"page-{page:05d}.json"
        (folder / filename).write_bytes(result["body"])
        page_records.append(
            {
                "page": page,
                "records": len(data),
                "requested_url": url,
                "final_url": result["final_url"],
                "http_status": result["status"],
                "sha256": sha256(result["body"]),
                "raw_file": filename,
            }
        )

        if not data:
            break
        if isinstance(total_pages, int) and page >= total_pages:
            break
        if payload.get("paginasRestantes") == 0:
            break

    manifest = {
        "schema_version": "0.1.0",
        "source_id": config["source_id"],
        "command": args.command,
        "captured_at": utc_now(),
        "query": {
            key: value
            for key, value in query.items()
            if key != "pagina"
        },
        "first_page": args.page,
        "requested_pages": args.pages,
        "total_pages_reported": total_pages,
        "pages": page_records,
        "privacy_rule": config["privacy_rule"],
    }
    write_json(folder / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
