"""Nesne kütüphanesinin veritabanı ve dosya işleri.

Fotoğraflar veri/nesneler/ altına yazılır; parmak izleri her açılışta
fotoğraflardan yeniden hesaplanır (kütüphane küçük olduğu için hızlıdır ve
veritabanında ikili veri tutmaktan daha sade).
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import cv2

from app import zaman
from app.kutuphane import Nesne, parmakizi_cikar

IZINLI_UZANTILAR = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
EN_BUYUK_DOSYA = 12 * 1024 * 1024  # 12 MB — telefon fotoğrafı rahat sığar


class NesneHatasi(Exception):
    """Kullanıcıya gösterilecek anlaşılır Türkçe hata."""


def nesne_ekle(baglanti: sqlite3.Connection, ad: str) -> int:
    ad = ad.strip()
    if not ad:
        raise NesneHatasi("Nesne adı boş olamaz (örn. 'Laffogato fincanı').")
    if len(ad) > 60:
        raise NesneHatasi("Nesne adı en fazla 60 karakter olabilir.")
    try:
        imlec = baglanti.execute(
            "INSERT INTO nesneler (ad, olusturuldu) VALUES (?, ?)", (ad, zaman.simdi_utc())
        )
    except sqlite3.IntegrityError:
        raise NesneHatasi(f"'{ad}' adında bir nesne zaten var.") from None
    baglanti.commit()
    return int(imlec.lastrowid)


def fotograf_ekle(
    baglanti: sqlite3.Connection, klasor: Path, nesne_id: int, dosya_adi: str, icerik: bytes
) -> str:
    """Yüklenen fotoğrafı doğrular, diske yazar, kayda geçer."""
    uzanti = Path(dosya_adi).suffix.lower()
    if uzanti not in IZINLI_UZANTILAR:
        raise NesneHatasi(f"'{dosya_adi}' desteklenmiyor. JPG, PNG veya WEBP fotoğraf yükleyin.")
    if len(icerik) > EN_BUYUK_DOSYA:
        raise NesneHatasi(f"'{dosya_adi}' çok büyük (en fazla 12 MB).")
    if baglanti.execute("SELECT 1 FROM nesneler WHERE id = ?", (nesne_id,)).fetchone() is None:
        raise NesneHatasi("Nesne bulunamadı; silinmiş olabilir.")

    ad = f"nesne{nesne_id}-{uuid.uuid4().hex[:8]}{uzanti}"
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = klasor / ad
    try:
        hedef.write_bytes(icerik)
    except OSError as hata:
        raise NesneHatasi(f"Fotoğraf kaydedilemedi: {hata.strerror}") from hata

    # Gerçekten okunabilir bir görüntü mü? (bozuk dosya kütüphaneyi kirletmesin)
    if cv2.imread(str(hedef)) is None:
        hedef.unlink(missing_ok=True)
        raise NesneHatasi(f"'{dosya_adi}' okunamadı; bozuk bir görüntü dosyası olabilir.")

    baglanti.execute(
        "INSERT INTO nesne_fotolari (nesne_id, dosya, eklendi) VALUES (?, ?, ?)",
        (nesne_id, ad, zaman.simdi_utc()),
    )
    baglanti.commit()
    return ad


def nesne_sil(baglanti: sqlite3.Connection, klasor: Path, nesne_id: int) -> None:
    for satir in baglanti.execute(
        "SELECT dosya FROM nesne_fotolari WHERE nesne_id = ?", (nesne_id,)
    ).fetchall():
        (klasor / satir["dosya"]).unlink(missing_ok=True)
    baglanti.execute("DELETE FROM nesneler WHERE id = ?", (nesne_id,))
    baglanti.commit()


def fotograf_sil(baglanti: sqlite3.Connection, klasor: Path, foto_id: int) -> None:
    satir = baglanti.execute("SELECT dosya FROM nesne_fotolari WHERE id = ?", (foto_id,)).fetchone()
    if satir is None:
        return
    (klasor / satir["dosya"]).unlink(missing_ok=True)
    baglanti.execute("DELETE FROM nesne_fotolari WHERE id = ?", (foto_id,))
    baglanti.commit()


def nesneleri_listele(baglanti: sqlite3.Connection) -> list[dict]:
    """Arayüz için: nesneler ve fotoğrafları."""
    nesneler = []
    for satir in baglanti.execute("SELECT * FROM nesneler ORDER BY ad"):
        fotolar = [
            {"id": f["id"], "dosya": f["dosya"], "eklendi": zaman.ekranda(f["eklendi"])}
            for f in baglanti.execute(
                "SELECT * FROM nesne_fotolari WHERE nesne_id = ? ORDER BY id", (satir["id"],)
            )
        ]
        nesneler.append({"id": satir["id"], "ad": satir["ad"], "fotolar": fotolar})
    return nesneler


def nesneleri_yukle(baglanti: sqlite3.Connection, klasor: Path) -> list[Nesne]:
    """Eşleştirme için parmak izleriyle birlikte nesneler."""
    nesneler: list[Nesne] = []
    for satir in baglanti.execute("SELECT * FROM nesneler ORDER BY id"):
        nesne = Nesne(id=satir["id"], ad=satir["ad"])
        for foto in baglanti.execute(
            "SELECT dosya FROM nesne_fotolari WHERE nesne_id = ?", (satir["id"],)
        ):
            gorsel = cv2.imread(str(klasor / foto["dosya"]))
            if gorsel is None:
                continue  # dosya silinmiş/bozuk — sessizce atla, kütüphane çalışsın
            izi = parmakizi_cikar(gorsel)
            if izi is not None:
                nesne.parmakizleri.append(izi)
        if nesne.parmakizleri:
            nesneler.append(nesne)
    return nesneler
