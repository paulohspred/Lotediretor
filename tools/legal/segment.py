"""Split Brazilian legal text into provisions (artigo, parágrafo, inciso…).

Pure functions, no I/O, so they are unit-tested. The splitter is deliberately
conservative: a line only starts a provision when it matches the formal
markers used in Brazilian legislation (LC 95/1998 drafting rules).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ARTICLE = re.compile(r"^\s*Art(?:igo)?\.?\s*(\d+[A-Z]?)\s*[º°o]?\s*[-–—.]?\s*(.*)$", re.I)
PARAGRAPH = re.compile(r"^\s*(?:§\s*(\d+)\s*[º°o]?|Par[aá]grafo\s+[uú]nico)\s*[-–—.]?\s*(.*)$", re.I)
INCISO = re.compile(r"^\s*([IVXLC]+)\s*[-–—]\s*(.*)$")
ALINEA = re.compile(r"^\s*([a-z])\)\s*(.*)$")
ANNEX = re.compile(r"^\s*ANEXO\s+([IVXLC\d]+[A-Z]?)\b\s*[-–—:.]?\s*(.*)$")
HEADING = re.compile(r"^\s*(T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O)\s+([IVXLC\d]+)\b\s*[-–—:.]?\s*(.*)$", re.I)
# Page furniture that pdftotext leaves between pages.
NOISE = re.compile(r"^\s*(\d{1,4}|p[aá]gina\s+\d+(\s+de\s+\d+)?)\s*$", re.I)


@dataclass
class Provision:
    kind: str
    path: str
    page_start: int
    page_end: int
    lines: list[str] = field(default_factory=list)
    parent_index: int | None = None

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.lines)).strip()


def _ordinal(n: str) -> str:
    return f"{n}º" if n.isdigit() and int(n) < 10 else n


def segment(pages: list[str]) -> list[Provision]:
    """pages: text of each page (1-based order). Returns provisions in order."""
    out: list[Provision] = []
    article_idx = paragraph_idx = inciso_idx = None
    article = paragraph = inciso = None

    def start(kind: str, path: str, page: int, first: str, parent: int | None) -> int:
        out.append(Provision(kind, path, page, page, [first] if first else [], parent))
        return len(out) - 1

    for page_no, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            line = raw.strip()
            if not line or NOISE.match(line):
                continue
            if m := HEADING.match(line):
                kind = {"T": "TITULO", "C": "CAPITULO", "S": "SECAO"}[m.group(1)[0].upper()]
                start(kind, f"{m.group(1).title()} {m.group(2)}", page_no, line, None)
                article = paragraph = inciso = None
                article_idx = paragraph_idx = inciso_idx = None
                continue
            if m := ANNEX.match(line):
                article = f"Anexo {m.group(1)}"
                article_idx = start("ANEXO", article, page_no, line, None)
                paragraph = inciso = None
                paragraph_idx = inciso_idx = None
                continue
            if m := ARTICLE.match(line):
                article = f"art. {_ordinal(m.group(1))}"
                article_idx = start("ARTIGO", article, page_no, line, None)
                paragraph = inciso = None
                paragraph_idx = inciso_idx = None
                continue
            if article and (m := PARAGRAPH.match(line)):
                paragraph = f"§ {_ordinal(m.group(1))}" if m.group(1) else "parágrafo único"
                inciso = None
                inciso_idx = None
                paragraph_idx = start("PARAGRAFO", f"{article} {paragraph}", page_no, line, article_idx)
                continue
            if article and (m := INCISO.match(line)):
                inciso = f"inc. {m.group(1)}"
                base = f"{article} {paragraph} " if paragraph else f"{article} "
                parent = paragraph_idx if paragraph_idx is not None else article_idx
                inciso_idx = start("INCISO", f"{base}{inciso}", page_no, line, parent)
                continue
            if article and inciso and (m := ALINEA.match(line)):
                base = f"{article} {paragraph} " if paragraph else f"{article} "
                start("ALINEA", f"{base}{inciso} al. {m.group(1)}", page_no, line, inciso_idx)
                continue
            if out:
                out[-1].lines.append(line)
                out[-1].page_end = page_no
            else:
                start("PREAMBULO", "preâmbulo", page_no, line, None)
    return [p for p in out if p.text]
