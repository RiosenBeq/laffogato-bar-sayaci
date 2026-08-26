"""Bardak kararının SAF mantığı — kamera, model ve veritabanı bağımsız.

Soru: yapılan bir bardak müşteriye mi gitti, barista kendine mi yaptı?

Yöntem: her bardak takibi (track) yaşadığı süre boyunca hangi bölgede
görüldüğü sayılır. Bardak kadrajdan çıkınca karar verilir:
- Ağırlıklı olarak MÜŞTERİ tarafında görüldüyse → müşteriye gitti
- Ağırlıklı olarak BARİSTA tarafında kaldıysa → barista kendine yaptı
- İkisi de belirgin değilse → belirsiz (uydurma sayı üretilmez)

Neden takip bazlı: tek karede bardak tezgâhın üstündeyken de görünür;
"nereye gitti" sorusunun cevabı ancak zaman içindeki yolculuğundadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MUSTERI = "musteri"
BARISTA = "barista"
BELIRSIZ = "belirsiz"

# Bir bardağın sayılması için en az kaç karede görülmesi gerektiği:
# tek karelik yanlış tespit günlük sayacı şişirmesin.
EN_AZ_GORULME = 4

# Kararın verilebilmesi için baskın tarafın gözlem oranı
BASKINLIK_ORANI = 0.60


@dataclass
class BardakDurumu:
    """Tek bir bardak takibinin biriken gözlemleri."""

    takip_id: int
    ilk_zaman: str
    son_zaman: str
    gorulme: int = 0
    bolge_sayaci: dict[str, int] = field(default_factory=dict)
    foto: str | None = None

    def gozlem_ekle(self, bolge: str, zaman_utc: str) -> None:
        self.gorulme += 1
        self.son_zaman = zaman_utc
        if bolge:
            self.bolge_sayaci[bolge] = self.bolge_sayaci.get(bolge, 0) + 1

    def sayilir_mi(self) -> bool:
        return self.gorulme >= EN_AZ_GORULME

    def karar(self) -> str:
        """Bardağın kime gittiği. Kanıt zayıfsa 'belirsiz'."""
        musteri = self.bolge_sayaci.get(MUSTERI, 0)
        barista = self.bolge_sayaci.get(BARISTA, 0)
        toplam = musteri + barista
        if toplam == 0:
            return BELIRSIZ  # hiç bölgede görülmedi (bölgeler çizilmemiş olabilir)
        if musteri / toplam >= BASKINLIK_ORANI:
            return MUSTERI
        if barista / toplam >= BASKINLIK_ORANI:
            return BARISTA
        return BELIRSIZ  # bardak iki taraf arasında gidip geldi, emin değiliz


def nokta_poligonda(nokta: tuple[float, float], poligon: list[tuple[float, float]]) -> bool:
    """Işın yöntemi. Nokta ve poligon aynı uzayda (normalize 0-1) olmalı."""
    if len(poligon) < 3:
        return False
    x, y = nokta
    icinde = False
    n = len(poligon)
    for i in range(n):
        x1, y1 = poligon[i]
        x2, y2 = poligon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            kesisim = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < kesisim:
                icinde = not icinde
    return icinde


def bolge_bul(
    nokta_normalize: tuple[float, float], bolgeler: dict[str, list[tuple[float, float]]]
) -> str:
    """Nokta hangi bölgede? Hiçbirinde değilse boş metin.

    Bölgeler çakışırsa müşteri tarafı önceliklidir: teslim edilmiş bir
    bardağı barista hanesine yazmak, tersinden daha yanıltıcıdır.
    """
    for ad in (MUSTERI, BARISTA):
        poligon = bolgeler.get(ad) or []
        if poligon and nokta_poligonda(nokta_normalize, poligon):
            return ad
    return ""


def gunluk_ozet(kararlar: list[str]) -> dict[str, int]:
    """Gün sonu tablosu: toplam / müşteri / barista / belirsiz."""
    return {
        "toplam": len(kararlar),
        MUSTERI: sum(1 for k in kararlar if k == MUSTERI),
        BARISTA: sum(1 for k in kararlar if k == BARISTA),
        BELIRSIZ: sum(1 for k in kararlar if k == BELIRSIZ),
    }
