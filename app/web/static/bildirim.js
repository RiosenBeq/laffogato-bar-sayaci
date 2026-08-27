// Canlı bildirimler: yeni olayları köşede cam bir kutuyla duyurur.
// Ses isteğe bağlıdır (data-ses-anahtari işaretli kutuyla açılır, tarayıcıda saklanır).
window.Bildirim = (function () {
  var kap = null;

  function kapAl() {
    if (!kap) {
      kap = document.createElement("div");
      kap.className = "bildirimler";
      document.body.appendChild(kap);
    }
    return kap;
  }

  function goster(html, tur, sureMs) {
    var kutu = document.createElement("div");
    kutu.className = "bildirim" + (tur ? " " + tur : "");
    kutu.innerHTML = html;
    kapAl().appendChild(kutu);
    setTimeout(function () {
      kutu.classList.add("cikiyor");
      setTimeout(function () { kutu.remove(); }, 350);
    }, sureMs || 5000);
  }

  var SES_ANAHTARI = "bildirim-sesi";

  function sesAcikMi() {
    try { return localStorage.getItem(SES_ANAHTARI) === "1"; } catch (hata) { return false; }
  }

  function sesAyarla(acik) {
    try { localStorage.setItem(SES_ANAHTARI, acik ? "1" : "0"); } catch (hata) { /* özel pencere */ }
  }

  function sesCal() {
    if (!sesAcikMi()) return;
    try {
      var baglam = new (window.AudioContext || window.webkitAudioContext)();
      var osilator = baglam.createOscillator();
      var kazanc = baglam.createGain();
      osilator.type = "sine";
      osilator.frequency.value = 880;
      kazanc.gain.setValueAtTime(0.001, baglam.currentTime);
      kazanc.gain.exponentialRampToValueAtTime(0.18, baglam.currentTime + 0.02);
      kazanc.gain.exponentialRampToValueAtTime(0.001, baglam.currentTime + 0.5);
      osilator.connect(kazanc);
      kazanc.connect(baglam.destination);
      osilator.start();
      osilator.stop(baglam.currentTime + 0.55);
      setTimeout(function () { baglam.close(); }, 700);
    } catch (hata) { /* ses desteklenmiyorsa sessiz kal */ }
  }

  document.querySelectorAll("[data-ses-anahtari]").forEach(function (kutu) {
    kutu.checked = sesAcikMi();
    kutu.addEventListener("change", function () {
      sesAyarla(kutu.checked);
      if (kutu.checked) sesCal(); // açınca duyulabilir bir deneme sesi
    });
  });

  return { goster: goster, sesCal: sesCal };
})();
