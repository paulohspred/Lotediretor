"""Municipal connector spec: load and validate data/connectors/municipal/*.json.

A spec says *where* a municipality publishes a layer and *how* its fields map
to the national schema. It is reviewed in git; the harvester only executes it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = ROOT / "data" / "connectors" / "municipal"
REGISTRY = ROOT / "data" / "source-registry" / "bootstrap.json"

KINDS = {"arcgis_feature_layer", "ogc_wfs", "file"}
STATUSES = {"DRAFT", "APPROVED", "SUSPENDED"}
ROLE_FIELDS = {
    "parcels": {
        "required": {"upstream_key"},
        "optional": {"fiscal_reference", "cib", "sector", "block", "lot", "unit",
                     "postal_code", "street", "house_number", "neighborhood",
                     "land_area_m2", "built_area_m2", "frontage_m",
                     "cadastral_use", "cadastral_status"},
    },
    "zoning": {
        "required": {"upstream_key", "zone_code"},
        "optional": {"zone_name"},
    },
}
# Field names that suggest personal data. They may never be requested,
# even if a municipality publishes them (LGPD minimization, Blueprint §17).
PERSONAL_FIELD = re.compile(
    r"(propriet|contribu|titular|cpf|cnpj|nome_?prop|owner|responsav|"
    r"telefone|email|e_mail|rg\b|nascimento)",
    re.IGNORECASE,
)
_IBGE = re.compile(r"^[0-9]{7}$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


class SpecError(ValueError):
    pass


def spec_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registry_ids() -> set[str]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {s["id"] for s in data["sources"]}


def requested_fields(layer: dict) -> list[str]:
    """Every upstream field the harvester is allowed to request."""
    fields = list(layer["fields"].values())
    fields += layer.get("attribute_allowlist", [])
    return list(dict.fromkeys(fields))


def validate(spec: dict, known_sources: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    ibge = spec.get("municipality_ibge", "")
    if not _IBGE.match(str(ibge)):
        errors.append("municipality_ibge must have 7 digits")
    if spec.get("status") not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if spec.get("status") == "APPROVED" and not (
        spec.get("reviewed_by") and spec.get("reviewed_at")
    ):
        errors.append("APPROVED specs need reviewed_by and reviewed_at")

    layers = spec.get("layers")
    if not isinstance(layers, list) or not layers:
        return errors + ["layers must be a non-empty list"]

    roles = [layer.get("role") for layer in layers]
    if len(roles) != len(set(roles)):
        errors.append("each role may appear only once")

    for i, layer in enumerate(layers):
        p = f"layers[{i}]"
        role = layer.get("role")
        if role not in ROLE_FIELDS:
            errors.append(f"{p}: role must be one of {sorted(ROLE_FIELDS)}")
            continue
        if layer.get("kind") not in KINDS:
            errors.append(f"{p}: kind must be one of {sorted(KINDS)}")
        url = str(layer.get("url", ""))
        if layer.get("kind") != "file" and not url.startswith("https://"):
            errors.append(f"{p}: url must be https")
        if layer.get("kind") == "ogc_wfs" and not layer.get("type_name"):
            errors.append(f"{p}: ogc_wfs needs type_name")
        if known_sources is not None and layer.get("source_id") not in known_sources:
            errors.append(f"{p}: source_id {layer.get('source_id')!r} not in registry")
        if not layer.get("license"):
            errors.append(f"{p}: license (or reviewed terms) is required")

        fields = layer.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"{p}: fields must be an object")
            continue
        spec_roles = ROLE_FIELDS[role]
        missing = spec_roles["required"] - fields.keys()
        unknown = fields.keys() - spec_roles["required"] - spec_roles["optional"]
        if missing:
            errors.append(f"{p}: missing field mappings {sorted(missing)}")
        if unknown:
            errors.append(f"{p}: unknown canonical fields {sorted(unknown)}")
        allow = layer.get("attribute_allowlist", [])
        if not isinstance(allow, list):
            errors.append(f"{p}: attribute_allowlist must be a list")
            allow = []
        for name in list(fields.values()) + allow:
            if not isinstance(name, str) or not _FIELD.match(name):
                errors.append(f"{p}: invalid upstream field name {name!r}")
            elif PERSONAL_FIELD.search(name):
                errors.append(
                    f"{p}: field {name!r} looks like personal data and may not be requested"
                )
        min_features = layer.get("min_features")
        if not isinstance(min_features, int) or min_features < 1:
            errors.append(f"{p}: min_features must be a positive integer")
        srid = layer.get("source_srid")
        if srid is not None and not (isinstance(srid, int) and 1000 < srid < 1_000_000):
            errors.append(f"{p}: source_srid must be an EPSG integer")
    return errors


def load(path: Path, known_sources: set[str] | None = None) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(spec, known_sources)
    if errors:
        raise SpecError(f"{path.name}: " + "; ".join(errors))
    if path.stem != spec["municipality_ibge"]:
        raise SpecError(f"{path.name}: file name must be <ibge>.json")
    return spec
