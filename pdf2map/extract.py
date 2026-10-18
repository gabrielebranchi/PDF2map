"""Estrazione del testo dal PDF e suddivisione in blocchi per l'LLM."""
from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf


@dataclass
class Chunk:
    section: str | None  # titolo di sezione preso dall'indice del PDF, se presente
    pages: tuple[int, int]  # prima e ultima pagina (numerate da 1)
    text: str  # testo con marcatori [p.N]


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "")  # trattino morbido
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # parole spezzate a fine riga
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_pdf(path: str) -> tuple[list[str], list[list], str]:
    """Restituisce (testo per pagina, indice [livello, titolo, pagina], titolo dai metadati)."""
    with pymupdf.open(path) as doc:
        pages = [_clean(p.get_text("text")) for p in doc]
        toc = doc.get_toc()
        title = ((doc.metadata or {}).get("title") or "").strip()
    return pages, toc, title


def _section_per_page(n_pages: int, toc: list[list]) -> list[str | None]:
    """Assegna a ogni pagina la sezione di livello più alto dell'indice che la contiene."""
    if not toc:
        return [None] * n_pages
    top = min(level for level, _, _ in toc)
    marks = sorted((max(1, page), title.strip()) for level, title, page in toc if level == top)
    out: list[str | None] = []
    for p in range(1, n_pages + 1):
        current = None
        for start, title in marks:
            if start <= p:
                current = title
            else:
                break
        out.append(current)
    return out


def _split_long(text: str, limit: int) -> list[str]:
    """Spezza un testo troppo lungo per paragrafi (o per lunghezza, in extremis)."""
    parts, buf = [], ""
    for para in text.split("\n\n"):
        while len(para) > limit:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(para[:limit])
            para = para[limit:]
        if len(buf) + len(para) + 2 > limit and buf:
            parts.append(buf)
            buf = ""
        buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        parts.append(buf)
    return parts


def make_chunks(pages: list[str], toc: list[list], max_chars: int = 8000) -> list[Chunk]:
    sections = _section_per_page(len(pages), toc)
    chunks: list[Chunk] = []
    buf: list[str] = []
    start = 1
    size = 0
    cur_section: str | None = None

    def flush(end_page: int) -> None:
        nonlocal buf, size
        if buf:
            chunks.append(Chunk(cur_section, (start, end_page), "\n\n".join(buf)))
        buf, size = [], 0

    for i, text in enumerate(pages, start=1):
        if len(text) < 20:  # pagina vuota o scansione senza testo
            continue
        pieces = _split_long(text, max_chars) if len(text) > max_chars else [text]
        for piece in pieces:
            block = f"[p.{i}]\n{piece}"
            new_section = sections[i - 1] != cur_section
            if buf and (new_section or size + len(block) > max_chars):
                flush(i)
            if not buf:
                start, cur_section = i, sections[i - 1]
            buf.append(block)
            size += len(block)
    flush(len(pages))
    # l'ultima pagina reale del blocco è quella dell'ultimo marcatore
    for c in chunks:
        found = [int(n) for n in re.findall(r"\[p\.(\d+)\]", c.text)]
        c.pages = (min(found), max(found))
    return chunks
