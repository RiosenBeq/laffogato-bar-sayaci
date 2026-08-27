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
    egitim_klasoru: Path
    bardak_model_klasoru: Path
    panel_sifresi: str = ""  # boşsa giriş istenmez; doluysa panel şifreyle açılır

    def kaynak_cozumle(self):
        """OpenCV'ye verilecek kaynak: kamera numarası (int) veya yol/adres."""
        ham = self.kaynak.strip()
        if ham.isdigit():
            return int(ham)  # 0 = bilgisayarın kamerası
        aday = self.kok / ham
        return str(aday) if aday.exists() else ham


def kaynagi_kaydet(kok: Path, deger: str) -> None:
    """KAYNAK satırını .env dosyasına yazar; dosya yoksa örnekten oluşturur.

    Kullanıcı kaynağı artık ekrandan seçer — .env'i elle düzenlemesi gerekmez.
    """
    env = kok / ".env"
    ornek = kok / ".env.example"
    if not env.exists() and ornek.exists():
        env.write_text(ornek.read_text(encoding="utf-8"), encoding="utf-8")
    # Boşluk ya da # içeren değer tırnaklanmazsa dotenv yarıda keser
    yazim = f'"{deger}"' if any(k in deger for k in " #'") and '"' not in deger else deger
    satirlar = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    bulundu = False
    for i, satir in enumerate(satirlar):
        if satir.strip().startswith("KAYNAK="):
            # Yinelenen KAYNAK satırlarının HEPSİ değişmeli; dotenv sonuncuyu okur
            satirlar[i] = f"KAYNAK={yazim}"
            bulundu = True
    if not bulundu:
        satirlar.append(f"KAYNAK={yazim}")
    try:
        env.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    except OSError as hata:
        raise AyarHatasi(f".env dosyasına yazılamadı: {hata.strerror}") from hata


def _varsayilan_model(kok: Path) -> str:
    """MODEL_DOSYASI boşsa eldeki en isabetli model seçilir.

    yolox_s belirgin daha isabetlidir ve modern bir işlemcide hız bütçesine
    rahat sığar; yoksa yolox_tiny ile devam edilir.
    """
    aday = kok / "models/yolox_s.onnx"
    # Boyut denetimi: yarım kalmış bir indirme (gerçeği ~34 MB) seçilirse
    # model hiç yüklenemezdi; şüpheli dosya varken tiny ile devam edilir
    if aday.exists() and aday.stat().st_size > 30_000_000:
        return "models/yolox_s.onnx"
    return "models/yolox_tiny.onnx"


def yukle(kok: Path | None = None) -> Ayarlar:
    kok = (kok or KOK).resolve()
    env = kok / ".env"
    degerler = {a: (d or "").strip() for a, d in dotenv_values(env).items()} if env.exists() else {}

    veri = kok / "veri"
    goruntuler = veri / "goruntuler"
    nesneler = veri / "nesneler"
    taramalar = veri / "taramalar"
    # Bardak Eğitimi: yüklenen görüntülerden çıkarılan aday kırpıklar
    egitim = veri / "egitim"
    for klasor in (veri, goruntuler, nesneler, taramalar, egitim):
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
        model_dosyasi=kok / (degerler.get("MODEL_DOSYASI") or _varsayilan_model(kok)),
        cihaz=cihaz,
        veritabani=veri / "laffogato.db",
        goruntu_klasoru=goruntuler,
        nesne_klasoru=nesneler,
        tarama_klasoru=taramalar,
        egitim_klasoru=egitim,
        # Eğitilen bardak doğrulayıcının sürümlü model klasörü
        bardak_model_klasoru=kok / "models" / "bardak",
        panel_sifresi=degerler.get("PANEL_SIFRESI") or "",
    )
