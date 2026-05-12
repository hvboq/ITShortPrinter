---
source: hermes-skill-backup
skill: moneyprinterv2-it-news-shorts
canonical_skill_path: /opt/data/skills/software-development/moneyprinterv2-it-news-shorts/SKILL.md
updated: 2026-04-26
---

# MoneyPrinterV2 IT News Shorts Customization

This file is a durable project-local backup of the Hermes skill used for this repository. Keep this under `/opt/data/MoneyPrinterV2/docs/` so the workflow survives even if the Hermes skill index is unavailable.

Use this when working on `FujiwaraChoki/MoneyPrinterV2` for the Korean IT-news Shorts workflow.

## User-specific target architecture

- Channel purpose: latest IT/device/technology news summarized for trend awareness and curiosity.
- CTA: use subscription only. Do not use “save this video” CTA.
- Avoid forced series framing unless explicitly requested.
- Text generation: local Ollama on host, model `gemma4:26b` for higher-quality Shorts scripts and analysis when available.
- Docker container accesses host Ollama at `http://host.docker.internal:11434` in the current Hermes/WSL environment when using the `ollama` Python SDK.
- Historical note: `internal.docker.host` was an earlier assumption, but in this container it did not resolve. Prefer `host.docker.internal` unless a future environment proves otherwise.
- Important URL distinction:
  - `ollama.Client(...).chat()` expects base host like `http://host.docker.internal:11434` without `/v1`.
  - OpenAI-compatible SDK calls expect `http://host.docker.internal:11434/v1`.
- Image generation/thumbnail visuals: Gemini API, not local GPU/diffusers.
- Environment keys may be named `GOOGLE_API_KEY` or `GEMINI_API_KEY`; code should support both.

## Persistent storage rules

The Hermes Docker volume is mounted at:

```text
/opt/data
```

Therefore durable project files must live under:

```text
/opt/data/MoneyPrinterV2
```

Avoid relying on:

```text
/root/MoneyPrinterV2
```

because `/root` is container writable-layer storage and may disappear when the container is recreated.

Important durable locations:

```text
/opt/data/MoneyPrinterV2                         # canonical repo working copy
/opt/data/skills/software-development/...        # Hermes skills
/opt/data/MoneyPrinterV2/docs/                   # project-local backups of workflow notes
/opt/data/firefox-profiles/youtube               # logged-in Firefox profile for YouTube upload
```

If work was accidentally done in `/root/MoneyPrinterV2`, copy it into the volume before finishing:

```bash
mkdir -p /opt/data
rm -rf /opt/data/MoneyPrinterV2
cp -a /root/MoneyPrinterV2 /opt/data/MoneyPrinterV2
git -C /opt/data/MoneyPrinterV2 status --short
```

## MoneyPrinterV2 current Shorts pipeline

Primary files:

- `src/main.py`: CLI entry point; YouTube Shorts option constructs `YouTube` and calls generation/upload flows.
- `src/classes/YouTube.py`: core Shorts pipeline.
- `src/classes/Tts.py`: KittenTTS local speech generation.
- `src/llm_provider.py`: Ollama text-generation wrapper.
- `src/config.py`: config getters.
- `config.example.json`: default config template.

`YouTube.generate_video()` flow:

1. `generate_topic()`
2. `generate_script()`
   - After the first script draft is generated, run one local Ollama review pass with `gemma4:26b` before metadata/TTS/video generation.
   - Config keys: `script_review_enabled=true`, `script_review_model="gemma4:26b"`.
   - Save review artifacts under `.mp/script_reviews/` for daily batch quality review.
3. `generate_metadata()`
4. `generate_prompts()`
5. `generate_image(prompt)` for each prompt
6. `generate_script_to_speech(tts_instance)`
7. `combine()`

Current video composition in `combine()`:

- Uses MoviePy locally to combine generated images, TTS audio, optional subtitles, and background music into 1080x1920 MP4.
- YouTube upload uses Selenium + logged-in Firefox profile.

## News Shorts integration pattern

MoneyPrinterV2 is originally a generic niche-to-video generator. For news-based Shorts, use a front-end news/ranking layer before script generation.

Implemented/minimum module layout:

```text
src/news/__init__.py
src/news/sources.py      # PHASE_1_SOURCES RSS registry
src/news/fetcher.py      # parse_rss(), fetch_rss()
src/news/ranker.py       # score_article(), rank_articles()
src/news/collector.py    # collect_ranked_news(), get_top_news()
src/news/shorts.py       # build_shorts_script_prompt()
```

Minimum workflow:

1. Fetch RSS/Google News RSS/HTML from IT sources.
2. Normalize articles to fields such as source, title, URL, published time, excerpt, source tier, brands, technologies, event type, rumor status.
3. Score using:
   - popularity: broad user relevance / brand scale / device category
   - feasibility: launched, completed research, patent registered, production, official announcement > early research/plans
   - LLM-like importance: model-style judgment of relevance and importance
   - Shorts virality: visual impact, surprising numbers, practical impact, controversy/curiosity
4. Select the highest-ranked item.
5. Inject selected news into `YouTube` via `generate_video_from_news(tts_instance, article)`.
6. Use Korean news-briefing script constraints:
   - 45–60 seconds
   - explain what happened and why it matters
   - distinguish rumor from official news
   - include only subscription CTA
   - no save CTA
   - no artificial “next episode” dependency

## Recommended implementation strategy

- Do not replace MoviePy with Gemini video generation initially. Use Gemini for images/visuals and MoviePy for final MP4 assembly; this is more deterministic for YouTube Shorts files.
- Start with generated MP4 only before automating YouTube upload, because Selenium upload requires a Docker-accessible logged-in Firefox profile.
- For upload, verify Firefox profile path, headless mode, and YouTube Studio DOM selectors.

## YouTube Firefox profile setup

Use a copied Firefox profile under the persistent volume:

```text
/opt/data/firefox-profiles/youtube
```

When MoneyPrinterV2 asks:

```text
=> Enter the path to the Firefox profile:
```

enter:

```text
/opt/data/firefox-profiles/youtube
```

Do not rely on a profile path under `/root`.

## Tests that should exist

```text
tests/test_local_ai_config.py   # Ollama host/model + Gemini/Google key fallback
tests/test_news_fetcher.py      # RSS XML -> normalized article dict
tests/test_tech_news_ranker.py  # official launch ranks high; rumors never alert; brand false positives avoided
tests/test_news_shorts.py       # prompt enforces news briefing, no save CTA, subscription CTA only
tests/test_youtube_news_menu.py # YouTube menu exposes ranked-news Shorts as the first option
```

Known pitfall: do not match the brand `Nothing` on the generic word `nothing`; restrict it to high-signal aliases such as `Nothing Phone`, `Nothing OS`, `CMF`, `Glyph`, and `낫싱`.

## Validation checklist

- Code changes live under `/opt/data/MoneyPrinterV2`, not only `/root/MoneyPrinterV2`.
- `config.json` exists and has Ollama host/model configured.
- Container can reach host Ollama:

```bash
curl http://host.docker.internal:11434/api/tags
```

- `gemma4:26b` is pulled on host Ollama for the quality-first workflow; `gemma4:e4b` remains a lightweight fallback.
- `GOOGLE_API_KEY` or `GEMINI_API_KEY` is visible inside the container.
- Gemini image call returns image bytes and writes into `.mp/`.
- `.mp/` exists.
- ImageMagick path is valid for MoviePy `TextClip`.
- ffmpeg/MoviePy can write MP4.
- TTS model can download/run.
- STT provider is configured: local faster-whisper or AssemblyAI.

Run syntax/tests after edits:

```bash
cd /opt/data/MoneyPrinterV2
python3 -m py_compile \
  src/config.py \
  src/news/ranker.py \
  src/news/shorts.py \
  src/news/fetcher.py \
  src/news/collector.py \
  src/classes/YouTube.py

python3 -m unittest \
  tests/test_local_ai_config.py \
  tests/test_tech_news_ranker.py \
  tests/test_news_shorts.py \
  tests/test_news_fetcher.py \
  tests/test_youtube_news_menu.py -v
```
