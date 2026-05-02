# Restart handoff — Docker env injection for Gemini/OpenAI keys

## User intent

The user will inject API keys at Docker/container startup and restart the container. Do **not** store real key values in chat, docs, memory, or git.

Expected environment variables:

```text
GOOGLE_API_KEY=[REDACTED]
OPENAI_API_KEY=[REDACTED]
```

Optional equivalent Gemini variable also supported:

```text
GEMINI_API_KEY=[REDACTED]
```

For production Gemini image generation, also set either env or config:

```text
IMAGE_PROVIDER=gemini
```

If `IMAGE_PROVIDER` is not set, current local `config.json` may still use `image_provider: "placeholder"`.

## Code state saved before restart

Canonical project path:

```text
/opt/data/MoneyPrinterV2
```

Important recent changes:

1. `src/config.py`
   - Supports env fallback for Gemini key:
     - `GEMINI_API_KEY`
     - `GOOGLE_API_KEY`
   - Added lightweight `.env` loader for local file-based env, but the user now prefers Docker env injection.
   - `termcolor` import has fallback so config can be imported even if `termcolor` is missing.

2. `.gitignore`
   - Ignores `.env` and `.env.*`, except `.env.example`.

3. `.env.example`
   - Documents expected env names without real values.

4. `scripts/set_env_keys.py`
   - Created for optional local `.env` creation, but not required if Docker env injection is used.

5. `src/classes/YouTube.py`
   - Korean subtitle fallback implemented.
   - If `faster-whisper` is missing, script-based Korean SRT is generated.
   - Captions are rendered with Pillow-backed MoviePy `ImageClip` overlays to avoid ImageMagick `TextClip` security-policy failures.

6. `tests/test_subtitle_fallback.py`
   - Verifies SRT fallback and ImageClip subtitle overlay path.

## Verified before restart

Environment visibility check before user restart showed all false in the current container/session:

```text
GOOGLE_API_KEY: false
GEMINI_API_KEY: false
OPENAI_API_KEY: false
IMAGE_PROVIDER: false
config_nanobanana2_key_present: false
gemini_getter_would_be_present: false
effective_image_provider: placeholder
```

This is why live Gemini image generation was still blocked before restart.

Subtitle/TTS video was verified working:

```text
/opt/data/MoneyPrinterV2/.mp/ff60a533-be23-4f49-b3d2-9b45f92fbd3a.mp4
```

Fallback SRT:

```text
/opt/data/MoneyPrinterV2/.mp/87a22a91-5481-4ada-9c86-3bcf514ce1f3.srt
```

Visual verification confirmed Korean subtitles on a frame:

```text
화웨이가 새롭게 Pura X Max를
공개하며 큰 관심을 받고
```

## After restart — next checks

Run from repo root:

```bash
cd /opt/data/MoneyPrinterV2
python3 - <<'PY'
import os, json
names = ['GOOGLE_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'IMAGE_PROVIDER']
print(json.dumps({name: bool(os.environ.get(name)) for name in names}, indent=2))
PY
```

Then verify MoneyPrinterV2 config getter without printing secrets:

```bash
cd /opt/data/MoneyPrinterV2
PYTHONPATH=src python3 - <<'PY'
from config import get_nanobanana2_api_key, get_image_provider
print('GEMINI_GETTER_PRESENT=' + str(bool(get_nanobanana2_api_key())))
print('IMAGE_PROVIDER=' + get_image_provider())
PY
```

Expected after successful env injection:

```text
GOOGLE_API_KEY or GEMINI_API_KEY: true
OPENAI_API_KEY: true
GEMINI_GETTER_PRESENT=True
IMAGE_PROVIDER=gemini
```

If `IMAGE_PROVIDER` remains `placeholder`, either pass `IMAGE_PROVIDER=gemini` at Docker run time or update `config.json` `image_provider` to `gemini`.

## Note about venv

A later check showed `/opt/data/MoneyPrinterV2/venv/bin/python` was missing/non-executable even though some `venv/` files remain. If the restarted container needs full video generation and the venv is broken, recreate or reinstall the light dependencies before running E2E:

```bash
cd /opt/data/MoneyPrinterV2
python3 -m venv venv
. venv/bin/activate
python -m pip install termcolor schedule requests prettytable ollama edge-tts moviepy==1.0.3 'Pillow>=10.0.0' imageio-ffmpeg
```

Avoid full `requirements.txt` unless necessary, because heavy ML/audio packages previously stalled or were killed.
