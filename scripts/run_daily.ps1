# Daily entrypoint for Windows Task Scheduler
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "$(Get-Date -Format 'yyyy-MM-dd').log"

function Write-LogLine {
    param([string]$Message)
    $line = "[$((Get-Date).ToString('o'))] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-LogLine "ERROR: .venv not found. Run: python -m venv .venv; pip install -e ."
    exit 1
}

. $VenvActivate

$env:MAIL_DIGEST_ROOT = $ProjectRoot

Write-LogLine "Starting Mail Digest run"

# Python setup_logging writes to the same daily log file; do not Tee-Object here or
# Windows will lock the file (FileHandler vs Out-File exclusive access).
python -m email_analyzer run 2>&1
$exitCode = $LASTEXITCODE

Write-LogLine "Finished with exit code $exitCode"
exit $exitCode
