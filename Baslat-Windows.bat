@echo off
REM Laffogato - Windows baslatici. Bu dosyaya cift tiklayin.
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python bulunamadi. https://www.python.org/downloads/ adresinden
  echo   Python 3.12 kurun ve "Add Python to PATH" kutusunu isaretleyin.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Ilk kurulum yapiliyor, birkac dakika surebilir...
  python -m venv .venv || exit /b 1
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt || exit /b 1
  echo Kurulum tamam.
)

if not exist ".env" copy .env.example .env >nul

echo Laffogato baslatiliyor -^> http://127.0.0.1:8100
start "" http://127.0.0.1:8100
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
