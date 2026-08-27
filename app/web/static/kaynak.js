// Görüntü kaynağı seçimi: tür kartına göre alanları göster, Bağlantıyı Sına.
(function () {
  var form = document.getElementById("kaynak-form");
  if (!form) return;

  function guncelle() {
    var secili = form.querySelector('input[name="tur"]:checked');
    var tur = secili ? secili.value : "";
    form.querySelectorAll(".kaynak-alan").forEach(function (alan) {
      alan.classList.toggle("acik", alan.dataset.tur === tur);
    });
  }
  form.querySelectorAll('input[name="tur"]').forEach(function (radyo) {
    radyo.addEventListener("change", guncelle);
  });
  guncelle();

  var sina = document.getElementById("kaynak-sina");
  var sonuc = document.getElementById("sina-sonuc");
  if (sina && sonuc) {
    sina.addEventListener("click", function () {
      var eskiMetin = sina.textContent;
      sina.disabled = true;
      sina.classList.add("yukleniyor");
      sina.textContent = "Bağlanılıyor… (birkaç saniye sürebilir)";
      sonuc.className = "sina-sonuc";
      sonuc.textContent = "";
      fetch("/ayarlar/kaynak/sina", { method: "POST", body: new FormData(form) })
        .then(function (y) { return y.json(); })
        .then(function (v) {
          sonuc.className = "sina-sonuc acik " + (v.ok ? "iyi" : "kotu");
          sonuc.textContent = (v.ok ? "✓ " : "✗ ") + v.mesaj;
          if (v.gorsel) {
            var img = document.createElement("img");
            img.src = v.gorsel;
            img.alt = "kaynaktan alınan görüntü";
            sonuc.appendChild(img);
          }
        })
        .catch(function () {
          sonuc.className = "sina-sonuc acik kotu";
          sonuc.textContent = "✗ Sınama isteği gönderilemedi; sistemin açık olduğundan emin olun.";
        })
        .finally(function () {
          sina.disabled = false;
          sina.classList.remove("yukleniyor");
          sina.textContent = eskiMetin;
        });
    });
  }

  // Kaydet: yeniden başlatma birkaç saniye sürer — düğmeyi kilitle, bilgi ver.
  // Enter'a art arda basmak da ikinci bir gönderim üretmesin.
  var gonderiliyor = false;
  form.addEventListener("submit", function (olay) {
    if (gonderiliyor) {
      olay.preventDefault();
      return;
    }
    gonderiliyor = true;
    var dugme = form.querySelector('button[type="submit"], button:not([type="button"])');
    if (dugme) {
      dugme.classList.add("yukleniyor");
      dugme.textContent = "Kaydediliyor ve yeniden başlatılıyor…";
    }
    if (sina) sina.disabled = true;
  });
})();

// Kaydırıcılar: değeri anlık göster (mesafe eşiği, hassasiyet)
document.querySelectorAll(".kaydirici").forEach(function (alan) {
  var surgu = alan.querySelector('input[type="range"]');
  var deger = alan.querySelector(".kaydirici-deger");
  if (!surgu || !deger) return;
  var birim = deger.dataset.birim || "";
  function yaz() { deger.textContent = String(surgu.value).replace(".", ",") + birim; }
  surgu.addEventListener("input", yaz);
  yaz();
});
