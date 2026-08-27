"""Event reaction functions and polarity.

For each scheduled release we measure what actually moved, over several
horizons, and then ask whether the move was in the direction the surprise
implies. That is what fixes an event's polarity for the day: a beat that
strengthens its own currency is ordinary; a beat that weakens it is the
signal worth writing down.
"""
from __future__ import annotations

from .config import CURRENCIES, REACTION_WINDOWS_MIN, tick_for


def _close_before(df, ts):
    """Close of the last bar that opened strictly before `ts`.

    Strictly before matters: the bar stamped 01:30 covers 01:30-01:35 and so
    already contains a 01:30 release. Using it as the baseline measures the
    fade after the spike instead of the spike itself.
    """
    prior = df[df.index < ts]
    return float(prior["close"].iloc[-1]) if len(prior) else None


def move(df, t0, minutes):
    """Reaction from the last pre-event close to the close `minutes` after t0."""
    if df is None or not len(df):
        return None
    a = _close_before(df, t0)
    b = _close_before(df, t0 + _mins(minutes))
    if a is None or b is None or a == 0 or b == a:
        return None if a is None or b is None else {
            "from": a, "to": b, "delta": 0.0, "pct": 0.0}
    return {"from": a, "to": b, "delta": b - a, "pct": (b / a - 1.0) * 100.0}


def _mins(m):
    import datetime as dt
    return dt.timedelta(minutes=m)


def session_vol(df, minutes=5):
    """Standard deviation of this instrument's bar-to-bar percent returns.

    Reaction sizes are only comparable across asset classes once divided by
    this: BTC moves 0.3% on nothing, EUR/GBP moving 0.3% is an event.
    """
    if df is None or len(df) < 8:
        return None
    r = df["close"].pct_change().dropna() * 100.0
    v = float(r.std())
    return v if v and v > 0 else None


def instrument_reactions(instruments, frames, t0, windows=None):
    """instrument -> {window_minutes: {delta, pips, pct}} around t0."""
    windows = windows or REACTION_WINDOWS_MIN
    out = {}
    for name in instruments:
        df = frames.get(name)
        if df is None:
            continue
        tick, unit = tick_for(name)
        per = {}
        for w in windows:
            m = move(df, t0, w)
            if m is None:
                continue
            per[w] = {"delta": m["delta"], "pips": m["delta"] / tick,
                      "pct": m["pct"], "unit": unit}
        if per:
            per["vol"] = session_vol(df)
            out[name] = per
    return out


def currency_impulse(snaps_frames, t0, minutes):
    """ccy -> mean percent move against the other seven majors over the window.

    This is the same construction as the market map's strength column, but
    measured across a short window straddling one event instead of the session.
    """
    per_ccy = {}
    for base in CURRENCIES:
        vals = []
        for quote in CURRENCIES:
            if base == quote:
                continue
            direct, inverse = "%s/%s" % (base, quote), "%s/%s" % (quote, base)
            if direct in snaps_frames:
                m = move(snaps_frames[direct], t0, minutes)
                if m:
                    vals.append(m["pct"])
            elif inverse in snaps_frames:
                m = move(snaps_frames[inverse], t0, minutes)
                if m:
                    # exact reciprocal, matching the market map convention
                    r = m["pct"] / 100.0
                    if r > -1.0:
                        vals.append((1.0 / (1.0 + r) - 1.0) * 100.0)
        per_ccy[base] = sum(vals) / len(vals) if vals else None
    return per_ccy


# A move smaller than this is noise, not a reaction. Expressed in percent of
# the currency's basket, so it is comparable across the eight.
IMPULSE_FLOOR_PCT = 0.04


def classify_polarity(event, impulse, horizon):
    """Read the event's polarity off its own currency's impulse.

    Returns a dict with the measured impulse, the surprise that preceded it,
    and a verdict. `unscored` means the release printed no comparable forecast,
    so direction can be reported but polarity cannot be inferred.
    """
    ccy = event.get("ccy")
    imp = impulse.get(ccy) if ccy in impulse else None
    sur = event.get("surprise")
    out = {"ccy": ccy, "horizon_min": horizon, "impulse_pct": imp,
           "surprise": sur, "surprise_rel": event.get("surprise_rel")}

    if imp is None:
        out.update(verdict="no-data",
                   note="no quotes around the release")
        return out
    if abs(imp) < IMPULSE_FLOOR_PCT:
        out.update(verdict="muted",
                   note="basket moved %.3f%%, inside the noise floor" % imp)
        return out

    direction = "stronger" if imp > 0 else "weaker"
    if sur is None:
        out.update(verdict="unscored",
                   note="%s %s by %.3f%%, but no forecast to score the surprise against"
                        % (ccy, direction, abs(imp)))
        return out

    if sur == 0:
        out.update(verdict="inline",
                   note="printed in line; %s still went %s by %.3f%%" % (ccy, direction, abs(imp)))
        return out

    aligned = (sur > 0) == (imp > 0)
    out["aligned"] = aligned
    out.update(
        verdict="normal" if aligned else "inverted",
        note="%s surprise -> %s %s %.3f%%%s" % (
            "beat" if sur > 0 else "miss", ccy, direction, abs(imp),
            "" if aligned else "  (opposite to the textbook sign)"),
    )
    return out


def build_reaction_functions(events, frames, detail_instruments,
                             windows=None, horizon=15):
    """One reaction record per scored event, most violent first."""
    windows = windows or REACTION_WINDOWS_MIN
    out = []
    for ev in events:
        if not ev.get("timed"):
            continue
        impulse = currency_impulse(frames, ev["ts"], horizon)
        reactions = instrument_reactions(detail_instruments, frames, ev["ts"], windows)
        pol = classify_polarity(ev, impulse, horizon)
        # Rank by move divided by the instrument's own volatility, so a 0.3%
        # lurch in BTC does not outrank a 0.3% break in EUR/GBP.
        w0 = windows[0]
        ranked = []
        for n, r in reactions.items():
            if w0 not in r:
                continue
            vol = r.get("vol")
            sigma = (r[w0]["pct"] / vol) if vol else None
            ranked.append((n, r[w0]["pct"], r[w0]["pips"], r[w0]["unit"], sigma))
        ranked.sort(key=lambda t: -(abs(t[4]) if t[4] is not None else 0.0))
        out.append({
            "event": ev, "impulse": impulse, "reactions": reactions,
            "polarity": pol, "top_movers": ranked[:6],
            "magnitude": max((abs(v) for v in impulse.values() if v is not None),
                             default=0.0),
        })
    out.sort(key=lambda r: -r["magnitude"])
    return out
