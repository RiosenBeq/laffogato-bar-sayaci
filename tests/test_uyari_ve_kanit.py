"""Uyarı akışı, kanıt fotoğrafı ve hassasiyet değişimi.

Bardak sayacında "sayı doğru mu" kadar önemli ikinci soru: kullanıcı sayımı
DUYUYOR mu ve gördüğü kanıt doğru anı mı gösteriyor?
"""

from __future__ import annotations

import numpy as np

from app import veritabani, zaman
from app.analiz import Analiz
from app.bardak import BARISTA, MUSTERI, BardakDurumu

_T = "2026-09-02T10:00:00+00:00"


def _kare(genislik=320, yukseklik=240):
    rng = np.random.default_rng(5)
    return rng.integers(0, 255, (yukseklik, genislik, 3), dtype=np.uint8)


def _analiz(ayarlar) -> Analiz:
    analiz = Analiz(ayarlar)
    analiz._kare_boyutu = (320, 240)
    return analiz


# ---- olay akışı ----


def test_sayilan_bardak_olay_uretir(ayarlar):
    analiz = _analiz(ayarlar)
    durum = BardakDurumu(takip_id=3, ilk_zaman=zaman.simdi_utc(), son_zaman=zaman.simdi_utc())
    for _ in range(6):
        durum.gozlem_ekle(MUSTERI, zaman.simdi_utc())
    analiz._olay_uret(durum)

    olaylar = analiz.olaylar()
    assert len(olaylar) == 1
    assert olaylar[0]["kime"] == MUSTERI
    assert olaylar[0]["id"] == 1
    assert analiz.son_olay_id == 1


def test_ayni_anda_iki_bardak_iki_ayri_olay(ayarlar):
    """ESKİ HATA: ekran sayaç farkına bakıyordu; aynı iki saniyelik pencerede
    kapanan iki bardak TEK uyarı oluyordu."""
    analiz = _analiz(ayarlar)
    for takip_id, kime in ((1, MUSTERI), (2, BARISTA)):
        durum = BardakDurumu(takip_id=takip_id, ilk_zaman=_T, son_zaman=_T)
        for _ in range(6):
            durum.gozlem_ekle(kime, _T)
        analiz._olay_uret(durum)

    olaylar = analiz.olaylar()
    assert [o["kime"] for o in olaylar] == [MUSTERI, BARISTA]


def test_gorulen_olaylar_tekrar_gonderilmez(ayarlar):
    """Ekran son gördüğü numarayı gönderir; aynı olay iki kez duyurulmamalı."""
    analiz = _analiz(ayarlar)
    for takip_id in (1, 2, 3):
        durum = BardakDurumu(takip_id=takip_id, ilk_zaman=_T, son_zaman=_T)
        for _ in range(6):
            durum.gozlem_ekle(MUSTERI, _T)
        analiz._olay_uret(durum)

    assert len(analiz.olaylar(sonra=0)) == 3
    assert len(analiz.olaylar(sonra=2)) == 1
    assert analiz.olaylar(sonra=3) == []


def test_canli_ucu_olaylari_dondurur(istemci):
    veri = istemci.get("/canli").json()
    assert "olaylar" in veri
    assert "son_olay_id" in veri
    assert "son_hata" in veri


# ---- kanıt fotoğrafı ----


def test_sayilmayan_bardak_diske_dosya_birakmaz(ayarlar):
    """ESKİ HATA: her yeni iz için hemen dosya yazılıyordu — birkaç karelik
    yanlış tespitler dahil. Hiçbiri temizlenmediği için disk sessizce doluyordu."""
    analiz = _analiz(ayarlar)
    veri = analiz._kirpik_kodla(_kare(), (50.0, 50.0, 120.0, 160.0))
    assert veri is not None and veri[:2] == b"\xff\xd8", "JPEG üretilmeli"
    # Kodlama diske DOKUNMAMALI
    assert list(ayarlar.goruntu_klasoru.glob("*.jpg")) == []


def test_sayilan_bardagin_fotografi_yazilir(ayarlar):
    analiz = _analiz(ayarlar)
    veri = analiz._kirpik_kodla(_kare(), (50.0, 50.0, 120.0, 160.0))
    ad = analiz._kirpigi_yaz(veri)
    assert ad is not None
    dosya = ayarlar.goruntu_klasoru / ad
    assert dosya.is_file() and dosya.read_bytes()[:2] == b"\xff\xd8"


def test_bos_kirpik_dosya_yazmaz(ayarlar):
    assert _analiz(ayarlar)._kirpigi_yaz(None) is None


def test_kare_disindaki_kutu_kirpilmaz(ayarlar):
    """Kare dışına düşen kutu (takipçinin tahmini kaymış olabilir) çökmemeli."""
    assert _analiz(ayarlar)._kirpik_kodla(_kare(), (400.0, 400.0, 402.0, 402.0)) is None


# ---- kayıt: aynı bardak ikinci kez kapanırsa GÜNCELLENİR ----


def test_ikinci_kapanis_karari_gunceller(ayarlar):
    """ESKİ HATA: INSERT OR IGNORE vardı. Bardak örtülüp yeniden göründüğünde
    takipçi aynı numarayı geri verir, kayıt ikinci kez kapanır ve DÜZELTİLMİŞ
    karar (bardak sonunda müşteriye gitti) sessizce çöpe giderdi."""
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        veritabani.semayi_uygula(baglanti)
        analiz = _analiz(ayarlar)

        ilk = BardakDurumu(takip_id=7, ilk_zaman=_T, son_zaman=_T)
        for _ in range(6):
            ilk.gozlem_ekle(BARISTA, _T)
        analiz._bardagi_kaydet(baglanti, ilk)

        satir = baglanti.execute("SELECT * FROM bardaklar").fetchone()
        assert satir["kime"] == BARISTA

        # Aynı takip numarası, bu kez müşteriye giderek kapanıyor
        ikinci = BardakDurumu(takip_id=7, ilk_zaman=_T, son_zaman=_T)
        for _ in range(6):
            ikinci.gozlem_ekle(BARISTA, _T)
        for _ in range(6):
            ikinci.gozlem_ekle(MUSTERI, _T)
        analiz._bardagi_kaydet(baglanti, ikinci)

        satirlar = baglanti.execute("SELECT * FROM bardaklar").fetchall()
        assert len(satirlar) == 1, "aynı bardak ikinci kayıt açmamalı"
        assert satirlar[0]["kime"] == MUSTERI, "düzeltilmiş karar yazılmalı"
    finally:
        baglanti.close()


# ---- hassasiyet değişimi ----


def test_hassasiyet_degisince_acik_kayitlar_bosaltilir(ayarlar):
    """ESKİ HATA: kaydırıcı oynatılınca takipçi yeniden kuruluyor ve numaralar
    1'den başlıyordu; açık kayıtlar durduğu için yeni numaralar BAŞKA
    bardakların gözlemlerinin üstüne biniyor, iki bardağın da kararı ters
    dönüyordu."""
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        veritabani.semayi_uygula(baglanti)
        analiz = _analiz(ayarlar)

        for takip_id, kime in ((1, BARISTA), (2, MUSTERI)):
            durum = BardakDurumu(takip_id=takip_id, ilk_zaman=_T, son_zaman=_T)
            for _ in range(6):
                durum.gozlem_ekle(kime, _T)
            analiz._acik[takip_id] = durum

        analiz._acik_kayitlari_bosalt(baglanti)

        assert analiz._acik == {}, "açık kayıtlar boşaltılmalı"
        assert analiz._kayip == {}
        kararlar = sorted(
            r["kime"] for r in baglanti.execute("SELECT kime FROM bardaklar").fetchall()
        )
        assert kararlar == [BARISTA, MUSTERI], "sayılabilir kayıtlar KAYBEDİLMEMELİ"
    finally:
        baglanti.close()


def test_sayilamayacak_acik_kayit_yazilmaz(ayarlar):
    """Birkaç karelik yanlış tespit, kaydırıcı oynatıldı diye sayıma girmemeli."""
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        veritabani.semayi_uygula(baglanti)
        analiz = _analiz(ayarlar)
        durum = BardakDurumu(takip_id=1, ilk_zaman=_T, son_zaman=_T)
        durum.gozlem_ekle(MUSTERI, _T)  # tek gözlem — EN_AZ_GORULME altında
        analiz._acik[1] = durum

        analiz._acik_kayitlari_bosalt(baglanti)
        assert baglanti.execute("SELECT COUNT(*) AS n FROM bardaklar").fetchone()["n"] == 0
    finally:
        baglanti.close()


# ---- günlük ----


def test_gunluk_dosyasi_olusur(ayarlar):
    """Eskiden hata hiçbir yere yazılmıyordu: kullanıcının kopyalayacak bir
    satırı yoktu."""
    analiz = _analiz(ayarlar)
    analiz._log.info("deneme satırı")
    for islem in analiz._log.handlers:
        islem.flush()
    gunluk = ayarlar.veritabani.parent / "loglar" / "laffogato.log"
    assert gunluk.is_file()
    assert "deneme satırı" in gunluk.read_text(encoding="utf-8")
