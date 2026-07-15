# ITShortPrinter

Korean IT-news Shorts automation fork based on
[FujiwaraChoki/MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2).

This project collects recent tech news, ranks Shorts-friendly topics, generates
Korean narration scripts, creates vertical video assets, renders a YouTube
Short, and optionally uploads or cross-posts the result.

> Fork / license notice: this repository is a customized fork of the original
> MoneyPrinterV2 project. The upstream project is licensed under AGPL-3.0, and
> this fork keeps that license. See [LICENSE](LICENSE).

Sponsored by Post Bridge

<a href="https://www.post-bridge.com/?ref=moneyprinter">
  <img src="docs/repo/PostBridgeBanner.png" alt="Post Bridge integration banner" width="720" />
</a>

## What This Fork Does

- Collects and ranks tech-news candidates from configured sources.
- Generates Korean YouTube Shorts scripts, metadata, thumbnails, and visual prompts.
- Uses local or configured LLM providers for text generation.
- Uses Gemini image generation by default, with placeholder image support for smoke tests.
- Generates TTS audio, subtitles, title overlays, and vertical Shorts video files.
- Supports batch Top 5 generation with a manifest and review frames.
- Supports YouTube Data API uploads through OAuth.
- Can optionally hand uploaded Shorts to Post Bridge for TikTok and Instagram cross-posting.
- Keeps inherited MoneyPrinterV2 Twitter, affiliate marketing, and outreach flows.

## Project Layout

```text
src/main.py                    Interactive CLI entrypoint
src/news/                      Lightweight news collection and ranking helpers
src/news_pipeline.py           Advanced tech-news crawler, parser, and scorer
src/classes/YouTube.py         YouTube orchestration and upload workflow
src/classes/youtube_*.py       Video composition, subtitles, visuals, and content helpers
scripts/setup_local.sh         Linux/macOS Python 3.12 bootstrap and preflight
scripts/setup_local_windows.ps1 Windows PowerShell Python 3.12 bootstrap and preflight
scripts/preflight_local.py     Local readiness checks
scripts/generate_top5_shorts.py
scripts/upload_top5_shorts.py
scripts/upload_top5_public_shorts.py
docs/                          Configuration and workflow notes
config.example.json            Safe example config
```

Runtime outputs, generated media, manifests, and local account caches are written
under `.mp/`. Do not commit real `.mp/` data.

## Requirements

- Python 3.12
- A virtual environment named `venv`
- ImageMagick for MoviePy subtitle/title rendering
- A text model provider:
  - local Ollama, or
  - Gemini-compatible model configuration
- Gemini or Google API key when `image_provider` is `gemini`
- A Google Cloud OAuth Desktop client authorized for YouTube uploads

Optional features may need extra setup:

- `faster-whisper` for local subtitle transcription
- AssemblyAI API key if using third-party STT
- Post Bridge API key for cross-posting
- Go toolchain for inherited outreach scraping workflows

## Quick Start

Run these commands from the repository root.

### mise (recommended)

Install [mise](https://mise.jdx.dev/getting-started.html), then run:

```bash
mise trust
mise install
mise run setup
```

`mise` installs the required Python 3.12 runtime, creates and activates the
project's `venv`, and delegates the remaining setup to the appropriate Windows
or Linux/macOS bootstrap script. The setup creates local `config.json` and
`.env` files when they are missing; add real credentials only to those ignored
files.

After setup, common workflows no longer require manually activating `venv`:

```bash
mise run app
mise run preflight
mise run test
mise run fetch-news
mise run make-short
mise run generate-top5
```

Run `mise tasks` to see every available command. `mise run deps` updates only
the Python packages without changing local configuration.

### Windows PowerShell

```powershell
git clone https://github.com/hvboq/ITShortPrinter.git
cd ITShortPrinter

powershell -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1
```

If an existing virtual environment was created with the wrong Python version:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_local_windows.ps1 -RecreateVenv
```

The Windows setup script copies `config.example.json` to `config.json`, copies
`.env.example` to `.env` when available, creates `.\venv` with Python 3.12,
installs requirements, applies Windows-friendly config defaults, and runs the
local preflight check.

Manual Windows setup is also supported:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe scripts\preflight_local.py
```

### Linux/macOS

```bash
git clone https://github.com/hvboq/ITShortPrinter.git
cd ITShortPrinter

cp config.example.json config.json
cp .env.example .env

bash scripts/setup_local.sh
```

If an existing virtual environment was created with the wrong Python version:

```bash
RECREATE_VENV=1 bash scripts/setup_local.sh
```

Manual Linux/macOS setup is also supported:

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python scripts/preflight_local.py
```

## Configuration

The main source of truth is `config.json`.

Start from `config.example.json`, then review these values first:

- `ollama_base_url` and `ollama_model`
- `image_provider`
- `nanobanana2_api_key`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY`
- `tts_provider` and `tts_voice`
- `stt_provider`, `whisper_model`, `whisper_device`, and `whisper_compute_type`
- `imagemagick_path`
- `firefox_profile` and `headless`
- `news_pipeline`
- `post_bridge`

Secrets can live in `.env`; keep `.env` and real `config.json` values out of git.
See [docs/Configuration.md](docs/Configuration.md) for the full config reference.

## Common Commands

Run the interactive CLI:

```bash
source venv/bin/activate
python src/main.py
```

Validate the local environment:

```bash
source venv/bin/activate
python scripts/preflight_local.py
```

Fetch and print ranked tech-news candidates:

```bash
source venv/bin/activate
python scripts/fetch_tech_news.py
```

Generate one news Short from ranked or cached news:

```bash
source venv/bin/activate
python scripts/make_news_short.py
```

Generate a batch of five Shorts:

```bash
source venv/bin/activate
python scripts/generate_top5_shorts.py
```

Limit source candidates or exclude terms during batch generation:

```bash
NEWS_LIMIT=30 EXCLUDE_TERMS="lawsuit|earnings|rumor" python scripts/generate_top5_shorts.py
```

Batch outputs are written to:

```text
.mp/batch_top5/manifest.json
.mp/batch_top5/frame_rank*.png
```

## Upload Workflow

YouTube upload automation uses the official YouTube Data API. Before uploading,
confirm the generated MP4s, metadata, and review frames in `.mp/batch_top5/`.
Scheduled cron uploads follow the same API-only path and do not depend on Firefox/Selenium profile locks.

First authorize a Google Cloud OAuth Desktop client with the upload scope:

```bash
source venv/bin/activate
python scripts/setup_youtube_oauth.py
```

If an older read-only OAuth token exists, delete
`secrets/youtube_oauth_token.json` and rerun the setup script.

Upload generated Top 5 Shorts as unlisted:

```bash
source venv/bin/activate
python scripts/upload_top5_shorts.py
```

Upload generated Top 5 Shorts as public:

```bash
source venv/bin/activate
python scripts/upload_top5_public_shorts.py
```

Control the public upload rank range:

```bash
START_RANK=2 END_RANK=4 python scripts/upload_top5_public_shorts.py
```

The upload scripts write manifests under `.mp/batch_top5/`.
Treat these as operational logs, not source files.

## Post Bridge Cross-Posting

Post Bridge is optional. When enabled, the project can upload the generated video
to Post Bridge after a successful YouTube upload and publish it to configured
TikTok or Instagram accounts.

Start with:

- [docs/PostBridge.md](docs/PostBridge.md)
- `post_bridge` in `config.json`
- `POST_BRIDGE_API_KEY` in `.env` or your shell environment

## Testing And Validation

There is no strict coverage gate yet, but the repo has unit tests. Use these
checks before committing code changes:

```bash
source venv/bin/activate
python -m unittest discover -s tests
python scripts/preflight_local.py
```

For documentation-only changes, a quick sanity check is usually enough:

```bash
git diff --check
```

## Operational Notes

- Generate locally first; upload only after checking the manifest and preview frames.
- Use `image_provider=placeholder` only for smoke tests, not production uploads.
- Keep YouTube Studio automation conservative because the web UI changes often.
- If upload fails, inspect screenshots in `.mp/batch_top5/upload_screens/`.
- If the wrong YouTube channel is active, the upload scripts should abort instead of posting.

## More Documentation

- [docs/Configuration.md](docs/Configuration.md)
- [docs/WindowsSetup.md](docs/WindowsSetup.md)
- [docs/YouTube.md](docs/YouTube.md)
- [docs/PostBridge.md](docs/PostBridge.md)
- [docs/Roadmap.md](docs/Roadmap.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Keep PRs focused, open them against
`main`, and avoid committing generated media, cache data, credentials, browser
profiles, or local manifests.

## License And Attribution

This fork is based on
[FujiwaraChoki/MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2).
MoneyPrinterV2 is licensed under the GNU Affero General Public License v3.0.
This fork preserves that license; see [LICENSE](LICENSE) for the full text.

If you run a modified version as a network service, review the AGPL-3.0
source-code availability obligations.

## Disclaimer

This project is for educational and operational experimentation purposes. Review
all generated content, account actions, and uploads before publishing.
