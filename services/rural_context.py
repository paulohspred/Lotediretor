"""Rural SIGEF/CAR context using only public non-personal attributes."""
from __future__ import annotations
import json, os
import psycopg2

DB_DSN=os.environ.get("LOTEDIRETOR_DB_DSN","dbname=lotediretor user=sentinelx host=/var/run/postgresql")

def load(lng: float, lat: float) -> dict:
    with psycopg2.connect(DB_DSN) as conn, conn.cursor() as cur:
        cur.execute("select ld_api.rural_context(%s,%s)",(lng,lat))
        row=cur.fetchone()
    return row[0] if row and row[0] else {"sigef":None,"car":None,"restrictions":[],"warnings":[]}

def report_values(ctx: dict) -> list[dict]:
    out=[]
    sig=ctx.get("sigef")
    if sig:
        out += [
          {"label":"Parcela SIGEF certificada","value":sig.get("parcel_code")},
          {"label":"Situação pública SIGEF","value":sig.get("status")},
          {"label":"Área SIGEF","value":sig.get("area_ha"),"unit":"ha"},
        ]
    car=ctx.get("car")
    if car:
        out += [
          {"label":"Código CAR","value":car.get("car_code")},
          {"label":"Situação pública CAR","value":car.get("status")},
          {"label":"Área declarada CAR","value":car.get("area_ha"),"unit":"ha"},
          {"label":"Tipo do imóvel rural","value":car.get("property_type")},
        ]
    for r in ctx.get("restrictions") or []:
        relation="intersecta" if r.get("intersects") else f"a {float(r.get('distance_m') or 0):.1f} m"
        out.append({"label":f"{r.get('theme')} · {r.get('label') or 'feição oficial'}",
                    "value":f"{relation}. Fonte: {r.get('authority')}. Carga: {str(r.get('loaded_at') or '')[:10]}."})
    for w in ctx.get("warnings") or []:
        out.append({"label":"Aviso de interpretação","value":w})
    if not out:
        out.append({"label":"Cadastro rural","value":"Nenhuma parcela SIGEF/CAR ativa contém o ponto consultado."})
    return out
