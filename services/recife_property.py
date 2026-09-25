#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("/srv/lotediretor/app")
PARCEL="https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Planejamento/BASES_BAIRRO_FACEQUADRA_LOGRADOURO_LOTE/FeatureServer/3"
ZBASE="https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Planejamento/BASES_ZONEAMENTO_G_PD2020/FeatureServer"
BOUNDS=(-35.10,-8.20,-34.80,-7.88)
PF=["OBJECTID","SITUACAOIMOVEL","DISTRITO","SETOR","QUADRA","FACE","LOTE","ENDNUMERO","V0","AREATOTALCONSTRUIDA","QTDPAVIMENTOS","TIPOEMPREENDIMENTO","AREALOTE","TESTADAPRINCIPAL","SEQIMOVEL","DSQFL","QTDUNHAB","ANCONSTR","QTDMULTIPLAS","NMEDIFICACAO","NMENDCOMP","TLOTESULAT","NMTIPOEMPRENDIMENTO","EFTUTZDESC"]
ZLAYERS={
"zoning":(6,["OBJECTID","MACROZONA","ZONA","ZONA2","VLCOEFMIN","VLCOEFBAS","VLCOEFMAX","NMCONSIDERAC"]),
"iep":(0,["OBJECTID","CDIEP","NMDESCR","NMLEI","DTANOTOMBAMENTO"]),
"zec":(1,["OBJECTID","ID","ZEC"]),
"zeis":(2,["OBJECTID","NMNOME","NMLEI"]),
"zeph":(3,["OBJECTID","NMNOME","NMLEI","TIPO"]),
"ipav":(4,["OBJECTID","COD_IPAV","ENDERECO","LEI","NOME_IPAV"]),
"ucn":(5,["OBJECTID","CDID","CDZONA_NOME","CDZONA_TIPO"]),
"aru":(7,["OBJECTID","ZONA_NOME","ZONA_TIPO","NMCONSIDERAC"])}
LABEL={"identity":"Identidade","land":"Terreno","building":"Edificação","IPTU":"IPTU","PGV":"PGV","ITBI":"ITBI","registry reference":"Registro imobiliário","zoning":"Zoneamento","urban parameters":"Parâmetros urbanísticos","permits":"Licenciamento","habite-se":"Habite-se","environment":"Ambiental","risk":"Risco","heritage":"Patrimônio","electricity":"Energia","gas":"Gás","water/sewer":"Água e esgoto","drainage":"Drenagem","telecom":"Telecom","transport":"Sistema viário","imagery":"Imagens","terrain":"Terreno/topografia","public works":"Obras públicas","public processes":"Processos públicos","official gazette":"Diário Oficial","historical data":"Histórico"}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"LoteDiretor/0.1 (+https://lotediretor.com)","Accept":"application/json, application/geo+json"})
    with urllib.request.urlopen(req,timeout=15) as r:
        raw=r.read(6000001)
    if len(raw)>6000000: raise RuntimeError("response_too_large")
    data=json.loads(raw)
    if data.get("error"): raise RuntimeError("arcgis_error")
    return data

def query(url,fields,lat=None,lng=None,where=None,geometry=True,count=20):
    q={"f":"geojson","outSR":"4326","returnGeometry":"true" if geometry else "false","outFields":",".join(fields),"resultRecordCount":str(count)}
    if where is None:q.update({"geometry":f"{lng},{lat}","geometryType":"esriGeometryPoint","inSR":"4326","spatialRel":"esriSpatialRelIntersects"})
    else:q["where"]=where
    data=get(url+"/query?"+urllib.parse.urlencode(q)); allowed=set(fields); out=[]
    for f in data.get("features") or []:
        p=f.get("properties") or {}
        if set(p)-allowed: raise RuntimeError("unexpected_fields")
        out.append({"type":"Feature","id":f.get("id"),"geometry":f.get("geometry"),"properties":p})
    return out

def public(f):
    p=f["properties"]
    return {"type":"Feature","id":f"recife-{p.get('OBJECTID')}","geometry":f.get("geometry"),"properties":{
        "municipal_parcel_feature_id":p.get("OBJECTID"),"parcel_status":p.get("SITUACAOIMOVEL"),
        "district":p.get("DISTRITO"),"fiscal_sector":p.get("SETOR"),"fiscal_block":p.get("QUADRA"),
        "face":p.get("FACE"),"fiscal_lot":p.get("LOTE"),"number":p.get("ENDNUMERO"),"v0":p.get("V0"),
        "built_area_m2":p.get("AREATOTALCONSTRUIDA"),"floors":p.get("QTDPAVIMENTOS"),
        "land_area_m2":p.get("AREALOTE"),"frontage_m":p.get("TESTADAPRINCIPAL"),
        "seqimovel":str(p.get("SEQIMOVEL")) if p.get("SEQIMOVEL") is not None else None,
        "dsqfl":p.get("DSQFL"),"units":p.get("QTDUNHAB"),"construction_year":p.get("ANCONSTR"),
        "blocks":p.get("QTDMULTIPLAS"),"building_name":p.get("NMEDIFICACAO"),"street":p.get("NMENDCOMP"),
        "use_description":p.get("EFTUTZDESC"),"sql_reference":p.get("DSQFL"),"cib":None,"cib_status":None,
        "complement":None,"parcel_type":p.get("TIPOEMPREENDIMENTO") or p.get("NMTIPOEMPRENDIMENTO")}}

def point(lat,lng):
    a,b,c,d=BOUNDS
    if not(b<=lat<=d and a<=lng<=c): raise ValueError("outside_recife_bounds")
    fs=query(PARCEL,PF,lat=lat,lng=lng,count=5)
    return public(fs[0]) if fs else None

def context(lat,lng,parcel):
    layers={};errors={}
    for k,(i,fields) in ZLAYERS.items():
        try:layers[k]=query(f"{ZBASE}/{i}",fields,lat=lat,lng=lng,geometry=False)
        except Exception as e:layers[k]=[];errors[k]=type(e).__name__
    z=((layers.get("zoning") or [{}])[0].get("properties") or {});p=parcel["properties"]
    return {"planning":{"zoning":{"properties":{"cd_zoneamento_perimetro":z.get("ZONA"),"tx_zoneamento_perimetro":z.get("ZONA2") or z.get("ZONA"),"macrozone":z.get("MACROZONA"),"ca_min":z.get("VLCOEFMIN"),"ca_basic":z.get("VLCOEFBAS"),"ca_max":z.get("VLCOEFMAX"),"considerations":z.get("NMCONSIDERAC")}},"special_regimes":{k:v for k,v in layers.items() if k!="zoning" and v}},
    "buildings":[],"terrain":{"available":False,"reason":"pending_recife_terrain"},"risk":{"geological":[],"hydrological":[]},
    "heritage":{"assets":layers.get("iep") or [],"buffers":{"ZEPH":layers.get("zeph") or [],"IPAV":layers.get("ipav") or [],"UCN":layers.get("ucn") or []}},
    "utilities":{},"licensing":{"housing_permits_exact_sql":[],"impact_spatial_incidence":[],"environment_spatial_incidence":[]},
    "fiscal":{"pgv":{"found":False},"iptu":{"found":True,"latest":{"land_area_m2":p.get("land_area_m2"),"built_area_m2":p.get("built_area_m2"),"frontage_m":p.get("frontage_m"),"floors":p.get("floors"),"corrected_construction_year":p.get("construction_year"),"use_description":p.get("use_description"),"property_status":p.get("parcel_status"),"raw_v0":p.get("v0")}},"itbi":{"available":False,"count":0,"registry_references":[],"transactions":[]}},
    "query_errors":errors,"queried_at":now(),"source":"Prefeitura do Recife / ESIG"}

def vals(s,p,c):
    q=p["properties"];z=((c["planning"].get("zoning") or {}).get("properties") or {});sp=c["planning"].get("special_regimes") or {}
    if s=="executive_summary":return [{"label":"Endereço","value":q.get("street")},{"label":"DSQFL","value":q.get("dsqfl")},{"label":"SeqImóvel","value":q.get("seqimovel")},{"label":"Situação","value":q.get("parcel_status")},{"label":"Área do lote","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Área construída","value":q.get("built_area_m2"),"unit":"m²"},{"label":"Zona","value":z.get("cd_zoneamento_perimetro")},{"label":"CA máximo","value":z.get("ca_max")}]
    if s=="identity_location":return [{"label":"DSQFL","value":q.get("dsqfl")},{"label":"SeqImóvel","value":q.get("seqimovel")},{"label":"Situação cadastral","value":q.get("parcel_status")},{"label":"Distrito","value":q.get("district")},{"label":"Setor","value":q.get("fiscal_sector")},{"label":"Quadra","value":q.get("fiscal_block")},{"label":"Face","value":q.get("face")},{"label":"Lote","value":q.get("fiscal_lot")},{"label":"Endereço","value":q.get("street")},{"label":"Área","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Testada","value":q.get("frontage_m"),"unit":"m"}]
    if s=="building_existing":return [{"label":"Área construída","value":q.get("built_area_m2"),"unit":"m²"},{"label":"Pavimentos","value":q.get("floors")},{"label":"Ano construção","value":q.get("construction_year")},{"label":"Unidades","value":q.get("units")},{"label":"Blocos","value":q.get("blocks")},{"label":"Uso","value":q.get("use_description")}]
    if s=="planning_buildability":
        out=[{"label":"Macrozona","value":z.get("macrozone")},{"label":"Zona","value":z.get("cd_zoneamento_perimetro")},{"label":"Descrição","value":z.get("tx_zoneamento_perimetro")},{"label":"CA mínimo","value":z.get("ca_min")},{"label":"CA básico","value":z.get("ca_basic")},{"label":"CA máximo","value":z.get("ca_max")},{"label":"Considerações","value":z.get("considerations")}]
        for k,l in [("zec","ZEC"),("zeis","ZEIS"),("aru","ARU")]:
            for x in sp.get(k) or []:
                r=x.get("properties") or {};out.append({"label":f"Incidência {l}","value":r.get("NMNOME") or r.get("ZEC") or r.get("ZONA_NOME") or l})
        return out
    if s=="fiscal_market":return [{"label":"Campo V0 · ESIG","value":q.get("v0")},{"label":"Situação cadastral","value":q.get("parcel_status")},{"label":"Área lote","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Área construída","value":q.get("built_area_m2"),"unit":"m²"},{"label":"Testada","value":q.get("frontage_m"),"unit":"m"},{"label":"Observação","value":"V0 permanece campo bruto; significado fiscal não é inferido."}]
    if s=="environment_risk_heritage":
        out=[]
        for k,l in [("iep","IEP"),("zeph","ZEPH"),("ipav","IPAV"),("ucn","UCN")]:
            for x in sp.get(k) or []:
                r=x.get("properties") or {};out.append({"label":f"Incidência {l}","value":r.get("NMDESCR") or r.get("NMNOME") or r.get("NOME_IPAV") or r.get("CDZONA_NOME") or l})
        return out or [{"label":"Patrimônio/áreas especiais","value":"Sem incidência nas camadas consultadas."}]
    return []

def report(parcel,ctx):
    spec=json.loads((ROOT/"data/property-dossier/report-spec.json").read_text());m=json.loads((ROOT/"data/deployment/professional-completion-matrix.json").read_text());city=next(x for x in m["first_wave"] if x.get("ibge")=="2611606");rows={r["field"]:r for r in city["rows"]};ss=[]
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
    d=re.sub(r"\D","",q or "")
    if not d:raise ValueError("unsupported_search_format")
    where=f"DSQFL='{d[:20]}'" if len(d)>=12 else f"SEQIMOVEL={int(d)}"
    fs=query(PARCEL,PF,where=where,count=10)
    return [{"feature":public(x),"representative_point":centroid(x.get("geometry") or {})} for x in fs]

def response_for_point(lat,lng):
    p=point(lat,lng)
    if not p:return None
    c=context(lat,lng,p)
    return {"found":True,"clicked":{"lat":lat,"lng":lng},"feature":p,"context":c,"source":{"id":"pe-recife-esig-lotes","authority":"Prefeitura do Recife / ESIG","layer":"FeatureServer/3","license":"PUBLIC_QUERY_ONLY_PENDING_LAYER_REUSE_REVIEW","queried_at":now(),"method":"ArcGIS point-intersection + closed allowlist"},"report":report(p,c)}
