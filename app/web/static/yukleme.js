// Dosya yükleme alanı: sürükle-bırak, önizleme, doğrulama, gönderim durumu.
// JS kapalıysa bile çalışır: input dosya alanının üstünü kapladığı için
// tıklamak her koşulda dosya seçtirir; buradaki kod deneyimi zenginleştirir.
(function () {
  var GORSEL_UZANTILAR = [".jpg", ".jpeg", ".png", ".webp", ".bmp"];
  var VIDEO_UZANTILAR = [".mp4", ".mov", ".avi", ".mkv", ".webm"];
  var EN_BUYUK_GORSEL = 12 * 1024 * 1024; // 12 MB
  var EN_BUYUK_VIDEO = 200 * 1024 * 1024; // 200 MB

  function uzanti(ad) {
    var n = ad.lastIndexOf(".");
    return n === -1 ? "" : ad.slice(n).toLowerCase();
  }

  function boyutMetni(bayt) {
    if (bayt >= 1024 * 1024) return (bayt / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
    return Math.max(1, Math.round(bayt / 1024)) + " KB";
  }

  document.querySelectorAll(".yukleme").forEach(function (alan) {
    var input = alan.querySelector('input[type="file"]');
    var birak = alan.querySelector(".birak-alani");
    var liste = alan.querySelector(".secilenler");
    var mesaj = alan.querySelector(".yukleme-mesaj");
    if (!input || !birak || !liste) return;

    var enCok = parseInt(alan.dataset.enCok || "0", 10); // 0 = sınırsız
    var videoOlur = alan.dataset.video === "1";
    var dosyalar = []; // seçili File nesneleri (bizim tuttuğumuz gerçek liste)

    function hataGoster(metin) {
      if (!mesaj) return;
      mesaj.textContent = metin;
      mesaj.hidden = !metin;
    }

    function inputaYaz() {
      // Tarayıcıya gidecek gerçek listeyi input.files'a geri yaz.
      var tasima = new DataTransfer();
      dosyalar.forEach(function (d) { tasima.items.add(d); });
      input.files = tasima.files;
    }

    function ciz() {
      liste.innerHTML = "";
      liste.hidden = dosyalar.length === 0;
      dosyalar.forEach(function (dosya, sira) {
        var kart = document.createElement("div");
        kart.className = "secili-kart";

        if (VIDEO_UZANTILAR.indexOf(uzanti(dosya.name)) !== -1) {
          var video = document.createElement("div");
          video.className = "secili-video";
          video.textContent = "🎬";
          kart.appendChild(video);
        } else {
          var img = document.createElement("img");
          img.alt = dosya.name;
          img.src = URL.createObjectURL(dosya);
          img.onload = function () { URL.revokeObjectURL(img.src); };
          kart.appendChild(img);
        }

        var ad = document.createElement("div");
        ad.className = "secili-ad";
        ad.textContent = dosya.name + " · " + boyutMetni(dosya.size);
        ad.title = dosya.name;
        kart.appendChild(ad);

        var kaldir = document.createElement("button");
        kaldir.type = "button";
        kaldir.className = "secili-kaldir";
        kaldir.textContent = "✕";
        kaldir.setAttribute("aria-label", dosya.name + " dosyasını listeden çıkar");
        kaldir.addEventListener("click", function () {
          dosyalar.splice(sira, 1);
          inputaYaz();
          ciz();
          hataGoster("");
        });
        kart.appendChild(kaldir);

        liste.appendChild(kart);
      });
    }

    function ekle(yeniDosyalar) {
      var hatalar = [];
      Array.prototype.forEach.call(yeniDosyalar, function (dosya) {
        var uz = uzanti(dosya.name);
        var video = VIDEO_UZANTILAR.indexOf(uz) !== -1;
        var gorsel = GORSEL_UZANTILAR.indexOf(uz) !== -1;

        if (!gorsel && !(videoOlur && video)) {
          hatalar.push("'" + dosya.name + "' desteklenmiyor (JPG, PNG, WEBP" +
            (videoOlur ? " ya da MP4/MOV video" : "") + " seçin).");
          return;
        }
        var sinir = video ? EN_BUYUK_VIDEO : EN_BUYUK_GORSEL;
        if (dosya.size > sinir) {
          hatalar.push("'" + dosya.name + "' çok büyük (en fazla " +
            (video ? "200 MB video" : "12 MB fotoğraf") + ").");
          return;
        }
        var zatenVar = dosyalar.some(function (d) {
          return d.name === dosya.name && d.size === dosya.size;
        });
        if (zatenVar) return; // aynı dosya iki kez eklenmesin
        if (enCok && dosyalar.length >= enCok) {
          hatalar.push("En fazla " + enCok + " dosya seçilebilir; fazlası alınmadı.");
          return;
        }
        dosyalar.push(dosya);
      });
      inputaYaz();
      ciz();
      hataGoster(hatalar.length ? hatalar[0] : "");
    }

    // Dosya seçme penceresinden gelenler
    input.addEventListener("change", function () {
      var secilenler = Array.prototype.slice.call(input.files);
      dosyalar = [];
      ekle(secilenler);
    });

    // Sürükle-bırak
    ["dragenter", "dragover"].forEach(function (tur) {
      birak.addEventListener(tur, function (olay) {
        olay.preventDefault();
        birak.classList.add("surukleniyor");
      });
    });
    ["dragleave", "drop"].forEach(function (tur) {
      birak.addEventListener(tur, function (olay) {
        olay.preventDefault();
        birak.classList.remove("surukleniyor");
      });
    });
    birak.addEventListener("drop", function (olay) {
      if (olay.dataTransfer && olay.dataTransfer.files.length) {
        ekle(olay.dataTransfer.files);
      }
    });

    // Gönderim: boş göndermeyi engelle, düğmeyi "Yükleniyor…" durumuna al
    var form = alan.closest("form");
    if (form) {
      form.addEventListener("submit", function (olay) {
        if (alan.dataset.zorunlu === "1" && dosyalar.length === 0 && input.files.length === 0) {
          olay.preventDefault();
          hataGoster("Önce dosya seçin ya da bu alana sürükleyin.");
          return;
        }
        var dugme = form.querySelector('button[type="submit"], button:not([type])');
        if (dugme) {
          dugme.classList.add("yukleniyor");
          dugme.dataset.eskiMetin = dugme.textContent;
          var videoVar = dosyalar.some(function (d) {
            return VIDEO_UZANTILAR.indexOf(uzanti(d.name)) !== -1;
          });
          dugme.textContent = videoVar
            ? "Video işleniyor… (birkaç saniye sürebilir)"
            : "Yükleniyor…";
        }
      });
    }
  });

  // Tüm sayfalarda: gönderilen sıradan formların düğmesi de kilitlensin
  // (çift tıklamayla aynı kaydın iki kez gitmesini önler).
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (olay) {
      if (olay.defaultPrevented) return; // engellenen gönderim düğmeyi kilitlemesin
      var dugme = form.querySelector('button[type="submit"], button:not([type])');
      if (dugme && !dugme.classList.contains("yukleniyor")) {
        setTimeout(function () { dugme.disabled = true; }, 0);
        setTimeout(function () { dugme.disabled = false; }, 4000);
      }
    });
  });
})();
