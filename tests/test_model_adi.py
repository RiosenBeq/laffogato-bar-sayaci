"""Ekranda görünen model adı: dosya adı değil, marka + kademe.

Neden test: dosya adları (indirme betiği, .env, ayarlar.py) teknik gerçek
olarak DEĞİŞMEDEN kalır; kullanıcı yalnızca "NextGen AI Hızlı / İsabetli"
görür. Bu eşlemenin tek kaynağı ayarlar.gorunen_model_adi'dir — şablonda
elle yazılmış bir ad kalırsa sürüm yükseltmesinde sessizce yanlışa döner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ayarlar import gorunen_model_adi


@pytest.mark.parametrize(
    ("dosya", "beklenen"),
    [
        ("yolox_tiny.onnx", "NextGen AI Hızlı"),
        ("yolox_s.onnx", "NextGen AI İsabetli"),
        # Klasörlü yol da aynı adı vermeli — ayarlar tam yol tutar
        ("models/yolox_s.onnx", "NextGen AI İsabetli"),
        ("/bir/yer/models/yolox_tiny.onnx", "NextGen AI Hızlı"),
        # Windows yazımı
        ("models\\yolox_s.onnx", "NextGen AI İsabetli"),
    ],
)
def test_bilinen_kademeler(dosya, beklenen):
    assert gorunen_model_adi(dosya) == beklenen


@pytest.mark.parametrize(
    "dosya",
    ["models/kendi_modelim.onnx", "bardak_v3.onnx", "", "models/yok.onnx"],
)
def test_taninmayan_dosya_ozel_model_sayilir(dosya):
    assert gorunen_model_adi(dosya) == "NextGen AI (özel model)"


def test_path_nesnesi_de_kabul_edilir():
    """Rota, Ayarlar.model_dosyasi (Path) değerini geçiriyor."""
    assert gorunen_model_adi(str(Path("models") / "yolox_s.onnx")) == "NextGen AI İsabetli"


def test_ayarlarin_sectigi_dosyalar_eslemede_var():
    """_varsayilan_model'in döndürebileceği HER dosya adının markalı karşılığı
    olmalı; biri eklenip eşleme unutulursa ekranda "özel model" yazardı."""
    from app import ayarlar as ayarlar_modulu

    kaynak = Path(ayarlar_modulu.__file__).read_text(encoding="utf-8")
    import re

    dosyalar = set(re.findall(r'"models/([\w.-]+\.onnx)"', kaynak))
    assert dosyalar, "ayarlar.py içinde varsayılan model dosyası bulunamadı"
    for ad in dosyalar:
        assert ad in ayarlar_modulu.GORUNEN_MODEL_ADLARI, f"{ad} için görünen ad tanımlı değil"
