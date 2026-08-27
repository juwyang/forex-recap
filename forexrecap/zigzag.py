"""Segment an intraday series into alternating up/down legs.

A fixed threshold is useless across a mixed instrument set: what draws four
clean legs on EUR/USD draws forty on BTC/USD. So the threshold is a fraction of
the session's own range, auto-tuned until the leg count lands in a target band.
The result is the "big lines" view -- swings a human would point at -- not
every wiggle.
"""
from __future__ import annotations

from .config import (ZZ_MAX_LEGS, ZZ_MIN_BARS, ZZ_MIN_FRAC, ZZ_MIN_LEGS,
                     ZZ_START_FRAC)


def _raw_pivots(values, threshold):
    """Alternating-extreme zigzag driven purely by `threshold` (price units).

    Tracks the running high and low simultaneously so the opening direction is
    decided by whichever side breaks the threshold first, rather than being
    assumed.
    """
    n = len(values)
    if n < 2:
        return [0, n - 1] if n == 2 else []

    pivots = [0]
    direction = 0  # +1 rising, -1 falling, 0 not yet established
    hi_i = lo_i = 0
    hi_v = lo_v = values[0]

    for i in range(1, n):
        v = values[i]
        if v > hi_v:
            hi_i, hi_v = i, v
        if v < lo_v:
            lo_i, lo_v = i, v

        # A retrace of `threshold` off the running high ends an up-leg.
        if direction >= 0 and (hi_v - v) >= threshold and hi_i > pivots[-1]:
            pivots.append(hi_i)
            direction = -1
            lo_i, lo_v = _extreme(values, hi_i, i, lowest=True)
            hi_i, hi_v = i, v
            continue

        if direction <= 0 and (v - lo_v) >= threshold and lo_i > pivots[-1]:
            pivots.append(lo_i)
            direction = 1
            hi_i, hi_v = _extreme(values, lo_i, i, lowest=False)
            lo_i, lo_v = i, v
            continue

    if pivots[-1] != n - 1:
        pivots.append(n - 1)
    return pivots


def _extreme(values, a, b, lowest):
    """Index/value of the min (or max) of values[a:b+1]."""
    seg = values[a:b + 1]
    v = min(seg) if lowest else max(seg)
    return a + seg.index(v), v


def _alternate(pivots, values):
    """Drop pivots that leave two consecutive legs pointing the same way."""
    changed = True
    while changed and len(pivots) > 2:
        changed = False
        for k in range(1, len(pivots) - 1):
            a, b, c = pivots[k - 1], pivots[k], pivots[k + 1]
            up1 = values[b] >= values[a]
            up2 = values[c] >= values[b]
            if up1 == up2:
                pivots.pop(k)
                changed = True
                break
    return pivots


def _enforce_min_bars(pivots, values, min_bars):
    """Merge away legs shorter than `min_bars`, smallest amplitude first."""
    while len(pivots) > 2:
        short = [(k, pivots[k + 1] - pivots[k],
                  abs(values[pivots[k + 1]] - values[pivots[k]]))
                 for k in range(len(pivots) - 1)
                 if pivots[k + 1] - pivots[k] < min_bars]
        if not short:
            break
        k = min(short, key=lambda t: t[2])[0]
        # Drop the interior endpoint of the offending leg; if it is the tail
        # leg, drop its start instead so the series still ends on the last bar.
        pivots.pop(k + 1 if k + 1 < len(pivots) - 1 else k)
        _alternate(pivots, values)
    return pivots


def _enforce_min_amplitude(pivots, values, threshold, floor=0.5):
    """Drop interior legs too shallow to be worth drawing.

    Alternation repair can leave a leg smaller than the reversal threshold that
    produced it -- a 3-pip wobble inside a 39-pip range. The closing leg is
    exempt: it runs to the last bar and is genuinely unconfirmed, not noise.
    """
    limit = threshold * floor
    while len(pivots) > 3:
        interior = [(k, abs(values[pivots[k + 1]] - values[pivots[k]]))
                    for k in range(len(pivots) - 2)]
        small = [(k, amp) for k, amp in interior if amp < limit]
        if not small:
            break
        k = min(small, key=lambda t: t[1])[0]
        pivots.pop(k + 1 if k + 1 < len(pivots) - 1 else k)
        _alternate(pivots, values)
    return pivots


def segment(series, min_legs=ZZ_MIN_LEGS, max_legs=ZZ_MAX_LEGS,
            start_frac=ZZ_START_FRAC, min_bars=ZZ_MIN_BARS):
    """pandas Series (UTC index) -> (legs, meta) with the threshold auto-tuned."""
    values = [float(v) for v in series.values]
    times = list(series.index)
    empty = {"threshold": None, "threshold_frac": None, "range": None, "tuned": False}
    if len(values) < 4:
        return [], empty

    rng = max(values) - min(values)
    if rng <= 0:
        return [], dict(empty, range=0.0)

    frac, best, best_miss = start_frac, None, None
    for _ in range(30):
        pv = _alternate(_raw_pivots(values, rng * frac), values)
        pv = _enforce_min_bars(pv, values, min_bars)
        pv = _enforce_min_amplitude(pv, values, rng * frac)
        count = len(pv) - 1
        miss = 0 if min_legs <= count <= max_legs else min(
            abs(count - min_legs), abs(count - max_legs))
        if best_miss is None or miss < best_miss:
            best, best_miss = (list(pv), frac), miss
        if miss == 0:
            break
        if count > max_legs:
            frac *= 1.25
        else:
            frac *= 0.8
            if frac < ZZ_MIN_FRAC:
                break
        if frac > 0.9:
            break

    pv, frac = best
    legs = []
    for a, b in zip(pv[:-1], pv[1:]):
        legs.append({
            "start_ts": times[a], "end_ts": times[b],
            "start_px": values[a], "end_px": values[b],
            "start_i": a, "end_i": b,
            "bars": b - a,
            "dir": "up" if values[b] >= values[a] else "down",
        })
    return legs, {"threshold": rng * frac, "threshold_frac": frac,
                  "range": rng, "tuned": best_miss == 0}


def enrich(legs, pair, tick, unit):
    """Attach amplitude in ticks/pips, percent return, and duration."""
    out = []
    for leg in legs:
        delta = leg["end_px"] - leg["start_px"]
        mins = (leg["end_ts"] - leg["start_ts"]).total_seconds() / 60.0
        item = dict(leg)
        item.update({
            "pair": pair,
            "delta": delta,
            "pips": delta / tick if tick else None,
            "abs_pips": abs(delta) / tick if tick else None,
            "ret_pct": (leg["end_px"] / leg["start_px"] - 1.0) * 100.0 if leg["start_px"] else None,
            "minutes": mins,
            "unit": unit,
            "speed_pips_per_h": (abs(delta) / tick) / (mins / 60.0) if tick and mins else None,
        })
        out.append(item)
    return out
