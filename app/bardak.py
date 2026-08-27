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
    # Tekrar koruması için: bardağın son görüldüğü yer/boy ve renk imzası
    son_merkez: tuple[float, float] = (0.0, 0.0)
    son_boyut: tuple[float, float] = (0.0, 0.0)
    renk_imzasi: tuple[float, ...] | None = None
    # Az önce kapanmış bir bardağın devamı olarak işaretlendiyse sayılmaz
    tekrar_mi: bool = False

    def gozlem_ekle(self, bolge: str, zaman_utc: str) -> None:
        self.gorulme += 1
        self.son_zaman = zaman_utc
        if bolge:
            self.bolge_sayaci[bolge] = self.bolge_sayaci.get(bolge, 0) + 1

    def sayilir_mi(self) -> bool:
        """Sayıma girer mi? Tekrar sayım koruması işaretlediyse GİRMEZ."""
        return self.gorulme >= EN_AZ_GORULME and not self.tekrar_mi

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


# ---------------------------------------------------------------- tekrar koruması
#
# Sorun (README'nin kendi kabul ettiği sınır): tezgâhta bekleyen bardak
# barista önünden geçerken kapanır, takipçi izi düşürür, bardak yeniden
# göründüğünde YENİ takip numarası alır ve ikinci kez sayılır.
#
# Birinci savunma analiz.py'dedir (takipçinin hafızası saniye cinsinden
# ayarlanır). Bu ikinci savunma, oradan kaçanı yakalar: kapanan her bardağın
# yeri, boyu ve renk imzası kısa süre hatırlanır; aynı yerde aynı görünümle
# yeni bir iz açılırsa bu "devam" sayılır ve tekrar sayılmaz.
#
# Renk imzası neden? Bu projenin kendi kırpıklarında ölçüldü: ORB desen
# kanıtı medyan 1 anahtar nokta veriyor (kutuphane.py eşiği 8) — yani desen
# bu görüntülerde tutunacak bir iz DEĞİL. Renk histogramı çalışıyor.

# Kapanan bardak bu kadar saniye hatırlanır — BİLEREK ÇOK KISA.
#
# Neden kısa: bu koruma yalnızca takipçinin hafızasının BİTTİĞİ andan hemen
# sonraki boşluğu kapatmalıdır. Ölçüldü ki uzun pencere felakete yol açıyor:
# 90 sn'lik pencereyle, tezgâhın aynı noktasında 60 sn'de bir hazırlanan
# 10 gerçek bardağın 9'u "aynı bardak" sanılıp SAYILMADI. Sebebi basit —
# bir kafede bardaklar zaten birbirinin aynısıdır ve hep aynı noktaya konur;
# renk ve konum, "aynı bardak mı" sorusunu ayırt etmeye yetmez.
# (Ölçüm: rastgele bardak kırpığı çiftlerinin %97,9'u renk eşiğini aşıyor.)
#
# Asıl koruma bu değil, takipçinin hafızasıdır (_IZ_HAFIZASI_SN): o süre
# içinde ByteTrack bardağa AYNI takip numarasını geri verir ve
# UNIQUE (gun, takip_id) kısıtı ikinci kaydı zaten engeller.
TEKRAR_PENCERESI_SN = 10.0
# Merkezler bu normalize mesafeden yakınsa "aynı yer" (kare genişliğine göre)
TEKRAR_MERKEZ_MESAFESI = 0.06
# Boyut farkı bu orandan küçükse "aynı boy"
TEKRAR_BOYUT_FARKI = 0.35
# Renk imzası benzerliği bu değerin üstündeyse "aynı görünüm"
TEKRAR_RENK_BENZERLIGI = 0.70


def renk_benzerligi(a: tuple[float, ...] | None, b: tuple[float, ...] | None) -> float:
    """İki renk imzası arasında histogram kesişimi: 0 (hiç) — 1 (aynı).

    İmza, analiz tarafında OpenCV ile çıkarılıp buraya sade sayı dizisi
    olarak verilir; bu dosya kameradan ve OpenCV'den bağımsız kalsın diye.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    ortak = sum(min(x, y) for x, y in zip(a, b, strict=True))
    toplam = sum(max(x, y) for x, y in zip(a, b, strict=True))
    return ortak / toplam if toplam > 0 else 0.0


@dataclass
class KapananBardak:
    """Sayımı kesinleşmiş bir bardağın kısa süreli hatırası."""

    merkez: tuple[float, float]  # normalize (0-1)
    boyut: tuple[float, float]  # normalize genişlik/yükseklik
    renk_imzasi: tuple[float, ...] | None
    kapanma_s: float  # monotonic saniye


class TekrarKorumasi:
    """Kapanan bardakları hatırlar ve aynı bardağın tekrar sayılmasını engeller.

    Saf mantık: kamera, model ve veritabanı bilmez — testi saniyeler sürer.
    """

    def __init__(
        self,
        pencere_sn: float = TEKRAR_PENCERESI_SN,
        merkez_mesafesi: float = TEKRAR_MERKEZ_MESAFESI,
        boyut_farki: float = TEKRAR_BOYUT_FARKI,
        renk_benzerligi_esigi: float = TEKRAR_RENK_BENZERLIGI,
    ) -> None:
        self.pencere_sn = pencere_sn
        self.merkez_mesafesi = merkez_mesafesi
        self.boyut_farki = boyut_farki
        self.renk_benzerligi_esigi = renk_benzerligi_esigi
        self._kapananlar: list[KapananBardak] = []
        self.bastirilan = 0  # şeffaflık: kaç bardak "aynı bardak" diye sayılmadı

    def hatirla(
        self,
        merkez: tuple[float, float],
        boyut: tuple[float, float],
        renk_imzasi: tuple[float, ...] | None,
        simdi_s: float,
    ) -> None:
        self._sureyi_gecenleri_at(simdi_s)
        self._kapananlar.append(
            KapananBardak(merkez=merkez, boyut=boyut, renk_imzasi=renk_imzasi, kapanma_s=simdi_s)
        )

    def ayni_bardak_mi(
        self,
        merkez: tuple[float, float],
        boyut: tuple[float, float],
        renk_imzasi: tuple[float, ...] | None,
        simdi_s: float,
    ) -> bool:
        """Yeni açılan iz, az önce kapanmış bir bardağın devamı mı?

        ÜÇ koşulun HEPSİ gerekir (yer + boy + renk). Tek koşulla bastırmak,
        arka arkaya aynı yere konan farklı bardakları yutardı.
        """
        self._sureyi_gecenleri_at(simdi_s)
        for eski in list(self._kapananlar):
            if not self._yeri_ayni(eski.merkez, merkez):
                continue
            if not self._boyu_ayni(eski.boyut, boyut):
                continue
            # Renk imzası iki tarafta da varsa benzerlik ARANIR; imza
            # çıkarılamadıysa (çok küçük kırpık) renk kanıtı yok sayılır ve
            # yalnız yer+boy ile bastırma YAPILMAZ — emin olmadan yutmayız.
            if eski.renk_imzasi is None or renk_imzasi is None:
                continue
            if renk_benzerligi(eski.renk_imzasi, renk_imzasi) < self.renk_benzerligi_esigi:
                continue
            self.bastirilan += 1
            # Hatıra TÜKENİR: aynı kayıt ikinci bir bardağı bastıramaz.
            # Tazeleme/zincirleme yapılsaydı, tezgâhın o noktası kalıcı bir
            # "yutma alanı"na dönüşür ve sonraki bütün bardaklar kaybolurdu.
            self._kapananlar.remove(eski)
            return True
        return False

    def _sureyi_gecenleri_at(self, simdi_s: float) -> None:
        sinir = simdi_s - self.pencere_sn
        self._kapananlar = [k for k in self._kapananlar if k.kapanma_s >= sinir]

    def _yeri_ayni(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 <= self.merkez_mesafesi

    def _boyu_ayni(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        for eski, yeni in zip(a, b, strict=True):
            buyuk = max(eski, yeni)
            if buyuk <= 0:
                return False
            if abs(eski - yeni) / buyuk > self.boyut_farki:
                return False
        return True
