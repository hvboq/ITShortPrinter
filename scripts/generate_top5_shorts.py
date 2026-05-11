from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from moviepy.editor import VideoFileClip
from news.collector import collect_ranked_news
from classes.YouTube import YouTube
from classes.Tts import TTS
from config import get_image_provider, get_nanobanana2_model, get_tts_provider, get_env_var
from project_paths import project_root

ROOT = project_root()
OUT_DIR = ROOT / '.mp' / 'batch_top5'
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / 'manifest.json'

print('BATCH_TOP5_START', flush=True)
print('image_provider=', get_image_provider(), flush=True)
print('image_model=', get_nanobanana2_model(), flush=True)
print('tts_provider=', get_tts_provider(), flush=True)
print('google_key_visible=', bool(get_env_var('GOOGLE_API_KEY')), flush=True)

articles = collect_ranked_news(limit=int(os.environ.get('NEWS_LIMIT', '50')))
exclude_terms = [
    term.strip().lower()
    for term in os.environ.get('EXCLUDE_TERMS', '').split('|')
    if term.strip()
]
if exclude_terms:
    print('EXCLUDE_TERMS=', ' | '.join(exclude_terms), flush=True)
seen = set()
selected = []
for a in articles:
    key = (a.get('url') or a.get('title') or '').strip().lower()
    title = (a.get('title') or '').strip()
    if not key or not title:
        continue
    title_norm = re.sub(r'\s+', ' ', title.lower())
    haystack = ' '.join(
        str(a.get(field) or '').lower()
        for field in ('title', 'url', 'summary', 'excerpt', 'source_name')
    )
    if exclude_terms and any(term in haystack for term in exclude_terms):
        print(f"SKIP_EXCLUDED|title={title}", flush=True)
        continue
    if key in seen or title_norm in seen:
        continue
    seen.add(key); seen.add(title_norm)
    selected.append(a)
    if len(selected) >= 5:
        break

if len(selected) < 5:
    raise SystemExit(f'Only found {len(selected)} unique ranked articles')

print('SELECTED_TOP5=', flush=True)
for i, a in enumerate(selected, 1):
    print(f"TOP{i}|score={a.get('shorts_score')}|source={a.get('source_name')}|title={a.get('title')}", flush=True)

manifest = []
for idx, article in enumerate(selected, 1):
    print(f'GENERATE_{idx}_START', flush=True)
    yt = YouTube.for_local_generation(niche='Korean IT News', language='Korean')
    path = yt.generate_video_from_news(TTS(), article)
    abs_path = str(Path(path).resolve())
    clip = VideoFileClip(abs_path)
    info = {
        'rank': idx,
        'score': article.get('shorts_score'),
        'source': article.get('source_name'),
        'article_title': article.get('title'),
        'article_url': article.get('url'),
        'video_path': abs_path,
        'metadata': getattr(yt, 'metadata', {}),
        'script': getattr(yt, 'script', ''),
        'images': list(getattr(yt, 'images', [])),
        'bytes': Path(abs_path).stat().st_size,
        'duration': round(float(clip.duration), 2),
        'size': clip.size,
        'fps': float(clip.fps),
    }
    # Extract a mid-frame for later visual review
    frame_path = OUT_DIR / f'frame_rank{idx}.png'
    clip.save_frame(str(frame_path), t=min(max(clip.duration * 0.35, 1.0), max(clip.duration - 1, 1)))
    clip.close()
    info['frame_path'] = str(frame_path)
    manifest.append(info)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"GENERATE_{idx}_DONE|path={abs_path}|duration={info['duration']}|bytes={info['bytes']}", flush=True)

print('BATCH_TOP5_DONE', flush=True)
print('MANIFEST=', str(MANIFEST), flush=True)
