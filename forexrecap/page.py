"""Compose the full HTML page and the Markdown twin."""
from __future__ import annotations

from .config import EXTRA_INSTRUMENTS
from .render import (_esc, _fmt_px, _pct, _pips, ahead_html, analysis_html,
                     headlines_html, legs_table, market_map_html, reactions_html,
                     risks_html, scenarios_html, snapshot_rows, zigzag_svg)
from .util import hhmm

CSS = """
:root{
  --bg:#fbfbfa; --panel:#fff; --fg:#1c1c1a; --dim:#6b6b66; --line:#e3e2de;
  --flat:#eceae6; --up:#12783f; --down:#c0392b; --accent:#2b5cd9;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  --bg:#131315; --panel:#1a1a1d; --fg:#e9e8e4; --dim:#96958f; --line:#2c2c30;
  --flat:#262629; --up:#3ec27a; --down:#f0705f; --accent:#7aa2ff;
}}
:root[data-theme=dark]{
  --bg:#131315; --panel:#1a1a1d; --fg:#e9e8e4; --dim:#96958f; --line:#2c2c30;
  --flat:#262629; --up:#3ec27a; --down:#f0705f; --accent:#7aa2ff;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:44px 0 12px;letter-spacing:-.01em;
  padding-bottom:7px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:22px 0 8px;color:var(--dim);
  text-transform:uppercase;letter-spacing:.07em}
p{margin:0 0 10px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:2px}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.dim{color:var(--dim)}
.nowrap{white-space:nowrap}
.up{color:var(--up)} .down{color:var(--down)}
td.dir{text-align:center;font-size:11px;width:20px}
.lede{font-size:16.5px;line-height:1.6;margin-bottom:18px}
.empty,.warn{color:var(--dim);font-size:13.5px;background:var(--flat);
  padding:10px 13px;border-radius:7px;border:1px solid var(--line)}

/* header strip */
.strip{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 6px}
.kv{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:8px 12px;min-width:96px}
.kv .k{font-size:10.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.07em}
.kv .v{font-family:var(--mono);font-size:15px;font-weight:600;margin-top:2px}

/* market map */
.mm-scroll{overflow-x:auto;padding-bottom:6px}
.mm{display:flex;gap:5px;min-width:760px}
.mm-col{flex:1 1 0;display:flex;flex-direction:column;gap:2px;min-width:96px}
.mm-cell{height:32px;border-radius:4px;padding:0 8px;display:flex;
  align-items:center;justify-content:space-between;font-size:11.5px}
.mm-pair{font-weight:600;letter-spacing:-.01em}
.mm-val{font-family:var(--mono);font-variant-numeric:tabular-nums}
.mm-head{height:38px;border-radius:4px;background:var(--panel);
  border:1px solid var(--line);display:flex;align-items:center;
  justify-content:space-between;padding:0 8px;margin:3px 0}
.mm-head b{font-size:14px;letter-spacing:.02em}
.mm-head span{font-family:var(--mono);font-size:11px;color:var(--dim)}

/* tables */
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-weight:600;font-size:10.5px;color:var(--dim);
  text-transform:uppercase;letter-spacing:.07em;padding:0 9px 7px;
  border-bottom:1px solid var(--line)}
th.num{text-align:right}
td{padding:8px 9px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:none}

/* instrument blocks */
.inst{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:16px 18px;margin-bottom:14px}
.inst-h{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.inst-h b{font-size:16px}
.inst-h .px{font-family:var(--mono);color:var(--dim);font-size:13px}
.inst-h .chg{font-family:var(--mono);font-size:14px;font-weight:600}
.zz{width:100%;height:170px;display:block;margin:2px 0 6px}
.zz-price{fill:none;stroke:var(--dim);stroke-width:1;opacity:.42}
.zz-leg{stroke-width:2.1;stroke-linecap:round}
.zz-leg.up{stroke:var(--up)} .zz-leg.down{stroke:var(--down)}
.zz-lab{font:600 10.5px var(--mono);text-anchor:middle}
.zz-lab.up{fill:var(--up)} .zz-lab.down{fill:var(--down)}
.zz-dot{stroke:var(--panel);stroke-width:1.4}
.zz-dot.conf-high{fill:var(--accent)} .zz-dot.conf-med{fill:#d68a1a}
.zz-dot.conf-low{fill:var(--dim)} .zz-dot.conf-none{fill:var(--flat)}
.contrib{color:var(--dim);font-size:12px;margin-top:3px;padding-left:11px;
  border-left:2px solid var(--line)}
.contrib em{font-style:normal;font-family:var(--mono)}

/* badges */
.badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;padding:2px 6px;border-radius:4px;margin-right:6px;
  vertical-align:1px}
.conf-high{background:rgba(43,92,217,.16);color:var(--accent)}
.conf-med{background:rgba(214,138,26,.18);color:#c07d10}
.conf-low{background:var(--flat);color:var(--dim)}
.conf-none{background:transparent;color:var(--dim);border:1px solid var(--line)}
.pol-normal{background:rgba(18,120,63,.15);color:var(--up)}
.pol-inverted{background:rgba(192,57,43,.16);color:var(--down)}
.pol-muted{background:var(--flat);color:var(--dim)}
.imp{display:inline-block;font-size:9.5px;font-weight:700;padding:2px 5px;
  border-radius:3px;text-transform:uppercase;letter-spacing:.04em}
.imp-high{background:rgba(192,57,43,.16);color:var(--down)}
.imp-medium{background:rgba(214,138,26,.18);color:#c07d10}
.imp-low{background:var(--flat);color:var(--dim)}
.chip{display:inline-block;background:var(--flat);color:var(--dim);font-size:10px;
  font-weight:700;padding:1px 5px;border-radius:3px;margin-left:5px}

/* reactions */
.react{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px;margin-bottom:11px}
.react-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.react-head .t{color:var(--dim);font-size:13px}
.react-head .ccy{font-weight:700;font-size:13px}
.react-head .rtitle{flex:1 1 240px;font-weight:600}
.members{color:var(--dim);font-size:12px;margin-top:4px}
.react-nums{font-family:var(--mono);font-size:12.5px;color:var(--dim);margin-top:7px}
.react-note{font-size:13.5px;margin-top:5px}
.mv-head{font-size:10.5px;color:var(--dim);text-transform:uppercase;
  letter-spacing:.06em;margin:11px 0 5px}
.movers{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.movers li{display:flex;gap:7px;align-items:baseline;background:var(--flat);
  border-radius:6px;padding:4px 9px;font-size:12.5px}
.mv-name{font-weight:600}
.mv-sig{font-family:var(--mono);font-weight:700}
.mv-pips{font-family:var(--mono);color:var(--dim);font-size:11.5px}

/* analysis */
.themes{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:11px}
.theme{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:12px 14px}
.theme-h{font-weight:650;margin-bottom:5px}
.theme-b{font-size:13.5px;color:var(--dim)}
.reads{margin:0;padding-left:19px} .reads li{margin-bottom:7px;font-size:13.5px}
.scenarios{display:flex;flex-direction:column;gap:13px}
.scen{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:15px 17px}
.scen-h{display:flex;align-items:baseline;gap:10px;margin-bottom:7px}
.scen-p{font-family:var(--mono);font-size:19px;font-weight:700;color:var(--accent)}
.scen-h b{font-size:15.5px}
.trig{margin:6px 0;padding-left:19px;font-size:13px;color:var(--dim)}
.scen-inval{font-size:13px;color:var(--dim);margin:8px 0 4px}
.paths{margin-top:9px}
.risks{list-style:none;margin:0;padding:0;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:11px}
.risks li{background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--down);border-radius:9px;padding:12px 14px;font-size:13.5px}
.risks li div{color:var(--dim);margin-top:4px}
.watch{font-size:12.5px;font-family:var(--mono)}
.heads{list-style:none;margin:0;padding:0}
.heads li{display:flex;gap:9px;align-items:baseline;padding:6px 0;
  border-bottom:1px solid var(--line);font-size:13.5px}
.heads .t{color:var(--dim);font-size:12.5px}
footer{margin-top:52px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--dim);font-size:12.5px}
@media(max-width:640px){.wrap{padding:20px 13px 60px}h1{font-size:21px}}
"""


def _kv(k, v, cls=""):
    return ('<div class="kv"><div class="k">%s</div>'
            '<div class="v %s">%s</div></div>' % (_esc(k), cls, _esc(v)))


def build_html(report, analysis, frames):
    m = report["meta"]
    strength = report["map"]["strength"]
    strongest, weakest = strength[0], strength[-1]

    title = "FX %s &mdash; %s" % (_esc(m["edition_title"]), _esc(m["date"]))
    window = "%s &rarr; %s" % (m["start_local"].strftime("%a %d %b %H:%M"),
                               m["end_local"].strftime("%a %d %b %H:%M %Z"))

    strip = "".join([
        _kv("window", "%dh" % round((m["end_utc"] - m["start_utc"]).total_seconds() / 3600)),
        _kv("strongest", "%s %s" % (strongest[0], _pct(strongest[1]))),
        _kv("weakest", "%s %s" % (weakest[0], _pct(weakest[1]))),
        _kv("releases", "%d timed" % len([e for e in report["events"] if e.get("timed")])),
        _kv("headlines", str(len(report["headlines"]))),
        _kv("instruments", "%d" % m["instruments_loaded"]),
    ])

    instruments = []
    for entry in report["detail"]:
        s = entry["snapshot"]
        if not s:
            continue
        cls = "up" if s["chg_pct"] >= 0 else "down"
        instruments.append(
            '<div class="inst"><div class="inst-h">'
            '<b>%s</b><span class="px">%s</span>'
            '<span class="chg %s">%s %s &middot; %s</span>'
            '<span class="px dim">range %s %s</span></div>%s%s</div>'
            % (_esc(entry["instrument"]), _fmt_px(s["close"]), cls,
               _pips(s["chg_pips"]), _esc(s["unit"]), _pct(s["chg_pct"]),
               _pips(s["range_pips"]).lstrip("+"), _esc(s["unit"]),
               zigzag_svg(entry, frames), legs_table(entry)))

    extras = [report["snapshots"][k] for k in EXTRA_INSTRUMENTS if k in report["snapshots"]]

    cal = m.get("calendar") or {}
    prov = ("Prices and headlines: ForexFactory Market Data Service "
            "(mds-api.forexfactory.com), 15-minute bars; reactions measured on "
            "5-minute bars. Calendar with actuals: ForexFactory week page"
            "%s. Analysis: %s."
            % (" (%s profile)" % cal.get("profile") if cal.get("profile") else "",
               _esc((analysis or {}).get("_model", "not run"))))
    if cal.get("degraded"):
        prov += (" <b>Calendar degraded</b>: actuals unavailable, so event "
                 "polarity could not be scored.")
    if m.get("instruments_failed"):
        prov += " Missing instruments: %s." % _esc(", ".join(m["instruments_failed"]))

    if m.get("partial"):
        prov = ("<b>Partial window</b>: this edition was built %d minutes into a "
                "%dh window, so it covers the session so far, not a closed one. "
                % (m["coverage_min"],
                   round((m["end_utc"] - m["start_utc"]).total_seconds() / 3600))) + prov

    resc = (analysis or {}).get("_probabilities_rescaled")
    resc_note = ('<div class="warn">Scenario probabilities summed to %s and were '
                 'rescaled to 1.</div>' % resc) if resc else ""

    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>FX %s %s</title>
<style>%s</style></head><body>
<div class="wrap">
<h1>%s</h1>
<div class="sub">%s &middot; %s</div>
<div class="strip">%s</div>

<h2>Where the money went</h2>
%s

<h2>Currency market map</h2>
<p class="sub">Every major against every other over the window. Columns ordered
strongest to weakest by mean move against the other seven. Reciprocal cells are
exact inverses, so USD/AUD is not simply the negative of AUD/USD.</p>
%s

<h2>Beyond the majors</h2>
<table><thead><tr><th>instrument</th><th class="num">close</th>
<th class="num">change</th><th class="num">%%</th><th class="num">range</th>
<th class="num">close in range</th></tr></thead><tbody>%s</tbody></table>

<h3>Risk context</h3>
<table><thead><tr><th>instrument</th><th class="num">close</th>
<th class="num">change</th><th class="num">%%</th><th class="num">range</th>
<th class="num">close in range</th></tr></thead><tbody>%s</tbody></table>

<h2>Event reaction functions and polarity</h2>
<p class="sub">Each release is measured from the last complete bar before it.
Polarity asks whether the currency moved the way its surprise implies &mdash;
an <b>inverted</b> read is the one worth acting on.</p>
%s

<h2>Path and attribution</h2>
<p class="sub">Legs are a zigzag over 15-minute closes, with the reversal
threshold auto-tuned to the window&rsquo;s own range so the shape stays readable.
A leg only gets a named cause when a release actually moved price the right way
within it; otherwise it is marked as having no clear catalyst.</p>
%s

<h2>Scenarios for the window ahead</h2>
%s%s

<h2>Risks</h2>
%s

<h2>Calendar ahead &mdash; %s to %s</h2>
%s

<h2>Headlines in the window</h2>
%s

<footer>%s<br>Generated %s UTC.</footer>
</div></body></html>""" % (
        _esc(m["edition_title"]), _esc(m["date"]), CSS,
        title, window, _esc(m["sessions"]), strip,
        analysis_html(analysis),
        market_map_html(report),
        snapshot_rows(extras),
        snapshot_rows(report["context"]),
        reactions_html(report),
        "\n".join(instruments),
        resc_note, scenarios_html(analysis),
        risks_html(analysis),
        m["fwd_start_utc"].astimezone(m["start_local"].tzinfo).strftime("%a %H:%M"),
        m["fwd_end_utc"].astimezone(m["start_local"].tzinfo).strftime("%a %H:%M %Z"),
        ahead_html(report),
        headlines_html(report),
        prov, m["generated_utc"].strftime("%Y-%m-%d %H:%M"),
    )


def build_markdown(report, analysis):
    m = report["meta"]
    L = []
    L.append("# FX %s - %s" % (m["edition_title"], m["date"]))
    L.append("")
    L.append("%s -> %s (%s)" % (m["start_local"].strftime("%a %d %b %H:%M"),
                                m["end_local"].strftime("%a %d %b %H:%M %Z"),
                                m["sessions"]))
    L.append("")
    if analysis and not analysis.get("error"):
        L.append(analysis.get("session_summary", ""))
        L.append("")

    L.append("## Currency strength")
    L.append("")
    L.append("| ccy | mean vs majors |")
    L.append("|---|---|")
    for c, v in report["map"]["strength"]:
        L.append("| %s | %s |" % (c, _pct(v)))
    L.append("")

    L.append("## Beyond the majors")
    L.append("")
    L.append("| instrument | close | change | % | range |")
    L.append("|---|---|---|---|---|")
    for k in EXTRA_INSTRUMENTS:
        s = report["snapshots"].get(k)
        if s:
            L.append("| %s | %s | %s %s | %s | %s |"
                     % (k, _fmt_px(s["close"]), _pips(s["chg_pips"]), s["unit"],
                        _pct(s["chg_pct"]), _pips(s["range_pips"]).lstrip("+")))
    L.append("")

    L.append("## Event reactions")
    L.append("")
    for r in report["reactions"]:
        ev, pol = r["event"], r["polarity"]
        L.append("### %s %s %s - %s" % (hhmm(ev["ts"]), ev["ccy"], ev["impact"],
                                        ev["title"]))
        L.append("actual **%s** / forecast %s / previous %s -> **%s**"
                 % (ev["actual"] or "-", ev["forecast"] or "-",
                    ev["previous"] or "-", pol["verdict"]))
        L.append("")
        L.append(pol["note"])
        L.append("")
        for n, pc, pp, u, sg in r["top_movers"]:
            L.append("- %s: %s %s (%s)" % (n, _pips(pp), u,
                                           ("%+.1f sigma" % sg) if sg else "-"))
        L.append("")

    L.append("## Path and attribution")
    L.append("")
    for entry in report["detail"]:
        L.append("### %s" % entry["instrument"])
        L.append("")
        L.append("| window | dir | %s | return | dur | attribution |"
                 % (entry["legs"][0]["unit"] if entry["legs"] else "pips"))
        L.append("|---|---|---|---|---|---|")
        for leg in entry["legs"]:
            a = leg["attribution"]
            L.append("| %s->%s | %s | %s | %s | %d min | %s: %s |"
                     % (hhmm(leg["start_ts"]), hhmm(leg["end_ts"]), leg["dir"],
                        _pips(leg["pips"]), _pct(leg["ret_pct"], 3),
                        int(leg["minutes"]), a["confidence"],
                        a["explanation"].replace("|", "/")))
        L.append("")

    if analysis and not analysis.get("error"):
        L.append("## Scenarios")
        L.append("")
        for s in sorted(analysis.get("scenarios") or [],
                        key=lambda x: -(x.get("probability") or 0)):
            p = s.get("probability")
            L.append("### %s (%s)" % (s.get("name"),
                                      "%.0f%%" % (100 * p) if isinstance(p, (int, float)) else "-"))
            L.append("")
            L.append(s.get("thesis", ""))
            L.append("")
            for pp in s.get("pair_paths") or []:
                L.append("- **%s** %s %s - %s"
                         % (pp.get("instrument"), pp.get("direction"),
                            pp.get("magnitude_pips"), pp.get("rationale")))
            L.append("")
            L.append("_Invalidated if: %s_" % s.get("invalidation", ""))
            L.append("")
        L.append("## Risks")
        L.append("")
        for r in analysis.get("risks") or []:
            L.append("- **%s** - %s (watch: %s)"
                     % (r.get("risk"), r.get("why_it_matters"), r.get("watch")))
        L.append("")

    L.append("## Calendar ahead")
    L.append("")
    L.append("| time | ccy | impact | event | forecast | previous |")
    L.append("|---|---|---|---|---|---|")
    for e in report["ahead_notable"]:
        L.append("| %s | %s | %s | %s | %s | %s |"
                 % (hhmm(e["ts"]), e["ccy"], e["impact"], e["title"],
                    e["forecast"] or "-", e["previous"] or "-"))
    L.append("")
    L.append("---")
    L.append("")
    L.append("Data: ForexFactory MDS (bars M15/M5, news) + FF calendar week page "
             "(actuals). Analysis: %s. Generated %s UTC."
             % ((analysis or {}).get("_model", "not run"),
                m["generated_utc"].strftime("%Y-%m-%d %H:%M")))
    return "\n".join(L)
