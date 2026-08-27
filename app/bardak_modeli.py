"""Bardak doğrulayıcı: "dedektörün bulduğu bu kutu BİZİM bardağımız mı?"

Neden böyle: hazır YOLOX modeli COCO'nun genel "cup/wine glass" sınıflarını
bilir, kafenin kendi bardaklarını bilmez. Modelin kendisini yeniden eğitmek
torch ister; bu projede torch YOKTUR ve eklenmez. Onun yerine kardeş projede
(DALSAN-ISG forklift) çalışan iki aşamalı desen kurulur:

    YOLOX aday kutuyu bulur  →  küçük sınıflandırıcı "bizim bardağımız mı?" der

Sınıflandırıcı, kullanıcının Bardak Eğitimi sayfasından yüklediği ve
etiketlediği görüntülerle eğitilir (app/egitim.py).

ÜÇ DURUM: bardak / değil / belirsiz. Karar bandının ortasına düşen kırpık
"belirsiz"dir ve sayımı DEĞİŞTİRMEZ — uydurma karar üretilmez.

MODEL YOKSA SİSTEM BUGÜNKÜ GİBİ ÇALIŞIR: tek bir davranış bile değişmez.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np


def _log() -> logging.Logger:
    return logging.getLogger("laffogato.bardak_modeli")


BARDAK = "bardak"
DEGIL = "degil"
BELIRSIZ = "belirsiz"

# --- Kırpma ve öznitelik SÖZLEŞMESİ ---------------------------------------
# Toplama, eğitim ve canlı çıkarım BU fonksiyonları kullanır. Sözleşmenin iki
# yerde ayrı ayrı yazılması, sebebi bulunamayan isabet kaybının klasik
# kaynağıdır; bu yüzden tek yerde durur.
KIRPMA_PAYI = 0.08  # kutunun her kenarına oranla pay
GRI_BOY = 8  # 8x8 gri  = 64 sayı
TON_GOZ, DOYGUNLUK_GOZ = 12, 4  # 12x4 renk = 48 sayı
# 64 + 48 + 2 (biçim) = 114 sayı. Bilerek KÜÇÜK: örnek sayısı birkaç yüzken
# binlerce öznitelik, modelin öğrenmek yerine ezberlemesi demektir.
OZNITELIK_BOYU = GRI_BOY * GRI_BOY + TON_GOZ * DOYGUNLUK_GOZ + 2


def bardak_kirp(kare: np.ndarray, kutu: tuple[float, float, float, float]) -> np.ndarray | None:
    """Aday kutuyu sözleşmeye göre kırpar. Kutu çok küçük/bozuksa None."""
    if kare is None or kare.size == 0:
        return None
    x1, y1, x2, y2 = (float(v) for v in kutu)
    pay_x = (x2 - x1) * KIRPMA_PAYI
    pay_y = (y2 - y1) * KIRPMA_PAYI
    x1 = max(0, int(x1 - pay_x))
    y1 = max(0, int(y1 - pay_y))
    x2 = min(kare.shape[1], int(x2 + pay_x))
    y2 = min(kare.shape[0], int(y2 + pay_y))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return kare[y1:y2, x1:x2]


def oznitelik(kirpik: np.ndarray) -> np.ndarray:
    """Kırpık → 114 sayılık öznitelik vektörü (float32).

    Üç kanıt: kaba biçim (gri 8x8), renk dağılımı (HS histogramı) ve
    en-boy oranı. Hepsi ölçekten bağımsızdır; tavandaki kameranın 40
    piksellik kırpığı ile telefon fotoğrafı aynı uzaya iner.
    """
    gri = cv2.cvtColor(kirpik, cv2.COLOR_BGR2GRAY)
    kucuk = cv2.resize(gri, (GRI_BOY, GRI_BOY), interpolation=cv2.INTER_AREA)
    # Parlaklığa dayanıklılık: kırpığın kendi ortalamasına göre normalize
    kucuk = kucuk.astype(np.float32)
    kucuk = (kucuk - kucuk.mean()) / (kucuk.std() + 1e-6)

    hsv = cv2.cvtColor(kirpik, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [TON_GOZ, DOYGUNLUK_GOZ], [0, 180, 0, 256])
    toplam = float(histogram.sum())
    histogram = (histogram / toplam) if toplam > 0 else histogram

    yukseklik, genislik = kirpik.shape[:2]
    en_boy = genislik / max(yukseklik, 1)
    bicim = np.array([en_boy, min(en_boy, 3.0) / 3.0], dtype=np.float32)

    return np.concatenate([kucuk.flatten(), histogram.flatten().astype(np.float32), bicim]).astype(
        np.float32
    )


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


class BardakModeli:
    """models/bardak/aktif.json'daki devredeki modeli yükler ve uygular.

    Eğitim, çalışan sistemi durdurmadan yeni sürümü devreye alabilsin diye
    `gerekirse_yenile` aktif.json değişince modeli yeniden yükler.
    """

    def __init__(self, klasor: Path) -> None:
        self._klasor = Path(klasor)
        self._damga: float | None = None
        self.model_var = False
        self.surum = ""
        self.alt_esik = 0.40
        self.ust_esik = 0.60
        self._w: np.ndarray | None = None
        self._b = 0.0
        self._ortalama: np.ndarray | None = None
        self._sapma: np.ndarray | None = None
        self._yukle()

    def gerekirse_yenile(self) -> None:
        aktif = self._klasor / "aktif.json"
        try:
            damga = aktif.stat().st_mtime if aktif.exists() else None
        except OSError:
            damga = None
        if damga != self._damga:
            self._yukle()

    def olasilik(self, x: np.ndarray) -> np.ndarray:
        """(n, 114) öznitelik matrisi → her satır için 'bardak' olasılığı."""
        return sigmoid(((x - self._ortalama) / self._sapma) @ self._w + self._b)

    def karar(self, kirpik: np.ndarray) -> tuple[str, float]:
        """Kırpık → (bardak|degil|belirsiz, olasılık). Model yoksa belirsiz."""
        if not self.model_var or kirpik is None or kirpik.size == 0:
            return BELIRSIZ, 0.0
        p = float(self.olasilik(oznitelik(kirpik)[np.newaxis])[0])
        if p >= self.ust_esik:
            return BARDAK, p
        if p <= self.alt_esik:
            return DEGIL, p
        return BELIRSIZ, p

    # ---- iç ----

    def _yukle(self) -> None:
        aktif = self._klasor / "aktif.json"
        self.model_var = False
        try:
            self._damga = aktif.stat().st_mtime if aktif.exists() else None
            if not aktif.exists():
                return  # model henüz eğitilmedi — normal durum, sessiz
            bilgi = json.loads(aktif.read_text(encoding="utf-8"))
            self.surum = str(bilgi["surum"])
            self.alt_esik = float(bilgi["alt_esik"])
            self.ust_esik = float(bilgi["ust_esik"])
            veri = np.load(self._klasor / f"{self.surum}.npz")
            w = veri["w"]
            if w.shape != (OZNITELIK_BOYU,):
                raise ValueError(f"ağırlık boyutu beklenenden farklı: {w.shape}")
            self._w = w
            self._b = float(veri["b"])
            self._ortalama = veri["ortalama"]
            self._sapma = veri["sapma"]
            self.model_var = True
            _log().info(f"Bardak modeli devrede: {self.surum}")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as hata:
            # Bozuk model sistemi durdurmaz: doğrulayıcı devre dışı kalır ve
            # sayım bugünkü davranışına döner.
            _log().error(f"Bardak modeli yüklenemedi ({self._klasor}): {hata}")
