#!/usr/bin/env python3
"""Materialize São Paulo PGV 2026 Annex II into a keyed terrain-value index.

Source: Lei 18.330/2025, official municipal legislation catalog.
The parser produces Codlog + SQ -> vm2t (BRL/m² of land) and preserves the
official annex PDF as the evidence artifact. It does not calculate IPTU or
official assessed value.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LAW_URL = "https://legislacao.prefeitura.sp.gov.br/lei-18330-de-11-de-novembro-de-2025"
ANNEX_DOCUMENT_ID = "145975345"
ALLOWED_HOSTS = {
    "legislacao.prefeitura.sp.gov.br",
    "diariooficial.prefeitura.sp.gov.br",
}
ROW_RE = re.compile(r"^\s*(\d{6})\s+(\d{6})\s+(\d+)\s*$", re.MULTILINE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, *, timeout: int = 60, max_bytes: int = 20 * 1024 * 1024) -> tuple[bytes, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"host not allowed: {parsed.hostname!r}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        final = response.geturl()
        final_host = urllib.parse.urlsplit(final).hostname
        if final_host not in ALLOWED_HOSTS:
            raise ValueError(f"redirect host not allowed: {final_host!r}")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("download exceeded max_bytes")
        return body, final


def annex_url_from_law_page(page: bytes) -> str:
    text = page.decode("utf-8", errors="replace")
    pattern = re.compile(
        rf'href=["\']([^"\']+)["\'][^>]*>[^<]*{ANNEX_DOCUMENT_ID}',
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError("official annex link not found on law page")
    url = html.unescape(match.group(1))
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


def parse_rows(text: str) -> dict[str, int]:
    records: dict[str, int] = {}
    for codlog, sq, vm2t_raw in ROW_RE.findall(text):
        key = f"{codlog}:{sq}"
        vm2t = int(vm2t_raw)
        previous = records.get(key)
        if previous is not None and previous != vm2t:
            raise ValueError(
                f"conflicting values for {key}: {previous} vs {vm2t}"
            )
        records[key] = vm2t
    if len(records) < 100_000:
        raise ValueError(
            f"implausibly small Annex II parse: {len(records)} records"
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    if shutil.which("pdftotext") is None:
        raise SystemExit("pdftotext is required (poppler-utils)")

    args.out.mkdir(parents=True, exist_ok=True)
    law_html, law_final = fetch(LAW_URL, timeout=args.timeout, max_bytes=2 * 1024 * 1024)
    annex_url = annex_url_from_law_page(law_html)
    pdf, annex_final = fetch(annex_url, timeout=args.timeout)

    pdf_path = args.out / "annex-I-II-lei-18330-2025.pdf"
    txt_path = args.out / "annex-I-II-lei-18330-2025.txt"
    index_path = args.out / "pgv-terrain-values-2026.json"
    manifest_path = args.out / "manifest.json"

    pdf_path.write_bytes(pdf)
    subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
        check=True,
    )
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    records = parse_rows(text)

    index = {
        "schema_version": "0.1.0",
        "source_id": "sp-sao-paulo-pgv-2026",
        "law": "Lei 18.330/2025",
        "effective_from": "2026-01-01",
        "annex": "II",
        "key": "codlog + sq",
        "value_field": "vm2t",
        "value_unit": "BRL_per_m2_land",
        "source_pdf_sha256": sha256_bytes(pdf),
        "record_count": len(records),
        "records": records,
    }
    encoded = json.dumps(
        index,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    index_path.write_bytes(encoded)

    manifest = {
        "schema_version": "0.1.0",
        "source_id": "sp-sao-paulo-pgv-2026",
        "captured_at": utc_now(),
        "law_url": law_final,
        "annex_url": annex_final,
        "annex_document_id": ANNEX_DOCUMENT_ID,
        "pdf_file": pdf_path.name,
        "pdf_sha256": sha256_bytes(pdf),
        "text_file": txt_path.name,
        "index_file": index_path.name,
        "index_sha256": sha256_bytes(encoded),
        "record_count": len(records),
        "parser": "pdftotext -layout + strict three-column row regex",
        "notes": (
            "Index is Codlog + SQ -> vm2t from Annex II. It is an input to "
            "valuation logic, not the official IPTU amount or assessed value."
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
