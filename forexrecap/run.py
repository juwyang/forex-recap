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
from .util import is_trading_day, report_tz


# Below this share of the window actually trading, an edition is a weekend
# artefact: a Sunday recap has nothing but crypto in it, and a Saturday evening
# one only repeats the sliver of Friday that Saturday morning already covered.
MIN_FX_COVERAGE = 0.25


def _today_local():
    return dt.datetime.now(report_tz()).date()


def _json_default(o):
    if isinstance(o, dt.datetime):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def build_one(day, edition, args, seen=None):
    """Build and write one edition.

    Returns True if anything was written. `seen`, if given, receives the meta
    dict so the caller can act on it -- --strict needs it and the writing lives
    here, not in main.
    """
    if not is_trading_day(day):
        print("[skip] %s %s -- market closed all weekend, no edition published"
              % (day, edition))
        return False
    report = build(day, edition, ttl=args.ttl)
    if seen is not None:
        seen.append(report["meta"])
    cov = report["meta"]["fx_coverage"]
    if cov < MIN_FX_COVERAGE:
        print("[skip] %s %s -- FX traded for only %.0f%% of the window"
              % (day, edition, 100 * cov))
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

Weekend days are skipped outright; Monday's morning edition bridges back
    to Friday, so nothing is lost by not publishing on Saturday or Sunday.
    """
    days = [end_day - dt.timedelta(days=i) for i in range(args.backfill, -1, -1)]
    days = [d for d in days if is_trading_day(d)]
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

    metas = []
    if not build_one(day, args.edition, args, seen=metas):
        return 0

    n = render_index(args.out)
    print("[out] %s/index.html (%d reports)" % (args.out, n))

    if args.strict:
        meta = metas[-1]
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
