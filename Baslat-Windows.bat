@echo off
REM Laffogato - Windows baslatici. Bu dosyaya cift tiklayin.
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python bulunamadi. https://www.python.org/downloads/ adresinden
  echo   Python 3.12 kurun ve "Add Python to PATH" kutusunu isaretleyin.
  echo.
  pause
  exit /b 1
)

REM Kurulum ancak SONUNA KADAR bittiyse tamam sayilir. Isaret dosyasi yoksa
REM pip eksikleri tamamlar (kurulu paketleri atladigi icin cogu zaman hizlidir).
if exist ".venv\kurulum-tamamlandi-v2" goto :calistir

if not exist ".venv\Scripts\python.exe" (
  if exist ".venv" rmdir /s /q .venv
  echo.
  echo Ilk kurulum basliyor. Internet hizina gore 2-10 dakika surer.
  echo Asagida indirme ilerlemesi gorunecek - pencereyi KAPATMAYIN.
  echo.
  python -m venv .venv
  if errorlevel 1 (
    echo Python ortami olusturulamadi.
    pause
    exit /b 1
  )
) else (
  echo Kurulum denetleniyor, eksik paketler tamamlaniyor...
)

.venv\Scripts\python -m pip install --upgrade pip
if errorlevel 1 (
  echo pip guncellenemedi. Internet baglantinizi kontrol edin.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Paket kurulumu tamamlanamadi. Internet baglantinizi kontrol edip tekrar deneyin.
  pause
  exit /b 1
)
type nul > ".venv\kurulum-tamamlandi-v2"
echo.
echo Kurulum tamam.

:calistir
if not exist ".env" copy .env.example .env >nul

echo.
echo Laffogato baslatiliyor - uygulama kendi penceresinde acilacak.
echo Kapatmak icin uygulama penceresini kapatmaniz yeterli.
.venv\Scripts\python masaustu.py
if errorlevel 1 (
  echo.
  echo Uygulama beklenmedik sekilde durdu.
  echo Yukaridaki son satirlari kopyalayip yapay zekaya yapistirirsaniz sorunu bulur.
  pause
)
