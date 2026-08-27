"""Masaüstü penceresi: Laffogato'yu kendi penceresinde açar.

Çift tıklanan Baslat betiği bu dosyayı çalıştırır. Sunucu arka planda
başlar, uygulama tarayıcı yerine yerli bir pencerede görünür ve pencere
kapatılınca sunucu da durur. pywebview yoksa ya da pencere açılamazsa
tarayıcıya düşülür — uygulama her koşulda kullanılabilir kalır.
"""

from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

BASLIK = "Laffogato Bar Sayacı"
PORT = 8100
ADRES = f"http://127.0.0.1:{PORT}"


def port_dinleniyor() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def sunucuyu_baslat():
    import uvicorn

    ayar = uvicorn.Config("app.main:app", host="127.0.0.1", port=PORT, log_level="info")
    sunucu = uvicorn.Server(ayar)
    threading.Thread(target=sunucu.run, daemon=True).start()
    return sunucu


def tarayicida_tut() -> int:
    """Pencere açılamadığında yedek yol: tarayıcı + açık tutulan sunucu."""
    print(f"Uygulama tarayıcıda açılıyor: {ADRES}")
    print("Kapatmak için bu pencerede Ctrl+C yapın.")
    webbrowser.open(ADRES)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    os.chdir(Path(__file__).resolve().parent)

    sunucu = None
    if not port_dinleniyor():
        sunucu = sunucuyu_baslat()
        for _ in range(100):  # en fazla 20 saniye bekle
            if port_dinleniyor():
                break
            time.sleep(0.2)
        else:
            print("Sunucu açılamadı; yukarıdaki hata satırlarına bakın.")
            return 1

    try:
        import webview
    except Exception as hata:  # pywebview kurulamamış olabilir — tarayıcı yeterli
        print(f"Pencere kütüphanesi yüklenemedi ({hata}).")
        return tarayicida_tut()

    try:
        webview.create_window(BASLIK, ADRES, width=1280, height=860, min_size=(900, 600))
        webview.start()  # pencere kapanana kadar bloklar
    except Exception as hata:  # örn. Windows'ta WebView2 çalışma zamanı yoksa
        print(f"Pencere açılamadı ({hata}).")
        return tarayicida_tut()

    if sunucu is not None:
        sunucu.should_exit = True
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
