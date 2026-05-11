from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from moviepy.editor import VideoFileClip
from news.archive import mark_shorts_status
from news.collector import collect_ranked_news
from news.ranker import select_portfolio_articles
from classes.YouTube import YouTube
from classes.Tts import TTS
from config import get_image_provider, get_nanobanana2_model, get_tts_provider, get_env_var
from project_paths import project_root

ROOT = project_root()
OUT_DIR = ROOT / '.mp' / 'batch_top5'
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / 'manifest.json'
UPLOAD_HISTORY = ROOT / 'data' / 'upload_history.json'


def _norm_text(value: str) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def _load_upload_history() -> list[dict]:
    if not UPLOAD_HISTORY.exists():
        return []
    try:
        data = json.loads(UPLOAD_HISTORY.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f'UPLOAD_HISTORY_READ_FAILED={exc}', flush=True)
        return []


print('BATCH_TOP5_START', flush=True)
print('image_provider=', get_image_provider(), flush=True)
print('image_model=', get_nanobanana2_model(), flush=True)
print('tts_provider=', get_tts_provider(), flush=True)
print('google_key_visible=', bool(get_env_var('GOOGLE_API_KEY')), flush=True)

articles = collect_ranked_news(limit=int(os.environ.get('NEWS_LIMIT', '50')))

# Current daily cron scope includes AI/software/platform as valid IT news
# alongside hardware categories. Keep default exclusions empty; callers can still
# pass one-off exclusions through EXCLUDE_TERMS when needed.
DEFAULT_EXCLUDE_TERMS = []
extra_exclude_terms = [
    term.strip().lower()
    for term in os.environ.get('EXCLUDE_TERMS', '').split('|')
    if term.strip()
]
exclude_terms = []
for term in DEFAULT_EXCLUDE_TERMS + extra_exclude_terms:
    if term and term not in exclude_terms:
        exclude_terms.append(term)

def _matches_exclude_term(haystack: str, term: str) -> bool:
    # Short technical tokens such as "ai" must match as standalone words;
    # otherwise unrelated strings can be filtered by accident.
    if term in {'ai'}:
        return bool(re.search(r'(?<![a-z0-9])ai(?![a-z0-9])', haystack))
    return term in haystack

if exclude_terms:
    print('EXCLUDE_TERMS=', ' | '.join(exclude_terms), flush=True)

upload_history = _load_upload_history()
history_urls = {
    _norm_text(str(item.get('article_url') or item.get('url') or ''))
    for item in upload_history
    if item.get('article_url') or item.get('url')
}
history_titles = {
    _norm_text(str(item.get(field) or ''))
    for item in upload_history
    for field in ('article_title', 'title')
    if item.get(field)
}
if upload_history:
    print('UPLOAD_HISTORY_COUNT=', len(upload_history), flush=True)
seen = set()
candidates = []
for a in articles:
    key = (a.get('url') or a.get('title') or '').strip().lower()
    title = (a.get('title') or '').strip()
    if not key or not title:
        continue
    title_norm = _norm_text(title)
    article_url_norm = _norm_text(str(a.get('url') or ''))
    if article_url_norm and article_url_norm in history_urls:
        print(f"SKIP_ALREADY_UPLOADED|match=url|title={title}", flush=True)
        continue
    if title_norm and title_norm in history_titles:
        print(f"SKIP_ALREADY_UPLOADED|match=title|title={title}", flush=True)
        continue
    haystack = ' '.join(
        str(a.get(field) or '').lower()
        for field in ('title', 'url', 'summary', 'excerpt', 'source_name')
    )
    matched_exclude = next(
        (term for term in exclude_terms if _matches_exclude_term(haystack, term)),
        None,
    )
    if matched_exclude:
        print(f"SKIP_EXCLUDED|term={matched_exclude}|title={title}", flush=True)
        continue
    if key in seen or title_norm in seen:
        continue
    seen.add(key); seen.add(title_norm)
    candidates.append(a)

selected = select_portfolio_articles(candidates, count=5)

if len(selected) < 5:
    raise SystemExit(f'Only found {len(selected)} unique ranked articles')

print('SELECTED_TOP5=', flush=True)
for i, a in enumerate(selected, 1):
    print(f"TOP{i}|score={a.get('shorts_score')}|bucket={a.get('topic_bucket')}|audience={a.get('audience_fit')}|angle={(a.get('shorts_angle') or {}).get('angle_type')}|source={a.get('source_name')}|title={a.get('title')}", flush=True)

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
        'strategic_importance_score': article.get('strategic_importance_score'),
        'shorts_angle': article.get('shorts_angle'),
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
    # Extract a mid-frame for later visual review
    frame_path = OUT_DIR / f'frame_rank{idx}.png'
    clip.save_frame(str(frame_path), t=min(max(clip.duration * 0.35, 1.0), max(clip.duration - 1, 1)))
    clip.close()
    info['frame_path'] = str(frame_path)
    mark_shorts_status(article, 'generated', rank=idx, video_path=abs_path)
    manifest.append(info)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"GENERATE_{idx}_DONE|path={abs_path}|duration={info['duration']}|bytes={info['bytes']}", flush=True)

print('BATCH_TOP5_DONE', flush=True)
print('MANIFEST=', str(MANIFEST), flush=True)
