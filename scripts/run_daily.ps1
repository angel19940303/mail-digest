# Daily entrypoint for Windows Task Scheduler
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "$(Get-Date -Format 'yyyy-MM-dd').log"

$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    "[$((Get-Date).ToString('o'))] ERROR: .venv not found. Run: python -m venv .venv; pip install -e ." |
        Tee-Object -FilePath $LogFile -Append
    exit 1
}

. $VenvActivate

$env:MAIL_DIGEST_ROOT = $ProjectRoot

"[$((Get-Date).ToString('o'))] Starting Mail Digest run" | Tee-Object -FilePath $LogFile -Append

python -m email_analyzer run --non-interactive 2>&1 | Tee-Object -FilePath $LogFile -Append
$exitCode = $LASTEXITCODE

"[$((Get-Date).ToString('o'))] Finished with exit code $exitCode" | Tee-Object -FilePath $LogFile -Append
exit $exitCode
