"""Split every pair's move into what each of its two currencies contributed.

A pair does not move; two currencies move and the pair reports the difference.
In log space that is an identity rather than an approximation. Define

    s(X) = (1/8) * sum over all eight Z of ln( (X/Z)_close / (X/Z)_open )

with the Z = X term contributing zero. Then for any pair

    s(base) - s(quote) = ln( (base/quote)_close / (base/quote)_open )

exactly, because the Z terms cancel pairwise. So the pair's return decomposes
losslessly into a base leg and a quote leg, and "how much of USD/JPY was the
dollar" stops being a matter of opinion.

The residual is not zero in practice -- about 0.002 percentage points at worst
on this data. That is not the maths failing; it is that FF quotes all 28
crosses independently and they are not perfectly arbitrage-consistent with each
other. `decompose` reports it per pair so a reader can see it is noise.

The same identity is what makes a *reason* composable: a pair's explanation is
the two currency stories weighted by their shares, not a twenty-ninth narrative
invented for the pair itself.
"""
from __future__ import annotations

import math

from .config import CURRENCIES


def _leg_log(frames, x, y):
    """ln return of x/y over the window, from whichever way FF quotes it."""
    if x == y:
        return 0.0
    for a, b, sign in ((x, y, 1.0), (y, x, -1.0)):
        df = frames.get("%s/%s" % (a, b))
        if df is not None and len(df):
            o, c = float(df["open"].iloc[0]), float(df["close"].iloc[-1])
            if o > 0 and c > 0:
                return sign * math.log(c / o)
    return None


def strengths(frames):
    """ccy -> s(X), the log-space strength that makes the split exact.

    Missing legs are dropped from the average rather than treated as zero,
    which would quietly pull a currency towards the middle.
    """
    out = {}
    for base in CURRENCIES:
        legs = [_leg_log(frames, base, z) for z in CURRENCIES]
        legs = [v for v in legs if v is not None]
        out[base] = sum(legs) / len(legs) if legs else None
    return out


def decompose(pair, frames, s=None):
    """One pair's move split into its base and quote contributions.

    Percentages are the log figures scaled by 100, so they add exactly; over a
    single session they differ from simple returns only in the third decimal.
    """
    s = s or strengths(frames)
    base, quote = pair.split("/")
    if s.get(base) is None or s.get(quote) is None:
        return None
    actual = _leg_log(frames, base, quote)
    base_c, quote_c = 100.0 * s[base], -100.0 * s[quote]
    total = base_c + quote_c
    weight = abs(base_c) + abs(quote_c)
    return {
        "pair": pair, "base": base, "quote": quote,
        "total_pct": total,
        "base_contrib": base_c,        # what the base currency did
        "quote_contrib": quote_c,      # what the quote currency did, sign-flipped
        "base_share": abs(base_c) / weight if weight else 0.5,
        "same_way": (base_c >= 0) == (quote_c >= 0),
        "actual_pct": 100.0 * actual if actual is not None else None,
        "residual_pp": (total - 100.0 * actual) if actual is not None else None,
    }


def decompose_all(pairs, frames):
    s = strengths(frames)
    out = {}
    for p in pairs:
        d = decompose(p, frames, s)
        if d:
            out[p] = d
    return out


def strength_path(frames, start, end, step_hours=1):
    """ccy -> hourly walk of s(X) across the window, in percent.

    The close-to-close number hides the shape, and the shape is most of the
    story: a currency that led all session and handed it back at the close is
    not the same as one that closed on its high, even when both print the same
    daily change.
    """
    import datetime as dt

    grid, t = [], start
    while t <= end:
        grid.append(t)
        t += dt.timedelta(hours=step_hours)

    def at(df, ts):
        sub = df[df.index <= ts]
        return float(sub["close"].iloc[-1]) if len(sub) else None

    out = {c: [] for c in CURRENCIES}
    for ts in grid:
        snap = {}
        for base in CURRENCIES:
            legs = []
            for quote in CURRENCIES:
                if base == quote:
                    legs.append(0.0)
                    continue
                for a, b, sign in ((base, quote, 1.0), (quote, base, -1.0)):
                    df = frames.get("%s/%s" % (a, b))
                    if df is None or not len(df):
                        continue
                    o, c = float(df["open"].iloc[0]), at(df, ts)
                    if o and c and o > 0 and c > 0:
                        legs.append(sign * math.log(c / o))
                    break
            snap[base] = 100.0 * sum(legs) / len(legs) if legs else None
        for c in CURRENCIES:
            out[c].append(snap[c])
    return out, grid


# --- what each currency actually did, so a reason can be composed ---------
def currency_facts(frames, path, reactions):
    """One measured record per currency: rank, shape, rejection, its events.

    `path` is the hourly strength walk from `build`; `reactions` the scored
    releases. Nothing here is interpretation -- it is the evidence a one-line
    driver is allowed to draw on.
    """
    s = strengths(frames)
    ranked = sorted((c for c in CURRENCIES if s.get(c) is not None),
                    key=lambda c: -s[c])
    facts = {}
    for i, ccy in enumerate(ranked):
        walk = [v for v in (path.get(ccy) or []) if v is not None]
        peak = max(walk) if walk else None
        trough = min(walk) if walk else None
        close = walk[-1] if walk else None
        verdict, note = "held its range", None
        if walk and peak is not None and peak > trough:
            span = peak - trough
            gave = (peak - close) / span
            took = (close - trough) / span
            if close >= peak - 0.02:
                verdict = "closed at its best"
            elif gave > 0.6 and peak > 0.05:
                verdict, note = "attempt rejected", "led %+.2f%%, gave back %.0f%%" % (peak, 100 * gave)
            elif took > 0.6 and trough < -0.05:
                verdict, note = "selling rejected", "sold to %+.2f%%, recovered %.0f%%" % (trough, 100 * took)
        # releases in this currency, and the biggest move it took from any release
        own = [r for r in reactions if r["event"].get("ccy") == ccy]
        sensitivities = []
        for r in reactions:
            for name, pct, pips, unit, sigma in r["top_movers"]:
                if sigma is None or ccy not in name.split("/"):
                    continue
                sensitivities.append((abs(sigma), r["event"]["title"], name, sigma))
        sensitivities.sort(reverse=True)
        facts[ccy] = {
            "ccy": ccy, "rank": i + 1, "strength_pct": 100.0 * s[ccy],
            "peak": peak, "trough": trough, "close": close,
            "verdict": verdict, "shape_note": note,
            "own_releases": [{"title": r["event"]["title"],
                              "impact": r["event"]["impact"],
                              "actual": r["event"]["actual"],
                              "forecast": r["event"]["forecast"],
                              "polarity": r["polarity"]["verdict"],
                              "note": r["polarity"]["note"]} for r in own],
            "biggest_reaction": ({"event": sensitivities[0][1],
                                  "instrument": sensitivities[0][2],
                                  "sigma": round(sensitivities[0][3], 2)}
                                 if sensitivities else None),
        }
    return facts
