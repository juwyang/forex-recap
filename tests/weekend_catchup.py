"""What the local task decides on a weekend.

The task is registered for all seven days, so the weekend behaviour has to come
from the code rather than from the trigger. Three things must hold:

  1. Saturday and Sunday are never themselves published.
  2. A weekend run with a complete archive does nothing.
  3. A weekend run repairs a Friday the machine slept through -- which is the
     whole reason the trigger is not restricted to Mon-Fri.
"""
import datetime as dt
import sys

sys.path.insert(0, ".")
from forexrecap.config import EDITIONS          # noqa: E402
from forexrecap.util import cutoff, is_trading_day  # noqa: E402

FRI = dt.date(2026, 9, 4)
SAT = dt.date(2026, 9, 5)
SUN = dt.date(2026, 9, 6)
MON = dt.date(2026, 9, 7)


def due(today, have, now, max_days=4):
    """Mirror of run.catchup's selection, so the test exercises the real rules."""
    out = []
    for back in range(max_days, -1, -1):
        day = today - dt.timedelta(days=back)
        if not is_trading_day(day):
            continue
        for edition in sorted(EDITIONS):
            if edition in have.get(day, set()):
                continue
            if cutoff(day, edition) > now:
                continue
            out.append("%s %s" % (day, edition))
    return out


def at(day, hour):
    return dt.datetime.combine(day, dt.time(hour), tzinfo=dt.timezone.utc)


def archive(*, through, missing=()):
    """Every trading day up to `through` present, minus the named gaps.

    The lookback reaches back four days, so a fixture that lists only Friday
    and Monday leaves Tuesday to Thursday looking absent and every assertion
    fails for the wrong reason.
    """
    have = {}
    day = through - dt.timedelta(days=8)
    while day <= through:
        if is_trading_day(day):
            have[day] = {"morning", "evening"}
        day += dt.timedelta(days=1)
    for d, ed in missing:
        have[d].discard(ed)
    return have


COMPLETE = archive(through=MON)
MISSED_FRI_PM = archive(through=MON, missing=[(FRI, "evening")])

fail = 0


def check(label, got, want):
    global fail
    ok = got == want
    if not ok:
        fail = 1
    print("  %-5s %-46s -> %s" % ("ok" if ok else "FAIL", label,
                                  ", ".join(got) if got else "nothing to do"))


print("1. a weekend day is never published")
check("Sat run, archive complete", due(SAT, COMPLETE, at(SAT, 12)), [])
check("Sun run, archive complete", due(SUN, COMPLETE, at(SUN, 12)), [])

print("2. a weekday run with nothing outstanding is a no-op")
check("Mon 19:30 after both Monday editions ran",
      due(MON, COMPLETE, at(MON, 19)), [])

print("3. the weekend run repairs a Friday the machine slept through")
check("Sat 07:05, Friday evening missing",
      due(SAT, MISSED_FRI_PM, at(SAT, 5)), ["2026-09-04 evening"])
check("Sun 19:05, still missing",
      due(SUN, MISSED_FRI_PM, at(SUN, 17)), ["2026-09-04 evening"])

print("4. Monday builds its own bridged editions, not Saturday's")
check("Mon 07:05, Friday PM still missing",
      due(MON, archive(through=FRI, missing=[(FRI, "evening")]), at(MON, 5)),
      ["2026-09-04 evening", "2026-09-07 morning"])

sys.exit(fail)
