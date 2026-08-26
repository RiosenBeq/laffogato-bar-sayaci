"""Nesne kütüphanesi ve kare kare tarama sayfaları.

Bu iki sayfa canlı sayımdan bağımsızdır: kamera bağlı olmasa da çalışır ve
günlük sayaçlara dokunmaz. Amaç, kendi nesnelerini tanıtmak ve kareler
üzerinde deneme yapmaktır.
"""

from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import nesne_deposu
from app import tarama as tarama_modulu
from app.kutuphane import VARSAYILAN_ESIK
from app.nesne_deposu import NesneHatasi
from app.tespit import ModelHatasi, Tespitci
from app.web.rotalar import baglanti_al, sablonlar

router = APIRouter()

# Aynı anda taranabilecek en çok kare (tarayıcı da, işlemci de boğulmasın)
EN_COK_KARE = 12


@router.get("/kutuphane", response_class=HTMLResponse)
def kutuphane(istek: Request, hata: str = "", baglanti=Depends(baglanti_al)):
    return sablonlar.TemplateResponse(
        istek,
        "kutuphane.html",
        {
            "nesneler": nesne_deposu.nesneleri_listele(baglanti),
            "hata": hata,
            "esik_yuzde": int(VARSAYILAN_ESIK * 100),
        },
    )


@router.post("/kutuphane/nesne")
async def nesne_olustur(
    istek: Request,
    ad: str = Form(...),
    fotograflar: list[UploadFile] = None,  # noqa: RUF013 — FastAPI çoklu dosya
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    try:
        nesne_id = nesne_deposu.nesne_ekle(baglanti, ad)
        for dosya in fotograflar or []:
            if not dosya.filename:
                continue
            nesne_deposu.fotograf_ekle(
                baglanti, ayarlar.nesne_klasoru, nesne_id, dosya.filename, await dosya.read()
            )
    except NesneHatasi as hata:
        return RedirectResponse(f"/kutuphane?hata={hata}", status_code=303)
    return RedirectResponse("/kutuphane", status_code=303)


@router.post("/kutuphane/{nesne_id}/fotograf")
async def fotograf_yukle(
    istek: Request,
    nesne_id: int,
    fotograflar: list[UploadFile] = None,  # noqa: RUF013
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    eklendi = 0
    try:
        for dosya in fotograflar or []:
            if not dosya.filename:
                continue
            nesne_deposu.fotograf_ekle(
                baglanti, ayarlar.nesne_klasoru, nesne_id, dosya.filename, await dosya.read()
            )
            eklendi += 1
    except NesneHatasi as hata:
        return RedirectResponse(f"/kutuphane?hata={hata}", status_code=303)
    if eklendi == 0:
        return RedirectResponse(
            "/kutuphane?hata=Fotoğraf seçilmedi. Farklı açılardan 3-8 fotoğraf önerilir.",
            status_code=303,
        )
    return RedirectResponse("/kutuphane", status_code=303)


@router.post("/kutuphane/{nesne_id}/sil")
def nesne_sil(istek: Request, nesne_id: int, baglanti=Depends(baglanti_al)):
    nesne_deposu.nesne_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, nesne_id)
    return RedirectResponse("/kutuphane", status_code=303)


@router.post("/kutuphane/fotograf/{foto_id}/sil")
def foto_sil(istek: Request, foto_id: int, baglanti=Depends(baglanti_al)):
    nesne_deposu.fotograf_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, foto_id)
    return RedirectResponse("/kutuphane", status_code=303)


@router.get("/nesne-foto/{ad}")
def nesne_fotografi(istek: Request, ad: str):
    return _guvenli_dosya(istek.app.state.ayarlar.nesne_klasoru, ad)


@router.get("/tarama-foto/{ad}")
def tarama_fotografi(istek: Request, ad: str):
    return _guvenli_dosya(istek.app.state.ayarlar.tarama_klasoru, ad)


def _guvenli_dosya(kok, ad: str) -> Response:
    kok = kok.resolve()
    dosya = (kok / ad).resolve()
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    tur = "image/png" if dosya.suffix.lower() == ".png" else "image/jpeg"
    return Response(content=dosya.read_bytes(), media_type=tur)


@router.get("/tarama", response_class=HTMLResponse)
def tarama_sayfasi(istek: Request, hata: str = "", baglanti=Depends(baglanti_al)):
    return sablonlar.TemplateResponse(
        istek,
        "tarama.html",
        {
            "sonuclar": [],
            "nesne_sayisi": len(nesne_deposu.nesneleri_listele(baglanti)),
            "hata": hata,
            "esik_yuzde": int(VARSAYILAN_ESIK * 100),
        },
    )


@router.post("/tarama", response_class=HTMLResponse)
async def tarama_yap(
    istek: Request,
    kareler: list[UploadFile] = None,  # noqa: RUF013
    esik_yuzde: str = Form("42"),
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    dosyalar = [d for d in (kareler or []) if d.filename]
    if not dosyalar:
        return RedirectResponse(
            "/tarama?hata=Kare seçilmedi. Kameradan aldığınız görüntüleri seçin.",
            status_code=303,
        )
    if len(dosyalar) > EN_COK_KARE:
        return RedirectResponse(
            f"/tarama?hata=En fazla {EN_COK_KARE} kare taranabilir; {len(dosyalar)} kare seçilmiş.",
            status_code=303,
        )
    try:
        esik = max(5, min(95, int(float(str(esik_yuzde).replace(",", "."))))) / 100
    except ValueError:
        esik = VARSAYILAN_ESIK

    # Canlı analizin tespitçisi varsa onu kullan; yoksa tarama için ayrıca yükle
    analiz = getattr(istek.app.state, "analiz", None)
    tespitci: Tespitci | None = getattr(analiz, "_tespitci", None)
    if tespitci is None:
        try:
            tespitci = Tespitci(ayarlar.model_dosyasi, ayarlar.cihaz, guven=0.25)
        except ModelHatasi:
            tespitci = None

    nesneler = nesne_deposu.nesneleri_yukle(baglanti, ayarlar.nesne_klasoru)
    sonuclar = []
    for dosya in dosyalar:
        veri = await dosya.read()
        gorsel = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
        if gorsel is None:
            sonuclar.append(
                tarama_modulu.TaramaSonucu(
                    dosya_adi=dosya.filename,
                    sonuc_gorseli="",
                    bulgular=[],
                    uyari="Bu dosya bir görüntü olarak okunamadı (bozuk ya da desteklenmeyen tür).",
                )
            )
            continue
        sonuclar.append(
            tarama_modulu.tara(
                gorsel, dosya.filename, tespitci, nesneler, ayarlar.tarama_klasoru, esik
            )
        )
    tarama_modulu.eski_taramalari_temizle(ayarlar.tarama_klasoru)

    return sablonlar.TemplateResponse(
        istek,
        "tarama.html",
        {
            "sonuclar": sonuclar,
            "nesne_sayisi": len(nesneler),
            "hata": "",
            "esik_yuzde": int(esik * 100),
            "toplam_eslesen": sum(s.eslesen_sayisi for s in sonuclar),
        },
    )
