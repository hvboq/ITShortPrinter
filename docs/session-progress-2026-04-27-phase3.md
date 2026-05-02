# Session Progress — 2026-04-27, Phase 3

## Scope

This phase connected the previously verified layers into a browser-free, no-upload end-to-end smoke path:

```text
RSS/news ranking -> Ollama script/metadata/prompts -> image generation layer -> silent TTS WAV -> MoviePy MP4
```

The goal was not final production output quality. The goal was to prove the orchestration can create a local MP4 without Firefox/YouTube upload and without real TTS/Gemini credentials.

## Changes completed

### Browser-free local generation factory

Added to `src/classes/YouTube.py`:

```python
YouTube.for_local_generation(niche="IT News", language="Korean")
```

This creates a `YouTube` object without launching Firefox, installing GeckoDriver, or requiring a logged-in YouTube profile. It is for local MP4 generation and no-upload smoke tests.

### Configurable development image provider

Added to `src/config.py`:

```python
get_image_provider()
get_max_image_prompts()
```

Current local `config.json` smoke settings:

```json
"image_provider": "placeholder",
"max_image_prompts": 2,
"tts_provider": "silent"
```

`config.example.json` keeps production-oriented defaults:

```json
"image_provider": "gemini",
"max_image_prompts": 5,
"tts_provider": "kitten"
```

Important: `placeholder` is development-only. It allows end-to-end orchestration tests when Gemini keys are missing. Final production image generation remains Gemini.

### Placeholder image generation

Added to `src/classes/YouTube.py`:

```python
generate_placeholder_image(prompt)
```

This writes a simple 1080x1920 PNG to `.mp/` and appends it to `self.images`. `generate_image()` now routes based on `get_image_provider()`:

- `gemini` -> Gemini API via `generate_image_nanobanana2()`
- `placeholder` -> local placeholder PNG with an explicit warning
- unknown provider -> warn and fall back to Gemini

### Fixed Ollama model default inside YouTube generation

`YouTube.generate_response()` now passes the configured model when no model override is provided:

```python
generate_text(prompt, model_name=model_name or get_ollama_model())
```

This fixed the live no-upload E2E failure:

```text
RuntimeError: No Ollama model selected. Call select_model() first or pass model_name.
```

### Fixed image prompt explosion

`generate_prompts()` previously used:

```python
n_prompts = len(self.script) / 3
```

This could accidentally request hundreds of image prompts. It now uses:

```python
n_prompts = get_max_image_prompts()
```

and caps returned prompts accordingly.

## Tests added

```text
tests/test_local_no_upload_generation.py
tests/test_youtube_llm_defaults.py
```

These verify:

- local generation factory does not start Firefox
- placeholder image provider writes PNG without Gemini key
- image prompts are capped by config
- YouTube LLM calls use configured Ollama model by default

## Live no-upload E2E smoke result

Command path used:

```python
article = get_top_news()
youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
path = youtube.generate_video_from_news(TTS(), article)
```

Selected article:

```text
Huawei Pura X Max, Pura 90 Pro, Moto Edge 70 Pro are official, Week 17 in review
```

Ranking:

```text
SHORTS_SCORE=97
EVENT_TYPE=product_launch
```

Smoke settings:

```text
IMAGE_PROVIDER=placeholder
TTS_PROVIDER=silent
MAX_IMAGE_PROMPTS=2
```

Generated MP4:

```text
/opt/data/MoneyPrinterV2/.mp/07c6990a-457d-4c62-83c2-2327f6561360.mp4
```

Size:

```text
232,933 bytes
```

Generated image count:

```text
2
```

The run completed successfully. Subtitle generation still logs a missing `faster-whisper` warning, then continues without subtitles as intended.

## Full verification

Ran:

```bash
venv/bin/python -m py_compile src/config.py src/gemini_image.py src/classes/Tts.py src/classes/YouTube.py src/llm_provider.py src/news/ranker.py src/news/shorts.py src/news/fetcher.py src/news/collector.py src/main.py src/constants.py

venv/bin/python -m unittest tests/test_gemini_image_generation.py tests/test_moviepy_smoke.py tests/test_youtube_combine_smoke.py tests/test_local_no_upload_generation.py tests/test_youtube_llm_defaults.py tests/test_config_optional_deps.py tests/test_local_ai_config.py tests/test_tts_provider.py tests/test_tech_news_ranker.py tests/test_news_shorts.py tests/test_news_fetcher.py tests/test_youtube_news_menu.py -v
```

Result:

```text
Ran 20 tests in 1.133s
OK
```

## Current status

Working:

- News collection/ranking
- Korean IT news script generation via local Ollama
- Metadata and image prompt generation via local Ollama
- Browser-free no-upload generation object
- Placeholder image generation for smoke tests
- Silent TTS WAV
- MoviePy MP4 composition
- End-to-end local MP4 creation without upload

Still pending for production quality:

1. Provide `GOOGLE_API_KEY`/`GEMINI_API_KEY` or `nanobanana2_api_key`, then switch:
   ```json
   "image_provider": "gemini"
   ```
2. Run real Gemini image smoke test.
3. Replace silent TTS with real TTS.
4. Decide subtitle provider: install `faster-whisper` or switch to AssemblyAI.
5. Verify Firefox profile and YouTube upload.
6. Improve Korean metadata prompt quality. Current generated title can still be English/hype-style.
