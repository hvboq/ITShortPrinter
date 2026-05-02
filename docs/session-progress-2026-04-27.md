# Session Progress — 2026-04-27

## Scope

Continued the MoneyPrinterV2 IT-news Shorts setup from the previous checkpoint, focusing on getting a lightweight, verifiable development/runtime path working before attempting full video generation.

## Completed

1. Confirmed work is continuing in the persistent canonical path:
   ```text
   /opt/data/MoneyPrinterV2
   ```

2. Added a configurable TTS provider layer in `src/classes/Tts.py`:
   - `tts_provider: "kitten"` keeps the original KittenTTS behavior.
   - `tts_provider: "silent"` writes a valid silent WAV file without importing `kittentts`.
   - This unblocks smoke tests and pipeline development while the heavy TTS dependencies remain optional.

3. Added config support:
   - `get_tts_provider()` in `src/config.py`.
   - `config.json` now uses:
     ```json
     "tts_provider": "silent"
     ```
   - `config.example.json` documents:
     ```json
     "tts_provider": "kitten"
     ```

4. Made `srt_equalizer` optional at import time:
   - `src/config.py` no longer imports `srt_equalizer` globally.
   - It imports `srt_equalizer` only inside `equalize_subtitles()`.
   - This allows Ollama/news/config functions to run without installing subtitle dependencies first.

5. Updated Ollama host defaults and docs to the actual working Docker/WSL hostname:
   ```text
   http://host.docker.internal:11434
   ```
   Historical note: `internal.docker.host` did not resolve in this container.

6. Installed the lightweight dependencies needed for news collection and Ollama smoke tests in the Python 3.12 venv:
   ```bash
   . venv/bin/activate && python -m pip install termcolor schedule requests prettytable ollama
   ```

7. Added tests:
   ```text
   tests/test_tts_provider.py
   tests/test_config_optional_deps.py
   ```

8. Verified syntax and tests:
   ```bash
   python3 -m py_compile src/config.py src/classes/Tts.py src/llm_provider.py src/news/ranker.py src/news/shorts.py src/news/fetcher.py src/news/collector.py src/main.py src/constants.py
   python3 -m unittest tests/test_config_optional_deps.py tests/test_local_ai_config.py tests/test_tts_provider.py tests/test_tech_news_ranker.py tests/test_news_shorts.py tests/test_news_fetcher.py tests/test_youtube_news_menu.py -v
   ```
   Result:
   ```text
   Ran 11 tests ... OK
   ```

9. Completed live news → prompt → local Ollama smoke test:
   - Selected article:
     ```text
     Huawei Pura X Max, Pura 90 Pro, Moto Edge 70 Pro are official, Week 17 in review
     ```
   - Shorts score:
     ```text
     97
     ```
   - Event type:
     ```text
     product_launch
     ```
   - Ollama base:
     ```text
     http://host.docker.internal:11434
     ```
   - Ollama model:
     ```text
     gemma4:e4b
     ```
   - Result: Ollama generated a Korean 3-sentence Shorts briefing successfully.

10. Patched the Hermes skill `moneyprinterv2-it-news-shorts` to replace the outdated `internal.docker.host` guidance with `host.docker.internal`.

## Current limitations

- Full `requirements.txt` is still not installed; heavy dependencies such as `kittentts`, `faster-whisper`, and `ctranslate2` remain pending.
- Full video generation is not verified yet because MoviePy/Image generation/TTS/subtitle/video composition dependencies are not fully installed.
- YouTube upload is not verified yet; it still depends on Firefox/Gecko/Selenium and a logged-in profile at:
  ```text
  /opt/data/firefox-profiles/youtube
  ```

## Recommended next step

Proceed in layers:

1. Add or verify a Gemini image-generation smoke test that writes one image file to `.mp/`.
2. Install only MoviePy/Pillow/ffmpeg-related requirements needed for local MP4 composition.
3. Run a local no-upload video-generation smoke test using `tts_provider: "silent"` first.
4. After MP4 creation works, switch back to `tts_provider: "kitten"` or another real TTS provider and solve TTS dependencies separately.
5. Only after local MP4 generation works, test Selenium/Firefox YouTube upload.
