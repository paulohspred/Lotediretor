#!/usr/bin/env python3
from __future__ import annotations
import json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
import municipality_utilities
from shapely.geometry import Point,shape,LineString
from math import atan2,cos,degrees,radians,sin,sqrt

ROOT=Path("/srv/lotediretor/app")
WFS="https://bhmap.pbh.gov.br/v2/api/idebhgeo/wfs"
BOUNDS=(-44.10,-20.10,-43.80,-19.75)
LAYERS={
 "parcel":("ide_bhgeo:LOTE_CTM",["ID_LT","NULOTCTM","ID_QUADRA_CTM","AREA_M2","GEOMETRIA"]),
 "approved":("ide_bhgeo:LOTE_APROVADO",["ID_LCP","ZONA_FISCAL","QUARTEIRAO","LOTE","PLANTA_CP","GEOMETRIA"]),
 "zoning":("ide_bhgeo:ZONEAMENTO_11181",["ID_ZONEAMENTO","DESC_TIPO_ZONEAMENTO","SIGLA_TIPO_ZONEAMENTO","GEOMETRIA"]),
 "building":("ide_bhgeo:EDIFICACAO",["ID_EDIF","AREA","COTA_MAX_MDE","COTA_MAX_MDT","COTA_MIN_MDE","COTA_MIN_MDT","ID_LOTE_CTM","MEDIA_MDE","MEDIA_MDT","ALT_EST_MAXMDE_MINMDT","ALT_EST_MODAMDE_MINMDT","GEOMETRIA"]),
 "risk_flood":("ide_bhgeo:AREA_RISCO_INUNDACAO",["ID_ARG","RISCO_GEOLOGICO","GEOMETRIA"]),
 "risk_slide":("ide_bhgeo:AREA_RISCO_ESCORREGAMENTO",["ID_ARG","RISCO_GEOLOGICO","GEOMETRIA"]),
 "heritage_municipal":("ide_bhgeo:AREA_PROTECAO_CULTURAL_CDPCM-BH",["ID_AREA_PROTECAO_CULTURAL","DESC_TIPO_AREA_PROTECAO","NOME_AREA_PROTECAO","GEOMETRIA"]),
 "heritage_state":("ide_bhgeo:AREA_PROTECAO_CULTURAL_IEPHA",["ID_AREA_PROTECAO_CULTURAL","DESC_TIPO_AREA_PROTECAO","NOME_AREA_PROTECAO","GEOMETRIA"]),
 "heritage_federal":("ide_bhgeo:AREA_PROTECAO_CULTURAL_IPHAN",["ID_AREA_PROTECAO_CULTURAL","DESC_TIPO_AREA_PROTECAO","NOME_AREA_PROTECAO","GEOMETRIA"]),
 "contour_1m":("ide_bhgeo:CURVA_NIVEL_SEGMENTADA_1M",["ID_CURVA_SEC_SEGMENTADA","ID_CURVA_SEC","COTA_CURVA_NIVEL","GEOMETRIA"]),
 "env_ade":("ide_bhgeo:ADE_INTERESSE_AMBIENTAL_11181",["ID_ADE_INTERESSE_AMBIENTAL","NOME_TIPO_ADE_INTERESSE_AMB","GEOMETRIA"]),
 "env_aeis":("ide_bhgeo:AEIS_INTERESSE_AMBIENTAL_11181",["ID_AEIS_INTERESSE_AMBIENTAL","NOME_AEIS_INTERESSE_AMBIENT","GEOMETRIA"]),
 "env_uc":("ide_bhgeo:UNID_CONSERV_AMBIENTAL",["ID_UCA","CATEGORIA","DESC_CATEGORIA","COMPETENCIA","NOME","TIPO_USO","LEGISLACAO","GEOMETRIA"]),
 "env_park":("ide_bhgeo:PARQUES_MUNICIPAIS",["ID_UNIDADE_FPMZB","NOME_UNIDADE_FPMZB","IND_ABERTO_PUBLICO","LEGISLACAO","BAIRRO","GEOMETRIA"]),
 "env_corridor":("ide_bhgeo:CORREDOR_ECOLOGICO_SERRA_CURRAL",["ID_COR_ECO_ESPI_SERRA_CURRAL","CATEGORIA","DESC_CATEGORIA","UCA_ORIGEM","NOME","LEGISLACAO","GEOMETRIA"]),
 "road_class":("ide_bhgeo:CLASSIFICACAO_VIARIA_11181",["ID_CLASSIFICACAO_VIARIA","TP_LOG","NO_LOG","CLASSIFICACAO_VIARIA","SUBDIVISAO_CLASSF_VIARIA","AFASTAMENTO_FRONTAL","TIPO_LARGURA_VIA","DESCRICAO_TIPO_LARGURA","GEOMETRIA"]),
 "road_circulation":("ide_bhgeo:CIRCULACAO_VIARIA",["ID_TCV","TIPO_TRECHO_CIRCULACAO","TIPO_LOGRADOURO","LOGRADOURO","COD_LOGRADOURO","GEOMETRIA"]),
 "microdrainage":("ide_bhgeo:REDE_MICRODRENAGEM",["ID_REDE_MICRODRENAGEM","MATERIAL","DIAMETRO","ALTURA","LARGURA","COMPRIMENTO","GEOMETRIA"]),
 "permit":("ide_bhgeo:PROJETO_EDIFICACAO_LICENCIADO",["ID_PROJETO_EDIFICACOES","NUMERO_PROCESSO","SITUACAO_REQUERIMENTO","TITULO_PROJETO","TIPO","SITUACAO_PROJETO","NUM_ULTIMO_ALVARA","DT_EMISSAO_ALVARA_CONSTRUCAO","DT_CONCESSAO_ULTIMO_ALVARA","DT_VALIDADE_ULTIMO_ALVARA","DATA_COMUNICADO_INICIO_OBRA","DATA_ULTIMA_BAIXA","TIPO_ULTIMA_BAIXA","ENDERECO","LOTE_PROJETO","USO_GERAL","QTD_UND_RESIDENCIAL","QTD_UND_NAO_RESIDENCIAL","AREA_CONSTRUIDA","TIPO_APROVACAO","DATA_APROVACAO","AREA_LIQUIDA","QTDE_PAVIMENTOS","LINK_SIATU_EDIFICACAO","GEOMETRIA"])
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

def parcel_intersections(key,parcel,count=1000):
    geom=shape(parcel.get("geometry") or {})
    minx,miny,maxx,maxy=geom.bounds
    typename,fields=LAYERS[key]
    q={
        "service":"WFS","version":"2.0.0","request":"GetFeature",
        "typeNames":typename,"srsName":"EPSG:4326","count":str(count),
        "propertyName":",".join(fields),"outputFormat":"application/json",
        "bbox":f"{minx},{miny},{maxx},{maxy},EPSG:4326"
    }
    data=request(q);allowed=set(fields)-{"GEOMETRIA"};out=[]
    for f in data.get("features") or []:
        p=f.get("properties") or {}
        if set(p)-allowed:raise RuntimeError("bh_unexpected_fields")
        item={"type":"Feature","id":f.get("id"),"geometry":f.get("geometry"),"properties":p}
        if item["geometry"] and shape(item["geometry"]).intersects(geom):out.append(item)
    return out

def _distance_m(a,b):
    lat1,lon1,lat2,lon2=map(radians,[a[1],a[0],b[1],b[0]])
    dlat=lat2-lat1;dlon=lon2-lon1
    h=sin(dlat/2)**2+cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371008.8*2*atan2(sqrt(h),sqrt(max(0,1-h)))

def _bearing(a,b):
    lat1,lat2=radians(a[1]),radians(b[1]);dlon=radians(b[0]-a[0])
    y=sin(dlon)*cos(lat2);x=cos(lat1)*sin(lat2)-sin(lat1)*cos(lat2)*cos(dlon)
    return (degrees(atan2(y,x))+360)%360

def _profile_segments(parcel_geometry):
    poly=shape(parcel_geometry)
    if poly.is_empty:return []
    if poly.geom_type=="MultiPolygon":poly=max(poly.geoms,key=lambda p:p.area)
    rect=poly.minimum_rotated_rectangle
    pts=list(rect.exterior.coords)[:-1]
    edges=[(pts[i],pts[(i+1)%4],_distance_m(pts[i],pts[(i+1)%4])) for i in range(4)]
    a0,a1,_=max(edges,key=lambda x:x[2])
    dx,dy=a1[0]-a0[0],a1[1]-a0[1]
    mag=max((dx*dx+dy*dy)**.5,1e-12);ux,uy=dx/mag,dy/mag
    cx,cy=poly.centroid.x,poly.centroid.y
    span=max(max(p[0] for p in pts)-min(p[0] for p in pts),max(p[1] for p in pts)-min(p[1] for p in pts))*4+0.002
    out=[]
    for name,(vx,vy) in [("A-A",(ux,uy)),("B-B",(-uy,ux))]:
        line=LineString([(cx-vx*span,cy-vy*span),(cx+vx*span,cy+vy*span)])
        inter=poly.intersection(line)
        segs=[inter] if inter.geom_type=="LineString" else list(inter.geoms) if inter.geom_type=="MultiLineString" else []
        if not segs:continue
        seg=max(segs,key=lambda s:s.length)
        xy=list(seg.coords)
        if len(xy)>=2:out.append((name,seg,xy[0],xy[-1]))
    return out

def _contour_profiles(parcel_geometry,contours):
    profiles=[]
    for name,line,a,b in _profile_segments(parcel_geometry):
        length=_distance_m(a,b);hits=[]
        for item in contours:
            z=(item.get("properties") or {}).get("COTA_CURVA_NIVEL")
            if not isinstance(z,(int,float)) or not item.get("geometry"):continue
            inter=line.intersection(shape(item["geometry"]))
            if inter.is_empty:continue
            points=[]
            if inter.geom_type=="Point":points=[inter]
            elif inter.geom_type=="MultiPoint":points=[p for p in inter.geoms if not p.is_empty]
            elif inter.geom_type in ("LineString","MultiLineString"):
                segs=[inter] if inter.geom_type=="LineString" else [g for g in inter.geoms if not g.is_empty]
                if segs:
                    g=max(segs,key=lambda x:x.length)
                    pt=g.interpolate(.5,normalized=True)
                    if not pt.is_empty:points=[pt]
            for pt in points:
                if pt.is_empty:continue
                frac=line.project(pt)/max(line.length,1e-12)
                hits.append({"distance_m":round(length*frac,2),"elevation_m":float(z),"lat":pt.y,"lng":pt.x})
        hits=sorted(hits,key=lambda x:x["distance_m"])
        dedup=[]
        for h in hits:
            if not dedup or abs(h["distance_m"]-dedup[-1]["distance_m"])>.15 or h["elevation_m"]!=dedup[-1]["elevation_m"]:
                dedup.append(h)
        if len(dedup)>=2:
            dz=dedup[-1]["elevation_m"]-dedup[0]["elevation_m"]
            profiles.append({
                "name":name,"length_m":round(length,2),"bearing_deg":round(_bearing(a,b),1),
                "delta_elevation_m":round(dz,2),"average_slope_pct":round((dz/length*100) if length else 0,2),
                "samples":dedup,"line_coordinates_wgs84":[[a[0],a[1]],[b[0],b[1]]],
                "profile_method":"Interseções do corte com curvas oficiais de nível de 1 m"
            })
    return profiles

def context(lat,lng,parcel):
    errors={}
    try:approved=spatial("approved",lat,lng)
    except Exception as e:approved=[];errors["approved_lot"]=type(e).__name__
    try:zoning=spatial("zoning",lat,lng)
    except Exception as e:zoning=[];errors["zoning"]=type(e).__name__
    parcel_id=(parcel.get("properties") or {}).get("municipal_parcel_feature_id")
    try:buildings=query("building",cql=f"ID_LOTE_CTM={int(parcel_id)}",count=200) if parcel_id is not None else []
    except Exception as e:buildings=[];errors["buildings"]=type(e).__name__
    try:risk_flood=spatial("risk_flood",lat,lng)
    except Exception as e:risk_flood=[];errors["risk_flood"]=type(e).__name__
    try:risk_slide=spatial("risk_slide",lat,lng)
    except Exception as e:risk_slide=[];errors["risk_slide"]=type(e).__name__
    heritage={}
    for key in ["heritage_municipal","heritage_state","heritage_federal"]:
        try:heritage[key]=spatial(key,lat,lng)
        except Exception as e:heritage[key]=[];errors[key]=type(e).__name__
    try:permits=spatial("permit",lat,lng)
    except Exception as e:permits=[];errors["permits"]=type(e).__name__
    try:contours=parcel_intersections("contour_1m",parcel,count=1000)
    except Exception as e:contours=[];errors["terrain_contours"]=type(e).__name__
    environment={}
    for key in ["env_ade","env_aeis","env_uc","env_park","env_corridor"]:
        try:environment[key]=parcel_intersections(key,parcel,count=200)
        except Exception as e:environment[key]=[];errors[key]=type(e).__name__
    transport={}
    for key in ["road_class","road_circulation"]:
        try:transport[key]=parcel_intersections(key,parcel,count=200)
        except Exception as e:transport[key]=[];errors[key]=type(e).__name__
    try:microdrainage=parcel_intersections("microdrainage",parcel,count=500)
    except Exception as e:microdrainage=[];errors["microdrainage"]=type(e).__name__
    contour_values=sorted({(x.get("properties") or {}).get("COTA_CURVA_NIVEL") for x in contours if isinstance((x.get("properties") or {}).get("COTA_CURVA_NIVEL"),(int,float))})
    profiles=_contour_profiles(parcel.get("geometry") or {},contours) if contour_values else []
    terrain={
        "available":bool(contour_values),
        "method":"Curvas de nível oficiais de 1 m que cruzam o terreno",
        "quality":"Perfil discreto baseado em curvas oficiais de nível de 1 m",
        "contour_count":len(contours),
        "min_elevation_m":min(contour_values) if contour_values else None,
        "max_elevation_m":max(contour_values) if contour_values else None,
        "amplitude_m":(max(contour_values)-min(contour_values)) if contour_values else None,
        "contour_elevations_m":contour_values,
        "profiles":profiles,
        "caveat":"Faixa e cortes altimétricos baseados nas curvas oficiais que cruzam o lote; não há interpolação apresentada como levantamento contínuo. Não substitui MDT contínuo nem levantamento topográfico de campo."
    }
    z=(zoning[0].get("properties") if zoning else {}) or {}
    return {"planning":{"zoning":{"properties":{"cd_zoneamento_perimetro":z.get("SIGLA_TIPO_ZONEAMENTO"),"tx_zoneamento_perimetro":z.get("DESC_TIPO_ZONEAMENTO"),"source_layer":"ZONEAMENTO_11181"}},"special_regimes":{}},
    "approved_parcel":approved,"buildings":buildings,"terrain":terrain,
    "risk":{"geological":risk_slide,"hydrological":risk_flood},
    "environment":environment,
    "transport":transport,
    "drainage_assets":microdrainage,
    "heritage":{"assets":[],"buffers":heritage},"utilities":municipality_utilities.load("3106200"),
    "licensing":{"housing_permits_exact_sql":permits,"impact_spatial_incidence":[],"environment_spatial_incidence":[]},
    "fiscal":{"pgv":{"found":False},"iptu":{"found":False,"latest":{}},"itbi":{"available":False,"count":0,"registry_references":[],"transactions":[]}},
    "query_errors":errors,"queried_at":now(),"source":"Prefeitura de Belo Horizonte / IDE-BHGEO"}

def vals(s,p,c):
    q=p["properties"];z=(c["planning"]["zoning"] or {}).get("properties") or {};approved=c.get("approved_parcel") or []
    if s=="executive_summary":return [{"label":"Identificação cadastral do lote","value":q.get("ctm_number")},{"label":"Área do lote","value":q.get("land_area_m2"),"unit":"m²"},{"label":"Zoneamento","value":z.get("cd_zoneamento_perimetro")},{"label":"Descrição","value":z.get("tx_zoneamento_perimetro")}]
    if s=="identity_location":
        out=[{"label":"Identificação cadastral do lote","value":q.get("ctm_number")},{"label":"Identificador cadastral do lote","value":q.get("municipal_parcel_feature_id")},{"label":"Identificador cadastral da quadra","value":q.get("ctm_block_id")},{"label":"Área cadastral do terreno","value":q.get("land_area_m2"),"unit":"m²"}]
        for x in approved[:5]:
            r=x.get("properties") or {};out.extend([{"label":"Zona fiscal · lote aprovado","value":r.get("ZONA_FISCAL")},{"label":"Quarteirão · lote aprovado","value":r.get("QUARTEIRAO")},{"label":"Lote aprovado","value":r.get("LOTE")},{"label":"Planta CP","value":r.get("PLANTA_CP")}])
        return out
    if s=="building_existing":
        buildings=c.get("buildings") or []
        areas=[(x.get("properties") or {}).get("AREA") for x in buildings if isinstance((x.get("properties") or {}).get("AREA"),(int,float))]
        heights=[(x.get("properties") or {}).get("ALT_EST_MAXMDE_MINMDT") for x in buildings if isinstance((x.get("properties") or {}).get("ALT_EST_MAXMDE_MINMDT"),(int,float))]
        return [
            {"label":"Edificações cartográficas vinculadas ao terreno","value":len(buildings)},
            {"label":"Soma de áreas de footprint","value":round(sum(areas),2) if areas else None,"unit":"m²"},
            {"label":"Maior altura estimada das edificações","value":round(max(heights),2) if heights else None,"unit":"m"},
            {"label":"Ressalva","value":"Alturas e contornos de edificações são contexto cartográfico e não substituem cadastro ou licenciamento vigente."}
        ]
    if s=="licensing_history":
        out=[]
        for item in (c.get("licensing") or {}).get("housing_permits_exact_sql") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"Processo licenciamento","value":r.get("NUMERO_PROCESSO")},
                {"label":"Título do projeto","value":r.get("TITULO_PROJETO")},
                {"label":"Tipo","value":r.get("TIPO")},
                {"label":"Situação","value":r.get("SITUACAO_PROJETO") or r.get("SITUACAO_REQUERIMENTO")},
                {"label":"Último alvará","value":r.get("NUM_ULTIMO_ALVARA")},
                {"label":"Emissão alvará","value":r.get("DT_EMISSAO_ALVARA_CONSTRUCAO")},
                {"label":"Validade alvará","value":r.get("DT_VALIDADE_ULTIMO_ALVARA")},
                {"label":"Última baixa","value":r.get("DATA_ULTIMA_BAIXA")},
                {"label":"Tipo última baixa","value":r.get("TIPO_ULTIMA_BAIXA")},
                {"label":"Área construída licenciada","value":r.get("AREA_CONSTRUIDA"),"unit":"m²"},
                {"label":"Pavimentos licenciados","value":r.get("QTDE_PAVIMENTOS")}
            ])
        return out or [{"label":"Projeto licenciado no ponto","value":"Nenhum projeto intersectante localizado na camada BHGEO consultada."}]
    if s=="terrain_visual":
        t=c.get("terrain") or {}
        if not t.get("available"):
            return [{"label":"Topografia","value":"Nenhuma curva de nível de 1 m intersecta o lote nesta consulta."}]
        return [
            {"label":"Curvas de nível de 1 m intersectantes","value":t.get("contour_count")},
            {"label":"Menor cota de curva no lote","value":t.get("min_elevation_m"),"unit":"m"},
            {"label":"Maior cota de curva no lote","value":t.get("max_elevation_m"),"unit":"m"},
            {"label":"Amplitude entre curvas intersectantes","value":t.get("amplitude_m"),"unit":"m"},
            {"label":"Cotas intersectantes","value":", ".join(str(v) for v in t.get("contour_elevations_m") or [])},
            {"label":"Método","value":t.get("method")},
            {"label":"Limite topográfico","value":t.get("caveat")}
        ]
    if s=="environment_risk_heritage":
        out=[]
        env=c.get("environment") or {}
        for item in env.get("env_ade") or []:
            r=item.get("properties") or {};out.append({"label":"Área de interesse ambiental","value":r.get("NOME_TIPO_ADE_INTERESSE_AMB") or "Incidência identificada"})
        for item in env.get("env_aeis") or []:
            r=item.get("properties") or {};out.append({"label":"Área especial de interesse ambiental","value":r.get("NOME_AEIS_INTERESSE_AMBIENT") or "Incidência identificada"})
        for item in env.get("env_uc") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"Unidade de conservação","value":r.get("NOME") or r.get("DESC_CATEGORIA")},
                {"label":"Categoria da unidade de conservação","value":r.get("CATEGORIA") or r.get("DESC_CATEGORIA")},
                {"label":"Legislação ambiental","value":r.get("LEGISLACAO")}
            ])
        for item in env.get("env_park") or []:
            r=item.get("properties") or {};out.append({"label":"Parque municipal","value":r.get("NOME_UNIDADE_FPMZB")})
        for item in env.get("env_corridor") or []:
            r=item.get("properties") or {};out.append({"label":"Corredor ecológico","value":r.get("NOME") or r.get("DESC_CATEGORIA")})
        for item in (c.get("risk") or {}).get("hydrological") or []:
            r=item.get("properties") or {};out.append({"label":"Risco de inundação","value":r.get("RISCO_GEOLOGICO")})
        for item in (c.get("risk") or {}).get("geological") or []:
            r=item.get("properties") or {};out.append({"label":"Risco de escorregamento","value":r.get("RISCO_GEOLOGICO")})
        labels={"heritage_municipal":"Proteção cultural municipal","heritage_state":"Proteção cultural IEPHA","heritage_federal":"Proteção cultural IPHAN"}
        for key,items in ((c.get("heritage") or {}).get("buffers") or {}).items():
            for item in items:
                r=item.get("properties") or {}
                out.extend([
                    {"label":labels.get(key,key),"value":r.get("NOME_AREA_PROTECAO")},
                    {"label":"Tipo de proteção","value":r.get("DESC_TIPO_AREA_PROTECAO")}
                ])
        return out or [{"label":"Risco/patrimônio","value":"Sem incidência nas camadas consultadas."}]
    if s=="planning_buildability":return [{"label":"Zoneamento Lei 11.181","value":z.get("cd_zoneamento_perimetro")},{"label":"Descrição do zoneamento","value":z.get("tx_zoneamento_perimetro")},{"label":"Fonte do zoneamento","value":"Mapa oficial de zoneamento da Prefeitura de Belo Horizonte"}]
    if s=="infrastructure_utilities":
        out=municipality_utilities.report_values(c.get("utilities") or {})
        for item in c.get("drainage_assets") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"Microdrenagem mapeada no terreno","value":"Trecho de rede cartográfica intersecta o lote"},
                {"label":"Material da microdrenagem","value":r.get("MATERIAL")},
                {"label":"Diâmetro informado","value":r.get("DIAMETRO")}
            ])
        return out
    if s=="public_change_context":
        out=[]
        for item in (c.get("transport") or {}).get("road_class") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"Classificação viária","value":r.get("CLASSIFICACAO_VIARIA")},
                {"label":"Subdivisão viária","value":r.get("SUBDIVISAO_CLASSF_VIARIA")},
                {"label":"Logradouro classificado","value":" ".join(str(x) for x in [r.get("TP_LOG"),r.get("NO_LOG")] if x)},
                {"label":"Afastamento frontal informado","value":r.get("AFASTAMENTO_FRONTAL")},
                {"label":"Largura viária","value":r.get("DESCRICAO_TIPO_LARGURA") or r.get("TIPO_LARGURA_VIA")}
            ])
        for item in (c.get("transport") or {}).get("road_circulation") or []:
            r=item.get("properties") or {}
            out.extend([
                {"label":"Trecho de circulação viária","value":" ".join(str(x) for x in [r.get("TIPO_LOGRADOURO"),r.get("LOGRADOURO")] if x)},
                {"label":"Tipo de circulação","value":r.get("TIPO_TRECHO_CIRCULACAO")}
            ])
        return out
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
