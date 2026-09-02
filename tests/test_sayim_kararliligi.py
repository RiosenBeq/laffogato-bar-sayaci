"""Sayım kararlılığı: kararın nereye baktığı, zemin noktası, kapanma süresi,
hassasiyet değişimi ve tespit sınıf seçimi.

Bu dosyadaki her test, sahada ÖLÇÜLMÜŞ bir hatanın geri gelmesini engeller.
Hiçbiri kamera ya da model gerektirmez.
"""

from __future__ import annotations

import numpy as np

from app.bardak import (
    BARISTA,
    BELIRSIZ,
    MUSTERI,
    BardakDurumu,
    bolge_bul,
    zemin_noktasi,
)


def _durum(bolgeler: list[str]) -> BardakDurumu:
    d = BardakDurumu(takip_id=1, ilk_zaman="t0", son_zaman="t0")
    for i, b in enumerate(bolgeler):
        d.gozlem_ekle(b, f"t{i}")
    return d


# ---- karar: bardağın NEREYE GİTTİĞİ ----


def test_uzun_bekleyip_musteriye_giden_bardak_musteri_sayilir():
    """ESKİ HATA: karar tüm yaşam boyu gözlem sayısına bakıyordu. Tezgâhta 2
    dakika bekleyip müşteriye giden bardak 'barista' yazılıyordu; bar ne kadar
    yoğunsa hata o kadar büyüyordu."""
    durum = _durum([BARISTA] * 40 + [MUSTERI] * 8)
    assert durum.karar() == MUSTERI


def test_baristada_kalan_bardak_barista_sayilir():
    assert _durum([BARISTA] * 30).karar() == BARISTA


def test_musteriye_gidip_geri_donen_bardak_son_haline_bakar():
    durum = _durum([MUSTERI] * 20 + [BARISTA] * 8)
    assert durum.karar() == BARISTA


def test_son_gozlemler_kararsizsa_tum_yasama_bakilir():
    """Son pencere iki taraf arasında bölünmüşse eski (tüm yaşam) oylaması
    devreye girer — uydurma karar üretilmez."""
    durum = _durum([MUSTERI] * 30 + [MUSTERI, BARISTA] * 4)
    assert durum.karar() == MUSTERI


def test_az_gozlemde_son_pencereye_guvenilmez():
    """Sadece 2 gözlem varsa 'son pencere' kararı istatistiksel olarak anlamsız."""
    durum = _durum([BARISTA, MUSTERI])
    assert durum.karar() == BELIRSIZ


def test_hic_bolgede_gorulmeyen_bardak_belirsiz():
    assert _durum(["", "", ""]).karar() == BELIRSIZ


# ---- zemin noktası ----


def test_zemin_noktasi_kutunun_alt_ortasi():
    """Bölge kararı bardağın tezgâha DEĞDİĞİ yerle verilmeli. Kutu merkezi
    kullanılırsa, bara açılı bakan kamerada uzun bir bardağın merkezi ayak
    izinden yukarıda kalır ve sınırın gerisindeki bardak 'önünde' görünürdü."""
    assert zemin_noktasi((100.0, 200.0, 200.0, 400.0), (1000.0, 1000.0)) == (0.15, 0.4)


def test_uzun_bardak_sinirin_dogru_tarafinda_sayilir():
    bolgeler = {
        MUSTERI: [(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)],  # üst yarı
        BARISTA: [(0.0, 0.5), (1.0, 0.5), (1.0, 1.0), (0.0, 1.0)],  # alt yarı
    }
    # Barista tarafında duran UZUN bir bardak: tabanı 0.62, merkezi 0.47
    kutu = (400.0, 320.0, 460.0, 620.0)
    kare = (1000.0, 1000.0)
    merkez = ((kutu[0] + kutu[2]) / 2 / kare[0], (kutu[1] + kutu[3]) / 2 / kare[1])
    assert bolge_bul(merkez, bolgeler) == MUSTERI, "eski davranış (merkez) yanlış tarafı verir"
    assert bolge_bul(zemin_noktasi(kutu, kare), bolgeler) == BARISTA


# ---- kapanma süresi ----


def test_kapanma_esigi_saniye_cinsinden_ve_takipci_hafizasindan_kisa():
    """ESKİ HATA: eşik sabit 12 KARE idi — 1 fps'te 12 sn, 15 fps'te 0,8 sn.
    4 fps'te 3 saniyeye denk geliyor ve takipçinin 15 saniyelik hafızasından
    ÖNCE kapanıyordu: geri gelen bardak yeni kayıt açıyor, düzeltilmiş karar
    sessizce çöpe gidiyordu."""
    from app.analiz import _IZ_HAFIZASI_SN, _KAYIP_ESIGI_SN

    assert _KAYIP_ESIGI_SN < _IZ_HAFIZASI_SN, (
        "kayıt, takipçi izi düşürmeden ÖNCE kapanmalı ki aynı numara geri gelsin"
    )


def test_kapanma_esigi_fpse_gore_olceklenir(ayarlar):
    from dataclasses import replace

    from app.analiz import Analiz

    for fps, en_az in ((1.0, 8), (4.0, 40), (10.0, 100)):
        analiz = Analiz(replace(ayarlar, kare_fps=fps))
        kare = analiz._kayip_esigi_kare()
        assert kare >= en_az * 0.9, f"{fps} fps için {kare} kare çok kısa"


# ---- tespit: sınıf seçimi ----


def _tespitci(guven=0.30, genis=False):
    from app.tespit import Tespitci

    t = Tespitci.__new__(Tespitci)
    t._boy = 416
    t.guven = guven
    t.genis_aday = genis
    return t


def _cikti(satirlar):
    toplam = sum((416 // adim) ** 2 for adim in (8, 16, 32))
    c = np.zeros((toplam, 85), dtype=np.float32)
    for i, (cx, cy, w, h, nesnelik, siniflar) in enumerate(satirlar):
        c[i, 0] = cx / 8.0
        c[i, 1] = cy / 8.0
        c[i, 2] = np.log(w / 8.0)
        c[i, 3] = np.log(h / 8.0)
        c[i, 4] = nesnelik
        for sinif, skor in siniflar.items():
            c[i, 5 + sinif] = skor
    return c


def test_ilgisiz_sinif_baskin_olsa_bile_bardak_kaybolmaz():
    """ESKİ HATA: 80 COCO sınıfı üzerinde argmax alınıyordu. Fincan/kâse/masa
    birbirine en çok karışan sınıflardır; 0,42 ile 'fincan', 0,45 ile 'yemek
    masası' bulunan gerçek bir bardak SESSİZCE kayboluyordu."""
    t = _tespitci(guven=0.30)
    # 41 = cup (bizim), 60 = dining table (ilgisiz, daha yüksek)
    kutular, guvenler, tipler = t._son_isle(
        _cikti([(200, 200, 40, 60, 1.0, {41: 0.42, 60: 0.75})]), 1.0, 640, 480
    )
    assert list(tipler) == ["bardak"], (kutular, guvenler)


def test_sise_dogrudan_bardak_sayilmaz():
    """COCO 39 = bottle. Tezgâhta duran su/şurup şişesi 'yapılan bardak' olarak
    günlük sayaca giriyordu. Artık ADAY: doğrulayıcı açıkça 'bardak' demeli."""
    from app.tespit import GENIS_ADAY_ESLEME, SINIF_ESLEME

    assert 39 not in SINIF_ESLEME
    assert GENIS_ADAY_ESLEME[39] == "aday"


def test_aday_bardagi_nmste_bastiramaz():
    """ESKİ HATA: aday (kâse/vazo/şişe) ile bardak aynı NMS bandındaydı; üst
    üste binen bir kâse kutusu bardağı bastırıyor, hayatta kalan kutu 'aday'
    olduğu için eleniyordu. Sonuç: doğrulayıcıyı açmak sayıyı DÜŞÜRÜYORDU."""
    t = _tespitci(guven=0.30, genis=True)
    _, _, tipler = t._son_isle(
        _cikti(
            [
                (200, 200, 40, 60, 1.0, {41: 0.80}),  # gerçek bardak
                (203, 202, 44, 62, 1.0, {45: 0.85}),  # neredeyse aynı yerde kâse
            ]
        ),
        1.0,
        640,
        480,
    )
    assert "bardak" in list(tipler), f"bardak bastırılmamalı: {list(tipler)}"


def test_kisi_ve_bardak_birbirini_bastirmaz():
    t = _tespitci(guven=0.30)
    _, _, tipler = t._son_isle(
        _cikti(
            [
                (200, 300, 90, 220, 1.0, {0: 0.85}),
                (205, 305, 40, 60, 1.0, {41: 0.70}),
            ]
        ),
        1.0,
        640,
        480,
    )
    assert sorted(tipler) == ["bardak", "kisi"]


# ---- takipçi eşiği ----


def test_dusuk_hassasiyette_olu_bant_yok(ayarlar):
    """supervision içeride det_thresh = eşik + 0,1 kullanır ve yeni izi ANCAK
    bunun üstünde başlatır. Eski formülde (hassasiyet*0,6) hassasiyet 0,25'in
    altında det_thresh hassasiyetin ÜSTÜNE çıkıyordu: bardak tespit ediliyor
    ama hiç takip edilmiyor, ekranda kutu bile çıkmıyordu."""
    from app.analiz import Analiz

    analiz = Analiz(ayarlar)
    for hassasiyet in (0.15, 0.20, 0.25, 0.30, 0.50):
        izleyici = analiz._izleyici_kur(hassasiyet)
        assert izleyici.det_thresh < hassasiyet, (
            f"hassasiyet {hassasiyet}: yeni iz için gereken {izleyici.det_thresh:.2f} "
            "eşiğin üstünde — bardak sayılamaz"
        )


def test_takipci_hizli_harekete_toleransli(ayarlar):
    """Barista bardağı müşteriye uzatırken bardak kare başına çok yol alır;
    varsayılan tolerans (0,8) düşük kare hızında izi koparıp bardağı İKİ KEZ
    saydırıyordu."""
    from app.analiz import Analiz

    izleyici = Analiz(ayarlar)._izleyici_kur(0.30)
    assert izleyici.minimum_matching_threshold >= 0.9
