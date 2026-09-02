"""Analiz iş parçacığı: kamera → tespit → takip → bardak kararı → kayıt.

Sayım ilkesi: her BENZERSİZ bardak takibi günde bir kez sayılır. Bardak
kadrajdan çıkınca (birkaç saniye görünmeyince) "kime gitti" kararı verilir
ve kaydedilir; bu yüzden sayılar birkaç saniye gecikmeyle görünür.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import supervision as sv  # noqa: E402

from app import veritabani, zaman  # noqa: E402
from app.ayarlar import Ayarlar  # noqa: E402
from app.bardak import (  # noqa: E402
    BARISTA,
    MUSTERI,
    BardakDurumu,
    TekrarKorumasi,
    bolge_bul,
    zemin_noktasi,
)
from app.bardak_modeli import BardakModeli, bardak_kirp  # noqa: E402
from app.tespit import ModelHatasi, Tespitci  # noqa: E402

# Bardak bu kadar SANİYE görünmezse "gitti" sayılır ve kararı kesinleşir.
#
# DİKKAT — bu değer KARE değil SANİYE cinsindendir ve takipçinin hafızasından
# (_IZ_HAFIZASI_SN) KISA olmalıdır. Eskiden sabit 12 KARE idi: 1 fps'te 12
# saniye, 15 fps'te 0,8 saniye ediyordu. Daha kötüsü, 4 fps'te 3 saniyeye denk
# geliyordu; yani kayıt kapanıyor, ama takipçi aynı bardağa 15 saniye boyunca
# AYNI numarayı geri veriyordu. Geri gelen bardak yeni bir kayıt açıyor,
# INSERT OR IGNORE ile düzeltilmiş karar sessizce çöpe gidiyordu.
# Şimdi: kapanma, takipçinin izi düşürmesinden hemen ÖNCE olur — barista
# bardağın önünden geçtiğinde kayıt bölünmez.
_KAYIP_ESIGI_SN = 12.0

# Takipçinin kayıp bir izi hatırlama süresi, SANİYE cinsinden.
#
# DİKKAT — çift sayımın kök nedeni buradaydı: supervision, lost_track_buffer'ı
# doğrudan kare olarak saymaz, şunu yapar:
#     max_time_lost = int(frame_rate / 30 * lost_track_buffer)
# Yani 4 fps'te lost_track_buffer=60 vermek 60 kare (15 sn) DEĞİL, yalnızca
# int(4/30*60)=8 kare = 2 SANİYE hafıza demekti. Barista bardağın önünden
# 2 saniyeden uzun geçince iz düşüyor, bardak yeniden göründüğünde YENİ takip
# numarası alıyor ve ikinci kez sayılıyordu.
# Doğrusu: buffer = 30 * istenen_saniye  →  max_time_lost = fps * istenen_saniye.
_IZ_HAFIZASI_SN = 15.0

# Renk imzası: tekrar korumasının "aynı görünüm mü" kanıtı (bkz. bardak.py).
# ORB deseni bu projenin kırpıklarında ölçüldü ve tutunacak iz vermiyor
# (medyan 1 anahtar nokta); renk histogramı çalışıyor.
_IMZA_TON_GOZ, _IMZA_DOYGUNLUK_GOZ = 12, 4

# Kanıt fotoğrafı her bu kadar gözlemde bir tazelenir (bellekte)
_FOTO_TAZELEME = 10

_RENKLER = {"bardak": (60, 190, 255), "kisi": (150, 150, 150)}
_BOLGE_RENKLERI = {MUSTERI: (90, 200, 90), BARISTA: (200, 140, 60)}


def _log_kur(ayarlar: Ayarlar) -> logging.Logger:
    """Günlük dosyası: veri/loglar/laffogato.log.

    Eskiden hiçbir yere yazılmıyordu; bir hata yalnızca `durum` metnine düşüyor
    ve bir sonraki başarılı karede siliniyordu. Sorun bildirmek isteyen kullanıcının
    kopyalayacak bir satırı yoktu.
    """
    log = logging.getLogger("laffogato")
    klasor = ayarlar.veritabani.parent / "loglar"
    hedef = str((klasor / "laffogato.log").resolve())
    # Aynı hedefe zaten kuruluysa dokunma; hedef DEĞİŞTİYSE (testler, taşınan
    # kurulum) eski işleyicileri bırak ve yeniden kur — aksi halde günlük ilk
    # açılışta belirlenen klasöre yazmaya devam ederdi.
    if log.handlers:
        if any(getattr(h, "baseFilename", None) == hedef for h in log.handlers):
            return log
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        klasor.mkdir(parents=True, exist_ok=True)
        dosya = RotatingFileHandler(
            klasor / "laffogato.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        dosya.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(dosya)
    except OSError:
        pass  # dosyaya yazılamıyorsa ekran akışı yeter
    ekran = logging.StreamHandler()
    ekran.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(ekran)
    return log


class Analiz:
    def __init__(self, ayarlar: Ayarlar) -> None:
        self.ayarlar = ayarlar
        self._dur = threading.Event()
        self._is = threading.Thread(target=self._dongu, name="analiz", daemon=True)
        self._kilit = threading.Lock()
        self._son_jpeg: bytes | None = None
        self._kare_boyutu: tuple[int, int] = (0, 0)

        self.durum = "başlatılıyor"
        self.model_hatasi: str | None = None
        self.kaynak_hatasi: str | None = None
        self.canli_bardak = 0
        self.canli_kisi = 0

        self._tespitci: Tespitci | None = None
        self._hassasiyet = 0.30
        self._izleyici = self._izleyici_kur(self._hassasiyet)
        self._acik: dict[int, BardakDurumu] = {}
        self._kayip: dict[int, int] = {}
        self._bolgeler: dict[str, list[tuple[float, float]]] = {}
        self._tekrar = TekrarKorumasi()
        # Takip numaraları izleyici her kurulduğunda 1'den başlar. Kayıt
        # tablosunda UNIQUE (gun, takip_id) olduğu için, gün içinde ikinci kez
        # kullanılan bir numara INSERT OR IGNORE ile SESSİZCE düşerdi — yani
        # bardak sayılmazdı. Bu ofset, o günkü en büyük numaranın üstünden
        # devam ederek çakışmayı engeller.
        self._id_ofseti = 0
        # Son sayılan bardaklar: ekran bunları TEK TEK okur ve her biri için
        # bir uyarı verir. Eskiden ekran, iki saniyelik yoklamalar arasındaki
        # SAYAÇ FARKINA bakıyordu: aynı pencerede kapanan iki bardak tek uyarı
        # oluyor, geçmiş gün görüntülenirken uyarı hiç gelmiyordu.
        self._olaylar: deque = deque(maxlen=100)
        self._olay_sayaci = 0
        self.son_hata: str = ""
        self._log = _log_kur(ayarlar)
        # Eğitilmiş bardak doğrulayıcı. Yoksa sayım bugünkü gibi çalışır.
        self._model = BardakModeli(ayarlar.bardak_model_klasoru)
        self.dogrulayici_eledi = 0

    # ---- yaşam döngüsü ----

    def baslat(self) -> None:
        self._is.start()

    def durdur(self) -> bool:
        """Durdurma isteği gönderir; iş parçacığı gerçekten bittiyse True döner."""
        self._dur.set()
        if self._is.is_alive():
            self._is.join(timeout=8)
        return not self._is.is_alive()

    def onizleme(self) -> bytes | None:
        with self._kilit:
            return self._son_jpeg

    @property
    def kare_boyutu(self) -> tuple[int, int]:
        return self._kare_boyutu

    def sayaclari_sifirla(self) -> None:
        self._acik.clear()
        self._kayip.clear()
        self._tekrar = TekrarKorumasi()

    def olaylar(self, sonra: int = 0) -> list[dict]:
        """`sonra` numarasından yeni olan sayım olayları (ekran bunu yoklar)."""
        return [o for o in list(self._olaylar) if o["id"] > sonra]

    @property
    def son_olay_id(self) -> int:
        return self._olay_sayaci

    @property
    def tekrar_bastirilan(self) -> int:
        """Kaç bardak 'az önce sayılanın devamı' diye tekrar sayılmadı."""
        return self._tekrar.bastirilan

    # ---- ana döngü ----

    def _id_ofsetini_tazele(self, baglanti) -> None:
        satir = baglanti.execute(
            "SELECT COALESCE(MAX(takip_id), 0) AS son FROM bardaklar WHERE gun = ?",
            (zaman.bugun(),),
        ).fetchone()
        self._id_ofseti = int(satir["son"])

    def _dongu(self) -> None:
        baglanti = veritabani.baglanti_ac(self.ayarlar.veritabani)
        self._id_ofsetini_tazele(baglanti)
        try:
            self._tespitci = Tespitci(self.ayarlar.model_dosyasi, self.ayarlar.cihaz)
        except ModelHatasi as hata:
            # Ekrana YALNIZCA sade metin çıkar (ana sayfadaki uyarı kutusu).
            # Tam yol ve özgün istisna metni tespit.py içinde günlüğe yazıldı.
            self.model_hatasi = hata.mesaj
            self._log.error("Tespit modeli açılamadı: %s", hata.teknik)
            self.durum = "model yok"

        bekleme = 1.0
        try:
            while not self._dur.is_set():
                yakalayici = self._kaynagi_ac()
                if yakalayici is None:
                    self.durum = "kameraya bağlanılamadı"
                    if self._dur.wait(bekleme):
                        break
                    bekleme = min(bekleme * 2, 30.0)
                    continue
                bekleme = 1.0
                self.kaynak_hatasi = None
                self.durum = "canlı"
                try:
                    self._kareleri_isle(yakalayici, baglanti)
                finally:
                    yakalayici.release()
        finally:
            baglanti.close()
            self.durum = "durdu"

    def _kaynagi_ac(self):
        kaynak = self.ayarlar.kaynak_cozumle()
        if isinstance(kaynak, int):
            # Windows'ta varsayılan arka uç (MSMF) yerleşik kamerada sık takılır
            # ve açılışı 10+ sn sürdürebilir; DirectShow güvenilir çalışır.
            # macOS/Linux'ta varsayılan arka uç doğrudur.
            arka_uc = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            yakalayici = cv2.VideoCapture(kaynak, arka_uc)
        else:
            # Zaman aşımı olmadan kopan RTSP bağlantısı read() içinde dakikalarca
            # bloklanabilir; o zaman durdur() da bekler. 10 sn üst sınır koyuyoruz.
            yakalayici = cv2.VideoCapture(
                kaynak,
                cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000],
            )
        if not yakalayici.isOpened():
            yakalayici.release()
            self.kaynak_hatasi = (
                f"Kamera açılamadı (KAYNAK={self.ayarlar.kaynak}).\n"
                "• Bilgisayar kamerası için: macOS'ta ilk açılışta kamera izni "
                "sorulur — 'İzin Ver' deyin (Sistem Ayarları → Gizlilik ve "
                "Güvenlik → Kamera).\n"
                "• Kamerayı başka bir program (Zoom, FaceTime) kullanıyorsa "
                "kapatın.\n"
                "• IP kamera için RTSP adresini kontrol edin."
            )
            return None
        return yakalayici

    def _kareleri_isle(self, yakalayici, baglanti) -> None:
        aralik = 1.0 / self.ayarlar.kare_fps
        kaynak = self.ayarlar.kaynak_cozumle()
        dosya_mi = isinstance(kaynak, str) and not kaynak.lower().startswith(("rtsp", "http"))
        while not self._dur.is_set():
            basla = time.monotonic()
            tamam, kare = yakalayici.read()
            if not tamam:
                if dosya_mi:
                    yakalayici.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if self._dur.wait(0.1):  # bozuk dosyada boş dönüp CPU yakmasın
                        return
                    continue
                return  # canlı akış koptu → yeniden bağlan
            self._kare_boyutu = (kare.shape[1], kare.shape[0])
            try:
                self._kareyi_degerlendir(kare, baglanti)
            except Exception as hata:  # noqa: BLE001 — demo döngüsü ölmemeli
                # `durum` bir sonraki başarılı karede silinir; son_hata KALIR ve
                # ekranda görünür, ayrıca günlüğe yazılır. Eskiden hata hiçbir
                # yere düşmüyordu: kullanıcının kopyalayacak bir satırı yoktu.
                self.durum = f"hata: {hata}"
                self.son_hata = f"{zaman.saat(zaman.simdi_utc())} — {hata}"
                self._log.error(f"Kare işlenemedi: {hata}", exc_info=hata)
            if self._dur.wait(max(0.0, aralik - (time.monotonic() - basla))):
                return

    def _kareyi_degerlendir(self, kare: np.ndarray, baglanti) -> None:
        self._bolgeler = veritabani.bolgeleri_oku(baglanti)
        if self._tespitci is None:
            self._onizleme_yaz(kare, [])
            return
        self._hassasiyeti_uygula(baglanti)

        # Devreye alınan yeni model yeniden başlatmadan yüklensin
        self._model.gerekirse_yenile()
        # Seramik fincanın COCO'da saklandığı bowl/vase sınıfları YALNIZCA
        # doğrulayıcı devredeyken aday olur; onları eleyecek bir şey var demektir.
        self._tespitci.genis_aday = self._model.model_var

        kutular, guvenler, tipler = self._tespitci.bul(kare)
        kutular, guvenler, tipler = self._adaylari_dogrula(kare, kutular, guvenler, tipler)
        izler = self._takip_et(kutular, guvenler, tipler)
        bardaklar = [i for i in izler if i["tip"] == "bardak"]
        self.canli_bardak = len(bardaklar)
        self.canli_kisi = sum(1 for i in izler if i["tip"] == "kisi")

        self._bardaklari_izle(bardaklar, kare, baglanti)
        self._onizleme_yaz(kare, izler)

    def _adaylari_dogrula(self, kare, kutular, guvenler, tipler):
        """Eğitilmiş doğrulayıcı devredeyse "bardak değil" denen kutuları eler.

        Model yoksa hiçbir şey değişmez. "Belirsiz" çıkan kutu da ELENMEZ —
        emin olmadan bardağı sayımdan düşürmeyiz (kanıtın yokluğu, yokluğun
        kanıtı değildir).
        """
        if not self._model.model_var or len(kutular) == 0:
            return kutular, guvenler, tipler
        tutulacak: list[int] = []
        yeni_tipler = list(tipler)
        for i, tip in enumerate(tipler):
            if tip not in ("bardak", "aday"):
                tutulacak.append(i)  # kişi kutularına dokunulmaz
                continue
            kirpik = bardak_kirp(kare, tuple(float(v) for v in kutular[i]))
            karar, _ = self._model.karar(kirpik)
            if tip == "aday":
                # Hazır modelin "kâse/vazo" dediği kutu: ancak doğrulayıcı
                # AÇIKÇA "bardak" derse sayıma girer. Belirsiz olan elenir —
                # bugün zaten sayılmıyordu, riski artırmayız.
                if karar == "bardak":
                    yeni_tipler[i] = "bardak"
                    tutulacak.append(i)
                continue
            # Hazır modelin bardak dediği kutu: yalnızca AÇIKÇA "değil" ise
            # elenir. Belirsiz olan ELENMEZ (kanıtın yokluğu, yokluğun kanıtı değil).
            if karar == "degil":
                self.dogrulayici_eledi += 1
                continue
            tutulacak.append(i)
        secim = np.array(tutulacak, dtype=int)
        tip_dizisi = np.array(yeni_tipler, dtype=object)
        if len(tutulacak) == len(tipler):
            return kutular, guvenler, tip_dizisi
        return kutular[secim], guvenler[secim], tip_dizisi[secim]

    def _izleyici_kur(self, hassasiyet: float) -> sv.ByteTrack:
        """ByteTrack'i tespit hassasiyetine göre kurar.

        KRİTİK: ByteTrack, aktivasyon eşiğinin ALTINDA kalan tespitlerle yeni
        iz BAŞLATMAZ. Eşik tespit hassasiyetiyle aynı olursa (ör. ikisi de
        0,30) bardak her karede tespit edilse bile hiç takip edilmez ve
        sayaç sıfırda kalır. Bu yüzden aktivasyon, hassasiyetin belirgin
        şekilde altında tutulur.
        """
        kare_hizi = max(int(self.ayarlar.kare_fps), 1)
        return sv.ByteTrack(
            # AKTİVASYON EŞİĞİ: supervision içeride det_thresh = eşik + 0,1
            # kullanır ve yeni izi ANCAK bunun üstünde başlatır. Eşik
            # hassasiyet*0,6 iken, hassasiyet 0,25'in altında det_thresh
            # hassasiyetin ÜSTÜNE çıkıyordu: bardak tespit ediliyor ama hiç
            # takip edilmiyor, ekranda kutu bile çıkmıyordu (ölü bant).
            # Bu biçimde det_thresh her zaman hassasiyetin altında kalır.
            track_activation_threshold=max(0.02, hassasiyet - 0.12),
            # Bardak elle kapatılıp tekrar görünebilir; izi çabuk düşürme.
            # 30 ile çarpım ZORUNLU — gerekçesi _IZ_HAFIZASI_SN'de yazılı.
            lost_track_buffer=int(_IZ_HAFIZASI_SN * 30),
            # EŞLEŞTİRME TOLERANSI (IoU uzaklığı üst sınırı). Varsayılan 0,8
            # (IoU ≥ 0,20) düşük kare hızında yetmiyordu: barista bardağı
            # müşteriye uzatırken bardak kare başına kendi genişliğinin
            # yarısından çok yol alınca iz kopuyor, bardak İKİ KEZ sayılıyor ve
            # müşteri/barista ayrımı uyduruluyordu. 0,92 → IoU ≥ 0,08.
            minimum_matching_threshold=0.92,
            frame_rate=kare_hizi,
        )

    def _hassasiyeti_uygula(self, baglanti) -> None:
        """Ekrandan değiştirilen tespit hassasiyeti anında geçerli olsun."""
        ham = veritabani.ayarlari_oku(baglanti).get("tespit_hassasiyeti", "0.30")
        try:
            deger = float(ham)
        except ValueError:
            return  # bozuk değer: mevcut ayar korunur
        deger = min(max(deger, veritabani.HASSASIYET_EN_AZ), veritabani.HASSASIYET_EN_COK)
        # Tespit eşiği HER KAREDE uygulanır: aksi halde Tespitci kendi
        # yapıcı varsayılanında (0,35) kalır ve ayarlanan hassasiyet hiç
        # devreye girmez — bardaklar sessizce elenirdi.
        self._tespitci.guven = deger
        if abs(deger - self._hassasiyet) < 1e-9:
            return
        self._hassasiyet = deger
        # AÇIK KAYITLAR ÖNCE KAPATILIR. Yeni takipçi numaraları 1'den başlatır;
        # eski açık kayıtlar durursa, yeniden verilen numaralar BAŞKA bardaklara
        # ait gözlemlerin üstüne binerdi (ölçüldü: iki bardağın kararı da ters
        # dönüyordu). Sayılabilir durumdakiler kaydedilir, gerisi atılır.
        self._acik_kayitlari_bosalt(baglanti)
        # Takipçi eşiği hassasiyete bağlı: yeniden kurulur. Numaralar 1'den
        # başlayacağı için ofset tazelenir; yoksa o günkü ilk bardaklarla
        # çakışıp yeni bardaklar sessizce sayılmazdı.
        self._izleyici = self._izleyici_kur(deger)
        self._id_ofsetini_tazele(baglanti)

    def _acik_kayitlari_bosalt(self, baglanti) -> None:
        """Açık bardak kayıtlarını kapatır (sayılabilenleri yazarak)."""
        saat = time.monotonic()
        for durum in list(self._acik.values()):
            if durum.sayilir_mi():
                self._tekrar.hatirla(durum.son_merkez, durum.son_boyut, durum.renk_imzasi, saat)
                durum.foto = self._kirpigi_yaz(durum.foto_veri)
                self._bardagi_kaydet(baglanti, durum)
                self._olay_uret(durum)
        self._acik.clear()
        self._kayip.clear()

    def _takip_et(self, kutular, guvenler, tipler) -> list[dict]:
        if len(kutular) == 0:
            algilar = sv.Detections.empty()
        else:
            algilar = sv.Detections(
                xyxy=kutular.astype(float),
                confidence=guvenler.astype(float),
                class_id=np.array([0 if t == "kisi" else 1 for t in tipler]),
            )
        sonuc = self._izleyici.update_with_detections(algilar)
        izler = []
        for i in range(len(sonuc)):
            takip_id = sonuc.tracker_id[i] if sonuc.tracker_id is not None else None
            if takip_id is None:
                continue
            izler.append(
                {
                    "tip": "kisi" if int(sonuc.class_id[i]) == 0 else "bardak",
                    "takip_id": int(takip_id),
                    "kutu": tuple(float(v) for v in sonuc.xyxy[i]),
                }
            )
        return izler

    # ---- bardak takibi ----

    def _bardaklari_izle(self, bardaklar: list[dict], kare, baglanti) -> None:
        simdi = zaman.simdi_utc()
        saat = time.monotonic()
        genislik, yukseklik = self._kare_boyutu
        gorulenler = set()

        for bardak in bardaklar:
            takip_id = bardak["takip_id"]
            gorulenler.add(takip_id)
            x1, y1, x2, y2 = bardak["kutu"]
            merkez = ((x1 + x2) / 2 / genislik, (y1 + y2) / 2 / yukseklik)
            boyut = (abs(x2 - x1) / genislik, abs(y2 - y1) / yukseklik)
            # Bölge kararı ZEMİN noktasıyla (kutunun alt-ortası): bardağın
            # tezgâha DEĞDİĞİ yer, kutusunun merkezi değil. Tekrar koruması
            # merkezi kullanmayı sürdürür (görünüm eşlemesi için doğrusu odur).
            bolge = bolge_bul(zemin_noktasi(bardak["kutu"], (genislik, yukseklik)), self._bolgeler)

            durum = self._acik.get(takip_id)
            if durum is None:
                durum = BardakDurumu(takip_id=takip_id, ilk_zaman=simdi, son_zaman=simdi)
                durum.foto_veri = self._kirpik_kodla(kare, bardak["kutu"])
                durum.renk_imzasi = self._renk_imzasi(kare, bardak["kutu"])
                # Az önce kapanmış bir bardağın devamı mı? Öyleyse bu iz
                # sayılmaz — tezgâhta bekleyen bardağın ikinci kez sayılmasını
                # önleyen ikinci savunma (birincisi: _IZ_HAFIZASI_SN).
                durum.tekrar_mi = self._tekrar.ayni_bardak_mi(
                    merkez, boyut, durum.renk_imzasi, saat
                )
                self._acik[takip_id] = durum
            durum.son_merkez = merkez
            durum.son_boyut = boyut
            durum.gozlem_ekle(bolge, simdi)
            # Kanıt fotoğrafını ara ara tazele: ilk karede çekilen fotoğraf
            # bardağı BARİSTA tarafında gösterirken kayıt "müşteriye gitti"
            # diyordu — bakan kişi haklı olarak sisteme güvenmiyordu.
            if durum.gorulme % _FOTO_TAZELEME == 0:
                yeni = self._kirpik_kodla(kare, bardak["kutu"])
                if yeni is not None:
                    durum.foto_veri = yeni
            self._kayip.pop(takip_id, None)

        # Görünmeyen bardaklar: yeterince beklendiyse kararı kesinleştir
        for takip_id in list(self._acik):
            if takip_id in gorulenler:
                continue
            self._kayip[takip_id] = self._kayip.get(takip_id, 0) + 1
            if self._kayip[takip_id] < self._kayip_esigi_kare():
                continue
            durum = self._acik.pop(takip_id)
            self._kayip.pop(takip_id, None)
            # YALNIZCA gerçekten sayılan bardaklar hatırlanır. Birkaç karelik
            # yanlış tespit (şekerlik, kaşık) hatırlanırsa, az sonra tam o
            # noktada hazırlanan GERÇEK bardağı "devam" sanıp yutardı.
            if durum.sayilir_mi():
                # YALNIZCA sayılan bardaklar hatırlanır. Bastırılmış izleri de
                # hatırlamak, tezgâhın o noktasını kalıcı bir "yutma alanı"na
                # çevirir ve sonraki gerçek bardakların hepsi kaybolurdu.
                self._tekrar.hatirla(durum.son_merkez, durum.son_boyut, durum.renk_imzasi, saat)
                # Kanıt fotoğrafı ANCAK burada diske yazılır: sayılmayan izler
                # (yanlış tespit, tekrar bastırılan) dosya bırakmaz.
                durum.foto = self._kirpigi_yaz(durum.foto_veri)
                self._bardagi_kaydet(baglanti, durum)
                self._olay_uret(durum)

    def _olay_uret(self, durum: BardakDurumu) -> None:
        """Sayılan bardağı olay akışına koyar — ekrandaki uyarının kaynağı.

        Ekran eskiden SAYAÇ FARKINA bakıyordu: aynı iki saniyelik pencerede
        kapanan iki bardak tek uyarı oluyor, geçmiş bir gün görüntülenirken hiç
        uyarı gelmiyordu.
        """
        self._olay_sayaci += 1
        karar = durum.karar()
        self._olaylar.append(
            {
                "id": self._olay_sayaci,
                "kime": karar,
                "zaman": zaman.saat(durum.son_zaman),
                "foto": durum.foto,
            }
        )
        self._log.info(f"Bardak sayıldı: {karar} (takip {durum.takip_id})")

    def _kayip_esigi_kare(self) -> int:
        """Saniye cinsinden eşiği, o anki örnekleme hızına göre kareye çevirir."""
        return max(2, round(_KAYIP_ESIGI_SN * max(self.ayarlar.kare_fps, 0.2)))

    def _bardagi_kaydet(self, baglanti, durum: BardakDurumu) -> None:
        """Bardağı yazar. Aynı (gün, takip_id) ikinci kez kapanırsa kayıt
        GÜNCELLENİR, sessizce atılmaz.

        Eskiden INSERT OR IGNORE vardı: bardak örtülüp yeniden göründüğünde
        takipçi aynı numarayı geri verir, kayıt ikinci kez kapanır ve
        DÜZELTİLMİŞ karar (bardak sonunda müşteriye gitti) sessizce çöpe
        giderdi; ekranda ilk, yanlış karar kalırdı.
        """
        baglanti.execute(
            "INSERT INTO bardaklar "
            "(gun, takip_id, baslangic, bitis, kime, musteri_gozlem, barista_gozlem, foto) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(gun, takip_id) DO UPDATE SET "
            "  bitis = excluded.bitis, kime = excluded.kime, "
            "  musteri_gozlem = excluded.musteri_gozlem, "
            "  barista_gozlem = excluded.barista_gozlem, "
            "  foto = COALESCE(bardaklar.foto, excluded.foto)",
            (
                zaman.bugun(),
                self._id_ofseti + durum.takip_id,
                durum.ilk_zaman,
                durum.son_zaman,
                durum.karar(),
                durum.bolge_sayaci.get(MUSTERI, 0),
                durum.bolge_sayaci.get(BARISTA, 0),
                durum.foto,
            ),
        )
        baglanti.commit()

    def _renk_imzasi(self, kare: np.ndarray, kutu) -> tuple[float, ...] | None:
        """Kutunun renk parmak izi (HSV histogramı), sade sayı dizisi olarak.

        bardak.py OpenCV bilmesin diye çıkarım burada yapılır; oradaki
        tekrar koruması yalnız sayıları karşılaştırır.
        """
        x1, y1, x2, y2 = (int(v) for v in kutu)
        x1, y1 = max(x1, 0), max(y1, 0)
        x2, y2 = min(x2, kare.shape[1]), min(y2, kare.shape[0])
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        hsv = cv2.cvtColor(kare[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        histogram = cv2.calcHist(
            [hsv], [0, 1], None, [_IMZA_TON_GOZ, _IMZA_DOYGUNLUK_GOZ], [0, 180, 0, 256]
        )
        toplam = float(histogram.sum())
        if toplam <= 0:
            return None
        return tuple((histogram / toplam).flatten().tolist())

    def _kirpik_kodla(self, kare: np.ndarray, kutu) -> bytes | None:
        """Kanıt kırpığını JPEG olarak BELLEĞE alır (diske yazmaz).

        Eskiden her yeni iz için hemen dosya yazılıyordu — birkaç karelik
        yanlış tespitler dahil. Hiçbiri temizlenmediği için kafe bilgisayarının
        diski sessizce doluyordu.
        """
        x1, y1, x2, y2 = (int(v) for v in kutu)
        pay = 10
        x1, y1 = max(x1 - pay, 0), max(y1 - pay, 0)
        x2 = min(x2 + pay, kare.shape[1])
        y2 = min(y2 + pay, kare.shape[0])
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        try:
            tamam, tampon = cv2.imencode(".jpg", kare[y1:y2, x1:x2])
        except cv2.error:
            return None
        return tampon.tobytes() if tamam else None

    def _kirpigi_yaz(self, veri: bytes | None) -> str | None:
        """Bellekteki kırpığı diske yazar; dosya adını döndürür.

        cv2.imwrite KULLANILMAZ: yolu işletim sisteminin kod sayfasıyla kodlar
        ve Türkçe klasör adında hata FIRLATMADAN başarısız olur — veritabanında
        var görünen, diskte olmayan fotoğraflar oluşurdu.
        """
        if not veri:
            return None
        ad = f"bardak-{zaman.bugun()}-{uuid.uuid4().hex[:8]}.jpg"
        try:
            (self.ayarlar.goruntu_klasoru / ad).write_bytes(veri)
        except OSError as hata:
            self._log.error(f"Kanıt fotoğrafı yazılamadı ({ad}): {hata}")
            return None
        return ad

    # ---- önizleme ----

    def _onizleme_yaz(self, kare, izler) -> None:
        gorsel = kare.copy()
        yukseklik, genislik = gorsel.shape[:2]

        for ad, poligon in self._bolgeler.items():
            if len(poligon) < 3:
                continue
            noktalar = np.array([(int(x * genislik), int(y * yukseklik)) for x, y in poligon])
            renk = _BOLGE_RENKLERI.get(ad, (180, 180, 180))
            cv2.polylines(gorsel, [noktalar], True, renk, 2)
            etiket = "Müşteri tarafı" if ad == MUSTERI else "Barista tarafı"
            cv2.putText(
                gorsel,
                etiket,
                tuple(noktalar[0] + np.array([4, 18])),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                renk,
                1,
                cv2.LINE_AA,
            )

        for iz in izler:
            x1, y1, x2, y2 = (int(v) for v in iz["kutu"])
            renk = _RENKLER.get(iz["tip"], (180, 180, 180))
            kalinlik = 2 if iz["tip"] == "bardak" else 1
            cv2.rectangle(gorsel, (x1, y1), (x2, y2), renk, kalinlik)
            if iz["tip"] == "bardak":
                cv2.putText(
                    gorsel,
                    f"bardak #{iz['takip_id']}",
                    (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    renk,
                    1,
                    cv2.LINE_AA,
                )

        tamam, jpeg = cv2.imencode(".jpg", gorsel, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if tamam:
            with self._kilit:
                self._son_jpeg = jpeg.tobytes()


def ornek_video_uret(hedef: Path) -> None:
    """Kaynak yoksa ekranın boş kalmaması için bilgi videosu."""
    hedef.parent.mkdir(parents=True, exist_ok=True)
    yazici = cv2.VideoWriter(str(hedef), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
    for _ in range(60):
        kare = np.full((360, 640, 3), 45, dtype=np.uint8)
        cv2.putText(
            kare,
            "Kamera baglanmadi - .env icindeki KAYNAK satirina bakin",
            (30, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
            cv2.LINE_AA,
        )
        yazici.write(kare)
    yazici.release()
