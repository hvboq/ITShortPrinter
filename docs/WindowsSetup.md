# Windows Local Setup

Use this guide when developing ITShortPrinter on native Windows PowerShell.

## Prerequisites

- Windows 10 or newer
- Git
- [mise](https://mise.jdx.dev/getting-started.html) (recommended), or Python 3.12 available through the Windows launcher (`py -3.12`)
- FFmpeg available on `PATH` for audio/video rendering
- Optional: Ollama running at `http://127.0.0.1:11434` for local text generation
- Optional: ImageMagick for inherited workflows; current Shorts text overlays use Pillow
- Optional: Google Cloud OAuth Desktop client for YouTube API upload scripts

## Recommended mise setup

Run from the repository root:

```powershell
mise trust
mise install
mise run setup
mise run doctor
```

## PowerShell setup script

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1
```

The script will:

1. Create `config.json` from `config.example.json` when missing.
2. Create `.env` from `.env.example` when available and missing.
3. Create `.\venv` with Python 3.12.
4. Install `requirements.txt`.
5. Detect an optional `magick.exe` and Firefox profile path when possible.
6. Normalize `ollama_base_url` to `http://127.0.0.1:11434` for native Windows.
7. Run `scripts/preflight_local.py`.

Missing provider credentials or CLIs are reported by preflight but do not undo a
successful dependency installation. Configure `.env` and `config.json`, then run
`mise run doctor` or the preflight script again.

If `.\venv` already exists with the wrong Python version, recreate it:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1 -RecreateVenv
```

## Manual setup

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.json
Copy-Item .env.example .env
.\venv\Scripts\python.exe scripts\preflight_local.py
```

## Common commands

```powershell
.\venv\Scripts\python.exe src\main.py
.\venv\Scripts\python.exe scripts\fetch_tech_news.py
.\venv\Scripts\python.exe scripts\make_news_short.py
.\venv\Scripts\python.exe -m unittest discover -s tests
```

## Troubleshooting

### Python 3.12 was not found

Install Python 3.12 and confirm:

```powershell
py -3.12 --version
```

### Preflight reports missing API keys

Fill only your local `.env` or ignored `config.json`. Do not commit real API keys,
tokens, browser profiles, generated media, or `.mp/` runtime data.

### FFmpeg is not detected

Install FFmpeg, reopen PowerShell, and confirm:

```powershell
ffmpeg -version
```

ImageMagick is not required for the current Pillow-based subtitle and title
renderer. If an inherited workflow explicitly needs it, install ImageMagick and
confirm `magick -version`; the setup script intentionally does not fall back to
Windows' unrelated `convert.exe` utility.
