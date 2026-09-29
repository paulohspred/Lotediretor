"""Derive structured territorial coverage from a source-registry entry.

Shared by validate_registry.py (so bad entries fail CI) and
tools/loaders/load_source_registry.py (so the database gets the same answer).
"""
from __future__ import annotations

import re

UF_CODES = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
}
_IBGE = re.compile(r"^[0-9]{7}$")
# IBGE geocódigo: the first two digits are the UF code.
_UF_BY_PREFIX = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}


class CoverageError(ValueError):
    pass


def derive_coverage(source: dict) -> dict:
    """Return {coverage_level, uf, municipality_ibge, domains}.

    Raises CoverageError when a municipal source has no usable IBGE code,
    because such a source can never be matched to a municipality.
    """
    scope = str(source.get("scope") or "").strip()
    ibge = source.get("municipality_ibge") or source.get("ibge")
    if not ibge and _IBGE.match(scope):
        ibge = scope
    ibge = str(ibge) if ibge else None
    if ibge and not _IBGE.match(ibge):
        raise CoverageError(f"invalid municipality_ibge {ibge!r}")

    uf = source.get("uf")
    prefix = scope.split("_", 1)[0].upper()
    if not uf and prefix in UF_CODES:
        uf = prefix
    if not uf and ibge:
        uf = _UF_BY_PREFIX.get(ibge[:2])
    if uf is not None and uf not in UF_CODES:
        raise CoverageError(f"invalid uf {uf!r}")
    if ibge and uf and _UF_BY_PREFIX.get(ibge[:2]) != uf:
        raise CoverageError(f"uf {uf} does not match IBGE code {ibge}")

    if ibge:
        level = "MUNICIPAL"
    elif scope == "GLOBAL" or scope.startswith("LATAM"):
        level = "GLOBAL"
    elif scope.startswith("BR"):
        level = "NATIONAL"
    elif scope.lower().startswith("state") or prefix in UF_CODES or scope in UF_CODES:
        if not uf:
            raise CoverageError(f"state-level scope {scope!r} without uf")
        level = "STATE"
    else:
        raise CoverageError(
            f"municipal/unknown scope {scope!r} requires municipality_ibge"
        )

    domains = source.get("domain") or []
    if isinstance(domains, str):
        domains = [domains]
    return {
        "coverage_level": level,
        "uf": uf if level in {"STATE", "MUNICIPAL"} else None,
        "municipality_ibge": ibge,
        "domains": sorted({str(d) for d in domains}),
    }
