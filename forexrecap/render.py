"""Render one edition to a self-contained HTML page and a Markdown twin."""
from __future__ import annotations

import html

from .config import CURRENCIES
from .util import hhmm


# --- formatting helpers ---------------------------------------------------
def _cell_colour(pct, cap=0.8):
    """Shade a map cell by magnitude: deep green up, deep red down, grey flat."""
    if pct is None:
        return "var(--flat)", "var(--fg)"
    x = max(-1.0, min(1.0, pct / cap))
    if abs(x) < 0.04:
        return "var(--flat)", "var(--fg)"
    lightness = 44 - 24 * abs(x)
    hue = 145 if x > 0 else 2
    return "hsl(%d 58%% %d%%)" % (hue, round(lightness)), "#fff"


def _pct(v, dp=2):
    return "-" if v is None else ("%+." + str(dp) + "f%%") % v


def _pips(v, dp=1):
    return "-" if v is None else ("%+." + str(dp) + "f") % v


def _esc(s):
    return html.escape("" if s is None else str(s))


def _trim(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def _fmt_px(v):
    if v >= 1000:
        return format(v, ",.1f")
    if v >= 100:
        return "%.2f" % v
    if v >= 10:
        return "%.3f" % v
    return "%.5f" % v


# --- market map -----------------------------------------------------------
def market_map_html(report):
    """Barchart-style map: one column per currency, strongest on the left."""
    cells = report["map"]["cells"]
    strength = report["map"]["strength"]
    order = [c for c, _ in strength]
    smap = dict(strength)

    cols = []
    for base in order:
        rows = sorted(((q, cells[base].get(q)) for q in CURRENCIES if q != base),
                      key=lambda t: (t[1] is None, -(t[1] or 0.0)))
        ups = [(q, v) for q, v in rows if v is not None and v > 0]
        downs = [(q, v) for q, v in rows if v is None or v <= 0]
        cols.append((base, ups, downs))

    maxup = max((len(u) for _, u, _ in cols), default=0)

    def cell(base, quote, v):
        bg, fg = _cell_colour(v)
        return ('<div class="mm-cell" style="background:%s;color:%s">'
                '<span class="mm-pair">%s/%s</span>'
                '<span class="mm-val">%s</span></div>') % (bg, fg, base, quote, _pct(v))

    out = ['<div class="mm-scroll"><div class="mm">']
    for base, ups, downs in cols:
        out.append('<div class="mm-col">')
        out.append('<div class="mm-pad" style="height:%dpx"></div>' % ((maxup - len(ups)) * 34))
        for q, v in ups:
            out.append(cell(base, q, v))
        out.append('<div class="mm-head"><b>%s</b><span>%s</span></div>'
                   % (base, _pct(smap.get(base))))
        for q, v in downs:
            out.append(cell(base, q, v))
        out.append('</div>')
    out.append('</div></div>')
    return "\n".join(out)


# --- reaction functions ---------------------------------------------------
POLARITY_BADGE = {
    "normal": ("pol-normal", "textbook polarity"),
    "inverted": ("pol-inverted", "INVERTED"),
    "muted": ("pol-muted", "no reaction"),
    "inline": ("pol-muted", "printed in line"),
    "unscored": ("pol-muted", "no forecast"),
    "no-data": ("pol-muted", "no quotes"),
}


def reactions_html(report):
    if not report["reactions"]:
        return ('<p class="empty">No medium- or high-impact release landed in '
                'this window.</p>')
    out = []
    for r in report["reactions"]:
        ev, pol = r["event"], r["polarity"]
        cls, text = POLARITY_BADGE.get(pol["verdict"], ("pol-muted", pol["verdict"]))
        members = ""
        if len(ev.get("members", [])) > 1:
            members = ('<div class="members">released together: %s</div>'
                       % _esc(", ".join(ev["block_titles"])))
        movers = "".join(
            '<li><span class="mv-name">%s</span>'
            '<span class="mv-sig %s">%s</span>'
            '<span class="mv-pips">%s</span></li>'
            % (_esc(m[0]), "up" if (m[4] or 0) >= 0 else "down",
               ("%+.1fσ" % m[4]) if m[4] is not None else "-", _pips(m[2]))
            for m in r["top_movers"])
        out.append(
            '<div class="react">'
            '<div class="react-head"><span class="mono t">%s</span>'
            '<span class="ccy">%s</span>'
            '<span class="imp imp-%s">%s</span>'
            '<span class="rtitle">%s</span>'
            '<span class="badge %s">%s</span></div>%s'
            '<div class="react-nums">actual <b>%s</b> &middot; forecast %s '
            '&middot; previous %s%s</div>'
            '<div class="react-note">%s</div>'
            '<div class="mv-head">strongest reactions, 5 min, normalised by each '
            'instrument’s own volatility</div>'
            '<ul class="movers">%s</ul></div>'
            % (hhmm(ev["ts"]), _esc(ev["ccy"]), _esc(ev["impact"].lower()),
               _esc(ev["impact"]), _esc(_trim(ev["title"], 120)), cls, text, members,
               _esc(ev["actual"] or "-"), _esc(ev["forecast"] or "-"),
               _esc(ev["previous"] or "-"),
               (" &middot; revised %s" % _esc(ev["revision"])) if ev.get("revision") else "",
               _esc(pol["note"]), movers))
    return "\n".join(out)


def snapshot_rows(snaps):
    rows = []
    for s in snaps:
        cls = "up" if (s["chg_pct"] or 0) >= 0 else "down"
        rows.append('<tr><td class="nowrap">%s</td><td class="num mono">%s</td>'
                    '<td class="num %s">%s</td><td class="num %s">%s</td>'
                    '<td class="num dim">%s</td><td class="num dim">%.0f%%</td></tr>'
                    % (_esc(s["instrument"]), _fmt_px(s["close"]),
                       cls, _pips(s["chg_pips"]), cls, _pct(s["chg_pct"]),
                       _pips(s["range_pips"]).lstrip("+"), 100 * s["close_pos"]))
    return "".join(rows)


# --- LLM sections ---------------------------------------------------------
def analysis_html(analysis):
    if not analysis or analysis.get("error"):
        why = _esc((analysis or {}).get("error", "not requested"))
        return ('<div class="warn">Structured analysis unavailable: %s. '
                'Every measurement above is unaffected.</div>' % why)

    out = []
    out.append('<p class="lede">%s</p>' % _esc(analysis.get("session_summary")))

    themes = analysis.get("themes") or []
    if themes:
        out.append('<div class="themes">')
        for t in themes:
            ccys = "".join('<span class="chip">%s</span>' % _esc(c)
                           for c in (t.get("currencies") or []))
            out.append('<div class="theme"><div class="theme-h">%s%s</div>'
                       '<div class="theme-b">%s</div></div>'
                       % (_esc(t.get("theme")), ccys, _esc(t.get("evidence"))))
        out.append('</div>')

    pol = analysis.get("polarity_reads") or []
    if pol:
        out.append('<h3>What the reactions imply</h3><ul class="reads">')
        for p in pol:
            out.append('<li><b>%s</b> &mdash; %s</li>'
                       % (_esc(p.get("event")), _esc(p.get("read"))))
        out.append('</ul>')
    return "\n".join(out)


DIR_ARROW = {"up": "▲", "down": "▼", "range": "▬"}


def scenarios_html(analysis):
    if not analysis or analysis.get("error"):
        return ""
    scen = analysis.get("scenarios") or []
    if not scen:
        return ""
    out = ['<div class="scenarios">']
    for s in sorted(scen, key=lambda x: -(x.get("probability") or 0)):
        prob = s.get("probability")
        pct = "%.0f%%" % (100 * prob) if isinstance(prob, (int, float)) else "-"
        paths = "".join(
            '<tr><td class="nowrap">%s</td>'
            '<td class="dir %s">%s</td>'
            '<td class="num %s">%s</td><td>%s</td></tr>'
            % (_esc(p.get("instrument")),
               _esc(p.get("direction")), DIR_ARROW.get(p.get("direction"), "?"),
               _esc(p.get("direction")),
               _pips(p.get("magnitude_pips")) if isinstance(
                   p.get("magnitude_pips"), (int, float)) else "-",
               _esc(p.get("rationale")))
            for p in (s.get("pair_paths") or []))
        triggers = "".join("<li>%s</li>" % _esc(t) for t in (s.get("triggers") or []))
        out.append(
            '<div class="scen"><div class="scen-h">'
            '<span class="scen-p">%s</span><b>%s</b></div>'
            '<p>%s</p>'
            '%s'
            '<div class="scen-inval"><b>Invalidated if:</b> %s</div>'
            '<div class="tw"><table class="paths"><thead><tr><th>instrument</th>'
            '<th></th><th class="num">expected</th><th>why</th></tr></thead>'
            '<tbody>%s</tbody></table></div></div>'
            % (pct, _esc(s.get("name")), _esc(s.get("thesis")),
               ('<ul class="trig">%s</ul>' % triggers) if triggers else "",
               _esc(s.get("invalidation")), paths))
    out.append('</div>')
    return "\n".join(out)


def risks_html(analysis):
    if not analysis or analysis.get("error"):
        return ""
    risks = analysis.get("risks") or []
    if not risks:
        return ""
    items = "".join(
        '<li><b>%s</b><div>%s</div><div class="watch">watch: %s</div></li>'
        % (_esc(r.get("risk")), _esc(r.get("why_it_matters")), _esc(r.get("watch")))
        for r in risks)
    return '<ul class="risks">%s</ul>' % items


def ahead_html(report):
    rows = report["ahead_notable"]
    if not rows:
        return '<p class="empty">Nothing above low impact scheduled in the next window.</p>'
    body = "".join(
        '<tr><td class="mono nowrap">%s</td><td>%s</td>'
        '<td><span class="imp imp-%s">%s</span></td><td>%s</td>'
        '<td class="num dim">%s</td><td class="num dim">%s</td></tr>'
        % (hhmm(e["ts"]), _esc(e["ccy"]), _esc(e["impact"].lower()),
           _esc(e["impact"]), _esc(e["title"]),
           _esc(e["forecast"] or "-"), _esc(e["previous"] or "-"))
        for e in rows)
    return ('<div class="tw"><table class="ahead"><thead><tr><th>time</th>'
            '<th>ccy</th><th>impact</th><th>event</th><th class="num">forecast</th>'
            '<th class="num">previous</th></tr></thead><tbody>%s</tbody></table></div>'
            % body)


def headlines_html(report):
    hl = sorted(report["headlines"], key=lambda h: (-h["impact_value"], h["ts"]))[:14]
    if not hl:
        return ""
    return '<ul class="heads">%s</ul>' % "".join(
        '<li><span class="mono t">%s</span>'
        '<span class="imp imp-%s">%s</span>'
        '<a href="%s" rel="noreferrer">%s</a></li>'
        % (hhmm(h["ts"]), _esc(h["impact"]), _esc(h["impact"]),
           _esc(h["url"]), _esc(h["title"]))
        for h in hl)
