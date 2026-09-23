"""The companion map: what each pair's move was made of, and why.

The strength map answers "what moved". This answers "which of the two did it,
and on account of what". Every cell carries the same number the strength map
shows, split into a base leg and a quote leg that add to it exactly, plus a
reason composed from the two currency drivers rather than invented for the pair.
"""
from __future__ import annotations

import html

from .config import CURRENCIES

# Below this the second currency is not worth naming in a one-line reason.
MENTION_SHARE = 0.28


def _esc(s):
    return html.escape("" if s is None else str(s))


def _pct(v, dp=2):
    return "-" if v is None else ("%+." + str(dp) + "f%%") % v


def reason_for(split, drivers):
    """Compose a pair's reason out of its two currency drivers.

    Whichever side did more of the work leads. The other is named only when it
    carried a real share, so a pair driven almost entirely by the dollar reads
    as a dollar story instead of pretending both sides had something to say.
    """
    base, quote = split["base"], split["quote"]
    bd, qd = (drivers or {}).get(base), (drivers or {}).get(quote)
    lead, other = (base, quote) if split["base_share"] >= 0.5 else (quote, base)
    lead_d = bd if lead == base else qd
    other_d = qd if lead == base else bd
    lead_share = split["base_share"] if lead == base else 1 - split["base_share"]

    if not lead_d and not other_d:
        return None
    bits = ["<b>%s %.0f%%</b> %s" % (lead, 100 * lead_share, _esc(lead_d or "no stated driver"))]
    if (1 - lead_share) >= MENTION_SHARE and other_d:
        bits.append("<b>%s %.0f%%</b> %s" % (other, 100 * (1 - lead_share), _esc(other_d)))
    return " &nbsp;·&nbsp; ".join(bits)


def _split_bar(split):
    """Two-tone bar: base leg on the left, quote leg on the right.

    Each half is coloured by whether that currency pushed the pair up or down,
    so a pair whose two legs fought each other looks different at a glance from
    one where they pulled together.
    """
    b, q = split["base_contrib"], split["quote_contrib"]
    w = abs(b) + abs(q)
    if not w:
        return ""
    bw = 100.0 * abs(b) / w
    bc = "up" if b >= 0 else "down"
    qc = "up" if q >= 0 else "down"
    return ('<span class="sb" title="%s %s, %s %s">'
            '<i class="%s" style="width:%.1f%%"></i>'
            '<i class="%s" style="width:%.1f%%"></i></span>'
            % (_esc(split["base"]), _pct(b), _esc(split["quote"]), _pct(q),
               bc, bw, qc, 100 - bw))


def attribution_map_html(report, analysis):
    """Barchart layout again, but every cell shows what the move was made of."""
    split = report.get("split") or {}
    if not split:
        return ""
    strength = report["map"]["strength"]
    order = [c for c, _ in strength]

    def cell_for(base, quote):
        d = split.get("%s/%s" % (base, quote))
        flip = False
        if d is None:
            d = split.get("%s/%s" % (quote, base))
            flip = True
        if d is None:
            return '<div class="am-cell empty"></div>'
        total = -d["total_pct"] if flip else d["total_pct"]
        bc = -d["quote_contrib"] if flip else d["base_contrib"]
        qc = -d["base_contrib"] if flip else d["quote_contrib"]
        view = {"base": base, "quote": quote, "base_contrib": bc,
                "quote_contrib": qc,
                "base_share": abs(bc) / (abs(bc) + abs(qc)) if (abs(bc) + abs(qc)) else 0.5}
        cls = "up" if total >= 0 else "down"
        return ('<div class="am-cell">'
                '<span class="am-pair">%s/%s</span>'
                '<span class="am-val %s">%s</span>%s'
                '<span class="am-legs">%s %s &nbsp; %s %s</span></div>'
                % (base, quote, cls, _pct(total), _split_bar(view),
                   base, _pct(bc), quote, _pct(qc)))

    cols = []
    for base in order:
        cells = "".join(cell_for(base, q) for q in order if q != base)
        s = dict(strength).get(base)
        cols.append('<div class="am-col"><div class="am-head"><b>%s</b>'
                    '<span>%s</span></div>%s</div>' % (base, _pct(s), cells))

    return ('<div class="am-scroll"><div class="am">%s</div></div>'
            % "".join(cols))


def drivers_html(analysis, report):
    """The eight building blocks, in strength order."""
    drivers = (analysis or {}).get("currency_drivers") or {}
    facts = report.get("ccy_facts") or {}
    if not drivers:
        return ""
    rows = []
    for ccy, _ in report["map"]["strength"]:
        d = drivers.get(ccy)
        f = facts.get(ccy) or {}
        if not d:
            continue
        shape = f.get("verdict") or ""
        note = f.get("shape_note")
        tag = ""
        if shape in ("attempt rejected", "selling rejected"):
            tag = '<span class="badge pol-inverted">%s</span>' % _esc(shape)
        elif shape == "closed at its best":
            tag = '<span class="badge pol-normal">%s</span>' % _esc(shape)
        rows.append('<li><span class="dr-ccy">%s</span>'
                    '<span class="dr-str %s">%s</span>'
                    '<span class="dr-txt">%s %s%s</span></li>'
                    % (_esc(ccy),
                       "up" if f.get("strength_pct", 0) >= 0 else "down",
                       _pct(f.get("strength_pct")), _esc(d), tag,
                       ('<em class="dr-note">%s</em>' % _esc(note)) if note else ""))
    return '<ul class="drivers">%s</ul>' % "".join(rows)


def pair_reasons_html(report, analysis):
    """Per-pair reason table for the pairs the report tracks in detail."""
    split = report.get("split") or {}
    drivers = (analysis or {}).get("currency_drivers") or {}
    if not split:
        return ""
    wanted = [p for p in (d["instrument"] for d in report["detail"]) if p in split]
    rows = []
    for p in wanted:
        d = split[p]
        reason = reason_for(d, drivers) or "<span class='dim'>no stated driver</span>"
        resid = d.get("residual_pp")
        rows.append(
            '<tr><td class="nowrap"><b>%s</b></td>'
            '<td class="num %s">%s</td>'
            '<td class="num">%s</td><td class="num">%s</td>'
            '<td class="sbcell">%s</td>'
            '<td>%s</td></tr>'
            % (_esc(p), "up" if d["total_pct"] >= 0 else "down", _pct(d["total_pct"]),
               "%s %s" % (d["base"], _pct(d["base_contrib"])),
               "%s %s" % (d["quote"], _pct(d["quote_contrib"])),
               _split_bar(d), reason))
    if not rows:
        return ""
    worst = max((abs(v["residual_pp"]) for v in split.values()
                 if v.get("residual_pp") is not None), default=0.0)
    return ('<div class="tw"><table class="reasons"><thead><tr>'
            '<th>pair</th><th class="num">move</th><th class="num">base leg</th>'
            '<th class="num">quote leg</th><th>split</th><th>why</th>'
            '</tr></thead><tbody>%s</tbody></table></div>'
            '<p class="sub">The two legs add to the move by construction. Worst '
            'residual across all 28 pairs today: %.4f pp &mdash; that is FF '
            'quoting each cross independently, not the split failing.</p>'
            % ("".join(rows), worst))
