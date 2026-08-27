# CLAUDE.md — LAFFOGATO (kafe bar sayacı)

Claude Code'un bu depoda çalışırken uyacağı kurallar. Her oturumun başında okunur.

> **ÖNEMLİ:** Projeyi yazılım bilmeyen bir kişi, yapay zeka yardımıyla yürütüyor.
> Kullanıcı kodu okumaz; sistemin **davranışını** deneyerek onaylar.

## 1. Proje tek cümleyle

Bar alanına bakan kameradan (kafede **HIK Connect / Hikvision**, RTSP ile yerel
ağdan) günde kaç bardak yapıldığını, kaçının müşteriye gittiğini ve baristanın
kendine kaç tane yaptığını sayan; kendi bardaklarını tanımak için arayüzden
eğitilebilen uygulama. Port 8100; NextGen Detector ailesindendir ve kardeş
projelerden (DALSAN-ISG, OTOPARK-DEMO) tamamen bağımsız çalışır.

## 2. Altın kurallar

1. **En az parça:** yeni kütüphane/servis eklemeden önce "bu olmadan yapılabilir
   mi?" diye sor. **torch YOK ve eklenemez** — eğitim numpy lojistik regresyondur.
2. **Sayı uydurma:** kanıt yetersizse "belirsiz" denir; belirsiz asla sonuç
   sayılmaz. Eğitim ölçümü şüpheliyse (kopya veri, tek parti, küçük/dengesiz
   test kümesi) eğitim ÇALIŞMAZ ve nedenini Türkçe söyler.
3. **Ölçmeden devreye alma:** yeni model, eski yöntemle AYNI test kırpıklarında
   karşılaştırılır; yalnızca belirsizi düşürüp isabeti korursa devreye girer.
4. **Her şey Türkçe ve açıklamalı:** her ana bölümde "?" balonu, kritik
   düğmelerde `title`. Yeni arayüz öğesi eklerken açıklamasını da ekle.

## 3. Teknoloji — sabit

| Katman | Karar |
|---|---|
| Dil / çatı | Python 3.12, FastAPI, Jinja2 + sade JS (React/Node YOK) |
| Veritabanı | SQLite: `veri/laffogato.db`; şema `app/sema.sql` (idempotent) |
| Görüntü | OpenCV (RTSP over TCP); tespit YOLOX ONNX + onnxruntime |
| Takip | supervision (ByteTrack) — `lost_track_buffer = int(saniye * 30)`; |
|  | supervision bunu `int(fps/30*buffer)` ile ölçekler, düz sayı verme! |
| Test / lint | pytest, ruff (line-length 100) |

## 4. Kritik tasarım kararları (ölçülerek alındı — geri alma)

- **Çift sayım:** birinci savunma takipçi hafızası (`_IZ_HAFIZASI_SN=15`);
  ikincisi `TekrarKorumasi` (bardak.py) — penceresi BİLEREK kısa (10 sn),
  zincirleme yok, her hatıra bir kez bastırır. Uzun pencere gerçek bardakları
  yutar: 90 sn'de 10 bardaktan 9'u kaybolmuştu (ölçüldü).
- **Eğitim bölmesi parti bazlı**, en eski parti daima eğitimde kalır; yakın
  kopyalar testten çıkarılır. `app/egitim.py` üstündeki açıklamaları oku.
- **Doğrulayıcı:** modelin "değil" dediği kutu elenir, "belirsiz" ELENMEZ;
  genişletilmiş sınıflar (bowl/vase → "aday") ancak model AÇIKÇA "bardak"
  derse sayıma girer.

## 5. Test komutları

```bash
.venv/bin/python -m pytest -q     # ~115 test, kamerasız, saniyeler
.venv/bin/ruff check . && .venv/bin/ruff format .
```

## 6. Marka

Laffogato kendi markasını taşır (☕ başlık); sayfa altında **NextGen Detector**
imzası vardır (`app/web/static/logo.svg`). Logo değişirse üç kardeş projede
birden güncellenir.
