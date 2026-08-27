"""Bardak Eğitimi sayfasının web akışı testleri."""

from __future__ import annotations

import cv2
import numpy as np

from app import veritabani, zaman


def _ornek_ekle(ayarlar, etiket=None) -> int:
    kirpik = np.random.default_rng(3).integers(0, 255, (40, 30, 3), dtype=np.uint8)
    cv2.imwrite(str(ayarlar.egitim_klasoru / "w-ornek.jpg"), kirpik)
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        veritabani.semayi_uygula(baglanti)
        imlec = baglanti.execute(
            "INSERT INTO bardak_ornekleri (dosya, parti, kaynak, kutu, etiket, eklendi) "
            "VALUES ('w-ornek.jpg', 'p001', 'yukleme', '[0,0,1,1]', ?, ?)",
            (etiket, zaman.simdi_utc()),
        )
        baglanti.commit()
        return imlec.lastrowid
    finally:
        baglanti.close()


def test_egitim_sayfasi_acilir(istemci, ayarlar):
    yanit = istemci.get("/egitim")
    assert yanit.status_code == 200
    assert "Bardak Eğitimi" in yanit.text or "bardak eğitimi" in yanit.text
    assert "Devredeki model" in yanit.text
    # Model yokken dürüst mesaj
    assert "Yok" in yanit.text


def test_bolge_cizilmemisse_uyarilir(istemci):
    """Ekrandaki 'belirsiz' sayısının sebebi çoğu zaman çizilmemiş bölgedir."""
    metin = istemci.get("/egitim").text
    assert "çizilmemiş" in metin
    assert "bardak eğitimi DÜZELTMEZ" in metin


def test_etiketleme_calisir(istemci, ayarlar):
    ornek_id = _ornek_ekle(ayarlar)
    assert f"ornek-{ornek_id}" in istemci.get("/egitim").text

    yanit = istemci.post(f"/egitim/{ornek_id}/etiket?etiket=bardak")
    assert yanit.status_code == 204
    # Etiketlenen kart listeden düşer
    assert f"ornek-{ornek_id}" not in istemci.get("/egitim").text


def test_gecersiz_etiket_reddedilir(istemci, ayarlar):
    ornek_id = _ornek_ekle(ayarlar)
    assert istemci.post(f"/egitim/{ornek_id}/etiket?etiket=olmayan").status_code == 400


def test_olmayan_ornek_404(istemci, ayarlar):
    _ornek_ekle(ayarlar)
    assert istemci.post("/egitim/99999/etiket?etiket=bardak").status_code == 404


def test_ornek_gorseli_servis_edilir(istemci, ayarlar):
    _ornek_ekle(ayarlar)
    yanit = istemci.get("/egitim-foto/w-ornek.jpg")
    assert yanit.status_code == 200
    assert yanit.headers["content-type"].startswith("image/")


def test_klasor_disina_cikilamaz(istemci):
    """Yol gezinmesi engellenmeli."""
    assert istemci.get("/egitim-foto/..%2F..%2F.env").status_code == 404


def test_dosyasiz_yukleme_anlasilir_hata_verir(istemci):
    yanit = istemci.post("/egitim/yukle", files=[], follow_redirects=False)
    assert yanit.status_code == 303
    assert "Dosya" in yanit.headers["location"]


def test_veri_yokken_egitim_dugmesi_durust_cevap_verir(istemci):
    yanit = istemci.post("/egitim/calistir")
    assert yanit.status_code == 200
    assert "Eğitim çalıştırılamadı" in yanit.text
    # Karşılığı olmayan bir isabet sayısı GÖSTERİLMEMELİ
    assert "İsabet" not in yanit.text


def test_devrede_model_yokken_cikarma_hata_verir(istemci):
    yanit = istemci.post("/egitim/devreden-cikar", follow_redirects=False)
    assert yanit.status_code == 303
    assert "hata" in yanit.headers["location"]
