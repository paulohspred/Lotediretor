#!/usr/bin/env python3
"""Persist a privacy-filtered property dossier response into LoteDiretor PostGIS."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json


def now():
    return datetime.now(timezone.utc)


def compact(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def primary_identity(ibge, props):
    if ibge == "3550308":
        value = props.get("sql_reference")
        if not value:
            raise ValueError("São Paulo dossier has no SQL")
        return "PMSP_SQL", str(value)
    if ibge == "2611606":
        value = props.get("dsqfl") or props.get("sql_reference")
        if not value:
            raise ValueError("Recife dossier has no DSQFL")
        return "RECIFE_DSQFL", str(value)
    raise ValueError(f"unsupported municipality {ibge}")


def access_class(source_id):
    if source_id == "sp-sao-paulo-geosampa-wfs":
        return "OPEN_REUSABLE"
    return "PUBLIC_QUERY_ONLY"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--ibge", required=True)
    ap.add_argument("--dbname", default="lotediretor")
    args = ap.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not payload.get("found"):
        raise SystemExit("input is not a found property dossier")
    feature = payload["feature"]
    props = feature.get("properties") or {}
    geom = feature.get("geometry")
    if not geom:
        raise SystemExit("input dossier has no parcel geometry")
    namespace, identifier = primary_identity(args.ibge, props)
    source = payload.get("source") or {}
    source_id = source.get("id") or f"property-resolver-{args.ibge}"
    raw = compact(payload)
    digest = hashlib.sha256(raw).hexdigest()
    captured = now()

    conn = psycopg2.connect(dbname=args.dbname)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ld_catalog.source
                   (source_id,authority,scope,source_type,access_class,license,
                    verification_status,canonical_url,metadata)
                   VALUES (%s,%s,'municipality','PROPERTY_RESOLVER',%s,%s,
                           'VALIDATED_PROPERTY_RESOLVER',%s,%s)
                   ON CONFLICT (source_id) DO UPDATE SET
                     authority=EXCLUDED.authority,
                     access_class=EXCLUDED.access_class,
                     license=COALESCE(EXCLUDED.license,ld_catalog.source.license),
                     metadata=ld_catalog.source.metadata || EXCLUDED.metadata""",
                (
                    source_id,
                    source.get("authority") or "Official municipal source",
                    access_class(source_id),
                    source.get("license"),
                    source.get("layer"),
                    Json({"method": source.get("method"), "municipality_ibge": args.ibge}),
                ),
            )
            synthetic_url = f"lotediretor://property/{args.ibge}/{namespace}/{identifier}"
            cur.execute(
                """INSERT INTO ld_catalog.snapshot
                   (source_id,captured_at,requested_url,final_url,http_status,
                    content_type,content_length,sha256,manifest)
                   VALUES (%s,%s,%s,%s,200,'application/json',%s,%s,%s)
                   ON CONFLICT (source_id,sha256) DO UPDATE SET
                     captured_at=EXCLUDED.captured_at
                   RETURNING snapshot_id""",
                (source_id, captured, synthetic_url, synthetic_url, len(raw), digest,
                 Json({"public_safe": True, "query": payload.get("clicked")})),
            )
            snapshot_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO ld_catalog.normalized_record
                   (source_id,snapshot_id,upstream_key,record_kind,observed_at,
                    captured_at,payload_sha256,attributes)
                   VALUES (%s,%s,%s,'PROPERTY_DOSSIER_QUERY',%s,%s,%s,%s)
                   ON CONFLICT (source_id,upstream_key,snapshot_id) DO UPDATE SET
                     observed_at=EXCLUDED.observed_at
                   RETURNING record_id""",
                (source_id, snapshot_id, identifier, captured, captured, digest, Json(props)),
            )
            record_id = cur.fetchone()[0]

            cur.execute(
                """SELECT subject_id FROM ld_core.subject_identifier
                   WHERE namespace=%s AND identifier_value=%s LIMIT 1""",
                (namespace, identifier),
            )
            row = cur.fetchone()
            geojson = json.dumps(geom, ensure_ascii=False)
            if row:
                subject_id = row[0]
                cur.execute(
                    """UPDATE ld_core.subject
                       SET canonical_geom=ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674),
                           canonical_point=ST_PointOnSurface(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674)),
                           geom_method='OFFICIAL_PARCEL_QUERY',geom_confidence='CONFIRMED'
                       WHERE subject_id=%s""",
                    (geojson, geojson, subject_id),
                )
            else:
                cur.execute(
                    """INSERT INTO ld_core.subject
                       (subject_type,municipality_ibge,canonical_geom,canonical_point,
                        geom_method,geom_confidence)
                       VALUES ('URBAN_PARCEL',%s,
                         ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674),
                         ST_PointOnSurface(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674)),
                         'OFFICIAL_PARCEL_QUERY','CONFIRMED')
                       RETURNING subject_id""",
                    (args.ibge, geojson, geojson),
                )
                subject_id = cur.fetchone()[0]

            identifiers = [(namespace, identifier)]
            if args.ibge == "3550308" and props.get("cib"):
                identifiers.append(("CIB", str(props["cib"])))
            if args.ibge == "2611606" and props.get("seqimovel"):
                identifiers.append(("RECIFE_SEQIMOVEL", str(props["seqimovel"])))
            for ns, val in identifiers:
                cur.execute(
                    """INSERT INTO ld_core.subject_identifier
                       (subject_id,namespace,identifier_value,issuer,access_class,
                        source_record_id)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (namespace,identifier_value,subject_id) DO UPDATE SET
                         source_record_id=EXCLUDED.source_record_id""",
                    (
                        subject_id, ns, val,
                        source.get("authority") or "Municipal authority",
                        access_class(source_id), record_id,
                    ),
                )

            cur.execute(
                """SELECT 1 FROM ld_core.parcel_geometry_version
                   WHERE subject_id=%s AND source_record_id=%s""",
                (subject_id, record_id),
            )
            if not cur.fetchone():
                cur.execute(
                    """INSERT INTO ld_core.parcel_geometry_version
                       (subject_id,source_record_id,geom,source_crs,area_source_m2,
                        area_calculated_m2,geometry_role)
                       VALUES (%s,%s,
                         ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674)),
                         'EPSG:4326',%s,
                         ST_Area(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),31983)),
                         'CADASTRAL')""",
                    (subject_id, record_id, geojson, props.get("land_area_m2"), geojson),
                )

            fiscal = (payload.get("context") or {}).get("fiscal") or {}
            iptu = (fiscal.get("iptu") or {}).get("latest") or {}
            pgv = fiscal.get("pgv") or {}
            cur.execute(
                """SELECT 1 FROM ld_domain.fiscal_record
                   WHERE subject_id=%s AND source_record_id=%s""",
                (subject_id, record_id),
            )
            if not cur.fetchone() and (iptu or pgv):
                cur.execute(
                    """INSERT INTO ld_domain.fiscal_record
                       (subject_id,source_record_id,tax_year,fiscal_identifier,
                        land_area_m2,built_area_m2,pgv_land_unit_value_brl_m2,
                        pgv_building_unit_value_brl_m2,attributes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        subject_id, record_id,
                        2026 if args.ibge == "3550308" else None,
                        identifier,
                        iptu.get("land_area_m2") or props.get("land_area_m2"),
                        iptu.get("built_area_m2") or props.get("built_area_m2"),
                        pgv.get("vm2t_brl_per_m2"),
                        iptu.get("building_unit_value_brl_m2"),
                        Json({"iptu": iptu, "pgv": pgv}),
                    ),
                )

            for section in (payload.get("report") or {}).get("sections") or []:
                for item in section.get("actual_values") or []:
                    value = item.get("value")
                    if value in (None, ""):
                        continue
                    field_key = item.get("label") or "value"
                    cur.execute(
                        """DELETE FROM ld_evidence.assertion
                           WHERE subject_id=%s AND section_id=%s AND field_key=%s
                             AND source_record_id=%s""",
                        (subject_id, section.get("id"), field_key, record_id),
                    )
                    cur.execute(
                        """INSERT INTO ld_evidence.assertion
                           (subject_id,section_id,field_key,assertion_status,
                            assertion_class,value,unit,confidence,access_class,
                            source_record_id,method,observed_at,captured_at,
                            public_release_allowed)
                           VALUES (%s,%s,%s,'AVAILABLE','OFFICIAL_QUERY_RESULT',
                                   %s,%s,'SUPPORTED',%s,%s,%s,%s,%s,true)""",
                        (
                            subject_id, section.get("id"), field_key,
                            Json(value), item.get("unit"),
                            access_class(source_id), record_id,
                            source.get("method") or "property dossier resolver",
                            captured, captured,
                        ),
                    )

            cur.execute(
                """INSERT INTO ld_api.property_dossier_cache
                   (subject_id,municipality_ibge,primary_namespace,
                    primary_identifier,parcel_geom,dossier,dossier_sha256,
                    generated_at,expires_at,source_summary)
                   VALUES (%s,%s,%s,%s,
                     ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),4674),
                     %s,%s,%s,%s,%s)
                   ON CONFLICT (municipality_ibge,primary_namespace,primary_identifier)
                   DO UPDATE SET
                     subject_id=EXCLUDED.subject_id,
                     parcel_geom=EXCLUDED.parcel_geom,
                     dossier=EXCLUDED.dossier,
                     dossier_sha256=EXCLUDED.dossier_sha256,
                     generated_at=EXCLUDED.generated_at,
                     expires_at=EXCLUDED.expires_at,
                     source_summary=EXCLUDED.source_summary""",
                (
                    subject_id,args.ibge,namespace,identifier,geojson,Json(payload),
                    digest,captured,None,Json(source),
                ),
            )
            print(json.dumps({
                "subject_id": str(subject_id),
                "municipality_ibge": args.ibge,
                "primary_namespace": namespace,
                "primary_identifier": identifier,
                "dossier_sha256": digest,
            }, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
