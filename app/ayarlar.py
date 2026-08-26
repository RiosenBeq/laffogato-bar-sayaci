"""Ayarların tek kaynağı: kök klasördeki .env dosyası.

Bölgeler ve eşikler .env'de DEĞİL veritabanındadır — ekrandan değiştirilir,
sistem yeniden başlamaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

KOK = Path(__file__).resolve().parents[1]


class AyarHatasi(Exception):
    """Anlaşılır Türkçe mesajla açılışı durdurur."""


@dataclass(frozen=True)
class Ayarlar:
    kok: Path
    kaynak: str
    kare_fps: float
    model_dosyasi: Path
    cihaz: str
    veritabani: Path
    goruntu_klasoru: Path
    nesne_klasoru: Path
    tarama_klasoru: Path

    def kaynak_cozumle(self):
        """OpenCV'ye verilecek kaynak: kamera numarası (int) veya yol/adres."""
        ham = self.kaynak.strip()
        if ham.isdigit():
            return int(ham)  # 0 = bilgisayarın kamerası
        aday = self.kok / ham
        return str(aday) if aday.exists() else ham


def yukle(kok: Path | None = None) -> Ayarlar:
    kok = (kok or KOK).resolve()
    env = kok / ".env"
    degerler = {a: (d or "").strip() for a, d in dotenv_values(env).items()} if env.exists() else {}

    veri = kok / "veri"
    goruntuler = veri / "goruntuler"
    nesneler = veri / "nesneler"
    taramalar = veri / "taramalar"
    for klasor in (veri, goruntuler, nesneler, taramalar):
        try:
            klasor.mkdir(parents=True, exist_ok=True)
        except OSError as hata:
            raise AyarHatasi(f"{klasor} klasörü oluşturulamadı: {hata.strerror}") from hata

    ham_fps = degerler.get("KARE_FPS") or "4"
    try:
        kare_fps = float(ham_fps.replace(",", "."))
    except ValueError:
        raise AyarHatasi(
            f".env dosyasındaki KARE_FPS sayı olmalı; şu an '{ham_fps}' yazıyor."
        ) from None
    if not 0.2 <= kare_fps <= 15:
        raise AyarHatasi(f"KARE_FPS 0,2 ile 15 arasında olmalı; şu an {kare_fps:g}.")

    cihaz = degerler.get("CIHAZ") or "cpu"
    if cihaz not in ("cpu", "cuda"):
        raise AyarHatasi(f".env dosyasında CIHAZ 'cpu' veya 'cuda' olmalı; şu an '{cihaz}'.")

    return Ayarlar(
        kok=kok,
        kaynak=degerler.get("KAYNAK") or "0",
        kare_fps=kare_fps,
        model_dosyasi=kok / (degerler.get("MODEL_DOSYASI") or "models/yolox_tiny.onnx"),
        cihaz=cihaz,
        veritabani=veri / "laffogato.db",
        goruntu_klasoru=goruntuler,
        nesne_klasoru=nesneler,
        tarama_klasoru=taramalar,
    )
