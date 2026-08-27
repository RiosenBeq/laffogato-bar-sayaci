"""Bardak eğitimi testleri.

Asıl mesele modelin gücü değil, ÖLÇÜMÜN DÜRÜSTLÜĞÜ: yetersiz ya da
kopya veriyle sistem sayı uydurmamalı, eğitimi hiç çalıştırmamalı.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app import egitim as egitim_modulu
from app import veritabani, zaman
from app.egitim import EN_AZ_BARDAK, EN_AZ_DEGIL, egit

KUTU = "[0.2, 0.2, 0.8, 0.8]"


@pytest.fixture
def baglanti(ayarlar):
    b = veritabani.baglanti_ac(ayarlar.veritabani)
    veritabani.semayi_uygula(b)
    yield b
    b.close()


def _kirpik_yaz(ayarlar, ad: str, renk, tohum: int, kopya: bool = False) -> str:
    """Sınıfa özgü RENKLİ ama her biri birbirinden farklı kırpık üretir.

    Sınıf işareti renktedir (model bunu öğrenir); arka plan, nesnenin yeri ve
    boyu örnekten örneğe değişir — böylece kırpıklar birbirinin kopyası olmaz
    ve yakın-kopya denetimi boşuna tetiklenmez.

    kopya=True: bilerek birbirinin aynısı kırpıklar (kopya denetimi testi için).
    """
    rng = np.random.default_rng(tohum)
    if kopya:
        kirpik = np.zeros((60, 50, 3), dtype=np.uint8)
        kirpik[10:50, 8:42] = np.array(renk, dtype=np.uint8)
    else:
        zemin = int(rng.integers(15, 120))
        kirpik = np.clip(zemin + rng.integers(-12, 12, (60, 50, 3)), 0, 255).astype(np.uint8)
        y0, x0 = int(rng.integers(4, 16)), int(rng.integers(3, 14))
        y1, x1 = y0 + int(rng.integers(28, 42)), x0 + int(rng.integers(24, 34))
        y1, x1 = min(y1, 60), min(x1, 50)
        kirpik[y0:y1, x0:x1] = np.clip(
            np.array(renk, dtype=np.int16) + rng.integers(-20, 20, 3), 0, 255
        ).astype(np.uint8)
    yol = ayarlar.egitim_klasoru / ad
    cv2.imwrite(str(yol), kirpik)
    return ad


def _ornek_ekle(baglanti, ayarlar, sayi: int, etiket: str, renk, parti: str, tohum0: int) -> None:
    for i in range(sayi):
        ad = _kirpik_yaz(ayarlar, f"{parti}-{etiket}-{i:03d}.jpg", renk, tohum=tohum0 + i)
        baglanti.execute(
            "INSERT INTO bardak_ornekleri "
            "(dosya, parti, kaynak, kutu, coco_bardak, etiket, eklendi, etiketlendi) "
            "VALUES (?, ?, 'yukleme', ?, 1, ?, ?, ?)",
            (ad, parti, KUTU, etiket, zaman.simdi_utc(), zaman.simdi_utc()),
        )
    baglanti.commit()


def _iki_partili_veri(baglanti, ayarlar, tohum=0):
    """İki ayrı yükleme; her partide hem bardak hem 'değil' örnekleri."""
    for sira, parti in enumerate(("p001", "p002")):
        _ornek_ekle(baglanti, ayarlar, 22, "bardak", (30, 140, 230), parti, tohum + sira * 100)
        _ornek_ekle(baglanti, ayarlar, 22, "degil", (200, 90, 60), parti, tohum + 50 + sira * 100)


def test_veri_yoksa_egitim_reddedilir(baglanti, ayarlar):
    sonuc = egit(baglanti, ayarlar)
    assert sonuc.hata is not None
    assert str(EN_AZ_BARDAK) in sonuc.hata
    assert sonuc.devreye_alindi is False
    assert not (ayarlar.bardak_model_klasoru / "aktif.json").exists()


def test_tek_yukleme_ile_egitim_reddedilir(baglanti, ayarlar):
    """Tek partiyi ikiye bölmek ölçümü yalan yapar; sistem buna izin vermez."""
    _ornek_ekle(baglanti, ayarlar, EN_AZ_BARDAK + 5, "bardak", (30, 140, 230), "p001", 0)
    _ornek_ekle(baglanti, ayarlar, EN_AZ_DEGIL + 5, "degil", (200, 90, 60), "p001", 500)
    sonuc = egit(baglanti, ayarlar)
    assert sonuc.hata is not None
    assert "AYRI yükleme" in sonuc.hata
    assert sonuc.devreye_alindi is False


def test_yakin_kopya_verisi_olcumu_gecersiz_kilar(baglanti, ayarlar):
    """Aynı görüntünün tekrarıyla eğitim %100 isabet üretirdi — bu bir yalandır.

    (Depodaki veri/goruntuler klasörü tam olarak böyle: 176 kırpığın medyan
    piksel farkı 0.0, yani birebir aynı kareler.)
    """
    for parti in ("p001", "p002"):
        for etiket, renk in (("bardak", (30, 140, 230)), ("degil", (200, 90, 60))):
            for i in range(22):
                # kopya=True → bütün kırpıklar birbirinin aynısı
                ad = _kirpik_yaz(ayarlar, f"{parti}-{etiket}-{i:03d}.jpg", renk, 1, kopya=True)
                baglanti.execute(
                    "INSERT INTO bardak_ornekleri "
                    "(dosya, parti, kaynak, kutu, coco_bardak, etiket, eklendi, etiketlendi) "
                    "VALUES (?, ?, 'yukleme', ?, 1, ?, ?, ?)",
                    (ad, parti, KUTU, etiket, zaman.simdi_utc(), zaman.simdi_utc()),
                )
    baglanti.commit()
    sonuc = egit(baglanti, ayarlar)
    assert sonuc.hata is not None
    assert "AYNI görüntü" in sonuc.hata
    assert sonuc.devreye_alindi is False


def test_tek_sinifli_test_kumesi_reddedilir(baglanti, ayarlar):
    """Son yüklemede yalnız bardak varsa isabet ölçmek anlamsızdır."""
    _ornek_ekle(baglanti, ayarlar, 30, "bardak", (30, 140, 230), "p001", 0)
    _ornek_ekle(baglanti, ayarlar, 30, "degil", (200, 90, 60), "p001", 300)
    _ornek_ekle(baglanti, ayarlar, 20, "bardak", (30, 140, 230), "p002", 600)
    sonuc = egit(baglanti, ayarlar)
    assert sonuc.hata is not None
    assert "tek sınıftan" in sonuc.hata


def test_saglikli_veriyle_egitim_calisir_ve_karsilastirir(baglanti, ayarlar):
    _iki_partili_veri(baglanti, ayarlar)
    sonuc = egit(baglanti, ayarlar)

    assert sonuc.hata is None, sonuc.hata
    assert sonuc.surum == "v001"
    assert sonuc.test_sayisi >= 12
    # Eski yöntem (kütüphane boş) hiçbir kırpığa karar veremez: hepsi belirsiz
    assert sonuc.eski.belirsiz == sonuc.test_sayisi
    # Yeni model ayırt edilebilir veride belirsizi düşürmeli
    assert sonuc.yeni.belirsiz < sonuc.eski.belirsiz
    assert sonuc.devreye_alindi is True
    assert sonuc.sebep

    klasor = ayarlar.bardak_model_klasoru
    assert (klasor / "v001.npz").is_file()
    assert (klasor / "v001.json").is_file()
    assert (klasor / "aktif.json").is_file()


def test_devreye_alinan_model_yuklenir_ve_karar_verir(baglanti, ayarlar):
    from app.bardak_modeli import BardakModeli

    _iki_partili_veri(baglanti, ayarlar)
    assert egit(baglanti, ayarlar).devreye_alindi

    model = BardakModeli(ayarlar.bardak_model_klasoru)
    assert model.model_var and model.surum == "v001"

    # Eğitimde HİÇ görülmemiş yeni kırpıklar (aynı üreticiden, yeni tohumlar).
    # Tek örneğe değil, çoğunluğa bakılır: amaç modelin sınıfları ayırt
    # edebildiğini görmek, tek bir kırpıkta kusursuzluk beklemek değil.
    dogru = 0
    for i in range(10):
        ad = _kirpik_yaz(ayarlar, f"yeni-bardak-{i}.jpg", (30, 140, 230), tohum=9000 + i)
        kirpik = cv2.imread(str(ayarlar.egitim_klasoru / ad))
        if model.karar(kirpik)[0] == "bardak":
            dogru += 1
    assert dogru >= 6, f"10 yeni bardak kırpığının yalnızca {dogru} tanesi tanındı"

    # Model klasörü yoksa asla karar verilmez
    yok = BardakModeli(ayarlar.kok / "olmayan")
    assert yok.model_var is False
    assert yok.karar(np.zeros((40, 30, 3), dtype=np.uint8))[0] == "belirsiz"
    assert yok.karar(None)[0] == "belirsiz"


def test_model_devreden_cikarilabilir(baglanti, ayarlar):
    _iki_partili_veri(baglanti, ayarlar)
    assert egit(baglanti, ayarlar).devreye_alindi
    assert egitim_modulu.modeli_devreden_cikar(ayarlar.bardak_model_klasoru) is True
    assert egitim_modulu.aktif_model_bilgisi(ayarlar.bardak_model_klasoru) is None
    # Sürüm dosyası kalır (kayıt), yalnız devreden çıkar
    assert (ayarlar.bardak_model_klasoru / "v001.npz").is_file()
    assert egitim_modulu.modeli_devreden_cikar(ayarlar.bardak_model_klasoru) is False


def test_etiketleme_ve_sayilar(baglanti, ayarlar):
    _kirpik_yaz(ayarlar, "tek.jpg", (30, 140, 230), 1)
    imlec = baglanti.execute(
        "INSERT INTO bardak_ornekleri (dosya, parti, kaynak, kutu, eklendi) "
        "VALUES ('tek.jpg', 'p001', 'yukleme', ?, ?)",
        (KUTU, zaman.simdi_utc()),
    )
    baglanti.commit()
    ornek_id = imlec.lastrowid

    assert len(egitim_modulu.etiketsizleri_getir(baglanti)) == 1
    assert egitim_modulu.etiketle(baglanti, ornek_id, "bardak") is True
    assert egitim_modulu.etiketsizleri_getir(baglanti) == []
    assert egitim_modulu.sayilar(baglanti)["bardak"] == 1

    with pytest.raises(ValueError):
        egitim_modulu.etiketle(baglanti, ornek_id, "olmayan-etiket")
    assert egitim_modulu.etiketle(baglanti, 9999, "bardak") is False
