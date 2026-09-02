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
  var KONUSMA_ANAHTARI = "bildirim-konusma";

  // TEK ses bağlamı. Her uyarıda yeni AudioContext açan kod, tarayıcının
  // otomatik oynatma kuralı yüzünden "suspended" durumda başlıyor ve HİÇ
  // ses çıkmıyordu; üstelik bu sessizlik görünmüyordu (açma kutusuna
  // tıklandığında çalışan deneme sesi gerçek bir kullanıcı hareketi
  // olduğu için duyuluyor, sonrakiler duyulmuyordu).
  var baglam = null;

  function baglamAl() {
    if (baglam) return baglam;
    var Yapici = window.AudioContext || window.webkitAudioContext;
    if (!Yapici) return null;
    try { baglam = new Yapici(); } catch (hata) { return null; }
    return baglam;
  }

  // İlk kullanıcı hareketinde bağlamı uyandır; sonrası sessizce çalışır.
  function uyandir() {
    var b = baglamAl();
    if (b && b.state === "suspended") b.resume();
  }
  document.addEventListener("click", uyandir);
  document.addEventListener("keydown", uyandir);

  function konusmaAcikMi() {
    try { return localStorage.getItem(KONUSMA_ANAHTARI) === "1"; } catch (hata) { return false; }
  }

  function konusmaAyarla(acik) {
    try { localStorage.setItem(KONUSMA_ANAHTARI, acik ? "1" : "0"); } catch (hata) { /* ozel */ }
  }

  function seslendir(metin) {
    if (!konusmaAcikMi() || !window.speechSynthesis) return;
    try {
      var soz = new window.SpeechSynthesisUtterance(metin);
      soz.lang = "tr-TR";
      window.speechSynthesis.speak(soz);
    } catch (hata) { /* seslendirme yoksa sessizce gec */ }
  }

  function sesAcikMi() {
    try { return localStorage.getItem(SES_ANAHTARI) === "1"; } catch (hata) { return false; }
  }

  function sesAyarla(acik) {
    try { localStorage.setItem(SES_ANAHTARI, acik ? "1" : "0"); } catch (hata) { /* özel pencere */ }
  }

  function sesCal() {
    if (!sesAcikMi()) return;
    var b = baglamAl();
    if (!b) return;
    if (b.state === "suspended") b.resume();
    try {
      var osilator = b.createOscillator();
      var kazanc = b.createGain();
      osilator.type = "sine";
      osilator.frequency.value = 880;
      kazanc.gain.setValueAtTime(0.001, b.currentTime);
      kazanc.gain.exponentialRampToValueAtTime(0.18, b.currentTime + 0.02);
      kazanc.gain.exponentialRampToValueAtTime(0.001, b.currentTime + 0.5);
      osilator.connect(kazanc);
      kazanc.connect(b.destination);
      osilator.start();
      osilator.stop(b.currentTime + 0.55);
    } catch (hata) { /* ses desteklenmiyorsa sessiz kal */ }
  }

  function sesDurumu() {
    var b = baglamAl();
    if (!b) return "yok";
    return b.state === "suspended" ? "beklemede" : "hazir";
  }

  document.querySelectorAll("[data-ses-anahtari]").forEach(function (kutu) {
    kutu.checked = sesAcikMi();
    kutu.addEventListener("change", function () {
      sesAyarla(kutu.checked);
      uyandir();
      if (kutu.checked) sesCal(); // açınca duyulabilir bir deneme sesi
    });
  });

  document.querySelectorAll("[data-konusma-anahtari]").forEach(function (kutu) {
    kutu.checked = konusmaAcikMi();
    kutu.addEventListener("change", function () {
      konusmaAyarla(kutu.checked);
      if (kutu.checked) seslendir("Sesli bildirim açıldı");
    });
  });

  // Sayım olayını duyur: kutu + ses + (açıksa) Türkçe seslendirme
  var KIME_METNI = {
    musteri: "bardak müşteriye gitti",
    barista: "bardak barista tarafında kaldı",
    belirsiz: "bardak sayıldı, kime gittiği belirsiz",
  };

  function olayiDuyur(olay) {
    var metin = KIME_METNI[olay.kime] || "bardak sayıldı";
    var tur = olay.kime === "musteri" ? "iyi" : "";
    goster("<b>" + olay.zaman + "</b> — " + metin, tur, 4000);
    sesCal();
    seslendir(metin);
  }

  return {
    goster: goster,
    sesCal: sesCal,
    sesDurumu: sesDurumu,
    konusmaAcikMi: konusmaAcikMi,
    olayiDuyur: olayiDuyur,
  };
})();
