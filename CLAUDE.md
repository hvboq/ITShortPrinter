# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MoneyPrinterV2 (MPV2) is a Python 3.12 CLI tool that automates four online workflows:
1. **YouTube Shorts** — generate video (LLM script → TTS → images → MoviePy composite) and upload via Selenium
2. **Twitter/X Bot** — generate and post tweets via Selenium
3. **Affiliate Marketing** — scrape Amazon product info, generate pitch, share on Twitter
4. **Local Business Outreach** — scrape Google Maps (Go binary), extract emails, send cold outreach via SMTP

There is no web UI and no REST API. There is a `unittest`-based test suite under
`tests/` (run with `python -m unittest discover -s tests`); there is no linting
config. CI is configured under `.github/workflows/` to run the test suite.

## Running the Application

```bash
# First-time setup
cp config.example.json config.json   # then fill in values
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# macOS quick setup (auto-configures Ollama, ImageMagick, Firefox profile)
bash scripts/setup_local.sh

# Preflight check (validates services are reachable)
python scripts/preflight_local.py

# Run
python src/main.py
```

The app **must** be run from the project root. `python src/main.py` adds `src/` to `sys.path`, so all imports use bare module names (e.g., `from config import *`, not `from src.config import *`).

## Architecture

### Entry Points
- `src/main.py` — interactive menu loop (primary)
- `src/cron.py` — headless runner invoked by the scheduler as a subprocess: `python src/cron.py <platform> <account_uuid>`

### Provider Pattern
Several service categories use a string-based dispatch pattern configured in `config.json`:

| Category | Config key | Options |
|---|---|---|
| Text/LLM | `text_provider` | `ollama` (local, via `ollama` SDK), `gemini` (Google Generative Language API when the model name starts with `gemini`), `hermes` (Hermes CLI, default `gpt-5.5`). If no Ollama model is selected, the user picks from available models at startup. |
| Image gen | `image_provider` | `gemini` / `nanobanana2` (Gemini image API, default), `hermes` (consumes images from `.mp/hermes_images/queue`), `placeholder` (smoke tests) |
| TTS | `tts_provider` | `kitten` (KittenTTS, default), `silent` (smoke tests) |
| STT | `stt_provider` | `local_whisper`, `third_party_assemblyai` |

Text generation is routed by `text_provider` / the selected model name (see
`src/llm_provider.py::generate_text`). Image generation defaults to Nano Banana 2.

### Key Modules
- **`src/llm_provider.py`** — unified `generate_text(prompt)` that routes to Ollama, Gemini, or Hermes based on `text_provider`/model name
- **`src/config.py`** — 30+ getter functions over `config.json`. `load_config()` is cached and invalidated on the file's mtime, so getters don't re-parse on every call. `ROOT_DIR` = project root
- **`src/cache.py`** — JSON file persistence in `.mp/` directory (accounts, videos, posts, products)
- **`src/constants.py`** — menu strings, Selenium selectors (YouTube Studio, X.com, Amazon)
- **`src/classes/YouTube.py`** — most complex class; full pipeline: topic → script → metadata → image prompts → images → TTS → subtitles → MoviePy combine → Selenium upload
- **`src/classes/Twitter.py`** — Selenium automation against x.com
- **`src/classes/AFM.py`** — Amazon scraping + LLM pitch generation
- **`src/classes/Outreach.py`** — Google Maps scraper (requires Go) + email sending via yagmail
- **`src/classes/Tts.py`** — KittenTTS wrapper

### Data Storage
All persistent state lives in `.mp/` at the project root as JSON files (`youtube.json`, `twitter.json`, `afm.json`). This directory also serves as scratch space for temporary WAV, PNG, SRT, and MP4 files — non-JSON files are cleaned on each run by `rem_temp_files()`.

### Browser Automation
Selenium uses pre-authenticated Firefox profiles (never handles login). The profile path is stored per-account in the cache JSON and also in `config.json` as a default.

### CRON Scheduling
Uses Python's `schedule` library (in-process, not OS cron). The scheduled job spawns `subprocess.run(["python", "src/cron.py", platform, account_id])`.

## Configuration

All config lives in `config.json` at the project root. See `config.example.json` for the full template and `docs/Configuration.md` for reference. Key external dependencies to configure:
- **ImageMagick** — required for MoviePy subtitle rendering (`imagemagick_path`)
- **Firefox profile** — must be pre-logged-in to target platforms (`firefox_profile`)
- **Ollama** — for LLM text generation (via `ollama` Python SDK)
- **Nano Banana 2** — for image generation (Gemini image API)
- **Go** — only needed for Outreach (Google Maps scraper)

## Contributing

PRs go against `main`. One feature/fix per PR. Open an issue first. Use `WIP` label for in-progress PRs.

## Working Agreement for Claude

- **Always commit and push to `main` after making changes** in this repository.
  Whenever you modify files here, create a commit and push it to `origin/main`
  (rebase onto the latest `origin/main` first if the push is rejected). Do not
  leave changes uncommitted.
