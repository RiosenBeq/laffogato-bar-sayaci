#!/bin/bash
# Laffogato - Mac baslatici. Bu dosyaya cift tiklayin.
cd "$(dirname "$0")"

PY=""
for aday in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
  if command -v "$aday" >/dev/null 2>&1 && \
     "$aday" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
    PY="$aday"; break
  fi
done

if [ -z "$PY" ]; then
  echo ""
  echo "  Python 3.10+ bulunamadi."
  echo "  https://www.python.org/downloads/ adresinden Python 3.12 kurun."
  echo ""
  read -p "  Kapatmak icin Enter..."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "▶ Ilk kurulum yapiliyor (birkac dakika surebilir)..."
  "$PY" -m venv .venv || exit 1
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt || exit 1
  echo "✓ Kurulum tamam"
fi

[ -f .env ] || cp .env.example .env

echo "▶ Laffogato baslatiliyor → http://127.0.0.1:8100"
echo "  (Ilk acilista macOS kamera izni sorabilir: 'Izin Ver' deyin.)"
( sleep 3; open "http://127.0.0.1:8100" ) &
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
