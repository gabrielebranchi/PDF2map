import pymupdf

from pathlib import Path

from pdf2map import build_map, pdf_link, to_html, to_json, to_markdown
from pdf2map.extract import make_chunks, read_pdf
from pdf2map.llm import build_schema
from pdf2map.pipeline import _shift_boundaries, fill_pages, group_children, merge_into, tidy


def make_pdf(path, with_toc=True):
    doc = pymupdf.open()
    texts = [
        "La fotosintesi converte luce in energia chimica nei cloroplasti. " * 4,
        "La fase luminosa produce ATP e NADPH grazie alla clorofilla. " * 4,
        "Il ciclo di Calvin fissa la CO2 in zuccheri. " * 4,
    ]
    for t in texts:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 750), t, fontsize=11)
    if with_toc:
        doc.set_toc([[1, "Introduzione", 1], [1, "Fase luminosa", 2], [1, "Ciclo di Calvin", 3]])
    doc.save(path)


class FakeClient:
    def __init__(self):
        self.calls = 0

    def chat_json(self, system, user, schema):
        self.calls += 1
        if "chapters" in schema["properties"]:  # richiesta di riordino: qui non dovrebbe servire
            raise AssertionError("riordino non atteso")
        return {"title": "Tema", "children": [
            {"title": "Concetto A", "page": 1, "summary": "Spiega A.", "children": [{"title": "Dettaglio", "page": 1}]},
            {"title": "Concetto B"},
        ]}


def test_chunks_follow_toc(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p)
    pages, toc, _ = read_pdf(str(p))
    chunks = make_chunks(pages, toc, 8000)
    assert [c.section for c in chunks] == ["Introduzione", "Fase luminosa", "Ciclo di Calvin"]
    assert chunks[1].pages == (2, 2)


def test_chunks_split_by_size_without_toc(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, with_toc=False)
    pages, toc, _ = read_pdf(str(p))
    assert len(make_chunks(pages, toc, 300)) >= 3


def test_build_map_and_exports(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p)
    client = FakeClient()
    tree = build_map(str(p), client, depth=2)
    assert client.calls == 3
    assert [b["title"] for b in tree["children"]] == ["Introduzione", "Fase luminosa", "Ciclo di Calvin"]
    assert tree["children"][0]["children"][0]["title"] == "Concetto A"
    assert "- Concetto A (p. 1): Spiega A." in to_markdown(tree)
    assert tree["children"][0]["children"][0]["summary"] == "Spiega A."
    assert "Concetto B" in to_json(tree)
    assert "</script><" not in to_html(tree).split("const DATA")[1].split(";\n")[0]


def test_merge_dedupes_similar_titles():
    a = [{"title": "Cloroplasti", "page": 3, "children": []}]
    b = [{"title": "cloroplasti", "page": 1, "children": [{"title": "Tilacoidi", "page": 1, "children": []}]}]
    merge_into(a, b)
    assert len(a) == 1 and a[0]["page"] == 1 and a[0]["children"][0]["title"] == "Tilacoidi"


def test_schema_depth():
    def depth(node):
        kids = node.get("properties", {}).get("children")
        return 1 + depth(kids["items"]) if kids else 0
    assert depth(build_schema(3)) == 3


def test_schema_summary_only_when_explain():
    def has_summary(node):
        return "summary" in node["properties"]["children"]["items"]["properties"]
    assert has_summary(build_schema(2, explain=True))
    assert not has_summary(build_schema(2))


def _wide_node(n=10):
    return {"title": "Radice", "page": None, "summary": "", "children": [
        {"title": f"Argomento {i}", "page": i + 1, "summary": "", "children": []} for i in range(n)]}


class GroupClient:
    def __init__(self, chapters):
        self.chapters = chapters

    def chat_json(self, system, user, schema):
        return {"chapters": self.chapters}


def test_group_children_cuts_sorted_list_into_chapters():
    node = _wide_node()
    node["children"].reverse()  # il documento va riordinato per pagina prima del taglio
    ok = group_children(GroupClient([
        {"title": "Seconda parte", "start": 5},
        {"title": "Prima parte", "start": 0},
    ]), node)
    assert ok
    assert [c["title"] for c in node["children"]] == ["Prima parte", "Seconda parte"]
    assert [c["page"] for c in node["children"]] == [1, 6]
    flat = [k["title"] for c in node["children"] for k in c["children"]]
    assert flat == [f"Argomento {i}" for i in range(10)]  # nessun nodo perso, ordine di pagina


def test_group_children_forces_first_chapter_to_start_at_zero():
    node = _wide_node()
    group_children(GroupClient([{"title": "A", "start": 2}, {"title": "B", "start": 7}]), node)
    assert len(node["children"][0]["children"]) == 7


def test_group_children_failure_keeps_structure():
    class Broken:
        def chat_json(self, *a):
            raise RuntimeError("giù")
    node = _wide_node()
    assert not group_children(Broken(), node)
    assert len(node["children"]) == 10
    small = _wide_node(5)
    assert not group_children(GroupClient([]), small)  # sotto soglia: nessuna chiamata utile


def test_pdf_link_in_html(tmp_path):
    tree = {"title": "T", "children": []}
    assert '"doc%20x.pdf"' in to_html(tree, "doc%20x.pdf")
    assert "const PDF = null;" in to_html(tree)
    pdf = tmp_path / "doc x.pdf"
    pdf.write_bytes(b"")
    assert pdf_link(pdf, tmp_path) == "doc%20x.pdf"
    assert pdf_link(pdf, tmp_path / "out") == "../doc%20x.pdf"


def test_fill_pages_inherits_from_parent_then_chunk():
    tree = {"title": "R", "page": None, "children": [
        {"title": "A", "page": 5, "children": [{"title": "A1", "page": None, "children": []}]},
        {"title": "B", "page": None, "children": []}]}
    fill_pages(tree, 3)
    assert [tree["page"], tree["children"][0]["children"][0]["page"], tree["children"][1]["page"]] == [5, 5, 5]


def test_fill_pages_uses_default_when_nothing_known():
    tree = {"title": "R", "page": None, "children": [{"title": "A", "page": None, "children": []}]}
    fill_pages(tree, 3)
    assert [tree["page"], tree["children"][0]["page"]] == [3, 3]


def _n(title, page=None, summary="", children=()):
    return {"title": title, "page": page, "summary": summary, "children": list(children)}


def test_tidy_dissolves_same_title_child_and_folds_generic_child():
    tree = _n("R", children=[_n("Generalità", 3, children=[
        _n("Generalità", 3, "Intro.", [_n("Valore Aggiunto", 3)]),
        _n("Valore Aggiunto", 3, children=[_n("Definizione", 3, "Incremento di valore.")]),
        _n("Input", 3)])])
    tidy(tree)
    g = tree["children"][0]
    assert g["summary"] == "Intro."
    assert [c["title"] for c in g["children"]] == ["Valore Aggiunto", "Input"]
    assert g["children"][0]["children"] == []
    assert g["children"][0]["summary"] == "Incremento di valore."


def test_tidy_keeps_generic_child_when_parent_already_has_summary():
    tree = _n("R", children=[_n("X", 1, "Già spiegato.", [_n("Definizione", 1, "Altro testo.")])])
    tidy(tree)
    assert len(tree["children"][0]["children"]) == 1


def test_shift_boundaries_moves_lonely_trailing_node():
    kids = [_n(f"k{i}", p) for i, p in enumerate([11, 12, 12, 14, 14, 15])]
    chapters = [{"idx": [0, 1, 2, 3]}, {"idx": [4, 5]}]
    _shift_boundaries(chapters, kids)
    assert chapters[0]["idx"] == [0, 1, 2] and chapters[1]["idx"] == [3, 4, 5]
    same = [_n(f"k{i}", 3) for i in range(6)]  # tutte sulla stessa pagina: nessuno spostamento
    ch2 = [{"idx": [0, 1, 2]}, {"idx": [3, 4, 5]}]
    _shift_boundaries(ch2, same)
    assert ch2[0]["idx"] == [0, 1, 2]


class _Resp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self.content}}


def test_ollama_client_is_deterministic_and_varies_seed_on_retry(monkeypatch):
    from pdf2map import OllamaClient
    import pdf2map.llm as llm

    sent = []
    answers = iter(["non json", '{"title": "ok", "children": []}'])

    def fake_post(url, json, timeout):
        sent.append(json["options"])
        return _Resp(next(answers))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    assert OllamaClient().chat_json("s", "u", {}) == {"title": "ok", "children": []}
    assert [o["seed"] for o in sent] == [42, 43]
    assert [o["temperature"] for o in sent] == [0.0, 0.3]
