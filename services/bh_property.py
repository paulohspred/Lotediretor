#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
import municipality_utilities
from shapely.geometry import Point,shape

ROOT=Path("/srv/lotediretor/app")
WFS="https://bhmap.pbh.gov.br/v2/api/idebhgeo/wfs"
BOUNDS=(-44.10,-20.10,-43.80,-19.75)
LAYERS={
 "parcel":("ide_bhgeo:LOTE_CTM",["ID_LT","NULOTCTM","ID_QUADRA_CTM","AREA_M2","GEOMETRIA"]),
 "approved":("ide_bhgeo:LOTE_APROVADO",["ID_LCP","ZONA_FISCAL","QUARTEIRAO","LOTE","PLANTA_CP","GEOMETRIA"]),
 "zoning":("ide_bhgeo:ZONEAMENTO_11181",["ID_ZONEAMENTO","DESC_TIPO_ZONEAMENTO","SIGLA_TIPO_ZONEAMENTO","GEOMETRIA"])
}
LABEL={"identity":"Identidade","land":"Terreno","building":"Edificação","IPTU":"IPTU","PGV":"PGV","ITBI":"ITBI","registry reference":"Registro imobiliário","zoning":"Zoneamento","urban parameters":"Parâmetros urbanísticos","permits":"Licenciamento","habite-se":"Habite-se","environment":"Ambiental","risk":"Risco","heritage":"Patrimônio","electricity":"Energia","gas":"Gás","water/sewer":"Água e esgoto","drainage":"Drenagem","telecom":"Telecom","transport":"Sistema viário","imagery":"Imagens","terrain":"Terreno/topografia","public works":"Obras públicas","public processes":"Processos públicos","official gazette":"Diário Oficial","historical data":"Histórico"}

def now():return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def request(params):
    url=WFS+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"LoteDiretor/0.1 (+https://lotediretor.com)","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=15) as r: raw=r.read(5000001)
    if len(raw)>5000000:raise RuntimeError("bh_wfs_response_too_large")
    return json.loads(raw)

def query(key,lat=None,lng=None,cql=None,count=50):
    typename,fields=LAYERS[key]
    q={"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":typename,"srsName":"EPSG:4326","count":str(count),"propertyName":",".join(fields),"outputFormat":"application/json"}
    if cql:q["CQL_FILTER"]=cql
    else:
        d=.0005
        q["bbox"]=f"{lng-d},{lat-d},{lng+d},{lat+d},EPSG:4326"
    data=request(q);allowed=set(fields)-{"GEOMETRIA"};out=[]
    for f in data.get("features") or []:
        p=f.get("properties") or {}
        if set(p)-allowed:raise RuntimeError("bh_unexpected_fields")
        out.append({"type":"Feature","id":f.get("id"),"geometry":f.get("geometry"),"properties":p})
    return out

def contains(feature,lat,lng):
    g=feature.get("geometry")
    return bool(g and (shape(g).contains(Point(lng,lat)) or shape(g).touches(Point(lng,lat))))

def public(f):
    p=f["properties"]
    return {"type":"Feature","id":f"bh-{p.get('ID_LT')}","geometry":f.get("geometry"),"properties":{
        "municipal_parcel_feature_id":p.get("ID_LT"),"sql_reference":p.get("NULOTCTM"),
        "ctm_number":p.get("NULOTCTM"),"ctm_block_id":p.get("ID_QUADRA_CTM"),
        "land_area_m2":p.get("AREA_M2"),"fiscal_sector":None,"fiscal_block":None,"fiscal_lot":None,
        "street":None,"number":None,"built_area_m2":None,"use_description":None,"cib":None,
        "cib_status":None,"parcel_status":"LOTE_CTM","parcel_type":"CTM","complement":None}}

def point(lat,lng):
    a,b,c,d=BOUNDS
    if not(b<=lat<=d and a<=lng<=c):raise ValueError("outside_bh_bounds")
    fs=query("parcel",lat=lat,lng=lng)
    f=next((x for x in fs if contains(x,lat,lng)),None)
    return public(f) if f else None

def spatial(key,lat,lng):
    return [x for x in query(key,lat=lat,lng=lng) if contains(x,lat,lng)]

def context(lat,lng,parcel):
    errors={}
    try:approved=spatial("approved",lat,lng)
    except Exception as e:approved=[];errors["approved_lot"]=type(e).__name__
    try:zoning=spatial("zoning",lat,lng)
    except Exception as e:zoning=[];errors["zoning"]=type(e).__name__
    z=(zoning[0].get("properties") if zoning else {}) or {}
    return {"planning":{"zoning":{"properties":{"cd_zoneamento_perimetro":z.get("SIGLA_TIPO_ZONEAMENTO"),"tx_zoneamento_perimetro":z.get("DESC_TIPO_ZONEAMENTO"),"source_layer":"ZONEAMENTO_11181"}},"special_regimes":{}},
    "approved_parcel":approved,"buildings":[],"terrain":{"available":False,"reason":"pending_bh_terrain"},
    "risk":{"geological":[],"hydrological":[]},"heritage":{"assets":[],"buffers":{}},"utilities":municipality_utilities.load("3106200"),
    "licensing":{"housing_permits_exact_sql":[],"impact_spatial_incidence":[],"environment_spatial_incidence":[]},
    "fiscal":{"pgv":{"found":False},"iptu":{"found":False,"latest":{}},"itbi":{"available":False,"count":0,"registry_references":[],"transactions":[]}},
    "query_errors":errors,"queried_at":now(),"source":"Prefeitura de Belo Horizonte / IDE-BHGEO"}

def vals(s,p,c):
    q=p["properties"];z=(c["planning"]["zoning"] or {}).get("properties") or {};approved=c.get("approved_parcel") or []
    if s=="executive_summary":return [{"label":"Lote CTM","value":q.get("ctm_number")},{"label":"Área do lote","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Zoneamento","value":z.get("cd_zoneamento_perimetro")},{"label":"Descrição","value":z.get("tx_zoneamento_perimetro")}]
    if s=="identity_location":
        out=[{"label":"Lote CTM","value":q.get("ctm_number")},{"label":"ID lote CTM","value":q.get("municipal_parcel_feature_id")},{"label":"ID quadra CTM","value":q.get("ctm_block_id")},{"label":"Área CTM","value":q.get("land_area_m2"),"unit":"m²"}]
        for x in approved[:5]:
            r=x.get("properties") or {};out.extend([{"label":"Zona fiscal · lote aprovado","value":r.get("ZONA_FISCAL")},{"label":"Quarteirão · lote aprovado","value":r.get("QUARTEIRAO")},{"label":"Lote aprovado","value":r.get("LOTE")},{"label":"Planta CP","value":r.get("PLANTA_CP")}])
        return out
    if s=="planning_buildability":return [{"label":"Zoneamento Lei 11.181","value":z.get("cd_zoneamento_perimetro")},{"label":"Descrição do zoneamento","value":z.get("tx_zoneamento_perimetro")},{"label":"Camada","value":z.get("source_layer")}]
    if s=="infrastructure_utilities":
        return municipality_utilities.report_values(c.get("utilities") or {})
    return []

def report(parcel,ctx):
    spec=json.loads((ROOT/"data/property-dossier/report-spec.json").read_text());m=json.loads((ROOT/"data/deployment/professional-completion-matrix.json").read_text());city=next(x for x in m["first_wave"] if x.get("ibge")=="3106200");rows={r["field"]:r for r in city["rows"]};ss=[]
    for s in sorted(spec["sections"],key=lambda x:x["order"]):
        fields=[{"field":f,"label":LABEL.get(f,f),"status":rows[f].get("status"),"source_id":rows[f].get("source_id"),"connector_status":rows[f].get("connector_status"),"access_class":rows[f].get("access_class"),"missing_fields":rows[f].get("missing_fields") or []} for f in s.get("source_matrix_fields",[]) if f in rows]
        v=[x for x in vals(s["id"],parcel,ctx) if x.get("value") not in (None,"")]
        ss.append({"id":s["id"],"title":s["title"],"order":s["order"],"section_type":s.get("section_type"),"actual_values":v,"fields":fields})
    return {"title":spec["title"],"target_completion_level":spec["target_completion_level"],"principle":spec["principle"],"mode":"PUBLIC_PROPERTY_REPORT","sections":ss}

def centroid(g):
    p=shape(g).representative_point()
    return {"lat":p.y,"lng":p.x}

def search(q):
    v=re.sub(r"[^0-9A-Za-z]","",q or "")
    if not v:raise ValueError("unsupported_search_format")
    fs=query("parcel",cql=f"NULOTCTM='{v}'",count=20)
    return [{"feature":public(x),"representative_point":centroid(x["geometry"])} for x in fs]

def response_for_point(lat,lng):
    p=point(lat,lng)
    if not p:return None
    c=context(lat,lng,p)
    return {"found":True,"clicked":{"lat":lat,"lng":lng},"feature":p,"context":c,"source":{"id":"mg-bh-bhgeo-lote-ctm","authority":"Prefeitura de Belo Horizonte / BHGEO","layer":"ide_bhgeo:LOTE_CTM","license":"PUBLIC_GEOWEB_SERVICE","queried_at":now(),"method":"WFS bbox candidate + point-in-polygon with closed allowlist"},"report":report(p,c)}
