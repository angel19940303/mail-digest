# Register Windows Task Scheduler job for daily 6:00 PM run
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunScript = Join-Path $ProjectRoot "scripts\run_daily.ps1"
$TaskName = "EmailAnalyzerDaily"

if (-not (Test-Path $RunScript)) {
    Write-Error "Run script not found: $RunScript"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""

$Trigger = New-ScheduledTaskTrigger -Daily -At "6:00PM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Fetch Gmail, generate AI email report, post to Slack (rolling 24h window ending 6pm)" `
    -Force

Write-Host "Registered scheduled task: $TaskName (daily at 6:00 PM)"
Write-Host "Run script: $RunScript"
Write-Host "To test now: powershell -File `"$RunScript`""
