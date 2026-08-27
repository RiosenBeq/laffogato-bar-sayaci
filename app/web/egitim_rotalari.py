"""Bardak Eğitimi sayfası: kendi bardaklarını tanıt, etiketle, eğit.

Kullanıcı akışı (üç adım, hepsi bu sayfada):
  1. Bardaklarının fotoğraf/videolarını yükle — sistem her görüntüde aday
     kutuları bulup kırpar
  2. Her kırpığa üç düğmeden biriyle etiket ver
  3. "Eğitimi çalıştır" — eski ve yeni yöntem AYNI kırpıklarda karşılaştırılır,
     yeni model yalnızca daha iyiyse devreye alınır

Canlı sayımdan bağımsızdır: kamera bağlı olmasa da çalışır.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app import egitim as egitim_modulu
from app.egitim import EN_AZ_BARDAK, EN_AZ_DEGIL, EN_AZ_PARTI
from app.tespit import ModelHatasi, Tespitci
from app.web.nesne_rotalari import (
    _guvenli_dosya,
    _videodan_kareler,
    _yukleri_topla,
)
from app.web.rotalar import baglanti_al, sablonlar

router = APIRouter()

# Tek yüklemede işlenecek en çok görüntü ve videodan alınacak kare sayısı
EN_COK_GORSEL = 20
VIDEO_KARE_SAYISI = 10
# Tek yüklemede işlenecek TOPLAM kare tavanı. Dosya sayısını sınırlamak
# yetmiyor: 20 video x 10 kare = 200 kare, 1080p'de ~1,2 GB bellek demek.
EN_COK_KARE = 40


def _egitime_don(hata: str = "", mesaj: str = "") -> RedirectResponse:
    if hata:
        return RedirectResponse(f"/egitim?hata={quote(hata)}", status_code=303)
    if mesaj:
        return RedirectResponse(f"/egitim?mesaj={quote(mesaj)}", status_code=303)
    return RedirectResponse("/egitim", status_code=303)


@router.get("/egitim", response_class=HTMLResponse)
def egitim_sayfasi(istek: Request, hata: str = "", mesaj: str = "", baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    sayi = egitim_modulu.sayilar(baglanti)
    ornekler = egitim_modulu.etiketsizleri_getir(baglanti)
    etiketsiz_toplam = sayi["toplam"] - sayi["etiketli"]
    return sablonlar.TemplateResponse(
        istek,
        "egitim.html",
        {
            "sayilar": sayi,
            "ornekler": ornekler,
            "kalan": max(0, etiketsiz_toplam - len(ornekler)),
            "aktif_model": egitim_modulu.aktif_model_bilgisi(ayarlar.bardak_model_klasoru),
            "hata": hata,
            "mesaj": mesaj,
            "en_az_bardak": EN_AZ_BARDAK,
            "en_az_degil": EN_AZ_DEGIL,
            "en_az_parti": EN_AZ_PARTI,
            "bolge_uyarisi": _bolge_uyarisi(baglanti),
        },
    )


def _bolge_uyarisi(baglanti) -> str:
    """Ekrandaki 'belirsiz' sayısının asıl sebebi çoğu zaman çizilmemiş bölgedir.

    Bu, bardak tanımanın DEĞİL, bölge çiziminin sorunudur; kullanıcının iki
    'belirsiz'i karıştırmaması için açıkça söylenir.
    """
    from app import veritabani

    bolgeler = veritabani.bolgeleri_oku(baglanti)
    eksik = [ad for ad in ("musteri", "barista") if len(bolgeler.get(ad) or []) < 3]
    if not eksik:
        return ""
    adlar = " ve ".join("Müşteri tarafı" if a == "musteri" else "Barista tarafı" for a in eksik)
    return (
        f"{adlar} alanı çizilmemiş. Sayaç sayfasındaki 'belirsiz' sayısının sebebi "
        "büyük ihtimalle budur ve bunu bardak eğitimi DÜZELTMEZ — bölgeyi çizmek "
        "düzeltir. Buradaki eğitim, 'bu bizim bardağımız mı?' sorusunu iyileştirir."
    )


@router.post("/egitim/yukle")
async def gorsel_yukle(
    istek: Request,
    gorseller: list[UploadFile] = None,  # noqa: RUF013 — FastAPI çoklu dosya
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    dosyalar = [d for d in (gorseller or []) if d.filename]
    if not dosyalar:
        return _egitime_don(
            hata="Dosya seçilmedi. Bardaklarının farklı açılardan fotoğraflarını "
            "ya da kısa bir video yükleyin."
        )
    if len(dosyalar) > EN_COK_GORSEL:
        return _egitime_don(
            hata=f"Bir seferde en fazla {EN_COK_GORSEL} dosya yüklenebilir; "
            f"{len(dosyalar)} dosya seçilmiş."
        )

    ogeler = await _yukleri_topla(dosyalar)

    def _isle():
        # KENDİ Tespitci'mizi kurarız; canlı analizinkini ASLA paylaşmayız.
        # adaylari_bul, güven eşiğini ve geniş aday kipini geçici olarak
        # değiştirir; paylaşılan nesnede bu, o sırada işlenen canlı kareleri
        # bozar (kilitsiz yarış) ve sayaca yanlış bardak düşürürdü.
        try:
            tespitci = Tespitci(ayarlar.model_dosyasi, ayarlar.cihaz, guven=0.20)
        except ModelHatasi as hata:
            return 0, 0, str(hata)
        kareler = _kareleri_coz(ogeler)
        if not kareler:
            return 0, 0, ""
        eklenen, taranan = egitim_modulu.ornekleri_topla(baglanti, ayarlar, kareler, tespitci)
        return eklenen, taranan, ""

    try:
        eklenen, taranan, model_hatasi = await run_in_threadpool(_isle)
    finally:
        # Model yüklenemese bile geçici video dosyaları diskte kalmamalı
        _gecicileri_sil(ogeler)
    if model_hatasi:
        return _egitime_don(hata=model_hatasi)
    if taranan == 0:
        buyuk = [ad for ad, _tur, veri in ogeler if veri is None]
        if buyuk:
            return _egitime_don(
                hata=f"'{buyuk[0]}' çok büyük (video için en fazla 200 MB, "
                "fotoğraf için 25 MB). Dosyayı küçültüp yeniden deneyin."
            )
        return _egitime_don(
            hata="Yüklenen dosyaların hiçbiri görüntü ya da video olarak okunamadı."
        )
    if eklenen == 0:
        return _egitime_don(
            hata=f"{taranan} görüntü tarandı ama bardak olabilecek hiçbir kutu bulunamadı. "
            "Bardak karede daha büyük ve net görünsün; daha yakından çekmeyi deneyin."
        )
    return _egitime_don(
        mesaj=f"{taranan} görüntüden {eklenen} aday kırpık çıkarıldı. "
        "Şimdi aşağıdaki kartları etiketleyin."
    )


def _kareleri_coz(ogeler) -> list[tuple[str, np.ndarray]]:
    """Yüklenenleri BGR karelere çevirir; video ise eşit aralıklı kare alır."""
    kareler: list[tuple[str, np.ndarray]] = []
    for ad, tur, veri in ogeler:
        if len(kareler) >= EN_COK_KARE:
            break
        if veri is None:
            continue  # boyut sınırını aşmış: çağıran uyarır
        if tur == "video":
            kalan = EN_COK_KARE - len(kareler)
            for sira, kare in enumerate(
                _videodan_kareler(veri, min(VIDEO_KARE_SAYISI, kalan)), start=1
            ):
                kareler.append((f"{ad} — kare {sira}", kare))
            continue
        gorsel = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
        if gorsel is not None:
            kareler.append((ad, gorsel))
    return kareler


def _gecicileri_sil(ogeler) -> None:
    for _, tur, veri in ogeler:
        if tur == "video" and isinstance(veri, Path):
            veri.unlink(missing_ok=True)


@router.post("/egitim/{ornek_id}/etiket")
def ornegi_etiketle(ornek_id: int, etiket: str, baglanti=Depends(baglanti_al)):
    try:
        bulundu = egitim_modulu.etiketle(baglanti, ornek_id, etiket)
    except ValueError:
        return Response(status_code=400)
    return Response(status_code=204 if bulundu else 404)


@router.post("/egitim/calistir", response_class=HTMLResponse)
async def egitimi_calistir(istek: Request, baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    sonuc = await run_in_threadpool(egitim_modulu.egit, baglanti, ayarlar)
    return sablonlar.TemplateResponse(
        istek, "egitim_sonuc.html", {"sonuc": sonuc, "sayilar": egitim_modulu.sayilar(baglanti)}
    )


@router.post("/egitim/devreden-cikar")
def devreden_cikar(istek: Request):
    ayarlar = istek.app.state.ayarlar
    if egitim_modulu.modeli_devreden_cikar(ayarlar.bardak_model_klasoru):
        return _egitime_don(mesaj="Model devreden çıkarıldı; sistem eski davranışına döndü.")
    return _egitime_don(hata="Devrede bir model yok.")


@router.get("/egitim-foto/{ad}")
def egitim_fotografi(istek: Request, ad: str):
    return _guvenli_dosya(istek.app.state.ayarlar.egitim_klasoru, ad)


__all__ = ["router"]
