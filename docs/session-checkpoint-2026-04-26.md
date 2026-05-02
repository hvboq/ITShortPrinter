# MoneyPrinterV2 Session Checkpoint — 2026-04-26

## Durable working location

Canonical project path:

```text
/opt/data/MoneyPrinterV2
```

This is inside the Docker volume and should survive host reboot/container restart. Do not continue work from `/root/MoneyPrinterV2`.

## Current code state

Modified files:

```text
config.example.json
src/classes/YouTube.py
src/config.py
src/constants.py
src/main.py
```

New files/directories:

```text
PERSISTENCE.md
docs/hermes-moneyprinterv2-workflow.md
docs/session-checkpoint-2026-04-26.md
src/news/
tests/test_local_ai_config.py
tests/test_news_fetcher.py
tests/test_news_shorts.py
tests/test_tech_news_ranker.py
tests/test_youtube_news_menu.py
```

## Implemented features

- Persistent project copy moved to `/opt/data/MoneyPrinterV2`.
- Project workflow/skill backup saved to `docs/hermes-moneyprinterv2-workflow.md`.
- Persistence rules saved to `PERSISTENCE.md`.
- Korean IT-news Shorts pipeline added:
  - RSS fetcher
  - news sources registry
  - article ranking
  - news-to-shorts prompt builder
  - top-ranked news collector
- YouTube menu now starts with `Create Top Ranked News Short`.
- `YouTube.generate_video_from_news(tts_instance, article)` integration added.
- Ollama default config uses `gemma4:e4b`.
- Gemini image API key fallback supports `GEMINI_API_KEY` and `GOOGLE_API_KEY`.
- `get_ollama_base_url()` now supports environment override via `OLLAMA_BASE_URL`.

## Config created

`config.json` exists under `/opt/data/MoneyPrinterV2/config.json`.

Important non-secret settings:

```json
{
  "firefox_profile": "/opt/data/firefox-profiles/youtube",
  "headless": false,
  "ollama_base_url": "http://host.docker.internal:11434",
  "ollama_model": "gemma4:e4b",
  "imagemagick_path": "/usr/bin/convert"
}
```

Reason: `internal.docker.host` did not resolve in the current container, while `host.docker.internal` worked and Ollama returned model tags successfully.

## Verified before stopping

Successful tests before dependency install attempts:

```text
Ran 9 tests total after adding OLLAMA_BASE_URL override test.
All passed.
```

Ollama connectivity:

```text
http://host.docker.internal:11434/api/tags OK
model gemma4:e4b present: true
```

Environment key presence checked without printing values:

```text
GOOGLE_API_KEY=SET
GEMINI_API_KEY=SET
OPENAI_API_KEY=SET
```

## Dependency/runtime state

System packages:

- `python3-pip`, `python3-venv`, and `imagemagick` installed successfully with apt.
- Attempted `firefox-esr` install twice, but Debian download was too slow and timed out. Firefox is not confirmed installed.

Python runtime:

- System Python is 3.13.5.
- MoneyPrinterV2 dependencies require Python `<3.13` because `kittentts`/`misaki` do not support Python 3.13.
- Installed `uv` and installed CPython 3.12.13.
- Created venv:

```text
/opt/data/MoneyPrinterV2/venv
```

Current venv status:

```text
Python 3.12.13
pip 26.0.1
```

`pip install -r requirements.txt` was attempted, but full install pulled very large TTS/CUDA-related dependency chains and was interrupted/timed out. A second partial install excluding `kittentts` was also interrupted while downloading large packages. Treat dependencies as incomplete.

## Known blockers / next actions

1. Do not run full Shorts generation until dependencies are complete.
2. Decide whether to keep KittenTTS or replace/abstract TTS to avoid huge `kittentts` dependency chain.
3. Finish installing only needed runtime deps, preferably avoiding GPU/CUDA-heavy packages if possible.
4. Install or provide Firefox/geckodriver if YouTube upload is required.
5. Create/copy logged-in Firefox profile to:

```text
/opt/data/firefox-profiles/youtube
```

6. Re-run tests from the canonical path:

```bash
cd /opt/data/MoneyPrinterV2
venv/bin/python -m unittest \
  tests/test_local_ai_config.py \
  tests/test_tech_news_ranker.py \
  tests/test_news_shorts.py \
  tests/test_news_fetcher.py \
  tests/test_youtube_news_menu.py -v
```

7. Recommended next technical step: add a TTS provider abstraction or a lightweight mock/offline TTS option so script/image/video pipeline can be smoke-tested without KittenTTS first.

## Stop state

No active pip/apt install process was running at checkpoint time. Only zombie defunct apt/dpkg helper processes were visible, which do not continue work.
