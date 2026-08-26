"""Analiz iş parçacığı: kamera → tespit → takip → bardak kararı → kayıt.

Sayım ilkesi: her BENZERSİZ bardak takibi günde bir kez sayılır. Bardak
kadrajdan çıkınca (birkaç saniye görünmeyince) "kime gitti" kararı verilir
ve kaydedilir; bu yüzden sayılar birkaç saniye gecikmeyle görünür.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import supervision as sv  # noqa: E402

from app import veritabani, zaman  # noqa: E402
from app.ayarlar import Ayarlar  # noqa: E402
from app.bardak import BARISTA, MUSTERI, BardakDurumu, bolge_bul  # noqa: E402
from app.tespit import ModelHatasi, Tespitci  # noqa: E402

# Bardak bu kadar ardışık değerlendirmede görünmezse "gitti" sayılır ve
# kararı kesinleşir (kısa örtülmeler kararı bölmesin diye sabırlı davranırız).
_KAYIP_ESIGI = 12

_RENKLER = {"bardak": (60, 190, 255), "kisi": (150, 150, 150)}
_BOLGE_RENKLERI = {MUSTERI: (90, 200, 90), BARISTA: (200, 140, 60)}


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

    # ---- yaşam döngüsü ----

    def baslat(self) -> None:
        self._is.start()

    def durdur(self) -> None:
        self._dur.set()
        self._is.join(timeout=8)

    def onizleme(self) -> bytes | None:
        with self._kilit:
            return self._son_jpeg

    @property
    def kare_boyutu(self) -> tuple[int, int]:
        return self._kare_boyutu

    def sayaclari_sifirla(self) -> None:
        self._acik.clear()
        self._kayip.clear()

    # ---- ana döngü ----

    def _dongu(self) -> None:
        baglanti = veritabani.baglanti_ac(self.ayarlar.veritabani)
        try:
            self._tespitci = Tespitci(self.ayarlar.model_dosyasi, self.ayarlar.cihaz)
        except ModelHatasi as hata:
            self.model_hatasi = str(hata)
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
        yakalayici = (
            cv2.VideoCapture(kaynak)
            if isinstance(kaynak, int)
            else cv2.VideoCapture(kaynak, cv2.CAP_FFMPEG)
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
        dosya_mi = isinstance(kaynak, str) and not kaynak.lower().startswith("rtsp")
        while not self._dur.is_set():
            basla = time.monotonic()
            tamam, kare = yakalayici.read()
            if not tamam:
                if dosya_mi:
                    yakalayici.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                return  # canlı akış koptu → yeniden bağlan
            self._kare_boyutu = (kare.shape[1], kare.shape[0])
            try:
                self._kareyi_degerlendir(kare, baglanti)
            except Exception as hata:  # noqa: BLE001 — demo döngüsü ölmemeli
                self.durum = f"hata: {hata}"
            if self._dur.wait(max(0.0, aralik - (time.monotonic() - basla))):
                return

    def _kareyi_degerlendir(self, kare: np.ndarray, baglanti) -> None:
        self._bolgeler = veritabani.bolgeleri_oku(baglanti)
        if self._tespitci is None:
            self._onizleme_yaz(kare, [])
            return
        self._hassasiyeti_uygula(baglanti)

        kutular, guvenler, tipler = self._tespitci.bul(kare)
        izler = self._takip_et(kutular, guvenler, tipler)
        bardaklar = [i for i in izler if i["tip"] == "bardak"]
        self.canli_bardak = len(bardaklar)
        self.canli_kisi = sum(1 for i in izler if i["tip"] == "kisi")

        self._bardaklari_izle(bardaklar, kare, baglanti)
        self._onizleme_yaz(kare, izler)

    def _izleyici_kur(self, hassasiyet: float) -> sv.ByteTrack:
        """ByteTrack'i tespit hassasiyetine göre kurar.

        KRİTİK: ByteTrack, aktivasyon eşiğinin ALTINDA kalan tespitlerle yeni
        iz BAŞLATMAZ. Eşik tespit hassasiyetiyle aynı olursa (ör. ikisi de
        0,30) bardak her karede tespit edilse bile hiç takip edilmez ve
        sayaç sıfırda kalır. Bu yüzden aktivasyon, hassasiyetin belirgin
        şekilde altında tutulur.
        """
        return sv.ByteTrack(
            track_activation_threshold=max(0.10, hassasiyet * 0.6),
            # Bardak elle kapatılıp tekrar görünebilir; izi çabuk düşürme
            lost_track_buffer=60,
            frame_rate=max(int(self.ayarlar.kare_fps), 1),
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
        # Takipçi eşiği hassasiyete bağlı: yeniden kurulur (takip numaraları
        # sıfırlanır, o an ekranda olan bardaklar yeniden sayılabilir)
        self._izleyici = self._izleyici_kur(deger)

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
        genislik, yukseklik = self._kare_boyutu
        gorulenler = set()

        for bardak in bardaklar:
            takip_id = bardak["takip_id"]
            gorulenler.add(takip_id)
            x1, y1, x2, y2 = bardak["kutu"]
            merkez = ((x1 + x2) / 2 / genislik, (y1 + y2) / 2 / yukseklik)
            bolge = bolge_bul(merkez, self._bolgeler)

            durum = self._acik.get(takip_id)
            if durum is None:
                durum = BardakDurumu(takip_id=takip_id, ilk_zaman=simdi, son_zaman=simdi)
                durum.foto = self._kirpik_kaydet(kare, bardak["kutu"])
                self._acik[takip_id] = durum
            durum.gozlem_ekle(bolge, simdi)
            self._kayip.pop(takip_id, None)

        # Görünmeyen bardaklar: yeterince beklendiyse kararı kesinleştir
        for takip_id in list(self._acik):
            if takip_id in gorulenler:
                continue
            self._kayip[takip_id] = self._kayip.get(takip_id, 0) + 1
            if self._kayip[takip_id] < _KAYIP_ESIGI:
                continue
            durum = self._acik.pop(takip_id)
            self._kayip.pop(takip_id, None)
            if durum.sayilir_mi():
                self._bardagi_kaydet(baglanti, durum)

    def _bardagi_kaydet(self, baglanti, durum: BardakDurumu) -> None:
        baglanti.execute(
            "INSERT OR IGNORE INTO bardaklar "
            "(gun, takip_id, baslangic, bitis, kime, musteri_gozlem, barista_gozlem, foto) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                zaman.bugun(),
                durum.takip_id,
                durum.ilk_zaman,
                durum.son_zaman,
                durum.karar(),
                durum.bolge_sayaci.get(MUSTERI, 0),
                durum.bolge_sayaci.get(BARISTA, 0),
                durum.foto,
            ),
        )
        baglanti.commit()

    def _kirpik_kaydet(self, kare: np.ndarray, kutu) -> str | None:
        x1, y1, x2, y2 = (int(v) for v in kutu)
        pay = 10
        x1, y1 = max(x1 - pay, 0), max(y1 - pay, 0)
        x2 = min(x2 + pay, kare.shape[1])
        y2 = min(y2 + pay, kare.shape[0])
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        ad = f"bardak-{zaman.bugun()}-{uuid.uuid4().hex[:8]}.jpg"
        try:
            cv2.imwrite(str(self.ayarlar.goruntu_klasoru / ad), kare[y1:y2, x1:x2])
        except (OSError, cv2.error):
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
            renk = _RENKLER[iz["tip"]]
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
