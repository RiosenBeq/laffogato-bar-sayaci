"""Zamanın tek yeri: UTC saklanır, ekranda Türkiye saati gösterilir."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ISTANBUL = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    # Windows'ta IANA veritabanı olmayabilir; Türkiye sabit UTC+3
    ISTANBUL = timezone(timedelta(hours=3), "Europe/Istanbul")


def simdi_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def bugun() -> str:
    """Türkiye takvimine göre bugün (YYYY-AA-GG).

    Gün sınırı Türkiye saatine göredir: gece 02:00'deki araç, UTC'ye göre
    'dün' sayılmasın diye.
    """
    return datetime.now(ISTANBUL).strftime("%Y-%m-%d")


def ekranda(utc_metni: str) -> str:
    an = datetime.fromisoformat(utc_metni)
    if an.tzinfo is None:
        an = an.replace(tzinfo=UTC)
    return an.astimezone(ISTANBUL).strftime("%d.%m.%Y %H:%M:%S")


def saat(utc_metni: str) -> str:
    an = datetime.fromisoformat(utc_metni)
    if an.tzinfo is None:
        an = an.replace(tzinfo=UTC)
    return an.astimezone(ISTANBUL).strftime("%H:%M")


def gun_ekranda(gun: str) -> str:
    """'2026-08-26' → '26.08.2026'"""
    return datetime.strptime(gun, "%Y-%m-%d").strftime("%d.%m.%Y")
