"""Nesne kütüphanesi ve tarama testleri."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app import nesne_deposu, veritabani
from app.kutuphane import benzerlik, en_iyi_eslesme, parmakizi_cikar
from app.nesne_deposu import NesneHatasi


def desenli_nesne(ana_renk=(40, 40, 200), tohum: int = 1) -> np.ndarray:
    """Belirli renkte, tekrarlanabilir desenli sahte bir nesne fotoğrafı."""
    rastgele = np.random.default_rng(tohum)
    gorsel = np.full((180, 180, 3), ana_renk, dtype=np.uint8)
    for _ in range(40):  # ORB'nin tutunacağı köşeler
        x, y = rastgele.integers(10, 160, size=2)
        cv2.rectangle(gorsel, (int(x), int(y)), (int(x) + 12, int(y) + 12), (250, 250, 250), -1)
    return gorsel


def test_ayni_nesne_yuksek_benzerlik():
    a = parmakizi_cikar(desenli_nesne(tohum=1))
    b = parmakizi_cikar(desenli_nesne(tohum=1))  # aynı nesne
    assert benzerlik(a, b) > 0.8


def test_farkli_renk_dusuk_benzerlik():
    kirmizi = parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=1))
    yesil = parmakizi_cikar(desenli_nesne((40, 200, 40), tohum=7))
    assert benzerlik(kirmizi, yesil) < 0.45


def test_celiskili_kanit_eslesme_saydirmaz():
    """İki tuzak: (a) aynı renk ama başka desen — beyaz iki ayrı fincan,
    (b) farklı renk ama aynı desen — aynı markanın başka renk ürünü.
    İkisi de varsayılan eşiğin ALTINDA kalmalı."""
    from app.kutuphane import VARSAYILAN_ESIK

    ayni_renk_baska_desen = benzerlik(
        parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=1)),
        parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=5)),
    )
    baska_renk_ayni_desen = benzerlik(
        parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=1)),
        parmakizi_cikar(desenli_nesne((40, 200, 40), tohum=1)),
    )
    assert ayni_renk_baska_desen < VARSAYILAN_ESIK
    assert baska_renk_ayni_desen < VARSAYILAN_ESIK


def test_desensiz_nesne_yalniz_renkle_kolay_eslesemez():
    from app.kutuphane import VARSAYILAN_ESIK

    duz = np.full((180, 180, 3), (40, 40, 200), dtype=np.uint8)
    desenli = desenli_nesne((40, 40, 200), tohum=1)
    assert benzerlik(parmakizi_cikar(duz), parmakizi_cikar(desenli)) < VARSAYILAN_ESIK
    # Ama düz nesne KENDİSİYLE eşleşebilmeli (yoksa hiç tanınamazdı)
    assert benzerlik(parmakizi_cikar(duz), parmakizi_cikar(duz.copy())) >= VARSAYILAN_ESIK


def test_cok_kucuk_gorselden_parmakizi_cikmaz():
    assert parmakizi_cikar(np.zeros((8, 8, 3), dtype=np.uint8)) is None
    assert parmakizi_cikar(None) is None


def test_esik_altinda_eslesme_kabul_edilmez():
    from app.kutuphane import Nesne

    nesne = Nesne(id=1, ad="Fincan", parmakizleri=[parmakizi_cikar(desenli_nesne(tohum=1))])
    # Aynı nesne → eşleşir
    bulunan, skor = en_iyi_eslesme(desenli_nesne(tohum=1), [nesne])
    assert bulunan is not None and skor > 0.5
    # Çok farklı görüntü → isim UYDURULMAZ
    bulunan, _ = en_iyi_eslesme(desenli_nesne((40, 200, 40), tohum=9), [nesne])
    assert bulunan is None
    # Eşik yükseltilirse zayıf eşleşmeler elenir
    bulunan, _ = en_iyi_eslesme(desenli_nesne((45, 45, 195), tohum=3), [nesne], esik=0.95)
    assert bulunan is None


def test_kutuphane_bos_ise_eslesme_yok():
    assert en_iyi_eslesme(desenli_nesne(), []) == (None, 0.0)


# ---- depo (veritabanı + dosya) ----


@pytest.fixture
def depo(ayarlar):
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    veritabani.semayi_uygula(baglanti)
    yield baglanti, ayarlar
    baglanti.close()


def _jpeg(tohum=1) -> bytes:
    return cv2.imencode(".jpg", desenli_nesne(tohum=tohum))[1].tobytes()


def test_nesne_ve_fotograf_ekleme(depo):
    baglanti, ayarlar = depo
    nesne_id = nesne_deposu.nesne_ekle(baglanti, "Laffogato fincanı")
    for tohum in (1, 2, 3):
        nesne_deposu.fotograf_ekle(
            baglanti, ayarlar.nesne_klasoru, nesne_id, f"acı{tohum}.jpg", _jpeg(tohum)
        )
    liste = nesne_deposu.nesneleri_listele(baglanti)
    assert len(liste) == 1
    assert liste[0]["ad"] == "Laffogato fincanı"
    assert len(liste[0]["fotolar"]) == 3
    # Parmak izleri yüklenebiliyor
    nesneler = nesne_deposu.nesneleri_yukle(baglanti, ayarlar.nesne_klasoru)
    assert len(nesneler) == 1 and len(nesneler[0].parmakizleri) == 3


def test_ayni_isimde_iki_nesne_olmaz(depo):
    baglanti, _ = depo
    nesne_deposu.nesne_ekle(baglanti, "Fincan")
    with pytest.raises(NesneHatasi) as hata:
        nesne_deposu.nesne_ekle(baglanti, "Fincan")
    assert "zaten var" in str(hata.value)


def test_bos_ad_reddedilir(depo):
    baglanti, _ = depo
    with pytest.raises(NesneHatasi):
        nesne_deposu.nesne_ekle(baglanti, "   ")


def test_desteklenmeyen_dosya_reddedilir(depo):
    baglanti, ayarlar = depo
    nesne_id = nesne_deposu.nesne_ekle(baglanti, "Fincan")
    with pytest.raises(NesneHatasi) as hata:
        nesne_deposu.fotograf_ekle(
            baglanti, ayarlar.nesne_klasoru, nesne_id, "belge.pdf", b"%PDF-1.4"
        )
    assert "JPG" in str(hata.value)


def test_bozuk_gorsel_reddedilir_ve_diske_kalmaz(depo):
    baglanti, ayarlar = depo
    nesne_id = nesne_deposu.nesne_ekle(baglanti, "Fincan")
    with pytest.raises(NesneHatasi) as hata:
        nesne_deposu.fotograf_ekle(
            baglanti, ayarlar.nesne_klasoru, nesne_id, "bozuk.jpg", b"bu jpeg degil"
        )
    assert "okunamadı" in str(hata.value)
    assert list(ayarlar.nesne_klasoru.glob("*.jpg")) == []  # yarım dosya bırakmadı


def test_nesne_silinince_fotograflari_da_silinir(depo):
    baglanti, ayarlar = depo
    nesne_id = nesne_deposu.nesne_ekle(baglanti, "Fincan")
    ad = nesne_deposu.fotograf_ekle(baglanti, ayarlar.nesne_klasoru, nesne_id, "a.jpg", _jpeg())
    assert (ayarlar.nesne_klasoru / ad).exists()
    nesne_deposu.nesne_sil(baglanti, ayarlar.nesne_klasoru, nesne_id)
    assert not (ayarlar.nesne_klasoru / ad).exists()
    assert nesne_deposu.nesneleri_listele(baglanti) == []


def test_kayip_dosya_kutuphaneyi_bozmaz(depo):
    baglanti, ayarlar = depo
    nesne_id = nesne_deposu.nesne_ekle(baglanti, "Fincan")
    ad = nesne_deposu.fotograf_ekle(baglanti, ayarlar.nesne_klasoru, nesne_id, "a.jpg", _jpeg())
    (ayarlar.nesne_klasoru / ad).unlink()  # dosya elle silindi
    assert nesne_deposu.nesneleri_yukle(baglanti, ayarlar.nesne_klasoru) == []


# ---- tarama (model yokken de anlaşılır davranmalı) ----


def test_tarama_modelsiz_uyari_verir(ayarlar):
    from app.tarama import tara

    sonuc = tara(desenli_nesne(), "kare.jpg", None, [], ayarlar.tarama_klasoru)
    assert sonuc.bulgular == []
    assert "model" in sonuc.uyari.lower()
    assert (ayarlar.tarama_klasoru / sonuc.sonuc_gorseli).exists()


def test_eski_taramalar_temizlenir(ayarlar):
    from app.tarama import eski_taramalari_temizle

    for i in range(8):
        (ayarlar.tarama_klasoru / f"tarama-{i:02d}.jpg").write_bytes(b"x")
    eski_taramalari_temizle(ayarlar.tarama_klasoru, en_fazla=3)
    assert len(list(ayarlar.tarama_klasoru.glob("tarama-*.jpg"))) == 3


def test_desensiz_nesne_kendi_referansiyla_eslesir():
    """Gerçek sahada öğrenilen durum: küçük ve düz beyaz fincanda ORB hiç
    desen bulamaz. İKİ TARAF DA desensizse karar renge kalır; güçlü bir renk
    uyumu eşleşme saydırmalı, orta karar bir uyum saydırmamalıdır."""
    from app.kutuphane import VARSAYILAN_ESIK

    duz = np.full((160, 160, 3), (235, 238, 240), dtype=np.uint8)  # beyaz fincan
    # aynı nesne, hafif ışık farkı
    benzer = np.full((160, 160, 3), (232, 236, 239), dtype=np.uint8)
    farkli = np.full((160, 160, 3), (60, 120, 200), dtype=np.uint8)  # turuncu nesne

    assert benzerlik(parmakizi_cikar(duz), parmakizi_cikar(benzer)) >= VARSAYILAN_ESIK
    assert benzerlik(parmakizi_cikar(duz), parmakizi_cikar(farkli)) < VARSAYILAN_ESIK
