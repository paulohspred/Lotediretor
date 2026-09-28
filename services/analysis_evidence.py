#!/usr/bin/env python3
from __future__ import annotations

from uuid import UUID

import psycopg2

DB_DSN = "dbname=lotediretor user=sentinelx host=/var/run/postgresql"

HUMAN_AUTHORITY = {
    "3550308": "Prefeitura de São Paulo",
    "2611606": "Prefeitura do Recife",
    "3304557": "Prefeitura da Cidade do Rio de Janeiro",
    "3106200": "Prefeitura de Belo Horizonte",
    "2507507": "Prefeitura de João Pessoa",
}

IDENTIFIER_LABEL = {
    "SP_SQL": "Inscrição fiscal municipal",
    "BR_CIB": "Código imobiliário nacional",
    "RECIFE_DSQFL": "Inscrição fiscal municipal",
    "RECIFE_SEQIMOVEL": "Sequência cadastral municipal",
    "RIO_INSCRICAO_IMOBILIARIA": "Inscrição imobiliária municipal",
    "RIO_RGI": "Referência cadastral RGI",
    "RIO_MATRICULA_CADASTRAL": "Referência cadastral de matrícula",
    "RIO_CADPARCEL_REF": "Referência cadastral municipal",
    "BH_LOTE_CTM": "Identificação cadastral do lote",
    "BH_LOTE_REF": "Referência cadastral municipal",
    "JP_CODIGO_CARTOGRAFICO": "Código cartográfico municipal",
    "JP_LOTE_REF": "Referência cadastral municipal",
}


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def _slug(value: str) -> str:
    import re
    text = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "_", value or "").strip("_").lower()
    return text[:180] or "field"


def get_analysis_evidence(analysis_run_id: str) -> dict | None:
    try:
        run_uuid = str(UUID(str(analysis_run_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_analysis_run_id")

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT analysis_run_id::text,status,municipality_ibge::text,
                       primary_namespace,primary_identifier,lineage_status,
                       engine_version,contract_version,input_sha256,result_sha256,
                       created_at,completed_at
                FROM ld_analysis.analysis_run
                WHERE analysis_run_id=%s::uuid
                """,
                (run_uuid,),
            )
            run = cur.fetchone()
            if not run:
                return None

            (
                run_id,
                status,
                municipality_ibge,
                namespace,
                identifier,
                lineage_status,
                engine_version,
                contract_version,
                input_sha,
                result_sha,
                created_at,
                completed_at,
            ) = run

            cur.execute(
                """
                SELECT report_payload,report_sha256
                FROM ld_analysis.report_snapshot
                WHERE analysis_run_id=%s::uuid
                """,
                (run_id,),
            )
            report_row = cur.fetchone()
            report_payload = report_row[0] if report_row else {}
            report_sha = report_row[1] if report_row else None

            section_titles: dict[str, str] = {}
            labels: dict[tuple[str, str], str] = {}
            for section in (report_payload or {}).get("sections") or []:
                section_id = section.get("id") or "unknown"
                section_titles[section_id] = section.get("title") or "Informações"
                for item in section.get("actual_values") or []:
                    label = item.get("label")
                    if label:
                        labels[(section_id, _slug(label))] = label

            cur.execute(
                """
                SELECT ai.input_role,s.captured_at,s.sha256,s.content_type,
                       s.source_updated_at,nr.record_kind,nr.payload_sha256
                FROM ld_analysis.analysis_input ai
                JOIN ld_catalog.snapshot s ON s.snapshot_id=ai.snapshot_id
                LEFT JOIN ld_catalog.normalized_record nr
                  ON nr.record_id=ai.normalized_record_id
                WHERE ai.analysis_run_id=%s::uuid
                ORDER BY s.captured_at,ai.input_role
                """,
                (run_id,),
            )
            inputs = []
            for row in cur.fetchall():
                (
                    input_role,
                    captured_at,
                    snapshot_sha,
                    content_type,
                    source_updated_at,
                    record_kind,
                    payload_sha,
                ) = row
                inputs.append(
                    {
                        "kind": "Snapshot congelado do dossiê público",
                        "authority": HUMAN_AUTHORITY.get(
                            municipality_ibge, "Fonte pública municipal"
                        ),
                        "captured_at": _iso(captured_at),
                        "source_updated_at": _iso(source_updated_at),
                        "content_type": content_type,
                        "snapshot_sha256": snapshot_sha,
                        "normalized_payload_sha256": payload_sha,
                        "role": (
                            "Entrada principal da análise"
                            if input_role == "PRIMARY_PROPERTY_SNAPSHOT"
                            else "Entrada de contexto"
                        ),
                        "record_kind": (
                            "Dossiê público normalizado"
                            if record_kind == "PUBLIC_PROPERTY_DOSSIER"
                            else record_kind
                        ),
                    }
                )

            cur.execute(
                """
                SELECT finding_id::text,assertion_id::text,section_id,
                       field_key,value,unit,confidence
                FROM ld_analysis.finding
                WHERE analysis_run_id=%s::uuid
                ORDER BY section_id,field_key,finding_id
                """,
                (run_id,),
            )
            confidence_label = {
                "CONFIRMED": "Confirmada",
                "SUPPORTED": "Suportada",
                "INDICATIVE": "Indicativa",
                "UNKNOWN": "Desconhecida",
                "CONFLICTING": "Conflitante",
            }
            findings = []
            for row in cur.fetchall():
                (
                    finding_id,
                    assertion_id,
                    section_id,
                    field_key,
                    value,
                    unit,
                    confidence,
                ) = row
                findings.append(
                    {
                        "evidence_id": finding_id,
                        "assertion_id": assertion_id,
                        "section": section_titles.get(section_id, "Informações"),
                        "label": labels.get(
                            (section_id, field_key),
                            field_key.replace("_", " ").strip().capitalize(),
                        ),
                        "value": value,
                        "unit": unit,
                        "confidence": confidence_label.get(confidence, confidence),
                    }
                )

            complete = lineage_status == "SOURCE_SNAPSHOTS_COMPLETE"
            return {
                "analysis_run_id": run_id,
                "status": "Concluída" if status == "COMPLETED" else status,
                "property_reference": {
                    "label": IDENTIFIER_LABEL.get(
                        namespace, "Referência cadastral municipal"
                    ),
                    "value": identifier,
                },
                "created_at": _iso(created_at),
                "completed_at": _iso(completed_at),
                "engine": {
                    "version": engine_version,
                    "contract_version": contract_version,
                },
                "lineage": {
                    "complete_per_source": complete,
                    "status": (
                        "Snapshots individuais por fonte"
                        if complete
                        else "Snapshot agregado do dossiê público"
                    ),
                    "note": (
                        "Cada fonte de origem está congelada individualmente."
                        if complete
                        else (
                            "A execução é imutável pelo snapshot agregado do dossiê "
                            "público. A migração para snapshots individuais por "
                            "fonte ainda não está concluída."
                        )
                    ),
                },
                "integrity": {
                    "input_sha256": input_sha,
                    "result_sha256": result_sha,
                    "report_sha256": report_sha,
                },
                "inputs": inputs,
                "findings": findings,
            }
