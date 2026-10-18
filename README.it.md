# pdf2map

Trasforma un PDF in una **mappa concettuale interattiva**, tutto in locale con [Ollama](https://ollama.com). Nessun account, nessun cloud, nessun dato esce dal tuo computer.

*English: [README.md](README.md)*

Per ogni PDF crea:

- `nome.html`: mappa interattiva che funziona offline (apri/chiudi i rami, zoom, trascinamento; esporta in SVG, PNG o stampa in PDF)
- `nome.md`: elenco Markdown (importabile in markmap, Obsidian, XMind...)
- `nome.json`: albero grezzo, per usarlo in altri programmi

Ogni nodo riporta la **pagina del PDF** da cui proviene (`p.N`) e una **spiegazione** di una frase. Cliccalo per leggerla nel pannello laterale e usa **"Apri il PDF a pagina N"** per andare alla fonte.

## Avvio semplice (senza terminale)

1. Installa [Python 3.10+](https://www.python.org/downloads/) (su Windows spunta "Add python.exe to PATH") e [Ollama](https://ollama.com/download).
2. **Windows**: doppio clic su `start.bat`. **macOS**: doppio clic su `start.command` (se è bloccato, clic destro e Apri; se non parte, apri Terminale e scrivi `bash start.command`). **Linux**: `bash start.command`.
3. La prima volta prepara tutto da solo (qualche minuto) e propone di scaricare il modello. Poi si apre il browser con l'app. Chiudi la finestra per fermarlo.

## Installazione con Powershell

```bash
# 1. Ollama e un modello (esempio: un modello 7-8B sta in 8 GB di VRAM)
ollama pull qwen2.5:7b

# 2. pdf2map
python -m venv .venv
.venv\Scripts\activate
# cambiare cartella con quella con interno i file di PDF2map
pip install -e .                 # solo riga di comando
pip install -e ".[ui]"           # con interfaccia web (Streamlit)
```

## Uso

```bash
pdf2map examples/ciclo-dell-acqua.pdf                  # crea .html, .md, .json accanto al PDF
pdf2map documento.pdf -m llama3.1:8b -d 4 -o risultati/ # altro modello, 4 livelli, altra cartella
streamlit run app.py                                    # interfaccia web con caricamento file
```

| Opzione | Significato |
| --- | --- |
| `-m`, `--model` | modello Ollama (default `qwen2.5:7b`) |
| `-d`, `--depth` | livelli sotto la radice, da 1 a 5 (default 3) |
| `--max-chars` | caratteri di testo inviati al modello per chiamata; abbassalo con modelli piccoli |
| `--num-ctx` | finestra di contesto del modello (default 8192) |
| `--no-explain` | niente spiegazioni dei nodi (molto più veloce) |
| `--no-consolidate` | salta il raggruppamento finale in capitoli |
| `--temperature`, `--seed` | default `0` e `42`: lo stesso PDF dà (quasi sempre) la stessa mappa |
| `--host` | Ollama su un altro computer |

## Come funziona

1. **Estrazione**: PyMuPDF legge il testo pagina per pagina e usa i segnalibri del PDF, se ci sono, per riconoscere i capitoli.
2. **Blocchi**: il testo viene diviso per capitolo e dimensione, con marcatori di pagina `[p.N]`.
3. **LLM**: ogni blocco va a Ollama con un JSON schema, così la risposta è sempre un albero valido.
4. **Fusione**: i rami dei vari blocchi vengono uniti e i concetti duplicati accorpati.
5. **Raggruppamento**: se un nodo ha troppi figli (più di 8), si ordinano per pagina e il modello decide solo dove iniziano i capitoli. I contenuti non vengono riscritti, solo spostati, quindi non si perde niente. Se la chiamata fallisce si tiene la struttura originale.
6. **Pulizia**: si tolgono i doppioni più comuni (un nodo con lo stesso titolo del genitore, "Definizione" come unico figlio) e si sposta il nodo finale che per pagina appartiene al capitolo successivo.
7. **Export**: HTML, Markdown, JSON.

## Modelli e velocità

Provato su un portatile con GPU da 8 GB:

- `qwen2.5:7b` dà i risultati migliori tra quelli provati, anche in italiano. Un set di 21 slide ha richiesto circa un minuto a profondità 2 con le spiegazioni.
- `llama3.1:8b` sta sulla GPU ma tende a passare all'inglese e a ripetere la stessa spiegazione su nodi fratelli.
- `gemma2:9b` non sta in 8 GB: una parte gira sulla CPU e tutto rallenta. Controlla con `ollama ps` che la colonna `PROCESSOR` dica `100% GPU`.

## App per Windows (.exe)

C'è una piccola finestra per chi non vuole usare il terminale: scegli un PDF, scegli il modello, premi **Genera** e la mappa si apre nel browser.

```bash
pdf2map-gui          # dopo pip install -e .
```

Per avere un solo `pdf2map.exe` da avviare con un doppio clic:

- **scaricalo** dalla pagina *Releases* del repository (lo crea GitHub Actions quando si pubblica un tag come `v0.2.0`), oppure
- **crealo tu** su Windows lanciando `build_exe.bat` (serve Python 3.10 o più recente). Il file compare in `dist\pdf2map.exe`.

Note:

- L'app è solo l'interfaccia: **Ollama deve comunque essere installato e in esecuzione**, con un modello già scaricato (`ollama pull qwen2.5:7b`).
- Il file non è firmato, quindi Windows SmartScreen o un antivirus possono avvisare. Scegli *Ulteriori informazioni, Esegui comunque*, oppure crealo tu dal codice sorgente.
- È un file unico che si decomprime all'avvio, quindi si apre in qualche secondo.

## Limiti noti

- I **PDF scansionati** non hanno testo: passali prima da `ocrmypdf input.pdf output.pdf`.
- Le **tabelle perdono le colonne** nell'estrazione del testo, quindi il modello può invertire i valori. Controlla sempre tabelle e formule sul documento originale.
- I modelli piccoli possono inventare dettagli o esprimersi in modo strano. La mappa è un aiuto per studiare, non sostituisce la fonte.
- Se il link "Apri il PDF a pagina N" apre sempre l'ultima pagina vista, di solito è colpa di un'estensione del browser (per esempio Acrobat) che ignora `#page=`. Disattivala o prova in una finestra in incognito.
- Nell'interfaccia Streamlit il link usa la cartella `static/` (abilitata da `.streamlit/config.toml`).

## Sviluppo

```bash
pip install -e ".[dev]" && pytest
```

I test usano un finto LLM, quindi non serve Ollama.

## Idee

- Vere mappe concettuali con relazioni etichettate (concetto, relazione, concetto)
- Lettura delle immagini delle slide con un modello visivo, per recuperare tabelle e diagrammi
- Modifica manuale della mappa e salvataggio
- Chat con il documento

I contributi sono benvenuti. Licenza: MIT.
