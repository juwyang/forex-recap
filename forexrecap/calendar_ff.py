"""ForexFactory economic calendar, with actuals.

FF publishes two calendars and only one of them is useful here:

  * nfs.faireconomy.media/ff_calendar_thisweek.json -- keyless, but it is a
    forward-looking schedule only. It carries forecast and previous and has no
    `actual` field at all, so it cannot score a surprise.
  * www.forexfactory.com/calendar?week=... -- the real thing, with actual,
    revision, event ids and links, embedded in the page as
    `calendarComponentStates[N] = {days: [...]}`.

The page is behind Cloudflare and 403s a normal client, but the block is on
the TLS fingerprint, not on cookies: curl_cffi impersonating Safari walks
straight through with no cf_clearance and no session. Chrome fingerprints are
currently rejected, so the impersonation list is ordered accordingly and falls
back to the JSON feed if every profile fails.
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import re

from .config import IMPACT_WEIGHT
from .net import fetch_json
from .util import UTC, parse_number, surprise

WEEK_URL = "https://www.forexfactory.com/calendar?week=%s"
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Ordered by what actually passes Cloudflare today; see module docstring.
IMPERSONATE = ["safari17_0", "safari15_5", "chrome131", "chrome124"]

_STATES_RE = re.compile(r"calendarComponentStates\[\d+\]\s*=\s*\{")


def week_token(day):
    """FF's week URL token for the Monday of `day`'s week, e.g. 'aug24.2026'."""
    monday = day - dt.timedelta(days=day.weekday())
    return monday.strftime("%b%d.%Y").lower().lstrip("0")


def _extract_days(html):
    """Pull the `days:` array out of the inline JS state blob."""
    m = _STATES_RE.search(html)
    if not m:
        raise RuntimeError("calendarComponentStates not found -- page layout changed")
    i = html.find("days:", m.end() - 1)
    if i < 0:
        raise RuntimeError("days array not found in calendar state")
    j = html.find("[", i)
    depth, end = 0, None
    for k in range(j, len(html)):
        c = html[k]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = k + 1
                break
    if end is None:
        raise RuntimeError("days array not closed")
    return json.loads(html[j:end])


def _fetch_week_html(token, timeout=40):
    from curl_cffi import requests as cr
    last = None
    for profile in IMPERSONATE:
        try:
            r = cr.get(WEEK_URL % token, impersonate=profile, timeout=timeout)
            if r.status_code == 200 and "calendarComponentStates" in r.text:
                return r.text, profile
            last = "HTTP %s via %s" % (r.status_code, profile)
        except Exception as exc:  # noqa: BLE001
            last = "%s via %s" % (str(exc)[:80], profile)
    raise RuntimeError("all impersonation profiles rejected (%s)" % last)


def _from_page_event(e):
    ts = dt.datetime.fromtimestamp(int(e["dateline"]), UTC) if e.get("dateline") else None
    actual, forecast = e.get("actual") or None, e.get("forecast") or None
    raw_sur, rel_sur = surprise(actual, forecast)
    impact = (e.get("impactName") or "Low").title()
    return {
        "id": e.get("id"),
        "ts": ts,
        "ccy": e.get("currency") or e.get("country") or "",
        "impact": impact,
        "weight": IMPACT_WEIGHT.get(impact, 1),
        "title": htmllib.unescape(e.get("name") or "").strip(),
        "actual": actual,
        "forecast": forecast,
        "previous": e.get("previous") or None,
        "revision": e.get("revision") or None,
        "actual_num": parse_number(actual),
        "forecast_num": parse_number(forecast),
        "previous_num": parse_number(e.get("previous")),
        "surprise": raw_sur,
        "surprise_rel": rel_sur,
        # timeMasked marks all-day rows (holidays, "tentative") with no clock time.
        "timed": bool(ts) and not e.get("timeMasked"),
        "url": "https://www.forexfactory.com" + (e.get("url") or ""),
        "source": "page",
    }


def weeks_covering(start, end):
    """Week tokens spanning [start, end] inclusive, de-duplicated in order.

    A report window routinely straddles a week boundary -- a Friday evening
    edition projects into Monday -- and backfilling any past day needs that
    day's week, not the week the script happens to run in.
    """
    tokens, day = [], start
    while day <= end:
        t = week_token(day)
        if t not in tokens:
            tokens.append(t)
        day += dt.timedelta(days=7)
    last = week_token(end)
    if last not in tokens:
        tokens.append(last)
    return tokens


def load_events(days=None, ttl=1800, weeks=None):
    """Calendar rows covering `weeks` (defaults to the current week).

    Falls back to the keyless JSON feed if the page cannot be reached, in which
    case `actual` is absent for every row and polarity cannot be scored -- the
    caller is told via the returned `degraded` flag.
    """
    today = dt.date.today()
    tokens = weeks or [week_token(today)]
    events, degraded, profile_used = [], False, None

    for token in tokens:
        try:
            html, profile = _fetch_week_html(token)
            profile_used = profile
            for day in _extract_days(html):
                for e in day.get("events", []):
                    ev = _from_page_event(e)
                    if ev["ts"]:
                        events.append(ev)
        except Exception as exc:  # noqa: BLE001
            print("[calendar] week %s page unavailable: %s" % (token, exc))
            degraded = True

    if not events:
        print("[calendar] falling back to the schedule-only JSON feed (no actuals)")
        events = _load_feed(ttl=ttl)
        degraded = True

    seen, out = set(), []
    for e in sorted(events, key=lambda x: x["ts"]):
        key = (e["ts"].isoformat(), e["ccy"], e["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out, {"degraded": degraded, "profile": profile_used,
                 "with_actual": sum(1 for e in out if e["actual_num"] is not None)}


def _load_feed(ttl=1800):
    try:
        rows = fetch_json(FEED_URL, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        print("[calendar] JSON feed unavailable too: %s" % exc)
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        ts = _parse_iso(r.get("date"))
        if not ts:
            continue
        impact = r.get("impact") or "Low"
        out.append({
            "id": None, "ts": ts, "ccy": r.get("country") or "",
            "impact": impact, "weight": IMPACT_WEIGHT.get(impact, 1),
            "title": (r.get("title") or "").strip(),
            "actual": None, "forecast": r.get("forecast") or None,
            "previous": r.get("previous") or None, "revision": None,
            "actual_num": None, "forecast_num": parse_number(r.get("forecast")),
            "previous_num": parse_number(r.get("previous")),
            "surprise": None, "surprise_rel": None,
            "timed": True, "url": None, "source": "feed",
        })
    return out


def _parse_iso(raw):
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    try:
        return dt.datetime.fromisoformat(s).astimezone(UTC)
    except ValueError:
        return None


def in_window(events, start, end, ccys=None, min_impact=None):
    order = {"Low": 1, "Medium": 2, "High": 3}
    floor = order.get(min_impact, 0)
    return [e for e in events
            if start <= e["ts"] < end
            and (not ccys or e["ccy"] in ccys)
            and order.get(e["impact"], 0) >= floor]


def has_result(e):
    return e["actual_num"] is not None


def group_releases(events):
    """Collapse releases that print at the same instant for the same currency.

    A statistics agency drops CPI m/m, CPI y/y and the trimmed mean on one
    timestamp; the market trades them as a single event. Scoring each
    separately would triple-count the same price reaction and produce three
    identical reaction functions. The block's headline is whichever member
    carries the largest relative surprise, since that is what actually moved it.
    """
    blocks = {}
    for e in events:
        if not e.get("timed"):
            continue
        blocks.setdefault((e["ts"], e["ccy"]), []).append(e)

    out = []
    for (ts, ccy), members in sorted(blocks.items()):
        # Headline the block with a high-impact member if there is one -- the
        # market names the block after CPI, not after the construction survey
        # that happened to print a bigger relative surprise beside it.
        tier = [m for m in members if m["impact"] == "High"] or members
        scored = [m for m in tier if m.get("surprise_rel") is not None]
        head = (max(scored, key=lambda m: abs(m["surprise_rel"])) if scored
                else max(tier, key=lambda m: m.get("weight", 0)))
        impact = "High" if any(m["impact"] == "High" for m in members) else head["impact"]
        block = dict(head)
        block.update({
            "impact": impact,
            "members": members,
            "title": head["title"] if len(members) == 1 else
                     "%s +%d more" % (head["title"], len(members) - 1),
            "block_titles": [m["title"] for m in members],
        })
        out.append(block)
    return out
