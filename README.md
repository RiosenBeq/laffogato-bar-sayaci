# Laffogato — kafe bar sayacı

Bar alanına bakan kameradan **günde kaç bardak yapıldığını**, bunların
**ne kadarını müşterinin içtiğini** ve **baristanın kendine kaç tane
yaptığını** çıkaran deneme uygulaması. Canlı kamera görüntüsü ekranda izlenir.

Diğer projelerden tamamen ayrıdır: kendi klasörü, kendi veritabanı, kendi
portu (8100).

## Çalıştırma

1. **Baslat-Mac.command** (Windows'ta **Baslat-Windows.bat**) dosyasına çift tıkla.
2. Tarayıcı `http://127.0.0.1:8100` adresinde açılır.
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

## Nasıl sayıyor

Kamera bardakları tanır, her birine takip numarası verir ve kadrajdan çıkana
kadar **hangi tarafta durduğunu** sayar. Bardak kaybolunca karar verilir:

- Ağırlıklı olarak müşteri tarafında → **müşteri içti**
- Ağırlıklı olarak barista tarafında → **barista kendine yaptı**
- Kanıt zayıfsa → **belirsiz** (tahmin yürütülmez)

## Diğer sayfalar

| Sayfa | Ne yapar |
|---|---|
| **Kütüphane** | Kendi bardağını/nesneni farklı açılardan fotoğraflayıp tanıtırsın |
| **Kare tarama** | Kameradan aldığın kareleri yükleyip ne bulduğunu görürsün (sayaçlara dokunmaz) |

## Dürüst sınırlar

- Hazır model genel amaçlıdır; kafenin kendi bardaklarıyla ince ayar yapılırsa
  isabet belirgin artar.
- Üst üste duran, elle kapatılan veya çok küçük görünen bardaklar kaçabilir.
- Tezgâhta uzun süre bekleyip yeniden görünen bardak ikinci kez sayılabilir.
- Nesne tanıtma bir **model eğitimi değildir**: renk + desen parmak izi
  karşılaştırmasıdır. Düz beyaz fincanlarda yalnız renge dayanır.

## Test

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```
