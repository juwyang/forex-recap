<#
.SYNOPSIS
  Register the twice-daily local build with Windows Task Scheduler.

.DESCRIPTION
  Two triggers, 07:05 and 19:05 local, five minutes after each cutoff so the
  final 15-minute bar has settled upstream before the window is read.

  Fires every day, not Mon-Fri: see the weekend note in run_local.ps1. Weekend
  runs are seconds-long no-ops that exist to repair a Friday the machine slept
  through.

  StartWhenAvailable matters more than the trigger times do -- a laptop that
  was asleep at 07:05 runs the moment it wakes, and --catchup then builds
  whatever the nap cost.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'FX recap',
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$repo   = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script = Join-Path $repo 'scripts\run_local.ps1'
if (-not (Test-Path $script)) { throw "not found: $script" }

$argline = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
if ($Python) { $argline += " -Python `"$Python`"" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument $argline -WorkingDirectory $repo

# Two things have to be right here, and the obvious spelling gets both wrong.
#
# New-ScheduledTaskTrigger bakes the offset in force at registration time into
# StartBoundary ("2026-09-10T07:05:00+02:00"), and Windows then honours that
# absolute instant rather than the wall clock. When CEST ended the boundary
# rewrote itself to 06:05+01:00 -- the same moment in UTC, an hour early in
# local terms -- and both editions started firing BEFORE their own cutoffs,
# so --catchup correctly found nothing due and the task became a silent no-op.
# Stripping the offset makes the boundary float with local time, which is what
# "every day at 07:05" was supposed to mean.
#
# Deliberately NOT a repetition interval. Retrying every half hour would be
# papering over the boundary bug above rather than fixing it, and it retries
# the wrong thing: a run that finds nothing due exits 0, so unconditional
# repeats cost twelve pointless pulls a day while doing nothing for the case
# that actually fails. Restart-on-failure below covers that case instead.
$triggers = @()
foreach ($at in '07:05', '19:05') {
    $t = New-ScheduledTaskTrigger -Daily -At $at
    $t.StartBoundary = '2026-01-01T' + $at + ':00'   # no offset: local, DST-following
    $triggers += $t
}

# RestartCount fires only when the run exits non-zero -- an upstream timeout,
# a push that raced someone else -- so a healthy day is exactly two runs.
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
    -Settings $settings -Description 'Twice-daily FX recap (07:05 / 19:05 local)' `
    -Force | Out-Null

Write-Output "Registered '$TaskName':"
Get-ScheduledTask -TaskName $TaskName |
    Get-ScheduledTaskInfo |
    Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
Write-Output "Run it once now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "Logs:                  $repo\logs\"
