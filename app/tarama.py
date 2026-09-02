"""Kare kare tarama: yüklenen görüntülerde nesne arama.

Kameradan aldığın kareleri (ya da telefonla çektiğin fotoğrafları) buraya
yükleyip test edebilirsin. Her görüntü için:
  1. Model bilinen sınıfları bulur (bardak, kişi …)
  2. Bulunan her kutu, kütüphanendeki nesnelerle karşılaştırılır
  3. Sonuç işaretlenmiş görüntü + sayım tablosu olarak döner

Canlı analizden BAĞIMSIZDIR: kamera bağlı olmasa da çalışır, sayaçlara
dokunmaz. Amaç denemek ve ayar yapmaktır.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.kutuphane import VARSAYILAN_ESIK, Nesne, en_iyi_eslesme
from app.tespit import YENIDEN_BASLATMA_ONERISI, Tespitci

# Model açılamadığında tarama sonucunun altında görünen uyarı.
# Buraya hangi KADEME'nin (Hızlı/İsabetli) açılamadığı gelmez: tara() ayarları
# görmez, yalnızca "model yok mu" bilgisini alır. Bu yüzden marka kademesiz
# yazılır. Yapılacak adım, diğer iki ekrandakiyle AYNI cümledir — kullanıcı üç
# ayrı ekranda üç ayrı çözüm okumasın.
MODEL_YOK_UYARISI = (
    f"NextGen AI hazır değil; bu yüzden tarama yapılamadı. {YENIDEN_BASLATMA_ONERISI}"
)

# İşaretli sonuç görüntüsünde kullanılan renkler (BGR)
_RENK_EŞLESEN = (60, 190, 90)
_RENK_TESPIT = (60, 170, 255)


@dataclass
class TaramaBulgusu:
    tip: str  # modelin sınıfı (bardak/kisi/arac…)
    guven: float
    nesne_adi: str | None  # kütüphaneden eşleşen nesne
    skor: float  # eşleşme skoru (0-1)
    kutu: tuple[int, int, int, int]


@dataclass
class TaramaSonucu:
    dosya_adi: str
    sonuc_gorseli: str  # veri/taramalar altına göreli ad
    bulgular: list[TaramaBulgusu]
    uyari: str = ""

    @property
    def eslesen_sayisi(self) -> int:
        return sum(1 for b in self.bulgular if b.nesne_adi)


def tara(
    gorsel: np.ndarray,
    dosya_adi: str,
    tespitci: Tespitci | None,
    nesneler: list[Nesne],
    hedef_klasor: Path,
    esik: float = VARSAYILAN_ESIK,
) -> TaramaSonucu:
    """Tek bir görüntüyü tarar ve işaretlenmiş sonucu diske yazar."""
    if tespitci is None:
        return TaramaSonucu(
            dosya_adi=dosya_adi,
            sonuc_gorseli=_gorseli_yaz(gorsel, hedef_klasor),
            bulgular=[],
            uyari=MODEL_YOK_UYARISI,
        )

    kutular, guvenler, tipler = tespitci.bul(gorsel)
    isaretli = gorsel.copy()
    bulgular: list[TaramaBulgusu] = []

    for kutu, guven, tip in zip(kutular, guvenler, tipler, strict=True):
        x1, y1, x2, y2 = (int(v) for v in kutu)
        kirpik = gorsel[max(y1, 0) : y2, max(x1, 0) : x2]
        nesne, skor = en_iyi_eslesme(kirpik, nesneler, esik) if nesneler else (None, 0.0)
        bulgular.append(
            TaramaBulgusu(
                tip=tip,
                guven=float(guven),
                nesne_adi=nesne.ad if nesne else None,
                skor=round(float(skor), 2),
                kutu=(x1, y1, x2, y2),
            )
        )
        renk = _RENK_EŞLESEN if nesne else _RENK_TESPIT
        etiket = f"{nesne.ad} %{skor * 100:.0f}" if nesne else f"{tip} %{guven * 100:.0f}"
        cv2.rectangle(isaretli, (x1, y1), (x2, y2), renk, 2)
        cv2.putText(
            isaretli,
            etiket,
            (x1, max(y1 - 6, 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            renk,
            1,
            cv2.LINE_AA,
        )

    uyari = ""
    if not bulgular:
        uyari = (
            "Bu karede tanınan bir nesne bulunamadı. Hassasiyeti düşürmeyi, "
            "kamerayı yaklaştırmayı ya da daha aydınlık bir kare denemeyi deneyin."
        )
    elif nesneler and not any(b.nesne_adi for b in bulgular):
        uyari = (
            "Nesneler bulundu ama kütüphanendeki hiçbir nesneyle eşleşmedi. "
            "Nesnenin bu açıdan da bir fotoğrafını kütüphaneye eklemeyi deneyin."
        )
    return TaramaSonucu(
        dosya_adi=dosya_adi,
        sonuc_gorseli=_gorseli_yaz(isaretli, hedef_klasor),
        bulgular=bulgular,
        uyari=uyari,
    )


def _gorseli_yaz(gorsel: np.ndarray, klasor: Path) -> str:
    klasor.mkdir(parents=True, exist_ok=True)
    ad = f"tarama-{uuid.uuid4().hex[:10]}.jpg"
    cv2.imwrite(str(klasor / ad), gorsel, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return ad


def eski_taramalari_temizle(klasor: Path, en_fazla: int = 60) -> None:
    """Tarama çıktıları birikmesin: en yeni N tanesi kalır."""
    if not klasor.is_dir():
        return
    dosyalar = sorted(klasor.glob("tarama-*.jpg"), key=lambda d: d.stat().st_mtime, reverse=True)
    for eski in dosyalar[en_fazla:]:
        eski.unlink(missing_ok=True)
