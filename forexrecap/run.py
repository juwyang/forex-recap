"""CLI entry point: build one edition and write it out.

    python -m forexrecap.run                       # today's evening edition
    python -m forexrecap.run --edition morning
    python -m forexrecap.run --date 2026-08-26 --no-llm
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from .build import build
from .config import DEFAULT_EDITION, EDITIONS
from .llm import analyse
from .page import build_html, build_markdown
from .util import report_tz


def _today_local():
    return dt.datetime.now(report_tz()).date()


def _json_default(o):
    if isinstance(o, dt.datetime):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ForexFactory-sourced FX recap")
    ap.add_argument("--date", help="report date YYYY-MM-DD (default: today, local)")
    ap.add_argument("--edition", choices=sorted(EDITIONS), default=DEFAULT_EDITION)
    ap.add_argument("--out", default="reports", help="output directory")
    ap.add_argument("--no-llm", action="store_true", help="skip the DeepSeek pass")
    ap.add_argument("--ttl", type=int, default=900, help="http cache seconds")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if the calendar degraded or instruments are missing")
    args = ap.parse_args(argv)

    day = dt.date.fromisoformat(args.date) if args.date else _today_local()
    report = build(day, args.edition, ttl=args.ttl)
    frames = report.pop("_frames")

    analysis = None
    if not args.no_llm:
        print("[llm] requesting structured analysis...")
        analysis = analyse(report["facts"])
        if analysis.get("error"):
            print("[llm] %s" % analysis["error"])
        else:
            print("[llm] ok via %s (%s tokens)"
                  % (analysis.get("_model"),
                     (analysis.get("_usage") or {}).get("total_tokens", "?")))

    stem = "%s-%s" % (day.isoformat(), args.edition)
    outdir = os.path.join(args.out, day.strftime("%Y-%m"))
    os.makedirs(outdir, exist_ok=True)

    html_path = os.path.join(outdir, stem + ".html")
    md_path = os.path.join(outdir, stem + ".md")
    json_path = os.path.join(outdir, stem + ".json")

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html(report, analysis, frames))
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(build_markdown(report, analysis))
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"meta": report["meta"], "facts": report["facts"],
                   "analysis": analysis}, fh, ensure_ascii=False, indent=1,
                  default=_json_default)

    print("[out] %s" % html_path)
    print("[out] %s" % md_path)
    print("[out] %s" % json_path)

    write_index(args.out)

    if args.strict:
        meta = report["meta"]
        problems = []
        if (meta.get("calendar") or {}).get("degraded"):
            problems.append("calendar degraded (no actuals)")
        if meta.get("instruments_failed"):
            problems.append("instruments missing: %s" % ", ".join(meta["instruments_failed"]))
        if problems:
            print("[strict] " + "; ".join(problems), file=sys.stderr)
            return 1
    return 0


def write_index(root):
    """Regenerate a flat index of every report on disk, newest first."""
    rows = []
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".html") and f != "index.html":
                rel = os.path.relpath(os.path.join(dirpath, f), root).replace("\\", "/")
                stem = f[:-5]
                date, _, edition = stem.rpartition("-")
                rows.append((date, edition, rel))
    rows.sort(reverse=True)

    items = "\n".join(
        '<li><a href="%s"><span class="d">%s</span>'
        '<span class="e %s">%s</span></a></li>' % (rel, date, edition, edition)
        for date, edition, rel in rows)

    html = """<title>FX Recap</title>
<style>
:root{--bg:#fbfbfa;--panel:#fff;--fg:#1c1c1a;--dim:#6b6b66;--line:#e3e2de;--accent:#2b5cd9}
@media(prefers-color-scheme:dark){:root{--bg:#131315;--panel:#1a1a1d;--fg:#e9e8e4;
--dim:#96958f;--line:#2c2c30;--accent:#7aa2ff}}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:640px;margin:0 auto;padding:44px 20px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);font-size:13.5px;margin-bottom:24px}
ul{list-style:none;margin:0;padding:0}
li a{display:flex;align-items:center;gap:12px;padding:11px 14px;margin-bottom:6px;
background:var(--panel);border:1px solid var(--line);border-radius:9px;
color:var(--fg);text-decoration:none}
li a:hover{border-color:var(--accent)}
.d{font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:600}
.e{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
padding:2px 7px;border-radius:4px;background:var(--line);color:var(--dim)}
.e.evening{background:rgba(43,92,217,.15);color:var(--accent)}
</style>
<div class="wrap"><h1>FX Recap</h1>
<div class="sub">Twice daily from ForexFactory data &mdash; 07:00 overnight look-back,
19:00 full trading day. Europe/Zurich.</div>
<ul>%s</ul></div>""" % items

    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("[out] %s/index.html (%d reports)" % (root, len(rows)))


if __name__ == "__main__":
    raise SystemExit(main())
