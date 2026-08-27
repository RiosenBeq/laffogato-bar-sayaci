# Laffogato — kafe bar sayacı

Bar alanına bakan kameradan **günde kaç bardak yapıldığını**, bunların
**ne kadarını müşterinin içtiğini** ve **baristanın kendine kaç tane
yaptığını** çıkaran deneme uygulaması. Canlı kamera görüntüsü ekranda izlenir.

Diğer projelerden tamamen ayrıdır: kendi klasörü, kendi veritabanı, kendi
portu (8100).

## Çalıştırma

1. **Baslat-Mac.command** (Windows'ta **Baslat-Windows.bat**) dosyasına çift tıkla.
2. Uygulama **kendi penceresinde** açılır (tarayıcı gerekmez). Pencereyi kapatmak sistemi durdurur. Gerekirse tarayıcıdan da ulaşılabilir: `http://127.0.0.1:8100`
3. macOS ilk açılışta **kamera izni** sorar — "İzin Ver" de. (Sonradan:
   Sistem Ayarları → Gizlilik ve Güvenlik → Kamera.)

Kamerayı `.env` dosyasındaki **KAYNAK** satırı belirler:

```
KAYNAK=0                    # bilgisayarın kamerası (en kolay deneme)
KAYNAK=1                    # USB ile takılı ikinci kamera
KAYNAK=rtsp://...           # kafedeki IP/güvenlik kamerası
KAYNAK=veri/kayit.mp4       # kayıtlı video
```

## Kurulum sırası (bir kez)

1. Sistemi başlat, canlı görüntünün geldiğini gör.
2. **Barista tarafı** ve **Müşteri tarafı** alanlarını görüntü üzerine çiz
   (tezgâhın arkası ve önü).
3. Gerekirse **tespit hassasiyetini** ayarla (bardak küçük bir nesnedir;
   0,30 iyi bir başlangıç, düşürürsen daha çok yakalar ama yanlış tespit artar).
4. İstersen **Bardak eğitimi** sayfasından kendi bardaklarını tanıt: farklı
   açılardan görüntü yükle, çıkan kırpıkları etiketle, eğitimi çalıştır.
   Ölçüm dürüst olsun diye **en az iki ayrı yükleme** gerekir.

## Nasıl sayıyor

Kamera bardakları tanır, her birine takip numarası verir ve kadrajdan çıkana
kadar **hangi tarafta durduğunu** sayar. Bardak kaybolunca karar verilir:

- Ağırlıklı olarak müşteri tarafında → **müşteri içti**
- Ağırlıklı olarak barista tarafında → **barista kendine yaptı**
- Kanıt zayıfsa → **belirsiz** (tahmin yürütülmez)

## Diğer sayfalar

| Sayfa | Ne yapar |
|---|---|
| **Bardak eğitimi** | Kendi bardaklarının görüntülerini yükler, kırpıkları etiketler ve tanımayı eğitirsin |
| **Kütüphane** | Kendi bardağını/nesneni farklı açılardan fotoğraflayıp tanıtırsın |
| **Kare tarama** | Fotoğraf ya da video yükleyip ne bulduğunu görürsün — videodan kareler otomatik alınır (sayaçlara dokunmaz) |

## Dürüst sınırlar

- Hazır model genel amaçlıdır; kafenin kendi bardaklarıyla ince ayar yapılırsa
  isabet belirgin artar.
- Üst üste duran, elle kapatılan veya çok küçük görünen bardaklar kaçabilir.
- Tezgâhta bekleyip yeniden görünen bardağa karşı iki katmanlı koruma vardır
  (takipçi hafızası + aynı yer/boy/renk kontrolü); yine de arka arkaya aynı
  yere konan **birbirine çok benzeyen iki bardak** tek sayılabilir.
- **Kütüphane** sayfasındaki nesne tanıtma bir model eğitimi değildir: renk +
  desen parmak izi karşılaştırmasıdır. Düz beyaz fincanlarda yalnız renge dayanır.
- **Bardak eğitimi** sayfası gerçek bir eğitim yapar ama hazır tespit modelini
  yeniden eğitmez: onun bulduğu aday kutulara "bu bizim bardağımız mı?" diye
  soran küçük bir doğrulayıcı eğitir. Yeterli ve çeşitli veri yoksa eğitim
  çalışmaz — sistem karşılığı olmayan bir isabet sayısı göstermez.

## Platform ve Docker

| | Mac / Windows (çift tık) | Docker (Mac/Win) | Docker (Linux sunucu) |
|---|---|---|---|
| Arayüz, video dosyası, **RTSP kamera** | ✅ | ✅ | ✅ |
| **Bilgisayarın kendi kamerası** | ✅ | ❌ Docker Desktop kamerayı veremez | ⚠️ USB kamera, ayar gerekir |
| GPU hızlandırma | ❌ / ⚠️ WSL2 | ❌ | ✅ NVIDIA |
| 7/24 kendiliğinden çalışma | ⚠️ pencere açık kalmalı | ✅ | ✅ |

Docker ile çalıştırmak için:

```bash
cp .env.example .env
bash models/indir.sh      # model indirilmeden imaj DERLENMEZ (bilerek)
docker compose up -d
docker compose logs -f
```

`veri/` klasörü ve `.env` container dışında durur; container silinse de
veriler kaybolmaz. Ayrıntılı kılavuz: fabrika projesindeki `NASIL-CALISIR.md`.

## Test

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```
