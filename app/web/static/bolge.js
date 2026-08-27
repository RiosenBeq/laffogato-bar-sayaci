// Bölge çizimi — kolaylaştırılmış sürüm.
//
// Kullanım: "Çiz"e bas, görüntüde alanın köşelerine sırayla tıkla (en az 3).
// Fare gezerken kenar canlı önizlenir; İLK NOKTAYA tıklayınca alan kapanır.
// Esc iptal eder, "Geri Al" son köşeyi siler.
// Koordinatlar normalize (0-1) kaydedilir; çözünürlük değişse de geçerli.
(function () {
  var tuval = document.getElementById("tuval");
  var not = document.getElementById("tuval-not");
  if (!tuval) return;
  var ctx = tuval.getContext("2d");
  var kilavuz = document.getElementById("cizim-kilavuz");
  var geriDugme = document.getElementById("cizim-geri");
  var durumYazi = document.getElementById("cizim-durum");

  var noktalar = [];
  var taraf = null;
  var imlec = null;
  var kapandi = false;
  var TUTMA = 14; // px — ilk noktayı yakalama yarıçapı

  var RENK = { musteri: "#22c55e", barista: "#ea8c3c" };
  var AD = { musteri: "MÜŞTERİ", barista: "BARİSTA" };
  var VARSAYILAN_NOT =
    "Turuncu kutu = bardak. Yeşil alan = müşteri tarafı, turuncu alan = barista tarafı.";

  function boyutla() {
    if (tuval.width === tuval.clientWidth && tuval.height === tuval.clientHeight) return;
    tuval.width = tuval.clientWidth;
    tuval.height = tuval.clientHeight;
    ciz();
  }
  window.addEventListener("resize", boyutla);
  // Canlı görüntü sonradan gelince kart büyür; tampon ile ekran boyutu
  // ayrışırsa tıklamalar ve kapatma isabeti kayar — her yenilemede eşitle.
  var onizlemeImg = document.getElementById("onizleme");
  if (onizlemeImg) onizlemeImg.addEventListener("load", boyutla);

  function pikselde(n) { return [n[0] * tuval.width, n[1] * tuval.height]; }

  function ciz() {
    ctx.clearRect(0, 0, tuval.width, tuval.height);
    if (noktalar.length === 0) return;
    var renk = RENK[taraf] || "#22c55e";

    // alan çizgileri
    ctx.beginPath();
    noktalar.forEach(function (n, i) {
      var p = pikselde(n);
      if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
    });
    if (kapandi || noktalar.length > 2) ctx.closePath();
    ctx.strokeStyle = renk;
    ctx.lineWidth = 3;
    ctx.stroke();
    if (noktalar.length > 2) {
      ctx.fillStyle = renk + "33";
      ctx.fill();
    }

    // canlı önizleme: son köşeden fareye kesikli çizgi
    if (!kapandi && taraf && imlec && noktalar.length > 0) {
      var son = pikselde(noktalar[noktalar.length - 1]);
      ctx.setLineDash([7, 6]);
      ctx.lineWidth = 2;
      ctx.strokeStyle = renk;
      ctx.beginPath();
      ctx.moveTo(son[0], son[1]);
      ctx.lineTo(imlec[0], imlec[1]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // köşe noktaları; ilk nokta kapatma hedefi olarak vurgulanır
    noktalar.forEach(function (n, i) {
      var p = pikselde(n);
      ctx.beginPath();
      ctx.arc(p[0], p[1], i === 0 && !kapandi && noktalar.length >= 3 ? 8 : 5, 0, 7);
      ctx.fillStyle = renk;
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#fff";
      ctx.stroke();
    });
  }

  function kilavuzYaz(metin) {
    if (!kilavuz) return;
    kilavuz.textContent = metin;
    kilavuz.classList.toggle("acik", !!metin);
  }

  function durumYaz(metin) {
    if (durumYazi) durumYazi.textContent = metin;
  }

  function formaYaz() {
    document.getElementById("poligon").value = JSON.stringify(noktalar);
    document.getElementById("bolge-kaydet").disabled = noktalar.length < 3;
    if (geriDugme) geriDugme.disabled = noktalar.length === 0;
  }

  function kapat() {
    kapandi = true;
    imlec = null;
    tuval.classList.remove("aktif");
    kilavuzYaz("Alan kapatıldı (" + noktalar.length +
      " köşe). Şimdi 'Bölgeyi Kaydet'e basın; vazgeçmek için İptal.");
    durumYaz("Alan hazır ✓ — " + noktalar.length + " köşe");
    if (not) not.textContent = "Alan hazır. 'Bölgeyi Kaydet'e basın.";
    ciz();
  }

  tuval.addEventListener("click", function (olay) {
    if (!taraf || kapandi) return;
    boyutla(); // tıklamadan önce tampon ve ekran boyutu aynı olsun
    var kutu = tuval.getBoundingClientRect();
    var x = olay.clientX - kutu.left, y = olay.clientY - kutu.top;

    // ilk noktaya yeterince yakın tıklama alanı kapatır
    if (noktalar.length >= 3) {
      var ilk = pikselde(noktalar[0]);
      if (Math.hypot(ilk[0] - x, ilk[1] - y) <= TUTMA) {
        formaYaz();
        kapat();
        return;
      }
    }

    noktalar.push([x / kutu.width, y / kutu.height]);
    formaYaz();
    ciz();
    if (noktalar.length < 3) {
      durumYaz(noktalar.length + " köşe — en az 3 gerekli");
      kilavuzYaz(AD[taraf] + " tarafını çiziyorsunuz: köşelere sırayla tıklayın (en az 3). " +
        "Esc: iptal, Geri Al: son köşe.");
    } else {
      durumYaz(noktalar.length + " köşe ✓");
      kilavuzYaz("Köşe eklemeye devam edebilirsiniz. Bitirmek için İLK (büyük) noktaya tıklayın " +
        "ya da doğrudan 'Bölgeyi Kaydet'e basın.");
      if (not) not.textContent = "Alan hazır (" + noktalar.length +
        " köşe). Köşe ekleyebilir ya da 'Bölgeyi Kaydet'e basabilirsiniz.";
    }
  });

  tuval.addEventListener("mousemove", function (olay) {
    if (!taraf || kapandi || noktalar.length === 0) return;
    var kutu = tuval.getBoundingClientRect();
    imlec = [olay.clientX - kutu.left, olay.clientY - kutu.top];
    ciz();
  });

  function sifirla() {
    taraf = null;
    noktalar = [];
    imlec = null;
    kapandi = false;
    ciz();
    tuval.classList.remove("aktif");
    document.getElementById("bolge-form").classList.add("gizli");
    kilavuzYaz("");
    durumYaz("");
    if (not) not.textContent = VARSAYILAN_NOT;
  }

  document.addEventListener("keydown", function (olay) {
    if (olay.key === "Escape" && taraf) sifirla();
  });

  if (geriDugme) geriDugme.addEventListener("click", function () {
    if (!taraf) return;
    noktalar.pop();
    kapandi = false;
    formaYaz();
    tuval.classList.add("aktif");
    durumYaz(noktalar.length + " köşe" + (noktalar.length >= 3 ? " ✓" : " — en az 3 gerekli"));
    kilavuzYaz(noktalar.length >= 3
      ? "Köşe eklemeye devam edebilirsiniz. Bitirmek için İLK (büyük) noktaya tıklayın " +
        "ya da 'Bölgeyi Kaydet'e basın."
      : AD[taraf] + " tarafını çiziyorsunuz: köşelere sırayla tıklayın (en az 3).");
    if (not) not.textContent = noktalar.length >= 3
      ? "Alan hazır (" + noktalar.length + " köşe). 'Bölgeyi Kaydet'e basabilirsiniz."
      : AD[taraf] + " tarafını çiziyorsunuz: köşelere sırayla tıklayın (en az 3).";
    ciz();
  });

  document.querySelectorAll("[data-ciz]").forEach(function (dugme) {
    dugme.addEventListener("click", function () {
      taraf = dugme.dataset.ciz;
      noktalar = [];
      imlec = null;
      kapandi = false;
      ciz();
      tuval.classList.add("aktif");
      document.getElementById("taraf").value = taraf;
      document.getElementById("poligon").value = "";
      document.getElementById("bolge-form").classList.remove("gizli");
      document.getElementById("bolge-kaydet").disabled = true;
      if (geriDugme) geriDugme.disabled = true;
      kilavuzYaz(AD[taraf] + " tarafını çiziyorsunuz: görüntüde alanın köşelerine " +
        "sırayla tıklayın (en az 3). Fare gezerken kenar önizlenir; bitirince ilk noktaya tıklayın.");
      durumYaz("0 köşe");
      if (not) not.textContent =
        AD[taraf] + " tarafını çiziyorsunuz: görüntüde alanın köşelerine sırayla tıklayın (en az 3).";
    });
  });

  document.getElementById("bolge-iptal").addEventListener("click", sifirla);

  setTimeout(boyutla, 300);
  boyutla();
})();
