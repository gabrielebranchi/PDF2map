"""Interfaccia a riga di comando: pdf2map documento.pdf"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import OllamaClient, build_map, pdf_link, to_html, to_json, to_markdown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pdf2map", description="Crea una mappa concettuale da un PDF, in locale con Ollama.")
    ap.add_argument("pdf", help="file PDF di input")
    ap.add_argument("-o", "--output", help="cartella di output (default: accanto al PDF)")
    ap.add_argument("-m", "--model", default="qwen2.5:7b", help="modello Ollama (default: %(default)s)")
    ap.add_argument("--host", default="http://localhost:11434", help="indirizzo di Ollama")
    ap.add_argument("-d", "--depth", type=int, default=3, choices=range(1, 6), metavar="1-5",
                    help="livelli sotto la radice (default: %(default)s)")
    ap.add_argument("--max-chars", type=int, default=8000, help="caratteri per blocco inviato al modello")
    ap.add_argument("--num-ctx", type=int, default=8192, help="finestra di contesto del modello")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="creatività del modello; 0 = risultati ripetibili (default: %(default)s)")
    ap.add_argument("--seed", type=int, default=42, help="seme casuale (default: %(default)s)")
    ap.add_argument("--no-explain", action="store_true",
                    help="niente spiegazioni dei nodi (più veloce)")
    ap.add_argument("--no-consolidate", action="store_true",
                    help="salta il riordino finale dei capitoli")
    args = ap.parse_args(argv)

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"File non trovato: {pdf}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else pdf.parent
    out.mkdir(parents=True, exist_ok=True)

    client = OllamaClient(args.model, args.host, args.num_ctx, temperature=args.temperature, seed=args.seed)
    try:
        client.check()
        tree = build_map(str(pdf), client, args.depth, args.max_chars, explain=not args.no_explain,
                         consolidate=not args.no_consolidate,
                         on_progress=lambda i, n, msg: print(f"[{i}/{n}] {msg}", file=sys.stderr))
    except (RuntimeError, ValueError) as e:
        print(f"Errore: {e}", file=sys.stderr)
        return 1

    stem = out / pdf.stem
    stem.with_suffix(".html").write_text(to_html(tree, pdf_link(pdf, out)), encoding="utf-8")
    stem.with_suffix(".md").write_text(to_markdown(tree), encoding="utf-8")
    stem.with_suffix(".json").write_text(to_json(tree), encoding="utf-8")
    print(f"Creati: {stem}.html, .md, .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
