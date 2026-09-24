#!/usr/bin/env python3
"""Materialize São Paulo public ITBI transparency files into SQLite.

Source:
  Secretaria Municipal da Fazenda — Dados das Transações Imobiliárias
  com recolhimento de ITBI-IV.

The public materialization intentionally excludes any person/name/document
fields. It stores only property-, registry-, transaction- and current-IPTU
attributes present in the official public workbook.

Default public horizon: last five exercises (2022-2026), matching the
transparency horizon established by municipal law. Older official files can
be materialized explicitly with --years.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

INDEX_URL = "https://www2.prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501"
DEFAULT_YEARS = [2022, 2023, 2024, 2025, 2026]
USER_AGENT = "Mozilla/5.0 LoteDiretor/0.1 (+https://lotediretor.com)"

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


FIELD_ALIASES = {
    "sql": ["N° do Cadastro (SQL)", "Nº do Cadastro (SQL)", "N do Cadastro (SQL)"],
    "street": ["Nome do Logradouro"],
    "number": ["Número", "Número do Imóvel"],
    "complement": ["Complemento", "Complemento do Imóvel"],
    "neighborhood": ["Bairro"],
    "reference": ["Referência"],
    "cep": ["CEP"],
    "transaction_nature": ["Natureza de Transação"],
    "transaction_value": ["Valor de Transação (declarado pelo contribuinte)"],
    "transaction_date": ["Data de Transação"],
    "vvr": ["Valor Venal de Referência"],
    "transmitted_pct": ["Proporção Transmitida (%)"],
    "vvr_proportional": ["Valor Venal de Referência (proporcional)"],
    "tax_base": ["Base de Cálculo adotada"],
    "financing_type": ["Tipo de Financiamento"],
    "financed_value": ["Valor Financiado"],
    "registry_office": ["Cartório de Registro"],
    "registry_number": ["Matrícula do Imóvel"],
    "sql_status": ["Situação do SQL"],
    "land_area_m2": ["Área do Terreno (m2)", "Área do Terreno (m²)"],
    "frontage_m": ["Testada (m)"],
    "ideal_fraction": ["Fração Ideal"],
    "built_area_m2": ["Área Construída (m2)", "Área Construída (m²)"],
    "use_code": ["Uso (IPTU)"],
    "use_description": ["Descrição do uso (IPTU)"],
    "pattern_code": ["Padrão (IPTU)"],
    "pattern_description": [
        "Descrição do padrão (IPTU)",
        "Descrição do pardão (IPTU)",
    ],
    "construction_year": ["ACC (IPTU)"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def allowed_host(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host == "prefeitura.sp.gov.br" or host.endswith(".prefeitura.sp.gov.br")


def fetch(url: str, *, referer: str | None = None, timeout: int = 120) -> tuple[bytes, str]:
    if not allowed_host(url):
        raise ValueError(f"host not allowed: {url}")
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        if not allowed_host(final_url):
            raise ValueError(f"redirect host not allowed: {final_url}")
        body = response.read()
    return body, final_url


def discover_xlsx_links(index_html: str) -> dict[int, str]:
    links: dict[int, str] = {}
    pattern = re.compile(
        r"<li[^>]*>\s*<strong>\s*(20\d{2}|200\d)\s*"
        r"\(\s*<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>\s*Excel/xlsx\s*</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for year_raw, href in pattern.findall(index_html):
        year = int(year_raw)
        url = urllib.parse.urljoin(INDEX_URL, html.unescape(href))
        url = url.replace("http://", "https://", 1)
        parts = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit((
            parts.scheme,
            parts.netloc,
            urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/()%-._~"),
            parts.query,
            parts.fragment,
        ))
        links[year] = url
    if len(links) < 5:
        raise ValueError(f"ITBI index discovery returned only {len(links)} XLSX links")
    return links


def qn(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def normalize_header(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_sql(value: object) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None
    if len(digits) <= 11:
        digits = digits.zfill(11)
    return digits if len(digits) == 11 else None


def to_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def excel_serial_to_iso(value: object) -> str | None:
    number = to_float(value)
    if number is None:
        text = str(value or "").strip()
        return text or None
    if number < 1:
        return None
    date = datetime(1899, 12, 30) + timedelta(days=number)
    return date.date().isoformat()


def parse_workbook(path: Path):
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(qn(MAIN_NS, "si")):
                shared.append("".join(t.text or "" for t in si.iter(qn(MAIN_NS, "t"))))

        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall(qn(PKG_REL_NS, "Relationship"))
        }

        sheets: list[tuple[str, str]] = []
        for sheet in workbook.find(qn(MAIN_NS, "sheets")):
            rid = sheet.attrib[qn(REL_NS, "id")]
            target = relmap[rid]
            path_name = target.lstrip("/") if target.startswith("/") else "xl/" + target
            path_name = path_name.replace("xl/worksheets/../", "xl/")
            sheets.append((sheet.attrib["name"], path_name))

        def cell_value(cell: ET.Element):
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                inline = cell.find(qn(MAIN_NS, "is"))
                if inline is None:
                    return ""
                return "".join(t.text or "" for t in inline.iter(qn(MAIN_NS, "t")))
            value = cell.find(qn(MAIN_NS, "v"))
            if value is None:
                return ""
            raw = value.text or ""
            if cell_type == "s":
                try:
                    return shared[int(raw)]
                except (ValueError, IndexError):
                    return raw
            return raw

        for sheet_name, sheet_path in sheets:
            if sheet_name.upper() in {"LEGENDA", "EXPLICAÇÕES", "EXPLICACOES", "TABELA DE USOS", "TABELA DE PADRÕES"}:
                continue

            headers: dict[str, str] | None = None
            with z.open(sheet_path) as fh:
                for _, row in ET.iterparse(fh, events=("end",)):
                    if row.tag != qn(MAIN_NS, "row"):
                        continue
                    row_number = int(row.attrib.get("r", "0") or 0)
                    cells = {}
                    for cell in row.findall(qn(MAIN_NS, "c")):
                        ref = cell.attrib.get("r", "")
                        match = re.match(r"[A-Z]+", ref)
                        if not match:
                            continue
                        cells[match.group()] = cell_value(cell)
                    row.clear()
                    if not cells:
                        continue

                    if headers is None:
                        headers = {col: normalize_header(value) for col, value in cells.items()}
                        continue

                    values_by_header = {
                        headers[col]: value
                        for col, value in cells.items()
                        if col in headers
                    }
                    yield sheet_name, row_number, values_by_header


def field_value(row: dict[str, object], field: str):
    for header in FIELD_ALIASES[field]:
        if header in row:
            return row.get(header)
    return None


def init_db(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS source_files (
            year INTEGER PRIMARY KEY,
            source_url TEXT NOT NULL,
            final_url TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            transaction_rows INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            source_year INTEGER NOT NULL,
            source_sheet TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            sql TEXT,
            street TEXT,
            number TEXT,
            complement TEXT,
            neighborhood TEXT,
            reference TEXT,
            cep TEXT,
            transaction_nature TEXT,
            transaction_value REAL,
            transaction_date TEXT,
            vvr REAL,
            transmitted_pct REAL,
            vvr_proportional REAL,
            tax_base REAL,
            financing_type TEXT,
            financed_value REAL,
            registry_office TEXT,
            registry_number TEXT,
            sql_status TEXT,
            land_area_m2 REAL,
            frontage_m REAL,
            ideal_fraction REAL,
            built_area_m2 REAL,
            use_code TEXT,
            use_description TEXT,
            pattern_code TEXT,
            pattern_description TEXT,
            construction_year INTEGER,
            source_file_sha256 TEXT NOT NULL,
            UNIQUE(source_year, source_sheet, source_row)
        );

        CREATE INDEX IF NOT EXISTS idx_itbi_sql_date
        ON transactions(sql, transaction_date DESC);

        CREATE INDEX IF NOT EXISTS idx_itbi_registry
        ON transactions(registry_office, registry_number);
        """
    )


INSERT_SQL = """
INSERT OR REPLACE INTO transactions (
    source_year, source_sheet, source_row, sql, street, number, complement,
    neighborhood, reference, cep, transaction_nature, transaction_value,
    transaction_date, vvr, transmitted_pct, vvr_proportional, tax_base,
    financing_type, financed_value, registry_office, registry_number,
    sql_status, land_area_m2, frontage_m, ideal_fraction, built_area_m2,
    use_code, use_description, pattern_code, pattern_description,
    construction_year, source_file_sha256
) VALUES (
    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
)
"""


def materialize_year(
    db: sqlite3.Connection,
    out_dir: Path,
    year: int,
    url: str,
) -> dict:
    raw, final_url = fetch(url, referer=INDEX_URL)
    if not raw.startswith(b"PK"):
        raise ValueError(f"{year}: downloaded resource is not XLSX")

    xlsx_path = out_dir / f"itbi-{year}.xlsx"
    xlsx_path.write_bytes(raw)
    digest = sha256_file(xlsx_path)

    db.execute("DELETE FROM transactions WHERE source_year = ?", (year,))
    count = 0
    for sheet_name, row_number, row in parse_workbook(xlsx_path):
        sql = normalize_sql(field_value(row, "sql"))
        if not sql:
            continue

        record = (
            year,
            sheet_name,
            row_number,
            sql,
            str(field_value(row, "street") or "").strip() or None,
            str(field_value(row, "number") or "").strip() or None,
            str(field_value(row, "complement") or "").strip() or None,
            str(field_value(row, "neighborhood") or "").strip() or None,
            str(field_value(row, "reference") or "").strip() or None,
            re.sub(r"\D", "", str(field_value(row, "cep") or "")) or None,
            str(field_value(row, "transaction_nature") or "").strip() or None,
            to_float(field_value(row, "transaction_value")),
            excel_serial_to_iso(field_value(row, "transaction_date")),
            to_float(field_value(row, "vvr")),
            to_float(field_value(row, "transmitted_pct")),
            to_float(field_value(row, "vvr_proportional")),
            to_float(field_value(row, "tax_base")),
            str(field_value(row, "financing_type") or "").strip() or None,
            to_float(field_value(row, "financed_value")),
            str(field_value(row, "registry_office") or "").strip() or None,
            str(field_value(row, "registry_number") or "").strip() or None,
            str(field_value(row, "sql_status") or "").strip() or None,
            to_float(field_value(row, "land_area_m2")),
            to_float(field_value(row, "frontage_m")),
            to_float(field_value(row, "ideal_fraction")),
            to_float(field_value(row, "built_area_m2")),
            str(field_value(row, "use_code") or "").strip() or None,
            str(field_value(row, "use_description") or "").strip() or None,
            str(field_value(row, "pattern_code") or "").strip() or None,
            str(field_value(row, "pattern_description") or "").strip() or None,
            to_int(field_value(row, "construction_year")),
            digest,
        )
        db.execute(INSERT_SQL, record)
        count += 1
        if count % 5000 == 0:
            db.commit()

    db.execute(
        """
        INSERT OR REPLACE INTO source_files
        (year, source_url, final_url, captured_at, sha256, bytes, transaction_rows)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (year, url, final_url, utc_now(), digest, len(raw), count),
    )
    db.commit()
    return {
        "year": year,
        "source_url": url,
        "final_url": final_url,
        "sha256": digest,
        "bytes": len(raw),
        "transaction_rows": count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--years",
        default=",".join(str(year) for year in DEFAULT_YEARS),
        help="comma-separated years, or 'all'",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    index_raw, _ = fetch(INDEX_URL)
    index_html = index_raw.decode("utf-8", errors="replace")
    links = discover_xlsx_links(index_html)

    if args.years.strip().lower() == "all":
        years = sorted(links)
    else:
        years = sorted({int(value.strip()) for value in args.years.split(",") if value.strip()})

    missing = [year for year in years if year not in links]
    if missing:
        raise SystemExit(f"years missing from official index: {missing}")

    db_path = args.out / "itbi-transactions.sqlite3"
    db = sqlite3.connect(db_path)
    init_db(db)

    results = []
    for year in years:
        result = materialize_year(db, args.out, year, links[year])
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    total = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    sql_count = db.execute("SELECT COUNT(DISTINCT sql) FROM transactions").fetchone()[0]
    source_rows = db.execute(
        """SELECT year, source_url, final_url, captured_at, sha256, bytes,
                  transaction_rows
           FROM source_files
           ORDER BY year"""
    ).fetchall()
    coverage_years = [row[0] for row in source_rows]
    all_files = [
        {
            "year": row[0],
            "source_url": row[1],
            "final_url": row[2],
            "captured_at": row[3],
            "sha256": row[4],
            "bytes": row[5],
            "transaction_rows": row[6],
        }
        for row in source_rows
    ]
    manifest = {
        "schema_version": "0.1.0",
        "source_id": "sp-sao-paulo-itbi-transactions",
        "index_url": INDEX_URL,
        "captured_at": utc_now(),
        "years": coverage_years,
        "transaction_rows": total,
        "distinct_sql": sql_count,
        "database": db_path.name,
        "database_sha256": sha256_file(db_path),
        "files": all_files,
        "privacy": {
            "person_names": "not materialized",
            "cpf_cnpj": "not materialized",
            "public_fields_only": True,
        },
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
