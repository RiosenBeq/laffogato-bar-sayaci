"""Model açılamadığında ekrana ÇIKAN metin ile GÜNLÜĞE yazılan ayrıntı ayrılır.

Neden test: kullanıcı yazılımcı değildir. Eskiden aynı metin hem ana sayfadaki
uyarı kutusuna hem Eğitim sayfasına basılıyordu ve içinde dosya yolu ile
çalıştırılacak bir terminal komutu vardı. Kullanıcı bunların hiçbirini yapamaz;
teknik destek ise tam yolu görmek zorundadır. İkisi bir daha birleşmesin.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from urllib.parse import unquote

import cv2
import numpy as np
import pytest

from app.tespit import ModelHatasi, Tespitci

# Ekrana ASLA çıkmaması gereken izler: dosya adı/uzantısı, klasör yolu,
# terminal komutu ve kütüphanenin ham istisna metni.
YASAKLI = re.compile(r"yolox|\.onnx|indir\.sh|bash|models/|models\\|Traceback|ONNXRuntime", re.I)


def _ekran_metni(model_yolu: Path) -> str:
    with pytest.raises(ModelHatasi) as bilgi:
        Tespitci(model_yolu)
    return bilgi.value.mesaj


def test_model_yoksa_ekran_metni_markali_ve_sade(tmp_path):
    metin = _ekran_metni(tmp_path / "models" / "yolox_s.onnx")
    assert "NextGen AI İsabetli" in metin
    assert not YASAKLI.search(metin), metin
    # Kullanıcının GERÇEKTEN yapabileceği şey söylenir: uygulamayı yeniden aç
    assert "Başlat" in metin and "çift tık" in metin


def test_taninmayan_model_de_markali_gorunur(tmp_path):
    metin = _ekran_metni(tmp_path / "models" / "kendi_modelim.onnx")
    assert "NextGen AI (özel model)" in metin
    assert not YASAKLI.search(metin), metin


def test_bozuk_model_ekran_metninde_ham_istisna_gecmez(tmp_path):
    bozuk = tmp_path / "models" / "yolox_tiny.onnx"
    bozuk.parent.mkdir(parents=True)
    bozuk.write_bytes(b"bu bir model degil")
    metin = _ekran_metni(bozuk)
    assert "NextGen AI Hızlı" in metin
    assert not YASAKLI.search(metin), metin


def test_teknik_ayrinti_gunluge_yazilir(tmp_path, caplog):
    """Tam yol kaybolmaz — yalnızca ekrandan çıkar, günlükte kalır."""
    yol = tmp_path / "models" / "yolox_s.onnx"
    with caplog.at_level(logging.ERROR, logger="laffogato.tespit"):
        with pytest.raises(ModelHatasi) as bilgi:
            Tespitci(yol)
    assert str(yol) in bilgi.value.teknik
    assert any(str(yol) in kayit.getMessage() for kayit in caplog.records)


def test_egitim_sayfasi_hatayi_markali_gosterir(istemci):
    """Eğitim sayfasındaki yükleme de aynı sade metni gösterir."""
    gorsel = np.zeros((60, 60, 3), dtype=np.uint8)
    tampon = io.BytesIO(cv2.imencode(".jpg", gorsel)[1].tobytes())
    yanit = istemci.post(
        "/egitim/yukle",
        files=[("gorseller", ("deneme.jpg", tampon, "image/jpeg"))],
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    adres = unquote(yanit.headers["location"])
    assert "NextGen AI" in adres
    assert not YASAKLI.search(adres), adres

    sayfa = istemci.get(adres).text
    assert "NextGen AI" in sayfa
