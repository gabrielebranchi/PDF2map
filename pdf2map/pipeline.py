"""Pipeline: PDF -> blocchi -> LLM -> fusione in un'unica mappa."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from .extract import Chunk, make_chunks, read_pdf
from .llm import build_schema, group_prompt, group_schema, system_prompt

Progress = Callable[[int, int, str], None]


# ---------- pulizia e fusione ----------

def clean_node(n: dict, max_children: int = 12) -> dict | None:
    title = str(n.get("title", "")).strip()
    if not title:
        return None
    page = n.get("page")
    summary = str(n.get("summary") or "").strip()
    out = {
        "title": title[:120],
        "page": page if isinstance(page, int) and page > 0 else None,
        "summary": summary[:400],
        "children": [],
    }
    for k in (n.get("children") or [])[:max_children]:
        if isinstance(k, dict) and (c := clean_node(k, max_children)):
            out["children"].append(c)
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _same(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    # titoli corti che differiscono di un carattere ("Fase A" / "Fase B") restano distinti
    return min(len(na), len(nb)) >= 12 and SequenceMatcher(None, na, nb).ratio() >= 0.88


def merge_into(dst: list[dict], src: list[dict]) -> None:
    """Aggiunge i nodi di src a dst, unendo quelli con titolo uguale o molto simile."""
    for n in src:
        match = next((d for d in dst if _same(d["title"], n["title"])), None)
        if match is None:
            dst.append(n)
            continue
        if n.get("page") and (not match.get("page") or n["page"] < match["page"]):
            match["page"] = n["page"]
        if n.get("summary") and not match.get("summary"):
            match["summary"] = n["summary"]
        merge_into(match["children"], n["children"])


def _infer_pages(n: dict) -> int | None:
    """Un nodo senza pagina prende la più bassa tra quelle dei suoi discendenti."""
    kid_pages = [p for c in n["children"] if (p := _infer_pages(c))]
    n["page"] = n.get("page") or (min(kid_pages) if kid_pages else None)
    return n["page"]


def _inherit_pages(n: dict, default: int | None) -> None:
    n["page"] = n.get("page") or default
    for c in n["children"]:
        _inherit_pages(c, n["page"])


def fill_pages(node: dict, default: int | None) -> None:
    """Completa le pagine mancanti: dai discendenti, poi dal genitore, infine dall'inizio del blocco."""
    _infer_pages(node)
    _inherit_pages(node, default)


# ---------- pulizia ----------

_GENERIC_CHILD = {"definizione", "descrizione", "panoramica"}


def tidy(node: dict) -> None:
    """Toglie i doppioni più comuni lasciati dal modello, senza perdere informazioni.

    - un figlio con lo stesso titolo del genitore viene sciolto nel genitore
    - un unico figlio generico ("Definizione") passa la sua spiegazione al genitore
    - una spiegazione identica a quella del genitore viene tolta dal figlio
    """
    for c in node["children"]:
        tidy(c)
    same = [c for c in node["children"] if _norm(c["title"]) == _norm(node["title"])]
    if same:
        rest = [c for c in node["children"] if c not in same]
        lifted = [k for c in same for k in c["children"]]
        for c in same:
            node["summary"] = node.get("summary") or c.get("summary", "")
        merged: list[dict] = []
        merge_into(merged, rest + lifted)
        node["children"] = merged
    if len(node["children"]) == 1:
        only = node["children"][0]
        if not only["children"] and not node.get("summary") and _norm(only["title"]) in _GENERIC_CHILD:
            node["summary"] = only.get("summary", "")
            node["children"] = []
    for c in node["children"]:
        if c.get("summary") and c["summary"] == node.get("summary"):
            c["summary"] = ""


# ---------- LLM ----------

def summarize_chunk(client, chunk: Chunk, depth: int, explain: bool = False, retries: int = 1) -> dict | None:
    header = f"Section: {chunk.section}\n" if chunk.section else ""
    user = f"{header}Pages {chunk.pages[0]}-{chunk.pages[1]}\n\nPASSAGE:\n{chunk.text}"
    for _ in range(retries):
        try:
            tree = clean_node(client.chat_json(system_prompt(explain), user, build_schema(depth, explain)))
            if tree:
                return tree
        except Exception:  # JSON malformato, timeout, ecc.: riprova
            continue
    return None


# ---------- riordino dei capitoli ----------

MAX_FLAT = 8  # oltre questo numero di figli il nodo viene raggruppato in capitoli


def _min_page(n: dict) -> int | None:
    pages = [n["page"]] if n.get("page") else []
    pages += [p for c in n["children"] if (p := _min_page(c))]
    return min(pages) if pages else None


def _validate_groups(data: dict, n: int) -> list[dict] | None:
    """Trasforma i punti di inizio indicati dal modello in capitoli di nodi consecutivi."""
    starts: dict[int, tuple[str, str]] = {}
    for ch in data.get("chapters") or []:
        start, title = ch.get("start"), str(ch.get("title", "")).strip()
        if isinstance(start, int) and 0 <= start < n and title and start not in starts:
            starts[start] = (title[:120], str(ch.get("summary") or "").strip()[:400])
    if len(starts) < 2:
        return None
    order = sorted(starts)
    if order[0] != 0:  # il primo capitolo parte sempre dall'inizio della lista
        starts[0] = starts.pop(order[0])
        order[0] = 0
    out = []
    for k, start in enumerate(order):
        end = order[k + 1] if k + 1 < len(order) else n
        out.append({"title": starts[start][0], "summary": starts[start][1], "idx": list(range(start, end))})
    return out


def _shift_boundaries(chapters: list[dict], kids: list[dict]) -> None:
    """Sposta nel capitolo successivo il nodo finale che per pagina gli appartiene."""
    for i in range(len(chapters) - 1):
        cur, nxt = chapters[i]["idx"], chapters[i + 1]["idx"]
        while len(cur) > 2:
            last, prev, first_next = (_min_page(kids[cur[-1]]), _min_page(kids[cur[-2]]),
                                      _min_page(kids[nxt[0]]))
            if last and prev and first_next and last > prev and last >= first_next:
                nxt.insert(0, cur.pop())
            else:
                break


def group_children(client, node: dict, explain: bool = False, retries: int = 1) -> bool:
    """Divide i figli di un nodo troppo largo in capitoli consecutivi (in ordine di pagina)."""
    if len(node["children"]) <= MAX_FLAT:
        return False
    kids = sorted(node["children"], key=lambda k: _min_page(k) or 10**6)  # ordine stabile per pagina
    lines = []
    for i, k in enumerate(kids):
        page = _min_page(k)
        hint = f" - {k['summary'][:80]}" if k.get("summary") else ""
        lines.append(f"{i}. {k['title']}" + (f" (p. {page})" if page else "") + hint)
    user = f"Topics of \"{node['title']}\":\n" + "\n".join(lines)
    chapters = None
    for _ in range(retries):
        try:
            chapters = _validate_groups(client.chat_json(group_prompt(explain), user, group_schema(explain)), len(kids))
        except Exception:
            chapters = None
        if chapters:
            break
    if not chapters:
        return False  # in caso di problemi si tiene la struttura originale
    _shift_boundaries(chapters, kids)
    new_children: list[dict] = []
    for ch in chapters:
        members = [kids[i] for i in ch["idx"]]
        if len(members) == 1:
            new_children.append(members[0])
            continue
        merged: list[dict] = []
        merge_into(merged, members)  # accorpa i doppioni dentro lo stesso capitolo
        new_children.append({"title": ch["title"], "page": _min_page({"page": None, "children": merged}),
                             "summary": ch["summary"], "children": merged})
    node["children"] = new_children
    return True


def consolidate_tree(client, root: dict, explain: bool = False) -> None:
    group_children(client, root, explain)
    for branch in list(root["children"]):
        group_children(client, branch, explain)


def build_map(path: str, client, depth: int = 3, max_chars: int = 8000,
              on_progress: Progress | None = None, explain: bool = True, consolidate: bool = True) -> dict:
    pages, toc, meta_title = read_pdf(path)
    chunks = make_chunks(pages, toc, max_chars)
    if not chunks:
        raise ValueError(
            "Nessun testo estraibile: il PDF sembra una scansione. "
            "Esegui prima un OCR (es. `ocrmypdf input.pdf output.pdf`)."
        )
    root: dict = {"title": meta_title or Path(path).stem, "page": None, "summary": "", "children": []}
    sections: dict[str, dict] = {}
    done = 0
    for i, ch in enumerate(chunks, start=1):
        if on_progress:
            on_progress(i - 1, len(chunks), f"Analizzo pagine {ch.pages[0]}-{ch.pages[1]}")
        tree = summarize_chunk(client, ch, depth, explain)
        if tree is None:
            continue
        done += 1
        fill_pages(tree, ch.pages[0])
        if ch.section:
            branch = sections.get(ch.section)
            if branch is None:
                branch = {"title": ch.section, "page": ch.pages[0], "summary": "", "children": []}
                sections[ch.section] = branch
                root["children"].append(branch)
            merge_into(branch["children"], tree["children"] or [tree])
        else:
            tree["page"] = tree["page"] or ch.pages[0]
            merge_into(root["children"], [tree])
    if not done:
        raise RuntimeError("Il modello non ha restituito risultati validi. Prova un modello più grande.")
    tidy(root)
    if consolidate:
        if on_progress:
            on_progress(len(chunks), len(chunks), "Riordino i capitoli")
        consolidate_tree(client, root, explain)
        tidy(root)
    if on_progress:
        on_progress(len(chunks), len(chunks), "Fatto")
    return root
