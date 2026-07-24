$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".\venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Python venv not found: $Python. Run scripts/setup_local_windows.ps1 first."
    exit 1
}

if (-not $env:SHORTS_JOB_VISIBILITY) {
    $env:SHORTS_JOB_VISIBILITY = "unlisted"
}

$LogDir = Join-Path $RepoRoot ".mp\two_hour_job\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogDir "two_hour_short_job_$Timestamp.log"

Write-Host "ITShortPrinter two-hour Shorts job starting"
Write-Host "Repo: $RepoRoot"
Write-Host "Visibility: $env:SHORTS_JOB_VISIBILITY"
Write-Host "Log: $LogPath"

& $Python "scripts\run_two_hour_short_job.py" *>&1 | Tee-Object -FilePath $LogPath
exit $LASTEXITCODE
