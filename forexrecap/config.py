"""Static configuration: editions, instrument universe, thresholds.

Every instrument name here is ForexFactory's own display name, because that is
what mds-api's `instrument` parameter expects. FF names metals and energy in
words -- "Gold/USD", not "XAU/USD" -- and rejects the ISO form.
"""
from __future__ import annotations

REPORT_TZ = "Europe/Zurich"

# Two editions a day. `lookback_h` is the window the recap covers, `forward_h`
# the calendar horizon it projects -- both in local wall-clock hours, so a DST
# switch stretches or shrinks the window rather than sliding the cutoff.
#   evening 19:00 -> the full trading day just finished (prev 19:00 -> 19:00)
#   morning 07:00 -> the overnight look-back (prev 19:00 -> 07:00, Asia session)
EDITIONS = {
    "evening": {
        "hour": 19, "lookback_h": 24, "forward_h": 24,
        "title": "Daily Recap", "window_label": "full trading day",
        "sessions": "Asia -> London -> NY morning",
    },
    "morning": {
        "hour": 7, "lookback_h": 12, "forward_h": 12,
        "title": "Overnight Recap", "window_label": "overnight",
        "sessions": "NY afternoon -> Asia",
    },
}
DEFAULT_EDITION = "evening"

# The eight majors. Column order in the market map is by measured strength;
# this list only fixes tie-breaks and iteration order.
CURRENCIES = ["USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "NZD"]

# All 28 crosses of the eight majors, in the direction FF actually quotes them.
# The market map derives the other 28 directions by inversion.
MAJOR_PAIRS = [
    "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/JPY", "USD/CHF", "USD/CAD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD", "EUR/NZD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD", "GBP/NZD",
    "AUD/JPY", "AUD/CHF", "AUD/CAD", "AUD/NZD",
    "NZD/JPY", "NZD/CHF", "NZD/CAD",
    "CAD/JPY", "CAD/CHF",
    "CHF/JPY",
]

# Instruments outside the major complex, reported in their own table.
EXTRA_INSTRUMENTS = ["USD/ZAR", "USD/MXN", "Gold/USD", "BTC/USD", "Brent/USD"]

# Quoted for context only -- they frame the session's risk tone but are not
# part of the strength ranking.
CONTEXT_INSTRUMENTS = ["DXY/USD", "SPX/USD", "VIX/USD"]

# Pairs that get the full zigzag / leg-attribution treatment.
DETAIL_PAIRS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD",
    "EUR/CHF", "CHF/JPY", "AUD/NZD", "EUR/GBP", "AUD/CHF", "NZD/CHF",
    "USD/ZAR", "USD/MXN", "Gold/USD", "BTC/USD", "Brent/USD",
]

# Risk-tone proxies quoted in the header line.
RISK_PROXIES = ["Gold/USD", "BTC/USD", "Brent/USD", "SPX/USD", "VIX/USD", "AUD/JPY"]

# --- tick sizes ----------------------------------------------------------
# Explicit so "pips" is never ambiguous on gold, oil or crypto. Anything not
# listed falls back to the FX convention (0.01 for JPY quotes, else 0.0001).
TICKS = {
    "Gold/USD":  (0.10, "pips ($0.10)"),
    "Silver/USD": (0.01, "pips ($0.01)"),
    "Brent/USD": (0.01, "pips ($0.01)"),
    "WTI/USD":   (0.01, "pips ($0.01)"),
    "BTC/USD":   (1.00, "pips ($1)"),
    "ETH/USD":   (0.10, "pips ($0.10)"),
    "DXY/USD":   (0.01, "points"),
    "SPX/USD":   (1.00, "points"),
    "VIX/USD":   (0.01, "points"),
}


def tick_for(instrument):
    """(tick size, unit label) for an instrument."""
    if instrument in TICKS:
        return TICKS[instrument]
    if instrument.endswith("/JPY"):
        return 0.01, "pips"
    return 0.0001, "pips"


IMPACT_WEIGHT = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0, "Non-Economic": 0}

# --- zigzag tuning -------------------------------------------------------
# The segmenter auto-tunes its reversal threshold until the leg count lands in
# this band, so a quiet day and a CPI day both produce a readable number of legs.
# The tuner only ever raises the threshold to cut noise. It will relax it a
# little for a one-way instrument, but not past ZZ_MIN_FRAC: a day that made
# two clean moves should be drawn as two legs, not shredded into five to hit
# a quota.
ZZ_MIN_LEGS = 2
ZZ_MAX_LEGS = 8
ZZ_START_FRAC = 0.28   # initial threshold as a fraction of the session range
ZZ_MIN_FRAC = 0.18     # never shrink below this -- past it, legs are noise
ZZ_MIN_BARS = 3        # a leg must span at least this many 15m bars (45 min)

# --- attribution ---------------------------------------------------------
ATTR_LEAD_MIN = 10     # an event may precede a leg's start by this many minutes
ATTR_LAG_MIN = 45      # ...or follow it by this many
REACTION_WINDOWS_MIN = [5, 15, 60]
