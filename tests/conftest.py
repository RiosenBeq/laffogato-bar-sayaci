"""Test kurulumu: geçici klasörler, kamera/analiz kapalı."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def ayarlar(tmp_path: Path):
    from app.ayarlar import Ayarlar

    veri = tmp_path / "veri"
    goruntuler = veri / "goruntuler"
    nesneler = veri / "nesneler"
    taramalar = veri / "taramalar"
    for klasor in (goruntuler, nesneler, taramalar):
        klasor.mkdir(parents=True)
    return Ayarlar(
        kok=tmp_path,
        kaynak="0",
        kare_fps=4,
        model_dosyasi=tmp_path / "models" / "yok.onnx",
        cihaz="cpu",
        veritabani=veri / "laffogato.db",
        goruntu_klasoru=goruntuler,
        nesne_klasoru=nesneler,
        tarama_klasoru=taramalar,
    )


@pytest.fixture
def istemci(ayarlar):
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    # analiz_ac=False: kamera açılmaz, testler saniyeler içinde biter
    with TestClient(uygulama_olustur(ayarlar, analiz_ac=False)) as istemci:
        yield istemci
