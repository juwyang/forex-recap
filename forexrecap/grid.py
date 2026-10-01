"""The session as a table: every currency against the dollar, bucket by bucket.

Two deliberate choices.

**Everything is quoted as ccy/USD, including the pairs the market quotes the
other way round.** The point of a dollar-only table is that any cross can be
read off it by subtraction -- EUR/CHF is the EUR row minus the CHF row -- and
that only works if every row faces the same way. So the JPY row is JPY/USD, not
USD/JPY, and a positive number always means the currency beat the dollar. Pips
stay in the traded pair's own tick so the magnitude is still the one a trader
recognises; only the sign is normalised.

**The buckets chain exactly.** Each bucket runs from the price at its left edge
to the price at its right edge, not from the first to the last bar inside it, so
the six returns compose to the day's return with nothing falling down the gaps
between them.

The column count is fixed at six and the bucket width follows the window: four
hours on a 24-hour evening edition, two on the 12-hour morning one, twelve on a
Monday's 72-hour bridge. The header says which.
"""
from __future__ import annotations

import datetime as dt

from .config import MAJOR_PAIRS, tick_for
from .util import hhmm, to_local

# ccy, the pair FF actually quotes, whether that quote is USD-base
USD_ROWS = [
    ("EUR", "EUR/USD", False), ("GBP", "GBP/USD", False),
    ("AUD", "AUD/USD", False), ("NZD", "NZD/USD", False),
    ("JPY", "USD/JPY", True), ("CHF", "USD/CHF", True),
    ("CAD", "USD/CAD", True), ("SEK", "USD/SEK", True),
    ("NOK", "USD/NOK", True), ("ZAR", "USD/ZAR", True),
    ("MXN", "USD/MXN", True),
]

CROSSES = [p for p in MAJOR_PAIRS if "USD" not in p.split("/")]
N_BUCKETS = 6


def buckets(start, end, n=N_BUCKETS):
    span = (end - start) / n
    return [(start + i * span, start + (i + 1) * span) for i in range(n)]


def _price_at(df, ts, window_start):
    """Price on the bucket boundary.

    At the window's own left edge there is no earlier bar, so the first bar's
    open is the reference; everywhere else it is the last close strictly
    before the boundary, which is what makes consecutive buckets chain.
    """
    if df is None or not len(df):
        return None
    if ts <= window_start:
        return float(df["open"].iloc[0])
    prior = df[df.index < ts]
    return float(prior["close"].iloc[-1]) if len(prior) else float(df["open"].iloc[0])


def usd_grid(frames, start, end, n=N_BUCKETS):
    """One row per currency: its move against the dollar in each bucket."""
    bks = buckets(start, end, n)
    rows = []
    for ccy, pair, inverted in USD_ROWS:
        df = frames.get(pair)
        if df is None or not len(df):
            continue
        tick = tick_for(pair)[0]

        def leg(a, b):
            """ccy-vs-USD return between two boundary prices.

            Inverting a quote is a reciprocal, not a negation: if USD/CAD rises
            by r, CAD/USD does not fall by r, it falls by 1-1/(1+r). Using the
            negation costs little on one bucket and visibly breaks the chain
            across six. Pips stay in the traded pair's tick, sign-flipped, so
            the magnitude is still the familiar one.
            """
            if not a or not b:
                return None
            pct = (a / b - 1.0) if inverted else (b / a - 1.0)
            pips = (a - b) / tick if inverted else (b - a) / tick
            return {"pct": 100.0 * pct, "pips": pips}

        cells = [leg(_price_at(df, b0, start), _price_at(df, b1, start))
                 for b0, b1 in bks]
        day = leg(_price_at(df, start, start), _price_at(df, end, start))
        rows.append({"ccy": ccy, "pair": pair, "inverted": inverted,
                     "cells": cells, "day": day})
    rows.sort(key=lambda r: -(r["day"]["pct"] if r["day"] else 0))
    return rows, bks


def bucket_events(report, bks):
    """Which releases and notable headlines landed in each bucket."""
    out = [[] for _ in bks]
    for blk in report.get("release_blocks") or []:
        for i, (b0, b1) in enumerate(bks):
            if b0 <= blk["ts"] < b1:
                out[i].append({"ts": blk["ts"], "ccy": blk["ccy"],
                               "impact": blk["impact"], "title": blk["title"],
                               "actual": blk.get("actual"),
                               "forecast": blk.get("forecast"), "kind": "release"})
    for h in report.get("headlines") or []:
        if str(h.get("impact", "")).lower() not in ("high", "medium"):
            continue
        for i, (b0, b1) in enumerate(bks):
            if b0 <= h["ts"] < b1:
                out[i].append({"ts": h["ts"], "ccy": None,
                               "impact": h["impact"], "title": h["title"],
                               "kind": "news"})
    for lst in out:
        lst.sort(key=lambda e: e["ts"])
    return out


def cross_table(frames, start, end):
    """Daily OHLC and open-to-close change for every non-dollar cross."""
    rows = []
    for pair in CROSSES:
        df = frames.get(pair)
        if df is None or not len(df):
            continue
        tick, unit = tick_for(pair)
        o = float(df["open"].iloc[0])
        h = float(df["high"].max())
        lo = float(df["low"].min())
        c = float(df["close"].iloc[-1])
        rows.append({"pair": pair, "open": o, "high": h, "low": lo, "close": c,
                     "chg_pct": (c / o - 1.0) * 100.0,
                     "chg_pips": (c - o) / tick,
                     "range_pips": (h - lo) / tick,
                     "close_pos": (c - lo) / (h - lo) if h > lo else 0.5,
                     "unit": unit})
    rows.sort(key=lambda r: -abs(r["chg_pct"]))
    return rows


# --- rendering ------------------------------------------------------------
import html as _html


def _esc(s):
    return _html.escape("" if s is None else str(s))


def _fmt(v, dp=2, suffix=""):
    return "-" if v is None else ("%+." + str(dp) + "f%s") % (v, suffix)


def _px(v):
    if v >= 1000:
        return format(v, ",.1f")
    if v >= 100:
        return "%.2f" % v
    if v >= 10:
        return "%.3f" % v
    return "%.5f" % v


IMP = {"High": "imp-high", "high": "imp-high",
       "Medium": "imp-medium", "medium": "imp-medium"}


def usd_grid_html(frames, report, start, end):
    rows, bks = usd_grid(frames, start, end)
    if not rows:
        return ""
    evs = bucket_events(report, bks)
    width_h = (bks[0][1] - bks[0][0]).total_seconds() / 3600.0

    head = "".join(
        '<th class="gcol"><span class="gt">%s&ndash;%s</span>%s</th>'
        % (hhmm(b0), hhmm(b1),
           "".join('<span class="gev %s" title="%s">%s %s</span>'
                   % (IMP.get(e["impact"], "imp-low"),
                      _esc("%s %s%s" % (hhmm(e["ts"]), e["title"],
                                        ("  (actual %s vs %s)" % (e["actual"], e["forecast"]))
                                        if e.get("actual") else "")),
                      _esc(e["ccy"] or "·"),
                      _esc(_short(e["title"], 22)))
                   for e in evs[i][:3]))
        for i, (b0, b1) in enumerate(bks))

    body = []
    for r in rows:
        cells = "".join(
            '<td class="num %s">%s<em>%s</em></td>'
            % ("up" if c and c["pct"] >= 0 else ("down" if c else "dim"),
               _fmt(c["pct"] if c else None, 2, "%"),
               _fmt(c["pips"] if c else None, 0))
            for c in r["cells"])
        d = r["day"]
        body.append(
            '<tr><th class="grow"><b>%s</b>/USD<span class="gq">%s</span></th>%s'
            '<td class="num day %s">%s<em>%s</em></td></tr>'
            % (_esc(r["ccy"]), _esc(r["pair"]) if r["inverted"] else "",
               cells, "up" if d and d["pct"] >= 0 else "down",
               _fmt(d["pct"] if d else None, 2, "%"),
               _fmt(d["pips"] if d else None, 0)))

    return (
        '<p class="sub">Every row faces the same way &mdash; <b>currency vs USD</b> '
        '&mdash; so any cross is the difference of two rows: EUR/CHF is the EUR row '
        'minus the CHF row. Rows marked with a quote in grey are inverted from the '
        'pair the market quotes, so a positive JPY reading is USD/JPY falling. '
        'Pips keep the traded pair&rsquo;s own tick. Buckets are %.0f hours and chain '
        'exactly into the day column.</p>'
        '<div class="tw"><table class="grid"><thead><tr><th></th>%s'
        '<th class="gcol day"><span class="gt">day</span></th></tr></thead>'
        '<tbody>%s</tbody></table></div>' % (width_h, head, "".join(body)))


def _short(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def cross_table_html(frames, start, end):
    rows = cross_table(frames, start, end)
    if not rows:
        return ""
    body = "".join(
        '<tr><td class="nowrap"><b>%s</b></td>'
        '<td class="num mono">%s</td><td class="num mono">%s</td>'
        '<td class="num mono">%s</td><td class="num mono">%s</td>'
        '<td class="num %s">%s</td><td class="num %s">%s</td>'
        '<td class="num dim">%s</td><td class="num dim">%.0f%%</td></tr>'
        % (_esc(r["pair"]), _px(r["open"]), _px(r["high"]), _px(r["low"]), _px(r["close"]),
           "up" if r["chg_pct"] >= 0 else "down", _fmt(r["chg_pct"], 2, "%"),
           "up" if r["chg_pct"] >= 0 else "down", _fmt(r["chg_pips"], 0),
           _fmt(r["range_pips"], 0).lstrip("+"), 100 * r["close_pos"])
        for r in rows)
    return ('<p class="sub">Open to close over the window, sorted by size of move. '
            'Close-in-range says where in the day&rsquo;s span it finished: near 0 is '
            'on the low, near 100 on the high.</p>'
            '<div class="tw"><table class="crosses"><thead><tr><th>cross</th>'
            '<th class="num">open</th><th class="num">high</th><th class="num">low</th>'
            '<th class="num">close</th><th class="num">chg</th><th class="num">pips</th>'
            '<th class="num">range</th><th class="num">close in range</th>'
            '</tr></thead><tbody>%s</tbody></table></div>' % body)
