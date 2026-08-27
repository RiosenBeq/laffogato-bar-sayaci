"""Denetimde bulunan kusurların regresyon testleri.

Bu dosyadaki her test, gerçekten yaşanmış bir hataya karşılık gelir; sessizce
geri gelmesinler diye buradalar.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app import veritabani, zaman
from app.egitim import (
    EN_AZ_ISABET,
    EN_AZ_TEST_SINIF,
    Karsilastirma,
    _bolme_hatasi,
    _kapiyi_uygula,
    _partiye_gore_bol,
)
from app.egitim import EgitimSonucu as Sonuc


@pytest.fixture
def baglanti(ayarlar):
    b = veritabani.baglanti_ac(ayarlar.veritabani)
    veritabani.semayi_uygula(b)
    yield b
    b.close()


def _veri(partiler: dict[str, int]) -> list[dict]:
    veri = []
    for parti, adet in partiler.items():
        for i in range(adet):
            veri.append({"parti": parti, "etiket": "bardak" if i % 2 else "degil"})
    return veri


def test_bolme_egitim_kumesini_bosaltmaz():
    """Küçük son partiler hedefe ulaşmak için TÜM partileri teste çekiyordu."""
    veri = _veri({"p1": 80, "p2": 24})
    egitim, test = _partiye_gore_bol(veri, ["p1", "p2"])
    assert len(egitim) > 0, "en eski parti her zaman eğitimde kalmalı"
    assert len(test) > 0
    assert len(egitim) + len(test) == len(veri)


def test_bolme_cok_partide_de_egitimi_korur():
    veri = _veri({"p1": 160, "p2": 8, "p3": 8, "p4": 8, "p5": 8})
    egitim, test = _partiye_gore_bol(veri, ["p1", "p2", "p3", "p4", "p5"])
    assert len(egitim) >= 160, "en eski (büyük) parti eğitimde kalmalı"


def test_dengesiz_test_kumesi_reddedilir():
    """11'e 1 dengesiz test kümesinde boş bir model %92 isabet gösterirdi."""
    egitim = _veri({"p1": 40})
    test = [{"etiket": "degil"} for _ in range(11)] + [{"etiket": "bardak"}]
    hata = _bolme_hatasi(egitim, test)
    assert hata is not None
    assert str(EN_AZ_TEST_SINIF) in hata


def test_dusuk_isabetli_model_devreye_alinmaz():
    """Kütüphane boşken eski isabet 0 olur ve 'gerilemedi' şartı kendiliğinden
    sağlanırdı; kötü bir model bu boşluktan devreye girerdi."""
    s = Sonuc(test_sayisi=40)
    s.eski = Karsilastirma("eski", dogru=0, yanlis=0, belirsiz=40)
    s.yeni = Karsilastirma("yeni", dogru=12, yanlis=23, belirsiz=5)  # isabet ~%34
    _kapiyi_uygula(s)
    assert s.yeni.isabet < EN_AZ_ISABET
    assert s.devreye_alindi is False
    assert "en az" in s.sebep


def test_iyi_model_devreye_alinir():
    s = Sonuc(test_sayisi=40)
    s.eski = Karsilastirma("eski", dogru=0, yanlis=0, belirsiz=40)
    s.yeni = Karsilastirma("yeni", dogru=34, yanlis=2, belirsiz=4)
    _kapiyi_uygula(s)
    assert s.devreye_alindi is True


def test_belirsiz_dusmezse_devreye_alinmaz():
    s = Sonuc(test_sayisi=40)
    s.eski = Karsilastirma("eski", dogru=30, yanlis=2, belirsiz=8)
    s.yeni = Karsilastirma("yeni", dogru=28, yanlis=2, belirsiz=10)
    _kapiyi_uygula(s)
    assert s.devreye_alindi is False
    assert "Belirsiz sayısı düşmedi" in s.sebep


def test_isabet_metni_hic_karar_verilmeyince_yuzde_gostermez():
    """'%0' yanıltıcıdır: yöntem yanlış cevap vermedi, hiç cevap veremedi."""
    bos = Karsilastirma("eski", dogru=0, yanlis=0, belirsiz=40)
    assert "%" not in bos.isabet_metni
    dolu = Karsilastirma("yeni", dogru=9, yanlis=1, belirsiz=0)
    assert dolu.isabet_metni == "%90"


def test_ayni_anda_iki_yukleme_ayri_parti_olur(baglanti, ayarlar):
    """Aynı saniyeye düşen iki yükleme tek partiye çökmemeli."""
    from app.egitim import ornekleri_topla

    class SahteTespitci:
        def adaylari_bul(self, kare, guven=0.20):
            return [((5.0, 5.0, 45.0, 55.0), 0.9, 1)]

    kare = np.random.default_rng(2).integers(0, 255, (80, 60, 3), dtype=np.uint8)
    ornekleri_topla(baglanti, ayarlar, [("a.jpg", kare)], SahteTespitci())
    ornekleri_topla(baglanti, ayarlar, [("b.jpg", kare)], SahteTespitci())

    satirlar = baglanti.execute("SELECT parti, dosya FROM bardak_ornekleri").fetchall()
    assert len({s["parti"] for s in satirlar}) == 2, "iki ayrı yükleme = iki parti"
    assert len({s["dosya"] for s in satirlar}) == 2, "kırpık dosyaları çakışmamalı"
    for s in satirlar:
        assert (ayarlar.egitim_klasoru / s["dosya"]).is_file()


def test_model_yoksa_hicbir_kutu_elenmez(ayarlar):
    """Model devrede değilken canlı sayım davranışı birebir korunmalı."""
    from app.analiz import Analiz

    analiz = Analiz(ayarlar)
    kare = np.zeros((100, 100, 3), dtype=np.uint8)
    kutular = np.array([[10.0, 10.0, 40.0, 60.0], [50.0, 10.0, 90.0, 60.0]])
    guvenler = np.array([0.8, 0.7])
    tipler = np.array(["bardak", "kisi"], dtype=object)
    k2, g2, t2 = analiz._adaylari_dogrula(kare, kutular, guvenler, tipler)
    assert len(k2) == 2 and list(t2) == ["bardak", "kisi"]


class _SahteModel:
    """Verilen kararları sırayla döndüren sahte doğrulayıcı."""

    def __init__(self, kararlar):
        self.model_var = True
        self._kararlar = list(kararlar)

    def karar(self, kirpik):
        return self._kararlar.pop(0), 0.5

    def gerekirse_yenile(self):
        pass


def test_belirsiz_kase_vazo_sayima_girmez(ayarlar):
    """Genişletilmiş sınıflar (kâse/vazo) ancak AÇIKÇA 'bardak' denirse sayılır.

    Aksi halde tezgâhtaki seramik şeker kâsesi, model ona 'belirsiz' dediğinde
    bardak olarak sayılırdı — bugün hiç sayılmayan bir şey için gerileme olurdu.
    """
    from app.analiz import Analiz

    analiz = Analiz(ayarlar)
    kare = np.random.default_rng(7).integers(0, 255, (100, 100, 3), dtype=np.uint8)
    kutular = np.array([[10.0, 10.0, 40.0, 60.0], [50.0, 10.0, 90.0, 60.0]])
    guvenler = np.array([0.8, 0.7])
    tipler = np.array(["aday", "aday"], dtype=object)

    # İlk kâseye "belirsiz", ikincisine "bardak" denir
    analiz._model = _SahteModel(["belirsiz", "bardak"])
    k2, _g2, t2 = analiz._adaylari_dogrula(kare, kutular, guvenler, tipler)
    assert len(k2) == 1, "belirsiz kâse sayıma girmemeli"
    assert list(t2) == ["bardak"], "onaylanan aday 'bardak' olarak devam etmeli"


def test_belirsiz_bardak_elenmez(ayarlar):
    """Hazır modelin bardak dediği kutu, YALNIZCA açıkça 'değil' ise elenir."""
    from app.analiz import Analiz

    analiz = Analiz(ayarlar)
    kare = np.random.default_rng(8).integers(0, 255, (100, 100, 3), dtype=np.uint8)
    kutular = np.array([[10.0, 10.0, 40.0, 60.0], [50.0, 10.0, 90.0, 60.0]])
    guvenler = np.array([0.8, 0.7])
    tipler = np.array(["bardak", "bardak"], dtype=object)

    analiz._model = _SahteModel(["belirsiz", "degil"])
    k2, _g2, t2 = analiz._adaylari_dogrula(kare, kutular, guvenler, tipler)
    assert len(k2) == 1, "belirsiz bardak elenmemeli, 'değil' elenmeli"
    assert analiz.dogrulayici_eledi == 1


def test_toplam_kare_tavani_uygulanir():
    """Dosya sayısını sınırlamak yetmiyordu: 20 video x 10 kare = 200 kare."""
    from app.web.egitim_rotalari import EN_COK_KARE, _kareleri_coz

    kucuk = cv2.imencode(".jpg", np.zeros((20, 20, 3), dtype=np.uint8))[1].tobytes()
    ogeler = [(f"{i}.jpg", "gorsel", kucuk) for i in range(EN_COK_KARE + 15)]
    assert len(_kareleri_coz(ogeler)) == EN_COK_KARE


def test_cok_buyuk_dosya_bellege_okunmaz():
    """Video listesinde olmayan uzantılar sınırsız belleğe okunuyordu."""
    import asyncio

    from app.web.nesne_rotalari import EN_BUYUK_GORSEL, _yukleri_topla

    class SahteYukleme:
        filename = "bar.m4v"  # VIDEO_UZANTILAR'da YOK → 'görsel' sayılırdı

        def __init__(self):
            self._kalan = EN_BUYUK_GORSEL + 5 * 1024 * 1024

        async def read(self, n=-1):
            if self._kalan <= 0:
                return b""
            parca = min(n if n > 0 else self._kalan, self._kalan)
            self._kalan -= parca
            return b"\0" * parca

    ogeler = asyncio.run(_yukleri_topla([SahteYukleme()]))
    assert ogeler[0][2] is None, "sınırı aşan dosya belleğe alınmamalı"


def test_bozuk_veri_kareleri_cozmeyi_bozmaz():
    from app.web.egitim_rotalari import _kareleri_coz

    assert _kareleri_coz([("a.jpg", "gorsel", None), ("b.jpg", "gorsel", b"bozuk")]) == []


def test_parti_sayisi_egitimle_ayni_seyi_sayar(baglanti, ayarlar):
    """Durum tablosu '2 yükleme ✓' derken eğitim '2 gerekiyor' diye reddetmemeli."""
    from app.egitim import sayilar

    kirpik = np.random.default_rng(11).integers(0, 255, (40, 30, 3), dtype=np.uint8)
    for i, (parti, etiket) in enumerate(
        (("p1", "bardak"), ("p1", "degil"), ("p2", None), ("p3", None))
    ):
        ad = f"s{i}.jpg"
        cv2.imwrite(str(ayarlar.egitim_klasoru / ad), kirpik)
        baglanti.execute(
            "INSERT INTO bardak_ornekleri (dosya, parti, kaynak, kutu, etiket, eklendi) "
            "VALUES (?, ?, 'yukleme', '[0,0,1,1]', ?, ?)",
            (ad, parti, etiket, zaman.simdi_utc()),
        )
    baglanti.commit()
    # Etiketli kırpığı olan tek yükleme var (p1); p2/p3 etiketsiz
    assert sayilar(baglanti)["parti"] == 1
