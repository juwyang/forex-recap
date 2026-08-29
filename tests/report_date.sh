#!/usr/bin/env bash
# The report date must follow the edition's cutoff, not the moment the runner
# starts. GitHub delivered a Friday 19:00 cron at 02:56 on Saturday; reading the
# clock made the job build a Saturday edition, which does not exist, and the
# missing file then failed the summary step and skipped the commit.
resolve() {                      # resolve <edition> <local hour> <today> <yesterday>
  local EDITION="$1" NOW_H="$2" TODAY="$3" YESTERDAY="$4" CUT=19
  [ "$EDITION" = "morning" ] && CUT=7
  if [ "$((10#$NOW_H))" -lt "$CUT" ]; then echo "$YESTERDAY"; else echo "$TODAY"; fi
}

THU=2026-08-27; FRI=2026-08-28; SAT=2026-08-29
fail=0
check() {                        # check <edition> <hour> <today> <yesterday> <expect> <note>
  local got; got=$(resolve "$1" "$2" "$3" "$4")
  if [ "$got" = "$5" ]; then printf '  ok    '; else printf '  FAIL  '; fail=1; fi
  printf '%-8s at %s local, today=%s -> %s   %s\n' "$1" "$2" "$3" "$got" "$6"
}

echo "Friday's 19:08 evening slot -- every delivery must recap Friday"
check evening 19 "$FRI" "$THU" "$FRI" "on time"
check evening 20 "$FRI" "$THU" "$FRI" "84 min late, still Friday"
check evening 02 "$SAT" "$FRI" "$FRI" "6h late, clock says Saturday"

echo "Friday's 07:08 morning slot -- every delivery must recap Friday"
check morning 07 "$FRI" "$THU" "$FRI" "on time"
check morning 11 "$FRI" "$THU" "$FRI" "4h late"
check morning 23 "$FRI" "$THU" "$FRI" "absurdly late, same day"
check morning 06 "$FRI" "$THU" "$THU" "delivered before the cutoff"

exit $fail
