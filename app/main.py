"""Giriş noktası: uvicorn app.main:app --host 127.0.0.1 --port 8100"""

from __future__ import annotations

import sys

from app.ayarlar import AyarHatasi, yukle
from app.uygulama import uygulama_olustur


def _kur():
    try:
        ayarlar = yukle()
    except AyarHatasi as hata:
        print(f"\n[AYAR HATASI] {hata}\n", file=sys.stderr)
        raise SystemExit(1) from hata
    return uygulama_olustur(ayarlar)


app = _kur()
