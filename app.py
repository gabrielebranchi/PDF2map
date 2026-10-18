"""Interfaccia web locale:  streamlit run app.py"""
import os
import re
from pathlib import Path
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

from pdf2map import OllamaClient, build_map, to_html, to_json, to_markdown

# Cartella servita da Streamlit (vedi .streamlit/config.toml): serve ad aprire il PDF dai nodi
STATIC = Path(__file__).parent / "static"

st.set_page_config(page_title="pdf2map", layout="wide")
st.title("Mappa concettuale da PDF")

with st.sidebar:
    host = st.text_input("Indirizzo Ollama", "http://localhost:11434")
    try:
        models = OllamaClient(host=host).list_models()
    except Exception:
        models = []
    model = st.selectbox("Modello", models) if models else st.text_input("Modello", "qwen2.5:7b")
    depth = st.slider("Livelli di dettaglio", 1, 5, 3)
    max_chars = st.slider("Caratteri per blocco", 3000, 16000, 5000, 500)
    explain = st.checkbox("Spiegazione di ogni nodo (più lento)", value=True)
    consolidate = st.checkbox("Riordina i capitoli alla fine", value=True)
    if not models:
        st.warning("Ollama non risponde: avvialo con `ollama serve`.")

pdf = st.file_uploader("Carica un PDF", type="pdf")
if pdf and st.button("Genera mappa", type="primary"):
    STATIC.mkdir(exist_ok=True)
    name = re.sub(r"[^\w.\- ]", "_", os.path.basename(pdf.name))
    path = STATIC / name
    path.write_bytes(pdf.getvalue())
    client = OllamaClient(model, host)
    bar = st.progress(0.0, text="Avvio…")
    try:
        client.check()
        st.session_state["tree"] = build_map(
            str(path), client, depth, max_chars, explain=explain, consolidate=consolidate,
            on_progress=lambda i, n, msg: bar.progress(i / max(n, 1), text=msg),
        )
        st.session_state["pdf_name"] = name
    except (RuntimeError, ValueError) as e:
        st.error(str(e))
    bar.empty()

tree = st.session_state.get("tree")
if tree:
    name = st.session_state.get("pdf_name")
    # nella pagina il PDF è servito da Streamlit; nel file scaricato si presume accanto all'HTML
    page_html = to_html(tree, f"/app/static/{quote(name)}" if name else None)
    download_html = to_html(tree, quote(name) if name else None)
    components.html(page_html, height=720)
    c1, c2, c3 = st.columns(3)
    c1.download_button("Scarica HTML", download_html, "mappa.html", "text/html")
    c2.download_button("Scarica Markdown", to_markdown(tree), "mappa.md", "text/markdown")
    c3.download_button("Scarica JSON", to_json(tree), "mappa.json", "application/json")
