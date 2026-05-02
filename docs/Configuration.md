# Configuration

All your configurations live in a root-level `config.json`, which starts as a copy of `config.example.json`. Update the values in `config.json` for your local environment.

## Values

- `verbose`: `boolean` - If `true`, the application prints more information.
- `firefox_profile`: `string` - Path to your Firefox profile so the app can reuse your logged-in social accounts.
- `headless`: `boolean` - If `true`, the browser runs without a visible window.
- `ollama_base_url`: `string` - Base URL of your local Ollama server. Default: `http://127.0.0.1:11434`.
- `ollama_model`: `string` - Text model to use for generation. Recommended for this repo: `gemma4:e4b`. Local Ollama models such as `gemma4:26b` are supported, and Gemini models such as `gemini-2.5-flash` can also be used when needed. If empty, the app queries Ollama and lets you choose interactively.
- `twitter_language`: `string` - Language used for tweet generation and posting.
- `nanobanana2_api_base_url`: `string` - Nano Banana 2 API base URL. Default: `https://generativelanguage.googleapis.com/v1beta`.
- `nanobanana2_api_key`: `string` - API key for Nano Banana 2. If empty, MPV2 falls back to `GEMINI_API_KEY`.
- `nanobanana2_model`: `string` - Nano Banana 2 model name. Default: `gemini-3.1-flash-image-preview`.
- `nanobanana2_aspect_ratio`: `string` - Aspect ratio for generated images. Default: `9:16`.
- `threads`: `number` - Number of worker threads for operations such as video rendering.
- `is_for_kids`: `boolean` - If `true`, uploaded videos are marked as made for kids.
- `google_maps_scraper`: `string` - URL to the Google Maps scraper archive.
- `zip_url`: `string` - URL to the ZIP archive containing music assets.
- `email`: `object` - SMTP settings for email-based flows.
- `google_maps_scraper_niche`: `string` - Business niche for Google Maps scraping.
- `scraper_timeout`: `number` - Timeout for the Google Maps scraper.
- `outreach_message_subject`: `string` - Outreach email subject. `{{COMPANY_NAME}}` is replaced automatically.
- `outreach_message_body_file`: `string` - HTML file used as the outreach email body. `{{COMPANY_NAME}}` is replaced automatically.
- `stt_provider`: `string` - Subtitle transcription provider. Supported values: `local_whisper`, `third_party_assemblyai`.
- `whisper_model`: `string` - Whisper model for local transcription, for example `base`, `small`, `medium`, `large-v3`.
- `whisper_device`: `string` - Whisper execution device: `auto`, `cpu`, or `cuda`.
- `whisper_compute_type`: `string` - Whisper compute type such as `int8` or `float16`.
- `assembly_ai_api_key`: `string` - AssemblyAI API key.
- `tts_voice`: `string` - KittenTTS voice. Default: `Jasper`.
- `font`: `string` - Font filename from the `fonts/` directory.
- `imagemagick_path`: `string` - Path to the ImageMagick binary used by MoviePy.
- `script_sentence_length`: `number` - Number of sentences in the generated video script. Default: `4`.
- `news_pipeline`: `object` - Settings for tech-news collection and ranking.
- `news_pipeline.enabled`: `boolean` - Enables the local tech-news pipeline.
- `news_pipeline.max_article_age_hours`: `number` - Maximum age of candidate articles.
- `news_pipeline.max_candidates_per_source`: `number` - Maximum parsed candidates kept per source.
- `news_pipeline.max_selected_articles`: `number` - Final number of ranked articles kept after dedupe.
- `news_pipeline.use_llm_scoring`: `boolean` - Enables LLM-assisted scoring in addition to heuristic scoring.
- `news_pipeline.sources`: `string[]` - Supported sources: `theverge`, `zdnet_korea`, `bloter`.
- `news_pipeline.priority_keywords`: `string[]` - Keywords that boost ranking for product launches and core technologies.
- `news_pipeline.scoring_weights`: `object` - Weights for `public_interest`, `realism`, `llm`, and `keyword`.
- `post_bridge`: `object` - Settings for cross-posting after uploads.
- `post_bridge.enabled`: `boolean` - Enables Post Bridge integration.
- `post_bridge.api_key`: `string` - Post Bridge API key. If empty, MPV2 falls back to `POST_BRIDGE_API_KEY`.
- `post_bridge.platforms`: `string[]` - Supported values: `tiktok`, `instagram`.
- `post_bridge.account_ids`: `number[]` - Optional fixed account IDs to avoid interactive account selection.
- `post_bridge.auto_crosspost`: `boolean` - If `true`, cross-post automatically after a successful upload.

## Example

```json
{
  "verbose": true,
  "firefox_profile": "",
  "headless": false,
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_model": "gemma4:e4b",
  "twitter_language": "English",
  "nanobanana2_api_base_url": "https://generativelanguage.googleapis.com/v1beta",
  "nanobanana2_api_key": "",
  "nanobanana2_model": "gemini-3.1-flash-image-preview",
  "nanobanana2_aspect_ratio": "9:16",
  "threads": 2,
  "zip_url": "",
  "is_for_kids": false,
  "google_maps_scraper": "https://github.com/gosom/google-maps-scraper/archive/refs/tags/v0.9.7.zip",
  "email": {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "",
    "password": ""
  },
  "google_maps_scraper_niche": "",
  "scraper_timeout": 300,
  "outreach_message_subject": "I have a question...",
  "outreach_message_body_file": "outreach_message.html",
  "stt_provider": "local_whisper",
  "whisper_model": "base",
  "whisper_device": "auto",
  "whisper_compute_type": "int8",
  "assembly_ai_api_key": "",
  "tts_voice": "Jasper",
  "font": "bold_font.ttf",
  "imagemagick_path": "Path to magick.exe or on linux/macOS just /usr/bin/convert",
  "script_sentence_length": 4,
  "news_pipeline": {
    "enabled": true,
    "max_article_age_hours": 48,
    "max_candidates_per_source": 6,
    "max_selected_articles": 5,
    "use_llm_scoring": true,
    "sources": ["theverge", "zdnet_korea", "bloter"],
    "priority_keywords": [
      "samsung",
      "galaxy",
      "battery",
      "display",
      "udc",
      "출시",
      "공개",
      "발표",
      "반도체",
      "디스플레이",
      "배터리"
    ],
    "scoring_weights": {
      "public_interest": 0.35,
      "realism": 0.30,
      "llm": 0.25,
      "keyword": 0.10
    }
  },
  "post_bridge": {
    "enabled": false,
    "api_key": "",
    "platforms": ["tiktok", "instagram"],
    "account_ids": [],
    "auto_crosspost": false
  }
}
```

## Environment Variable Fallbacks

- `GEMINI_API_KEY`: used when `nanobanana2_api_key` is empty and also for Gemini text generation.
- `POST_BRIDGE_API_KEY`: used when `post_bridge.api_key` is empty.

Example:

```bash
export GEMINI_API_KEY="your_api_key_here"
export POST_BRIDGE_API_KEY="your_post_bridge_api_key_here"
```

See [PostBridge.md](./PostBridge.md) for full Post Bridge setup details.
