#!/usr/bin/env python3
"""Validate LoteDiretor property-dossier instances using stdlib invariants.

This complements JSON Schema validation with provenance rules:
- available facts need a value and traceable evidence;
- derived facts need a method and upstream facts;
- no-evidence facts cannot carry a value;
- restricted/query-only facts are not public by default;
- fact and geometry references must resolve.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ALLOWED_COMPLETION = {"L0", "L1", "L2", "L3", "L4", "UNASSESSED"}
ALLOWED_SECTION_STATUS = {
    "COMPLETE", "PARTIAL", "UNAVAILABLE_PUBLICLY", "REQUIRES_QUERY",
    "REQUIRES_USER_DOCUMENT", "RESTRICTED", "NOT_APPLICABLE", "UNKNOWN",
}
ALLOWED_FACT_STATUS = {
    "AVAILABLE", "NOT_AVAILABLE", "NOT_PUBLICLY_AVAILABLE", "QUERY_ONLY",
    "REQUIRES_USER_DOCUMENT", "RESTRICTED", "NOT_APPLICABLE", "UNKNOWN",
    "CONFLICTING_EVIDENCE",
}
ALLOWED_EVIDENCE = {
    "OFFICIAL_SOURCE", "OFFICIAL_DOCUMENT", "USER_DOCUMENT", "DERIVED",
    "INDICATIVE_PUBLIC_SOURCE", "RESTRICTED_OFFICIAL_SOURCE", "NO_EVIDENCE",
}
ALLOWED_ACCESS = {
    "OPEN_REUSABLE", "PUBLIC_QUERY_ONLY", "PUBLIC_READ_ONLY", "AUTH_REQUIRED",
    "USER_PRIVATE", "RESTRICTED", "LICENSE_REVIEW_REQUIRED", "UNKNOWN",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    require(data.get("schema_version") == "0.1.0", "schema_version must be 0.1.0", errors)
    require(bool(data.get("dossier_id")), "dossier_id is required", errors)
    require(bool(data.get("generated_at")), "generated_at is required", errors)
    require(
        data.get("completion_level", "UNASSESSED") in ALLOWED_COMPLETION,
        "invalid completion_level",
        errors,
    )

    subject = data.get("subject")
    require(isinstance(subject, dict), "subject must be an object", errors)
    if isinstance(subject, dict):
        require(
            isinstance(subject.get("identity_refs"), list),
            "subject.identity_refs must be an array",
            errors,
        )

    geometry_ids = set()
    if isinstance(subject, dict):
        for i, geometry in enumerate(subject.get("geometry_refs", [])):
            gid = geometry.get("id") if isinstance(geometry, dict) else None
            require(bool(gid), f"subject.geometry_refs[{i}].id is required", errors)
            if gid:
                require(gid not in geometry_ids, f"duplicate geometry id: {gid}", errors)
                geometry_ids.add(gid)

    sections = data.get("sections")
    require(isinstance(sections, list) and sections, "sections must be a non-empty array", errors)

    fact_ids: set[str] = set()
    facts: list[tuple[str, dict]] = []

    for sidx, section in enumerate(sections or []):
        prefix = f"sections[{sidx}]"
        require(isinstance(section, dict), f"{prefix} must be an object", errors)
        if not isinstance(section, dict):
            continue
        require(bool(section.get("id")), f"{prefix}.id is required", errors)
        require(
            section.get("status") in ALLOWED_SECTION_STATUS,
            f"{prefix}.status is invalid",
            errors,
        )
        sfacts = section.get("facts")
        require(isinstance(sfacts, list), f"{prefix}.facts must be an array", errors)
        for fidx, fact in enumerate(sfacts or []):
            fp = f"{prefix}.facts[{fidx}]"
            require(isinstance(fact, dict), f"{fp} must be an object", errors)
            if not isinstance(fact, dict):
                continue
            fid = fact.get("id")
            require(bool(fid), f"{fp}.id is required", errors)
            if fid:
                require(fid not in fact_ids, f"duplicate fact id: {fid}", errors)
                fact_ids.add(fid)
            facts.append((fp, fact))

    for fp, fact in facts:
        status = fact.get("status")
        evidence = fact.get("evidence_class")
        access = fact.get("access_class")
        provenance = fact.get("provenance")

        require(bool(fact.get("field")), f"{fp}.field is required", errors)
        require(status in ALLOWED_FACT_STATUS, f"{fp}.status is invalid", errors)
        require(evidence in ALLOWED_EVIDENCE, f"{fp}.evidence_class is invalid", errors)
        require(access in ALLOWED_ACCESS, f"{fp}.access_class is invalid", errors)
        require(isinstance(provenance, dict), f"{fp}.provenance must be an object", errors)

        if isinstance(provenance, dict):
            require(
                bool(provenance.get("captured_at")),
                f"{fp}.provenance.captured_at is required",
                errors,
            )
            digest = provenance.get("snapshot_sha256")
            if digest is not None:
                require(
                    bool(SHA256.fullmatch(digest)),
                    f"{fp}.provenance.snapshot_sha256 is invalid",
                    errors,
                )

        if status == "AVAILABLE":
            require("value" in fact, f"{fp}: AVAILABLE fact must include value", errors)
            require(
                evidence != "NO_EVIDENCE",
                f"{fp}: AVAILABLE fact cannot use NO_EVIDENCE",
                errors,
            )
            if evidence not in {"USER_DOCUMENT", "DERIVED"} and isinstance(provenance, dict):
                require(
                    bool(provenance.get("source_id")),
                    f"{fp}: AVAILABLE fact needs provenance.source_id",
                    errors,
                )
                require(
                    bool(provenance.get("authority")),
                    f"{fp}: AVAILABLE fact needs provenance.authority",
                    errors,
                )

        if evidence == "DERIVED":
            require(bool(fact.get("method")), f"{fp}: DERIVED fact needs method", errors)
            upstream = fact.get("upstream_fact_ids")
            require(
                isinstance(upstream, list) and upstream,
                f"{fp}: DERIVED fact needs upstream_fact_ids",
                errors,
            )

        if evidence == "NO_EVIDENCE":
            require("value" not in fact, f"{fp}: NO_EVIDENCE fact must not carry value", errors)

        if status in {"QUERY_ONLY", "RESTRICTED", "REQUIRES_USER_DOCUMENT"}:
            require(
                not fact.get("public_release_allowed", False),
                f"{fp}: restricted/query/user-document fact cannot default to public release",
                errors,
            )

        geometry_ref = fact.get("geometry_ref")
        if geometry_ref is not None:
            require(
                geometry_ref in geometry_ids,
                f"{fp}: unknown geometry_ref {geometry_ref}",
                errors,
            )

    for fp, fact in facts:
        for upstream in fact.get("upstream_fact_ids", []):
            require(
                upstream in fact_ids,
                f"{fp}: unknown upstream fact id {upstream}",
                errors,
            )

    unknowns = data.get("unknowns")
    require(isinstance(unknowns, list), "unknowns must be an array", errors)
    for idx, unknown in enumerate(unknowns or []):
        up = f"unknowns[{idx}]"
        require(isinstance(unknown, dict), f"{up} must be an object", errors)
        if isinstance(unknown, dict):
            require(bool(unknown.get("field")), f"{up}.field is required", errors)
            require(bool(unknown.get("reason")), f"{up}.reason is required", errors)
            require(bool(unknown.get("next_action")), f"{up}.next_action is required", errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dossier", type=Path)
    args = parser.parse_args()

    try:
        errors = validate(args.dossier)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"{len(errors)} validation error(s)")
        return 1

    print(f"OK: {args.dossier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
