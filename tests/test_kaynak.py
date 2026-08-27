"""Görüntü kaynağı ayarları: doğrulama, .env'e yazma, bağlantı sınama.

Testlerde analiz kapalıdır (analiz_ac=False); kaydetme akışı .env + ayarlar
değişimini yapar ama analiz yeniden başlatma adımını atlar — kamera gerekmez.
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import cv2
import numpy as np


def _yonlendirme_parametresi(yanit, ad: str) -> str:
    sorgu = parse_qs(urlparse(unquote(yanit.headers["location"])).query)
    return sorgu[ad][0]


def _ornek_video(yol, kare_sayisi: int = 10) -> None:
    yazici = cv2.VideoWriter(str(yol), cv2.VideoWriter_fourcc(*"mp4v"), 5, (160, 120))
    for i in range(kare_sayisi):
        yazici.write(np.full((120, 160, 3), (i * 20 % 255, 90, 150), dtype=np.uint8))
    yazici.release()


# ---- doğrulama ----


def test_gecersiz_kamera_no_reddedilir(istemci):
    yanit = istemci.post(
        "/ayarlar/kaynak", data={"tur": "kamera", "kamera_no": "abc"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "Kamera numarası" in _yonlendirme_parametresi(yanit, "hata")


def test_rtsp_olmayan_adres_reddedilir(istemci):
    yanit = istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "rtsp", "rtsp_adres": "192.168.1.50"},
        follow_redirects=False,
    )
    assert "rtsp://" in _yonlendirme_parametresi(yanit, "hata")


def test_olmayan_dosya_reddedilir(istemci):
    yanit = istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "dosya", "dosya_yolu": "veri/olmayan.mp4"},
        follow_redirects=False,
    )
    assert "bulunamadı" in _yonlendirme_parametresi(yanit, "hata")


# ---- kaydetme ----


def test_dosya_kaynagi_kaydedilir_ve_enve_yazilir(istemci, ayarlar):
    (ayarlar.kok / "veri" / "kayit.mp4").write_bytes(b"x")
    yanit = istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "dosya", "dosya_yolu": "veri/kayit.mp4"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert "kaydedildi" in _yonlendirme_parametresi(yanit, "mesaj")
    assert "KAYNAK=veri/kayit.mp4" in (ayarlar.kok / ".env").read_text(encoding="utf-8")
    assert istemci.app.state.ayarlar.kaynak == "veri/kayit.mp4"
    # Başarı mesajı sayfada görünür
    assert "kaydedildi" in istemci.get(yanit.headers["location"]).text


def test_kamera_kaynagi_kaydedilir_ve_secim_hatirlanir(istemci, ayarlar):
    yanit = istemci.post(
        "/ayarlar/kaynak", data={"tur": "kamera", "kamera_no": "1"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "KAYNAK=1" in (ayarlar.kok / ".env").read_text(encoding="utf-8")
    sayfa = istemci.get("/").text
    assert 'value="kamera" checked' in sayfa  # arayüz doğru kartı seçili gösterir


def test_env_yeniden_yazildiginda_diger_satirlar_korunur(istemci, ayarlar):
    (ayarlar.kok / ".env").write_text("KARE_FPS=3\nKAYNAK=eski.mp4\nCIHAZ=cpu\n", encoding="utf-8")
    (ayarlar.kok / "veri" / "yeni.mp4").write_bytes(b"x")
    istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "dosya", "dosya_yolu": "veri/yeni.mp4"},
        follow_redirects=False,
    )
    icerik = (ayarlar.kok / ".env").read_text(encoding="utf-8")
    assert "KARE_FPS=3" in icerik and "CIHAZ=cpu" in icerik
    assert "KAYNAK=veri/yeni.mp4" in icerik and "eski.mp4" not in icerik


# ---- bağlantı sınama ----


def test_sina_gecersiz_girdide_anlasilir_mesaj(istemci):
    yanit = istemci.post("/ayarlar/kaynak/sina", data={"tur": "rtsp", "rtsp_adres": "abc"})
    veri = yanit.json()
    assert veri["ok"] is False
    assert "rtsp://" in veri["mesaj"]


def test_sina_bozuk_dosyada_baglanamadi_der(istemci, ayarlar):
    (ayarlar.kok / "veri" / "bozuk.mp4").write_bytes(b"video degil")
    yanit = istemci.post(
        "/ayarlar/kaynak/sina", data={"tur": "dosya", "dosya_yolu": "veri/bozuk.mp4"}
    )
    veri = yanit.json()
    assert veri["ok"] is False
    assert veri["gorsel"] is None


def test_sina_gecerli_videoda_onizleme_doner(istemci, ayarlar):
    _ornek_video(ayarlar.kok / "veri" / "gercek.mp4")
    yanit = istemci.post(
        "/ayarlar/kaynak/sina", data={"tur": "dosya", "dosya_yolu": "veri/gercek.mp4"}
    )
    veri = yanit.json()
    assert veri["ok"] is True
    assert "başarılı" in veri["mesaj"]
    assert veri["gorsel"].startswith("data:image/jpeg;base64,")


# ---- sertleştirme: enjeksiyon ve şifre gizliliği ----


def test_rtsp_satir_sonu_enjeksiyonu_engellenir(istemci, ayarlar):
    yanit = istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "rtsp", "rtsp_adres": "rtsp://x\nCIHAZ=cuda"},
        follow_redirects=False,
    )
    assert "hata=" in yanit.headers["location"]
    env = ayarlar.kok / ".env"
    assert not env.exists() or "CIHAZ=cuda" not in env.read_text(encoding="utf-8")


def test_rtsp_sifresi_sayfada_gorunmez(istemci):
    istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "rtsp", "rtsp_adres": "rtsp://ali:gizli123@10.0.0.5:554/s1"},
        follow_redirects=False,
    )
    sayfa = istemci.get("/").text
    assert "gizli123" not in sayfa  # şifre ne metinde ne form alanında görünür
    assert "rtsp://ali:••••@10.0.0.5:554/s1" in sayfa


# ---- yeniden başlatma dalı ve ek doğrulamalar ----


def test_kaydet_calisan_analizi_durdurup_yenisini_kurar(istemci, ayarlar):
    """Gerçek akış: eski analiz durdurulur, yerine YENİ bir Analiz kurulur."""
    from app.analiz import Analiz

    class SahteAnaliz:
        durduruldu = False

        def durdur(self):
            self.durduruldu = True
            return True

    sahte = SahteAnaliz()
    istemci.app.state.analiz = sahte
    (ayarlar.kok / "veri" / "yeni-kaynak.mp4").write_bytes(b"x")
    yanit = istemci.post(
        "/ayarlar/kaynak",
        data={"tur": "dosya", "dosya_yolu": "veri/yeni-kaynak.mp4"},
        follow_redirects=False,
    )
    try:
        assert "yeniden başlatıldı" in _yonlendirme_parametresi(yanit, "mesaj")
        assert sahte.durduruldu is True
        yeni = istemci.app.state.analiz
        assert isinstance(yeni, Analiz)
        assert yeni.ayarlar.kaynak == "veri/yeni-kaynak.mp4"
    finally:
        analiz = istemci.app.state.analiz
        if hasattr(analiz, "_is"):
            analiz.durdur()  # arka plan iş parçacığı test bitince kapanmalı
        istemci.app.state.analiz = None


def test_mutlak_yol_ve_ust_dizin_reddedilir(istemci, tmp_path):
    disarida = tmp_path.parent / "disarida.mp4"
    disarida.write_bytes(b"x")
    for yol in (str(disarida), "../disarida.mp4"):
        yanit = istemci.post(
            "/ayarlar/kaynak", data={"tur": "dosya", "dosya_yolu": yol}, follow_redirects=False
        )
        assert "proje klasörünün içinde" in _yonlendirme_parametresi(yanit, "hata")


def test_ascii_olmayan_rakam_reddedilir(istemci):
    for deger in ("٥", "²"):  # Arapça rakam, üst simge — int() ile uyuşmaz
        yanit = istemci.post(
            "/ayarlar/kaynak", data={"tur": "kamera", "kamera_no": deger}, follow_redirects=False
        )
        assert "Kamera numarası" in _yonlendirme_parametresi(yanit, "hata")


def test_bosluklu_dosya_adi_tirnaklanir_ve_geri_okunur(ayarlar):
    from dotenv import dotenv_values

    from app import ayarlar as ayarlar_modulu

    ayarlar_modulu.kaynagi_kaydet(ayarlar.kok, "veri/oda #2 kaydi.mp4")
    okunan = dotenv_values(ayarlar.kok / ".env")["KAYNAK"]
    assert okunan == "veri/oda #2 kaydi.mp4"  # '#' yorum sanılıp kesilmemeli
