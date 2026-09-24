#!/usr/bin/env python3
"""Materialize São Paulo open IPTU fiscal cadastre by exercise into SQLite.

The official GeoSampa public download exposes IPTU_<year>.zip under:
  Cadastro / IPTU_INTER / XLS_CSV

This materializer uses the privacy-filtered public bulk dataset (IPTU_INTER),
not the interactive/captcha-protected integration surface. It intentionally
does not attempt to obtain owner/person fields.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://download.geosampa.prefeitura.sp.gov.br/PaginasPublicas"
APP_URL = BASE + "/_SBC.aspx"
DOWNLOAD_URL = BASE + "/downloadArquivo.aspx"
USER_AGENT = "Mozilla/5.0 LoteDiretor/0.1 (+https://lotediretor.com)"

HEADERS = {
    "sql": "NUMERO DO CONTRIBUINTE",
    "exercise": "ANO DO EXERCICIO",
    "notice_number": "NUMERO DA NL",
    "registration_date": "DATA DO CADASTRAMENTO",
    "condominium": "NUMERO DO CONDOMINIO",
    "street_code": "CODLOG DO IMOVEL",
    "street": "NOME DE LOGRADOURO DO IMOVEL",
    "number": "NUMERO DO IMOVEL",
    "complement": "COMPLEMENTO DO IMOVEL",
    "neighborhood": "BAIRRO DO IMOVEL",
    "reference": "REFERENCIA DO IMOVEL",
    "cep": "CEP DO IMOVEL",
    "corner_front_count": "QUANTIDADE DE ESQUINAS/FRENTES",
    "ideal_fraction": "FRACAO IDEAL",
    "land_area_m2": "AREA DO TERRENO",
    "built_area_m2": "AREA CONSTRUIDA",
    "occupied_area_m2": "AREA OCUPADA",
    "land_unit_value_brl_m2": "VALOR DO M2 DO TERRENO",
    "construction_unit_value_brl_m2": "VALOR DO M2 DE CONSTRUCAO",
    "corrected_construction_year": "ANO DA CONSTRUCAO CORRIGIDO",
    "floors": "QUANTIDADE DE PAVIMENTOS",
    "frontage_m": "TESTADA PARA CALCULO",
    "use_description": "TIPO DE USO DO IMOVEL",
    "construction_pattern": "TIPO DE PADRAO DA CONSTRUCAO",
    "terrain_type": "TIPO DE TERRENO",
    "obsolescence_factor": "FATOR DE OBSOLESCENCIA",
    "life_start_year": "ANO DE INICIO DA VIDA DO CONTRIBUINTE",
    "life_start_month": "MES DE INICIO DA VIDA DO CONTRIBUINTE",
    "contributor_phase": "FASE DO CONTRIBUINTE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_sql(value: str) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 11 else None


def digits_or_none(value: str) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits or None


def text_or_none(value: str) -> str | None:
    text = (value or "").strip()
    return text or None


def to_float(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def to_int(value: str) -> int | None:
    number = to_float(value)
    return None if number is None else int(number)


def official_file_exists(year: int) -> bool:
    payload = json.dumps({
        "pNomePasta": "12_Cadastro\\IPTU_INTER\\XLS_CSV"
    }).encode("utf-8")
    request = urllib.request.Request(
        APP_URL + "/pesquisaArquivos",
        data=payload,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Referer": APP_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response).get("d") or ""
    return f"IPTU_{year}.zip" in result.split("|")


def download_year(year: int) -> tuple[bytes, str]:
    if not official_file_exists(year):
        raise ValueError(f"IPTU_{year}.zip not listed by official GeoSampa app")
    archive = f"IPTU_{year}.zip"
    path = f"12_Cadastro\\IPTU_INTER\\XLS_CSV\\{archive}"
    url = DOWNLOAD_URL + "?" + urllib.parse.urlencode({
        "orig": "DownloadTemas",
        "arq": path,
        "arqTipo": "zip",
    })
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": APP_URL,
            "Accept": "application/zip,application/octet-stream,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        body = response.read(250 * 1024 * 1024 + 1)
        final_url = response.geturl()
    if len(body) > 250 * 1024 * 1024:
        raise ValueError("IPTU ZIP exceeds safety limit")
    if not body.startswith(b"PK"):
        raise ValueError("official IPTU endpoint did not return ZIP")
    return body, final_url


def init_db(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=NORMAL;
        PRAGMA temp_store=MEMORY;

        CREATE TABLE IF NOT EXISTS source_files (
            exercise INTEGER PRIMARY KEY,
            source_url TEXT NOT NULL,
            final_url TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            zip_sha256 TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            row_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cadastre (
            sql TEXT NOT NULL,
            exercise INTEGER NOT NULL,
            notice_number INTEGER,
            registration_date TEXT,
            condominium TEXT,
            street_code TEXT,
            street TEXT,
            number TEXT,
            complement TEXT,
            neighborhood TEXT,
            reference TEXT,
            cep TEXT,
            corner_front_count INTEGER,
            ideal_fraction REAL,
            land_area_m2 REAL,
            built_area_m2 REAL,
            occupied_area_m2 REAL,
            land_unit_value_brl_m2 REAL,
            construction_unit_value_brl_m2 REAL,
            corrected_construction_year INTEGER,
            floors INTEGER,
            frontage_m REAL,
            use_description TEXT,
            construction_pattern TEXT,
            terrain_type TEXT,
            obsolescence_factor REAL,
            life_start_year INTEGER,
            life_start_month INTEGER,
            contributor_phase TEXT,
            source_zip_sha256 TEXT NOT NULL,
            PRIMARY KEY (exercise, sql)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS idx_iptu_sql_exercise
        ON cadastre(sql, exercise DESC);
        """
    )


INSERT_SQL = """
INSERT OR REPLACE INTO cadastre (
    sql, exercise, notice_number, registration_date, condominium,
    street_code, street, number, complement, neighborhood, reference, cep,
    corner_front_count, ideal_fraction, land_area_m2, built_area_m2,
    occupied_area_m2, land_unit_value_brl_m2,
    construction_unit_value_brl_m2, corrected_construction_year, floors,
    frontage_m, use_description, construction_pattern, terrain_type,
    obsolescence_factor, life_start_year, life_start_month,
    contributor_phase, source_zip_sha256
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def materialize(year: int, out: Path, archive_path: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if archive_path is not None:
        raw = archive_path.read_bytes()
        if not raw.startswith(b"PK"):
            raise ValueError("provided IPTU archive is not ZIP")
        final_url = "local-validation-copy:" + str(archive_path)
    else:
        raw, final_url = download_year(year)
    zip_sha = sha256_bytes(raw)
    zip_path = out / f"IPTU_{year}.zip"
    zip_path.write_bytes(raw)

    db_path = out / "iptu-cadastre.sqlite3"
    db = sqlite3.connect(db_path)
    init_db(db)
    db.execute("DELETE FROM cadastre WHERE exercise = ?", (year,))

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        expected = f"IPTU_{year}.csv"
        if expected not in names:
            raise ValueError(f"{expected} missing from official archive")
        info = archive.getinfo(expected)
        if info.file_size > 2 * 1024 * 1024 * 1024:
            raise ValueError("IPTU CSV exceeds safety limit")

        with archive.open(info) as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text, delimiter=";")
            actual = set(reader.fieldnames or [])
            missing = [header for header in HEADERS.values() if header not in actual]
            if missing:
                raise ValueError(f"IPTU schema missing fields: {missing}")

            count = 0
            batch = []
            for row in reader:
                sql = normalize_sql(row[HEADERS["sql"]])
                exercise = to_int(row[HEADERS["exercise"]])
                if not sql or exercise != year:
                    continue
                batch.append((
                    sql,
                    exercise,
                    to_int(row[HEADERS["notice_number"]]),
                    text_or_none(row[HEADERS["registration_date"]]),
                    text_or_none(row[HEADERS["condominium"]]),
                    digits_or_none(row[HEADERS["street_code"]]),
                    text_or_none(row[HEADERS["street"]]),
                    text_or_none(row[HEADERS["number"]]),
                    text_or_none(row[HEADERS["complement"]]),
                    text_or_none(row[HEADERS["neighborhood"]]),
                    text_or_none(row[HEADERS["reference"]]),
                    digits_or_none(row[HEADERS["cep"]]),
                    to_int(row[HEADERS["corner_front_count"]]),
                    to_float(row[HEADERS["ideal_fraction"]]),
                    to_float(row[HEADERS["land_area_m2"]]),
                    to_float(row[HEADERS["built_area_m2"]]),
                    to_float(row[HEADERS["occupied_area_m2"]]),
                    to_float(row[HEADERS["land_unit_value_brl_m2"]]),
                    to_float(row[HEADERS["construction_unit_value_brl_m2"]]),
                    to_int(row[HEADERS["corrected_construction_year"]]),
                    to_int(row[HEADERS["floors"]]),
                    to_float(row[HEADERS["frontage_m"]]),
                    text_or_none(row[HEADERS["use_description"]]),
                    text_or_none(row[HEADERS["construction_pattern"]]),
                    text_or_none(row[HEADERS["terrain_type"]]),
                    to_float(row[HEADERS["obsolescence_factor"]]),
                    to_int(row[HEADERS["life_start_year"]]),
                    to_int(row[HEADERS["life_start_month"]]),
                    text_or_none(row[HEADERS["contributor_phase"]]),
                    zip_sha,
                ))
                count += 1
                if len(batch) >= 10000:
                    db.executemany(INSERT_SQL, batch)
                    db.commit()
                    batch.clear()
            if batch:
                db.executemany(INSERT_SQL, batch)
                db.commit()

    source_url = (
        DOWNLOAD_URL + "?" + urllib.parse.urlencode({
            "orig": "DownloadTemas",
            "arq": f"12_Cadastro\\IPTU_INTER\\XLS_CSV\\IPTU_{year}.zip",
            "arqTipo": "zip",
        })
    )
    db.execute(
        """
        INSERT OR REPLACE INTO source_files
        (exercise, source_url, final_url, captured_at, zip_sha256, bytes, row_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (year, source_url, final_url, utc_now(), zip_sha, len(raw), count),
    )
    db.commit()

    unique_count = db.execute(
        "SELECT COUNT(*) FROM cadastre WHERE exercise = ?",
        (year,),
    ).fetchone()[0]
    manifest = {
        "schema_version": "0.1.0",
        "source_id": "sp-sao-paulo-iptu-cadastro-fiscal",
        "exercise": year,
        "captured_at": utc_now(),
        "zip_file": zip_path.name,
        "zip_sha256": zip_sha,
        "download_bytes": len(raw),
        "parsed_rows": count,
        "unique_sql": unique_count,
        "database": db_path.name,
        "privacy": {
            "surface": "IPTU_INTER public bulk dataset",
            "owner_name": "not present/not materialized",
            "cpf_cnpj": "not present/not materialized",
        },
    }
    (out / f"manifest-{year}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    db.close()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="optional already-downloaded official IPTU_<year>.zip for validation/replay",
    )
    args = parser.parse_args()
    materialize(args.year, args.out, args.archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
