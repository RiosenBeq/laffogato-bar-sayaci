"""Bardak doğrulayıcının eğitimi, dürüst karşılaştırması ve devreye alınması.

Akış:
  1. Kullanıcı Bardak Eğitimi sayfasına fotoğraf/video yükler
  2. Dedektör her görüntüde aday kutuları bulur, kırpıklar etiketsiz kaydedilir
  3. Kullanıcı üç düğmeyle etiketler: Bizim bardağımız / Bardak değil / Belirsiz
  4. "Eğitimi çalıştır" → model eğitilir ve ESKİ yöntemle AYNI kırpıklarda
     karşılaştırılır
  5. Yeni model yalnızca ölçülebilir şekilde daha iyiyse devreye alınır

"ESKİ" NEDİR: bugün "bu bizim bardağımız mı?" sorusuna cevap veren tek
mekanizma, kütüphanedeki renk+desen parmak izi eşleştirmesidir
(app/kutuphane.py). Eşik altında kalınca "eşleşme yok" der — bu onun
"belirsiz"idir. Yeni model aynı kırpıklarda bununla karşılaştırılır.

ÖLÇÜM DÜRÜSTLÜĞÜ — bu dosyanın asıl işi:
  * Bölme PARTİ bazlıdır (aynı yüklemenin kareleri bölünmez)
  * Eğitim ve test arasında YAKIN KOPYA taraması yapılır; kopya varsa
    ölçüm geçersiz sayılır ve sayı GÖSTERİLMEZ
  * Test kümesi tek sınıftan oluşuyorsa ya da çok küçükse eğitim reddedilir
  * Hiçbir koşulda "isabet %98" gibi karşılığı olmayan bir sayı üretilmez
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from app import zaman
from app.bardak_modeli import (
    BARDAK,
    BELIRSIZ,
    DEGIL,
    OZNITELIK_BOYU,
    BardakModeli,
    oznitelik,
    sigmoid,
)
from app.kutuphane import VARSAYILAN_ESIK, en_iyi_eslesme

# --- Eğitim ön koşulları ---------------------------------------------------
# Hedef bunlar DEĞİL, ALT SINIR. Altında eğitim çalışmaz ve nedeni söylenir.
EN_AZ_BARDAK = 25
EN_AZ_DEGIL = 25
EN_AZ_PARTI = 2  # en az iki ayrı yükleme: biri eğitime, biri teste
EN_AZ_TEST = 12
# Test kümesinde HER İKİ sınıftan en az bu kadar örnek olmalı
EN_AZ_TEST_SINIF = 4
TEST_PAYI = 0.25

# İki kırpık bu ortalama piksel farkının altındaysa YAKIN KOPYA sayılır.
# (Bu projenin veri/goruntuler klasöründeki 176 kırpık ölçüldü: medyan fark
# 0.0 — yani birebir aynı kareler. Böyle bir veriyle eğitim/test bölmek
# %100 isabet üretir ve bu sayı tamamen yalandır.)
YAKIN_KOPYA_FARKI = 3.0
KOPYA_BOY = 32
# Test kırpıklarının bu orandan fazlası eğitimin kopyasıysa veri dejeneredir
# ve ölçüm HİÇ yapılmaz. Altındaysa kopyalar testten çıkarılır.
KOPYA_RET_ORANI = 0.30

# Lojistik regresyon — deterministik, numpy, saniyeler
_OGRENME_ADIMI = 0.5
_TUR_SAYISI = 400
# Güçlü L2: öznitelik sayısı (114) örnek sayısına yakın olabilir; ceza
# olmadan model ezberler ve olasılıklar 0/1'e yapışıp "belirsiz" bandını yok eder.
_L2 = 0.05

ALT_ESIK, UST_ESIK = 0.40, 0.60
# Devreye alınabilmek için gereken EN AZ isabet (karar verdikleri içinde)
EN_AZ_ISABET = 0.70


@dataclass
class Karsilastirma:
    """Bir yöntemin AYNI test kırpıklarındaki sonucu."""

    ad: str
    dogru: int = 0
    yanlis: int = 0
    belirsiz: int = 0

    @property
    def karar_verilen(self) -> int:
        return self.dogru + self.yanlis

    @property
    def isabet(self) -> float:
        """Karar verebildiklerinin ne kadarı doğru (belirsizler hariç)."""
        return self.dogru / self.karar_verilen if self.karar_verilen else 0.0

    @property
    def isabet_metni(self) -> str:
        """Ekranda gösterilecek isabet. Hiç karar verilmediyse yüzde YAZILMAZ:
        '%0' yanıltıcıdır — yöntem yanlış cevap vermedi, hiç cevap veremedi."""
        return f"%{self.isabet * 100:.0f}" if self.karar_verilen else "— (hiç karar veremedi)"


@dataclass
class EgitimSonucu:
    hata: str | None = None
    surum: str = ""
    egitim_sayisi: int = 0
    test_sayisi: int = 0
    bardak_sayisi: int = 0
    degil_sayisi: int = 0
    parti_sayisi: int = 0
    eski: Karsilastirma = field(default_factory=lambda: Karsilastirma("eski"))
    yeni: Karsilastirma = field(default_factory=lambda: Karsilastirma("yeni"))
    devreye_alindi: bool = False
    sebep: str = ""
    uyarilar: list[str] = field(default_factory=list)


def egit(baglanti, ayarlar) -> EgitimSonucu:
    """Eğitimi uçtan uca çalıştırır. Hata durumunda istisna değil, kullanıcıya
    gösterilecek Türkçe mesaj taşıyan EgitimSonucu döner."""
    satirlar = baglanti.execute(
        "SELECT * FROM bardak_ornekleri WHERE etiket IN ('bardak', 'degil') ORDER BY parti, id"
    ).fetchall()
    bardak_n = sum(1 for s in satirlar if s["etiket"] == BARDAK)
    degil_n = len(satirlar) - bardak_n
    partiler = sorted({s["parti"] for s in satirlar})

    on_kosul = _on_kosul_hatasi(bardak_n, degil_n, len(partiler))
    if on_kosul:
        return EgitimSonucu(
            hata=on_kosul,
            bardak_sayisi=bardak_n,
            degil_sayisi=degil_n,
            parti_sayisi=len(partiler),
        )

    veri, atlanan = _veriyi_hazirla(satirlar, ayarlar)
    if not veri:
        return EgitimSonucu(
            hata="Etiketli kırpıkların hiçbiri okunamadı; dosyalar silinmiş olabilir.",
            bardak_sayisi=bardak_n,
            degil_sayisi=degil_n,
            parti_sayisi=len(partiler),
        )

    egitim, test = _partiye_gore_bol(veri, partiler)
    bolme_hatasi = _bolme_hatasi(egitim, test)
    if bolme_hatasi:
        return EgitimSonucu(
            hata=bolme_hatasi,
            bardak_sayisi=bardak_n,
            degil_sayisi=degil_n,
            parti_sayisi=len(partiler),
        )

    kopyalar = _yakin_kopya_indeksleri(egitim, test)
    if len(kopyalar) / len(test) > KOPYA_RET_ORANI:
        return EgitimSonucu(
            hata=(
                f"Ölçüm yapılamadı: test kırpıklarının {len(kopyalar)}/{len(test)} tanesi "
                "eğitimdekilerle neredeyse AYNI görüntü. Böyle bir veriyle çıkan isabet "
                "sayısı gerçeği göstermez. Farklı zamanlarda ve farklı açılardan çekilmiş "
                "görüntüler yükleyin — aynı videonun ardışık kareleri değil."
            ),
            bardak_sayisi=bardak_n,
            degil_sayisi=degil_n,
            parti_sayisi=len(partiler),
        )
    kopya_uyarisi = ""
    if kopyalar:
        # Az sayıda benzeşme bütün eğitimi öldürmesin: sızan kırpıklar testten
        # çıkarılır ve kaç tanesinin çıkarıldığı kullanıcıya söylenir.
        test = [o for i, o in enumerate(test) if i not in kopyalar]
        kopya_uyarisi = (
            f"{len(kopyalar)} test kırpığı eğitimdekilerle çok benzediği için ölçüme "
            "alınmadı (sızıntıyı önlemek üzere)."
        )
        kalan_hata = _bolme_hatasi(egitim, test)
        if kalan_hata:
            return EgitimSonucu(
                hata=kalan_hata,
                bardak_sayisi=bardak_n,
                degil_sayisi=degil_n,
                parti_sayisi=len(partiler),
            )

    x_egitim = np.stack([o["x"] for o in egitim])
    y_egitim = np.array([1.0 if o["etiket"] == BARDAK else 0.0 for o in egitim])
    ortalama = x_egitim.mean(axis=0)
    sapma = x_egitim.std(axis=0) + 1e-6
    w, b = _lojistik_egit((x_egitim - ortalama) / sapma, y_egitim)

    sonuc = EgitimSonucu(
        surum=_siradaki_surum(ayarlar.bardak_model_klasoru),
        egitim_sayisi=len(egitim),
        test_sayisi=len(test),
        bardak_sayisi=bardak_n,
        degil_sayisi=degil_n,
        parti_sayisi=len(partiler),
        yeni=_yeniyi_olc(test, w, b, ortalama, sapma),
        eski=_eskiyi_olc(test, baglanti, ayarlar),
    )
    if atlanan:
        sonuc.uyarilar.append(f"{atlanan} kırpık okunamadı ve ölçüme alınmadı.")
    if kopya_uyarisi:
        sonuc.uyarilar.append(kopya_uyarisi)

    _kapiyi_uygula(sonuc)
    _kaydet(ayarlar.bardak_model_klasoru, sonuc, w, b, ortalama, sapma)
    return sonuc


# ---- ön koşullar ve bölme -------------------------------------------------


def _on_kosul_hatasi(bardak_n: int, degil_n: int, parti_n: int) -> str | None:
    if bardak_n < EN_AZ_BARDAK or degil_n < EN_AZ_DEGIL:
        return (
            f"Eğitim için en az {EN_AZ_BARDAK} 'Bizim bardağımız' ve {EN_AZ_DEGIL} "
            f"'Bardak değil' etiketi gerekiyor; şu an {bardak_n} ve {degil_n} var. "
            "Yeni görüntü yükleyip etiketlemeye devam edin."
        )
    if parti_n < EN_AZ_PARTI:
        return (
            f"Ölçümün anlamlı olması için en az {EN_AZ_PARTI} AYRI yükleme gerekiyor; "
            f"şu an {parti_n} yükleme var. Tek yüklemeyi ikiye bölmek ölçümü yalan "
            "yapardı: bir yüklemeyle eğitilip aynı yüklemeyle sınanan model, "
            "ezberlediğini bilemez. Farklı bir gün/açı ile ikinci bir yükleme yapın."
        )
    return None


def _veriyi_hazirla(satirlar, ayarlar) -> tuple[list[dict], int]:
    veri, atlanan = [], 0
    for satir in satirlar:
        kirpik = cv2.imread(str(ayarlar.egitim_klasoru / satir["dosya"]))
        if kirpik is None or min(kirpik.shape[:2]) < 8:
            atlanan += 1
            continue
        veri.append(
            {
                "x": oznitelik(kirpik),
                "etiket": satir["etiket"],
                "parti": satir["parti"],
                "kirpik": kirpik,
                "coco_bardak": bool(satir["coco_bardak"]),
            }
        )
    return veri, atlanan


def _partiye_gore_bol(veri: list[dict], partiler: list[str]) -> tuple[list[dict], list[dict]]:
    """Test kümesi SON partilerden alınır; parti asla bölünmez.

    Rastgele bölme YASAK: aynı yüklemenin kareleri birbirine çok benzer,
    ikiye bölünürse model ezberlediğini test eder ve skor yalan çıkar.
    """
    hedef = max(EN_AZ_TEST, int(len(veri) * TEST_PAYI))
    test_partileri: set[str] = set()
    toplam = 0
    # En ESKİ parti her zaman eğitimde kalır: aksi halde küçük son partiler
    # hedefe ulaşmak için bütün partileri teste çeker ve eğitim kümesi
    # BOŞALIRDI ("daha fazla yükleyin" diyen ama aslında bölme hatası olan durum).
    for parti in reversed(partiler[1:]):
        if toplam >= hedef and test_partileri:
            break
        test_partileri.add(parti)
        toplam += sum(1 for o in veri if o["parti"] == parti)
    egitim = [o for o in veri if o["parti"] not in test_partileri]
    test = [o for o in veri if o["parti"] in test_partileri]
    return egitim, test


def _bolme_hatasi(egitim: list[dict], test: list[dict]) -> str | None:
    if len(test) < EN_AZ_TEST:
        return (
            f"Test kümesi çok küçük ({len(test)} kırpık, en az {EN_AZ_TEST} gerekli). "
            "Bu kadar az örnekle ölçülen isabet rastlantıdan ayırt edilemez."
        )
    if len(egitim) < EN_AZ_TEST:
        return (
            f"Eğitim kümesi çok küçük ({len(egitim)} kırpık). Daha fazla görüntü "
            "yükleyip etiketleyin."
        )
    for ad, kume in (("Test", test), ("Eğitim", egitim)):
        etiketler = {o["etiket"] for o in kume}
        if len(etiketler) < 2:
            tek = "bardak" if BARDAK in etiketler else "bardak değil"
            return (
                f"{ad} kümesinin tamamı tek sınıftan ('{tek}') oluşuyor. Böyle bir "
                "kümede isabet ölçmek anlamsızdır. Her yüklemede hem bardak hem "
                "bardak olmayan kutuları etiketleyin."
            )
    # Sınıf başına alt sınır: 11'e 1 dengesiz bir test kümesinde "her şeye
    # değil de" diyen boş bir model %92 isabet gösterirdi.
    for etiket, ad in ((BARDAK, "bardak"), (DEGIL, "bardak değil")):
        adet = sum(1 for o in test if o["etiket"] == etiket)
        if adet < EN_AZ_TEST_SINIF:
            return (
                f"Test kümesinde yalnızca {adet} adet '{ad}' örneği var (en az "
                f"{EN_AZ_TEST_SINIF} gerekli). Dengesiz bir test kümesinde ölçülen "
                "isabet yanıltıcıdır. Son yüklemenizde her iki türden de örnek "
                "etiketleyin."
            )
    return None


def _yakin_kopya_indeksleri(egitim: list[dict], test: list[dict]) -> set[int]:
    """Test kırpıklarından hangileri eğitimdekilerle neredeyse aynı görüntü?"""

    def kucult(kirpik):
        gri = cv2.cvtColor(kirpik, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gri, (KOPYA_BOY, KOPYA_BOY), interpolation=cv2.INTER_AREA).astype(
            np.float32
        )

    egitim_kucuk = [kucult(o["kirpik"]) for o in egitim]
    kopyalar: set[int] = set()
    for i, o in enumerate(test):
        t = kucult(o["kirpik"])
        if any(float(np.abs(t - e).mean()) < YAKIN_KOPYA_FARKI for e in egitim_kucuk):
            kopyalar.add(i)
    return kopyalar


# ---- ölçüm ----------------------------------------------------------------


def _yeniyi_olc(test, w, b, ortalama, sapma) -> Karsilastirma:
    olcum = Karsilastirma("Yeni model")
    x = np.stack([o["x"] for o in test])
    p = sigmoid(((x - ortalama) / sapma) @ w + b)
    for olasilik, o in zip(p, test, strict=True):
        gercek = o["etiket"]
        if olasilik >= UST_ESIK:
            tahmin = BARDAK
        elif olasilik <= ALT_ESIK:
            tahmin = DEGIL
        else:
            tahmin = BELIRSIZ
        _say(olcum, tahmin, gercek)
    return olcum


def _eskiyi_olc(test, baglanti, ayarlar) -> Karsilastirma:
    """Bugünkü yöntem: kütüphane parmak izi eşleştirmesi.

    Eşleşme yoksa "belirsiz" — bugün sistemin "bu bizim bardağımız mı?"
    sorusuna verebildiği tek cevap budur.
    """
    from app import nesne_deposu

    olcum = Karsilastirma("Bugünkü yöntem (parmak izi)")
    nesneler = nesne_deposu.nesneleri_yukle(baglanti, ayarlar.nesne_klasoru)
    for o in test:
        if not nesneler:
            tahmin = BELIRSIZ  # kütüphane boş: bugün hiçbir bardağı tanıyamaz
        else:
            nesne, _ = en_iyi_eslesme(o["kirpik"], nesneler, VARSAYILAN_ESIK)
            tahmin = BARDAK if nesne else BELIRSIZ
        _say(olcum, tahmin, o["etiket"])
    return olcum


def _say(olcum: Karsilastirma, tahmin: str, gercek: str) -> None:
    if tahmin == BELIRSIZ:
        olcum.belirsiz += 1
    elif tahmin == gercek:
        olcum.dogru += 1
    else:
        olcum.yanlis += 1


def _kapiyi_uygula(sonuc: EgitimSonucu) -> None:
    """Devreye alma kuralı: belirsiz DÜŞECEK ve isabet GERİLEMEYECEK.

    Kullanıcının kuralı "belirsiz düşüyorsa devreye al". Buna isabet şartı
    ekleniyor: belirsizi düşürüp her şeye "bardak" diyen bir model belirsizi
    sıfırlar ama sayımı bozardı. İki sayı da ekranda gösterilir.
    """
    belirsiz_dustu = sonuc.yeni.belirsiz < sonuc.eski.belirsiz
    isabet_korundu = sonuc.yeni.isabet >= sonuc.eski.isabet
    # Mutlak taban: kütüphane boşken eski isabet 0 olur ve "gerilemedi" şartı
    # kendiliğinden sağlanırdı — kötü bir model bu boşluktan devreye girerdi.
    yeterince_isabetli = sonuc.yeni.isabet >= EN_AZ_ISABET
    sonuc.devreye_alindi = belirsiz_dustu and isabet_korundu and yeterince_isabetli

    if not yeterince_isabetli and belirsiz_dustu and isabet_korundu:
        sonuc.sebep = (
            f"Yeni model belirsizi düşürdü ama karar verdiklerinin yalnızca "
            f"%{sonuc.yeni.isabet * 100:.0f}'i doğru; devreye alınabilmesi için en az "
            f"%{EN_AZ_ISABET * 100:.0f} gerekiyor. Devreye ALINMADI. Daha fazla ve "
            "daha çeşitli görüntü etiketleyip yeniden deneyin."
        )
        return

    if sonuc.devreye_alindi and not sonuc.eski.karar_verilen:
        sonuc.sebep = (
            f"Bugünkü yöntem bu {sonuc.test_sayisi} kırpığın hiçbirine karar veremedi "
            f"(hepsi belirsiz). Yeni model {sonuc.yeni.karar_verilen} tanesine karar verdi "
            f"ve bunların %{sonuc.yeni.isabet * 100:.0f}'i doğru. Devreye alındı."
        )
    elif sonuc.devreye_alindi:
        sonuc.sebep = (
            f"Belirsiz sayısı {sonuc.eski.belirsiz} → {sonuc.yeni.belirsiz} düştü ve "
            f"isabet %{sonuc.eski.isabet * 100:.0f} → %{sonuc.yeni.isabet * 100:.0f} "
            "gerilemedi. Yeni model devreye alındı."
        )
    elif not belirsiz_dustu:
        sonuc.sebep = (
            f"Belirsiz sayısı düşmedi ({sonuc.eski.belirsiz} → {sonuc.yeni.belirsiz}). "
            "Yeni model devreye ALINMADI; sistem bugünkü gibi çalışmaya devam ediyor."
        )
    else:
        sonuc.sebep = (
            f"Belirsiz düştü ama isabet geriledi (%{sonuc.eski.isabet * 100:.0f} → "
            f"%{sonuc.yeni.isabet * 100:.0f}). Belirsizi azaltıp yanlış sayan bir model "
            "sayacı bozar; devreye ALINMADI."
        )


# ---- eğitim ve kayıt ------------------------------------------------------


def _lojistik_egit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    w = np.zeros(x.shape[1])
    b = 0.0
    n = len(y)
    # Sınıf dengesizliğinde azınlık sınıf ezilmesin diye ağırlıklı kayıp
    poz = max(float(y.sum()), 1.0)
    neg = max(float(n - y.sum()), 1.0)
    agirlik = np.where(y > 0.5, n / (2 * poz), n / (2 * neg))
    for _ in range(_TUR_SAYISI):
        p = sigmoid(x @ w + b)
        fark = (p - y) * agirlik
        w -= _OGRENME_ADIMI * (x.T @ fark / n + _L2 * w)
        b -= _OGRENME_ADIMI * float(fark.mean())
    return w, b


def _siradaki_surum(klasor: Path) -> str:
    mevcut = sorted(Path(klasor).glob("v*.npz"))
    return "v001" if not mevcut else f"v{int(mevcut[-1].stem[1:]) + 1:03d}"


def _kaydet(klasor: Path, sonuc: EgitimSonucu, w, b, ortalama, sapma) -> None:
    """Her eğitim sürümlü kaydedilir; YALNIZCA kapıyı geçen devreye alınır."""
    klasor = Path(klasor)
    klasor.mkdir(parents=True, exist_ok=True)
    np.savez(klasor / f"{sonuc.surum}.npz", w=w, b=b, ortalama=ortalama, sapma=sapma)
    kayit = {
        "surum": sonuc.surum,
        "egitim_zamani": zaman.simdi_utc(),
        "egitim_sayisi": sonuc.egitim_sayisi,
        "test_sayisi": sonuc.test_sayisi,
        "eski_isabet": round(sonuc.eski.isabet, 4),
        "eski_belirsiz": sonuc.eski.belirsiz,
        "yeni_isabet": round(sonuc.yeni.isabet, 4),
        "yeni_belirsiz": sonuc.yeni.belirsiz,
        "devreye_alindi": sonuc.devreye_alindi,
        "oznitelik_boyu": OZNITELIK_BOYU,
        "alt_esik": ALT_ESIK,
        "ust_esik": UST_ESIK,
    }
    (klasor / f"{sonuc.surum}.json").write_text(
        json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if sonuc.devreye_alindi:
        (klasor / "aktif.json").write_text(
            json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def aktif_model_bilgisi(klasor: Path) -> dict | None:
    """Devredeki modelin kaydı (yoksa None) — arayüzde gösterilir."""
    aktif = Path(klasor) / "aktif.json"
    if not aktif.is_file():
        return None
    try:
        return json.loads(aktif.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def modeli_devreden_cikar(klasor: Path) -> bool:
    """Kullanıcı geri almak isterse: sistem bugünkü davranışına döner."""
    aktif = Path(klasor) / "aktif.json"
    if not aktif.is_file():
        return False
    aktif.unlink()
    return True


# ---- örnek toplama ve etiketleme -----------------------------------------

# Tek görüntüden en çok kaç aday alınır (kullanıcı etiket yağmuruna tutulmasın)
GORSEL_BASINA_ADAY = 8
ETIKETLER = (BARDAK, DEGIL, BELIRSIZ)


def ornekleri_topla(baglanti, ayarlar, gorseller, tespitci) -> tuple[int, int]:
    """Yüklenen görüntülerde aday kutuları bulup etiketsiz kırpık olarak yazar.

    gorseller: [(dosya_adi, BGR görüntü)]. Döner: (eklenen kırpık, taranan görüntü).
    Tek çağrı = tek PARTİ: sızıntısız bölme buna dayanır (bkz. _partiye_gore_bol).
    """
    if tespitci is None:
        return 0, 0
    # Parti adı BENZERSİZ olmalı: aynı saniyeye düşen iki yükleme aynı adı
    # alırsa hem kırpık dosyaları birbirinin üzerine yazılır hem de iki ayrı
    # yükleme tek partiye çöker (sızıntısız bölme bozulurdu).
    parti = f"p{zaman.simdi_utc().replace(':', '').replace('-', '')[:15]}-{uuid4().hex[:6]}"
    klasor = Path(ayarlar.egitim_klasoru)
    klasor.mkdir(parents=True, exist_ok=True)

    eklenen, taranan = 0, 0
    for ad, gorsel in gorseller:
        if gorsel is None or gorsel.size == 0:
            continue
        taranan += 1
        yukseklik, genislik = gorsel.shape[:2]
        adaylar = sorted(tespitci.adaylari_bul(gorsel), key=lambda a: -a[1])
        for kutu, _guven, coco_bardak in adaylar[:GORSEL_BASINA_ADAY]:
            from app.bardak_modeli import bardak_kirp

            kirpik = bardak_kirp(gorsel, kutu)
            if kirpik is None:
                continue
            dosya = f"ornek-{parti}-{eklenen:03d}.jpg"
            try:
                cv2.imwrite(str(klasor / dosya), kirpik, [cv2.IMWRITE_JPEG_QUALITY, 88])
            except (OSError, cv2.error):
                continue
            normalize = [
                round(kutu[0] / genislik, 4),
                round(kutu[1] / yukseklik, 4),
                round(kutu[2] / genislik, 4),
                round(kutu[3] / yukseklik, 4),
            ]
            baglanti.execute(
                "INSERT INTO bardak_ornekleri "
                "(dosya, parti, kaynak, kutu, coco_bardak, eklendi) "
                "VALUES (?, ?, 'yukleme', ?, ?, ?)",
                (dosya, parti, json.dumps(normalize), coco_bardak, zaman.simdi_utc()),
            )
            eklenen += 1
        _ = ad  # dosya adı yalnızca çağıranın raporu için
    baglanti.commit()
    return eklenen, taranan


def etiketle(baglanti, ornek_id: int, etiket: str) -> bool:
    """Örneği etiketler. Geçersiz etikette ValueError, bulunamazsa False."""
    if etiket not in ETIKETLER:
        raise ValueError(f"Geçersiz etiket: {etiket}")
    guncellenen = baglanti.execute(
        "UPDATE bardak_ornekleri SET etiket = ?, etiketlendi = ? WHERE id = ?",
        (etiket, zaman.simdi_utc(), ornek_id),
    ).rowcount
    baglanti.commit()
    return guncellenen > 0


def etiketsizleri_getir(baglanti, en_cok: int = 24) -> list[dict]:
    return [
        dict(satir)
        for satir in baglanti.execute(
            "SELECT * FROM bardak_ornekleri WHERE etiket IS NULL ORDER BY id LIMIT ?",
            (en_cok,),
        )
    ]


def sayilar(baglanti) -> dict:
    satir = baglanti.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN etiket IS NOT NULL THEN 1 ELSE 0 END) AS etiketli, "
        "SUM(CASE WHEN etiket = 'bardak' THEN 1 ELSE 0 END) AS bardak, "
        "SUM(CASE WHEN etiket = 'degil' THEN 1 ELSE 0 END) AS degil, "
        "SUM(CASE WHEN etiket = 'belirsiz' THEN 1 ELSE 0 END) AS belirsiz, "
        # Yalnızca EĞİTİME GİREN satırların partisi sayılır. Etiketsizleri de
        # saymak, durum tablosunun "2 ayrı yükleme ✓" derken eğitimin
        # "en az 2 ayrı yükleme gerekiyor" diye reddetmesine yol açardı.
        "COUNT(DISTINCT CASE WHEN etiket IN ('bardak', 'degil') THEN parti END) AS parti "
        "FROM bardak_ornekleri"
    ).fetchone()
    return {a: (satir[a] or 0) for a in satir.keys()}


def ornek_sil(baglanti, ayarlar, ornek_id: int) -> None:
    satir = baglanti.execute(
        "SELECT dosya FROM bardak_ornekleri WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is None:
        return
    (Path(ayarlar.egitim_klasoru) / satir["dosya"]).unlink(missing_ok=True)
    baglanti.execute("DELETE FROM bardak_ornekleri WHERE id = ?", (ornek_id,))
    baglanti.commit()


__all__ = [
    "ETIKETLER",
    "BardakModeli",
    "EgitimSonucu",
    "Karsilastirma",
    "aktif_model_bilgisi",
    "egit",
    "etiketle",
    "etiketsizleri_getir",
    "modeli_devreden_cikar",
    "ornek_sil",
    "ornekleri_topla",
    "sayilar",
]
