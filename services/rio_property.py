#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import municipality_utilities

ROOT=Path("/srv/lotediretor/app")
PARCEL="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadParcel/IMOVEIS_TERRITORIAIS/FeatureServer/0"
ZBASE="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Urbanismo/LBB_Zoneamento_urbano_vigente/FeatureServer"
EDIF="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadLog/Edificacoes_2019/FeatureServer/0"
RISK="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Estudos/ISMFI_Indice_de_Suscetibilidade_do_Meio_Fisico_a_Inundacoes/MapServer/0"
APAC="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Urbanismo/LBB_APAC/FeatureServer/0"
MDT="https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Cartografia/Modelo_Digital_de_Terreno__Lidar_2019__escala_1_10_000_/MapServer"
EF=["objectid","altura","base","clnp","cod_edifica","cod_lote","cod_projecao","cod_unico","flag_produto","tipo","topo","Shape__Area","Shape__Length"]
RF=["objectid","id","cd_geocodi","tipo","cd_geocodb","nm_bairro","cd_geocods","nm_subdist","cd_geocodd","nm_distrit","cd_geocodm","nm_municip","nm_micro","nm_meso","area__m2_","dens","areakm","fid_1","cd_geoco_1","ind_dec","ind_imp","ind_cota","ind_prox","ismfi_v45"]
AF=["objectid","codigo","legislacao","tipo","nome","subareas","endereco","orgao","obs","Shape__Area","Shape__Length"]
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

def query_polygon(url,fields,geometry,count=200):
    coords=(geometry or {}).get("coordinates") or []
    kind=(geometry or {}).get("type")
    rings=[]
    if kind=="Polygon":
        rings=coords
    elif kind=="MultiPolygon":
        for poly in coords:
            rings.extend(poly)
    if not rings:
        return []
    arc={"rings":rings,"spatialReference":{"wkid":4326}}
    q={
        "f":"geojson","outSR":"4326","returnGeometry":"true",
        "outFields":",".join(fields),"resultRecordCount":str(count),
        "geometry":json.dumps(arc,separators=(",",":")),
        "geometryType":"esriGeometryPolygon","inSR":"4326",
        "spatialRel":"esriSpatialRelIntersects"
    }
    d=get(url+"/query?"+urllib.parse.urlencode(q));a=set(fields);out=[]
    for f in d.get("features") or []:
        p=f.get("properties") or {}
        if set(p)-a: raise RuntimeError("unexpected_fields")
        out.append({"type":"Feature","id":f.get("id"),"geometry":f.get("geometry"),"properties":p})
    return out


def mdt_value(lat,lng):
    q={
        "f":"json",
        "geometry":json.dumps({"x":lng,"y":lat,"spatialReference":{"wkid":4326}},separators=(",",":")),
        "geometryType":"esriGeometryPoint","sr":"4326","layers":"all:0","tolerance":"2",
        "mapExtent":f"{lng-0.0003},{lat-0.0003},{lng+0.0003},{lat+0.0003}",
        "imageDisplay":"256,256,96","returnGeometry":"false"
    }
    d=get(MDT+"/identify?"+urllib.parse.urlencode(q))
    rs=d.get("results") or []
    if not rs:return None
    raw=(rs[0].get("attributes") or {}).get("Classify.Pixel Value")
    try:return float(str(raw).replace(",","."))
    except (TypeError,ValueError):return None

def terrain_context(parcel,lat,lng):
    g=parcel.get("geometry") or {};coords=g.get("coordinates") or [];rings=[]
    if g.get("type")=="Polygon" and coords:rings=[coords[0]]
    elif g.get("type")=="MultiPolygon":rings=[p[0] for p in coords if p]
    vertices=[pt for ring in rings for pt in ring[:-1] if isinstance(pt,list) and len(pt)>=2]
    picks=[(lat,lng)]
    if vertices:
        n=len(vertices)
        for i in sorted({0,n//4,n//2,(3*n)//4}):
            x,y=vertices[min(i,n-1)][:2];picks.append((y,x))
    unique=[]
    for p in picks:
        if p not in unique:unique.append(p)
    with ThreadPoolExecutor(max_workers=min(5,len(unique))) as ex:
        values=list(ex.map(lambda p:mdt_value(p[0],p[1]),unique))
    samples=[{"lat":p[0],"lng":p[1],"elevation_m":v} for p,v in zip(unique,values) if isinstance(v,(int,float))]
    if not samples:return {"available":False,"reason":"mdt_identify_no_sample"}
    elevations=[x["elevation_m"] for x in samples]
    return {
        "available":True,"sample_method":"clicked point + parcel boundary samples",
        "sample_count":len(samples),"clicked_elevation_m":samples[0]["elevation_m"] if samples and samples[0]["lat"]==lat and samples[0]["lng"]==lng else None,
        "min_sampled_elevation_m":min(elevations),"max_sampled_elevation_m":max(elevations),
        "sampled_relief_m":max(elevations)-min(elevations),"samples":samples,
        "source":{"authority":"Instituto Pereira Passos / Prefeitura do Rio","dataset":"Modelo Digital de Terreno LiDAR 2019","resolution_m":5,"license":"CC BY 4.0","method":"ArcGIS MapServer identify"}
    }

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
    try:buildings=query_polygon(EDIF,EF,parcel.get("geometry") or {},count=300)
    except Exception as e:buildings=[];errors["buildings"]=type(e).__name__
    try:risk=query(RISK,RF,lat=lat,lng=lng,geometry=False,count=10)
    except Exception as e:risk=[];errors["flood_susceptibility"]=type(e).__name__
    try:apac=query(APAC,AF,lat=lat,lng=lng,geometry=False,count=20)
    except Exception as e:apac=[];errors["apac"]=type(e).__name__
    try:terrain=terrain_context(parcel,lat,lng)
    except Exception as e:terrain={"available":False,"reason":"mdt_unavailable"};errors["terrain"]=type(e).__name__
    return {"planning":{"zoning":{"properties":{"cd_zoneamento_perimetro":z.get("sigla") or z.get("zona"),"tx_zoneamento_perimetro":" ".join(x for x in [z.get("zona"),z.get("subzona")] if x),"macrozone":m.get("macrozona"),"legislation":z.get("legislacao"),"ap":z.get("ap"),"ca_basic":z.get("cab"),"ca_max":z.get("cam"),"occupancy":z.get("to_"),"min_lot_area_m2":z.get("lote_min"),"min_frontage_m":z.get("testada_min"),"max_height_setback":z.get("gab_afast"),"max_height_no_setback":z.get("gab_n_afast"),"front_setback":z.get("afast_fron"),"ics":z.get("ics"),"observations":z.get("obs")}},"special_regimes":{}},
    "registry":{"available":bool(refs),"references":refs,"interpretation":"Matrícula/RGI são referências públicas da camada cadastral territorial da PCRJ; não substituem certidão atualizada."},
    "buildings":buildings,"terrain":terrain,"risk":{"geological":[],"hydrological":risk},"heritage":{"assets":apac,"buffers":{}},"utilities":municipality_utilities.load("3304557"),"licensing":{"housing_permits_exact_sql":[],"impact_spatial_incidence":[],"environment_spatial_incidence":[]},
    "fiscal":{"pgv":{"found":False},"iptu":{"found":False,"latest":{}},"itbi":{"available":False,"count":0,"registry_references":[],"transactions":[]}},
    "query_errors":errors,"queried_at":now(),"source":"Prefeitura da Cidade do Rio de Janeiro / Data.Rio"}

def vals(s,p,c):
    q=p["properties"];z=(c["planning"]["zoning"] or {}).get("properties") or {};reg=c.get("registry") or {}
    if s=="executive_summary":return [{"label":"Inscrição imobiliária","value":q.get("inscricao_imobiliaria")},{"label":"RGI","value":q.get("rgi")},{"label":"Matrícula cadastral","value":q.get("matricula")},{"label":"Quadra","value":q.get("fiscal_block")},{"label":"Lote","value":q.get("fiscal_lot")},{"label":"Zona","value":z.get("cd_zoneamento_perimetro")},{"label":"CA básico","value":z.get("ca_basic")},{"label":"CA máximo","value":z.get("ca_max")}]
    if s=="identity_location":return [{"label":"Inscrição imobiliária","value":q.get("inscricao_imobiliaria")},{"label":"RGI","value":q.get("rgi")},{"label":"Projeto","value":q.get("project_number")},{"label":"PAA","value":q.get("paa")},{"label":"Tipo parcelamento","value":q.get("parceling_type")},{"label":"Origem","value":q.get("origin")},{"label":"Tipo do lote","value":q.get("parcel_type")},{"label":"Classificação","value":q.get("classification")},{"label":"Quadra","value":q.get("fiscal_block")},{"label":"Lote","value":q.get("fiscal_lot")},{"label":"Área descrita","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Data verificação","value":q.get("verification_date")},{"label":"Publicação","value":q.get("publication_date")}]
    if s=="building_existing":
        buildings=c.get("buildings") or []
        heights=[(x.get("properties") or {}).get("altura") for x in buildings if isinstance((x.get("properties") or {}).get("altura"),(int,float))]
        types=sorted({str((x.get("properties") or {}).get("tipo")) for x in buildings if (x.get("properties") or {}).get("tipo")})
        return [
            {"label":"Edificações cartográficas 2019 intersectantes","value":len(buildings)},
            {"label":"Maior altura cartográfica","value":max(heights) if heights else None,"unit":"m"},
            {"label":"Tipos cartográficos","value":", ".join(types[:8]) if types else None},
            {"label":"Ressalva","value":"Edificações 2019 são contexto cartográfico e não substituem cadastro/licenciamento atual."}
        ]
    if s=="planning_buildability":return [{"label":"Macrozona","value":z.get("macrozone")},{"label":"Zona/subzona","value":z.get("tx_zoneamento_perimetro")},{"label":"Sigla","value":z.get("cd_zoneamento_perimetro")},{"label":"Legislação","value":z.get("legislation")},{"label":"AP","value":z.get("ap")},{"label":"Coeficiente de aproveitamento básico","value":z.get("ca_basic")},{"label":"Coeficiente de aproveitamento máximo","value":z.get("ca_max")},{"label":"Taxa de ocupação","value":z.get("occupancy")},{"label":"Lote mínimo","value":z.get("min_lot_area_m2"),"unit":"m²"},{"label":"Testada mínima","value":z.get("min_frontage_m"),"unit":"m"},{"label":"Gabarito com afastamento","value":z.get("max_height_setback")},{"label":"Gabarito sem afastamento","value":z.get("max_height_no_setback")},{"label":"Afastamento frontal","value":z.get("front_setback")},{"label":"Parâmetro urbanístico ICS","value":z.get("ics")}]
    if s=="environment_risk_heritage":
        out=[]
        for item in (c.get("risk") or {}).get("hydrological") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"Suscetibilidade física a inundação (ISMFI)","value":r.get("ismfi_v45")},
                {"label":"Bairro considerado no índice de inundação","value":r.get("nm_bairro")},
                {"label":"Índice declividade","value":r.get("ind_dec")},
                {"label":"Índice impermeabilização","value":r.get("ind_imp")},
                {"label":"Índice cota","value":r.get("ind_cota")},
                {"label":"Índice proximidade","value":r.get("ind_prox")}
            ])
        for item in (c.get("heritage") or {}).get("assets") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"APAC","value":r.get("nome")},
                {"label":"Tipo APAC","value":r.get("tipo")},
                {"label":"Legislação APAC","value":r.get("legislacao")},
                {"label":"Órgão APAC","value":r.get("orgao")}
            ])
        return out or [{"label":"Risco/patrimônio","value":"Sem incidência nas camadas consultadas."}]
    if s=="registry_due_diligence":
        out=[]
        for r in reg.get("references") or []:out.extend([{"label":"Matrícula cadastral publicada","value":r.get("registry_number")},{"label":"Fonte registral","value":r.get("source")},{"label":"Data de verificação cadastral","value":r.get("verification_date")}])
        out.append({"label":"Ressalva","value":reg.get("interpretation")})
        return out
    if s=="infrastructure_utilities":
        return municipality_utilities.report_values(c.get("utilities") or {})
    if s=="terrain_visual":
        t=c.get("terrain") or {}
        if not t.get("available"):
            return [{"label":"Topografia","value":"MDT LiDAR 2019 indisponível nesta consulta."}]
        src=t.get("source") or {}
        return [
            {"label":"Cota no ponto consultado","value":t.get("clicked_elevation_m"),"unit":"m"},
            {"label":"Cota mínima amostrada","value":t.get("min_sampled_elevation_m"),"unit":"m"},
            {"label":"Cota máxima amostrada","value":t.get("max_sampled_elevation_m"),"unit":"m"},
            {"label":"Desnível amostrado","value":t.get("sampled_relief_m"),"unit":"m"},
            {"label":"Pontos de terreno analisados","value":t.get("sample_count")},
            {"label":"Fonte topográfica","value":src.get("dataset")},
            {"label":"Resolução do modelo de terreno","value":src.get("resolution_m"),"unit":"m"},
            {"label":"Ano do modelo de terreno","value":2019},
            {"label":"Qualidade","value":"Triagem topográfica por MDT LiDAR reamostrado; não substitui levantamento planialtimétrico executivo."}
        ]
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
