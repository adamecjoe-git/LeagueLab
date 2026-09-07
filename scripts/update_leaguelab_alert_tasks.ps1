param(
    [ValidateSet("preview", "test", "live")]
    [string]$Mode = "preview",

    [string]$Date = "",

    [switch]$PlanOnly,

    [switch]$IncludePast,

    [switch]$InstallDailyTask,

    [string]$DailyTime = "06:00"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\jadamec\source\FantasyFootball"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"
$Planner = "$ProjectRoot\src\leaguelab\dynamic_alert_scheduler.py"
$Runner = "$ProjectRoot\src\leaguelab\roster_alert_runner.py"
$LogDir = "$ProjectRoot\logs"
$TaskPrefix = "LeagueLab Alert "
$DailyTaskName = "LeagueLab Daily Scheduler"
$ThisScript = $MyInvocation.MyCommand.Path

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function ConvertTo-EncodedPowerShell {
    param([string]$CommandText)

    $bytes = [System.Text.Encoding]::Unicode.GetBytes($CommandText)
    return [Convert]::ToBase64String($bytes)
}

function New-LeagueLabPrincipal {
    return New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited
}

function Install-DailySchedulerTask {
    $time = [DateTime]::ParseExact(
        $DailyTime,
        "HH:mm",
        [System.Globalization.CultureInfo]::InvariantCulture
    )

    $dailyLog = "$LogDir\daily_scheduler.log"

    $command = @"
`$env:PYTHONPATH = '$ProjectRoot\src'
Set-Location '$ProjectRoot'
'============================================================' | Out-File '$dailyLog' -Append
'Daily scheduler started: ' + (Get-Date) | Out-File '$dailyLog' -Append
& '$ThisScript' -Mode '$Mode' *>> '$dailyLog'
'Daily scheduler finished: ' + (Get-Date) | Out-File '$dailyLog' -Append
"@

    $encoded = ConvertTo-EncodedPowerShell $command

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand $encoded" `
        -WorkingDirectory $ProjectRoot

    # Reconcile once per hour beginning at the configured anchor time.
    # This only checks the NFL schedule; Yahoo is still refreshed only by
    # actual 30/5-minute alert tasks.
    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At $time `
        -RepetitionInterval (New-TimeSpan -Hours 1) `
        -RepetitionDuration (New-TimeSpan -Days 3650)

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $DailyTaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal (New-LeagueLabPrincipal) `
        -Settings $settings `
        -Force | Out-Null

    Write-Host ""
    Write-Host "Installed: $DailyTaskName"
    Write-Host "First run: $DailyTime"
    Write-Host "Reconciliation: every hour"
    Write-Host "Mode: $Mode"
    Write-Host "The task runs only in the logged-on Windows session (locked is OK)."
}

if ($InstallDailyTask) {
    Install-DailySchedulerTask
    exit 0
}

$plannerArgs = @(
    $Planner,
    "--json"
)

if ($Date) {
    $plannerArgs += @("--date", $Date)
}

if ($IncludePast) {
    $plannerArgs += "--include-past"
}

$env:PYTHONPATH = "$ProjectRoot\src"
Set-Location $ProjectRoot

$json = & $Python @plannerArgs

if ($LASTEXITCODE -ne 0) {
    throw "LeagueLab dynamic planner failed with exit code $LASTEXITCODE."
}

$plan = $json | ConvertFrom-Json

Write-Host ""
Write-Host "LeagueLab Dynamic Task Scheduler"
Write-Host "================================"
Write-Host "Date: $($plan.date)"

if ($null -eq $plan.season) {
    Write-Host "No NFL regular-season games today."

    if (-not $PlanOnly) {
        # Only remove generated alert tasks for the target date.  Do not touch
        # future-dated LeagueLab alert tasks that may have been created for
        # testing or for another scheduled NFL date.
        $targetTaskPrefix = "$TaskPrefix$($plan.date) "
        $tasksToRemove = @(
            Get-ScheduledTask -ErrorAction SilentlyContinue |
                Where-Object { $_.TaskName -like "$targetTaskPrefix*" }
        )

        if ($tasksToRemove.Count -gt 0) {
            $tasksToRemove |
                Unregister-ScheduledTask -Confirm:$false

            Write-Host (
                "Removed {0} LeagueLab alert task(s) for {1}." -f `
                $tasksToRemove.Count,
                $plan.date
            )
        }
        else {
            Write-Host "No LeagueLab alert tasks exist for $($plan.date)."
        }
    }

    exit 0
}

Write-Host "NFL: $($plan.season) Week $($plan.week)"
Write-Host "Schedule: $($plan.schedule)"
Write-Host "Mode: $Mode"
Write-Host ""

if (-not $plan.checkpoints -or $plan.checkpoints.Count -eq 0) {
    Write-Host "No future checkpoints remain for this date."
    exit 0
}

foreach ($checkpoint in $plan.checkpoints) {
    $runAt = [DateTimeOffset]::Parse($checkpoint.run_at).LocalDateTime
    Write-Host ("{0}  RUN" -f $runAt.ToString("ddd h:mm tt"))

    foreach ($kickoff in $checkpoint.kickoffs) {
        $kickoffAt = [DateTimeOffset]::Parse($kickoff.kickoff_at).LocalDateTime
        Write-Host (
            "    {0} min before {1} {2} @ {3}" -f `
            $kickoff.minutes_before,
            $kickoffAt.ToString("h:mm tt"),
            $kickoff.away,
            $kickoff.home
        )
    }
}

if ($PlanOnly) {
    Write-Host ""
    Write-Host "PLAN ONLY - Windows Task Scheduler was not changed."
    exit 0
}

# Replace only LeagueLab's generated alert tasks for the target date.
# The permanent scheduler task and other dates are intentionally untouched.
$targetTaskPrefix = "$TaskPrefix$($plan.date) "
$existingTargetTasks = @(
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like "$targetTaskPrefix*" }
)

if ($existingTargetTasks.Count -gt 0) {
    $existingTargetTasks |
        Unregister-ScheduledTask -Confirm:$false

    Write-Host (
        "Replacing {0} existing LeagueLab alert task(s) for {1}." -f `
        $existingTargetTasks.Count,
        $plan.date
    )
}

$principal = New-LeagueLabPrincipal

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

foreach ($checkpoint in $plan.checkpoints) {
    $runAtOffset = [DateTimeOffset]::Parse($checkpoint.run_at)
    $runAt = $runAtOffset.LocalDateTime

    $minuteLabels = @(
        $checkpoint.kickoffs |
        ForEach-Object { "$($_.minutes_before)m" } |
        Sort-Object -Unique
    )
    $minuteLabel = $minuteLabels -join "-"

    $taskName = (
        "{0}{1} {2} W{3} {4}" -f `
        $TaskPrefix,
        $runAt.ToString("yyyy-MM-dd"),
        $runAt.ToString("HH-mm"),
        $plan.week,
        $minuteLabel
    )

    $logFile = (
        "$LogDir\roster_alert_{0}_{1}.log" -f `
        $runAt.ToString("yyyyMMdd"),
        $runAt.ToString("HHmm")
    )

    # Always refresh Yahoo explicitly.  In preview this lets us validate the
    # same data path used in production while preserving zero-send safety.
    $command = @"
`$env:PYTHONPATH = '$ProjectRoot\src'
Set-Location '$ProjectRoot'
'============================================================' | Out-File '$logFile' -Append
'Task started: ' + (Get-Date) | Out-File '$logFile' -Append
& '$Python' '$Runner' --season $($plan.season) --week $($plan.week) --mode '$Mode' --refresh-schedule --refresh-yahoo *>> '$logFile'
'Exit code: ' + `$LASTEXITCODE | Out-File '$logFile' -Append
'Task finished: ' + (Get-Date) | Out-File '$logFile' -Append
"@

    $encoded = ConvertTo-EncodedPowerShell $command

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand $encoded" `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -Once -At $runAt

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Force | Out-Null

    Write-Host "Created: $taskName"
}

Write-Host ""
Write-Host "Dynamic LeagueLab alert tasks installed successfully."
Write-Host "Mode: $Mode"
Write-Host "Log folder: $LogDir"
