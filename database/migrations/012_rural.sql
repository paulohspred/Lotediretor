-- Phase 8 — rural model (public SIGEF/CAR geometry only)
BEGIN;

CREATE TABLE IF NOT EXISTS ld_core.rural_layer (
  layer_key text PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('SIGEF','CAR')),
  source_id text NOT NULL REFERENCES ld_catalog.source(source_id),
  authority text NOT NULL,
  source_url text NOT NULL,
  status text NOT NULL DEFAULT 'NOT_LOADED'
    CHECK (status IN ('NOT_LOADED','ACTIVE','SOURCE_UNAVAILABLE','FAILED_VALIDATION')),
  current_snapshot_id uuid REFERENCES ld_catalog.snapshot(snapshot_id),
  feature_count bigint NOT NULL DEFAULT 0,
  loaded_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ld_core.sigef_parcel (
  sigef_id bigserial PRIMARY KEY,
  snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
  parcel_code text NOT NULL,
  public_status text,
  approval_date timestamptz,
  municipality_id integer,
  uf_id integer,
  area_ha numeric(18,6),
  submission_type text,
  captured_at timestamptz NOT NULL,
  geom geometry(MultiPolygon,4674) NOT NULL,
  UNIQUE(snapshot_id, parcel_code),
  CHECK (ST_IsValid(geom))
);
CREATE INDEX IF NOT EXISTS sigef_parcel_geom_gix ON ld_core.sigef_parcel USING gist(geom);
CREATE INDEX IF NOT EXISTS sigef_parcel_code_idx ON ld_core.sigef_parcel(parcel_code);

CREATE TABLE IF NOT EXISTS ld_core.car_area (
  car_id bigserial PRIMARY KEY,
  snapshot_id uuid NOT NULL REFERENCES ld_catalog.snapshot(snapshot_id),
  car_code text NOT NULL,
  public_status text,
  created_source_at timestamptz,
  updated_source_at timestamptz,
  area_ha numeric(18,6),
  public_condition text,
  uf char(2),
  municipality text,
  municipality_ibge char(7),
  fiscal_modules numeric(18,6),
  property_type text,
  captured_at timestamptz NOT NULL,
  geom geometry(MultiPolygon,4674) NOT NULL,
  UNIQUE(snapshot_id, car_code),
  CHECK (ST_IsValid(geom))
);
CREATE INDEX IF NOT EXISTS car_area_geom_gix ON ld_core.car_area USING gist(geom);
CREATE INDEX IF NOT EXISTS car_area_code_idx ON ld_core.car_area(car_code);
CREATE INDEX IF NOT EXISTS car_area_ibge_idx ON ld_core.car_area(municipality_ibge);

CREATE OR REPLACE FUNCTION ld_api.rural_context(p_lng double precision, p_lat double precision)
RETURNS jsonb
LANGUAGE sql STABLE
AS $fn$
WITH pt AS (SELECT ST_SetSRID(ST_MakePoint(p_lng,p_lat),4674) AS g),
sig AS (
  SELECT jsonb_build_object(
    'parcel_code',s.parcel_code,'status',s.public_status,'approval_date',s.approval_date,
    'area_ha',s.area_ha,'submission_type',s.submission_type
  ) AS j
  FROM ld_core.sigef_parcel s
  JOIN ld_core.rural_layer l ON l.layer_key='sigef_public'
    AND l.current_snapshot_id=s.snapshot_id AND l.status='ACTIVE', pt
  WHERE ST_Intersects(s.geom,pt.g)
  ORDER BY s.area_ha NULLS LAST LIMIT 1
),
car AS (
  SELECT jsonb_build_object(
    'car_code',c.car_code,'status',c.public_status,'created_at',c.created_source_at,
    'updated_at',c.updated_source_at,'area_ha',c.area_ha,'condition',c.public_condition,
    'uf',c.uf,'municipality',c.municipality,'municipality_ibge',c.municipality_ibge,
    'fiscal_modules',c.fiscal_modules,'property_type',c.property_type
  ) AS j
  FROM ld_core.car_area c
  JOIN ld_core.rural_layer l ON l.layer_key=('car_'||lower(c.uf))
    AND l.current_snapshot_id=c.snapshot_id AND l.status='ACTIVE', pt
  WHERE ST_Intersects(c.geom,pt.g)
  ORDER BY c.area_ha NULLS LAST LIMIT 1
),
restr AS (
  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'theme',theme,'authority',authority,'label',label,'category',category,
    'intersects',intersects,'distance_m',distance_m,'source_url',source_url,
    'loaded_at',loaded_at,'source_updated_at',source_updated_at
  ) ORDER BY theme), '[]'::jsonb) AS j
  FROM ld_api.restrictions_for_point(p_lng,p_lat,5000)
  WHERE theme IN ('CONSERVATION_UNIT','INDIGENOUS_LAND','DEFORESTATION','MINING_PROCESS')
)
SELECT jsonb_build_object(
  'sigef',(SELECT j FROM sig),
  'car',(SELECT j FROM car),
  'restrictions',(SELECT j FROM restr),
  'warnings',jsonb_build_array(
    'CAR/SICAR é cadastro declaratório e não prova domínio ou titularidade.',
    'SIGEF certifica a geometria nos termos do sistema; não substitui certidão atual do registro de imóveis.'
  )
)
$fn$;

DO $g$
DECLARE app_role text := coalesce(nullif(current_setting('lotediretor.app_role',true),''),'sentinelx');
BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=app_role) THEN
  EXECUTE format('GRANT SELECT ON ld_core.rural_layer, ld_core.sigef_parcel, ld_core.car_area TO %I',app_role);
  EXECUTE format('GRANT EXECUTE ON FUNCTION ld_api.rural_context(double precision,double precision) TO %I',app_role);
 END IF;
END $g$;
COMMIT;
