#!/bin/bash
# Tespit modellerini indirir (YOLOX, Apache-2.0). Kullanım: bash models/indir.sh
set -e
cd "$(dirname "$0")"
TABAN="https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0"

# Önce geçici ada indirilir, ancak TAM inince gerçek ada taşınır —
# yarım kalan indirme "model var" sanılıp sistemi bozamasın.
indir() {
  ad="$1"
  boyut="$2"
  if [ -s "$ad" ]; then
    echo "✓ $ad zaten var"
    return 0
  fi
  echo "▶ $ad indiriliyor ($boyut)..."
  if curl -L --fail --progress-bar -o "$ad.indiriliyor" "$TABAN/$ad"; then
    mv "$ad.indiriliyor" "$ad"
  else
    rm -f "$ad.indiriliyor"
    return 1
  fi
}

indir yolox_tiny.onnx "~19 MB"
# yolox_s daha isabetlidir; indirilemezse tiny ile devam edilebilir
indir yolox_s.onnx "~34 MB, daha isabetli model" \
  || echo "! yolox_s indirilemedi — sistem yolox_tiny ile calisir"
echo "✓ tamam"
