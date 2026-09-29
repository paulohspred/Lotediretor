"""Extract CANDIDATE urban parameters from legal text.

Heuristic by design: every result is a CANDIDATE that a person must confirm
(Blueprint §8/§16). Each candidate carries the exact excerpt it came from.
Numbers use the Brazilian decimal comma.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EXTRACTOR_VERSION = "legal-rules-heuristic-1"

NUM = r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)"


def to_number(raw: str) -> float:
    raw = raw.strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")  # "1.000" is one thousand in pt-BR
    return float(raw)


@dataclass
class Candidate:
    parameter: str
    value: float | None
    unit: str
    use_condition: str
    excerpt: str
    no_restriction: bool = False


def _clip(text: str, start: int, end: int, pad: int = 60) -> str:
    return text[max(0, start - pad): min(len(text), end + pad)].strip()


def _use_blocks(section: str) -> list[tuple[str, str]]:
    """Split 'a) residência unifamiliar: ... b) comércio ...: ...' into uses."""
    parts = re.split(r"(?:^|\s)([a-h])\)\s*", section)
    if len(parts) < 3:
        return [("GERAL", section)]
    blocks = []
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1]
        use, _, rest = body.partition(":")
        use = re.sub(r"\s+", " ", use).strip(" .;=") or "GERAL"
        # "a) de frente = 15,00m" is an item, not a use label.
        if len(use) > 80 or "=" in use or not rest:
            use, rest = "GERAL", body
        blocks.append((use, rest))
    return blocks


def _section(text: str, header: str, next_headers: str) -> str | None:
    m = re.search(header + r"(.*?)(?=" + next_headers + r"|$)", text, re.I | re.S)
    return m.group(1) if m else None


ROMAN_HEADER = r"\b[IVX]+\s*[-–—]\s*"


def extract(text: str) -> list[Candidate]:
    t = re.sub(r"\s+", " ", text)
    out: list[Candidate] = []

    # Lot size / frontage, usually in the article head.
    if m := re.search(r"[áa]rea m[íi]nima de\s*" + NUM + r"\s*m(?:2|²)", t, re.I):
        out.append(Candidate("LOTE_MINIMO_M2", to_number(m.group(1)), "m2", "GERAL",
                             _clip(t, m.start(), m.end())))
    if m := re.search(r"frente m[íi]nima de\s*" + NUM + r"\s*m\b", t, re.I):
        out.append(Candidate("TESTADA_MINIMA_M", to_number(m.group(1)), "m", "GERAL",
                             _clip(t, m.start(), m.end())))

    ca = _section(t, r"coeficiente de aproveitamento\s*:?", ROMAN_HEADER)
    if ca:
        for use, body in _use_blocks(ca):
            for label, param in (("m[íi]nimo", "CA_MINIMO"), ("b[áa]sico", "CA_BASICO"),
                                 ("m[áa]ximo", "CA_MAXIMO")):
                if m := re.search(label + r"\s*=\s*" + NUM, body, re.I):
                    out.append(Candidate(param, to_number(m.group(1)), "ratio", use,
                                         _clip(body, m.start(), m.end(), 40)))

    to = _section(t, r"taxa de ocupa[çc][ãa]o\s*:?", ROMAN_HEADER)
    if to:
        for use, body in _use_blocks(to):
            # First percentage of the block = main rule; others are conditions.
            if m := re.search(NUM + r"\s*%", body):
                out.append(Candidate("TO_MAXIMA", to_number(m.group(1)), "percent", use,
                                     _clip(body, m.start(), m.end(), 60)))

    recuos = _section(t, r"recuos\s*:?", ROMAN_HEADER + r"|§\s*\d")
    if recuos:
        for use, body in _use_blocks(recuos):
            for label, param in (("frente", "RECUO_FRONTAL_M"), ("laterais|lateral", "RECUO_LATERAL_M"),
                                 ("fundos?", "RECUO_FUNDOS_M")):
                m = re.search(r"(?:de\s+)?(?:" + label + r")\s*=\s*(?:" + NUM + r"\s*m|(sem restri[çc][õo]es))",
                              body, re.I)
                if not m:
                    continue
                if m.group(2):
                    out.append(Candidate(param, None, "m", use,
                                         _clip(body, m.start(), m.end(), 40), no_restriction=True))
                else:
                    out.append(Candidate(param, to_number(m.group(1)), "m", use,
                                         _clip(body, m.start(), m.end(), 40)))
    return out
