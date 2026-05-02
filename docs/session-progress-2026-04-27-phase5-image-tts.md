# Session Progress — 2026-04-27 Phase 5 Image/TTS Production Path

## User Request

- Add image generation and TTS.
- Explain why previous output appeared English.

## Findings

Runtime config before changes:

```text
IMAGE_PROVIDER=placeholder
TTS_PROVIDER=silent
GEMINI_KEY_PRESENT=False
ENV_GOOGLE_PRESENT=False
ENV_GEMINI_PRESENT=False
GEMINI_MODEL=gemini-3.1-flash-image-preview
OLLAMA_MODEL=gemma4:e4b
```

The previous video looked partly English for two reasons:

1. Source news titles from GSM Arena/Android Authority/9to5Mac are English and were reported as original article titles.
2. The development placeholder image used the English overlay text `IT NEWS SMOKE TEST`.

The generated script/metadata path had already been moved toward Korean, but the placeholder image overlay still needed Korean text.

## Code Changes

- `src/classes/Tts.py`
  - Added `tts_provider: "edge"` support using `edge-tts`.
  - Default Korean voice for this provider: `ko-KR-SunHiNeural`.
  - Edge TTS output is saved as temporary MP3 and converted to PCM WAV via ffmpeg/imageio-ffmpeg so existing MoviePy pipeline remains compatible.
  - Existing providers preserved:
    - `silent` for local smoke tests.
    - `kitten` for original KittenTTS path.

- `requirements.txt`
  - Added `edge-tts`.

- `config.json`
  - Changed local runtime TTS config:

```json
"tts_provider": "edge",
"tts_voice": "ko-KR-SunHiNeural"
```

- `config.example.json`
  - Updated production example to include:

```json
"tts_provider": "edge",
"tts_voice": "ko-KR-SunHiNeural",
"image_provider": "gemini"
```

- `src/classes/YouTube.py`
  - Placeholder image overlay changed from English `IT NEWS SMOKE TEST` to Korean `IT 뉴스 쇼츠 테스트`.
  - Metadata prompts strengthened: product/brand names may keep original spelling, but explanatory text must be Korean; description prompt now forbids markdown/list-heavy output.

## Tests Added

- `tests/test_edge_tts_provider.py`
  - Verifies `tts_provider="edge"` uses Korean voice and converts provider audio to WAV.

## Verification

Installed lightweight TTS dependency:

```bash
. venv/bin/activate && python -m pip install edge-tts
```

Edge TTS smoke:

```text
AUDIO_PATH=/opt/data/MoneyPrinterV2/.mp/edge-tts-smoke.wav
AUDIO_SIZE=342222
DURATION=7.13
```

Full relevant tests:

```text
Ran 24 tests in 1.166s
OK
```

Generated a new latest-news short using:

```text
text: Ollama gemma4:e4b
TTS: edge / ko-KR-SunHiNeural
image_provider: placeholder because Gemini key is not present in runtime
```

Generated output:

```text
VIDEO_PATH=/opt/data/MoneyPrinterV2/.mp/0fafe3b5-08f2-4d6b-b672-038b9ed7a6c9.mp4
VIDEO_SIZE=778483
VIDEO_DURATION=40.23
VIDEO_SIZE_PIXELS=[1080, 1920]
VIDEO_FPS=30.0
AUDIO_DURATION=40.22
TTS_PATH=/opt/data/MoneyPrinterV2/.mp/a9974375-74a4-4f91-936e-9bd1c380254c.wav
TTS_SIZE=1930830
```

## Gemini Image Status

Gemini image module and Gemini unit tests exist and pass, but actual Gemini image generation is still blocked because no image API key is present in the current runtime:

```text
GEMINI_KEY_PRESENT=False
GOOGLE_API_KEY=False
GEMINI_API_KEY=False
config nanobanana2_api_key empty
```

Attempting the platform image-generation tool also failed because its backend key was absent:

```text
FAL_KEY environment variable not set
```

Therefore this phase produced a real Korean TTS video with placeholder images. To switch to real Gemini images, inject `GOOGLE_API_KEY` or `GEMINI_API_KEY` into the container or set `nanobanana2_api_key` in `config.json`, then switch:

```json
"image_provider": "gemini"
```

Do not log or store actual API key values.
