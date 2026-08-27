"""Web üzerinden fotoğraf ve video yükleme akışları.

Model dosyası testte yoktur; tarama "model yüklenemedi" uyarısıyla döner ama
yükleme, kare çıkarma ve sayfa akışı gerçek koddan geçer.
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import cv2
import numpy as np


def _jpeg_bayt(tohum: int = 1) -> bytes:
    rastgele = np.random.default_rng(tohum)
    gorsel = rastgele.integers(0, 255, size=(120, 160, 3), dtype=np.uint8)
    return cv2.imencode(".jpg", gorsel)[1].tobytes()


def _mp4_bayt(tmp_path, kare_sayisi: int = 30) -> bytes:
    yol = tmp_path / "ornek.mp4"
    yazici = cv2.VideoWriter(str(yol), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for i in range(kare_sayisi):
        kare = np.full((120, 160, 3), (i * 8 % 255, 80, 160), dtype=np.uint8)
        yazici.write(kare)
    yazici.release()
    return yol.read_bytes()


def _yonlendirme_parametresi(yanit, ad: str) -> str:
    sorgu = parse_qs(urlparse(unquote(yanit.headers["location"])).query)
    return sorgu[ad][0]


# ---- kütüphane yükleme akışı ----


def test_fotografsiz_nesne_olusturulamaz(istemci):
    yanit = istemci.post("/kutuphane/nesne", data={"ad": "Fincan"}, follow_redirects=False)
    assert yanit.status_code == 303
    assert "Fotoğraf seçilmedi" in _yonlendirme_parametresi(yanit, "hata")
    # Yarım nesne kalmadı
    assert "Fincan" not in istemci.get("/kutuphane").text


def test_nesne_fotografla_olusur_ve_basari_mesaji_doner(istemci):
    yanit = istemci.post(
        "/kutuphane/nesne",
        data={"ad": "Servis aracı"},
        files=[
            ("fotograflar", ("a.jpg", _jpeg_bayt(1), "image/jpeg")),
            ("fotograflar", ("b.jpg", _jpeg_bayt(2), "image/jpeg")),
        ],
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    mesaj = _yonlendirme_parametresi(yanit, "mesaj")
    assert "2 fotoğraf eklendi" in mesaj
    sayfa = istemci.get(yanit.headers["location"]).text
    assert "Servis aracı" in sayfa
    assert "2 fotoğraf eklendi" in sayfa


def test_tumu_bozuksa_nesne_geri_alinir(istemci):
    yanit = istemci.post(
        "/kutuphane/nesne",
        data={"ad": "Bozuk deneme"},
        files=[("fotograflar", ("bozuk.jpg", b"jpeg degil", "image/jpeg"))],
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert "okunamadı" in _yonlendirme_parametresi(yanit, "hata")
    assert "Bozuk deneme" not in istemci.get("/kutuphane").text


def test_karisik_yuklemede_saglamlar_eklenir_bozuk_bildirilir(istemci):
    yanit = istemci.post(
        "/kutuphane/nesne",
        data={"ad": "Karışık"},
        files=[
            ("fotograflar", ("iyi.jpg", _jpeg_bayt(3), "image/jpeg")),
            ("fotograflar", ("bozuk.jpg", b"jpeg degil", "image/jpeg")),
        ],
        follow_redirects=False,
    )
    mesaj = _yonlendirme_parametresi(yanit, "mesaj")
    assert "1 fotoğraf eklendi" in mesaj
    assert "1 dosya alınamadı" in mesaj


# ---- tarama: fotoğraf ve video ----


def test_dosyasiz_tarama_uyari_verir(istemci):
    yanit = istemci.post("/tarama", data={"esik_yuzde": "42"}, follow_redirects=False)
    assert yanit.status_code == 303
    assert "Dosya seçilmedi" in _yonlendirme_parametresi(yanit, "hata")


def test_fotograf_taramasi_calisir(istemci):
    yanit = istemci.post(
        "/tarama",
        data={"esik_yuzde": "42"},
        files=[("kareler", ("kare.jpg", _jpeg_bayt(), "image/jpeg"))],
    )
    assert yanit.status_code == 200
    assert "kare.jpg" in yanit.text
    assert "1 kare tarandı" in yanit.text


def test_video_yuklenince_kareler_ornekleniyor(istemci, tmp_path):
    veri = _mp4_bayt(tmp_path, kare_sayisi=30)
    yanit = istemci.post(
        "/tarama",
        data={"esik_yuzde": "42"},
        files=[("kareler", ("ornek.mp4", veri, "video/mp4"))],
    )
    assert yanit.status_code == 200
    # 30 karelik videodan 8 kare örneklenir
    assert "8 kare tarandı" in yanit.text
    assert "ornek.mp4 — kare 1/8" in yanit.text
    assert "ornek.mp4 — kare 8/8" in yanit.text


def test_bozuk_video_anlasilir_uyari_verir(istemci):
    yanit = istemci.post(
        "/tarama",
        data={"esik_yuzde": "42"},
        files=[("kareler", ("bozuk.mp4", b"video degil", "video/mp4"))],
    )
    assert yanit.status_code == 200
    assert "video olarak açılamadı" in yanit.text


def test_video_ve_fotograf_birlikte_taranir(istemci, tmp_path):
    veri = _mp4_bayt(tmp_path, kare_sayisi=20)
    yanit = istemci.post(
        "/tarama",
        data={"esik_yuzde": "42"},
        files=[
            ("kareler", ("kare.jpg", _jpeg_bayt(), "image/jpeg")),
            ("kareler", ("ornek.mp4", veri, "video/mp4")),
        ],
    )
    assert yanit.status_code == 200
    # 1 fotoğraf + 8 video karesi
    assert "9 kare tarandı" in yanit.text
