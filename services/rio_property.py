#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
import municipality_utilities

ROOT=Path("/srv/lotediretor/app")
PARCEL="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadParcel/IMOVEIS_TERRITORIAIS/FeatureServer/0"
ZBASE="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Urbanismo/LBB_Zoneamento_urbano_vigente/FeatureServer"
BOUNDS=(-43.82,-23.10,-43.05,-22.72)
PF=["objectid","num_projeto","paa","tipo_parcelamento","rgi","observacao","inscricao_imobiliaria","matricula","origem","tipo_do_lote","classificacao","quadra","lote","categoria","lote_vinculado","data_doacao","area_descrita","data_verificacao","justificativa","publicacao"]
ZF=["objectid","legislacao","zona","subzona","sigla","ap","cab","obs_cab","cam","obs_cam","to_","obs_to","lote_min","obs_lote_min","testada_min","obs_testada_min","gab_afast","obs_gab_afast","gab_n_afast","obs_gab_n_afast","afast_fron","obs_afast_fron","ics","obs_ics","obs_riu","obs"]
MF=["objectid_1","objectid","macrozona"]
LABEL={"identity":"Identidade","land":"Terreno","building":"Edificação","IPTU":"IPTU","PGV":"PGV","ITBI":"ITBI","registry reference":"Registro imobiliário","zoning":"Zoneamento","urban parameters":"Parâmetros urbanísticos","permits":"Licenciamento","habite-se":"Habite-se","environment":"Ambiental","risk":"Risco","heritage":"Patrimônio","electricity":"Energia","gas":"Gás","water/sewer":"Água e esgoto","drainage":"Drenagem","telecom":"Telecom","transport":"Sistema viário","imagery":"Imagens","terrain":"Terreno/topografia","public works":"Obras públicas","public processes":"Processos públicos","official gazette":"Diário Oficial","historical data":"Histórico"}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"LoteDiretor/0.1 (+https://lotediretor.com)","Accept":"application/json, application/geo+json"})
    with urllib.request.urlopen(req,timeout=15) as r: raw=r.read(6000001)
    if len(raw)>6000000: raise RuntimeError("response_too_large")
    d=json.loads(raw)
    if d.get("error"): raise RuntimeError("arcgis_error")
    return d

def query(url,fields,lat=None,lng=None,where=None,geometry=True,count=20):
    q={"f":"geojson","outSR":"4326","returnGeometry":"true" if geometry else "false","outFields":",".join(fields),"resultRecordCount":str(count)}
    if where is None:q.update({"geometry":f"{lng},{lat}","geometryType":"esriGeometryPoint","inSR":"4326","spatialRel":"esriSpatialRelIntersects"})
    else:q["where"]=where
    d=get(url+"/query?"+urllib.parse.urlencode(q));a=set(fields);out=[]
    for f in d.get("features") or []:
        p=f.get("properties") or {}
        if set(p)-a: raise RuntimeError("unexpected_fields")
        out.append({"type":"Feature","id":f.get("id"),"geometry":f.get("geometry"),"properties":p})
    return out

def date(v):
    if not isinstance(v,(int,float)): return None
    return datetime.fromtimestamp(v/1000,timezone.utc).date().isoformat()

def public(f):
    p=f["properties"]; ident=p.get("inscricao_imobiliaria") or p.get("rgi") or str(p.get("objectid"))
    return {"type":"Feature","id":f"rio-{p.get('objectid')}","geometry":f.get("geometry"),"properties":{
        "municipal_parcel_feature_id":p.get("objectid"),"sql_reference":ident,"inscricao_imobiliaria":p.get("inscricao_imobiliaria"),
        "rgi":p.get("rgi"),"matricula":p.get("matricula"),"project_number":p.get("num_projeto"),"paa":p.get("paa"),
        "parceling_type":p.get("tipo_parcelamento"),"origin":p.get("origem"),"parcel_type":p.get("tipo_do_lote"),
        "classification":p.get("classificacao"),"fiscal_block":p.get("quadra"),"fiscal_lot":p.get("lote"),
        "category":p.get("categoria"),"linked_lot":p.get("lote_vinculado"),"donation_date":date(p.get("data_doacao")),
        "land_area_m2":p.get("area_descrita"),"verification_date":date(p.get("data_verificacao")),
        "publication_date":date(p.get("publicacao")),"observation":p.get("observacao"),"justification":p.get("justificativa"),
        "street":None,"number":None,"built_area_m2":None,"use_description":None,"cib":None,"cib_status":None,
        "parcel_status":p.get("classificacao"),"complement":None}}

def point(lat,lng):
    a,b,c,d=BOUNDS
    if not(b<=lat<=d and a<=lng<=c): raise ValueError("outside_rio_bounds")
    fs=query(PARCEL,PF,lat=lat,lng=lng,count=10)
    return public(fs[0]) if fs else None

def context(lat,lng,parcel):
    errors={}
    try:z=(query(ZBASE+"/0",ZF,lat=lat,lng=lng,geometry=False,count=10) or [{}])[0].get("properties") or {}
    except Exception as e:z={};errors["zoning"]=type(e).__name__
    try:m=(query(ZBASE+"/1",MF,lat=lat,lng=lng,geometry=False,count=10) or [{}])[0].get("properties") or {}
    except Exception as e:m={};errors["macrozone"]=type(e).__name__
    p=parcel["properties"]; refs=[]
    if p.get("matricula"):refs.append({"registry_office":None,"registry_number":p.get("matricula"),"source":"PCRJ CadParcel","verification_date":p.get("verification_date")})
    return {"planning":{"zoning":{"properties":{"cd_zoneamento_perimetro":z.get("sigla") or z.get("zona"),"tx_zoneamento_perimetro":" ".join(x for x in [z.get("zona"),z.get("subzona")] if x),"macrozone":m.get("macrozona"),"legislation":z.get("legislacao"),"ap":z.get("ap"),"ca_basic":z.get("cab"),"ca_max":z.get("cam"),"occupancy":z.get("to_"),"min_lot_area_m2":z.get("lote_min"),"min_frontage_m":z.get("testada_min"),"max_height_setback":z.get("gab_afast"),"max_height_no_setback":z.get("gab_n_afast"),"front_setback":z.get("afast_fron"),"ics":z.get("ics"),"observations":z.get("obs")}},"special_regimes":{}},
    "registry":{"available":bool(refs),"references":refs,"interpretation":"Matrícula/RGI são referências públicas da camada cadastral territorial da PCRJ; não substituem certidão atualizada."},
    "buildings":[],"terrain":{"available":False,"reason":"pending_rio_terrain"},"risk":{"geological":[],"hydrological":[]},"heritage":{"assets":[],"buffers":{}},"utilities":municipality_utilities.load("3304557"),"licensing":{"housing_permits_exact_sql":[],"impact_spatial_incidence":[],"environment_spatial_incidence":[]},
    "fiscal":{"pgv":{"found":False},"iptu":{"found":False,"latest":{}},"itbi":{"available":False,"count":0,"registry_references":[],"transactions":[]}},
    "query_errors":errors,"queried_at":now(),"source":"Prefeitura da Cidade do Rio de Janeiro / Data.Rio"}

def vals(s,p,c):
    q=p["properties"];z=(c["planning"]["zoning"] or {}).get("properties") or {};reg=c.get("registry") or {}
    if s=="executive_summary":return [{"label":"Inscrição imobiliária","value":q.get("inscricao_imobiliaria")},{"label":"RGI","value":q.get("rgi")},{"label":"Matrícula cadastral","value":q.get("matricula")},{"label":"Quadra","value":q.get("fiscal_block")},{"label":"Lote","value":q.get("fiscal_lot")},{"label":"Zona","value":z.get("cd_zoneamento_perimetro")},{"label":"CA básico","value":z.get("ca_basic")},{"label":"CA máximo","value":z.get("ca_max")}]
    if s=="identity_location":return [{"label":"Inscrição imobiliária","value":q.get("inscricao_imobiliaria")},{"label":"RGI","value":q.get("rgi")},{"label":"Projeto","value":q.get("project_number")},{"label":"PAA","value":q.get("paa")},{"label":"Tipo parcelamento","value":q.get("parceling_type")},{"label":"Origem","value":q.get("origin")},{"label":"Tipo do lote","value":q.get("parcel_type")},{"label":"Classificação","value":q.get("classification")},{"label":"Quadra","value":q.get("fiscal_block")},{"label":"Lote","value":q.get("fiscal_lot")},{"label":"Área descrita","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Data verificação","value":q.get("verification_date")},{"label":"Publicação","value":q.get("publication_date")}]
    if s=="planning_buildability":return [{"label":"Macrozona","value":z.get("macrozone")},{"label":"Zona/subzona","value":z.get("tx_zoneamento_perimetro")},{"label":"Sigla","value":z.get("cd_zoneamento_perimetro")},{"label":"Legislação","value":z.get("legislation")},{"label":"AP","value":z.get("ap")},{"label":"CAB","value":z.get("ca_basic")},{"label":"CAM","value":z.get("ca_max")},{"label":"Taxa de ocupação","value":z.get("occupancy")},{"label":"Lote mínimo","value":z.get("min_lot_area_m2"),"unit":"m²"},{"label":"Testada mínima","value":z.get("min_frontage_m"),"unit":"m"},{"label":"Gabarito com afastamento","value":z.get("max_height_setback")},{"label":"Gabarito sem afastamento","value":z.get("max_height_no_setback")},{"label":"Afastamento frontal","value":z.get("front_setback")},{"label":"ICS","value":z.get("ics")}]
    if s=="registry_due_diligence":
        out=[]
        for r in reg.get("references") or []:out.extend([{"label":"Matrícula cadastral publicada","value":r.get("registry_number")},{"label":"Fonte registral","value":r.get("source")},{"label":"Data de verificação cadastral","value":r.get("verification_date")}])
        out.append({"label":"Ressalva","value":reg.get("interpretation")})
        return out
    if s=="infrastructure_utilities":
        return municipality_utilities.report_values(c.get("utilities") or {})
    return []

def report(parcel,ctx):
    spec=json.loads((ROOT/"data/property-dossier/report-spec.json").read_text());m=json.loads((ROOT/"data/deployment/professional-completion-matrix.json").read_text());city=next(x for x in m["first_wave"] if x.get("ibge")=="3304557");rows={r["field"]:r for r in city["rows"]};ss=[]
    for s in sorted(spec["sections"],key=lambda x:x["order"]):
        fields=[{"field":f,"label":LABEL.get(f,f),"status":rows[f].get("status"),"source_id":rows[f].get("source_id"),"connector_status":rows[f].get("connector_status"),"access_class":rows[f].get("access_class"),"missing_fields":rows[f].get("missing_fields") or []} for f in s.get("source_matrix_fields",[]) if f in rows]
        v=[x for x in vals(s["id"],parcel,ctx) if x.get("value") not in (None,"")]
        ss.append({"id":s["id"],"title":s["title"],"order":s["order"],"section_type":s.get("section_type"),"actual_values":v,"fields":fields})
    return {"title":spec["title"],"target_completion_level":spec["target_completion_level"],"principle":spec["principle"],"mode":"PUBLIC_PROPERTY_REPORT","sections":ss}

def centroid(g):
    c=g.get("coordinates") or [];ring=c[0] if g.get("type")=="Polygon" and c else (c[0][0] if g.get("type")=="MultiPolygon" and c and c[0] else [])
    pts=ring[:-1] if len(ring)>1 and ring[0]==ring[-1] else ring
    return {"lat":sum(x[1] for x in pts)/len(pts),"lng":sum(x[0] for x in pts)/len(pts)}

def search(q):
    raw=(q or "").strip()
    if not raw:raise ValueError("unsupported_search_format")
    safe=raw.replace("'","''")
    clauses=[f"inscricao_imobiliaria='{safe}'",f"matricula='{safe}'",f"rgi='{safe}'"]
    fs=query(PARCEL,PF,where=" OR ".join(clauses),count=20)
    return [{"feature":public(x),"representative_point":centroid(x.get("geometry") or {})} for x in fs]

def response_for_point(lat,lng):
    p=point(lat,lng)
    if not p:return None
    c=context(lat,lng,p)
    return {"found":True,"clicked":{"lat":lat,"lng":lng},"feature":p,"context":c,"source":{"id":"rj-rio-cadparcel-imoveis-territoriais","authority":"Prefeitura da Cidade do Rio de Janeiro","layer":"CadParcel/IMOVEIS_TERRITORIAIS/FeatureServer/0","license":"Uso público com citação da fonte e preservação das informações originais","queried_at":now(),"method":"ArcGIS point-intersection + closed allowlist"},"report":report(p,c)}
