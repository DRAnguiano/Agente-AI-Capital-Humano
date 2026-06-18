"""live-reply B7.2 — helper is_business_hours (8:00–17:30 L–V, America/Mexico_City).

Deterministas, sin Groq/DB. Cubren límites de hora, fin de semana, interpretación de
naive como hora de México y conversión de tz-aware (UTC).
"""
from __future__ import annotations

import datetime

import pytest

from app.knowledge.business_hours import _TZ, is_business_hours


@pytest.fixture
def monday() -> datetime.date:
    d = datetime.date(2026, 6, 1)
    while d.weekday() != 0:  # 0 = lunes
        d += datetime.timedelta(days=1)
    return d


def _at(date: datetime.date, hh: int, mm: int) -> datetime.datetime:
    return datetime.datetime(date.year, date.month, date.day, hh, mm, tzinfo=_TZ)


def test_weekday_in_hours(monday):
    assert is_business_hours(_at(monday, 10, 0)) is True


def test_weekday_boundaries(monday):
    assert is_business_hours(_at(monday, 8, 0)) is True     # apertura inclusive
    assert is_business_hours(_at(monday, 17, 30)) is True   # cierre inclusive
    assert is_business_hours(_at(monday, 7, 59)) is False
    assert is_business_hours(_at(monday, 17, 31)) is False


def test_weekend_is_closed(monday):
    saturday = monday + datetime.timedelta(days=5)
    sunday = monday + datetime.timedelta(days=6)
    assert is_business_hours(_at(saturday, 10, 0)) is False
    assert is_business_hours(_at(sunday, 10, 0)) is False


def test_naive_interpreted_as_mexico(monday):
    naive = datetime.datetime(monday.year, monday.month, monday.day, 10, 0)
    assert is_business_hours(naive) is True


def test_tzaware_utc_is_converted(monday):
    # México es UTC-6 (sin horario de verano desde 2022).
    # 22:00 UTC = 16:00 México (mismo lunes) → en horario.
    utc_in = datetime.datetime(monday.year, monday.month, monday.day, 22, 0, tzinfo=datetime.timezone.utc)
    assert is_business_hours(utc_in) is True
    # 02:00 UTC del lunes = 20:00 México del domingo → fuera (noche + fin de semana).
    utc_out = datetime.datetime(monday.year, monday.month, monday.day, 2, 0, tzinfo=datetime.timezone.utc)
    assert is_business_hours(utc_out) is False
