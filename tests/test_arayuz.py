"""Arayüz testleri: sayaçlar, bölge tanımı, rapor, görsel servisi."""

from __future__ import annotations

import json

from app import veritabani, zaman
from app.bardak import BARISTA, BELIRSIZ, MUSTERI

UCGEN = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]


def _bardak_ekle(ayarlar, takip_id: int, kime: str, gun=None):
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT OR IGNORE INTO bardaklar (gun, takip_id, baslangic, bitis, kime) "
            "VALUES (?, ?, ?, ?, ?)",
            (gun or zaman.bugun(), takip_id, simdi, simdi, kime),
        )
        baglanti.commit()
    finally:
        baglanti.close()


def test_ana_sayfa_acilir(istemci):
    yanit = istemci.get("/")
    assert yanit.status_code == 200
    assert "Laffogato" in yanit.text
    assert "bardak yapıldı" in yanit.text
    assert "müşteri içti" in yanit.text
    assert "barista kendine" in yanit.text


def test_sayimlar_dogru_dagitiliyor(istemci, ayarlar):
    for i, kime in enumerate([MUSTERI, MUSTERI, MUSTERI, BARISTA, BELIRSIZ], start=1):
        _bardak_ekle(ayarlar, i, kime)
    canli = istemci.get("/canli").json()
    assert canli["toplam"] == 5
    assert canli["musteri"] == 3
    assert canli["barista"] == 1
    assert canli["belirsiz"] == 1
    # Yüzdeler sayfada: 3/5 müşteri = %60, 1/5 barista = %20
    sayfa = istemci.get("/").text
    assert 'id="s-musteri-yuzde">60<' in sayfa
    assert 'id="s-barista-yuzde">20<' in sayfa


def test_ayni_bardak_iki_kez_sayilmaz(istemci, ayarlar):
    _bardak_ekle(ayarlar, 9, MUSTERI)
    _bardak_ekle(ayarlar, 9, BARISTA)  # aynı gün + aynı takip → UNIQUE engeller
    assert istemci.get("/canli").json()["toplam"] == 1


def test_bolge_kaydetme_ve_silme(istemci, ayarlar):
    yanit = istemci.post(
        "/bolge",
        data={"taraf": "musteri", "poligon": json.dumps(UCGEN)},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        assert len(veritabani.bolgeleri_oku(baglanti)["musteri"]) == 3
    finally:
        baglanti.close()
    assert "çizildi" in istemci.get("/").text

    istemci.post("/bolge/musteri/sil", follow_redirects=False)
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        assert veritabani.bolgeleri_oku(baglanti)["musteri"] == []
    finally:
        baglanti.close()


def test_eksik_bolge_reddedilir(istemci):
    yanit = istemci.post(
        "/bolge",
        data={"taraf": "barista", "poligon": json.dumps([[0.1, 0.1], [0.5, 0.5]])},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert "hata=" in yanit.headers["location"]
    assert "3 köşe" in istemci.get(yanit.headers["location"]).text


def test_gecersiz_taraf_reddedilir(istemci):
    yanit = istemci.post(
        "/bolge", data={"taraf": "sef", "poligon": json.dumps(UCGEN)}, follow_redirects=False
    )
    assert "hata=" in yanit.headers["location"]


def test_bozuk_bolge_kaydi_sistemi_bozmaz(istemci, ayarlar):
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani)
    try:
        veritabani.ayar_yaz(baglanti, "bolge_musteri", "bu json değil")
        assert veritabani.bolgeleri_oku(baglanti)["musteri"] == []
    finally:
        baglanti.close()
    assert istemci.get("/").status_code == 200


def test_csv_raporu(istemci, ayarlar):
    _bardak_ekle(ayarlar, 3, BARISTA)
    yanit = istemci.get("/rapor.csv")
    assert yanit.status_code == 200
    assert "Gün;Saat;Kime" in yanit.text
    assert "Barista kendine" in yanit.text


def test_sifirlama(istemci, ayarlar):
    _bardak_ekle(ayarlar, 4, MUSTERI)
    assert istemci.get("/canli").json()["toplam"] == 1
    istemci.post("/sifirla", data={"gun": zaman.bugun()}, follow_redirects=False)
    assert istemci.get("/canli").json()["toplam"] == 0


def test_gorsel_yolu_disari_cikamaz(istemci, ayarlar):
    (ayarlar.goruntu_klasoru / "bardak.jpg").write_bytes(b"sahte-jpeg")
    assert istemci.get("/gorsel/bardak.jpg").content == b"sahte-jpeg"
    assert istemci.get("/gorsel/../laffogato.db").status_code == 404


def test_kamera_yokken_onizleme_204(istemci):
    assert istemci.get("/onizleme.jpg").status_code == 204


def test_kaynak_cozumleme(ayarlar):
    from dataclasses import replace

    assert ayarlar.kaynak_cozumle() == 0  # "0" → bilgisayar kamerası
    assert replace(ayarlar, kaynak="1").kaynak_cozumle() == 1
    rtsp = "rtsp://kamera.local/stream"
    assert replace(ayarlar, kaynak=rtsp).kaynak_cozumle() == rtsp


def test_statik_dosya_surumleri_esit():
    """Şablonlar aynı stil.css'i farklı `?v=` ile isterse tarayıcı iki ayrı
    kopya önbelleğe alır: bir sayfa yeni CSS'i alır, öbürü eski kalır ve
    "bende düzeldi, sende düzelmedi" tablosu çıkar. Stil/JS değiştiğinde
    numara HER şablonda birden artırılmalı."""
    import re
    from pathlib import Path

    sablonlar = Path(__file__).resolve().parents[1] / "app" / "web" / "templates"
    surumler = {}
    for yol in sorted(sablonlar.glob("*.html")):
        metin = yol.read_text(encoding="utf-8")
        for dosya, surum in re.findall(r"/static/([\w.-]+\.(?:css|js))\?v=(\d+)", metin):
            surumler.setdefault(surum, []).append(f"{yol.name}:{dosya}")
    assert surumler, "şablonlarda sürümlü statik dosya çağrısı bulunamadı"
    assert len(surumler) == 1, f"karışık sürüm numaraları: {surumler}"


def test_teknoloji_karti_marka_adiyla_gorunur(istemci):
    """Kullanıcı ekranda kütüphane/dosya adı değil kademe adı görmeli.
    conftest'teki ayarlar tanınmayan bir dosyayı işaret ettiği için
    "özel model" beklenir."""
    sayfa = istemci.get("/").text
    assert "Nesne tanıma: NextGen AI (özel model)" in sayfa


def test_ekranda_teknik_kutuphane_adlari_gecmez():
    """Şablonlarda model kütüphanesinin adı, veri kümesi adı, üretici adı ya
    da dosya uzantısı görünmemeli — kullanıcıya tek ad tanıtılır: NextGen AI.
    (Lisans atfı LICENSE-THIRD-PARTY dosyasındadır, ekranda değil.)"""
    import re
    from pathlib import Path

    yasakli = re.compile(r"yolox|megvii|\bcoco\b|onnx", re.IGNORECASE)
    kok = Path(__file__).resolve().parents[1] / "app" / "web"
    for klasor in ("templates", "static"):
        for yol in sorted((kok / klasor).iterdir()):
            if yol.suffix.lower() not in (".html", ".js", ".css"):
                continue
            metin = yol.read_text(encoding="utf-8")
            bulunan = yasakli.findall(metin)
            assert not bulunan, f"{yol.name} içinde ekrana çıkan teknik ad: {bulunan}"
