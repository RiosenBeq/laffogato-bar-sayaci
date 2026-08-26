"""Laffogato arayüzü: canlı izleme, bölge tanımı, günlük bardak raporu."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import veritabani, zaman
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
def ana(istek: Request, gun: str = "", hata: str = "", baglanti=Depends(baglanti_al)):
    gun = gun or zaman.bugun()
    analiz = getattr(istek.app.state, "analiz", None)
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
    saatlik = [
        {"saat": s["saat"], "adet": s["adet"]}
        for s in baglanti.execute(
            "SELECT substr(baslangic, 12, 2) AS ham, COUNT(*) AS adet, "
            "substr(baslangic, 12, 2) AS saat FROM bardaklar WHERE gun = ? "
            "GROUP BY ham ORDER BY ham",
            (gun,),
        )
    ]
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
            "gunler": gunler,
            "bolge_musteri_var": len(bolgeler.get("musteri", [])) >= 3,
            "bolge_barista_var": len(bolgeler.get("barista", [])) >= 3,
            "hassasiyet": (db_ayarlar.get("tespit_hassasiyeti", "0.30")).replace(".", ","),
            "durum": getattr(analiz, "durum", "başlatılmadı"),
            "canli_bardak": getattr(analiz, "canli_bardak", 0),
            "canli_kisi": getattr(analiz, "canli_kisi", 0),
            "model_hatasi": getattr(analiz, "model_hatasi", None),
            "kaynak_hatasi": getattr(analiz, "kaynak_hatasi", None),
            "kaynak": istek.app.state.ayarlar.kaynak,
            "hata": hata,
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
def canli(istek: Request, gun: str = "", baglanti=Depends(baglanti_al)):
    gun = gun or zaman.bugun()
    analiz = getattr(istek.app.state, "analiz", None)
    return {
        **_ozet(baglanti, gun),
        "canli_bardak": getattr(analiz, "canli_bardak", 0),
        "canli_kisi": getattr(analiz, "canli_kisi", 0),
        "durum": getattr(analiz, "durum", "başlatılmadı"),
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
