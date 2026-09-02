"""Nesne kütüphanesi ve kare/video tarama sayfaları.

Bu iki sayfa canlı sayımdan bağımsızdır: kamera bağlı olmasa da çalışır ve
günlük sayaçlara dokunmaz. Amaç, kendi nesnelerini tanıtmak ve fotoğraf ya da
video üzerinde deneme yapmaktır.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app import nesne_deposu
from app import tarama as tarama_modulu
from app.kutuphane import VARSAYILAN_ESIK
from app.nesne_deposu import NesneHatasi
from app.tespit import ModelHatasi, Tespitci
from app.web.rotalar import baglanti_al, sablonlar

router = APIRouter()

_log = logging.getLogger("laffogato.tarama")

# Aynı anda taranabilecek en çok kare (tarayıcı da, işlemci de boğulmasın)
EN_COK_KARE = 12
# Bir videodan örneklenecek en çok kare (eşit aralıklı seçilir)
VIDEO_KARE_SAYISI = 8
VIDEO_UZANTILAR = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
EN_BUYUK_VIDEO = 200 * 1024 * 1024  # 200 MB — telefon videosu rahat sığar
# Fotoğraf tarafı da sınırlı olmalı: desteklenmeyen uzantılı büyük dosyalar
# 'görsel' sayılıp belleğe okunuyordu (bkz. _yukleri_topla)
EN_BUYUK_GORSEL = 25 * 1024 * 1024


@router.get("/kutuphane", response_class=HTMLResponse)
def kutuphane(istek: Request, hata: str = "", mesaj: str = "", baglanti=Depends(baglanti_al)):
    return sablonlar.TemplateResponse(
        istek,
        "kutuphane.html",
        {
            "nesneler": nesne_deposu.nesneleri_listele(baglanti),
            "hata": hata,
            "mesaj": mesaj,
            "esik_yuzde": int(VARSAYILAN_ESIK * 100),
        },
    )


def _kutuphaneye_don(hata: str = "", mesaj: str = "") -> RedirectResponse:
    if hata:
        return RedirectResponse(f"/kutuphane?hata={quote(hata)}", status_code=303)
    if mesaj:
        return RedirectResponse(f"/kutuphane?mesaj={quote(mesaj)}", status_code=303)
    return RedirectResponse("/kutuphane", status_code=303)


async def _fotograflari_kaydet(baglanti, klasor, nesne_id: int, dosyalar) -> tuple[int, list[str]]:
    """Fotoğrafları tek tek kaydeder; biri bozuksa diğerleri yine de eklenir."""
    eklendi, atlanan = 0, []
    for dosya in dosyalar:
        try:
            nesne_deposu.fotograf_ekle(
                baglanti, klasor, nesne_id, dosya.filename, await dosya.read()
            )
            eklendi += 1
        except NesneHatasi as hata:
            atlanan.append(str(hata))
    return eklendi, atlanan


def _ozet_mesaji(eklendi: int, atlanan: list[str], on_ek: str = "") -> str:
    mesaj = f"{on_ek}{eklendi} fotoğraf eklendi."
    if atlanan:
        mesaj += f" {len(atlanan)} dosya alınamadı: {atlanan[0]}"
    return mesaj


@router.post("/kutuphane/nesne")
async def nesne_olustur(
    istek: Request,
    ad: str = Form(...),
    fotograflar: list[UploadFile] = None,  # noqa: RUF013 — FastAPI çoklu dosya
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    dosyalar = [d for d in fotograflar or [] if d.filename]
    if not dosyalar:
        return _kutuphaneye_don(
            hata="Fotoğraf seçilmedi. Nesneyi tanıtmak için farklı açılardan 3-8 fotoğraf yükleyin."
        )
    try:
        nesne_id = nesne_deposu.nesne_ekle(baglanti, ad)
    except NesneHatasi as hata:
        return _kutuphaneye_don(hata=str(hata))

    eklendi, atlanan = await _fotograflari_kaydet(
        baglanti, ayarlar.nesne_klasoru, nesne_id, dosyalar
    )
    if eklendi == 0:
        # Hiç fotoğraf kaydedilemediyse yarım nesne bırakma
        nesne_deposu.nesne_sil(baglanti, ayarlar.nesne_klasoru, nesne_id)
        return _kutuphaneye_don(hata=atlanan[0])
    return _kutuphaneye_don(mesaj=_ozet_mesaji(eklendi, atlanan, on_ek=f"'{ad.strip()}' eklendi: "))


@router.post("/kutuphane/{nesne_id}/fotograf")
async def fotograf_yukle(
    istek: Request,
    nesne_id: int,
    fotograflar: list[UploadFile] = None,  # noqa: RUF013
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    dosyalar = [d for d in fotograflar or [] if d.filename]
    if not dosyalar:
        return _kutuphaneye_don(hata="Fotoğraf seçilmedi. Farklı açılardan 3-8 fotoğraf önerilir.")
    eklendi, atlanan = await _fotograflari_kaydet(
        baglanti, ayarlar.nesne_klasoru, nesne_id, dosyalar
    )
    if eklendi == 0:
        return _kutuphaneye_don(hata=atlanan[0])
    return _kutuphaneye_don(mesaj=_ozet_mesaji(eklendi, atlanan))


@router.post("/kutuphane/{nesne_id}/sil")
def nesne_sil(istek: Request, nesne_id: int, baglanti=Depends(baglanti_al)):
    nesne_deposu.nesne_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, nesne_id)
    return _kutuphaneye_don(mesaj="Nesne silindi.")


@router.post("/kutuphane/fotograf/{foto_id}/sil")
def foto_sil(istek: Request, foto_id: int, baglanti=Depends(baglanti_al)):
    nesne_deposu.fotograf_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, foto_id)
    return _kutuphaneye_don(mesaj="Fotoğraf kaldırıldı.")


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
            "en_cok_kare": EN_COK_KARE,
        },
    )


def _videodan_kareler(yol: Path, en_cok: int) -> list[np.ndarray]:
    """Videodan eşit aralıklı en çok `en_cok` kare çıkarır ([] = açılamadı)."""
    yakalayici = cv2.VideoCapture(str(yol))
    if not yakalayici.isOpened():
        return []
    try:
        toplam = int(yakalayici.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        kareler: list[np.ndarray] = []
        if toplam > 0:
            adet = min(en_cok, toplam)
            for sira in range(adet):
                indeks = round(sira * (toplam - 1) / max(adet - 1, 1))
                yakalayici.set(cv2.CAP_PROP_POS_FRAMES, indeks)
                tamam, kare = yakalayici.read()
                if tamam and kare is not None:
                    kareler.append(kare)
        else:
            # Kare sayısı bilinmeyen akışlar: sırayla oku, seyrelterek al
            sayac = 0
            while len(kareler) < en_cok and sayac < 3000:
                tamam, kare = yakalayici.read()
                if not tamam:
                    break
                if sayac % 10 == 0 and kare is not None:
                    kareler.append(kare)
                sayac += 1
        return kareler
    finally:
        yakalayici.release()


async def _yukleri_topla(dosyalar: list[UploadFile]) -> list[tuple[str, str, Path | bytes | None]]:
    """Yüklenen dosyaları asenkron okur: video → geçici dosya, fotoğraf → bellek.

    Öğe: (dosya_adı, tür, veri). Tür "video" ise veri geçici dosyanın yoludur
    (dosya çok büyükse None); "gorsel" ise ham bayttır.
    """
    ogeler: list[tuple[str, str, Path | bytes | None]] = []
    for dosya in dosyalar:
        uzanti = Path(dosya.filename).suffix.lower()
        if uzanti in VIDEO_UZANTILAR:
            boyut = 0
            with tempfile.NamedTemporaryFile(suffix=uzanti, delete=False) as f:
                gecici = Path(f.name)
                while parca := await dosya.read(1024 * 1024):
                    boyut += len(parca)
                    if boyut > EN_BUYUK_VIDEO:
                        break
                    f.write(parca)
            if boyut > EN_BUYUK_VIDEO:
                gecici.unlink(missing_ok=True)
                ogeler.append((dosya.filename, "video", None))
            else:
                ogeler.append((dosya.filename, "video", gecici))
        else:
            # Video listesinde OLMAYAN uzantılar (.m4v, .mpg, .mts …) buraya
            # düşer. Sınırsız okumak, kafedeki küçük bilgisayarda 1,5 GB'lık
            # bir dosyayı tek seferde RAM'e alıp sistemi kilitlerdi.
            veri = bytearray()
            asildi = False
            while parca := await dosya.read(1024 * 1024):
                veri.extend(parca)
                if len(veri) > EN_BUYUK_GORSEL:
                    asildi = True
                    break
            ogeler.append((dosya.filename, "gorsel", None if asildi else bytes(veri)))
    return ogeler


def _tarama_isle(ogeler, tespitci, nesneler, klasor: Path, esik: float):
    """Kod çözme + model çıkarımı: iş parçacığı havuzunda koşan ağır kısım."""
    sonuclar = []
    kirpildi = False
    try:
        for ad, tur, veri in ogeler:
            kalan = EN_COK_KARE - len(sonuclar)
            if kalan <= 0:
                kirpildi = True
                break

            if tur == "video":
                if veri is None:
                    uyari = f"'{ad}' çok büyük (en fazla 200 MB video yüklenebilir)."
                else:
                    video_kareleri = _videodan_kareler(veri, min(VIDEO_KARE_SAYISI, kalan))
                    if video_kareleri:
                        for sira, kare in enumerate(video_kareleri, start=1):
                            sonuclar.append(
                                tarama_modulu.tara(
                                    kare,
                                    f"{ad} — kare {sira}/{len(video_kareleri)}",
                                    tespitci,
                                    nesneler,
                                    klasor,
                                    esik,
                                )
                            )
                        continue
                    uyari = f"'{ad}' bir video olarak açılamadı (bozuk ya da desteklenmeyen tür)."
                sonuclar.append(
                    tarama_modulu.TaramaSonucu(
                        dosya_adi=ad, sonuc_gorseli="", bulgular=[], uyari=uyari
                    )
                )
                continue

            gorsel = (
                cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
                if veri is not None
                else None
            )
            if gorsel is None:
                sonuclar.append(
                    tarama_modulu.TaramaSonucu(
                        dosya_adi=ad,
                        sonuc_gorseli="",
                        bulgular=[],
                        uyari="Bu dosya bir görüntü olarak okunamadı "
                        "(bozuk ya da desteklenmeyen tür).",
                    )
                )
                continue
            sonuclar.append(tarama_modulu.tara(gorsel, ad, tespitci, nesneler, klasor, esik))
    finally:
        for _, tur, veri in ogeler:
            if tur == "video" and isinstance(veri, Path):
                veri.unlink(missing_ok=True)
    tarama_modulu.eski_taramalari_temizle(klasor)
    return sonuclar, kirpildi


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
            "/tarama?hata=" + quote("Dosya seçilmedi. Fotoğraf ya da video yükleyin."),
            status_code=303,
        )
    if len(dosyalar) > EN_COK_KARE:
        return RedirectResponse(
            "/tarama?hata="
            + quote(f"En fazla {EN_COK_KARE} dosya taranabilir; {len(dosyalar)} dosya seçilmiş."),
            status_code=303,
        )
    try:
        esik = max(5, min(95, int(float(str(esik_yuzde).replace(",", "."))))) / 100
    except ValueError:
        esik = VARSAYILAN_ESIK

    ogeler = await _yukleri_topla(dosyalar)
    analiz = getattr(istek.app.state, "analiz", None)

    def _isle():
        # Model yükleme, kod çözme ve çıkarım ağırdır; olay döngüsünü kilitlemesin
        tespitci: Tespitci | None = getattr(analiz, "_tespitci", None)
        if tespitci is None:
            try:
                tespitci = Tespitci(ayarlar.model_dosyasi, ayarlar.cihaz, guven=0.25)
            except ModelHatasi as hata:
                # Ekrana tarama.MODEL_YOK_UYARISI düşer (sade, markalı);
                # tam yol ve özgün istisna metni yalnızca günlüğe yazılır.
                _log.error("Tarama için tespit modeli açılamadı: %s", hata.teknik)
                tespitci = None
        nesneler = nesne_deposu.nesneleri_yukle(baglanti, ayarlar.nesne_klasoru)
        sonuclar, kirpildi = _tarama_isle(ogeler, tespitci, nesneler, ayarlar.tarama_klasoru, esik)
        return sonuclar, kirpildi, len(nesneler)

    sonuclar, kirpildi, nesne_sayisi = await run_in_threadpool(_isle)

    return sablonlar.TemplateResponse(
        istek,
        "tarama.html",
        {
            "sonuclar": sonuclar,
            "nesne_sayisi": nesne_sayisi,
            "hata": "",
            "esik_yuzde": int(esik * 100),
            "en_cok_kare": EN_COK_KARE,
            "toplam_eslesen": sum(s.eslesen_sayisi for s in sonuclar),
            "kirpilan_uyari": (
                f"Bir taramada en çok {EN_COK_KARE} kare işlenir; kalan dosyalar atlandı."
                if kirpildi
                else ""
            ),
        },
    )
