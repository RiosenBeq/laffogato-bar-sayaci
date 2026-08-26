#!/bin/bash
# Tespit modelini indirir (YOLOX, Apache-2.0). Kullanım: bash models/indir.sh
set -e
cd "$(dirname "$0")"
[ -s yolox_tiny.onnx ] && echo "✓ model zaten var" && exit 0
echo "▶ model indiriliyor..."
curl -L --fail --progress-bar -o yolox_tiny.onnx \
  "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
echo "✓ tamam"
