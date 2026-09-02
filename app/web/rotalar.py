"""Laffogato arayüzü: canlı izleme, bölge tanımı, günlük bardak raporu."""

from __future__ import annotations

import base64
import csv
import io
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import cv2
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import ayarlar as ayarlar_modulu
from app import veritabani, zaman
from app.ayarlar import AyarHatasi
from app.bardak import BARISTA, BELIRSIZ, MUSTERI, gunluk_ozet

router = APIRouter()
SABLONLAR = Path(__file__).resolve().parent / "templates"
sablonlar = Jinja2Templates(directory=str(SABLONLAR))

KIME_ADI = {MUSTERI: "Müşteri içti", BARISTA: "Barista kendine", BELIRSIZ: "Belirsiz"}


def baglanti_al(istek: Request):
    baglanti = veritabani.baglanti_ac(istek.app.state.ayarlar.veritabani)
    try:
        yield baglanti
    finally:
        baglanti.close()


def _ozet(baglanti, gun: str) -> dict:
    kararlar = [
        s["kime"] for s in baglanti.execute("SELECT kime FROM bardaklar WHERE gun = ?", (gun,))
    ]
    return gunluk_ozet(kararlar)


@router.get("/", response_class=HTMLResponse)
def ana(
    istek: Request,
    gun: str = "",
    hata: str = "",
    mesaj: str = "",
    baglanti=Depends(baglanti_al),
):
    gun = gun or zaman.bugun()
    analiz = getattr(istek.app.state, "analiz", None)
    nesne_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM nesneler").fetchone()["n"]
    bolgeler = veritabani.bolgeleri_oku(baglanti)
    db_ayarlar = veritabani.ayarlari_oku(baglanti)

    bardaklar = [
        {
            "saat": zaman.saat(s["baslangic"]),
            "kime": s["kime"],
            "kime_adi": KIME_ADI.get(s["kime"], s["kime"]),
            "foto": s["foto"],
            "musteri": s["musteri_gozlem"],
            "barista": s["barista_gozlem"],
        }
        for s in baglanti.execute(
            "SELECT * FROM bardaklar WHERE gun = ? ORDER BY baslangic DESC LIMIT 60", (gun,)
        )
    ]
    # Saat dağılımı Python'da hesaplanır — DB'de UTC saklanır, SQL substr
    # ile alınan saat Türkiye saatine göre yanlış olurdu
    saat_sayim = Counter(
        zaman.saat(s["baslangic"])[:2]
        for s in baglanti.execute("SELECT baslangic FROM bardaklar WHERE gun = ?", (gun,))
    )
    saatlik = [{"saat": s, "adet": saat_sayim[s]} for s in sorted(saat_sayim)]
    son7 = [
        {"etiket": zaman.gun_ekranda(s["gun"])[:5], "adet": s["adet"], "bugun": s["gun"] == gun}
        for s in baglanti.execute(
            "SELECT gun, COUNT(*) AS adet FROM bardaklar GROUP BY gun ORDER BY gun DESC LIMIT 7"
        )
    ][::-1]
    gunler = [
        {"gun": s["gun"], "etiket": zaman.gun_ekranda(s["gun"])}
        for s in baglanti.execute("SELECT DISTINCT gun FROM bardaklar ORDER BY gun DESC LIMIT 30")
    ]

    ozet = _ozet(baglanti, gun)
    en_yuksek = max((s["adet"] for s in saatlik), default=1) or 1
    return sablonlar.TemplateResponse(
        istek,
        "ana.html",
        {
            "gun": gun,
            "gun_etiketi": zaman.gun_ekranda(gun),
            "ozet": ozet,
            "musteri_yuzde": round(ozet[MUSTERI] * 100 / ozet["toplam"]) if ozet["toplam"] else 0,
            "barista_yuzde": round(ozet[BARISTA] * 100 / ozet["toplam"]) if ozet["toplam"] else 0,
            "bardaklar": bardaklar,
            "saatlik": saatlik,
            "en_yuksek": en_yuksek,
            "en_yogun_saat": (
                max(saatlik, key=lambda s: s["adet"])["saat"] + ":00" if saatlik else None
            ),
            "son7": son7,
            "son7_en_yuksek": max((g["adet"] for g in son7), default=1) or 1,
            "gunler": gunler,
            "bolge_musteri_var": len(bolgeler.get("musteri", [])) >= 3,
            "bolge_barista_var": len(bolgeler.get("barista", [])) >= 3,
            "hassasiyet": (db_ayarlar.get("tespit_hassasiyeti", "0.30")).replace(".", ","),
            "hassasiyet_sayi": db_ayarlar.get("tespit_hassasiyeti", "0.30"),
            "durum": getattr(analiz, "durum", "başlatılmadı"),
            "canli_bardak": getattr(analiz, "canli_bardak", 0),
            "canli_kisi": getattr(analiz, "canli_kisi", 0),
            "model_hatasi": getattr(analiz, "model_hatasi", None),
            # Ekranda dosya adı değil kademe adı görünür (Hızlı / İsabetli)
            "model_adi": ayarlar_modulu.gorunen_model_adi(
                str(istek.app.state.ayarlar.model_dosyasi)
            ),
            "kaynak_hatasi": getattr(analiz, "kaynak_hatasi", None),
            "kaynak": kaynak_gorunen(istek.app.state.ayarlar.kaynak),
            "kaynak_ham": istek.app.state.ayarlar.kaynak,
            "kaynak_tur": kaynak_turu(istek.app.state.ayarlar.kaynak),
            "nesne_sayisi": nesne_sayisi,
            "hata": hata,
            "mesaj": mesaj,
        },
    )


@router.post("/bolge")
def bolge_kaydet(
    taraf: str = Form(...),  # musteri | barista
    poligon: str = Form(...),  # JSON: [[x,y], ...] normalize 0-1
    baglanti=Depends(baglanti_al),
):
    if taraf not in (MUSTERI, BARISTA):
        return RedirectResponse("/?hata=Geçersiz bölge tarafı.", status_code=303)
    try:
        noktalar = [[float(x), float(y)] for x, y in json.loads(poligon)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return RedirectResponse("/?hata=Bölge çizimi okunamadı.", status_code=303)
    if len(noktalar) < 3:
        return RedirectResponse(
            "/?hata=Bölge en az 3 köşe içermeli. Görüntüye tıklayarak alanı çizin.",
            status_code=303,
        )
    if not all(0 <= x <= 1 and 0 <= y <= 1 for x, y in noktalar):
        return RedirectResponse("/?hata=Bölge görüntünün içinde olmalı.", status_code=303)
    veritabani.ayar_yaz(baglanti, f"bolge_{taraf}", json.dumps(noktalar))
    return RedirectResponse("/", status_code=303)


@router.post("/ayarlar/hassasiyet")
def hassasiyet_kaydet(deger: str = Form(...), baglanti=Depends(baglanti_al)):
    """Bardak küçük bir nesne: hassasiyeti kullanıcı kendi barına göre ayarlar."""
    try:
        sayi = float(str(deger).replace(",", "."))
    except ValueError:
        return RedirectResponse(
            f"/?hata=Hassasiyet sayı olmalı (örn. 0,30); '{deger}' yazılmış.",
            status_code=303,
        )
    if not veritabani.HASSASIYET_EN_AZ <= sayi <= veritabani.HASSASIYET_EN_COK:
        return RedirectResponse(
            f"/?hata=Hassasiyet {veritabani.HASSASIYET_EN_AZ:g} ile "
            f"{veritabani.HASSASIYET_EN_COK:g} arasında olmalı.",
            status_code=303,
        )
    veritabani.ayar_yaz(baglanti, "tespit_hassasiyeti", f"{sayi:g}")
    return RedirectResponse("/", status_code=303)


@router.post("/bolge/{taraf}/sil")
def bolge_sil(taraf: str, baglanti=Depends(baglanti_al)):
    if taraf in (MUSTERI, BARISTA):
        veritabani.ayar_yaz(baglanti, f"bolge_{taraf}", "[]")
    return RedirectResponse("/", status_code=303)


@router.get("/onizleme.jpg")
def onizleme(istek: Request):
    analiz = getattr(istek.app.state, "analiz", None)
    jpeg = analiz.onizleme() if analiz else None
    if jpeg is None:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")


@router.get("/canli")
def canli(istek: Request, gun: str = "", sonra: int = 0, baglanti=Depends(baglanti_al)):
    """Ekranın 2 saniyede bir yokladığı canlı özet.

    `sonra`: ekranın gördüğü son olay numarası. Yanıttaki `olaylar` listesi
    yalnızca ondan YENİ olanları içerir — böylece aynı pencerede kapanan iki
    bardak iki ayrı uyarı olur ve hiçbir olay atlanmaz. Eskiden ekran sayaç
    farkına bakıyordu: iki bardak tek uyarıya iniyor, geçmiş gün
    görüntülenirken uyarı hiç gelmiyordu.
    """
    gun = gun or zaman.bugun()
    analiz = getattr(istek.app.state, "analiz", None)
    return {
        **_ozet(baglanti, gun),
        "canli_bardak": getattr(analiz, "canli_bardak", 0),
        "canli_kisi": getattr(analiz, "canli_kisi", 0),
        "durum": getattr(analiz, "durum", "başlatılmadı"),
        "son_hata": getattr(analiz, "son_hata", ""),
        "olaylar": analiz.olaylar(sonra) if analiz is not None else [],
        "son_olay_id": getattr(analiz, "son_olay_id", 0),
    }


@router.get("/gorsel/{ad}")
def gorsel(istek: Request, ad: str):
    kok = istek.app.state.ayarlar.goruntu_klasoru.resolve()
    dosya = (kok / ad).resolve()
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    return Response(content=dosya.read_bytes(), media_type="image/jpeg")


@router.get("/rapor.csv")
def rapor(gun: str = "", baglanti=Depends(baglanti_al)):
    gun = gun or zaman.bugun()
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(["Gün", "Saat", "Kime", "Müşteri gözlemi", "Barista gözlemi"])
    for s in baglanti.execute("SELECT * FROM bardaklar WHERE gun = ? ORDER BY baslangic", (gun,)):
        yazici.writerow(
            [
                zaman.gun_ekranda(s["gun"]),
                zaman.saat(s["baslangic"]),
                KIME_ADI.get(s["kime"], s["kime"]),
                s["musteri_gozlem"],
                s["barista_gozlem"],
            ]
        )
    return Response(
        content="﻿" + tampon.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=laffogato-{gun}.csv"},
    )


@router.post("/sifirla")
def sifirla(istek: Request, gun: str = Form(""), baglanti=Depends(baglanti_al)):
    gun = gun or zaman.bugun()
    baglanti.execute("DELETE FROM bardaklar WHERE gun = ?", (gun,))
    baglanti.commit()
    analiz = getattr(istek.app.state, "analiz", None)
    if analiz is not None:
        analiz.sayaclari_sifirla()
    return RedirectResponse("/", status_code=303)


# ---- görüntü kaynağı (kamera / IP kamera / video dosyası) ----


class KaynakHatasi(Exception):
    """Kullanıcıya gösterilecek anlaşılır kaynak hatası."""


def kaynak_turu(kaynak: str) -> str:
    """Mevcut KAYNAK değerinden arayüzdeki seçimi çıkarır."""
    ham = (kaynak or "").strip()
    if ham.isdigit():
        return "kamera"
    if ham.lower().startswith(("rtsp://", "http://", "https://")):
        return "rtsp"
    return "dosya"


def kaynak_gorunen(kaynak: str) -> str:
    """Ekranda gösterilecek kaynak: rtsp şifresi maskelenir."""
    ham = (kaynak or "").strip()
    if "://" in ham and "@" in ham:
        sema, kalan = ham.split("://", 1)
        kimlik, sunucu = kalan.rsplit("@", 1)
        if ":" in kimlik:
            kullanici = kimlik.split(":", 1)[0]
            return f"{sema}://{kullanici}:••••@{sunucu}"
    return ham


def _kaynak_degeri(kok: Path, tur: str, kamera_no: str, rtsp_adres: str, dosya_yolu: str) -> str:
    if tur == "kamera":
        no = (kamera_no or "").strip()
        if not (no.isascii() and no.isdigit()) or len(no) > 2:
            raise KaynakHatasi(
                "Kamera numarası 0-99 arası bir sayı olmalı (0 = bilgisayarın kamerası)."
            )
        return no
    if tur == "rtsp":
        adres = (rtsp_adres or "").strip()
        if not adres.lower().startswith(("rtsp://", "http://", "https://")):
            raise KaynakHatasi(
                "Kamera adresi rtsp:// ile başlamalı — "
                "örn. rtsp://kullanici:sifre@192.168.1.50:554/stream1"
            )
        if any(karakter.isspace() for karakter in adres):
            raise KaynakHatasi("Kamera adresinde boşluk ya da satır sonu olamaz.")
        return adres
    if tur == "dosya":
        yol = (dosya_yolu or "").strip()
        if not yol:
            raise KaynakHatasi("Video dosyasının yolunu yazın (örn. veri/kayit.mp4).")
        if "\n" in yol or "\r" in yol:
            raise KaynakHatasi("Dosya yolunda satır sonu olamaz.")
        aday = Path(yol)
        tam = (aday if aday.is_absolute() else kok / aday).resolve()
        if not tam.is_relative_to(kok.resolve()):
            raise KaynakHatasi(
                "Video dosyası proje klasörünün içinde olmalı — dosyayı veri/ "
                "klasörüne kopyalayıp yolunu veri/dosyaadi.mp4 gibi yazın."
            )
        if not tam.is_file():
            raise KaynakHatasi(f"Video dosyası bulunamadı: {yol}")
        return yol
    raise KaynakHatasi("Geçersiz kaynak türü seçildi.")


@router.post("/ayarlar/kaynak")
def kaynak_kaydet(
    istek: Request,
    tur: str = Form(...),
    kamera_no: str = Form("0"),
    rtsp_adres: str = Form(""),
    dosya_yolu: str = Form(""),
):
    """Kaynağı .env'e yazar ve analizi yeni kaynakla yeniden başlatır."""
    ayar = istek.app.state.ayarlar
    try:
        deger = _kaynak_degeri(ayar.kok, tur, kamera_no, rtsp_adres, dosya_yolu)
        ayarlar_modulu.kaynagi_kaydet(ayar.kok, deger)
    except (KaynakHatasi, AyarHatasi) as hata:
        return RedirectResponse(f"/?hata={quote(str(hata))}", status_code=303)

    yeni_ayarlar = replace(ayar, kaynak=deger)
    istek.app.state.ayarlar = yeni_ayarlar

    eski = getattr(istek.app.state, "analiz", None)
    if eski is not None and callable(getattr(eski, "durdur", None)):
        durdu = eski.durdur()
        from app.analiz import Analiz  # analiz kapalıyken (testler) hiç yüklenmesin

        yeni_analiz = Analiz(yeni_ayarlar)
        istek.app.state.analiz = yeni_analiz
        yeni_analiz.baslat()
        mesaj = "Görüntü kaynağı kaydedildi; sistem yeni kaynakla yeniden başlatıldı."
        if durdu is False:  # eski bağlantı hâlâ kapanıyor (zaman aşımlı akış)
            mesaj += (
                " Eski bağlantının kapanması birkaç saniye sürebilir; "
                "görüntü gelmezse sayfayı yenileyin."
            )
    else:
        mesaj = "Görüntü kaynağı kaydedildi."
    return RedirectResponse(f"/?mesaj={quote(mesaj)}", status_code=303)


@router.post("/ayarlar/kaynak/sina")
def kaynak_sina(
    istek: Request,
    tur: str = Form(...),
    kamera_no: str = Form("0"),
    rtsp_adres: str = Form(""),
    dosya_yolu: str = Form(""),
):
    """Kaydetmeden dener: kaynağa bağlanıp tek kare alır, küçük önizleme döndürür."""
    ayar = istek.app.state.ayarlar
    try:
        deger = _kaynak_degeri(ayar.kok, tur, kamera_no, rtsp_adres, dosya_yolu)
    except KaynakHatasi as hata:
        return {"ok": False, "mesaj": str(hata), "gorsel": None}
    return _kaynagi_dene(ayar.kok, deger)


def _kaynagi_dene(kok: Path, deger: str) -> dict:
    ham = deger.strip()
    if ham.isdigit():
        arka_uc = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        yakalayici = cv2.VideoCapture(int(ham), arka_uc)
        ipucu = (
            "Kamera açılamadı. Kamerayı kullanan başka bir program (Zoom, FaceTime) "
            "açıksa kapatın; sistem şu an aynı kamerayla çalışıyorsa bu normaldir — "
            "önce Kaydet'e basıp sonucu canlı görüntüden izleyin. macOS'ta kamera "
            "iznini de kontrol edin (Sistem Ayarları → Gizlilik ve Güvenlik → Kamera)."
        )
    else:
        aday = kok / ham
        kaynak = str(aday) if aday.exists() else ham
        yakalayici = cv2.VideoCapture(
            kaynak,
            cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
        )
        ipucu = (
            "Kaynağa bağlanılamadı. Adresi/yolu, kullanıcı adı ve şifreyi kontrol edin; "
            "IP kameraysa bilgisayarla aynı ağda olduğundan emin olun."
        )
    try:
        if not yakalayici.isOpened():
            return {"ok": False, "mesaj": ipucu, "gorsel": None}
        tamam, kare = yakalayici.read()
        if not tamam or kare is None:
            return {
                "ok": False,
                "mesaj": "Bağlantı açıldı ama görüntü alınamadı; birkaç saniye sonra "
                "yeniden deneyin.",
                "gorsel": None,
            }
        yukseklik, genislik = kare.shape[:2]
        kucuk = kare
        if genislik > 480:
            kucuk = cv2.resize(kare, (480, max(1, int(yukseklik * 480 / genislik))))
        tamam2, jpeg = cv2.imencode(".jpg", kucuk, [cv2.IMWRITE_JPEG_QUALITY, 70])
        gorsel = (
            "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("ascii")
            if tamam2
            else None
        )
        return {
            "ok": True,
            "mesaj": f"Bağlantı başarılı — {genislik}×{yukseklik} boyutunda görüntü alındı.",
            "gorsel": gorsel,
        }
    finally:
        yakalayici.release()
