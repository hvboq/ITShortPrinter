# Session Progress — 2026-04-27 Phase 4 Korean Generation Enforcement

## Goal

Make the MoneyPrinterV2 IT-news Shorts generation path produce Korean outputs consistently, even when source news titles/excerpts are in English or a caller passes a non-Korean language label.

## Code Changes

- `src/news/shorts.py`
  - Changed the ranked-news script prompt to identify the assistant as a Korean IT-news Shorts writer.
  - Removed dynamic `언어: {language}` behavior from the news-script prompt.
  - Added an explicit rule: all narration must be written only in Korean, translating/reframing English news inputs into natural Korean.

- `src/classes/YouTube.py`
  - Rewrote the generic non-news script prompt in Korean.
  - Forced generic script output language to Korean.
  - Rewrote metadata prompts so the YouTube title and description must be Korean-only.
  - Rewrote image-prompt generation instructions in Korean.
  - Forced JSON array image prompt strings to be Korean.

## Tests Added

- `tests/test_korean_generation_policy.py`
  - Verifies ranked-news script prompt forces Korean even if `language="English"` is passed.
  - Verifies metadata prompts force Korean title/description.
  - Verifies image prompt generation asks for Korean-only JSON strings.

## Verification

Targeted RED/GREEN cycle:

```bash
venv/bin/python -m unittest tests/test_korean_generation_policy.py -v
```

Initial run failed as expected because the prior prompts still allowed English metadata/image prompts and dynamic language labels.

After implementation:

```text
Ran 3 tests in 0.326s
OK
```

Full relevant suite:

```bash
venv/bin/python -m py_compile src/config.py src/gemini_image.py src/classes/Tts.py src/classes/YouTube.py src/llm_provider.py src/news/ranker.py src/news/shorts.py src/news/fetcher.py src/news/collector.py src/main.py src/constants.py
venv/bin/python -m unittest tests/test_gemini_image_generation.py tests/test_moviepy_smoke.py tests/test_youtube_combine_smoke.py tests/test_local_no_upload_generation.py tests/test_youtube_llm_defaults.py tests/test_korean_generation_policy.py tests/test_config_optional_deps.py tests/test_local_ai_config.py tests/test_tts_provider.py tests/test_tech_news_ranker.py tests/test_news_shorts.py tests/test_news_fetcher.py tests/test_youtube_news_menu.py -v
```

Result:

```text
Ran 23 tests in 1.203s
OK
```

Live Ollama Korean smoke:

```text
MODEL=gemma4:e4b
TITLE=Huawei Pura X Max, Pura 90 Pro, Moto Edge 70 Pro are official, Week 17 in review
SCRIPT_SAMPLE=삼성과 애플에 이어, 또 다른 거대 기업이 플래그십 전성기를 열고 있습니다...
META_TITLE=[🚨주간 리뷰] Pura & Moto 신상 폰 대격돌! 🆚 17주 플래그십 총정리! #스마트폰 #IT리뷰 #핸드폰추천
```

## Notes

- This change intentionally prioritizes the user's Korean IT-news channel workflow over MoneyPrinterV2's original arbitrary-language generator behavior.
- Source article titles/excerpts can remain English; the generated narration, metadata, and image prompts are now instructed to be Korean-only.
- Placeholder image provider and silent TTS remain development/smoke-test settings. Production still requires Gemini API key and a real TTS provider.
