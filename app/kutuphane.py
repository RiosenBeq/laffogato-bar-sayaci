"""Nesne kütüphanesi: kendi nesnelerini fotoğrafla tanıtma ve eşleştirme.

Amaç: "bu benim Laffogato fincanım" gibi SANA ÖZEL nesneleri, model
eğitmeden tanıtabilmek. Nesnenin farklı açılardan 3-8 fotoğrafını yüklersin;
sistem her fotoğraftan iki parmak izi çıkarır:

1. **Renk parmak izi** (HSV histogramı): nesnenin renk dağılımı. Aydınlatma
   değişse de kabaca korunur; ama aynı renkte başka nesneler karışabilir.
2. **Desen parmak izi** (ORB anahtar noktaları): logo, yazı, kenar deseni.
   Renk aynı olsa bile deseni farklı olan nesneleri ayırır.

Eşleştirme ikisinin birleşimidir. Bu yöntem MODEL EĞİTİMİ DEĞİLDİR:
- Ayırt edici deseni/rengi olan nesnelerde (logolu fincan, markalı kutu) iyi çalışır.
- Düz beyaz, desensiz nesnelerde zayıftır — renk dışında tutunacak bir şey yoktur.
- Karar eşiğin altındaysa "eşleşme yok" der; uydurma isim yazmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# Karşılaştırmadan önce her görüntü bu boyuta getirilir (hız + tutarlılık)
_STANDART_BOYUT = (160, 160)
# HSV histogram gözleri: ton 24, doygunluk 8 (parlaklık bilerek düşük ağırlıklı)
_TON_GOZ, _DOYGUNLUK_GOZ = 24, 8
# ORB anahtar nokta sayısı
_ORB_NOKTA = 300
# İki ORB tanımlayıcısı bu Hamming mesafesinin altındaysa "eşleşti" sayılır
_ORB_MESAFE = 55
# Renk ve desen skorlarının karışım ağırlığı
_RENK_AGIRLIGI = 0.45
_DESEN_AGIRLIGI = 0.55
# İki kanıttan biri bu değerin altındaysa (biri uyuyor, öteki uymuyor) skor
# çarpanla düşürülür — çelişkili kanıt "eşleşti" saydırmamalı
_UYUSMA_ALT_SINIRI = 0.30
_CELISKI_CEZASI = 0.65
# Desen kanıtı için gereken en az anahtar nokta (altındaysa "desensiz")
_EN_AZ_ANAHTAR_NOKTA = 8
# İki taraf da desensizse: renk çıtası yüksek tutulur, sonra kabul edilir
_DUZ_RENK_BARI = 0.68
_DUZ_KABUL = 0.62
_DUZ_ZAYIF = 0.45
# Biri desenli öteki düz: kanıtlar uyuşmuyor
_KANIT_UYUSMAZLIGI = 0.40
# Bu skorun altındaki eşleşmeler kabul edilmez ("eşleşme yok")
VARSAYILAN_ESIK = 0.42


@dataclass
class Parmakizi:
    renk: np.ndarray
    desen: np.ndarray | None


@dataclass
class Nesne:
    """Bir nesnenin adı ve referans fotoğraflarının parmak izleri."""

    id: int
    ad: str
    parmakizleri: list[Parmakizi] = field(default_factory=list)


def _orb():
    return cv2.ORB_create(nfeatures=_ORB_NOKTA)


def parmakizi_cikar(bgr: np.ndarray) -> Parmakizi | None:
    """Görüntüden renk + desen parmak izi. Görüntü çok küçükse None."""
    if bgr is None or bgr.size == 0 or min(bgr.shape[:2]) < 16:
        return None
    kucuk = cv2.resize(bgr, _STANDART_BOYUT, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(kucuk, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [_TON_GOZ, _DOYGUNLUK_GOZ], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram, 0, 1, cv2.NORM_MINMAX)
    gri = cv2.cvtColor(kucuk, cv2.COLOR_BGR2GRAY)
    _, tanimlayicilar = _orb().detectAndCompute(gri, None)
    return Parmakizi(renk=histogram.flatten(), desen=tanimlayicilar)


def _desensiz(izi: Parmakizi) -> bool:
    """Tutunacak desen kanıtı var mı? (küçük/bulanık/düz yüzeyli nesnelerde yok)"""
    return izi.desen is None or len(izi.desen) < _EN_AZ_ANAHTAR_NOKTA


def _renk_benzerligi(a: np.ndarray, b: np.ndarray) -> float:
    """Histogram kesişimi: 0 (hiç benzemiyor) — 1 (aynı)."""
    toplam = float(np.sum(np.maximum(a, b)))
    if toplam <= 0:
        return 0.0
    return float(np.sum(np.minimum(a, b)) / toplam)


def _desen_benzerligi(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """Eşleşen ORB anahtar noktalarının oranı."""
    if a is None or b is None or len(a) < 8 or len(b) < 8:
        return 0.0
    eslestirici = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    eslesmeler = eslestirici.match(a, b)
    iyi = [e for e in eslesmeler if e.distance <= _ORB_MESAFE]
    return len(iyi) / min(len(a), len(b))


def benzerlik(aday: Parmakizi, referans: Parmakizi) -> float:
    """İki parmak izi arasında 0-1 arası benzerlik.

    İki kanıt (renk ve desen) birbirini DOĞRULAMALIDIR. Yalnız biri uyuyorsa
    skor düşürülür; çünkü:
    - aynı renk + farklı desen  → beyaz iki ayrı fincan
    - farklı renk + aynı desen  → aynı markanın başka renk ürünü
    Bunları "eşleşti" saymak, tarama raporunu güvenilmez yapar.
    """
    renk = _renk_benzerligi(aday.renk, referans.renk)
    aday_desensiz = _desensiz(aday)
    referans_desensiz = _desensiz(referans)

    if aday_desensiz != referans_desensiz:
        # Biri desenli, öteki düz: kanıtlar UYUŞMUYOR (aynı nesne olsaydı
        # ikisinde de benzer desen çıkardı) — sert cezalandırılır
        return renk * _KANIT_UYUSMAZLIGI

    if aday_desensiz and referans_desensiz:
        # İkisi de düz/desensiz (küçük beyaz fincan gibi): tutunacak tek iz
        # renktir. Bu durumda renk çıtası YÜKSELİR — orta karar bir renk
        # benzerliği "aynı nesne" saydırmaz.
        return renk * (_DUZ_KABUL if renk >= _DUZ_RENK_BARI else _DUZ_ZAYIF)

    desen = _desen_benzerligi(aday.desen, referans.desen)
    skor = _RENK_AGIRLIGI * renk + _DESEN_AGIRLIGI * desen
    if min(renk, desen) < _UYUSMA_ALT_SINIRI:
        skor *= _CELISKI_CEZASI
    return skor


def en_iyi_eslesme(
    aday_bgr: np.ndarray, nesneler: list[Nesne], esik: float = VARSAYILAN_ESIK
) -> tuple[Nesne | None, float]:
    """Aday görüntüyü kütüphanedeki nesnelerle karşılaştırır.

    Nesnenin BİRDEN ÇOK açıdan fotoğrafı varsa en iyi eşleşen açı kullanılır —
    bu yüzden farklı açılardan fotoğraf yüklemek isabeti artırır.
    Eşiğin altındaki en iyi skor bile kabul EDİLMEZ: (None, skor) döner.
    """
    aday = parmakizi_cikar(aday_bgr)
    if aday is None or not nesneler:
        return None, 0.0
    en_iyi_nesne, en_iyi_skor = None, 0.0
    for nesne in nesneler:
        for referans in nesne.parmakizleri:
            skor = benzerlik(aday, referans)
            if skor > en_iyi_skor:
                en_iyi_nesne, en_iyi_skor = nesne, skor
    if en_iyi_skor < esik:
        return None, en_iyi_skor
    return en_iyi_nesne, en_iyi_skor
