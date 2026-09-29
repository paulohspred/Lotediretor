#!/usr/bin/env python3
from __future__ import annotations
import csv, pathlib, re, subprocess, tempfile, urllib.request

SOURCE_URL = "https://portal.barueri.sp.gov.br/arquivos/sites/sm/2025/Plano_de_Adaptacao_e_Resiliencia_Climatica_rev1.pdf"
EXPECTED = {"ESC": 175, "INU": 72, "SOL": 1}
TARGET = "ld_stage.barueri_risk_reference_points"

def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, **kwargs)

def main():
    cache = pathlib.Path("/srv/lotediretor/app/data/cache/barueri")
    cache.mkdir(parents=True, exist_ok=True)
    pdf = cache / "PLANO_RESILIENCIA_2025.pdf"
    if not pdf.exists():
        urllib.request.urlretrieve(SOURCE_URL, pdf)

    txt = cache / "barueri_risk_table_layout.txt"
    run(["pdftotext", "-f", "89", "-l", "112", "-layout", str(pdf), str(txt)])
    body = txt.read_text(errors="replace")
    pattern = re.compile(r"BAR/\d{3}/\d{3}(?:\.\d{2})?/(?:INU|ESC|SOL)/\s*R\d")
    starts = list(pattern.finditer(body))
    rows = []
    for i, match in enumerate(starts):
        chunk = body[match.start() : starts[i + 1].start() if i + 1 < len(starts) else len(body)]
        code = re.sub(r"\s+", "", match.group(0))
        coords = re.search(r"(7\.\d{3}\.\d{3})\s+(\d{3}\.\d{3})\s+(\d+)\b", chunk)
        if not coords:
            raise SystemExit(f"registro sem coordenadas publicadas: {code}")
        north = int(coords.group(1).replace(".", ""))
        east = int(coords.group(2).replace(".", ""))
        area = int(coords.group(3))
        process = "inundacao" if "/INU/" in code else "escorregamento" if "/ESC/" in code else "solapamento"
        process_code = "INU" if "/INU/" in code else "ESC" if "/ESC/" in code else "SOL"
        risk_level = code.rsplit("/", 1)[-1]
        parent_area = code.split("/")[1]
        raw = " ".join(chunk.split())
        rows.append((code, parent_area, process_code, process, risk_level, east, north, area, raw))

    from collections import Counter
    counts = Counter(row[2] for row in rows)
    if len(rows) != 248 or dict(counts) != EXPECTED:
        raise SystemExit(f"contagem inesperada: total={len(rows)} por_processo={dict(counts)}")

    csv_path = cache / "barueri_risk_reference_points.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["risk_code","parent_area","process_code","process","risk_level","utm_e","utm_n","published_area_m2","raw_published_row"])
        w.writerows(rows)

    sql = f"""
BEGIN;
CREATE SCHEMA IF NOT EXISTS ld_stage;
DROP TABLE IF EXISTS {TARGET};
CREATE TABLE {TARGET} (
  risk_code text PRIMARY KEY,
  parent_area text NOT NULL,
  process_code text NOT NULL CHECK (process_code IN ('ESC','INU','SOL')),
  process text NOT NULL,
  risk_level text NOT NULL,
  utm_e integer NOT NULL,
  utm_n integer NOT NULL,
  published_area_m2 integer,
  raw_published_row text NOT NULL,
  source_authority text NOT NULL DEFAULT 'Prefeitura Municipal de Barueri · SEMA',
  source_url text NOT NULL DEFAULT '{SOURCE_URL}',
  source_reference text NOT NULL DEFAULT 'Plano Municipal de Adaptação e Resiliência Climática 2025 · Tabela 9; adaptado de Instituto Geológico (2020)',
  geometry_scope text NOT NULL DEFAULT 'REFERENCE_POINT_FROM_PUBLISHED_UTM_COORDINATE',
  geom geometry(Point,4674)
);
COMMIT;
"""
    run(["sudo","-u","postgres","psql","-d","lotediretor","-v","ON_ERROR_STOP=1","-c",sql])
    copy_sql = rf"""\copy {TARGET}(risk_code,parent_area,process_code,process,risk_level,utm_e,utm_n,published_area_m2,raw_published_row) FROM '{csv_path}' CSV HEADER"""
    run(["sudo","-u","postgres","psql","-d","lotediretor","-v","ON_ERROR_STOP=1","-c",copy_sql])
    finish = f"""
BEGIN;
UPDATE {TARGET}
SET geom = ST_Transform(ST_SetSRID(ST_MakePoint(utm_e, utm_n),31983),4674);
ALTER TABLE {TARGET} ALTER COLUMN geom SET NOT NULL;
CREATE INDEX barueri_risk_reference_points_geom_gix ON {TARGET} USING GIST (geom);
CREATE INDEX barueri_risk_reference_points_process_idx ON {TARGET} (process_code, risk_level);
ANALYZE {TARGET};
DO $$
DECLARE c integer; esc integer; inu integer; sol integer;
BEGIN
  SELECT count(*), count(*) FILTER (WHERE process_code='ESC'), count(*) FILTER (WHERE process_code='INU'), count(*) FILTER (WHERE process_code='SOL')
  INTO c, esc, inu, sol FROM {TARGET};
  IF c <> 248 OR esc <> 175 OR inu <> 72 OR sol <> 1 THEN
    RAISE EXCEPTION 'contagem inválida %, %, %, %', c, esc, inu, sol;
  END IF;
  IF EXISTS (
    SELECT 1 FROM {TARGET}
    WHERE ST_X(geom) NOT BETWEEN -47.05 AND -46.70
       OR ST_Y(geom) NOT BETWEEN -23.65 AND -23.40
  ) THEN
    RAISE EXCEPTION 'ponto transformado fora da região esperada de Barueri';
  END IF;
END $$;
GRANT SELECT ON {TARGET} TO sentinelx;
COMMIT;
"""
    run(["sudo","-u","postgres","psql","-d","lotediretor","-v","ON_ERROR_STOP=1","-c",finish])
    print(f"OK {TARGET}: 248 reference points (175 ESC, 72 INU, 1 SOL)")

if __name__ == "__main__":
    main()
