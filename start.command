#!/usr/bin/env bash
# Avvio con doppio clic su macOS; su Linux: bash start.command
cd "$(dirname "$0")" || exit 1
MODEL="qwen2.5:7b"

pause() { read -r -p "Premi Invio per chiudere / Press Enter to close " _; }
open_url() { (command -v open >/dev/null && open "$1") || (command -v xdg-open >/dev/null && xdg-open "$1") || true; }

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null && "$c" -c "import sys; sys.exit(sys.version_info < (3,10))" 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo
  echo "Python 3.10 o piu recente non trovato. / Python 3.10 or newer not found."
  echo "Installalo da https://www.python.org/downloads/"
  open_url https://www.python.org/downloads/
  pause; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Preparo l'ambiente Python, solo la prima volta..."
  "$PY" -m venv .venv || { echo "Non riesco a creare l'ambiente. / Could not create the environment."; pause; exit 1; }
fi
if [ ! -f .venv/.pdf2map-installed ]; then
  echo "Installo i componenti, puo richiedere qualche minuto..."
  .venv/bin/python -m pip install -e ".[ui]" || { echo "Installazione non riuscita, controlla Internet. / Install failed, check your connection."; pause; exit 1; }
  touch .venv/.pdf2map-installed
fi

if ! command -v ollama >/dev/null; then
  echo
  echo "Ollama non e installato. / Ollama is not installed."
  echo "Installalo da https://ollama.com/download e poi riapri questo file."
  open_url https://ollama.com/download
  pause; exit 1
fi
if ! ollama list >/dev/null 2>&1; then
  echo "Avvio Ollama..."
  (ollama serve >/dev/null 2>&1 &)
  sleep 5
fi
if ! ollama list 2>/dev/null | grep -qi "$MODEL"; then
  echo
  echo "Il modello $MODEL non e installato, occupa circa 4,7 GB."
  read -r -p "Vuoi scaricarlo adesso? [s/N] " ans
  case "$ans" in [sSyY]*) ollama pull "$MODEL" ;; esac
fi

mkdir -p static
echo
echo "Avvio di pdf2map. Il browser si apre da solo. Per fermarlo chiudi questa finestra (o premi Ctrl+C)."
exec .venv/bin/python -m streamlit run app.py --browser.gatherUsageStats false
