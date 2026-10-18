@echo off
setlocal
cd /d "%~dp0"
title pdf2map
set "MODEL=qwen2.5:7b"

rem ---- Python 3.10 o piu recente ----
set "PY="
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul && set "PY=python"
if not defined PY py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul && set "PY=py -3"
if not defined PY goto :nopython

rem ---- ambiente virtuale e componenti, solo la prima volta ----
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  %PY% -m venv .venv
  if errorlevel 1 goto :venvfail
)
if not exist ".venv\.pdf2map-installed" (
  echo Installo i componenti, puo richiedere qualche minuto...
  ".venv\Scripts\python.exe" -m pip install -e ".[ui]"
  if errorlevel 1 goto :pipfail
  echo ok> ".venv\.pdf2map-installed"
)

rem ---- Ollama ----
where ollama >nul 2>nul
if errorlevel 1 goto :noollama
ollama list >nul 2>nul
if errorlevel 1 (
  echo Avvio Ollama...
  start "" /min ollama serve
  timeout /t 5 /nobreak >nul
)
ollama list 2>nul | findstr /i /c:"%MODEL%" >nul
if not errorlevel 1 goto :launch
if not exist static mkdir static
echo.
echo Il modello %MODEL% non e installato, occupa circa 4,7 GB.
choice /c SN /m "Vuoi scaricarlo adesso"
if errorlevel 2 goto :launch
ollama pull %MODEL%

:launch
echo.
echo Avvio di pdf2map. Il browser si apre da solo.
echo Per fermare il programma chiudi questa finestra.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --browser.gatherUsageStats false
pause
exit /b 0

:nopython
echo.
echo Python 3.10 o piu recente non trovato.
echo Python 3.10 or newer not found.
echo Installalo da https://www.python.org/downloads/ e spunta "Add python.exe to PATH".
start "" https://www.python.org/downloads/
pause
exit /b 1

:venvfail
echo Non riesco a creare l'ambiente Python. / Could not create the Python environment.
pause
exit /b 1

:pipfail
echo Installazione non riuscita, controlla la connessione a Internet. / Install failed, check your internet connection.
pause
exit /b 1

:noollama
echo.
echo Ollama non e installato. / Ollama is not installed.
echo Installalo da https://ollama.com/download e poi riapri questo file.
start "" https://ollama.com/download
pause
exit /b 1
