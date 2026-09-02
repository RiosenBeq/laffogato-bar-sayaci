#!/bin/bash
# NextGen AI tespit modellerini indirir. Kullanım: bash models/indir.sh
# Üçüncü taraf ağırlıklar ve lisansları: kök klasördeki LICENSE-THIRD-PARTY.
set -e
cd "$(dirname "$0")"
TABAN="https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0"

# Önce geçici ada indirilir, ancak TAM inince gerçek ada taşınır —
# yarım kalan indirme "model var" sanılıp sistemi bozamasın.
indir() {
  ad="$1"       # diskteki dosya adı — DEĞİŞMEZ, sistem tam bu adı arar
  gorunen="$2"  # kullanıcıya gösterilen ad
  boyut="$3"
  if [ -s "$ad" ]; then
    echo "✓ $gorunen zaten kurulu"
    return 0
  fi
  echo "▶ $gorunen indiriliyor ($boyut)..."
  if curl -L --fail --progress-bar -o "$ad.indiriliyor" "$TABAN/$ad"; then
    mv "$ad.indiriliyor" "$ad"
  else
    rm -f "$ad.indiriliyor"
    return 1
  fi
}

indir yolox_tiny.onnx "NextGen AI Hızlı" "~19 MB"
# İsabetli kademe daha az kaçırır; inmezse Hızlı ile devam edilebilir
indir yolox_s.onnx "NextGen AI İsabetli" "~34 MB, daha az kaçırır" \
  || echo "! NextGen AI İsabetli indirilemedi — sistem NextGen AI Hızlı ile çalışır"
echo "✓ NextGen AI kurulumu tamam"
