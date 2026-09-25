#!/usr/bin/env python3
from __future__ import annotations
import json, sqlite3
from pathlib import Path
from shapely.geometry import Point, shape

DB=Path("/srv/lotediretor/data/recife/index/recife-property.sqlite3")

def num(v):
    if v in (None,""): return None
    if isinstance(v,(int,float)): return float(v)
    try: return float(str(v).strip().replace(".","").replace(",","."))
    except ValueError: return None

def resolve(parcel):
    out={"iptu":None,"licensing":[],"itbi":[],"coverage":{}}
    if not DB.exists(): return out
    p=parcel.get("properties") or {}
    geom=shape(parcel.get("geometry") or {})
    minx,miny,maxx,maxy=geom.bounds
    db=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=5)
    try:
        out["coverage"]={r[0]:{"captured_at":r[1],"record_count":r[2]} for r in db.execute("select dataset_key,captured_at,record_count from metadata")}
        seq=p.get("seqimovel")
        if seq:
            row=db.execute("select normalized_json from iptu where municipal_tax_reference=?",(str(seq),)).fetchone()
            if row: out["iptu"]=json.loads(row[0])
        dsq=p.get("dsqfl")
        if dsq:
            rows=db.execute("select normalized_json from licensing where dsqfl=? order by upstream_key desc limit 50",(str(dsq),)).fetchall()
            out["licensing"]=[json.loads(r[0]) for r in rows]
        rows=db.execute("""select normalized_json,latitude,longitude from itbi
                           where latitude between ? and ? and longitude between ? and ?
                           order by transaction_date desc limit 300""",(miny,maxy,minx,maxx)).fetchall()
        for raw,lat,lon in rows:
            if lat is None or lon is None: continue
            pt=Point(float(lon),float(lat))
            if geom.contains(pt) or geom.touches(pt):
                out["itbi"].append(json.loads(raw))
    finally:
        db.close()
    return out

def iptu_latest(row):
    if not row: return {}
    land=row.get("land") or {}; b=row.get("building") or {}; f=row.get("fiscal") or {}; a=row.get("address") or {}
    return {
        "land_area_m2":num(land.get("source_land_area_m2")),
        "built_area_m2":num(b.get("source_built_area_m2")),
        "occupied_area_m2":num(b.get("occupied_area_m2")),
        "ideal_fraction":num(land.get("ideal_fraction")),
        "floors":num(b.get("floors")),
        "corrected_construction_year":b.get("construction_year_corrected"),
        "use_description":b.get("use"),
        "construction_pattern":b.get("construction_standard"),
        "construction_type":b.get("construction_type"),
        "enterprise_type":b.get("enterprise_type"),
        "structure_type":b.get("structure_type"),
        "obsolescence_factor":num(b.get("obsolescence_factor")),
        "land_unit_value_brl_m2":num(f.get("land_unit_value_brl_m2")),
        "building_unit_value_brl_m2":num(f.get("building_unit_value_brl_m2")),
        "estimated_total_value_brl":num(f.get("estimated_total_value_brl")),
        "iptu_charged_brl":num(f.get("iptu_charged_brl")),
        "iptu_tax_regime":f.get("iptu_tax_regime"),
        "trsd_tax_regime":f.get("trsd_tax_regime"),
        "neighborhood":a.get("neighborhood"),"cep":a.get("postal_code"),
        "registration_date":row.get("registered_at")
    }

def transactions(rows):
    out=[]
    for row in rows:
        tr=row.get("transaction") or {}; a=row.get("address") or {}; p=row.get("property_attributes") or {}
        out.append({
            "source_year":tr.get("year"),"transaction_date":tr.get("date"),
            "transaction_nature":"ITBI Recife · avaliação publicada",
            "assessed_value":num(tr.get("assessed_value_brl")),
            "financing_type":"SFH" if num(tr.get("sfh")) not in (None,0) else None,
            "financed_value":num(tr.get("sfh")),"registry_office":None,"registry_number":None,
            "land_area_m2":num(p.get("land_area_m2")),"built_area_m2":num(p.get("built_area_m2")),
            "ideal_fraction":num(p.get("ideal_fraction")),"use_description":p.get("occupancy_type"),
            "construction_year":p.get("construction_year"),"property_type":p.get("property_type"),
            "street":a.get("street"),"number":a.get("number"),"match_method":"POINT_INSIDE_OFFICIAL_PARCEL"
        })
    return out

def permits(rows):
    out=[]
    for row in rows:
        p=row.get("permit") or {}; pr=row.get("project") or {}; pa=row.get("parallel_licensing") or {}
        out.append({"properties":{
            "num_licenca":p.get("license_number"),"num_processo":p.get("process_number"),
            "assunto":p.get("subject"),"situacao_processo":p.get("process_status"),
            "tipo_processo":p.get("process_type"),"data_emissao_licenca":p.get("license_issue_date"),
            "data_validade_licenca":p.get("license_valid_until"),"data_conclusao":p.get("completion_date"),
            "areatotalconstruida":pr.get("total_built_area_m2"),"uso_imovel":pr.get("property_use"),
            "licenciamento_urbanistico":pa.get("urban"),"licenciamento_ambiental":pa.get("environmental"),
            "licenciamento_sanitario":pa.get("sanitary")}})
    return out
