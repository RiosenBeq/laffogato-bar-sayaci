"""Nesne tespiti: YOLOX (Apache-2.0) + ONNX Runtime — torch gerekmez."""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

# COCO sınıfı → bizim tip. Bar alanında ilgilendiğimiz her şey burada.
# NOT: Hazır model "kahve fincanı"nı ayrı bir sınıf olarak bilmez; cup (41) ve
# wine glass (40) sınıfları bardak olarak sayılır. Kafenin kendi bardaklarıyla
# ince ayar yapılırsa isabet belirgin şekilde artar — demo bunu vaat etmez.
SINIF_ESLEME: dict[int, str] = {
    0: "kisi",
    39: "bardak",  # şişe biçimli takeaway bardaklar
    40: "bardak",  # kadeh / cam bardak
    41: "bardak",  # fincan / kupa
}


# Seramik fincan/kupa COCO'da sık sık "bowl" ya da "vase" olarak çıkar ve
# bugün SESSİZCE atılır. Bu sınıflar YALNIZCA eğitilmiş bardak doğrulayıcı
# devredeyken sayıma girer (genis_aday=True); model yokken sistem bugünkü
# davranışını birebir korur. Aynı "bardak" tipine eşlendikleri için NMS'te
# aynı uzaya düşerler — bir fincan iki kez sayılmaz.
# Bu sınıflar "aday" tipiyle döner, "bardak" ile DEĞİL: doğrulayıcı bunlara
# AÇIKÇA "bardak" demedikçe sayıma girmezler. Aksi halde tezgâhtaki seramik
# şeker kâsesi, model ona "belirsiz" dediğinde bardak olarak sayılırdı.
GENIS_ADAY_ESLEME: dict[int, str] = {45: "aday", 75: "aday"}

# Eğitim verisi toplarken taranan aday sınıflar (bardak olabilecek her şey).
# Geniş tutulur ki kullanıcı hem bardakları hem "bardak değil" örneklerini
# etiketleyebilsin.
TOPLAMA_SINIFLARI: dict[int, str] = {**SINIF_ESLEME, **GENIS_ADAY_ESLEME}
# Eğitim verisi ve canlı doğrulama için "bardak olabilecek" tipler
BARDAK_TIPLERI = ("bardak", "aday")

# Kişi (COCO 0) eşiği çarpanı ve gürültü kutusu alt sınırı
KISI_ESIK_CARPANI = 0.8
EN_KUCUK_KENAR_PX = 6


class ModelHatasi(Exception):
    pass


class Tespitci:
    def __init__(self, model_dosyasi: Path, cihaz: str = "cpu", guven: float = 0.35) -> None:
        import onnxruntime

        if not model_dosyasi.exists():
            raise ModelHatasi(
                f"Tespit modeli bulunamadı: {model_dosyasi}\n"
                "Çözüm: proje klasöründe 'bash models/indir.sh' komutunu çalıştırın."
            )
        saglayicilar = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if cihaz == "cuda"
            else ["CPUExecutionProvider"]
        )
        try:
            self._oturum = onnxruntime.InferenceSession(str(model_dosyasi), providers=saglayicilar)
        except Exception as hata:
            raise ModelHatasi(
                f"Model yüklenemedi ({model_dosyasi.name}): {hata}. "
                "Dosya bozuk olabilir, models/indir.sh ile yeniden indirin."
            ) from hata
        girdi = self._oturum.get_inputs()[0]
        self._girdi_adi = girdi.name
        self._boy = int(girdi.shape[2])
        self.guven = guven
        # Geniş aday kipi: bardak doğrulayıcı devredeyken bowl/vase de aday
        # sayılır. Varsayılan KAPALI — model yokken davranış değişmez.
        self.genis_aday = False
        self._kilit = threading.Lock()

    def bul(self, kare: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """BGR kare → (kutular_xyxy, güvenler, tipler['kisi'|'bardak'])."""
        girdi, oran = self._on_isle(kare)
        with self._kilit:
            cikti = self._oturum.run(None, {self._girdi_adi: girdi})[0]
        return self._son_isle(cikti[0], oran, kare.shape[1], kare.shape[0])

    def adaylari_bul(
        self, kare: np.ndarray, guven: float = 0.20
    ) -> list[tuple[tuple[float, float, float, float], float, int]]:
        """Eğitim verisi toplamak için: bardak OLABİLECEK her aday kutu.

        Canlı sayımdan bağımsızdır ve eşiği bilerek düşüktür — kullanıcı
        zayıf tespitleri de etiketleyebilsin. Döner: [(kutu, güven, coco_id)].
        """
        eski_guven, eski_genis = self.guven, self.genis_aday
        self.guven, self.genis_aday = guven, True
        try:
            girdi, oran = self._on_isle(kare)
            with self._kilit:
                cikti = self._oturum.run(None, {self._girdi_adi: girdi})[0]
            kutular, guvenler, tipler = self._son_isle(cikti[0], oran, kare.shape[1], kare.shape[0])
        finally:
            self.guven, self.genis_aday = eski_guven, eski_genis

        # Sınıf numarası _son_isle'dan dönmüyor; kutuları yeniden eşlemek yerine
        # COCO bardak sınıfı bilgisini kutu boyutundan DEĞİL, ikinci bir hızlı
        # geçişle alırız: burada yalnızca "bugünkü sayım bunu bardak sayar mıydı"
        # bilgisi gerekiyor, o da dar eşlemeyle aynı kareyi taramaktır.
        dar_kutular, _, dar_tipler = self.bul(kare)
        adaylar = []
        for kutu, g, tip in zip(kutular, guvenler, tipler, strict=True):
            # Yalnızca BARDAK OLABİLECEK kutular. Kişi kutuları da negatif
            # örnek olurdu ama fazlasıyla kolay ayırt edilir; kullanıcının
            # etiketleme emeği bardağa benzeyen kutulara harcanmalı.
            if tip not in BARDAK_TIPLERI:
                continue
            coco_bardak = any(
                t == "bardak" and _ortusuyor(kutu, dk)
                for dk, t in zip(dar_kutular, dar_tipler, strict=True)
            )
            adaylar.append((tuple(float(v) for v in kutu), float(g), 1 if coco_bardak else 0))
        return adaylar

    def _on_isle(self, kare: np.ndarray) -> tuple[np.ndarray, float]:
        dolgulu = np.full((self._boy, self._boy, 3), 114, dtype=np.uint8)
        oran = min(self._boy / kare.shape[0], self._boy / kare.shape[1])
        yeni = (int(kare.shape[1] * oran), int(kare.shape[0] * oran))
        dolgulu[: yeni[1], : yeni[0]] = cv2.resize(kare, yeni, interpolation=cv2.INTER_LINEAR)
        girdi = dolgulu.transpose(2, 0, 1).astype(np.float32)[np.newaxis]
        return np.ascontiguousarray(girdi), oran

    def _son_isle(self, cikti, oran, kare_g, kare_y):
        izgaralar, adimlar = [], []
        for adim in (8, 16, 32):
            kenar = self._boy // adim
            xv, yv = np.meshgrid(np.arange(kenar), np.arange(kenar))
            izgara = np.stack((xv, yv), 2).reshape(-1, 2)
            izgaralar.append(izgara)
            adimlar.append(np.full((izgara.shape[0], 1), adim))
        izgaralar = np.concatenate(izgaralar, 0)
        adimlar = np.concatenate(adimlar, 0)

        cikti = cikti.copy()
        cikti[:, :2] = (cikti[:, :2] + izgaralar) * adimlar
        cikti[:, 2:4] = np.exp(cikti[:, 2:4]) * adimlar

        skorlar = cikti[:, 4:5] * cikti[:, 5:]
        sinif_idler = skorlar.argmax(1)
        guvenler = skorlar[np.arange(len(skorlar)), sinif_idler]

        # Kişiler sahnede küçük/kısmen örtülü görünür; eşiği biraz daha cömert
        # tutmak kaçan kişileri azaltır (yanlış pozitifler NMS + takip ile elenir)
        sinif_esikleri = np.where(sinif_idler == 0, self.guven * KISI_ESIK_CARPANI, self.guven)
        esleme = {**SINIF_ESLEME, **GENIS_ADAY_ESLEME} if self.genis_aday else SINIF_ESLEME
        maske = (guvenler >= sinif_esikleri) & np.isin(sinif_idler, list(esleme))
        bos = (np.empty((0, 4)), np.empty((0,)), np.empty((0,), dtype=object))
        if not maske.any():
            return bos

        merkez = cikti[maske, :4] / oran
        guvenler, sinif_idler = guvenler[maske], sinif_idler[maske]
        kutular = np.empty_like(merkez)
        kutular[:, 0] = (merkez[:, 0] - merkez[:, 2] / 2).clip(0, kare_g)
        kutular[:, 1] = (merkez[:, 1] - merkez[:, 3] / 2).clip(0, kare_y)
        kutular[:, 2] = (merkez[:, 0] + merkez[:, 2] / 2).clip(0, kare_g)
        kutular[:, 3] = (merkez[:, 1] + merkez[:, 3] / 2).clip(0, kare_y)

        # Birkaç pikselden küçük kutular gürültüdür; takibe girmeden elensin
        genislikler = kutular[:, 2] - kutular[:, 0]
        yukseklikler = kutular[:, 3] - kutular[:, 1]
        boyut_maskesi = (genislikler >= EN_KUCUK_KENAR_PX) & (yukseklikler >= EN_KUCUK_KENAR_PX)
        if not boyut_maskesi.any():
            return bos
        kutular = kutular[boyut_maskesi]
        guvenler, sinif_idler = guvenler[boyut_maskesi], sinif_idler[boyut_maskesi]

        # Tip-bilinçli NMS: kutular TİP başına ayrı uzaya kaydırılır. Aynı tipe
        # eşlenen sınıflar (örn. otomobil+kamyon → arac) birbirini bastırabilsin
        # ki aynı nesne iki sınıf olarak çift sayılmasın; farklı tipler
        # (kişi vs diğer) ise birbirini bastırmasın.
        tip_indeksleri = np.where(sinif_idler == 0, 0.0, 1.0)
        kaydirma = tip_indeksleri[:, None] * (max(kare_g, kare_y) + 1.0)
        nms_kutulari = kutular + kaydirma
        secilen = cv2.dnn.NMSBoxes(
            [(x1, y1, x2 - x1, y2 - y1) for x1, y1, x2, y2 in nms_kutulari.tolist()],
            guvenler.tolist(),
            self.guven * KISI_ESIK_CARPANI,  # sınıf eşiği zaten uygulandı
            0.45,
        )
        if len(secilen) == 0:
            return bos
        secilen = np.array(secilen).reshape(-1)
        tipler = np.array([esleme[int(s)] for s in sinif_idler[secilen]], dtype=object)
        return kutular[secilen], guvenler[secilen], tipler


def _ortusuyor(a, b, esik: float = 0.6) -> bool:
    """İki kutu büyük ölçüde aynı yeri mi gösteriyor (IoU)?"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    kx1, ky1 = max(ax1, bx1), max(ay1, by1)
    kx2, ky2 = min(ax2, bx2), min(ay2, by2)
    if kx2 <= kx1 or ky2 <= ky1:
        return False
    kesisim = (kx2 - kx1) * (ky2 - ky1)
    birlesim = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - kesisim
    return birlesim > 0 and kesisim / birlesim >= esik
