#!/bin/bash
# Laffogato - Mac baslatici. Bu dosyaya cift tiklayin.
cd "$(dirname "$0")"

# Calistirma izni kaybolmus olabilir (ZIP ile geldiyse ya da Windows/exFAT
# uzerinden kopyalandiysa). Finder o zaman dosyayi hic acmaz; kendi iznimizi
# tazelemek en ucuz cozumdur.
chmod +x "$0" 2>/dev/null

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

# Uygun Python'u sec. Asgari surum 3.11'dir: app/zaman.py "from datetime import
# UTC" kullanir ve bu ad 3.11 ile geldi — 3.10 ve oncesinde uygulama daha
# acilirken ImportError verir.
#
# DIKKAT: /usr/bin/python3 her Mac'te VARDIR ama iki ayri tuzagi vardir:
#   1) Cogu makinede surumu 3.9'dur (Laffogato onunla CALISMAZ),
#   2) Command Line Tools kurulu degilse yalnizca bir yer tutucudur ve
#      calistirilinca "gelistirici araclari gerekiyor" penceresi acar.
# Bu yuzden once gercek Python kurulumlari denenir, /usr/bin/python3 EN SONA
# birakilir ve her aday gercekten 3.11+ mi diye SINANIR.
adaylar=(
  /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11
  /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11
)
# python.org kurulumlari
for framework in /Library/Frameworks/Python.framework/Versions/3.1[123]/bin/python3; do
  [ -x "$framework" ] && adaylar+=("$framework")
done
# PATH'teki python3 ve macOS'un kendi python3'u — en sona
adaylar+=(python3 /usr/bin/python3)

PY=""
for aday in "${adaylar[@]}"; do
  if command -v "$aday" >/dev/null 2>&1 && \
     "$aday" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    PY="$aday"; break
  fi
done

if [ -z "$PY" ]; then
  echo ""
  echo "  Calisan bir Python 3.11 veya ustu bulunamadi."
  echo "  (Mac ile gelen python3 surumu genellikle 3.9'dur; Laffogato onunla calismaz.)"
  echo ""
  echo "  Cozum: https://www.python.org/downloads/ adresinden Python 3.12 kurun."
  echo "  Homebrew kullaniyorsaniz: brew install python@3.12"
  echo ""
  echo "  Kurduktan sonra bu dosyaya tekrar cift tiklayin."
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
