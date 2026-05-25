from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import _bootstrap  # noqa: F401
from moviepy.editor import VideoFileClip

from classes.Tts import TTS
from classes.YouTube import YouTube
from config import get_env_var, get_image_provider, get_nanobanana2_model, get_tts_provider
from news.archive import mark_shorts_status

ROOT = Path('/opt/data/MoneyPrinterV2')
DB_PATH = ROOT / 'data' / 'news_archive.sqlite3'
UPLOAD_HISTORY = ROOT / 'data' / 'upload_history.json'
OUT_DIR = ROOT / '.mp' / 'daily2_from_archive'
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / 'manifest.json'


def _norm(value: object) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _load_upload_history() -> tuple[set[str], set[str]]:
    if not UPLOAD_HISTORY.exists():
        return set(), set()
    try:
        data = json.loads(UPLOAD_HISTORY.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'UPLOAD_HISTORY_READ_FAILED={type(exc).__name__}:{exc}', flush=True)
        return set(), set()
    if not isinstance(data, list):
        return set(), set()
    titles = {
        _norm(item.get(field))
        for item in data
        for field in ('article_title', 'title')
        if item.get(field)
    }
    urls = {
        _norm(item.get(field))
        for item in data
        for field in ('article_url', 'url')
        if item.get(field)
    }
    return titles, urls


def select_daily_articles(per_day: int = 2) -> list[dict]:
    history_titles, history_urls = _load_upload_history()
    selected: list[dict] = []
    per_date_counts: dict[str, int] = {}
    skipped_history = 0

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, date(fetched_at) AS archive_date, payload_json, title, url, canonical_url,
               source_name, shorts_score
        FROM articles
        WHERE shorts_video_status = 'not_generated'
        ORDER BY date(fetched_at), shorts_score DESC, id ASC
        """
    ).fetchall()
    con.close()

    for row in rows:
        archive_date = row['archive_date']
        if per_date_counts.get(archive_date, 0) >= per_day:
            continue
        title_norm = _norm(row['title'])
        url_norm = _norm(row['url'] or row['canonical_url'])
        if (title_norm and title_norm in history_titles) or (url_norm and url_norm in history_urls):
            skipped_history += 1
            continue
        try:
            article = json.loads(row['payload_json'] or '{}')
        except json.JSONDecodeError:
            article = {}
        article.update(
            {
                'id': row['id'],
                'archive_date': archive_date,
                'title': article.get('title') or row['title'],
                'url': article.get('url') or row['url'] or row['canonical_url'],
                'canonical_url': article.get('canonical_url') or row['canonical_url'] or row['url'],
                'source_name': article.get('source_name') or row['source_name'],
                'shorts_score': article.get('shorts_score') if article.get('shorts_score') is not None else row['shorts_score'],
                'topic_bucket': article.get('topic_bucket'),
                'audience_fit': article.get('audience_fit'),
            }
        )
        per_date_counts[archive_date] = per_date_counts.get(archive_date, 0) + 1
        article['daily_rank_ungenerated'] = per_date_counts[archive_date]
        selected.append(article)

    print(f'SKIPPED_UPLOAD_HISTORY={skipped_history}', flush=True)
    return selected


def main() -> int:
    print('DAILY2_ARCHIVE_GENERATION_START', flush=True)
    print('image_provider=', get_image_provider(), flush=True)
    print('image_model=', get_nanobanana2_model(), flush=True)
    print('tts_provider=', get_tts_provider(), flush=True)
    print('google_key_visible=', bool(get_env_var('GOOGLE_API_KEY')), flush=True)

    selected = select_daily_articles(per_day=2)
    if not selected:
        raise SystemExit('No not-generated archive articles found')

    print('SELECTED_DAILY2=', flush=True)
    for idx, article in enumerate(selected, 1):
        print(
            f"ITEM{idx}|date={article.get('archive_date')}|daily_rank={article.get('daily_rank_ungenerated')}|"
            f"score={article.get('shorts_score')}|source={article.get('source_name')}|title={article.get('title')}",
            flush=True,
        )

    manifest: list[dict] = []
    for idx, article in enumerate(selected, 1):
        archive_date = article.get('archive_date') or 'unknown-date'
        daily_rank = article.get('daily_rank_ungenerated') or idx
        print(f'GENERATE_{idx}_START|date={archive_date}|daily_rank={daily_rank}', flush=True)
        mark_shorts_status(article, 'selected', rank=daily_rank)

        yt = YouTube.for_local_generation(niche='Korean IT News', language='Korean')
        path = yt.generate_video_from_news(TTS(), article)
        abs_path = str(Path(path).resolve())

        clip = VideoFileClip(abs_path)
        frame_path = OUT_DIR / f'frame_{archive_date}_rank{daily_rank}.png'
        clip.save_frame(str(frame_path), t=min(max(clip.duration * 0.35, 1.0), max(clip.duration - 1, 1)))
        info = {
            'batch_index': idx,
            'archive_date': archive_date,
            'daily_rank_ungenerated': daily_rank,
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
            'frame_path': str(frame_path),
        }
        clip.close()

        mark_shorts_status(article, 'generated', rank=daily_rank, video_path=abs_path)
        manifest.append(info)
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(
            f"GENERATE_{idx}_DONE|date={archive_date}|daily_rank={daily_rank}|path={abs_path}|"
            f"duration={info['duration']}|bytes={info['bytes']}",
            flush=True,
        )

    print('DAILY2_ARCHIVE_GENERATION_DONE', flush=True)
    print('MANIFEST=', str(MANIFEST), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
