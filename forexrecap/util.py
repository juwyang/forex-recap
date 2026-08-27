"""Timezone, session windows, pip maths, and messy-number parsing."""
from __future__ import annotations

import datetime as dt
import re

from .config import DEFAULT_EDITION, EDITIONS, REPORT_TZ, tick_for

try:  # py3.9+
    from zoneinfo import ZoneInfo

    def _tz(name):
        return ZoneInfo(name)

    def _localize(naive, name):
        return naive.replace(tzinfo=ZoneInfo(name))
except ImportError:  # py3.8 / anaconda
    import pytz

    def _tz(name):
        return pytz.timezone(name)

    def _localize(naive, name):
        return pytz.timezone(name).localize(naive)


UTC = dt.timezone.utc


def report_tz():
    return _tz(REPORT_TZ)


def to_local(ts):
    """UTC-aware datetime -> report-timezone aware datetime."""
    return ts.astimezone(report_tz())


def edition_spec(edition=None):
    return EDITIONS[edition or DEFAULT_EDITION]


def cutoff(report_date, edition=None, offset_days=0):
    """The edition's cutoff instant (UTC) on report_date + offset_days."""
    spec = edition_spec(edition)
    naive = dt.datetime.combine(report_date + dt.timedelta(days=offset_days),
                                dt.time(spec["hour"], 0))
    return _localize(naive, REPORT_TZ).astimezone(UTC)


def session_window(report_date, edition=None):
    """(start, end) UTC for the window this edition recaps.

    Both ends are localised from naive wall-clock times, so a DST switch inside
    the window produces a 23h or 25h span -- which is what actually happened --
    instead of silently sliding the cutoff off 19:00 local.
    """
    spec = edition_spec(edition)
    end_naive = dt.datetime.combine(report_date, dt.time(spec["hour"], 0))
    start_naive = end_naive - dt.timedelta(hours=spec["lookback_h"])
    return (_localize(start_naive, REPORT_TZ).astimezone(UTC),
            _localize(end_naive, REPORT_TZ).astimezone(UTC))


def forward_window(report_date, edition=None):
    """(start, end) UTC for the calendar horizon this edition projects."""
    spec = edition_spec(edition)
    start_naive = dt.datetime.combine(report_date, dt.time(spec["hour"], 0))
    end_naive = start_naive + dt.timedelta(hours=spec["forward_h"])
    return (_localize(start_naive, REPORT_TZ).astimezone(UTC),
            _localize(end_naive, REPORT_TZ).astimezone(UTC))


def pip_size(instrument):
    """Tick size for an instrument -- see config.TICKS for the explicit cases."""
    return tick_for(instrument)[0]


def to_pips(instrument, price_delta):
    return price_delta / pip_size(instrument)


def pct(a, b):
    """Return in percent going from a to b."""
    if a in (None, 0):
        return None
    return (b / a - 1.0) * 100.0


_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_number(raw):
    """Parse ForexFactory's actual/forecast strings.

    Handles '3.1%', '-0.2%', '250K', '1.2M', '<0.1%', '2.75|3.00' (range),
    '$1.4B', '1,234'. Returns float or None. A range takes its midpoint.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in ("-", "--", "n/a", "N/A"):
        return None
    if "|" in s:  # FF uses a pipe for ranges
        parts = [parse_number(p) for p in s.split("|")]
        parts = [p for p in parts if p is not None]
        return sum(parts) / len(parts) if parts else None
    m = _NUM_RE.search(s)
    if not m:
        return None
    val = float(m.group(0).replace(",", ""))
    tail = s[m.end():].upper()
    for suf, mult in _SUFFIX.items():
        if tail.startswith(suf):
            val *= mult
            break
    return val


def surprise(actual, forecast):
    """Signed surprise and a scale-free version (as a fraction of |forecast|)."""
    a, f = parse_number(actual), parse_number(forecast)
    if a is None or f is None:
        return None, None
    raw = a - f
    rel = raw / abs(f) if f else None
    return raw, rel


def fmt_ts(ts, tz=True):
    local = to_local(ts)
    return local.strftime("%H:%M") if not tz else local.strftime("%Y-%m-%d %H:%M %Z")


def hhmm(ts):
    return to_local(ts).strftime("%H:%M")
