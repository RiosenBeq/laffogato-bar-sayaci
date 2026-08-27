#!/bin/bash
# Laffogato - Mac baslatici. Bu dosyaya cift tiklayin.
cd "$(dirname "$0")"

PORT=8100
ADRES="http://127.0.0.1:$PORT"

bekle_ve_cik() {
  echo ""
  read -p "  Kapatmak icin Enter tusuna basin..."
  exit 1
}

# Zaten calisiyorsa yeniden kurmaya calisma; dogrudan pencereyi ac.
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "✓ Laffogato zaten calisiyor → pencere aciliyor"
  if [ -x .venv/bin/python ]; then
    exec .venv/bin/python masaustu.py
  fi
  open "$ADRES"
  exit 0
fi

# Uygun Python'u sec (3.10+)
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
  bekle_ve_cik
fi

# Kurulum ancak SONUNA KADAR bittiyse tamam sayilir. Isaret dosyasi yoksa
# pip eksikleri tamamlar (kurulu paketleri atladigi icin cogu zaman hizlidir).
TAMAM=".venv/kurulum-tamamlandi-v2"
if [ ! -f "$TAMAM" ]; then
  if [ ! -x .venv/bin/python ]; then
    rm -rf .venv
    echo ""
    echo "▶ Ilk kurulum basliyor. Internet hizina gore 2-10 dakika surer."
    echo "  Asagida indirme ilerlemesi gorunecek — pencereyi KAPATMAYIN."
    echo ""
    "$PY" -m venv .venv || { echo "✗ Python ortami olusturulamadi."; bekle_ve_cik; }
  else
    echo "▶ Kurulum denetleniyor, eksik paketler tamamlaniyor..."
  fi
  .venv/bin/python -m pip install --upgrade pip \
    || { echo "✗ pip guncellenemedi. Internet baglantinizi kontrol edin."; bekle_ve_cik; }
  if ! .venv/bin/python -m pip install -r requirements.txt; then
    echo "▶ Kurulum bozuk gorunuyor; temizlenip bastan deneniyor..."
    rm -rf .venv
    "$PY" -m venv .venv || { echo "✗ Python ortami olusturulamadi."; bekle_ve_cik; }
    .venv/bin/python -m pip install --upgrade pip || { echo "✗ pip guncellenemedi."; bekle_ve_cik; }
    .venv/bin/python -m pip install -r requirements.txt \
      || { echo "✗ Paket kurulumu tamamlanamadi. Internet baglantinizi kontrol edip tekrar deneyin."; bekle_ve_cik; }
  fi
  touch "$TAMAM"
  echo "✓ Kurulum tamam."
fi

[ -f .env ] || cp .env.example .env

echo ""
echo "▶ Laffogato baslatiliyor — uygulama kendi penceresinde acilacak."
echo "  (Ilk acilista macOS kamera izni sorabilir: 'Izin Ver' deyin.)"
echo "  Kapatmak icin uygulama penceresini kapatmaniz yeterli."
.venv/bin/python masaustu.py
DURUM=$?
if [ $DURUM -ne 0 ]; then
  echo ""
  echo "✗ Uygulama beklenmedik sekilde durdu (kod: $DURUM)."
  echo "  Yukaridaki son satirlari kopyalayip yapay zekaya yapistirirsaniz sorunu bulur."
  bekle_ve_cik
fi
