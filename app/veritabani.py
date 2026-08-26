"""SQLite bağlantısı, şema ve ekrandan değiştirilen ayarlar (bölgeler)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SEMA_DOSYASI = Path(__file__).resolve().parent / "sema.sql"

VARSAYILAN_AYARLAR = {
    # Bölgeler normalize (0-1) poligon listesi olarak JSON saklanır
    "bolge_musteri": "[]",
    "bolge_barista": "[]",
    # Tespit hassasiyeti: bardak küçük bir nesnedir, araç/insan kadar kolay
    # görülmez. Düşük değer daha çok bardak yakalar ama yanlış tespiti artırır.
    # Ekrandan ayarlanır; sistem yeniden başlamaz.
    "tespit_hassasiyeti": "0.30",
}

HASSASIYET_EN_AZ = 0.15
HASSASIYET_EN_COK = 0.90


class VeritabaniHatasi(Exception):
    pass


def baglanti_ac(yol: Path | str) -> sqlite3.Connection:
    try:
        baglanti = sqlite3.connect(str(yol), check_same_thread=False)
        baglanti.row_factory = sqlite3.Row
        baglanti.execute("PRAGMA foreign_keys = ON")
        baglanti.execute("PRAGMA journal_mode = WAL")
        baglanti.execute("PRAGMA busy_timeout = 5000")
    except sqlite3.Error as hata:
        raise VeritabaniHatasi(
            f"Veritabanı açılamadı: {yol} — {hata}. Dosya bozuksa silip "
            "sistemi yeniden başlatabilirsiniz (demo verisi kaybolur)."
        ) from hata
    return baglanti


def semayi_uygula(baglanti: sqlite3.Connection) -> None:
    try:
        baglanti.executescript("BEGIN;\n" + SEMA_DOSYASI.read_text(encoding="utf-8") + "\nCOMMIT;")
    except sqlite3.Error as hata:
        baglanti.rollback()
        raise VeritabaniHatasi(f"Şema uygulanamadı: {hata}") from hata
    for anahtar, deger in VARSAYILAN_AYARLAR.items():
        baglanti.execute(
            "INSERT OR IGNORE INTO ayar (anahtar, deger) VALUES (?, ?)", (anahtar, deger)
        )
    baglanti.commit()


def ayarlari_oku(baglanti: sqlite3.Connection) -> dict[str, str]:
    return {s["anahtar"]: s["deger"] for s in baglanti.execute("SELECT * FROM ayar")}


def ayar_yaz(baglanti: sqlite3.Connection, anahtar: str, deger: str) -> None:
    baglanti.execute(
        "INSERT INTO ayar (anahtar, deger) VALUES (?, ?) "
        "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
        (anahtar, str(deger)),
    )
    baglanti.commit()


def bolgeleri_oku(baglanti: sqlite3.Connection) -> dict[str, list[tuple[float, float]]]:
    """Bozuk kayıtta boş bölge döner — analiz çökmez, ekran 'bölge yok' der."""
    ayarlar = ayarlari_oku(baglanti)
    bolgeler: dict[str, list[tuple[float, float]]] = {}
    for ad, anahtar in (("musteri", "bolge_musteri"), ("barista", "bolge_barista")):
        try:
            noktalar = json.loads(ayarlar.get(anahtar) or "[]")
            bolgeler[ad] = [(float(x), float(y)) for x, y in noktalar]
        except (json.JSONDecodeError, TypeError, ValueError):
            bolgeler[ad] = []
    return bolgeler
