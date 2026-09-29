#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, tempfile, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
import psycopg2

ROOT=Path(__file__).resolve().parents[2]
CACHE=Path(os.environ.get("LOTEDIRETOR_RURAL_CACHE","/var/cache/lotediretor/rural"))

SIGEF={
 "layer_key":"sigef_public","kind":"SIGEF","source_id":"br-incra-acervo-fundiario",
 "authority":"INCRA","base":"https://geoportal.incra.gov.br/geoserver/wfs","type_name":"geonode:sigef_geo",
 "fields":["status","data_aprovacao","parcela_codigo","municipio_id","uf_id","area_hectares","tipo_envio","geometry"],
}
CAR_FIELDS=["cod_imovel","status_imovel","dat_criacao","data_atualizacao","area","condicao","uf","municipio","cod_municipio_ibge","m_fiscal","tipo_imovel","geo_area_imovel"]

def cache_dir():
    try: CACHE.mkdir(parents=True,exist_ok=True); return CACHE
    except PermissionError:
        p=Path(tempfile.gettempdir())/"lotediretor-rural"; p.mkdir(parents=True,exist_ok=True); return p

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def fetch_wfs(base,type_name,fields,raw,norm,page_size=5000):
    start=0; features=[]; hashes=[]; final_url=base
    with raw.open("wb") as out:
        while True:
            params={
              "service":"WFS","version":"2.0.0","request":"GetFeature",
              "typeNames":type_name,"propertyName":",".join(fields),
              "outputFormat":"application/json","count":str(page_size),"startIndex":str(start),
              "srsName":"EPSG:4674",
            }
            url=base+"?"+urllib.parse.urlencode(params)
            req=urllib.request.Request(url,headers={"User-Agent":"LoteDiretor/1.0 (+https://lotediretor.com)"})
            with urllib.request.urlopen(req,timeout=180) as res:
                body=res.read(); final_url=res.geturl()
            hashes.append(hashlib.sha256(body).hexdigest()); out.write(body+b"\n")
            doc=json.loads(body); rows=doc.get("features") or []; features.extend(rows)
            if len(rows)<page_size: break
            start += len(rows)
            if start>8_000_000: raise RuntimeError("wfs_page_safety_limit")
    norm.write_text(json.dumps({"type":"FeatureCollection","features":features},ensure_ascii=False),encoding="utf-8")
    return final_url,{"page_sha256":hashes,"page_count":len(hashes),"feature_count_raw":len(features)}

def source_exists(cur,source_id):
    cur.execute("select 1 from ld_catalog.source where source_id=%s and retired_at is null",(source_id,))
    if not cur.fetchone(): raise RuntimeError(f"source not in registry: {source_id}")

def layer_row(cur,cfg):
    source_exists(cur,cfg["source_id"])
    cur.execute("""insert into ld_core.rural_layer(layer_key,kind,source_id,authority,source_url,status)
      values(%s,%s,%s,%s,%s,'NOT_LOADED')
      on conflict(layer_key) do update set source_id=excluded.source_id,authority=excluded.authority,
      source_url=excluded.source_url,updated_at=now()""",
      (cfg["layer_key"],cfg["kind"],cfg["source_id"],cfg["authority"],cfg["base"]))

def snapshot(cur,cfg,raw,final_url,manifest):
    digest=sha(raw)
    cur.execute("""insert into ld_catalog.snapshot
      (source_id,captured_at,requested_url,final_url,http_status,content_type,content_length,sha256,object_key,manifest)
      values(%s,now(),%s,%s,200,'application/jsonl',%s,%s,%s,%s)
      on conflict(source_id,sha256) do update set manifest=excluded.manifest
      returning snapshot_id,captured_at""",
      (cfg["source_id"],cfg["base"],final_url,raw.stat().st_size,digest,str(raw),json.dumps(manifest)))
    return cur.fetchone()

def import_geojson(dsn,path,table):
    subprocess=["ogr2ogr","-f","PostgreSQL","PG:"+dsn,str(path),"-nln","ld_stage."+table,
               "-overwrite","-lco","GEOMETRY_NAME=geom","-lco","SPATIAL_INDEX=NONE","-t_srs","EPSG:4674"]
    import subprocess as sp; sp.run(subprocess,check=True)

def promote_sigef(cur,snapshot_id,captured,table):
    cur.execute(f"""insert into ld_core.sigef_parcel
      (snapshot_id,parcel_code,public_status,approval_date,municipality_id,uf_id,area_ha,submission_type,captured_at,geom)
      select %s,parcela_codigo,status,data_aprovacao::timestamptz,municipio_id::integer,uf_id::integer,
             area_hectares::numeric,tipo_envio,%s,
             ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3))::geometry(MultiPolygon,4674)
      from ld_stage.{table}
      where geom is not null and parcela_codigo is not null
      on conflict(snapshot_id,parcel_code) do nothing""",(snapshot_id,captured))
    cur.execute("select count(*) from ld_core.sigef_parcel where snapshot_id=%s",(snapshot_id,)); return cur.fetchone()[0]

def promote_car(cur,snapshot_id,captured,table):
    cur.execute(f"""insert into ld_core.car_area
      (snapshot_id,car_code,public_status,created_source_at,updated_source_at,area_ha,public_condition,
       uf,municipality,municipality_ibge,fiscal_modules,property_type,captured_at,geom)
      select %s,cod_imovel,status_imovel,dat_criacao::timestamptz,data_atualizacao::timestamptz,
             area::numeric,condicao,upper(uf)::char(2),municipio,lpad(cod_municipio_ibge::text,7,'0')::char(7),
             m_fiscal::numeric,tipo_imovel,%s,
             ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3))::geometry(MultiPolygon,4674)
      from ld_stage.{table}
      where geom is not null and cod_imovel is not null
      on conflict(snapshot_id,car_code) do nothing""",(snapshot_id,captured))
    cur.execute("select count(*) from ld_core.car_area where snapshot_id=%s",(snapshot_id,)); return cur.fetchone()[0]

def load(dsn,cfg):
    cache=cache_dir(); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw=cache/f"{cfg['layer_key']}-{stamp}.wfs-pages.jsonl"; norm=cache/f"{cfg['layer_key']}-{stamp}.geojson"
    with psycopg2.connect(dsn) as conn,conn.cursor() as cur: layer_row(cur,cfg)
    try:
        final,manifest=fetch_wfs(cfg["base"],cfg["type_name"],cfg["fields"],raw,norm)
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        with psycopg2.connect(dsn) as conn,conn.cursor() as cur:
            cur.execute("update ld_core.rural_layer set status='SOURCE_UNAVAILABLE',updated_at=now() where layer_key=%s",(cfg["layer_key"],))
        return {"layer_key":cfg["layer_key"],"status":"SOURCE_UNAVAILABLE","error":type(exc).__name__}
    manifest.update({"authority":cfg["authority"],"source_url":cfg["base"],"fields":cfg["fields"],
                     "privacy":"allowlist excludes owner, holder, CPF/CNPJ and technical-responsible fields"})
    with psycopg2.connect(dsn) as conn,conn.cursor() as cur:
        sid,captured=snapshot(cur,cfg,raw,final,manifest)
    table="rural_"+cfg["layer_key"].replace("-","_")
    try:
        import_geojson(dsn,norm,table)
        with psycopg2.connect(dsn) as conn,conn.cursor() as cur:
            count=promote_sigef(cur,sid,captured,table) if cfg["kind"]=="SIGEF" else promote_car(cur,sid,captured,table)
            if count<1: raise RuntimeError("empty_validated_load")
            cur.execute("""update ld_core.rural_layer set status='ACTIVE',current_snapshot_id=%s,
              feature_count=%s,loaded_at=%s,updated_at=now() where layer_key=%s""",(sid,count,captured,cfg["layer_key"]))
        return {"layer_key":cfg["layer_key"],"status":"ACTIVE","features":count,"snapshot_id":str(sid),"sha256":sha(raw)}
    except Exception:
        with psycopg2.connect(dsn) as conn,conn.cursor() as cur:
            cur.execute("update ld_core.rural_layer set status='FAILED_VALIDATION',updated_at=now() where layer_key=%s",(cfg["layer_key"],))
        raise
    finally:
        with psycopg2.connect(dsn) as conn,conn.cursor() as cur: cur.execute(f"drop table if exists ld_stage.{table}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("dataset",choices=["sigef","car"])
    ap.add_argument("--uf",help="UF para CAR, ex.: MG"); ap.add_argument("--dsn",default=os.environ.get("LOTEDIRETOR_DB_DSN"))
    args=ap.parse_args()
    if not args.dsn: ap.error("--dsn ou LOTEDIRETOR_DB_DSN obrigatório")
    if args.dataset=="sigef": cfg=SIGEF
    else:
        if not args.uf or len(args.uf)!=2: ap.error("--uf obrigatório para CAR")
        uf=args.uf.lower()
        cfg={"layer_key":f"car_{uf}","kind":"CAR","source_id":"br-sicar-car","authority":"SFB / SICAR",
             "base":"https://geoserver.car.gov.br/geoserver/sicar/wfs","type_name":f"sicar:sicar_imoveis_{uf}","fields":CAR_FIELDS}
    print(json.dumps(load(args.dsn,cfg),ensure_ascii=False))
if __name__=="__main__": main()
