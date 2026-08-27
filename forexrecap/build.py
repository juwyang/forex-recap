"""Assemble one edition of the report: fetch, measure, attribute, analyse."""
from __future__ import annotations

import datetime as dt

from . import ff
from .attribution import attribute_legs
from .calendar_ff import (group_releases, in_window, load_events,
                          weeks_covering)
from .config import (CONTEXT_INSTRUMENTS, CURRENCIES, DETAIL_PAIRS,
                     EXTRA_INSTRUMENTS, MAJOR_PAIRS, REACTION_WINDOWS_MIN,
                     tick_for)
from .market import load_all, market_map
from .reaction import build_reaction_functions
from .util import (edition_spec, forward_window, hhmm, is_trading_day,
                   session_window, to_local)
from .zigzag import enrich, segment

UNIVERSE = MAJOR_PAIRS + EXTRA_INSTRUMENTS + CONTEXT_INSTRUMENTS


def build(report_date, edition="evening", ttl=900, want_llm=True):
    spec = edition_spec(edition)
    start, end = session_window(report_date, edition)
    fwd_start, fwd_end = forward_window(report_date, edition)

    # A run that fires early -- or a backfill of the current day -- covers a
    # window that has not finished yet. Say so rather than presenting a partial
    # session as a closed one.
    hours = (end - start).total_seconds() / 3600.0
    # Monday's morning edition spans the whole weekend, so the standing
    # "overnight" labels would be wrong by three days.
    bridged = hours > spec["lookback_h"] + 1
    window_label = ("since Friday's %02d:00" % spec["hour"]) if bridged else spec["window_label"]
    sessions = ("Friday close -> weekend -> Asia reopen" if bridged
                else spec["sessions"])

    now = dt.datetime.now(dt.timezone.utc)
    partial = now < end
    if partial:
        print("[build] window ends %s UTC, %d min from now -- partial session"
              % (end.strftime("%m-%d %H:%M"), (end - now).total_seconds() // 60))

    print("[build] %s %s edition | window %s -> %s UTC"
          % (report_date, edition, start.strftime("%m-%d %H:%M"), end.strftime("%m-%d %H:%M")))

    # --- prices -----------------------------------------------------------
    frames, snaps, failed = load_all(UNIVERSE, start, end, ttl=ttl)
    cells, strength, missing_cells = market_map(snaps)

    # How much of the window the FX market was actually open for. Measured on
    # the major complex alone: BTC trades all weekend, so "did any instrument
    # return bars" is not the same question and answers yes on a dead Sunday.
    expected = max((end - start).total_seconds() / 60.0 / 15.0, 1.0)
    covers = sorted(len(frames[p]) / expected for p in MAJOR_PAIRS if p in frames)
    fx_coverage = covers[len(covers) // 2] if covers else 0.0

    # --- news & calendar ---------------------------------------------------
    try:
        headlines = ff.news(start, end, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        print("[build] news unavailable: %s" % exc)
        headlines = []

    # Ask for the weeks the window actually spans. Defaulting to "this week"
    # silently gives a backfilled day an unrelated calendar, and drops the
    # look-ahead whenever a window crosses into the next week.
    all_events, cal_meta = load_events(
        ttl=ttl * 2, weeks=weeks_covering(start.date(), fwd_end.date()))
    events = in_window(all_events, start, end)
    ahead = in_window(all_events, fwd_start, fwd_end)
    ahead_notable = [e for e in ahead if e["impact"] in ("High", "Medium")]

    # --- legs & attribution ------------------------------------------------
    # Attribution reads release blocks so that CPI m/m, CPI y/y and the trimmed
    # mean printing together count once rather than three times.
    attrib_events = group_releases(events) + [e for e in events if not e.get("timed")]
    detail = []
    for name in DETAIL_PAIRS:
        df = frames.get(name)
        if df is None or len(df) < 6:
            continue
        tick, unit = tick_for(name)
        raw_legs, meta = segment(df["close"])
        legs = enrich(raw_legs, name, tick, unit)
        legs = attribute_legs(legs, name, df, attrib_events, headlines)
        detail.append({"instrument": name, "snapshot": snaps.get(name),
                       "legs": legs, "zigzag": meta})

    # --- reaction functions ------------------------------------------------
    # Measured on M5, not M15: a 5-minute reaction window on 15-minute bars
    # resolves to the same bar at both ends and always reads zero.
    fine, fine_snaps, fine_failed = load_all(UNIVERSE, start, end,
                                             interval="M5", ttl=ttl)
    if fine_failed:
        print("[build] M5 unavailable for %s; those fall back to M15"
              % ", ".join(fine_failed))
    react_frames = dict(frames)
    react_frames.update(fine)

    blocks = group_releases([e for e in events if e["impact"] in ("High", "Medium")])
    reactions = build_reaction_functions(blocks, react_frames, DETAIL_PAIRS,
                                         windows=REACTION_WINDOWS_MIN)

    report = {
        "meta": {
            "date": report_date.isoformat(),
            "edition": edition,
            "edition_title": spec["title"],
            "window_label": window_label,
            "sessions": sessions,
            "weekend_bridged": bridged,
            "hours": round(hours, 1),
            "start_utc": start, "end_utc": end,
            "start_local": to_local(start), "end_local": to_local(end),
            "fwd_start_utc": fwd_start, "fwd_end_utc": fwd_end,
            "generated_utc": now,
            "partial": partial,
            "coverage_min": int((min(now, end) - start).total_seconds() // 60),
            "instruments_loaded": len(snaps), "instruments_failed": failed,
            "fx_coverage": round(fx_coverage, 3),
            "m5_loaded": len(fine_snaps), "m5_failed": fine_failed,
            "reaction_interval": "M5",
            "missing_map_cells": missing_cells,
            "source": "ForexFactory MDS (bars, news) + FF calendar week page (actuals)",
            "calendar": cal_meta,
        },
        "snapshots": snaps,
        "map": {"cells": cells, "strength": strength, "currencies": CURRENCIES},
        "extras": [snaps[k] for k in EXTRA_INSTRUMENTS if k in snaps],
        "context": [snaps[k] for k in CONTEXT_INSTRUMENTS if k in snaps],
        "detail": detail,
        "events": events,
        "headlines": headlines,
        "reactions": reactions,
        "release_blocks": blocks,
        "ahead": ahead,
        "ahead_notable": ahead_notable,
    }
    report["_frames"] = frames
    report["facts"] = facts_for_llm(report)
    return report


def facts_for_llm(report):
    """A compact, numbers-only digest of the report for the model.

    Kept deliberately small: the model reasons better over a tight brief than
    over every bar, and everything here is already measured, so it has no
    reason to invent figures.
    """
    m = report["meta"]
    snaps = report["snapshots"]

    def snap_line(name):
        s = snaps.get(name)
        if not s:
            return None
        return {"instrument": name, "close": round(s["close"], 5),
                "chg_pips": round(s["chg_pips"], 1),
                "chg_pct": round(s["chg_pct"], 3),
                "range_pips": round(s["range_pips"], 1),
                "close_in_range": round(s["close_pos"], 2), "unit": s["unit"]}

    legs = []
    for d in report["detail"]:
        for leg in d["legs"]:
            att = leg["attribution"]
            legs.append({
                "instrument": d["instrument"],
                "from": hhmm(leg["start_ts"]), "to": hhmm(leg["end_ts"]),
                "dir": leg["dir"], "pips": round(leg["pips"], 1),
                "ret_pct": round(leg["ret_pct"], 3), "minutes": int(leg["minutes"]),
                "cause": (att["cause"] or {}).get("title") if att["cause"] else None,
                "cause_ccy": (att["cause"] or {}).get("ccy") if att["cause"] else None,
                "confidence": att["confidence"],
                "note": att["explanation"],
                # Releases that pushed the leg along without starting it. On a
                # long overnight leg this is usually where the real driver is.
                "in_leg_drivers": [
                    {"title": c["title"], "ccy": c["ccy"],
                     "pips": round(c["pips"], 1),
                     "share_of_leg": round(c["share_of_leg"], 2)}
                    for c in att.get("contributors", [])],
            })

    reacts = []
    for r in report["reactions"][:8]:
        ev, pol = r["event"], r["polarity"]
        reacts.append({
            "time": hhmm(ev["ts"]), "ccy": ev["ccy"], "impact": ev["impact"],
            "event": ev["title"], "actual": ev["actual"], "forecast": ev["forecast"],
            "previous": ev["previous"],
            "polarity": pol["verdict"], "polarity_note": pol["note"],
            "own_ccy_impulse_pct": (round(pol["impulse_pct"], 3)
                                    if pol.get("impulse_pct") is not None else None),
            "top_movers": [{"instrument": n, "pct": round(p, 3),
                            "pips": round(pp, 1), "unit": u,
                            "sigma": round(sg, 2) if sg is not None else None}
                           for n, p, pp, u, sg in r["top_movers"]],
        })

    return {
        "window": {
            "edition": m["edition"], "covers": m["window_label"],
            "sessions": m["sessions"],
            "from_local": m["start_local"].strftime("%Y-%m-%d %H:%M %Z"),
            "to_local": m["end_local"].strftime("%Y-%m-%d %H:%M %Z"),
        },
        "currency_strength_pct": [
            {"ccy": c, "mean_vs_majors_pct": round(v, 3) if v is not None else None}
            for c, v in report["map"]["strength"]],
        "majors": [x for x in (snap_line(p) for p in MAJOR_PAIRS[:7]) if x],
        "crosses": [x for x in (snap_line(p) for p in
                                ["EUR/CHF", "CHF/JPY", "AUD/NZD", "EUR/GBP",
                                 "AUD/CHF", "NZD/CHF"]) if x],
        "beyond_majors": [x for x in (snap_line(p) for p in EXTRA_INSTRUMENTS) if x],
        "risk_context": [x for x in (snap_line(p) for p in CONTEXT_INSTRUMENTS) if x],
        "legs": legs,
        "event_reactions": reacts,
        "headline_count": len(report["headlines"]),
        "top_headlines": [{"time": hhmm(h["ts"]), "impact": h["impact"],
                           "title": h["title"]}
                          for h in sorted(report["headlines"],
                                          key=lambda h: (-h["impact_value"], h["ts"]))[:12]],
        "calendar_ahead": [
            {"time": hhmm(e["ts"]), "ccy": e["ccy"], "impact": e["impact"],
             "event": e["title"], "forecast": e["forecast"], "previous": e["previous"]}
            for e in report["ahead_notable"]],
    }
