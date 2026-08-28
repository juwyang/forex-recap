#!/usr/bin/env bash
# Exercise the workflow's edition-selection logic against every cron/DST pair.
decide() {
  local SCHEDULE="$1" OFFSET="$2" EDITION WANT
  EDITION=auto
  if [ -n "$SCHEDULE" ]; then
    case "$SCHEDULE" in
      "8 5 * * 1-5")  EDITION=morning; WANT="+0200" ;;
      "8 6 * * 1-5")  EDITION=morning; WANT="+0100" ;;
      "8 17 * * 1-5") EDITION=evening; WANT="+0200" ;;
      "8 18 * * 1-5") EDITION=evening; WANT="+0100" ;;
      *) echo "SKIP  (unrecognised cron)"; return ;;
    esac
    if [ "$OFFSET" != "$WANT" ]; then
      echo "SKIP  (DST twin: offset $OFFSET, this cron is the $WANT one)"; return
    fi
    echo "BUILD $EDITION"
  fi
}

printf '%-34s %s\n' "trigger" "outcome"
echo "-- summer, Zurich at +0200 --"
printf '  %-30s %s\n' "cron 8 5  (07:08 CEST)"  "$(decide '8 5 * * 1-5'  '+0200')"
printf '  %-30s %s\n' "cron 8 6  (08:08 CEST)"  "$(decide '8 6 * * 1-5'  '+0200')"
printf '  %-30s %s\n' "cron 8 17 (19:08 CEST)"  "$(decide '8 17 * * 1-5' '+0200')"
printf '  %-30s %s\n' "cron 8 18 (20:08 CEST)"  "$(decide '8 18 * * 1-5' '+0200')"
echo "-- winter, Zurich at +0100 --"
printf '  %-30s %s\n' "cron 8 5  (06:08 CET)"   "$(decide '8 5 * * 1-5'  '+0100')"
printf '  %-30s %s\n' "cron 8 6  (07:08 CET)"   "$(decide '8 6 * * 1-5'  '+0100')"
printf '  %-30s %s\n' "cron 8 17 (18:08 CET)"   "$(decide '8 17 * * 1-5' '+0100')"
printf '  %-30s %s\n' "cron 8 18 (19:08 CET)"   "$(decide '8 18 * * 1-5' '+0100')"
echo "-- a queued run that arrives 90 minutes late, summer --"
printf '  %-30s %s\n' "cron 8 5 delivered 08:38" "$(decide '8 5 * * 1-5' '+0200')"
