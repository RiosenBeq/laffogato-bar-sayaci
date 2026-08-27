"""İsteğe bağlı panel girişi.

.env'deki PANEL_SIFRESI boşsa (varsayılan) uygulama şifresiz açılır.
Doldurulursa tüm sayfalar girişe yönlenir; şifre doğruysa imzalı bir
çerezle oturum açılır. Şifre çerezde TUTULMAZ — yalnızca türetilmiş imza.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

CEREZ_ADI = "panel_oturum"

router = APIRouter()


def _imza(sifre: str) -> str:
    return hmac.new(sifre.encode("utf-8"), b"panel-oturumu", hashlib.sha256).hexdigest()


def oturum_gecerli(istek: Request) -> bool:
    sifre = istek.app.state.ayarlar.panel_sifresi
    if not sifre:
        return True
    cerez = istek.cookies.get(CEREZ_ADI, "")
    return hmac.compare_digest(cerez, _imza(sifre))


@router.get("/giris", response_class=HTMLResponse)
def giris_sayfasi(istek: Request):
    from app.web.rotalar import sablonlar

    if oturum_gecerli(istek):
        return RedirectResponse("/", status_code=303)
    return sablonlar.TemplateResponse(
        istek, "giris.html", {"hata": istek.query_params.get("hata", "")}
    )


@router.post("/giris")
def giris_yap(istek: Request, sifre: str = Form("")):
    beklenen = istek.app.state.ayarlar.panel_sifresi
    if not beklenen or not hmac.compare_digest(sifre, beklenen):
        return RedirectResponse("/giris?hata=1", status_code=303)
    yanit = RedirectResponse("/", status_code=303)
    yanit.set_cookie(CEREZ_ADI, _imza(beklenen), httponly=True, samesite="lax")
    return yanit


@router.post("/cikis")
def cikis():
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(CEREZ_ADI)
    return yanit


async def giris_bekcisi(istek: Request, sonraki):
    """Şifre ayarlıysa korunan yolları girişe yönlendirir (middleware)."""
    yol = istek.url.path
    serbest = yol == "/giris" or yol.startswith("/static")
    if not serbest and not oturum_gecerli(istek):
        return RedirectResponse("/giris", status_code=303)
    return await sonraki(istek)
