"""Attach a cause to each zigzag leg -- or refuse to.

The honest default is "no clear catalyst". Plenty of intraday legs are flow,
positioning or liquidity, and labelling them with whatever release happened to
be nearby is how a recap becomes fiction. So a candidate has to clear three
tests: it must be relevant to the instrument, it must land near the leg's
start, and the price must actually have jumped on it in the right direction.
That last test -- the impulse check -- is what separates "happened during"
from "caused".
"""
from __future__ import annotations

import datetime as dt

from .config import ATTR_LAG_MIN, ATTR_LEAD_MIN, CURRENCIES, tick_for
from .reaction import move

# Score needed before a leg gets a named cause at all.
MIN_SCORE = 3.0
# The impulse must be at least this fraction of the leg to count as driving it.
IMPULSE_SHARE = 0.20

IMPACT_SCORE = {"High": 3.0, "Medium": 1.6, "Low": 0.5,
                "high": 3.0, "medium": 1.6, "low": 0.5}


def _currencies_of(instrument):
    """The major currencies an instrument is exposed to.

    Gold, Brent and BTC are quoted in USD, so they carry USD exposure and are
    additionally sensitive to global risk events.
    """
    parts = instrument.split("/")
    return [p for p in parts if p in CURRENCIES]


def _relevance(instrument, ev_ccy):
    ccys = _currencies_of(instrument)
    if ev_ccy in ccys:
        return 2.0
    if ev_ccy in ("All", "ALL", None, ""):
        return 1.0
    # A foreign release still matters through the dollar leg and risk channel.
    return 0.6 if "USD" in ccys else 0.3


def _timing(ev_ts, leg_start, leg_end):
    """1.0 right at the leg's start, decaying across the leg, 0 outside."""
    lead = (leg_start - ev_ts).total_seconds() / 60.0
    if lead > ATTR_LEAD_MIN:
        return 0.0                      # event is before the window opens
    lag = (ev_ts - leg_start).total_seconds() / 60.0
    if ev_ts > leg_end:
        return 0.0
    if lag <= 0:
        return 1.0                      # fires inside the lead tolerance
    if lag <= ATTR_LAG_MIN:
        return 1.0 - 0.5 * (lag / ATTR_LAG_MIN)
    # Later in the leg it can still matter, but only as a continuation driver.
    span = max((leg_end - leg_start).total_seconds() / 60.0, 1.0)
    return max(0.0, 0.4 * (1.0 - lag / span))


def _impulse_check(df, instrument, ev_ts, leg, minutes=15):
    """How much of the leg happened in the 15 minutes after the event."""
    m = move(df, ev_ts, minutes)
    if m is None:
        return None
    tick = tick_for(instrument)[0]
    leg_delta = leg["end_px"] - leg["start_px"]
    same_way = (m["delta"] >= 0) == (leg_delta >= 0)
    share = abs(m["delta"]) / abs(leg_delta) if leg_delta else 0.0
    return {"delta": m["delta"], "pips": m["delta"] / tick, "pct": m["pct"],
            "same_direction": same_way, "share_of_leg": share, "minutes": minutes}


def candidates_for_leg(leg, instrument, df, events, news):
    """Every plausible driver of one leg, scored and sorted."""
    out = []
    for ev in events:
        if not ev.get("timed"):
            continue
        t = _timing(ev["ts"], leg["start_ts"], leg["end_ts"])
        if t <= 0:
            continue
        base = IMPACT_SCORE.get(ev.get("impact"), 0.5)
        rel = _relevance(instrument, ev.get("ccy"))
        imp = _impulse_check(df, instrument, ev["ts"], leg)
        score = base * rel * t
        if imp:
            if imp["same_direction"]:
                score *= 1.0 + min(imp["share_of_leg"], 1.5)
            else:
                score *= 0.25          # moved the other way -- almost certainly not the cause
        out.append({"kind": "calendar", "ts": ev["ts"], "ccy": ev.get("ccy"),
                    "impact": ev.get("impact"), "title": ev.get("title"),
                    "actual": ev.get("actual"), "forecast": ev.get("forecast"),
                    "previous": ev.get("previous"), "surprise": ev.get("surprise"),
                    "impulse": imp, "score": score, "timing": t})

    for n in news:
        t = _timing(n["ts"], leg["start_ts"], leg["end_ts"])
        if t <= 0:
            continue
        base = IMPACT_SCORE.get(n.get("impact"), 0.5)
        imp = _impulse_check(df, instrument, n["ts"], leg)
        # Headlines carry no currency tag, so relevance is capped lower than a
        # matched calendar release and leans on the impulse to earn its place.
        score = base * 0.9 * t
        if imp:
            if imp["same_direction"]:
                score *= 1.0 + min(imp["share_of_leg"], 1.5)
            else:
                score *= 0.25
        out.append({"kind": "news", "ts": n["ts"], "ccy": None,
                    "impact": n.get("impact"), "title": n.get("title"),
                    "url": n.get("url"), "impulse": imp, "score": score, "timing": t})

    out.sort(key=lambda c: -c["score"])
    return out


def attribute(leg, instrument, df, events, news):
    """Decide this leg's cause, or record that there isn't an obvious one."""
    cands = candidates_for_leg(leg, instrument, df, events, news)
    top = cands[0] if cands else None

    contributors = _contributors(cands, top)

    if top is None or top["score"] < MIN_SCORE:
        return {
            "cause": None,
            "confidence": "none",
            "explanation": _no_catalyst_reason(cands, contributors),
            "candidates": cands[:4],
            "contributors": contributors,
        }

    imp = top.get("impulse") or {}
    share = imp.get("share_of_leg") or 0.0
    if imp.get("same_direction") and share >= IMPULSE_SHARE and top["score"] >= 6:
        conf = "high"
    elif imp.get("same_direction") and share >= IMPULSE_SHARE * 0.5:
        conf = "medium"
    else:
        conf = "low"

    return {"cause": top, "confidence": conf, "explanation": _explain(top, leg),
            "candidates": cands[:4], "contributors": contributors}


# A long leg often has no single origin but is pushed along mid-way by a
# release. Those are reported separately so the leg is not mislabelled as
# having been caused by something that landed hours after it began.
CONTRIB_SHARE = 0.15


def _contributors(cands, top):
    out = []
    for c in cands:
        if c is top:
            continue
        imp = c.get("impulse") or {}
        if (c.get("impact") in ("High", "high", "Medium", "medium")
                and imp.get("same_direction")
                and (imp.get("share_of_leg") or 0) >= CONTRIB_SHARE):
            out.append({"ts": c["ts"], "title": c["title"], "ccy": c.get("ccy"),
                        "impact": c.get("impact"),
                        "pips": imp["pips"], "share_of_leg": imp["share_of_leg"],
                        "minutes": imp["minutes"]})
    return out[:3]


def _no_catalyst_reason(cands, contributors=None):
    if contributors:
        c = contributors[0]
        return ("No single trigger started this leg, but %s pushed it along "
                "(%+.1f in %d min, %.0f%% of the move)."
                % (_short(c["title"], 60), c["pips"], c["minutes"],
                   100.0 * c["share_of_leg"]))
    if not cands:
        return "Nothing on the wire; flow or a technical level, not news."
    best = cands[0]
    imp = best.get("impulse") or {}
    if imp and not imp.get("same_direction"):
        return ("Nearest item %s moved price the other way."
                % _short(best["title"], 58))
    return "Nearest item %s, too weak to own the move." % _short(best["title"], 58)


def _explain(c, leg):
    imp = c.get("impulse") or {}
    bits = []
    if c["kind"] == "calendar":
        head = "%s %s" % (c.get("ccy") or "", c.get("title") or "")
        if c.get("actual") not in (None, "", "-"):
            head += " (actual %s vs forecast %s)" % (c.get("actual"), c.get("forecast") or "n/a")
        bits.append(head.strip())
    else:
        bits.append(_short(c.get("title")))
    if imp.get("pips") is not None:
        bits.append("%+.1f in the first %d min, %.0f%% of the leg"
                    % (imp["pips"], imp["minutes"], 100.0 * (imp.get("share_of_leg") or 0)))
    return " -- ".join(bits)


def _short(title, n=80):
    t = (title or "").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def attribute_legs(legs, instrument, df, events, news):
    return [dict(leg, attribution=attribute(leg, instrument, df, events, news))
            for leg in legs]
