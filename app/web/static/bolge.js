// Bölge çizimi: "Çiz" düğmesine bas, görüntüde köşelere tıkla, kaydet.
// Koordinatlar normalize (0-1) kaydedilir; çözünürlük değişse de geçerli kalır.
(function () {
  var tuval = document.getElementById("tuval");
  var not = document.getElementById("tuval-not");
  if (!tuval) return;
  var ctx = tuval.getContext("2d");
  var noktalar = [];
  var taraf = null;

  var RENK = { musteri: "#22c55e", barista: "#ea8c3c" };

  function boyutla() {
    tuval.width = tuval.clientWidth;
    tuval.height = tuval.clientHeight;
    ciz();
  }
  window.addEventListener("resize", boyutla);

  function ciz() {
    ctx.clearRect(0, 0, tuval.width, tuval.height);
    if (noktalar.length === 0) return;
    var renk = RENK[taraf] || "#22c55e";
    ctx.beginPath();
    noktalar.forEach(function (n, i) {
      var x = n[0] * tuval.width, y = n[1] * tuval.height;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    if (noktalar.length > 2) ctx.closePath();
    ctx.strokeStyle = renk;
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.fillStyle = renk + "33";
    ctx.fill();
    noktalar.forEach(function (n) {
      ctx.fillStyle = renk;
      ctx.beginPath();
      ctx.arc(n[0] * tuval.width, n[1] * tuval.height, 4, 0, 7);
      ctx.fill();
    });
  }

  tuval.addEventListener("click", function (olay) {
    if (!taraf) return;
    var kutu = tuval.getBoundingClientRect();
    noktalar.push([
      (olay.clientX - kutu.left) / kutu.width,
      (olay.clientY - kutu.top) / kutu.height,
    ]);
    ciz();
    document.getElementById("poligon").value = JSON.stringify(noktalar);
    document.getElementById("bolge-kaydet").disabled = noktalar.length < 3;
    if (noktalar.length >= 3) {
      not.textContent = "Alan hazır (" + noktalar.length +
        " köşe). Köşe eklemeye devam edebilir ya da 'Bölgeyi Kaydet'e basabilirsiniz.";
    }
  });

  document.querySelectorAll("[data-ciz]").forEach(function (dugme) {
    dugme.addEventListener("click", function () {
      taraf = dugme.dataset.ciz;
      noktalar = [];
      ciz();
      tuval.classList.add("aktif");
      document.getElementById("taraf").value = taraf;
      document.getElementById("poligon").value = "";
      document.getElementById("bolge-form").classList.remove("gizli");
      document.getElementById("bolge-kaydet").disabled = true;
      not.textContent =
        (taraf === "musteri" ? "MÜŞTERİ" : "BARİSTA") +
        " tarafını çiziyorsunuz: görüntüde alanın köşelerine sırayla tıklayın (en az 3).";
    });
  });

  document.getElementById("bolge-iptal").addEventListener("click", function () {
    taraf = null;
    noktalar = [];
    ciz();
    tuval.classList.remove("aktif");
    document.getElementById("bolge-form").classList.add("gizli");
    not.textContent =
      "Turuncu kutu = bardak. Yeşil alan = müşteri tarafı, turuncu alan = barista tarafı.";
  });

  setTimeout(boyutla, 300);
  boyutla();
})();
