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
from .index import render as render_index
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


def build_one(day, edition, args):
    """Build and write one edition. Returns True if anything was written."""
    report = build(day, edition, ttl=args.ttl)
    if report["meta"]["instruments_loaded"] == 0:
        print("[skip] %s %s -- no quotes in the window (market closed)"
              % (day, edition))
        return False
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

    stem = "%s-%s" % (day.isoformat(), edition)
    outdir = os.path.join(args.out, day.strftime("%Y-%m"))
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, stem + ".html"), "w", encoding="utf-8") as fh:
        fh.write(build_html(report, analysis, frames))
    with open(os.path.join(outdir, stem + ".md"), "w", encoding="utf-8") as fh:
        fh.write(build_markdown(report, analysis))
    with open(os.path.join(outdir, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": report["meta"], "facts": report["facts"],
                   "analysis": analysis}, fh, ensure_ascii=False, indent=1,
                  default=_json_default)
    print("[out] %s/%s.{html,md,json}" % (outdir, stem))
    return True


def backfill(end_day, args):
    """Rebuild history so the calendar is not empty on day one.

    Weekend editions are attempted rather than assumed away: a Monday morning
    edition covers Sunday evening, when the market has already reopened, so the
    honest test is whether quotes came back -- `build_one` skips only when they
    did not.
    """
    days = [end_day - dt.timedelta(days=i) for i in range(args.backfill, -1, -1)]
    written = 0
    for day in days:
        for edition in sorted(EDITIONS):
            try:
                written += bool(build_one(day, edition, args))
            except Exception as exc:  # noqa: BLE001 - one bad day must not stop the rest
                print("[backfill] %s %s failed: %s" % (day, edition, exc))
    n = render_index(args.out)
    print("[backfill] wrote %d editions; index now lists %d" % (written, n))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="ForexFactory-sourced FX recap")
    ap.add_argument("--date", help="report date YYYY-MM-DD (default: today, local)")
    ap.add_argument("--edition", choices=sorted(EDITIONS), default=DEFAULT_EDITION)
    ap.add_argument("--out", default="reports", help="output directory")
    ap.add_argument("--no-llm", action="store_true", help="skip the DeepSeek pass")
    ap.add_argument("--ttl", type=int, default=900, help="http cache seconds")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if the calendar degraded or instruments are missing")
    ap.add_argument("--backfill", type=int, metavar="N",
                    help="also build the N days before --date, both editions")
    args = ap.parse_args(argv)

    day = dt.date.fromisoformat(args.date) if args.date else _today_local()

    if args.backfill:
        return backfill(day, args)

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

    n = render_index(args.out)
    print("[out] %s/index.html (%d reports)" % (args.out, n))

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


if __name__ == "__main__":
    raise SystemExit(main())
