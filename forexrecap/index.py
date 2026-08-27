"""The landing page: a month-by-month calendar of every recap on disk.

Rebuilt from the filesystem on every run rather than appended to, so a report
that is deleted, backfilled or rebuilt is reflected without the index drifting
out of sync with what is actually published.
"""
from __future__ import annotations

import calendar
import datetime as dt
import html
import json
import os
import re

STEM_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(morning|evening)$")
EDITIONS = ["morning", "evening"]
EDITION_LABEL = {"morning": "AM", "evening": "PM"}
EDITION_TITLE = {"morning": "Overnight recap (07:00)",
                 "evening": "Daily recap (19:00)"}
MAX_MONTHS = 24


def _esc(s):
    return html.escape("" if s is None else str(s))


def scan(root):
    """date -> edition -> record, read from the report files themselves."""
    found = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".html") or name == "index.html":
                continue
            m = STEM_RE.match(name[:-5])
            if not m:
                continue
            y, mo, d, edition = m.groups()
            day = dt.date(int(y), int(mo), int(d))
            href = os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/")
            rec = {"href": href, "edition": edition}
            rec.update(_sidecar(os.path.join(dirpath, name[:-5] + ".json")))
            found.setdefault(day, {})[edition] = rec
    return found


def _sidecar(path):
    """Pull the one-line gist out of the report's JSON twin, if it is there."""
    out = {"strongest": None, "weakest": None, "partial": False,
           "summary": None, "degraded": False}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return out
    meta = data.get("meta") or {}
    facts = data.get("facts") or {}
    analysis = data.get("analysis") or {}
    strength = [s for s in (facts.get("currency_strength_pct") or [])
                if s.get("mean_vs_majors_pct") is not None]
    if strength:
        out["strongest"] = (strength[0]["ccy"], strength[0]["mean_vs_majors_pct"])
        out["weakest"] = (strength[-1]["ccy"], strength[-1]["mean_vs_majors_pct"])
    out["partial"] = bool(meta.get("partial"))
    out["degraded"] = bool((meta.get("calendar") or {}).get("degraded"))
    if isinstance(analysis, dict) and not analysis.get("error"):
        out["summary"] = analysis.get("session_summary")
    return out


def _chip(rec):
    if rec is None:
        return '<span class="chip none"></span>'
    flags = ""
    if rec["partial"]:
        flags += '<i class="flag" title="partial window">·</i>'
    if rec["degraded"]:
        flags += '<i class="flag warn" title="calendar degraded, no actuals">!</i>'
    tip = EDITION_TITLE[rec["edition"]]
    if rec["strongest"]:
        tip += "  —  %s %+.2f%%, %s %+.2f%%" % (
            rec["strongest"][0], rec["strongest"][1],
            rec["weakest"][0], rec["weakest"][1])
    return ('<a class="chip %s" href="%s" title="%s">%s%s</a>'
            % (rec["edition"], _esc(rec["href"]), _esc(tip),
               EDITION_LABEL[rec["edition"]], flags))


def _month_html(year, month, days, today):
    cal = calendar.Calendar(firstweekday=0)  # Monday
    cells = []
    for day in cal.itermonthdates(year, month):
        if day.month != month:
            cells.append('<div class="day out"></div>')
            continue
        recs = days.get(day) or {}
        classes = ["day"]
        if day.weekday() >= 5:
            classes.append("weekend")
        if day == today:
            classes.append("today")
        if not recs:
            classes.append("empty")
        chips = "".join(_chip(recs.get(e)) for e in EDITIONS)
        cells.append('<div class="%s"><span class="dnum">%d</span>'
                     '<div class="chips">%s</div></div>'
                     % (" ".join(classes), day.day, chips))

    heads = "".join('<div class="dow">%s</div>' % d
                    for d in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"])
    count = sum(len(v) for k, v in days.items()
                if k.year == year and k.month == month)
    return ('<section class="month"><h2>%s %d<span class="cnt">%d report%s</span></h2>'
            '<div class="grid">%s%s</div></section>'
            % (calendar.month_name[month], year, count,
               "" if count == 1 else "s", heads, "".join(cells)))


def _latest_html(found):
    if not found:
        return ""
    day = max(found)
    recs = found[day]
    rec = recs.get("evening") or recs.get("morning")
    gist = ""
    if rec.get("summary"):
        gist = '<p class="gist">%s</p>' % _esc(rec["summary"])
    links = " ".join(_chip(recs.get(e)) for e in EDITIONS if recs.get(e))
    return ('<a class="latest" href="%s"><div class="lat-h">'
            '<span class="lat-k">Latest</span><b>%s</b>%s</div>%s</a>'
            % (_esc(rec["href"]), day.strftime("%A %d %B %Y"), links, gist))


CSS = """
:root{--bg:#fbfbfa;--panel:#fff;--fg:#1c1c1a;--dim:#6b6b66;--line:#e3e2de;
--flat:#eceae6;--accent:#2b5cd9;--am:#c07d10;--pm:#2b5cd9;--warn:#c0392b;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#131315;--panel:#1a1a1d;--fg:#e9e8e4;--dim:#96958f;--line:#2c2c30;
--flat:#242427;--accent:#7aa2ff;--am:#e0a83c;--pm:#7aa2ff;--warn:#f0705f}}
:root[data-theme=dark]{--bg:#131315;--panel:#1a1a1d;--fg:#e9e8e4;--dim:#96958f;
--line:#2c2c30;--flat:#242427;--accent:#7aa2ff;--am:#e0a83c;--pm:#7aa2ff;--warn:#f0705f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:25px;margin:0 0 5px;letter-spacing:-.02em}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:26px}
a{color:inherit;text-decoration:none}

.latest{display:block;background:var(--panel);border:1px solid var(--line);
border-radius:12px;padding:16px 18px;margin-bottom:30px}
.latest:hover{border-color:var(--accent)}
.lat-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.lat-k{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
color:var(--dim);background:var(--flat);padding:3px 7px;border-radius:4px}
.lat-h b{font-size:15.5px}
.gist{margin:10px 0 0;font-size:13.5px;color:var(--dim);line-height:1.6}

.month{margin-bottom:32px}
h2{font-size:14px;margin:0 0 10px;font-weight:650;display:flex;
align-items:baseline;gap:9px}
.cnt{font-size:11px;color:var(--dim);font-weight:400;font-family:var(--mono)}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}
.dow{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.07em;
text-align:center;padding-bottom:3px}
.day{background:var(--panel);border:1px solid var(--line);border-radius:8px;
min-height:62px;padding:5px 6px 6px;display:flex;flex-direction:column;gap:4px}
.day.out{background:transparent;border:none;min-height:0}
.day.weekend{background:transparent}
.day.empty{opacity:.55}
.day.today{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.dnum{font-family:var(--mono);font-size:11px;color:var(--dim)}
.chips{display:flex;gap:3px;flex-wrap:wrap}
.chip{font-size:10px;font-weight:700;letter-spacing:.04em;padding:2px 5px;
border-radius:4px;font-family:var(--mono);display:inline-flex;align-items:center;gap:2px}
a.chip:hover{filter:brightness(1.18)}
.chip.morning{background:rgba(192,125,16,.16);color:var(--am)}
.chip.evening{background:rgba(43,92,217,.16);color:var(--pm)}
.chip.none{background:transparent;width:0;padding:0}
.flag{font-style:normal;font-size:9px;opacity:.75}
.flag.warn{color:var(--warn);font-weight:900}

.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--dim);font-size:12px;
border-top:1px solid var(--line);padding-top:14px;margin-top:8px}
.legend span{display:inline-flex;align-items:center;gap:5px}
@media(max-width:520px){.wrap{padding:24px 12px 60px}
.day{min-height:54px}.chip{font-size:9px;padding:2px 4px}}
"""


def render(root, today=None):
    """Write `root/index.html` and return how many reports it lists."""
    today = today or dt.date.today()
    found = scan(root)

    months = sorted({(d.year, d.month) for d in found}, reverse=True)[:MAX_MONTHS]
    body = "\n".join(_month_html(y, m, found, today) for y, m in months)
    total = sum(len(v) for v in found.values())

    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FX Recap</title><style>%s</style></head><body>
<div class="wrap">
<h1>FX Recap</h1>
<div class="sub">Twice daily from ForexFactory data &mdash; 07:00 overnight
look-back, 19:00 full trading day, Europe/Zurich. %d reports.</div>
%s
%s
<div class="legend">
<span><b class="chip morning">AM</b> overnight, 19:00&rarr;07:00</span>
<span><b class="chip evening">PM</b> full day, 19:00&rarr;19:00</span>
<span><i class="flag">·</i> partial window</span>
<span><i class="flag warn">!</i> calendar degraded</span>
</div>
</div></body></html>""" % (CSS, total, _latest_html(found), body)

    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    return total
