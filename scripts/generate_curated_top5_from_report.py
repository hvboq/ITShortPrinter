from __future__ import annotations

import json
import re
from pathlib import Path

import _bootstrap  # noqa: F401
from moviepy.editor import VideoFileClip
from news.archive import mark_shorts_status
from classes.YouTube import YouTube
from classes.Tts import TTS
from config import get_image_provider, get_nanobanana2_model, get_tts_provider, get_env_var

ROOT = Path('/opt/data/MoneyPrinterV2')
REPORT = ROOT / 'reports/news/collected_news_all_20260510_134648.json'
OUT_DIR = ROOT / '.mp' / 'batch_top5'
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / 'manifest.json'

TARGET_TITLES = [
    'Weekly deals: the Samsung Galaxy S26 trio gets discounts up to €500, iPhones also get price cuts',
    'Weekly poll: would you buy a Motorola Razr 70, Razr 70+ or Razr 70 Ultra? Which one?',
    'Nothing Ear (open) Bluetooth earphones are getting a new color on May 11',
    '에이서, 지마켓 ‘빅스마일데이’서 게이밍·AI 노트북 최대 36% 할인',
    'Samsung Galaxy Buds3 Pro and Buds4 Pro receive stability-focused software updates',
]

def norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip().lower())

print('CURATED_TOP5_START', flush=True)
print('image_provider=', get_image_provider(), flush=True)
print('image_model=', get_nanobanana2_model(), flush=True)
print('tts_provider=', get_tts_provider(), flush=True)
print('google_key_visible=', bool(get_env_var('GOOGLE_API_KEY')), flush=True)

articles = json.loads(REPORT.read_text(encoding='utf-8'))
by_title = {norm(a.get('title', '')): a for a in articles}
selected = []
for title in TARGET_TITLES:
    article = by_title.get(norm(title))
    if not article:
        raise SystemExit(f'Missing target article: {title}')
    selected.append(article)

print('SELECTED_CURATED_TOP5=', flush=True)
for i, a in enumerate(selected, 1):
    print(f"TOP{i}|score={a.get('shorts_score')}|bucket={a.get('topic_bucket')}|source={a.get('source_name')}|title={a.get('title')}", flush=True)

manifest = []
for idx, article in enumerate(selected, 1):
    print(f'GENERATE_{idx}_START', flush=True)
    mark_shorts_status(article, 'selected', rank=idx)
    yt = YouTube.for_local_generation(niche='Korean IT News', language='Korean')
    path = yt.generate_video_from_news(TTS(), article)
    abs_path = str(Path(path).resolve())
    clip = VideoFileClip(abs_path)
    info = {
        'rank': idx,
        'score': article.get('shorts_score'),
        'topic_bucket': article.get('topic_bucket'),
        'audience_fit': article.get('audience_fit'),
        'source': article.get('source_name'),
        'article_title': article.get('title'),
        'article_url': article.get('url'),
        'article_id': article.get('id'),
        'video_path': abs_path,
        'metadata': getattr(yt, 'metadata', {}),
        'script': getattr(yt, 'script', ''),
        'images': list(getattr(yt, 'images', [])),
        'bytes': Path(abs_path).stat().st_size,
        'duration': round(float(clip.duration), 2),
        'size': clip.size,
        'fps': float(clip.fps),
    }
    frame_path = OUT_DIR / f'frame_rank{idx}.png'
    clip.save_frame(str(frame_path), t=min(max(clip.duration * 0.35, 1.0), max(clip.duration - 1, 1)))
    clip.close()
    info['frame_path'] = str(frame_path)
    mark_shorts_status(article, 'generated', rank=idx, video_path=abs_path)
    manifest.append(info)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"GENERATE_{idx}_DONE|path={abs_path}|duration={info['duration']}|bytes={info['bytes']}", flush=True)

print('CURATED_TOP5_DONE', flush=True)
print('MANIFEST=', str(MANIFEST), flush=True)
