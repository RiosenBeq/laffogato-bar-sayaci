"""İsteğe bağlı panel şifresi: kapalıyken görünmez, açıkken korur."""

from __future__ import annotations

from dataclasses import replace


def test_sifre_kapaliyken_giris_istenmez(istemci):
    assert istemci.get("/", follow_redirects=False).status_code == 200


def _sifreli_istemci(ayarlar, sifre: str = "cok-gizli"):
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    sifreli = replace(ayarlar, panel_sifresi=sifre)
    return TestClient(uygulama_olustur(sifreli, analiz_ac=False))


def test_sifre_acikken_sayfalar_girise_yonlenir(ayarlar):
    with _sifreli_istemci(ayarlar) as istemci:
        yanit = istemci.get("/", follow_redirects=False)
        assert yanit.status_code == 303
        assert yanit.headers["location"] == "/giris"
        # statik dosyalar ve giriş sayfası serbest
        assert istemci.get("/giris").status_code == 200
        assert istemci.get("/static/stil.css").status_code == 200


def test_dogru_sifre_oturum_acar_yanlis_acmaz(ayarlar):
    with _sifreli_istemci(ayarlar) as istemci:
        yanlis = istemci.post("/giris", data={"sifre": "yanlis"}, follow_redirects=False)
        assert "hata=1" in yanlis.headers["location"]
        assert istemci.get("/", follow_redirects=False).status_code == 303

        dogru = istemci.post("/giris", data={"sifre": "cok-gizli"}, follow_redirects=False)
        assert dogru.headers["location"] == "/"
        assert istemci.get("/", follow_redirects=False).status_code == 200
        # çerezde şifre düz metin durmaz
        assert "cok-gizli" not in "".join(istemci.cookies.values())

        istemci.post("/cikis", follow_redirects=False)
        assert istemci.get("/", follow_redirects=False).status_code == 303


def test_turkce_sifre_kullaniciyi_kilitlemez(ayarlar):
    """KRİTİK ESKİ HATA: hmac.compare_digest METİN karşılaştırmasında ASCII dışı
    karakteri kabul etmez, TypeError fırlatır. PANEL_SIFRESI=şifre123 yazan bir
    kullanıcı için giriş KALICI olarak 500 veriyordu: doğru şifreyle bile
    panele hiç girilemiyordu. Bayta çevirip karşılaştırmak sorunu çözer ve
    zamanlama güvenliğini korur."""
    with _sifreli_istemci(ayarlar, "şifre123") as istemci:
        yanlis = istemci.post("/giris", data={"sifre": "yanlış"}, follow_redirects=False)
        assert yanlis.status_code == 303, "ASCII dışı YANLIŞ şifre 500 vermemeli"
        assert "hata=1" in yanlis.headers["location"]

        dogru = istemci.post("/giris", data={"sifre": "şifre123"}, follow_redirects=False)
        assert dogru.status_code == 303
        assert dogru.headers["location"] == "/", "doğru Türkçe şifre kabul edilmeli"
        assert istemci.get("/", follow_redirects=False).status_code == 200


def test_ayni_uzunlukta_yanlis_sifre_kabul_edilmez(ayarlar):
    """Bayta çevirme, karşılaştırmayı gevşetmemeli."""
    with _sifreli_istemci(ayarlar, "şifre123") as istemci:
        yanit = istemci.post("/giris", data={"sifre": "sifre123"}, follow_redirects=False)
        assert "hata=1" in yanit.headers["location"], "noktasız i ile giriş olmamalı"
