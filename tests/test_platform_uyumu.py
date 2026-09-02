"""Mac / Windows uyumu — platformdan bağımsız olarak sınanabilen kısımlar.

Bu testlerin tamamı her işletim sisteminde anlamlıdır: kod yolunu, dosya
içeriğini ve kodlama davranışını sınarlar. Amaç, "benim Mac'imde çalışıyordu"
diye başka bir makinede sessizce bozulan sınıfı hataları geri gelmeden
yakalamak. Kardeş proje DALSAN'daki aynı adlı dosyadan uyarlanmıştır.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

# Uygulamanın çalışabildiği en düşük Python sürümü. app/zaman.py
# "from datetime import UTC" kullanır; bu ad 3.11 ile geldi, 3.10 ve öncesinde
# uygulama daha açılırken ImportError verir.
ASGARI_SURUM = (3, 11)


# ---- başlatıcılar ----


def test_mac_baslaticisi_eski_python_kabul_etmez():
    """Mac ile gelen /usr/bin/python3 çoğu makinede 3.9'dur. Asgari sürüm
    denetimi 3.11'in altına düşerse betik uygulamayı çalışmayacağı bir
    yorumlayıcıyla başlatır ve kullanıcı sadece ImportError görür."""
    metin = (KOK / "Baslat-Mac.command").read_text(encoding="utf-8")
    surumler = set(re.findall(r"sys\.version_info >= \((\d+),\s*(\d+)\)", metin))
    assert surumler, "sürüm denetimi hiç yok"
    for buyuk, kucuk in surumler:
        assert (int(buyuk), int(kucuk)) >= ASGARI_SURUM, f"çok düşük eşik: {buyuk}.{kucuk}"


def test_mac_baslaticisi_stub_pythonu_en_sona_birakir():
    """/usr/bin/python3 her Mac'te vardır ama iki tuzağı var: sürümü eskidir ve
    Command Line Tools kurulu değilse yalnızca bir yer tutucudur (çalıştırılınca
    modal pencere açar). Gerçek kurulumlar önce denenmeli."""
    metin = (KOK / "Baslat-Mac.command").read_text(encoding="utf-8")
    homebrew = metin.index("/opt/homebrew/bin/python3.12")
    son_aday = metin.index("adaylar+=(python3 /usr/bin/python3)")
    assert homebrew < son_aday, "gerçek kurulumlar bare python3'ten ÖNCE denenmeli"
    assert "chmod +x" in metin, "ZIP'ten gelen dosyanın çalıştırma izni tazelenmeli"


def test_mac_baslaticisi_python_bulunamazsa_anlatir():
    """Kullanıcı yazılımcı değil: "bulunamadı" demek yetmez, ne yapacağı da
    yazmalı (CLAUDE.md §"her şey Türkçe ve açıklamalı")."""
    metin = (KOK / "Baslat-Mac.command").read_text(encoding="utf-8")
    assert "python.org/downloads" in metin
    assert "3.11" in metin, "istenen asgari sürüm mesajda geçmeli"
    assert "bekle_ve_cik" in metin, "hata dalında pencere kapanmamalı"


def test_mac_baslaticisi_calistirilabilir():
    """Git'te çalıştırma izni yoksa Finder dosyayı hiç açmaz."""
    cikti = subprocess.run(
        ["git", "ls-files", "-s", "Baslat-Mac.command"],
        cwd=KOK,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert cikti.startswith("100755"), f"çalıştırma izni yok: {cikti.strip()}"


def test_windows_baslaticisi_magaza_takma_adina_dusmez():
    """`where python` Windows 10/11'de Python KURULU OLMASA BİLE başarılıdır
    (Microsoft Store takma adı PATH'tedir): eski betik Mağaza'yı açıp pencereyi
    kapatıyor ve yardım mesajı hiç görünmüyordu."""
    metin = (KOK / "Baslat-Windows.bat").read_text(encoding="utf-8")
    # Açıklama satırları (REM) hariç: tuzağın kendisi anlatılıyor olabilir
    komutlar = "\n".join(
        s for s in metin.splitlines() if not s.strip().upper().startswith(("REM", "ECHO"))
    )
    assert "where python" not in komutlar, "Store takma adı tuzağına düşen kontrol"
    assert "py -3" in komutlar, "py launcher denenmeli (Add to PATH işaretlenmese de kurulur)"
    assert 'python -c "import sys"' in komutlar, "aday gerçekten Python mu, doğrulanmalı"


def test_windows_baslaticisi_eski_python_kabul_etmez():
    """Mac tarafıyla aynı eşik: iki başlatıcı ayrışırsa hata yalnızca bir
    platformda görünür ve teşhisi çok zorlaşır."""
    metin = (KOK / "Baslat-Windows.bat").read_text(encoding="utf-8")
    surumler = set(re.findall(r"sys\.version_info >= \((\d+),\s*(\d+)\)", metin))
    assert surumler, "sürüm denetimi hiç yok"
    for buyuk, kucuk in surumler:
        assert (int(buyuk), int(kucuk)) >= ASGARI_SURUM, f"çok düşük eşik: {buyuk}.{kucuk}"


def test_windows_baslaticisi_hatada_pencereyi_kapatmaz():
    """Çökme anında pencere kapanırsa kullanıcının kopyalayacak satırı kalmaz —
    destek akışının tamamı buna dayanır (CLAUDE.md §2.4)."""
    metin = (KOK / "Baslat-Windows.bat").read_text(encoding="utf-8")
    assert metin.count("pause") >= 2, "hem hata dalında hem Python yokken beklemeli"


def test_baslaticilar_ayni_asgari_surumu_ister():
    """Kod gerçekten 3.11+ istiyor mu — başlatıcıların eşiği uydurma değil,
    'from datetime import UTC' satırına dayanıyor."""
    zaman = (KOK / "app" / "zaman.py").read_text(encoding="utf-8")
    assert "from datetime import UTC" in zaman, (
        "UTC artık kullanılmıyorsa ASGARI_SURUM gerekçesi de gözden geçirilmeli"
    )


def test_bat_dosyasi_crlf_command_dosyasi_lf():
    """Satır sonları karışırsa: CRLF'li .command Mac'te "cd: $'\\r'" hatası
    verir; LF'li .bat'ta cmd.exe goto etiketlerini bozabilir."""
    assert b"\r\n" in (KOK / "Baslat-Windows.bat").read_bytes()
    assert b"\r\n" not in (KOK / "Baslat-Mac.command").read_bytes()


def test_gitattributes_satir_sonlarini_sabitler():
    """Yukarıdaki test ancak satır sonları depoda sabitlenirse kalıcıdır:
    aksi halde Windows'ta klonlayan kişide dosya CRLF'e çevrilir."""
    metin = (KOK / ".gitattributes").read_text(encoding="utf-8")
    kurallar = dict(
        (parca[0], " ".join(parca[1:]))
        for parca in (s.split() for s in metin.splitlines() if s and not s.startswith("#"))
    )
    assert kurallar["*.command"].endswith("eol=lf")
    assert kurallar["*.sh"].endswith("eol=lf")
    assert kurallar["*.bat"].endswith("eol=crlf")


# ---- metin kodlaması ----


def test_turkce_buyuk_harfler_cp1254te_cozulemez():
    """Aşağıdaki testin dayandığı olgu — kodlama davranışı gerçekten böyle.
    Windows'un varsayılan çözücüsü cp1254'tür ve UTF-8 ile yazılmış büyük
    Ş/Ğ/İ harfleri (0x9E gibi baytlar) orada TANIMSIZDIR."""
    ham = "BARDAK SAYIMI BAŞLATILIYOR".encode()
    try:
        ham.decode("cp1254")
    except UnicodeDecodeError:
        return  # beklenen
    raise AssertionError("cp1254 bu baytları çözebiliyorsa test varsayımı yanlış")


def _cagri_argumanlari(metin: str, ad: str) -> list[str]:
    """`.ad(` ile başlayan her çağrının parantezleri dengelenmiş argüman
    metnini döndürür — argümanlar birden çok satıra yayılmış olabilir."""
    parcalar = []
    for eslesme in re.finditer(rf"\.{ad}\(", metin):
        derinlik, i = 1, eslesme.end()
        while i < len(metin) and derinlik:
            derinlik += {"(": 1, ")": -1}.get(metin[i], 0)
            i += 1
        parcalar.append(metin[eslesme.end() : i - 1])
    return parcalar


def test_metin_dosyalari_acikca_utf8_okunur():
    """encoding verilmezse Windows dosyayı cp1254 sanar: .env, sema.sql ve
    eğitim JSON'ları Türkçe içerdiği için UnicodeDecodeError ile açılmaz."""
    eksik = []
    for yol in sorted((KOK / "app").rglob("*.py")):
        metin = yol.read_text(encoding="utf-8")
        for ad in ("read_text", "write_text"):
            for cagri in _cagri_argumanlari(metin, ad):
                if "encoding=" not in cagri:
                    eksik.append(f"{yol.relative_to(KOK)}: .{ad}({cagri.strip()[:50]})")
    assert not eksik, "encoding='utf-8' verilmemiş çağrılar: " + "; ".join(eksik)


# ---- dosya yolları ----


def test_kanit_fotografi_imwrite_ile_yazilmaz():
    """cv2.imwrite yolu işletim sisteminin kod sayfasıyla kodlar; Türkçe klasör
    adında HATA FIRLATMADAN başarısız olur — veritabanında var görünen, diskte
    olmayan kanıt fotoğrafları oluşurdu."""
    metin = (KOK / "app" / "analiz.py").read_text(encoding="utf-8")
    komutlar = "\n".join(s for s in metin.splitlines() if not s.strip().startswith("#"))
    # Açıklama bloklarında tuzağın adı geçebilir; asıl aranan çağrının kendisi.
    assert "cv2.imwrite(" not in komutlar, "kanıt yazımı write_bytes ile yapılmalı"
    assert "write_bytes(" in komutlar


# ---- bağımlılıklar ----


def test_windows_icin_saat_dilimi_paketi_isteniyor():
    """IANA saat dilimi veritabanı Windows ile GELMEZ; tzdata olmadan
    Europe/Istanbul bulunamaz ve gün sınırı UTC'ye kayar."""
    metin = (KOK / "requirements.txt").read_text(encoding="utf-8")
    satir = next((s for s in metin.splitlines() if s.startswith("tzdata")), None)
    assert satir is not None, "tzdata gerekli"
    assert "win32" in satir, "yalnızca Windows'ta kurulmalı"


def test_supervision_surumu_sabit():
    """supervision `lost_track_buffer`ı fps'e göre ölçekler ve bu davranış
    sürümler arasında değişti; sabitlenmezse sayım sessizce kayar
    (CLAUDE.md §3)."""
    metin = (KOK / "requirements.txt").read_text(encoding="utf-8")
    satir = next(s for s in metin.splitlines() if s.startswith("supervision"))
    assert "==" in satir, f"sürüm sabitlenmeli: {satir}"
