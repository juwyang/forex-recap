# forex-recap

A twice-daily FX recap built entirely from ForexFactory data: what moved, by how
much, why (or explicitly why not), how each pair reacted to each release, and
what the scenarios are into the next window.

Two editions, both anchored to **Europe/Zurich**:

| edition | runs at | covers | projects |
|---|---|---|---|
| `morning` | 07:00 | previous 19:00 → 07:00 (overnight, Asia) | 07:00 → 19:00 |
| `evening` | 19:00 | previous 19:00 → 19:00 (full trading day) | 19:00 → next 19:00 |

Nothing is published on Saturday or Sunday. Rather than leave the weekend
uncovered, **each edition spans everything since the previous edition of its own
kind**: Monday 07:00 runs from Friday 07:00 and Monday 19:00 from Friday 19:00,
both 72-hour windows carrying the Friday session, the weekend, and the Asia
reopen. Neither series double-counts and neither has a gap. The look-ahead
bridges the other way, so Friday evening previews Monday's calendar instead of
an empty Saturday.

Windows are localised at both ends, so a DST changeover produces a 23h or 25h
day rather than silently sliding the cutoff off 19:00 local.

## What it produces

`reports/index.html` is a month calendar: every day cell links its AM and PM
editions, with the session's strongest and weakest currency in the tooltip.
It is rebuilt by scanning the report files on every run, so a deleted or
rebuilt report can never leave it stale.

For each edition, into `reports/YYYY-MM/YYYY-MM-DD-<edition>.{html,md,json}`:

- **Currency market map** — every major against every other, laid out like
  barchart's, columns ordered strongest to weakest by mean move against the
  other seven. Reciprocal cells are exact inverses (`1/(1+r)-1`), so USD/AUD
  reads −0.13% when AUD/USD reads +0.12%, not −0.12%.
- **Beyond the majors** — USD/ZAR, USD/MXN, Gold/USD, BTC/USD, Brent/USD, plus
  DXY / SPX / VIX as risk context.
- **Path and attribution** — a zigzag over 15-minute closes for each tracked
  instrument, each leg carrying amplitude in pips *and* percent return, duration,
  and an attributed cause.
- **Event reaction functions and polarity** — for every medium/high release, the
  measured move across 5/15/60-minute horizons on every tracked instrument,
  ranked by size relative to that instrument's own volatility.
- **Scenarios, per-pair paths, and risks** — from DeepSeek, over the measured
  numbers only.

## The parts that required judgement

**Attribution refuses by default.** Plenty of intraday legs are flow or
positioning, and labelling them with whatever release happened to be nearby is
how a recap becomes fiction. A candidate must be relevant to the instrument,
land near the leg's *start*, and show a same-direction price impulse in the 15
minutes after it. Otherwise the leg is marked *no clear catalyst*. On a typical
day most legs are — that is the honest answer, not a bug.

Long legs get a second channel: releases that pushed a leg along without
starting it are reported as **in-leg drivers** rather than promoted to causes.

**The zigzag never fills a quota.** The reversal threshold is a fraction of the
window's own range, auto-tuned upward when a instrument is too noisy — but it is
only relaxed to a floor, never far enough to shred a clean two-move day into
five legs. An instrument that trended one way all session is drawn as one leg
and flagged as untuned.

**Polarity is measured, not assumed.** Each release is measured from the last
complete bar *before* it — the bar stamped 13:30 already contains a 13:30
release, so using it as the baseline measures the fade instead of the spike.
A release whose currency moves *against* its own surprise is labelled
**INVERTED**; that is the finding worth acting on.

**Reactions are normalised.** Ranking pairs by raw percent move just ranks them
by volatility and puts BTC on top every time. Movers are ranked by move ÷ that
instrument's own volatility over the window, reported in σ.

**A dead market is not a session.** An edition is skipped when the majors
traded for less than a quarter of its window. Testing "did any instrument
return bars" is not the same question and answers yes on a closed Sunday,
because BTC trades all weekend — a market map with one instrument in it and a
currency-strength spread of 0.000%.

**Simultaneous releases are one event.** CPI m/m, CPI y/y and the trimmed mean
print on one timestamp and trade as one block; scoring them separately would
triple-count a single price reaction.

## Data sources

Everything is ForexFactory, reached two ways:

- **Bars and news** — `mds-api.forexfactory.com`, the backend FF's own charts
  use. Anonymous JSON, no key, no cookie, no Cloudflare. 95 instruments,
  intervals M1…MN1.
  ```
  GET /bars?instrument=EUR/USD&interval=M15&from=<epoch>&to=<epoch>&per_page=1000
  GET /indicators/news?from=&to=&interval=M15&instrument=EUR/USD
  GET /instrument-list/status?dateline=<epoch>
  ```
  Instrument names are FF's display names with a slash — `Gold/USD`, not
  `XAU/USD`, which the API rejects.

- **Calendar with actuals** — `www.forexfactory.com/calendar?week=aug24.2026`,
  parsed out of the inline `calendarComponentStates` blob. The page 403s a
  normal client, but the block is on the **TLS fingerprint, not on cookies**:
  `curl_cffi` impersonating Safari walks through with no `cf_clearance` and no
  session. Chrome fingerprints are currently rejected, which is why the
  impersonation list is ordered Safari-first.

  The keyless `nfs.faireconomy.media/ff_calendar_thisweek.json` feed is kept as
  a fallback, but it is a **schedule only** — it has no `actual` field at all, so
  when it is used the report marks itself calendar-degraded and skips polarity
  rather than pretending.

## Running it

```bash
pip install -r requirements.txt
```

```bash
python -m forexrecap.run --edition evening
```

```bash
python -m forexrecap.run --date 2026-08-26 --edition morning --no-llm
```

`--backfill N` rebuilds the N days before `--date`, both editions, so the
calendar index has history from day one:

```bash
python -m forexrecap.run --backfill 13 --no-llm
```

`--catchup` builds every edition whose cutoff has already passed and which is
not on disk, and does nothing otherwise:

```bash
python -m forexrecap.run --catchup
```

`--strict` exits non-zero if the calendar degraded or instruments went missing,
for use in CI when you would rather fail than publish a thin report.

The DeepSeek key comes from `DEEPSEEK_API_KEY`, falling back to a local
`cred_deepseek.txt` (`API-key: sk-...`). `deepseek-v4-pro` is a reasoning model
and bills its reasoning to the same completion budget, so `DEEPSEEK_MAX_TOKENS`
defaults to 16000 — at 4000 the entire allowance goes to reasoning and the API
returns an empty string.

## Automation

`.github/workflows/recap.yml` runs both editions on a schedule and publishes to
GitHub Pages. GitHub cron is UTC with no DST awareness, so each edition is
scheduled at *both* its winter and summer UTC hour and the job discards the
twin that is an hour off.

It works that out from **which cron fired** (`github.event.schedule`) and
Zurich's current UTC offset — never from the wall clock at execution time.
GitHub's scheduler routinely delivers a scheduled run 10–60 minutes late, and
an hour-of-the-day check reads that delay as "wrong twin" and silently
publishes nothing. Lateness is otherwise harmless here: the window is derived
from the report date and the cutoff hour, so a late run simply has more
complete data. `tests/decide_matrix.sh` exercises all eight cron/DST
combinations plus a 90-minute-late delivery.

**GitHub's scheduler is best-effort, and it has dropped every slot for this
repository so far** — workflow state `active`, valid cron, public repo, Actions
operational, and still zero `schedule` events over two days, while
`workflow_dispatch` works every time. Nothing in the run reports an error,
because the run never happens. So the workflow does not assume each trigger
arrives: every run ends with a `--catchup` pass that builds whatever closed
window is missing from `reports/`. One trigger a day, whenever it lands, is
enough to keep the archive whole; a manual dispatch repairs it immediately.

Set the `DEEPSEEK_API_KEY` repository secret and enable Pages (source: GitHub
Actions). Without the key the report still builds — every measurement is
independent of the model — and the analysis section says it is unavailable.

**On a private repository.** Actions runs normally; at roughly 4 minutes a run,
twice a day on weekdays, this uses about 180 of the plan's monthly minutes.
Pages from a private repo needs GitHub Pro or above — on Free, flipping the repo
to private unpublishes the site. Changing visibility also resets the Pages
configuration either way, so re-select "GitHub Actions" as the source and
re-run the workflow afterwards.

A private repo does **not** make the published site private: the Pages URL stays
reachable to anyone who has it. Only Enterprise Cloud can put access control in
front of it. Both page templates therefore carry
`<meta name="robots" content="noindex,nofollow">` so the reports stay out of
search results. A `robots.txt` would not help — for a project page served from
a subpath, crawlers only honour the one at the domain root, which belongs to
the user site, not this repo.

The Safari-fingerprint Cloudflare bypass was a question mark for CI, since
datacenter ranges get challenged harder than residential ones. It has now been
verified on a GitHub-hosted runner: `calendar: ok via safari17_0 (38 actuals)`,
36/36 instruments. If it ever does start degrading, the run says so in the job
summary and on the page rather than quietly publishing a report with no event
polarity; the fix would be to route that one request through a residential
proxy, or to restore the `cf_clearance` cookie with the cookie in a secret.

## Layout

```
forexrecap/
  config.py        editions, instrument universe, tick sizes, thresholds
  util.py          timezone/DST window maths, pip conventions, number parsing
  net.py           http with disk cache, per-host throttle, 429 backoff
  ff.py            ForexFactory MDS client (bars, news, instrument list)
  calendar_ff.py   FF calendar week page w/ actuals, release-block grouping
  index.py         the month-calendar landing page
  market.py        session snapshots, currency strength, the 8x8 map
  zigzag.py        leg segmentation with an auto-tuned threshold
  attribution.py   leg -> cause, with the impulse test that lets it say no
  reaction.py      reaction functions, volatility normalisation, polarity
  llm.py           DeepSeek structured analysis, schema-checked
  render.py        map, charts, tables
  page.py          full HTML page + Markdown twin
  build.py         orchestration
  run.py           CLI
```
