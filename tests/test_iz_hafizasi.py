"""Takipçi hafızası testi: çift sayımın kök nedeni buradaydı.

supervision, lost_track_buffer'ı kare olarak SAYMAZ:
    max_time_lost = int(frame_rate / 30 * lost_track_buffer)
Bu yüzden 4 fps'te lost_track_buffer=60 vermek 15 saniye değil 2 saniye
hafıza demekti. Bu test, hafızanın gerçekten saniye cinsinden istediğimiz
kadar olduğunu sabitler — sessizce geri gelmesin.
"""

from __future__ import annotations

import pytest


def _analiz(ayarlar, fps: float):
    from dataclasses import replace

    from app.analiz import Analiz

    return Analiz(replace(ayarlar, kare_fps=fps))


@pytest.mark.parametrize("fps", [2, 4, 10])
def test_iz_hafizasi_saniye_cinsinden_dogru(ayarlar, fps):
    from app.analiz import _IZ_HAFIZASI_SN

    analiz = _analiz(ayarlar, fps)
    # max_time_lost KARE cinsindendir; saniyeye çevirince istediğimizi vermeli
    hafiza_sn = analiz._izleyici.max_time_lost / fps
    assert hafiza_sn == pytest.approx(_IZ_HAFIZASI_SN, rel=0.05)


def test_eski_hatali_ayar_geri_gelmemis(ayarlar):
    """Eski hâl (lost_track_buffer=60) 4 fps'te 8 kare = 2 saniye veriyordu."""
    analiz = _analiz(ayarlar, 4)
    assert analiz._izleyici.max_time_lost > 8, (
        "Takipçi hafızası yine 2 saniyeye düşmüş — bardak kapanınca yeni "
        "takip numarası alır ve ikinci kez sayılır."
    )


def test_hassasiyet_degisince_hafiza_korunur(ayarlar):
    """Hassasiyet değişince izleyici yeniden kurulur; hafıza kaybolmamalı."""
    from app.analiz import _IZ_HAFIZASI_SN

    analiz = _analiz(ayarlar, 4)
    yeni = analiz._izleyici_kur(0.55)
    assert yeni.max_time_lost / 4 == pytest.approx(_IZ_HAFIZASI_SN, rel=0.05)
