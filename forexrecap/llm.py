"""Structured analysis via DeepSeek.

Everything quantitative -- legs, amplitudes, the market map, reaction functions
-- is computed before the model is called. The model's job is interpretation:
naming the session's themes, projecting scenarios, and saying what each
instrument does under each. It is given the numbers and told not to invent new
ones, and its output is schema-checked, so a bad response degrades the report
to "analysis unavailable" rather than corrupting it.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

API = "https://api.deepseek.com/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
FALLBACK_MODEL = "deepseek-v4-flash"
# Must cover reasoning tokens as well as the answer on the -pro model.
MAX_TOKENS = int(os.environ.get("DEEPSEEK_MAX_TOKENS", "16000"))


def _clean_key(raw):
    """Accept either a bare key or a whole `API-key: sk-...` line.

    Pasting the full cred-file line into a CI secret is the obvious mistake and
    it fails silently -- the report still builds, the analysis section just says
    unavailable forever. Cheaper to tolerate it than to debug it.
    """
    if not raw:
        return None
    key = raw.strip().strip('"').strip("'")
    if ":" in key and not key.startswith("sk-"):
        key = key.split(":", 1)[1].strip()
    return key or None


def load_key(path=None):
    """DEEPSEEK_API_KEY wins; otherwise read the local cred file."""
    env = _clean_key(os.environ.get("DEEPSEEK_API_KEY"))
    if env:
        return env
    for cand in ([path] if path else []) + [
            os.path.join(os.getcwd(), "cred_deepseek.txt"),
            os.path.join(os.path.dirname(os.getcwd()), "cred_deepseek.txt")]:
        if cand and os.path.exists(cand):
            return _clean_key(open(cand, encoding="utf-8").read())
    return None


SYSTEM = """You are a sell-side FX strategist writing the analysis section of an \
intraday recap. You are given already-computed measurements: zigzag legs with \
amplitudes, a currency market map, event reaction functions with measured \
polarity, and the calendar for the window ahead.

Rules:
- Never invent a number. Every figure you cite must appear in the input.
- When the input says a leg has no clear catalyst, say so. Do not manufacture one.
- Polarity marked "inverted" means the currency moved against its surprise. \
That is a finding; explain what it implies about positioning.
- Scenario probabilities must sum to 1.0 across the scenarios you give.
- Be specific and short. No hedging boilerplate, no "traders should monitor".
Return only JSON matching the requested schema."""

SCHEMA_HINT = """Return JSON with exactly these keys:
{
 "session_summary": "3-4 sentences: what drove the window and what the tape says",
 "themes": [{"theme": "...", "evidence": "...", "currencies": ["USD","JPY"]}],
 "leg_notes": {"EUR/USD": "one sentence tying that instrument's legs together"},
 "polarity_reads": [{"event":"...","read":"what the measured reaction says about positioning"}],
 "scenarios": [{"name":"...","probability":0.45,"thesis":"...",
                "triggers":["..."],"invalidation":"...",
                "pair_paths":[{"instrument":"EUR/USD","direction":"up|down|range",
                               "magnitude_pips":40,"rationale":"..."}]}],
 "risks": [{"risk":"...","why_it_matters":"...","watch":"..."}],
 "calendar_ahead_note": "what in the coming window can change the picture"
}"""

REQUIRED = ["session_summary", "themes", "scenarios", "risks"]


def _post(payload, key, timeout=180):
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def analyse(facts, key=None, model=None, retries=2):
    """facts dict -> validated analysis dict, or {'error': ...} on failure."""
    key = key or load_key()
    if not key:
        return {"error": "no DeepSeek API key (set DEEPSEEK_API_KEY or cred_deepseek.txt)"}

    prompt = (SCHEMA_HINT + "\n\nMEASURED FACTS:\n"
              + json.dumps(facts, ensure_ascii=False, indent=1, default=str))
    models = [model or MODEL, FALLBACK_MODEL]
    last = None
    for m in models:
        for attempt in range(retries):
            try:
                data = _post({
                    "model": m,
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                    "max_tokens": MAX_TOKENS,
                }, key)
                choice = data["choices"][0]
                text = (choice.get("message") or {}).get("content") or ""
                if not text.strip():
                    # deepseek-v4-pro reasons before answering and bills that to
                    # the same completion budget. Too small a max_tokens and the
                    # whole allowance goes to reasoning_tokens, returning an
                    # empty string with finish_reason "length".
                    raise ValueError(
                        "empty content (finish_reason=%s, completion_tokens=%s) "
                        "-- raise DEEPSEEK_MAX_TOKENS"
                        % (choice.get("finish_reason"),
                           (data.get("usage") or {}).get("completion_tokens")))
                if choice.get("finish_reason") == "length":
                    raise ValueError("response truncated -- raise DEEPSEEK_MAX_TOKENS")
                parsed = json.loads(text)
                missing = [k for k in REQUIRED if k not in parsed]
                if missing:
                    raise ValueError("response missing keys: %s" % missing)
                parsed["_model"] = data.get("model", m)
                parsed["_usage"] = data.get("usage")
                _normalise_probabilities(parsed)
                return parsed
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < retries - 1:
                    time.sleep(4 * (attempt + 1))
        print("[llm] %s failed (%s); trying next model" % (m, last))
    return {"error": "DeepSeek analysis failed: %s" % last}


def _normalise_probabilities(parsed):
    """Rescale scenario probabilities to sum to 1 and flag that we did."""
    scen = parsed.get("scenarios") or []
    probs = [s.get("probability") for s in scen]
    vals = [p for p in probs if isinstance(p, (int, float))]
    total = sum(vals)
    if not vals or abs(total - 1.0) < 0.02 or total <= 0:
        return
    for s in scen:
        if isinstance(s.get("probability"), (int, float)):
            s["probability"] = s["probability"] / total
    parsed["_probabilities_rescaled"] = round(total, 3)
