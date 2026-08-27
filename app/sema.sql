-- Laffogato şeması. Zamanlar ISO-8601 UTC; ekranda Türkiye saati.
-- BEGIN/COMMIT yok: uygulama tek transaction içinde uygular.

CREATE TABLE IF NOT EXISTS ayar (
    anahtar TEXT PRIMARY KEY,
    deger   TEXT NOT NULL
);

-- Her benzersiz bardak takibi bir satır: "kaç bardak yapıldı" sayımı budur.
CREATE TABLE IF NOT EXISTS bardaklar (
    id          INTEGER PRIMARY KEY,
    gun         TEXT NOT NULL,               -- YYYY-AA-GG (Türkiye günü)
    takip_id    INTEGER NOT NULL,
    baslangic   TEXT NOT NULL,               -- ISO-8601 UTC
    bitis       TEXT NOT NULL,
    kime        TEXT NOT NULL CHECK (kime IN ('musteri', 'barista', 'belirsiz')),
    musteri_gozlem INTEGER NOT NULL DEFAULT 0,
    barista_gozlem INTEGER NOT NULL DEFAULT 0,
    foto        TEXT,
    UNIQUE (gun, takip_id)                   -- aynı bardak iki kez sayılmaz
);

CREATE INDEX IF NOT EXISTS idx_bardak_gun ON bardaklar (gun, kime);

-- Kullanıcının kendi tanıttığı nesneler (ör. "Laffogato fincanı")
CREATE TABLE IF NOT EXISTS nesneler (
    id          INTEGER PRIMARY KEY,
    ad          TEXT NOT NULL UNIQUE,
    olusturuldu TEXT NOT NULL                -- ISO-8601 UTC
);

-- Nesnenin farklı açılardan referans fotoğrafları
CREATE TABLE IF NOT EXISTS nesne_fotolari (
    id        INTEGER PRIMARY KEY,
    nesne_id  INTEGER NOT NULL REFERENCES nesneler (id) ON DELETE CASCADE,
    dosya     TEXT NOT NULL,                 -- veri/nesneler altına göreli ad
    eklendi   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_foto_nesne ON nesne_fotolari (nesne_id);

-- Bardak doğrulayıcının eğitim örnekleri (Bardak Eğitimi sayfası).
-- Kullanıcı fotoğraf/video yükler; dedektörün bulduğu HER aday kutu buraya
-- etiketsiz düşer ve üç düğmeyle etiketlenir.
CREATE TABLE IF NOT EXISTS bardak_ornekleri (
    id          INTEGER PRIMARY KEY,
    dosya       TEXT NOT NULL,               -- veri/egitim altına göreli kırpık
    -- Sızıntısız bölme için: aynı yüklemeden gelen kırpıklar aynı partidedir
    -- ve eğitim/test arasında BÖLÜNMEZ (aynı bardağın iki karesi iki tarafa
    -- düşerse skor yalan çıkar).
    parti       TEXT NOT NULL,
    kaynak      TEXT NOT NULL CHECK (kaynak IN ('yukleme', 'kamera')),
    kutu        TEXT NOT NULL,               -- JSON normalize [x1,y1,x2,y2]
    -- Bugünkü sayım bu kutuyu bardak sayar mıydı? (COCO 39/40/41)
    coco_bardak INTEGER NOT NULL DEFAULT 0,
    etiket      TEXT CHECK (etiket IN ('bardak', 'degil', 'belirsiz')),
    eklendi     TEXT NOT NULL,               -- ISO-8601 UTC
    etiketlendi TEXT
);

CREATE INDEX IF NOT EXISTS idx_ornek_etiket ON bardak_ornekleri (etiket);
CREATE INDEX IF NOT EXISTS idx_ornek_parti ON bardak_ornekleri (parti);
