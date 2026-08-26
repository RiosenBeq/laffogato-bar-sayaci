"""Bardak karar mantığı testleri — kamerasız, saniyeler içinde."""

from __future__ import annotations

from app.bardak import (
    BARISTA,
    BELIRSIZ,
    EN_AZ_GORULME,
    MUSTERI,
    BardakDurumu,
    bolge_bul,
    gunluk_ozet,
    nokta_poligonda,
)

SOL_YARI = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]
SAG_YARI = [(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)]
BOLGELER = {MUSTERI: SAG_YARI, BARISTA: SOL_YARI}


def durum(takip_id: int = 1) -> BardakDurumu:
    return BardakDurumu(
        takip_id=takip_id,
        ilk_zaman="2026-08-26T10:00:00+00:00",
        son_zaman="2026-08-26T10:00:00+00:00",
    )


def test_musteri_tarafinda_kalan_bardak_musteriye_gider():
    b = durum()
    for _ in range(10):
        b.gozlem_ekle(MUSTERI, "2026-08-26T10:00:05+00:00")
    assert b.sayilir_mi()
    assert b.karar() == MUSTERI


def test_barista_tarafinda_kalan_bardak_baristaya_yazilir():
    b = durum()
    for _ in range(10):
        b.gozlem_ekle(BARISTA, "2026-08-26T10:00:05+00:00")
    assert b.karar() == BARISTA


def test_tezgahta_hazirlanip_musteriye_giden_bardak():
    # Gerçek akış: bardak barista tarafında hazırlanır, sonra müşteriye gider.
    # Baskın taraf müşteri olduğunda müşteriye yazılmalı.
    b = durum()
    for _ in range(3):
        b.gozlem_ekle(BARISTA, "2026-08-26T10:00:02+00:00")
    for _ in range(12):
        b.gozlem_ekle(MUSTERI, "2026-08-26T10:00:20+00:00")
    assert b.karar() == MUSTERI


def test_iki_taraf_arasinda_gidip_gelen_bardak_belirsiz():
    # Kanıt zayıfsa TAHMİN YÜRÜTÜLMEZ — sayı uydurmak raporu bozar
    b = durum()
    for _ in range(6):
        b.gozlem_ekle(MUSTERI, "2026-08-26T10:00:10+00:00")
        b.gozlem_ekle(BARISTA, "2026-08-26T10:00:11+00:00")
    assert b.karar() == BELIRSIZ


def test_hic_bolgede_gorulmeyen_bardak_belirsiz():
    # Bölgeler çizilmemişse veya bardak iki alanın dışındaysa
    b = durum()
    for _ in range(10):
        b.gozlem_ekle("", "2026-08-26T10:00:10+00:00")
    assert b.karar() == BELIRSIZ


def test_tek_karelik_yanlis_tespit_sayilmaz():
    b = durum()
    for _ in range(EN_AZ_GORULME - 1):
        b.gozlem_ekle(MUSTERI, "2026-08-26T10:00:01+00:00")
    assert not b.sayilir_mi()  # günlük sayaca girmez
    b.gozlem_ekle(MUSTERI, "2026-08-26T10:00:02+00:00")
    assert b.sayilir_mi()


def test_bolge_bulma():
    assert bolge_bul((0.8, 0.5), BOLGELER) == MUSTERI
    assert bolge_bul((0.2, 0.5), BOLGELER) == BARISTA
    # Bölgesiz alan
    assert bolge_bul((0.8, 0.5), {}) == ""


def test_cakisan_bolgede_musteri_onceliklidir():
    # Teslim edilmiş bardağı barista hanesine yazmak daha yanıltıcı olurdu
    cakisan = {MUSTERI: SOL_YARI, BARISTA: SOL_YARI}
    assert bolge_bul((0.2, 0.5), cakisan) == MUSTERI


def test_nokta_poligonda():
    assert nokta_poligonda((0.25, 0.5), SOL_YARI)
    assert not nokta_poligonda((0.75, 0.5), SOL_YARI)
    assert not nokta_poligonda((0.5, 0.5), [(0, 0), (1, 0)])  # eksik poligon


def test_gunluk_ozet():
    ozet = gunluk_ozet([MUSTERI, MUSTERI, BARISTA, BELIRSIZ, MUSTERI])
    assert ozet == {"toplam": 5, MUSTERI: 3, BARISTA: 1, BELIRSIZ: 1}
    assert gunluk_ozet([]) == {"toplam": 0, MUSTERI: 0, BARISTA: 0, BELIRSIZ: 0}
