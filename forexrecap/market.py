"""Session snapshots and the currency market map.

The map mirrors barchart's layout: one column per currency ordered strongest to
weakest, each column listing that currency against the other seven. The 28
crosses FF quotes are used as-is; the other 28 directions are their exact
inverses, so USD/AUD reads -0.13% when AUD/USD reads +0.12% -- not -0.12%.
"""
from __future__ import annotations

from .config import CURRENCIES, MAJOR_PAIRS, tick_for
from .ff import bars


def load_window(instrument, start, end, interval="M15", ttl=900):
    """Bars strictly inside [start, end).

    The bar stamped `end` opens at the cutoff and belongs to the next session,
    so it is dropped; the bar stamped `start` opens at the previous cutoff and
    is the session's first.
    """
    df = bars(instrument, start, end, interval=interval, ttl=ttl)
    return df[(df.index >= start) & (df.index < end)]


def snapshot(instrument, df):
    """Open/close/high/low and the session change for one instrument."""
    if df is None or not len(df):
        return None
    tick, unit = tick_for(instrument)
    o = float(df["open"].iloc[0])
    c = float(df["close"].iloc[-1])
    hi, lo = float(df["high"].max()), float(df["low"].min())
    return {
        "instrument": instrument,
        "open": o, "close": c, "high": hi, "low": lo,
        "tick": tick, "unit": unit,
        "chg": c - o,
        "chg_pips": (c - o) / tick,
        "chg_pct": (c / o - 1.0) * 100.0 if o else None,
        "range_pips": (hi - lo) / tick,
        "range_pct": (hi / lo - 1.0) * 100.0 if lo else None,
        "bars": len(df),
        "first_ts": df.index[0], "last_ts": df.index[-1],
        # Where in the day's range the session closed: 1.0 = on the high.
        "close_pos": (c - lo) / (hi - lo) if hi > lo else 0.5,
    }


def load_all(instruments, start, end, interval="M15", ttl=900):
    """instrument -> (DataFrame, snapshot). Failures are reported, not raised."""
    frames, snaps, failed = {}, {}, []
    for name in instruments:
        try:
            df = load_window(name, start, end, interval=interval, ttl=ttl)
        except Exception as exc:  # noqa: BLE001 - one dead instrument must not kill the run
            print("[market] %s unavailable: %s" % (name, exc))
            failed.append(name)
            continue
        snap = snapshot(name, df)
        if snap is None:
            print("[market] %s returned no bars in window" % name)
            failed.append(name)
            continue
        frames[name], snaps[name] = df, snap
    return frames, snaps, failed


def _invert_pct(pct):
    """Return of the reciprocal quote: 1/(1+r) - 1, not simply -r."""
    if pct is None:
        return None
    r = pct / 100.0
    if r <= -1.0:
        return None
    return (1.0 / (1.0 + r) - 1.0) * 100.0


def market_map(snaps):
    """Full 8x8 map plus the strength ranking that orders its columns.

    Returns (cells, strength, missing) where
      cells[base][quote] = percent change of base/quote over the session,
      strength = [(ccy, mean percent vs the other seven)] strongest first.
    """
    cells = {b: {} for b in CURRENCIES}
    missing = []
    for base in CURRENCIES:
        for quote in CURRENCIES:
            if base == quote:
                continue
            direct = "%s/%s" % (base, quote)
            inverse = "%s/%s" % (quote, base)
            if direct in snaps:
                cells[base][quote] = snaps[direct]["chg_pct"]
            elif inverse in snaps:
                cells[base][quote] = _invert_pct(snaps[inverse]["chg_pct"])
            else:
                cells[base][quote] = None
                missing.append(direct)

    strength = []
    for ccy in CURRENCIES:
        vals = [v for v in cells[ccy].values() if v is not None]
        strength.append((ccy, sum(vals) / len(vals) if vals else None))
    strength.sort(key=lambda t: (t[1] is None, -(t[1] or 0.0)))
    return cells, strength, missing


def quoted_pairs_present(snaps):
    return [p for p in MAJOR_PAIRS if p in snaps]
