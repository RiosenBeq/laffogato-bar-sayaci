@echo off
REM Laffogato - Windows baslatici. Bu dosyaya cift tiklayin.
cd /d "%~dp0"

REM DIKKAT: "where python" Windows 10/11'de Python KURULU OLMASA BILE basarili
REM olur. Microsoft Store takma adi (sifir baytlik python.exe) PATH'tedir;
REM calistirilinca Magaza penceresi acilir, bizim pencere kapanir ve kullanici
REM hicbir yardim mesaji goremez. Bu yuzden once py.exe launcher denenir
REM ("Add Python to PATH" isaretlenmese de kurulur), sonra aday GERCEKTEN
REM calisan bir Python mu diye sinanir.
REM Asgari surum 3.11'dir: app/zaman.py "from datetime import UTC" kullanir ve
REM bu ad 3.11 ile geldi; 3.10 ve oncesinde uygulama acilirken ImportError verir.

set "PY="

py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto :duz_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

:duz_python
if defined PY goto :python_secildi
python -c "import sys" >nul 2>nul
if errorlevel 1 goto :python_yok
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"

:python_yok
if defined PY goto :python_secildi
echo.
echo   Calisan bir Python 3.11 veya ustu bulunamadi.
echo   https://www.python.org/downloads/ adresinden Python 3.12 kurun ve
echo   kurulum sirasinda "Add Python to PATH" kutusunu MUTLAKA isaretleyin.
echo.
pause
exit /b 1

:python_secildi

REM Kurulum ancak SONUNA KADAR bittiyse tamam sayilir. Isaret dosyasi yoksa
REM pip eksikleri tamamlar (kurulu paketleri atladigi icin cogu zaman hizlidir).
if exist ".venv\kurulum-tamamlandi-v2" goto :calistir

if not exist ".venv\Scripts\python.exe" (
  if exist ".venv" rmdir /s /q .venv
  echo.
  echo Ilk kurulum basliyor. Internet hizina gore 2-10 dakika surer.
  echo Asagida indirme ilerlemesi gorunecek - pencereyi KAPATMAYIN.
  echo.
  %PY% -m venv .venv
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
