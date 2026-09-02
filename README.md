# Laffogato — kafe bar sayacı

<sub>**NextGen Detector** ailesinden — kardeş projeler: DALSAN-ISG (fabrika), Otopark Takibi.</sub>

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

### HIK Connect (Hikvision) kamera — kafede kullandığımız

HIK Connect uygulaması görüntüyü buluttan izletir; bu sistem ise kameraya
**aynı ağdan, doğrudan RTSP ile** bağlanır (daha akıcıdır, internet kesilse
de çalışır). Sayaç sayfasındaki "Görüntü kaynağı" bölümünde **Hikvision
şablonunu doldur** düğmesi doğru kalıbı hazırlar:

```
rtsp://admin:SIFRE@192.168.1.64:554/Streaming/Channels/101
```

- **IP adresi:** HIK Connect'te kameranın ayarlarında ya da modemin cihaz
  listesinde yazar (192.168.x.x biçiminde).
- **Şifre:** kameranın etkinleştirme (aktivasyon) şifresi — HIK Connect'teki
  doğrulama kodu DEĞİL. Kullanıcı adı çoğu kamerada `admin`.
- **101 / 102:** 101 = ana akış (en kaliteli), 102 = düşük çözünürlüklü akış
  (eski bilgisayarda daha akıcı).
- Bağlanamazsanız kameranın web arayüzünde RTSP'nin açık olduğunu kontrol
  edin (Ayarlar → Ağ → Gelişmiş).

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

## Yönetici şifresi

Panel varsayılan olarak **şifresizdir** (kafe bilgisayarında yerel kullanım).
Şifre koymak için `.env` dosyasında şu satırı doldurup uygulamayı yeniden başlatın:

```
PANEL_SIFRESI=buraya-sifrenizi-yazin
```

Şifreyi unutursanız `.env` dosyasından silmeniz yeterli. `.env` GitHub'a
gönderilmez — kamera şifreniz ve panel şifreniz yalnızca kafedeki bilgisayarda durur.

---

## Sayım nasıl karar veriyor (özet)

Bardak, kadrajda göründüğü sürece TEK bir takip numarasıyla izlenir. Kadrajdan
çıkınca (takipçinin hafızası dolmadan hemen önce) kararı kesinleşir:

1. **Nereye gitti?** Önce bardağın SON gözlemlerine bakılır — tezgâhta ne kadar
   beklediği değil, sonunda hangi tarafa geçtiği önemlidir. Son gözlemler net
   bir taraf göstermiyorsa tüm yaşamı boyunca hangi tarafta daha çok görüldüğüne
   bakılır.
2. **Hangi taraf?** Karar, bardağın tezgâha DEĞDİĞİ nokta (kutunun alt-ortası)
   ile verilir; kutunun merkezi açılı kamerada yanıltır.
3. **Emin değilse "belirsiz".** Uydurma sayı üretilmez.

Kanıt fotoğrafı yalnızca **gerçekten sayılan** bardaklar için diske yazılır ve
bardağın son hâlini gösterir.

## Uyarılar

Yeni bir bardak sayıldığında ekranda bildirim çıkar. İsteğe bağlı olarak:

- **Sesli bildirim** — kısa bir bip. Tarayıcı kuralı gereği sayfaya bir kez
  tıklamak gerekir; ekranda "ses beklemede" yazarsa sebebi budur.
- **Sesli okuma** — "bardak müşteriye gitti" diye Türkçe seslendirir. Anons
  sistemi bağlanana kadar en pratik duyurma yoludur.

Uyarılar sunucudaki olay akışından gelir: aynı anda kapanan iki bardak iki ayrı
uyarı olur, hiçbiri atlanmaz.

## Günlük

`veri/loglar/laffogato.log` — sorun bildirirken bu dosyadaki satırları olduğu
gibi kopyalayın. Analizde bir hata olursa ana sayfada da kırmızı bir satır
olarak görünür.
