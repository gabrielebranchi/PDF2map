# pdf2map

Turn a PDF into an interactive **concept map**, entirely on your own computer with [Ollama](https://ollama.com). No account, no cloud, no data leaves your machine.

*Italiano: [README.it.md](README.it.md)*

For each PDF it creates:

- `name.html`: an interactive map that works offline (open/close branches, zoom, pan; export to SVG, PNG or print to PDF)
- `name.md`: a Markdown outline (works in markmap, Obsidian, XMind...)
- `name.json`: the raw tree, for use in other tools

Every node shows the **PDF page** it comes from (`p.N`) and has a one-sentence **explanation**. Click a node to read it in a side panel, and use **"Open the PDF at page N"** to jump to the source.

## Install

```bash
# 1. Ollama and a model (example: a 7-8B model fits in 8 GB of VRAM)
ollama pull qwen2.5:7b

# 2. pdf2map
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                 # command line only
pip install -e ".[ui]"           # plus the web interface (Streamlit)
```

## Use

```bash
pdf2map examples/ciclo-dell-acqua.pdf                  # writes .html, .md, .json next to the PDF
pdf2map paper.pdf -m llama3.1:8b -d 4 -o results/       # other model, 4 levels, other folder
streamlit run app.py                                    # web interface with file upload
```

| Option | Meaning |
| --- | --- |
| `-m`, `--model` | Ollama model (default `qwen2.5:7b`) |
| `-d`, `--depth` | levels below the root, 1-5 (default 3) |
| `--max-chars` | characters of text sent to the model per call; lower it for small models |
| `--num-ctx` | context window of the model (default 8192) |
| `--no-explain` | skip the node explanations (much faster) |
| `--no-consolidate` | skip the final grouping into chapters |
| `--temperature`, `--seed` | default `0` and `42`: the same PDF gives (almost always) the same map |
| `--host` | Ollama on another machine |

## How it works

1. **Extraction**: PyMuPDF reads the text page by page and uses the PDF bookmarks, when present, to find chapters.
2. **Chunks**: text is split by chapter and size, with `[p.N]` page markers.
3. **LLM**: each chunk goes to Ollama with a JSON schema, so the answer is always a valid tree.
4. **Merge**: branches from different chunks are merged and duplicated concepts are folded together.
5. **Grouping**: when a node has too many children (more than 8), pages are sorted and the model only decides where chapters start. Content is never rewritten, only moved, so nothing gets lost. If the call fails, the original structure is kept.
6. **Cleanup**: common duplicates are removed (a node with the same title as its parent, a lone "Definizione" child) and a trailing node that belongs to the next chapter by page is moved.
7. **Export**: HTML, Markdown, JSON.

## Models and speed

Tested on a laptop with an 8 GB GPU:

- `qwen2.5:7b` gives the best results of the models tried, including in Italian. A 21-page slide deck took about a minute at depth 2 with explanations.
- `llama3.1:8b` fits on the GPU but tended to switch to English and to repeat the same explanation on sibling nodes.
- `gemma2:9b` does not fit in 8 GB: part of it runs on the CPU and everything slows down. Check with `ollama ps` that the `PROCESSOR` column says `100% GPU`.

## Known limits

- **Scanned PDFs** have no text: run `ocrmypdf input.pdf output.pdf` first.
- **Tables lose their columns** in text extraction, so the model can swap values. Always check tables and formulas against the original.
- Small models can invent details or phrase things oddly. The map is a study aid, not a replacement for the source.
- If the "Open the PDF at page N" link always opens the last page you viewed, a browser PDF extension (for example Acrobat) is probably ignoring `#page=`. Disable it or try a private window.
- In the Streamlit app the link uses the `static/` folder (enabled in `.streamlit/config.toml`).

## Development

```bash
pip install -e ".[dev]" && pytest
```

The tests use a fake LLM, so Ollama is not needed.

## Ideas

- Concept maps with labelled relations (concept, relation, concept)
- Reading slide images with a vision model to recover tables and diagrams
- Manual editing and saving of the map
- Chat with the document

Contributions are welcome. License: MIT.
