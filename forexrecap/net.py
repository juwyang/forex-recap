"""HTTP with a disk cache and polite backoff.

The ForexFactory mirror rate-limits aggressively (it answers 200 with a
"Rate Limited" HTML page rather than 429), so every fetch goes through the
cache and retries exponentially. Callers must validate the payload shape --
see `fetch_json`, which treats non-JSON as a soft failure and retries.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CACHE_DIR = os.environ.get("FR_CACHE_DIR", os.path.join(os.getcwd(), "cache"))

# Both upstreams answer 429 under bursts, so every live request is spaced out
# per-host. Cache hits bypass this entirely.
MIN_INTERVAL = float(os.environ.get("FR_MIN_INTERVAL", "0.4"))
_last_hit = {}


def _host(url):
    return url.split("/")[2] if "//" in url else url


def _throttle(url):
    h = _host(url)
    wait = MIN_INTERVAL - (time.time() - _last_hit.get(h, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[h] = time.time()


def _cache_path(url):
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, h + ".cache")


def _backoff(attempt, exc):
    """Exponential with jitter; a 429 gets a much longer cool-down."""
    # mds-api has shown no rate limiting, but a 429 from any upstream is worth
    # waiting out properly rather than hammering through.
    base = 60.0 if "429" in str(exc) else 4.0
    return base * (1.7 ** attempt) * (0.75 + random.random() * 0.5)


def fetch(url, ttl=900, timeout=30, retries=5, headers=None):
    """GET `url` as text. Serves from disk cache when younger than `ttl` seconds."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    if ttl and os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)

    last = None
    for attempt in range(retries):
        try:
            _throttle(url)
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            return body
        except Exception as exc:  # noqa: BLE001 - upstream failures are varied
            last = exc
            if attempt < retries - 1:
                time.sleep(_backoff(attempt, exc))
    # Stale cache beats nothing at all.
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    raise RuntimeError("fetch failed: %s (%s)" % (url, last))


def fetch_json(url, ttl=900, timeout=30, retries=5, headers=None):
    """Like `fetch`, but a body that will not parse as JSON counts as a failure.

    That is the only way to detect the rate-limit page, which arrives as a
    200 with an HTML body.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    if ttl and os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError:
            os.remove(path)

    hdrs = {"User-Agent": UA, "Accept": "application/json,*/*"}
    if headers:
        hdrs.update(headers)

    last = None
    for attempt in range(retries):
        try:
            _throttle(url)
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            data = json.loads(body)  # raises on the rate-limit HTML page
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(_backoff(attempt, exc))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError:
            pass
    raise RuntimeError("fetch_json failed: %s (%s)" % (url, last))
