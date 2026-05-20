#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap ITShortPrinter on native Windows PowerShell.

.DESCRIPTION
  Creates config.json/.env from examples, creates a Python 3.12 virtual
  environment at .\venv, installs requirements, applies a few Windows-friendly
  config defaults, then runs scripts/preflight_local.py.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1 -RecreateVenv
#>

param(
    [switch]$RecreateVenv,
    [string]$Python = "",
    [string]$VenvDir = "venv"
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RootDir

$RequiredPythonVersion = "3.12"
$VenvPath = Join-Path $RootDir $VenvDir
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

function Write-Step([string]$Message) {
    Write-Host "[setup] $Message"
}

function Get-PythonMinorVersion([string]$PythonExe) {
    try {
        return (& $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") 2>$null
    }
    catch {
        return ""
    }
}

function Resolve-Python312 {
    $candidates = @()

    if ($Python) {
        $candidates += $Python
    }

    # Preferred Windows launcher path. Keep this literal for docs/tests: py -3.12
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $version = (& py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") 2>$null
            if ($version -eq $RequiredPythonVersion) {
                return @{ Command = "py"; Args = @("-3.12") }
            }
        }
        catch {
            # Keep checking explicit python executables below.
        }
    }

    foreach ($name in @("python3.12", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $candidates += $cmd.Source
        }
    }

    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        $version = Get-PythonMinorVersion $candidate
        if ($version -eq $RequiredPythonVersion) {
            return @{ Command = $candidate; Args = @() }
        }
    }

    throw "Python $RequiredPythonVersion was not found. Install Python 3.12 from python.org or winget, then rerun this script."
}

function Invoke-Python($PythonSpec, [string[]]$Arguments) {
    & $PythonSpec.Command @($PythonSpec.Args + $Arguments)
}

Write-Step "Root: $RootDir"

if (-not (Test-Path "config.json")) {
    Copy-Item "config.example.json" "config.json"
    Write-Step "Created config.json from config.example.json"
}

if ((Test-Path ".env.example") -and -not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Step "Created .env from .env.example"
}

if ((Test-Path $VenvPython) -and $RecreateVenv) {
    Write-Step "Removing existing $VenvDir because -RecreateVenv was passed"
    Remove-Item -Recurse -Force $VenvPath
}

if (Test-Path $VenvPython) {
    $existingVersion = Get-PythonMinorVersion $VenvPython
    if ($existingVersion -ne $RequiredPythonVersion) {
        throw "Existing $VenvDir uses Python $existingVersion, but this project requires $RequiredPythonVersion. Rerun with -RecreateVenv."
    }
}
else {
    $pythonSpec = Resolve-Python312
    Write-Step "Creating virtual environment at $VenvDir"
    Invoke-Python $pythonSpec @("-m", "venv", $VenvDir)
}

Write-Step "Using venv Python: $VenvPython"
& $VenvPython -m ensurepip --upgrade | Out-Null
& $VenvPython -m pip install --upgrade pip setuptools wheel
& $VenvPython -m pip install -r requirements.txt

$magickPath = ""
$magickCommand = Get-Command magick -ErrorAction SilentlyContinue
if ($magickCommand) {
    $magickPath = $magickCommand.Source
}
else {
    $convertCommand = Get-Command convert -ErrorAction SilentlyContinue
    if ($convertCommand) {
        $magickPath = $convertCommand.Source
    }
}

$firefoxProfile = ""
$profileRoot = Join-Path $env:APPDATA "Mozilla\Firefox\Profiles"
if (Test-Path $profileRoot) {
    $defaultProfile = Get-ChildItem $profileRoot -Directory -Filter "*default-release*" | Select-Object -First 1
    if (-not $defaultProfile) {
        $defaultProfile = Get-ChildItem $profileRoot -Directory | Select-Object -First 1
    }
    if ($defaultProfile) {
        $firefoxProfile = $defaultProfile.FullName
    }
}

$ConfigPath = Join-Path $RootDir "config.json"
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

if ($magickPath) {
    $config.imagemagick_path = $magickPath
}

if ($firefoxProfile -and -not $config.firefox_profile) {
    $config.firefox_profile = $firefoxProfile
}

if (-not $config.ollama_base_url -or $config.ollama_base_url -eq "http://host.docker.internal:11434") {
    $config.ollama_base_url = "http://127.0.0.1:11434"
}

if (-not $config.tts_provider) {
    $config | Add-Member -NotePropertyName "tts_provider" -NotePropertyValue "edge" -Force
}

$config | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $ConfigPath
Write-Step "Updated config.json with Windows-friendly defaults"

Write-Step "Running local preflight..."
& $VenvPython "scripts/preflight_local.py"
$preflightExit = $LASTEXITCODE

Write-Host ""
if ($preflightExit -eq 0) {
    Write-Step "Done. Start app with: .\venv\Scripts\python.exe src\main.py"
}
else {
    Write-Step "Setup finished, but preflight found blocking items. Fix config/API/provider values, then rerun: .\venv\Scripts\python.exe scripts\preflight_local.py"
    exit $preflightExit
}
