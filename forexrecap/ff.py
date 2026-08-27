"""ForexFactory Market Data Service client.

www.forexfactory.com is behind Cloudflare and answers 403 to scripts, but the
site's own data backend at mds-api.forexfactory.com is a plain anonymous JSON
API -- no cookie, no bearer, no browser fingerprint. That is where FF's own
charts and news ticker get their data, so this is first-party FF data.

    GET /bars?instrument=EUR/USD&interval=M15&from=&to=&per_page=
    GET /indicators/news?from=&to=&interval=M15&instrument=EUR/USD
    GET /instrument-list/status?dateline=

Quirks confirmed by probing (2026-08-26):
  * `instrument` is the display name with a slash: "EUR/USD", "Gold/USD".
    "XAU/USD" is rejected -- FF names metals and energy in words.
  * `per_page` is advisory; the whole window comes back in one response.
  * The news feed is site-wide; `instrument` is required but ignored. The
    `interval` controls the importance tier: M15/M30/H1 return low+medium+high,
    H4/D1 only high.
  * News windows are capped per interval (M15 ~21 days), so keep them short.
"""
from __future__ import annotations

import datetime as dt
import urllib.parse

import pandas as pd

from .net import fetch_json
from .util import UTC

BASE = "https://mds-api.forexfactory.com"
OHLC = ["open", "high", "low", "close"]


def _url(path, **params):
    return BASE + path + "?" + urllib.parse.urlencode(params)


def _unwrap(payload, what):
    data = (payload or {}).get("data")
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError("%s: %s (code %s)" % (what, data.get("error"), data.get("code")))
    if data is None:
        raise RuntimeError("%s: empty payload" % what)
    return data


def instruments(ttl=86400):
    """All tradable instrument names FF currently serves."""
    now = int(dt.datetime.now(UTC).timestamp())
    data = _unwrap(fetch_json(_url("/instrument-list/status", dateline=now), ttl=ttl),
                   "instrument-list")
    return [row["name"] for row in data if row.get("name")]


def bars(instrument, start, end, interval="M15", ttl=900):
    """OHLC DataFrame indexed by UTC bar-open time.

    `start`/`end` are aware datetimes. FF returns newest-first, so it is sorted
    here. An instrument that is closed over the window returns an empty frame
    rather than raising -- crosses halt at the weekend, indices overnight.
    """
    url = _url("/bars", instrument=instrument, interval=interval,
               **{"from": int(start.timestamp()), "to": int(end.timestamp()),
                  "per_page": 1000})
    rows = _unwrap(fetch_json(url, ttl=ttl), "bars %s" % instrument)
    if not rows:
        return pd.DataFrame(columns=OHLC, index=pd.DatetimeIndex([], tz=UTC))
    idx = pd.DatetimeIndex([dt.datetime.fromtimestamp(r["timestamp"], UTC) for r in rows])
    df = pd.DataFrame({k: [float(r[k]) for r in rows] for k in OHLC}, index=idx)
    return df[~df.index.duplicated(keep="last")].sort_index()


def news(start, end, interval="M15", ttl=900):
    """Site-wide FF news headlines in the window, oldest first.

    interval M15 widens the tier to low+medium+high; H4 narrows it to high only.
    """
    url = _url("/indicators/news", instrument="EUR/USD", interval=interval,
               **{"from": int(start.timestamp()), "to": int(end.timestamp()),
                  "per_page": 1000})
    rows = _unwrap(fetch_json(url, ttl=ttl), "news")
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "ts": dt.datetime.fromtimestamp(r["timestamp"], UTC),
            "title": (r.get("title") or "").strip(),
            "impact": (r.get("impact") or "low").lower(),
            "impact_value": r.get("impact_value") or 1,
            "views": r.get("views") or 0,
            "url": "https://www.forexfactory.com" + (r.get("url") or ""),
        })
    out.sort(key=lambda n: n["ts"])
    return out
