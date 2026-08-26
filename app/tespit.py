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
        self._kilit = threading.Lock()

    def bul(self, kare: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """BGR kare → (kutular_xyxy, güvenler, tipler['kisi'|'bardak'])."""
        girdi, oran = self._on_isle(kare)
        with self._kilit:
            cikti = self._oturum.run(None, {self._girdi_adi: girdi})[0]
        return self._son_isle(cikti[0], oran, kare.shape[1], kare.shape[0])

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

        maske = (guvenler >= self.guven) & np.isin(sinif_idler, list(SINIF_ESLEME))
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

        secilen = cv2.dnn.NMSBoxes(
            [(x1, y1, x2 - x1, y2 - y1) for x1, y1, x2, y2 in kutular.tolist()],
            guvenler.tolist(),
            self.guven,
            0.45,
        )
        if len(secilen) == 0:
            return bos
        secilen = np.array(secilen).reshape(-1)
        tipler = np.array([SINIF_ESLEME[int(s)] for s in sinif_idler[secilen]], dtype=object)
        return kutular[secilen], guvenler[secilen], tipler
