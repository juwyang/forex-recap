"""A shared-axis timeline: events on top, one narrow price lane per instrument.

The point of the layout is visual comparison, so every row must share one
mapping from time to x. That mapping is a function of the *timestamp*, never of
the bar index: instruments do not all print the same number of bars in a
window, and an index-based x would slide the lanes against each other by
however many bars they differ. Event guidelines are drawn through every lane at
the same x, so a release lines up with what it did to each pair.

A market closure inside the window (the weekend inside a Monday edition) shows
as a flat stretch rather than being squeezed out, which keeps the axis honest.
"""
from __future__ import annotations

import datetime as dt
import html

from .util import to_local

W = 1000          # viewBox width shared by the event band and every lane
GUTTER = 92       # left column: instrument name and session change
RPAD = 14
PLOT_L = GUTTER
PLOT_R = W - RPAD

LANE_H = 46       # plot height of one instrument lane
LANE_PAD = 7      # vertical breathing room inside a lane

LABEL_ROW_H = 13
CHAR_W = 5.35     # rough advance width of the 9px label font
LABEL_PAD = 14    # gap kept between two labels sharing a row


def _esc(s):
    return html.escape("" if s is None else str(s))


def x_for(ts, start, end):
    span = (end - start).total_seconds() or 1.0
    f = (ts - start).total_seconds() / span
    return PLOT_L + (PLOT_R - PLOT_L) * max(0.0, min(1.0, f))


# --- time axis ------------------------------------------------------------
def _tick_step_hours(hours):
    for limit, step in ((6, 1), (14, 2), (30, 3), (54, 6), (100, 12)):
        if hours <= limit:
            return step
    return 24


def axis_ticks(start, end):
    """Local wall-clock gridlines across the window."""
    hours = (end - start).total_seconds() / 3600.0
    step = _tick_step_hours(hours)
    local = to_local(start)
    # advance to the next clean multiple of `step` hours
    first = local.replace(minute=0, second=0, microsecond=0)
    while first.hour % step or first < local:
        first += dt.timedelta(hours=1)
    ticks, t = [], first
    while t <= to_local(end):
        ticks.append(t)
        t += dt.timedelta(hours=step)
    return ticks, step


def axis_svg(start, end, height=20):
    ticks, step = axis_ticks(start, end)
    p = ['<svg class="tl-axis" viewBox="0 0 %d %d" aria-hidden="true">'
         % (W, height)]
    for t in ticks:
        x = x_for(t.astimezone(dt.timezone.utc), start, end)
        label = t.strftime("%H:%M")
        if step >= 6 or t.hour == 0:
            label = t.strftime("%a %H:%M")
        p.append('<line class="ax-t" x1="%.1f" y1="0" x2="%.1f" y2="4"/>' % (x, x))
        p.append('<text class="ax-l" x="%.1f" y="14">%s</text>' % (x, _esc(label)))
    p.append('</svg>')
    return "\n".join(p), [x_for(t.astimezone(dt.timezone.utc), start, end) for t in ticks]


# --- event band -----------------------------------------------------------
IMPACT_RANK = {"High": 3, "high": 3, "Medium": 2, "medium": 2, "Low": 1, "low": 1}


def collect_markers(report, max_labelled=16):
    """Timed calendar releases and headlines, ranked so the band stays legible.

    Everything in the window gets a tick; only the most important get a text
    label, because a label per low-impact headline is unreadable and hides the
    releases that actually moved something.
    """
    out = []
    for blk in report.get("release_blocks") or []:
        out.append({
            "ts": blk["ts"], "kind": "release",
            "impact": blk["impact"],
            "rank": IMPACT_RANK.get(blk["impact"], 1) + 1,   # releases outrank news
            "label": "%s %s" % (blk["ccy"], _short(blk["title"], 34)),
            "title": blk["title"], "ccy": blk["ccy"],
        })
    for h in report.get("headlines") or []:
        out.append({
            "ts": h["ts"], "kind": "news",
            "impact": h["impact"],
            "rank": IMPACT_RANK.get(h["impact"], 1),
            "label": _short(h["title"], 40),
            "title": h["title"], "ccy": None,
        })
    out.sort(key=lambda m: m["ts"])

    for m in sorted(out, key=lambda m: (-m["rank"], m["ts"]))[:max_labelled]:
        m["labelled"] = True
    return out


def _short(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def _lay_out_labels(markers, start, end):
    """Greedy row assignment so label boxes never overlap horizontally."""
    rows = []          # each row is a list of (x_left, x_right)
    placed = []
    for m in markers:
        if not m.get("labelled"):
            continue
        x = x_for(m["ts"], start, end)
        # The rendered text is "HH:MM <label>", so the time prefix counts too;
        # estimating from the label alone under-measures by about six glyphs
        # and lets two labels collide on the same row.
        w = (len(m["label"]) + 6) * CHAR_W + LABEL_PAD
        left, right = x, x + w
        if right > W:                       # would run off the edge; anchor right
            left, right = x - w, x
            anchor = "end"
        else:
            anchor = "start"
        for r, spans in enumerate(rows):
            if all(right < a or left > b for a, b in spans):
                spans.append((left, right))
                placed.append((m, x, r, anchor))
                break
        else:
            rows.append([(left, right)])
            placed.append((m, x, len(rows) - 1, anchor))
    return placed, max(len(rows), 1)


def events_svg(report, start, end):
    """The event band. Returns (svg, [x of every marker]) for the lane guides."""
    markers = collect_markers(report)
    if not markers:
        return "", []
    placed, nrows = _lay_out_labels(markers, start, end)
    h = nrows * LABEL_ROW_H + 16

    p = ['<svg class="tl-events" viewBox="0 0 %d %d" '
         'role="img" aria-label="events in the window">' % (W, h)]
    for m, x, row, anchor in placed:
        y = h - 14 - row * LABEL_ROW_H
        p.append('<line class="ev-stem %s" x1="%.1f" y1="%.1f" x2="%.1f" y2="%d"/>'
                 % (m["kind"], x, y + 3, x, h - 4))
        p.append('<text class="ev-lab %s %s" x="%.1f" y="%.1f" text-anchor="%s">'
                 '%s %s</text>'
                 % (m["kind"], _impact_cls(m), x + (3 if anchor == "start" else -3),
                    y, anchor, _esc(to_local(m["ts"]).strftime("%H:%M")),
                    _esc(m["label"])))
    for m in markers:
        x = x_for(m["ts"], start, end)
        p.append('<circle class="ev-dot %s %s" cx="%.1f" cy="%d" r="%s"/>'
                 % (m["kind"], _impact_cls(m), x, h - 4,
                    "3.1" if m["kind"] == "release" else "2.2"))
    p.append('</svg>')
    xs = [x_for(m["ts"], start, end) for m in markers if m["rank"] >= 3]
    return "\n".join(p), xs


def _impact_cls(m):
    return "imp-" + str(m.get("impact", "low")).lower()


# --- price lanes ----------------------------------------------------------
def lane_svg(instrument, df, legs, start, end, guides, snap):
    """One instrument's path and zigzag on the shared axis."""
    if df is None or not len(df):
        return ""
    h = LANE_H
    ys = [float(v) for v in df["close"].values]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1e-9

    def Y(v):
        return LANE_PAD + (h - 2 * LANE_PAD) * (1.0 - (v - lo) / span)

    xs = [x_for(ts, start, end) for ts in df.index]

    p = ['<svg class="tl-lane" viewBox="0 0 %d %d" role="img" '
         'aria-label="%s path">' % (W, h, _esc(instrument))]
    for gx in guides:
        p.append('<line class="ln-guide" x1="%.1f" y1="0" x2="%.1f" y2="%d"/>'
                 % (gx, gx, h))
    p.append('<line class="ln-base" x1="%d" y1="%d" x2="%d" y2="%d"/>'
             % (PLOT_L, h, PLOT_R, h))

    p.append('<polyline class="ln-price" points="%s"/>'
             % " ".join("%.1f,%.1f" % (x, Y(v)) for x, v in zip(xs, ys)))

    at = {ts: i for i, ts in enumerate(df.index)}
    for leg in legs:
        a, b = at.get(leg["start_ts"]), at.get(leg["end_ts"])
        if a is None or b is None:
            continue
        cls = leg["dir"]
        p.append('<line class="ln-leg %s" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                 % (cls, xs[a], Y(ys[a]), xs[b], Y(ys[b])))
        mx = (xs[a] + xs[b]) / 2.0
        my = (Y(ys[a]) + Y(ys[b])) / 2.0
        p.append('<text class="ln-lab %s" x="%.1f" y="%.1f">%s</text>'
                 % (cls, mx, my - 4 if cls == "up" else my + 10,
                    _esc("%+.0f" % leg["pips"])))

    # left gutter: name and the session change
    chg_cls = "up" if (snap and snap["chg_pct"] >= 0) else "down"
    p.append('<text class="ln-name" x="4" y="%d">%s</text>' % (h / 2 - 1, _esc(instrument)))
    if snap:
        p.append('<text class="ln-chg %s" x="4" y="%d">%+.0f  %+.2f%%</text>'
                 % (chg_cls, h / 2 + 11, snap["chg_pips"], snap["chg_pct"]))
    p.append('</svg>')
    return "\n".join(p)


def timeline_html(report, frames):
    """The whole panel: event band, shared axis, and one lane per instrument."""
    start, end = report["meta"]["start_utc"], report["meta"]["end_utc"]
    ev, guides = events_svg(report, start, end)
    axis, _ = axis_svg(start, end)

    lanes = []
    for entry in report["detail"]:
        name = entry["instrument"]
        lane = lane_svg(name, frames.get(name), entry["legs"], start, end,
                        guides, entry.get("snapshot"))
        if lane:
            lanes.append('<div class="lane">%s</div>' % lane)
    if not lanes:
        return '<p class="empty">No price data in this window.</p>'

    # The panel has a floor width -- eighteen lanes and an event band stop being
    # readable below it -- so it scrolls inside its own box rather than forcing
    # the whole page to scroll sideways on a phone.
    return ('<div class="tl-scroll"><div class="tl">%s%s'
            '<div class="lanes">%s</div>%s</div></div>'
            % (ev, axis, "\n".join(lanes), axis))
