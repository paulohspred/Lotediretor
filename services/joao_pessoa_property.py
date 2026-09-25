#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from math import atan2, cos, degrees, radians, sin, sqrt
from pathlib import Path

import psycopg2
import municipality_utilities
from psycopg2.extras import RealDictCursor
from shapely.geometry import shape, Point, LineString

ROOT = Path("/srv/lotediretor/app")
DB_DSN = "dbname=lotediretor user=sentinelx host=/var/run/postgresql"
BOUNDS = (-34.98, -7.25, -34.78, -7.04)
FILIPEIA_WMS = "https://filipeia.joaopessoa.pb.gov.br/geoserver/wms"
FILIPEIA_WFS = "https://filipeia.joaopessoa.pb.gov.br/geoserver/wfs"
SPATIAL_LAYERS = {
    "coastal_restriction": ("digeoc:faixas", ["OBJECTID","Faixas","SHAPE_Area"]),
    "road_hierarchy": ("digeoc:Hierarquia", ["Hierarquia","Shape_Area"]),
    "buildings": ("digeoc:EDIFICACOES", ["OBJECTID_1","N_PAVIM","BAIRRO","EDIFICACAO","AREA","Shape_Area"]),
    "conservation": ("digeoc:UC", ["NOME","DECRETO"]),
    "susceptibility": ("digeoc:Suscetibilidade", ["OBJECTID","classe","tipo","Shape_Area"]),
    "heritage_iphan": ("digeoc:Tombamento_IPHAN", ["OBJECTID","codcart","nome","protecao_e","data_publi"]),
    "heritage_iphaep": ("digeoc:TOMBAMENTO_IPHAEP", ["Id","CODCART","NOME","PROTECAO_E","DATAPUBLIC"]),
    "historic_center": ("digeoc:centrohistorico", ["OBJECTID","ENTITY","LAYER","Area","Hectares"]),
    "zeis": ("digeoc:ZEIS", ["OBJECTID","nome","lei","processo"]),
}
PLANNING_LAYERS = {
    "zoning": "digeoc:zoneamento2024",
    "macrozone": "digeoc:zoneamento_pmjp_macrozoneamento_CAM",
}
PLANNING_FIELDS = {"sigla", "nome", "tipo"}
# LC 169/2024 substituted Annex V of LC 166/2024.
# Values below are occupancy parameters only; IA maximum comes from the
# Plano Diretor/instruments and is not inferred here. Art. 62 (coastal height)
# was held unconstitutional by TJPB on 2026-01-21, while the remaining LUOS
# stayed in force. Coastal height is therefore always flagged for specific review.
OCCUPANCY_169 = {
    "ZH1": {"to_max_pct":50,"tap_min_pct":10,"front_m":5.0,"height_rule":"Restrições das notas aplicáveis do Anexo IV da LC 169/2024","side_rule":"Até 3º pav.: 1,50 m; 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
    "ZH2": {"to_max_pct":55,"tap_min_pct":5,"front_m":5.0,"height_rule":"Restrições das notas aplicáveis do Anexo IV da LC 169/2024","side_rule":"Até 3º pav.: 1,50 m; 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 2º pav.: 2,00 m; 3º e 4º: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
    "ZH3": {"to_max_pct":50,"tap_min_pct":5,"front_m":5.0,"height_rule":"Faixa costeira: altura exige verificação específica; art. 62 não é usado como limite vigente","side_rule":"Até 3º pav.: 1,50 m; 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
    "ZH4": {"to_max_pct":50,"tap_min_pct":15,"front_m":5.0,"height_rule":"Faixa costeira/patrimônio: verificar restrições específicas","side_rule":"Até 3º pav.: 2,00 m; 4º pav.: 4,00 m; acima: 4,00 + [(N-4) × 0,30] m","rear_rule":"Até 4º pav.: 3,00 m; acima: 4,00 + [(N-4) × 0,30] m"},
    "ZH5": {"to_max_pct":50,"tap_min_pct":15,"front_m":5.0,"height_rule":"Faixa costeira: altura exige verificação específica","side_rule":"Até 2º pav.: 1,50 m; 3º e 4º: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
    "ZCS1": {"to_max_pct":80,"tap_min_pct":5,"front_m":0.0,"side_rule":"0,00 m","rear_rule":"2,00 m","conditional_note":"Para uso H, LC 169/2024 prevê faixas específicas de TO/TAP; confirmar conforme uso."},
    "ZCS2": {"to_max_pct":70,"tap_min_pct":5,"front_m":5.0,"side_rule":"Até 4º pav.: 0,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 4º pav.: 2,00 m; acima: 3,00 + [(N-4) × 0,30] m","conditional_note":"Para uso H, LC 169/2024 prevê faixas específicas de TO/TAP/recuo frontal; confirmar conforme uso."},
    "ZCS3": {"to_max_pct":65,"tap_min_pct":5,"front_m":5.0,"height_rule":"Faixa costeira/patrimônio: verificar restrições específicas","side_rule":"Até 2º pav.: 0,00 m; 3º e 4º: 2,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
    "ZCS4": {"to_max_pct":65,"tap_min_pct":5,"front_m":5.0,"side_rule":"Até 2º pav.: 0,00 m; 3º e 4º: 2,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 2º pav.: 2,00 m; 3º e 4º: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
    "ZCS5": {"to_max_pct":50,"tap_min_pct":25,"front_m":10.0,"side_rule":"5,00 m","rear_rule":"5,00 m","height_rule":"Faixa costeira: altura exige verificação específica"},
    "ZCS6": {"to_max_pct":30,"tap_min_pct":30,"front_m":10.0,"side_rule":"8,00 m","rear_rule":"8,00 m","height_rule":"Faixa costeira: altura exige verificação específica"},
    "ZCS7": {"to_max_pct":65,"tap_min_pct":10,"front_m":8.0,"side_rule":"4,00 m","rear_rule":"4,00 m"},
    "ZEPA1": {"special_rule":"Parâmetros conforme planos de manejo específicos, quando couber."},
    "ZEPA2": {"to_max_pct":40,"tap_min_pct":40,"front_m":10.0,"side_rule":"Até 3º pav.: 1,50 m; 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 2º pav.: 2,00 m; 3º e 4º: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","height_rule":"Altura sujeita às restrições costeiras e patrimoniais aplicáveis; art. 62 não é usado como limite vigente","environmental_license":True},
    "ZEPA3": {"to_max_pct":40,"tap_min_pct":40,"front_m":10.0,"side_rule":"Até 2º pav.: 1,50 m; 3º e 4º: 3,00 m","rear_rule":"Até o 4º pav.: 3,00 m","height_rule":"4 pavimentos no quadro, sujeito às restrições costeiras/patrimoniais aplicáveis","environmental_license":True},
    "ZI1": {"to_max_pct":50,"tap_min_pct":10,"front_m":6.0,"side_rule":"3,00 m","rear_rule":"3,00 m"},
    "ZI2": {"to_max_pct":50,"tap_min_pct":10,"front_m":6.0,"side_rule":"3,00 m","rear_rule":"3,00 m"},
    "ZBD": {"to_max_pct":10,"tap_min_pct":80,"front_m":10.0,"side_rule":"10,00 m","rear_rule":"10,00 m","height_rule":"2 pavimentos"},
    "SEAV": {"to_max_pct":40,"tap_min_pct":15,"front_m":5.0,"side_rule":"Até 3º pav.: 1,50 m; 4º pav.: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m","rear_rule":"Até 2º pav.: 2,00 m; 3º e 4º: 3,00 m; acima: 3,00 + [(N-4) × 0,30] m"},
}

MACROZONE_IA = {
    "MAD1": {"ia_basic":1.0,"ia_max":6.0,"name":"Macrozona Adensável 1"},
    "MAD2": {"ia_basic":1.0,"ia_max":4.0,"name":"Macrozona Adensável 2"},
    "MAD3": {"ia_basic":1.0,"ia_max":2.0,"name":"Macrozona Adensável 3"},
    "MBD": {"ia_basic":1.0,"ia_max":1.0,"name":"Macrozona de Baixa Densidade"},
    "MPA": {"ia_basic":1.0,"ia_max":1.0,"name":"Macrozona de Proteção Ambiental"},
    "MAP": {"ia_basic":1.0,"ia_max":1.0,"name":"Macrozona de Proteção Ambiental"},
}

def normalized_zone_code(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())

def occupancy_parameters(
    zone_code: str | None,
    macrozone_code: str | None,
    coastal_restrictions: list[dict],
    road_hierarchy: list[dict],
) -> dict:
    key=normalized_zone_code(zone_code)
    data=dict(OCCUPANCY_169.get(key) or {})
    if not data:
        return {"available":False,"zone_code":key}
    macro_key=normalized_zone_code(macrozone_code)
    macro_ia=MACROZONE_IA.get(macro_key) or {}
    data.update({
        "available":True,
        "zone_code":key,
        "macrozone_code":macro_key,
        "ia_basic":macro_ia.get("ia_basic",1.0),
        "ia_max":macro_ia.get("ia_max"),
        "legal_basis":"LC 166/2024 (art. 53) c/c LC 169/2024 (Anexo IV substitutivo do Anexo V da LC 166/2024)",
        "legal_status_checked_at":"2026-09-25",
        "legal_status_note":"TJPB manteve a LUOS em vigor em 21/01/2026, com inconstitucionalidade do art. 62. O sistema não usa o art. 62 para calcular altura na orla.",
        "coastal_restriction_intersections":len(coastal_restrictions or []),
        "road_hierarchy":sorted({
            str((item.get("properties") or {}).get("Hierarquia")).strip()
            for item in (road_hierarchy or [])
            if (item.get("properties") or {}).get("Hierarquia")
        }),
        "ia_legal_basis":"LC 164/2024, art. 50, §1º (Plano Diretor)",
    })
    if coastal_restrictions:
        data["coastal_restriction_note"]="O terreno intersecta faixa de restrição costeira publicada; gabarito/altura exige conferência específica da regra atualmente aplicável."
    return data

LABEL = {
    "identity": "Identidade",
    "land": "Terreno",
    "building": "Edificação",
    "IPTU": "IPTU",
    "PGV": "PGV",
    "ITBI": "ITBI",
    "registry reference": "Registro imobiliário",
    "zoning": "Zoneamento",
    "urban parameters": "Parâmetros urbanísticos",
    "permits": "Licenciamento",
    "habite-se": "Habite-se",
    "environment": "Ambiental",
    "risk": "Risco",
    "heritage": "Patrimônio",
    "electricity": "Energia",
    "gas": "Gás",
    "water/sewer": "Água e esgoto",
    "drainage": "Drenagem",
    "telecom": "Telecom",
    "transport": "Sistema viário",
    "imagery": "Imagens",
    "terrain": "Terreno/topografia",
    "public works": "Obras públicas",
    "public processes": "Processos públicos",
    "official gazette": "Diário Oficial",
    "historical data": "Histórico",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def db():
    return psycopg2.connect(DB_DSN)


def row_feature(row: dict) -> dict:
    props = {
        "municipal_parcel_feature_id": row.get("gid"),
        "sql_reference": row.get("codi_cart"),
        "cartographic_code": row.get("codi_cart"),
        "fiscal_sector": row.get("codi_seto"),
        "fiscal_block": row.get("codi_quad"),
        "fiscal_lot": row.get("codi_lote"),
        "street": row.get("desc_logr"),
        "number": None,
        "land_area_m2": float(row["area_m2"]) if row.get("area_m2") is not None else None,
        "built_area_m2": None,
        "use_description": row.get("tipo_imove"),
        "parcel_type": row.get("tipo_imove"),
        "parcel_status": "CADASTRADO",
        "cib": None,
        "cib_status": None,
        "complement": None,
    }
    return {
        "type": "Feature",
        "id": f"jp-{row.get('gid')}",
        "geometry": json.loads(row["geojson"]),
        "properties": props,
    }


def point(lat: float, lng: float) -> dict | None:
    min_lng, min_lat, max_lng, max_lat = BOUNDS
    if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
        raise ValueError("outside_joao_pessoa_bounds")
    sql = """
        SELECT gid,codi_cart,codi_seto,codi_quad,codi_lote,desc_logr,tipo_imove,
               ST_Area(ST_Transform(ST_Force2D(geom),31985)) AS area_m2,
               ST_AsGeoJSON(ST_Force2D(geom),7) AS geojson
        FROM ld_stage.jp_lotes
        WHERE ST_Covers(
            ST_Force2D(geom),
            ST_SetSRID(ST_Point(%s,%s),4674)
        )
        ORDER BY ST_Area(ST_Transform(ST_Force2D(geom),31985))
        LIMIT 1
    """
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (lng, lat))
        row = cur.fetchone()
    return row_feature(dict(row)) if row else None


def representative_point(geom: dict) -> dict:
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ST_Y(p),ST_X(p)
            FROM (
              SELECT ST_PointOnSurface(
                ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326)
              ) AS p
            ) q
            """,
            (json.dumps(geom),),
        )
        lat, lng = cur.fetchone()
    return {"lat": float(lat), "lng": float(lng)}


def search(query_text: str) -> list[dict]:
    code = re.sub(r"\D", "", query_text or "")
    if not re.fullmatch(r"\d{9}", code):
        raise ValueError("unsupported_search_format")
    sql = """
        SELECT gid,codi_cart,codi_seto,codi_quad,codi_lote,desc_logr,tipo_imove,
               ST_Area(ST_Transform(ST_Force2D(geom),31985)) AS area_m2,
               ST_AsGeoJSON(ST_Force2D(geom),7) AS geojson
        FROM ld_stage.jp_lotes
        WHERE codi_cart=%s
        LIMIT 10
    """
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (code,))
        rows = [dict(r) for r in cur.fetchall()]
    out = []
    for row in rows:
        feature = row_feature(row)
        out.append(
            {
                "feature": feature,
                "representative_point": representative_point(feature["geometry"]),
            }
        )
    return out


def _geo_distance(a,b):
    lat1,lon1,lat2,lon2=map(radians,[a[1],a[0],b[1],b[0]])
    dlat=lat2-lat1;dlon=lon2-lon1
    h=sin(dlat/2)**2+cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371008.8*2*atan2(sqrt(h),sqrt(max(0,1-h)))


def _geo_bearing(a,b):
    lat1,lat2=radians(a[1]),radians(b[1]);dlon=radians(b[0]-a[0])
    y=sin(dlon)*cos(lat2)
    x=cos(lat1)*sin(lat2)-sin(lat1)*cos(lat2)*cos(dlon)
    return (degrees(atan2(y,x))+360)%360


def _jp_profile_lines(geometry):
    poly=shape(geometry)
    if poly.is_empty:return []
    if poly.geom_type=="MultiPolygon":poly=max(poly.geoms,key=lambda p:p.area)
    pts=list(poly.minimum_rotated_rectangle.exterior.coords)[:-1]
    edges=[(pts[i],pts[(i+1)%4],_geo_distance(pts[i],pts[(i+1)%4])) for i in range(4)]
    a0,a1,_=max(edges,key=lambda x:x[2])
    dx,dy=a1[0]-a0[0],a1[1]-a0[1]
    mag=max((dx*dx+dy*dy)**.5,1e-12);ux,uy=dx/mag,dy/mag
    cx,cy=poly.centroid.x,poly.centroid.y
    span=max(max(x for x,_ in pts)-min(x for x,_ in pts),max(y for _,y in pts)-min(y for _,y in pts))*4+.002
    out=[]
    for name,(vx,vy) in (("A-A",(ux,uy)),("B-B",(-uy,ux))):
        line=LineString([(cx-vx*span,cy-vy*span),(cx+vx*span,cy+vy*span)])
        inter=poly.intersection(line)
        segs=[inter] if inter.geom_type=="LineString" else list(inter.geoms) if inter.geom_type=="MultiLineString" else []
        if segs:
            seg=max(segs,key=lambda s:s.length);xy=list(seg.coords)
            if len(xy)>=2:out.append((name,seg,xy[0],xy[-1]))
    return out


def _jp_profiles(parcel_geometry,contours):
    profiles=[]
    for name,line,a,b in _jp_profile_lines(parcel_geometry):
        length=_geo_distance(a,b);hits=[]
        for item in contours:
            inter=line.intersection(shape(item["geometry"]))
            if inter.is_empty:continue
            pts=[inter] if inter.geom_type=="Point" else list(inter.geoms) if inter.geom_type=="MultiPoint" else []
            for pt in pts:
                if pt.is_empty:continue
                frac=line.project(pt)/max(line.length,1e-12)
                hits.append({"distance_m":round(length*frac,2),"elevation_m":float(item["elevation_m"]),"lat":pt.y,"lng":pt.x})
        hits.sort(key=lambda x:x["distance_m"])
        if len(hits)>=2:
            dz=hits[-1]["elevation_m"]-hits[0]["elevation_m"]
            profiles.append({"name":name,"length_m":round(length,2),"bearing_deg":round(_geo_bearing(a,b),1),"delta_elevation_m":round(dz,2),"average_slope_pct":round(dz/length*100,2) if length else 0,"samples":hits,"line_coordinates_wgs84":[list(a),list(b)],"profile_method":"Interseções do corte com curvas oficiais de nível de 2022"})
    return profiles


def terrain_for_parcel(parcel: dict) -> dict:
    code=(parcel.get("properties") or {}).get("cartographic_code")
    if not code:return {"available":False,"reason":"missing_cartographic_code"}
    summary_sql="""
        SELECT count(*) contour_count,min(c.cota)::float8 min_elevation_m,
               max(c.cota)::float8 max_elevation_m,
               array_agg(DISTINCT c.cota ORDER BY c.cota) elevations
        FROM ld_stage.jp_lotes l JOIN ld_stage.jp_curvas_nivel_2022 c
          ON ST_Intersects(ST_Force2D(l.geom),c.geom)
        WHERE l.codi_cart=%s
    """
    detail_sql="""
        SELECT c.cota::float8 elevation_m,ST_AsGeoJSON(ST_Force2D(c.geom),7) geojson
        FROM ld_stage.jp_lotes l JOIN ld_stage.jp_curvas_nivel_2022 c
          ON ST_Intersects(ST_Force2D(l.geom),c.geom)
        WHERE l.codi_cart=%s
    """
    with db() as conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(summary_sql,(code,));row=dict(cur.fetchone())
        cur.execute(detail_sql,(code,));details=[dict(x) for x in cur.fetchall()]
    vals=[float(v) for v in (row.get("elevations") or [])]
    contours=[{"elevation_m":x["elevation_m"],"geometry":json.loads(x["geojson"])} for x in details if x.get("geojson") and x.get("elevation_m") is not None]
    profiles=_jp_profiles(parcel.get("geometry") or {},contours) if contours else []
    return {
        "available":bool(row.get("contour_count")),
        "method":"Curvas de nível oficiais de 2022 que cruzam o terreno",
        "quality":"Perfil discreto baseado em curvas oficiais de nível de 2022",
        "contour_count":int(row.get("contour_count") or 0),
        "min_elevation_m":row.get("min_elevation_m"),
        "max_elevation_m":row.get("max_elevation_m"),
        "amplitude_m":round(row["max_elevation_m"]-row["min_elevation_m"],3) if row.get("min_elevation_m") is not None and row.get("max_elevation_m") is not None else None,
        "contour_elevations_m":vals,"profiles":profiles,
        "source_sha256":"3b29f856cfef6b0e20a76120ecdfdedcdb43a18a538c14362b1b1439331d1fbb",
        "caveat":"Faixa e cortes altimétricos baseados nas curvas oficiais que cruzam o lote; não há interpolação apresentada como levantamento contínuo. Não substitui MDT contínuo ou levantamento topográfico de campo."
    }


def spatial_layer_for_parcel(key: str, parcel: dict, count: int = 250) -> list[dict]:
    layer, fields = SPATIAL_LAYERS[key]
    parcel_geom = shape(parcel.get("geometry") or {})
    if parcel_geom.is_empty:
        return []
    minx, miny, maxx, maxy = parcel_geom.bounds
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer,
        "srsName": "EPSG:4326",
        "count": str(count),
        "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
        "propertyName": ",".join(["the_geom"] + fields),
        "outputFormat": "application/json",
    }
    req = urllib.request.Request(
        FILIPEIA_WFS + "?" + urllib.parse.urlencode(params),
        headers={
            "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read(5000000))
    allowed = set(fields)
    out = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        clean = {k: props.get(k) for k in fields if props.get(k) is not None}
        if set(clean) - allowed:
            raise RuntimeError("jp_unexpected_fields")
        geom = feature.get("geometry")
        if geom and shape(geom).intersects(parcel_geom):
            out.append({
                "type": "Feature",
                "id": feature.get("id"),
                "geometry": geom,
                "properties": clean,
            })
    return out


def planning_at_point(lat: float, lng: float) -> tuple[dict, dict]:
    out = {}
    errors = {}
    pt = Point(lng, lat)
    for key, layer in PLANNING_LAYERS.items():
        span = 0.0007
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": layer,
            "srsName": "EPSG:4326",
            "count": "10",
            "bbox": f"{lng-span},{lat-span},{lng+span},{lat+span},EPSG:4326",
            "propertyName": "the_geom,sigla,nome,tipo",
            "outputFormat": "application/json",
        }
        try:
            req = urllib.request.Request(
                FILIPEIA_WFS + "?" + urllib.parse.urlencode(params),
                headers={
                    "User-Agent": "LoteDiretor/0.1 (+https://lotediretor.com)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read(2000000))
            selected = {}
            for feature in data.get("features") or []:
                geom = feature.get("geometry")
                props = feature.get("properties") or {}
                if geom and (shape(geom).contains(pt) or shape(geom).touches(pt)):
                    selected = {
                        k: props.get(k)
                        for k in PLANNING_FIELDS
                        if props.get(k) is not None
                    }
                    break
            out[key] = selected
        except Exception as exc:
            out[key] = {}
            errors[key] = type(exc).__name__
    return out, errors

def context(parcel: dict, lat: float, lng: float) -> dict:
    planning, planning_errors = planning_at_point(lat, lng)
    spatial = {}
    spatial_errors = {}
    with ThreadPoolExecutor(max_workers=len(SPATIAL_LAYERS)) as pool:
        jobs = {
            pool.submit(spatial_layer_for_parcel, key, parcel): key
            for key in SPATIAL_LAYERS
        }
        for future in as_completed(jobs):
            key = jobs[future]
            try:
                spatial[key] = future.result()
            except Exception as exc:
                spatial[key] = []
                spatial_errors[key] = type(exc).__name__
    heritage_assets = (spatial.get("heritage_iphan") or []) + (spatial.get("heritage_iphaep") or [])
    heritage_buffers = {
        "Centro Histórico": spatial.get("historic_center") or [],
    }
    occupancy = occupancy_parameters(
        (planning.get("zoning") or {}).get("sigla"),
        (planning.get("macrozone") or {}).get("sigla"),
        spatial.get("coastal_restriction") or [],
        spatial.get("road_hierarchy") or [],
    )
    return {
        "planning": {
            "zoning": {"properties": planning.get("zoning") or {}},
            "macrozone": {"properties": planning.get("macrozone") or {}},
            "special_regimes": {},
            "parameters": occupancy,
            "coastal_restrictions": spatial.get("coastal_restriction") or [],
            "note": (
                "Zoneamento e macrozoneamento 2024 consultados por interseção WFS no "
                "GeoServer oficial do Filipeia; a base não é espelhada."
            ),
        },
        "buildings": spatial.get("buildings") or [],
        "terrain": terrain_for_parcel(parcel),
        "environment": {
            "conservation_units": spatial.get("conservation") or [],
            "zeis": spatial.get("zeis") or [],
        },
        "risk": {
            "geological": [
                item for item in (spatial.get("susceptibility") or [])
                if "inund" not in " ".join(str(v) for v in (item.get("properties") or {}).values()).lower()
            ],
            "hydrological": [
                item for item in (spatial.get("susceptibility") or [])
                if "inund" in " ".join(str(v) for v in (item.get("properties") or {}).values()).lower()
            ],
        },
        "heritage": {"assets": heritage_assets, "buffers": heritage_buffers},
        "utilities": municipality_utilities.load("2507507"),
        "licensing": {
            "housing_permits_exact_sql": [],
            "impact_spatial_incidence": [],
            "environment_spatial_incidence": [],
            "interpretation": (
                "Licenciamento/habite-se municipal permanece em fluxo autenticado "
                "ou documental e não foi automatizado."
            ),
        },
        "fiscal": {
            "pgv": {"found": False},
            "iptu": {"found": False, "latest": {}},
            "itbi": {
                "available": False,
                "count": 0,
                "registry_references": [],
                "transactions": [],
            },
        },
        "query_errors": {
            **{f"planning_{k}": v for k, v in planning_errors.items()},
            **{f"spatial_{k}": v for k, v in spatial_errors.items()},
        },
        "queried_at": now(),
        "source": "Prefeitura de João Pessoa / SEPLAN",
    }


def vals(section_id: str, parcel: dict, ctx: dict) -> list[dict]:
    p = parcel["properties"]
    if section_id == "executive_summary":
        return [
            {"label": "Código cartográfico", "value": p.get("cartographic_code")},
            {"label": "Logradouro", "value": p.get("street")},
            {"label": "Setor", "value": p.get("fiscal_sector")},
            {"label": "Quadra", "value": p.get("fiscal_block")},
            {"label": "Lote", "value": p.get("fiscal_lot")},
            {"label": "Área geométrica", "value": p.get("land_area_m2"), "unit": "m²"},
            {"label": "Tipo cadastral", "value": p.get("parcel_type")},
        ]
    if section_id == "identity_location":
        return [
            {"label": "Código cartográfico", "value": p.get("cartographic_code")},
            {"label": "Setor cartográfico", "value": p.get("fiscal_sector")},
            {"label": "Quadra", "value": p.get("fiscal_block")},
            {"label": "Lote", "value": p.get("fiscal_lot")},
            {"label": "Logradouro", "value": p.get("street")},
            {"label": "Tipo do imóvel", "value": p.get("parcel_type")},
            {"label": "Área geométrica calculada", "value": p.get("land_area_m2"), "unit": "m²"},
        ]
    if section_id == "building_existing":
        buildings=ctx.get("buildings") or []
        areas=[]
        floors=[]
        types=[]
        for item in buildings:
            p0=item.get("properties") or {}
            try:
                if p0.get("Shape_Area") is not None:areas.append(float(p0.get("Shape_Area")))
                elif p0.get("AREA") is not None:areas.append(float(str(p0.get("AREA")).replace(",", ".")))
            except (TypeError,ValueError):
                pass
            if p0.get("N_PAVIM"):floors.append(str(p0.get("N_PAVIM")))
            if p0.get("EDIFICACAO"):types.append(str(p0.get("EDIFICACAO")))
        return [
            {"label":"Edificações mapeadas que intersectam o terreno","value":len(buildings)},
            {"label":"Área cartográfica somada das edificações","value":round(sum(areas),2) if areas else None,"unit":"m²"},
            {"label":"Pavimentos informados na cartografia","value":", ".join(sorted(set(floors))) if floors else None},
            {"label":"Tipos de edificação informados","value":", ".join(sorted(set(types))) if types else None},
            {"label":"Ressalva","value":"As edificações são contexto cartográfico municipal e não substituem cadastro fiscal, projeto aprovado ou levantamento atual."},
        ]
    if section_id == "environment_risk_heritage":
        out=[]
        for item in (ctx.get("environment") or {}).get("conservation_units") or []:
            p0=item.get("properties") or {}
            out.extend([
                {"label":"Unidade de conservação","value":p0.get("NOME")},
                {"label":"Norma da unidade de conservação","value":p0.get("DECRETO")},
            ])
        for item in (ctx.get("environment") or {}).get("zeis") or []:
            p0=item.get("properties") or {}
            out.extend([
                {"label":"ZEIS que intersecta o terreno","value":p0.get("nome")},
                {"label":"Base legal da ZEIS","value":p0.get("lei")},
            ])
        for risk_key, label in [("geological","Suscetibilidade geológica"),("hydrological","Suscetibilidade a inundação")]:
            for item in (ctx.get("risk") or {}).get(risk_key) or []:
                p0=item.get("properties") or {}
                parts=[str(x).strip() for x in [p0.get("tipo"),p0.get("classe")] if x and str(x).strip() not in {"-","—"}]
                out.append({"label":label,"value":" · ".join(parts) if parts else "Incidência na camada oficial"})
        for item in (ctx.get("heritage") or {}).get("assets") or []:
            p0=item.get("properties") or {}
            out.extend([
                {"label":"Bem protegido","value":p0.get("nome") or p0.get("NOME")},
                {"label":"Proteção cultural","value":p0.get("protecao_e") or p0.get("PROTECAO_E")},
            ])
        for item in ((ctx.get("heritage") or {}).get("buffers") or {}).get("Centro Histórico") or []:
            out.append({"label":"Centro Histórico","value":"Terreno intersecta a poligonal publicada."})
        return out or [{"label":"Incidências ambientais, de suscetibilidade e patrimônio","value":"Nenhuma incidência nas camadas oficiais consultadas para este terreno."}]
    if section_id == "planning_buildability":
        zoning=((ctx.get("planning") or {}).get("zoning") or {}).get("properties") or {}
        macro=((ctx.get("planning") or {}).get("macrozone") or {}).get("properties") or {}
        params=(ctx.get("planning") or {}).get("parameters") or {}
        out=[
            {"label":"Zoneamento 2024","value":zoning.get("sigla")},
            {"label":"Descrição do zoneamento","value":zoning.get("nome")},
            {"label":"Tipo de zoneamento","value":zoning.get("tipo")},
            {"label":"Macrozona 2024","value":macro.get("sigla")},
            {"label":"Descrição da macrozona","value":macro.get("nome")},
            {"label":"Tipo de macrozona","value":macro.get("tipo")},
            {"label":"Índice de aproveitamento básico","value":params.get("ia_basic")},
            {"label":"Índice de aproveitamento máximo","value":params.get("ia_max")},
            {"label":"Base legal dos índices de aproveitamento","value":params.get("ia_legal_basis")},
            {"label":"Taxa de ocupação máxima","value":params.get("to_max_pct"),"unit":"%"},
            {"label":"Taxa de área permeável mínima","value":params.get("tap_min_pct"),"unit":"%"},
            {"label":"Recuo frontal mínimo","value":params.get("front_m"),"unit":"m"},
            {"label":"Regra de recuo lateral","value":params.get("side_rule")},
            {"label":"Regra de recuo de fundos","value":params.get("rear_rule")},
            {"label":"Regra de altura","value":params.get("height_rule")},
            {"label":"Licenciamento ambiental exigido pela zona","value":params.get("environmental_license")},
            {"label":"Hierarquia viária no terreno","value":", ".join(params.get("road_hierarchy") or [])},
            {"label":"Faixa de restrição costeira intersectante","value":params.get("coastal_restriction_intersections")},
            {"label":"Condicionante costeira","value":params.get("coastal_restriction_note")},
            {"label":"Observação específica do quadro","value":params.get("conditional_note")},
            {"label":"Base legal dos parâmetros","value":params.get("legal_basis")},
            {"label":"Situação normativa considerada","value":params.get("legal_status_note")},
            {"label":"Método","value":"Zoneamento por interseção espacial e parâmetros de ocupação estruturados do quadro substitutivo publicado pela LC 169/2024."}
        ]
        return out
    if section_id == "terrain_visual":
        t=ctx.get("terrain") or {}
        if not t.get("available"):
            return [{"label":"Topografia","value":"Nenhuma curva de nível oficial intersecta o lote nesta consulta."}]
        return [
            {"label":"Curvas de nível 2022 intersectantes","value":t.get("contour_count")},
            {"label":"Menor cota no lote","value":t.get("min_elevation_m"),"unit":"m"},
            {"label":"Maior cota no lote","value":t.get("max_elevation_m"),"unit":"m"},
            {"label":"Amplitude entre curvas","value":t.get("amplitude_m"),"unit":"m"},
            {"label":"Cotas intersectantes","value":", ".join(str(v) for v in t.get("contour_elevations_m") or [])},
            {"label":"Método","value":t.get("method")},
            {"label":"Limite topográfico","value":t.get("caveat")}
        ]
    if section_id == "licensing_history":
        return [
            {
                "label": "Licenciamento/habite-se",
                "value": (
                    "Serviço municipal identificado, mas consulta depende de fluxo "
                    "autenticado/documental; não automatizado."
                ),
            }
        ]
    if section_id == "infrastructure_utilities":
        return municipality_utilities.report_values(ctx.get("utilities") or {})
    return []


def report(parcel: dict, ctx: dict) -> dict:
    spec = json.loads((ROOT / "data/property-dossier/report-spec.json").read_text())
    matrix = json.loads(
        (ROOT / "data/deployment/professional-completion-matrix.json").read_text()
    )
    city = next(x for x in matrix["first_wave"] if x.get("ibge") == "2507507")
    rows = {r["field"]: r for r in city["rows"]}
    sections = []
    for section in sorted(spec["sections"], key=lambda x: x["order"]):
        field_states = [
            {
                "field": field,
                "label": LABEL.get(field, field),
                "status": rows[field].get("status"),
                "source_id": rows[field].get("source_id"),
                "connector_status": rows[field].get("connector_status"),
                "access_class": rows[field].get("access_class"),
                "missing_fields": rows[field].get("missing_fields") or [],
            }
            for field in section.get("source_matrix_fields", [])
            if field in rows
        ]
        actual = [
            item
            for item in vals(section["id"], parcel, ctx)
            if item.get("value") not in (None, "")
        ]
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "order": section["order"],
                "section_type": section.get("section_type"),
                "actual_values": actual,
                "fields": field_states,
            }
        )
    return {
        "title": spec["title"],
        "target_completion_level": spec["target_completion_level"],
        "principle": spec["principle"],
        "mode": "PUBLIC_PROPERTY_REPORT",
        "sections": sections,
    }


def response_for_point(lat: float, lng: float) -> dict | None:
    parcel = point(lat, lng)
    if not parcel:
        return None
    ctx = context(parcel, lat, lng)
    return {
        "found": True,
        "clicked": {"lat": lat, "lng": lng},
        "feature": parcel,
        "context": ctx,
        "source": {
            "id": "pb-joao-pessoa-filipeia",
            "authority": "Filipeia / SEPLAN / PMJP",
            "layer": "Lotes.zip",
            "license": (
                "Consulta individual com atribuição. Termos do Filipeia vedam "
                "uso comercial/alienação onerosa dos arquivos ou informações."
            ),
            "queried_at": now(),
            "method": "PostGIS point-in-polygon over official Filipeia lot file",
        },
        "report": report(parcel, ctx),
    }
