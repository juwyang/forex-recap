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

$triggers = @(
    New-ScheduledTaskTrigger -Daily -At '07:05'
    New-ScheduledTaskTrigger -Daily -At '19:05'
)

$settings = New-ScheduledTaskSettingsSet `
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
