# MoneyPrinterV2 Phase 6 — Korean subtitle fallback and overlay

## Problem

Generated videos had Korean Edge TTS audio but no visible subtitles.

Root causes found:

1. The default local STT subtitle path depends on `faster-whisper`, which is not installed in this lightweight container.
2. The old code caught the STT failure and continued without subtitles.
3. A first SRT fallback still failed visually because MoviePy `SubtitlesClip`/`TextClip` invoked ImageMagick text rendering, which is blocked by the container's ImageMagick security policy for `@/tmp/*.txt`.

## Fix

Implemented script-based subtitle fallback in `src/classes/YouTube.py`:

- `generate_safe_subtitles(audio_path, duration_seconds)` tries STT first.
- If STT fails, it falls back to `generate_subtitles_from_script()`.
- The fallback splits the Korean narration script into short SRT chunks distributed across the TTS duration.
- Subtitle rendering now uses Pillow to draw transparent subtitle images and MoviePy `ImageClip` overlays, avoiding ImageMagick `TextClip`.

Added tests:

- `tests/test_subtitle_fallback.py`
  - verifies Korean SRT fallback generation
  - verifies fallback when STT raises `ImportError("No module named 'faster_whisper'")`
  - verifies subtitle overlays are MoviePy `ImageClip`s, not ImageMagick text clips

## Verification

Command:

```bash
venv/bin/python -m py_compile src/classes/YouTube.py src/config.py \
  && venv/bin/python -m unittest \
    tests/test_subtitle_fallback.py \
    tests/test_edge_tts_provider.py \
    tests/test_tts_provider.py \
    tests/test_config_optional_deps.py -v
```

Result:

```text
Ran 6 tests in 0.329s
OK
```

Generated a new MP4 from the top-ranked IT article:

```text
/opt/data/MoneyPrinterV2/.mp/ff60a533-be23-4f49-b3d2-9b45f92fbd3a.mp4
```

Generated fallback SRT:

```text
/opt/data/MoneyPrinterV2/.mp/87a22a91-5481-4ada-9c86-3bcf514ce1f3.srt
```

Visual frame verification extracted a frame and confirmed Korean subtitle text is visible:

```text
화웨이가 새롭게 Pura X Max를
공개하며 큰 관심을 받고
```

## API key visibility note

The code supports both `GEMINI_API_KEY` and `GOOGLE_API_KEY` through `get_nanobanana2_api_key()`.

In the current running Hermes/MoneyPrinterV2 process environment, boolean-only checks showed:

```text
GOOGLE_API_KEY: not visible
OPENAI_API_KEY: not visible
GEMINI_API_KEY: not visible
Gemini getter: false
```

No key values were printed or stored.

If keys were supplied at Docker run time, the current container/session may not have received them, or the process may need to be restarted with the variables passed into this same container. Until the key is visible and `image_provider` is `gemini`, the local pipeline remains on `placeholder` images.
