<#
.SYNOPSIS
  Build and publish whatever edition is due. Meant for Windows Task Scheduler.

.DESCRIPTION
  GitHub's own scheduler delivers this repository's cron runs 2.5-6.6 hours
  late (morning median 4.7h, evening 2.9h), while the build itself takes about
  three minutes. Running locally on time is the fix; the GitHub schedule stays
  on as a backup for whenever this machine is off.

  WEEKENDS. This task is registered for all seven days on purpose, and the
  decision of what to build is left to the code rather than to the trigger:

    * --catchup builds only editions whose cutoff has already passed, that are
      missing from reports/, and whose date is a trading day. A Saturday or
      Sunday run therefore finds nothing to do and exits in seconds.
    * But if this machine was asleep on Friday evening, the Saturday run is
      what repairs that missing edition. Restricting the trigger to Mon-Fri
      would throw that away and gain nothing, since weekend runs are no-ops.
    * Monday's editions bridge back over the weekend (Monday 07:00 recaps from
      Friday 07:00), which is handled in the window maths, not here.

  The pull is not optional: the GitHub backup may have committed a report since
  the last local run, and building on a stale tree recreates reports that
  already exist and then fails to push.
#>
[CmdletBinding()]
param(
    # How far back to repair. Four days covers a long weekend plus a day; the
    # default of ten would mean twenty LLM calls after a week-long absence.
    [int]$CatchupDays = 4,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$logDir = Join-Path (Get-Location) 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }
$log = Join-Path $logDir ("local-{0}.log" -f (Get-Date -Format 'yyyy-MM'))

function Write-Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $log -Value $line -Encoding utf8
    Write-Output $line
}

# Task Scheduler does not inherit an interactive PATH, so resolve python once
# and fail loudly rather than silently running nothing.
if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source }
    elseif (Test-Path 'D:\ANACONDA3\python.exe') { $Python = 'D:\ANACONDA3\python.exe' }
    else { Write-Log 'FAIL: python not found; pass -Python <path>'; exit 1 }
}

Write-Log "--- start (python: $Python) ---"

try {
    git pull --rebase --quiet
    if ($LASTEXITCODE -ne 0) { Write-Log 'FAIL: git pull --rebase'; exit 1 }

    & $Python -m forexrecap.run --catchup --catchup-days $CatchupDays --out reports 2>&1 |
        ForEach-Object { Write-Log $_ }
    if ($LASTEXITCODE -ne 0) { Write-Log "FAIL: build exited $LASTEXITCODE"; exit 1 }

    git add reports
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
        git commit --quiet -m "recap (local run $stamp)"
        git push --quiet
        if ($LASTEXITCODE -ne 0) { Write-Log 'FAIL: git push'; exit 1 }
        Write-Log 'pushed'
    } else {
        Write-Log 'nothing due; archive already complete'
    }
    Write-Log '--- done ---'
}
catch {
    Write-Log "FAIL: $_"
    exit 1
}
