"""Çift sayım koruması testleri — kamerasız, saniyeler içinde.

Senaryo: tezgâhta bekleyen bardak barista önünden geçerken kapanır, takipçi
izi düşürür ve bardak yeniden göründüğünde YENİ takip numarası alır.
Koruma bunu "aynı bardak" diye tanımalı; farklı bardağı ise YUTMAMALI.
"""

from __future__ import annotations

from app.bardak import (
    EN_AZ_GORULME,
    TEKRAR_PENCERESI_SN,
    BardakDurumu,
    TekrarKorumasi,
    renk_benzerligi,
)

BEYAZ = (0.8, 0.1, 0.05, 0.05)
KIRMIZI = (0.05, 0.05, 0.1, 0.8)

MERKEZ = (0.50, 0.50)
BOYUT = (0.10, 0.14)


def test_ayni_yer_ayni_gorunum_tekrar_sayilmaz():
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0)
    # Pencere içinde, aynı yerde ve aynı görünümde yeni iz açılıyor
    assert k.ayni_bardak_mi((0.51, 0.50), (0.10, 0.13), BEYAZ, simdi_s=105.0) is True
    assert k.bastirilan == 1


def test_pencere_dolunca_yeniden_sayilir():
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0)
    gec = 100.0 + TEKRAR_PENCERESI_SN + 1.0
    assert k.ayni_bardak_mi(MERKEZ, BOYUT, BEYAZ, simdi_s=gec) is False
    assert k.bastirilan == 0


def test_uzak_yerdeki_bardak_bastirilmaz():
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0)
    assert k.ayni_bardak_mi((0.85, 0.50), BOYUT, BEYAZ, simdi_s=105.0) is False


def test_farkli_renkli_bardak_bastirilmaz():
    """Aynı yere konan FARKLI bardak yutulmamalı — koruma sayıyı düşürmemeli."""
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0)
    assert k.ayni_bardak_mi(MERKEZ, BOYUT, KIRMIZI, simdi_s=105.0) is False
    assert k.bastirilan == 0


def test_boyu_cok_farkli_bardak_bastirilmaz():
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, (0.10, 0.14), BEYAZ, simdi_s=100.0)
    assert k.ayni_bardak_mi(MERKEZ, (0.30, 0.42), BEYAZ, simdi_s=105.0) is False


def test_renk_imzasi_yoksa_bastirma_yapilmaz():
    """Kanıt eksikken yutmayız: imza çıkarılamadıysa bardak sayılır."""
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, None, simdi_s=100.0)
    assert k.ayni_bardak_mi(MERKEZ, BOYUT, BEYAZ, simdi_s=105.0) is False
    k2 = TekrarKorumasi()
    k2.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0)
    assert k2.ayni_bardak_mi(MERKEZ, BOYUT, None, simdi_s=105.0) is False


def test_bastirilan_bardak_sayima_girmez():
    d = BardakDurumu(takip_id=7, ilk_zaman="t", son_zaman="t")
    for _ in range(EN_AZ_GORULME):
        d.gozlem_ekle("musteri", "t")
    assert d.sayilir_mi() is True
    d.tekrar_mi = True
    assert d.sayilir_mi() is False


def test_bir_hatira_yalnizca_bir_bardagi_bastirir():
    """Zincirleme YASAK — yoksa tezgâh noktası kalıcı 'yutma alanı' olurdu.

    Ölçüldü: hatıra her eşleşmede tazelenirse, aynı noktada 60 sn'de bir
    yapılan 10 gerçek bardaktan yalnızca 1'i sayılıyordu.
    """
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=0.0)
    assert k.ayni_bardak_mi(MERKEZ, BOYUT, BEYAZ, simdi_s=2.0) is True
    # Hatıra tükendi: ikinci bardak artık bastırılmaz
    assert k.ayni_bardak_mi(MERKEZ, BOYUT, BEYAZ, simdi_s=4.0) is False
    assert k.bastirilan == 1


def test_yogun_saatte_gercek_bardaklar_yutulmaz():
    """Kafenin normali: aynı noktada, birbirinin aynısı bardaklar, arka arkaya.

    Koruma bunları 'aynı bardak' sanıp sayımı düşürmemeli — uygulamanın
    asıl işi budur.
    """
    for aralik, adet in ((15.0, 40), (30.0, 60), (60.0, 30)):
        k = TekrarKorumasi()
        sayilan, t = 0, 0.0
        for _ in range(adet):
            if not k.ayni_bardak_mi(MERKEZ, BOYUT, BEYAZ, simdi_s=t):
                sayilan += 1
                k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=t)
            t += aralik
        assert sayilan == adet, (
            f"{aralik:.0f} sn arayla {adet} bardağın {adet - sayilan} tanesi yutuldu"
        )


def test_kisa_ortulmeden_donen_bardak_bastirilir():
    """Korumanın ASIL işi: takipçi hafızası bittikten sonraki kısa boşluk."""
    k = TekrarKorumasi()
    k.hatirla(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0)
    assert k.ayni_bardak_mi(MERKEZ, BOYUT, BEYAZ, simdi_s=100.0 + 3.0) is True


def test_renk_benzerligi_sinirlari():
    assert renk_benzerligi(BEYAZ, BEYAZ) == 1.0
    assert renk_benzerligi(BEYAZ, KIRMIZI) < 0.3
    assert renk_benzerligi(None, BEYAZ) == 0.0
    assert renk_benzerligi((0.5, 0.5), (0.5,)) == 0.0
