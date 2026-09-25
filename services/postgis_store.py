#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json

DB_DSN = "dbname=lotediretor user=sentinelx host=/var/run/postgresql"
RUNTIME_SOURCE_ID = "ld-runtime-public-dossier"

IDENTIFIER_NAMESPACES = {
    "3550308": [
        ("SP_SQL", "sql_reference"),
        ("BR_CIB", "cib"),
    ],
    "2611606": [
        ("RECIFE_DSQFL", "dsqfl"),
        ("RECIFE_SEQIMOVEL", "seqimovel"),
    ],
    "3304557": [
        ("RIO_INSCRICAO_IMOBILIARIA", "inscricao_imobiliaria"),
        ("RIO_RGI", "rgi"),
        ("RIO_MATRICULA_CADASTRAL", "matricula"),
        ("RIO_CADPARCEL_REF", "sql_reference"),
    ],
    "3106200": [
        ("BH_LOTE_CTM", "ctm_number"),
        ("BH_LOTE_REF", "sql_reference"),
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_payload(payload: dict) -> dict:
    context = dict(payload.get("context") or {})
    context.pop("queried_at", None)
    source = dict(payload.get("source") or {})
    source.pop("queried_at", None)
    return {
        "feature": payload.get("feature"),
        "context": context,
        "source": source,
        "report": payload.get("report"),
    }


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(
        stable_payload(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "_", value or "").strip("_").lower()
    return text[:180] or "field"


def source_catalog(cur) -> None:
    cur.execute(
        """
        INSERT INTO ld_catalog.source(
            source_id, authority, scope, source_type, access_class,
            license, verification_status, canonical_url, metadata
        )
        VALUES(
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT(source_id) DO UPDATE SET
            authority=EXCLUDED.authority,
            verification_status=EXCLUDED.verification_status,
            metadata=EXCLUDED.metadata
        """,
        (
            RUNTIME_SOURCE_ID,
            "LoteDiretor Brasil",
            "national",
            "derived_public_property_response",
            "DERIVED",
            None,
            "INTERNAL_NORMALIZED_PUBLIC_RESPONSE",
            "https://lotediretor.com",
            Json(
                {
                    "purpose": (
                        "Persist the already privacy-filtered public parcel dossier "
                        "for normalized read-model migration."
                    )
                }
            ),
        ),
    )


def ensure_snapshot(cur, municipality_ibge: str, primary_id: str, payload: dict) -> tuple[str, str]:
    body = canonical_bytes(payload)
    digest = sha256_hex(body)
    internal_url = f"lotediretor://public-property/{municipality_ibge}/{primary_id}"
    cur.execute(
        """
        INSERT INTO ld_catalog.snapshot(
            source_id, captured_at, requested_url, final_url, http_status,
            content_type, content_length, sha256, manifest
        )
        VALUES(%s, now(), %s, %s, 200, 'application/json', %s, %s, %s)
        ON CONFLICT(source_id, sha256) DO UPDATE SET sha256=EXCLUDED.sha256
        RETURNING snapshot_id::text
        """,
        (
            RUNTIME_SOURCE_ID,
            internal_url,
            internal_url,
            len(body),
            digest,
            Json(
                {
                    "municipality_ibge": municipality_ibge,
                    "primary_id": primary_id,
                    "source": payload.get("source") or {},
                }
            ),
        ),
    )
    snapshot_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO ld_catalog.normalized_record(
            source_id, snapshot_id, upstream_key, record_kind,
            observed_at, captured_at, payload_sha256, attributes
        )
        VALUES(%s, %s::uuid, %s, 'PUBLIC_PROPERTY_DOSSIER',
               now(), now(), %s, %s)
        ON CONFLICT(source_id, upstream_key, snapshot_id)
        DO UPDATE SET attributes=EXCLUDED.attributes
        RETURNING record_id::text
        """,
        (
            RUNTIME_SOURCE_ID,
            snapshot_id,
            f"{municipality_ibge}:{primary_id}",
            digest,
            Json(stable_payload(payload)),
        ),
    )
    return snapshot_id, cur.fetchone()[0]


def primary_identifier(municipality_ibge: str, props: dict) -> tuple[str, str]:
    for namespace, key in IDENTIFIER_NAMESPACES.get(municipality_ibge, []):
        value = props.get(key)
        if value not in (None, ""):
            return namespace, str(value)
    feature_id = props.get("municipal_parcel_feature_id")
    return f"MUNICIPAL_PARCEL_{municipality_ibge}", str(feature_id or "unknown")


def ensure_subject(
    cur,
    municipality_ibge: str,
    feature: dict,
    source_record_id: str,
) -> tuple[str, str]:
    props = feature.get("properties") or {}
    namespace, primary_id = primary_identifier(municipality_ibge, props)
    cur.execute(
        """
        SELECT si.subject_id::text
        FROM ld_core.subject_identifier si
        JOIN ld_core.subject s ON s.subject_id=si.subject_id
        WHERE si.namespace=%s AND si.identifier_value=%s
          AND s.municipality_ibge=%s
        ORDER BY si.created_at
        LIMIT 1
        """,
        (namespace, primary_id, municipality_ibge),
    )
    row = cur.fetchone()
    geom_json = json.dumps(feature.get("geometry") or {})
    if row:
        subject_id = row[0]
        cur.execute(
            """
            UPDATE ld_core.subject
            SET canonical_geom=ST_Transform(
                    ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),4674
                ),
                canonical_point=ST_PointOnSurface(
                    ST_Transform(
                        ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),4674
                    )
                ),
                geom_method='OFFICIAL_PARCEL_GEOMETRY',
                geom_confidence='CONFIRMED'
            WHERE subject_id=%s::uuid
            """,
            (geom_json, geom_json, subject_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO ld_core.subject(
                subject_type, municipality_ibge, canonical_geom, canonical_point,
                geom_method, geom_confidence
            )
            VALUES(
                'URBAN_PARCEL', %s,
                ST_Transform(
                    ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),4674
                ),
                ST_PointOnSurface(
                    ST_Transform(
                        ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),4674
                    )
                ),
                'OFFICIAL_PARCEL_GEOMETRY', 'CONFIRMED'
            )
            RETURNING subject_id::text
            """,
            (municipality_ibge, geom_json, geom_json),
        )
        subject_id = cur.fetchone()[0]

    for id_namespace, key in IDENTIFIER_NAMESPACES.get(municipality_ibge, []):
        value = props.get(key)
        if value in (None, ""):
            continue
        cur.execute(
            """
            INSERT INTO ld_core.subject_identifier(
                subject_id, namespace, identifier_value, issuer,
                access_class, source_record_id
            )
            VALUES(%s::uuid,%s,%s,%s,'PUBLIC_QUERY_ONLY',%s::uuid)
            ON CONFLICT(namespace,identifier_value,subject_id) DO NOTHING
            """,
            (
                subject_id,
                id_namespace,
                str(value),
                "Municipal official property source",
                source_record_id,
            ),
        )

    cur.execute(
        """
        INSERT INTO ld_core.parcel_geometry_version(
            subject_id, source_record_id, geom, source_crs,
            area_source_m2, area_calculated_m2, perimeter_calculated_m,
            geometry_role
        )
        SELECT
            %s::uuid, %s::uuid,
            ST_Multi(
                ST_Transform(
                    ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),4674
                )
            ),
            'EPSG:4326',
            %s,
            ST_Area(
                ST_Transform(
                    ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),31983
                )
            ),
            ST_Perimeter(
                ST_Transform(
                    ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),31983
                )
            ),
            'CADASTRAL'
        WHERE NOT EXISTS(
            SELECT 1 FROM ld_core.parcel_geometry_version
            WHERE subject_id=%s::uuid AND source_record_id=%s::uuid
        )
        """,
        (
            subject_id,
            source_record_id,
            geom_json,
            props.get("land_area_m2"),
            geom_json,
            geom_json,
            subject_id,
            source_record_id,
        ),
    )

    cur.execute(
        """
        INSERT INTO ld_core.address(
            subject_id, source_record_id, address_role, street, number,
            complement, municipality_ibge, normalized_text, geom, confidence
        )
        SELECT %s::uuid,%s::uuid,'PROPERTY',%s,%s,%s,%s,%s,
               ST_PointOnSurface(
                   ST_Transform(
                       ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(%s)),4326),4674
                   )
               ),
               'SUPPORTED'
        WHERE NOT EXISTS(
            SELECT 1 FROM ld_core.address
            WHERE subject_id=%s::uuid AND source_record_id=%s::uuid
        )
        """,
        (
            subject_id,
            source_record_id,
            props.get("street"),
            props.get("number"),
            props.get("complement"),
            municipality_ibge,
            ", ".join(
                str(x) for x in [props.get("street"), props.get("number")]
                if x not in (None, "")
            ) or None,
            geom_json,
            subject_id,
            source_record_id,
        ),
    )
    return subject_id, primary_id


def persist_fiscal(cur, subject_id: str, source_record_id: str, context: dict) -> None:
    fiscal = context.get("fiscal") or {}
    iptu = (fiscal.get("iptu") or {}).get("latest") or {}
    pgv = fiscal.get("pgv") or {}
    if iptu or pgv.get("found"):
        cur.execute(
            """
            INSERT INTO ld_domain.fiscal_record(
                subject_id, source_record_id, tax_year, fiscal_identifier,
                land_area_m2, built_area_m2, pgv_land_unit_value_brl_m2,
                attributes
            )
            SELECT %s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s
            WHERE NOT EXISTS(
                SELECT 1 FROM ld_domain.fiscal_record
                WHERE subject_id=%s::uuid AND source_record_id=%s::uuid
            )
            """,
            (
                subject_id,
                source_record_id,
                iptu.get("exercise"),
                iptu.get("sql_reference") or iptu.get("fiscal_identifier"),
                iptu.get("land_area_m2"),
                iptu.get("built_area_m2"),
                pgv.get("vm2t_brl_per_m2") or iptu.get("land_unit_value_brl_m2"),
                Json({"iptu": fiscal.get("iptu"), "pgv": pgv}),
                subject_id,
                source_record_id,
            ),
        )

    for tx in (fiscal.get("itbi") or {}).get("transactions") or []:
        fingerprint = sha256_hex(
            json.dumps(tx, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        )
        cur.execute(
            """
            INSERT INTO ld_domain.transaction_record(
                subject_id, source_record_id, transaction_date,
                transaction_type, transmitted_share, declared_value_brl,
                assessed_value_brl, attributes
            )
            SELECT %s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s
            WHERE NOT EXISTS(
                SELECT 1 FROM ld_domain.transaction_record
                WHERE subject_id=%s::uuid
                  AND attributes->>'fingerprint'=%s
            )
            """,
            (
                subject_id,
                source_record_id,
                tx.get("transaction_date"),
                tx.get("transaction_nature") or tx.get("transaction_type"),
                tx.get("transmitted_pct") or tx.get("transmitted_share"),
                tx.get("transaction_value") or tx.get("declared_value"),
                tx.get("vvr") or tx.get("assessed_value"),
                Json({"fingerprint": fingerprint, **tx}),
                subject_id,
                fingerprint,
            ),
        )


def persist_assertions(cur, subject_id: str, source_record_id: str, report: dict) -> None:
    for section in report.get("sections") or []:
        section_id = section.get("id") or "unknown"
        for item in section.get("actual_values") or []:
            value = item.get("value")
            if value in (None, ""):
                continue
            field_key = slug(item.get("label") or "field")
            cur.execute(
                """
                INSERT INTO ld_evidence.assertion(
                    subject_id, section_id, field_key, assertion_status,
                    assertion_class, value, unit, confidence, access_class,
                    source_record_id, method, captured_at,
                    public_release_allowed, warnings
                )
                SELECT %s::uuid,%s,%s,'AVAILABLE','DERIVED_ANALYSIS',
                       %s,%s,'SUPPORTED','DERIVED',%s::uuid,
                       'LoteDiretor normalized public dossier',now(),true,'[]'::jsonb
                WHERE NOT EXISTS(
                    SELECT 1 FROM ld_evidence.assertion
                    WHERE subject_id=%s::uuid
                      AND source_record_id=%s::uuid
                      AND section_id=%s AND field_key=%s
                )
                """,
                (
                    subject_id,
                    section_id,
                    field_key,
                    Json(value),
                    item.get("unit"),
                    source_record_id,
                    subject_id,
                    source_record_id,
                    section_id,
                    field_key,
                ),
            )


def persist_payload(payload: dict, municipality_ibge: str) -> dict:
    feature = payload.get("feature") or {}
    props = feature.get("properties") or {}
    _, primary_id = primary_identifier(municipality_ibge, props)
    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            source_catalog(cur)
            _, record_id = ensure_snapshot(
                cur, municipality_ibge, primary_id, payload
            )
            subject_id, primary_id = ensure_subject(
                cur, municipality_ibge, feature, record_id
            )
            persist_fiscal(cur, subject_id, record_id, payload.get("context") or {})
            persist_assertions(cur, subject_id, record_id, payload.get("report") or {})
        conn.commit()
    return {
        "subject_id": subject_id,
        "primary_id": primary_id,
        "municipality_ibge": municipality_ibge,
        "persisted_at": utc_now(),
    }
