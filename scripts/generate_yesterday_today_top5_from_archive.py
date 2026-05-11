from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from moviepy.editor import VideoFileClip

from classes.Tts import TTS
from classes.YouTube import YouTube
from config import get_env_var, get_image_provider, get_nanobanana2_model, get_tts_provider
from news.archive import mark_shorts_status

ROOT = Path('/opt/data/MoneyPrinterV2')
DB_PATH = ROOT / 'data' / 'news_archive.sqlite3'
UPLOAD_HISTORY = ROOT / 'data' / 'upload_history.json'
KST = timezone(timedelta(hours=9))
RUN_TS = datetime.now(KST).strftime('%Y%m%d_%H%M%S')
OUT_DIR = ROOT / '.mp' / f'yesterday_today_top5_{RUN_TS}'
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / 'manifest.json'
RUN_INFO = OUT_DIR / 'run_info.json'


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
    titles = {_norm(item.get(field)) for item in data for field in ('article_title', 'title') if item.get(field)}
    urls = {_norm(item.get(field)) for item in data for field in ('article_url', 'url') if item.get(field)}
    return titles, urls


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _row_to_article(row: sqlite3.Row, label_date: str, daily_rank: int, selection_basis: str) -> dict:
    try:
        article = json.loads(row['payload_json'] or '{}')
    except json.JSONDecodeError:
        article = {}
    article.update({
        'id': row['id'],
        'archive_date': label_date,
        'selection_label_date': label_date,
        'selection_basis': selection_basis,
        'title': article.get('title') or row['title'],
        'url': article.get('url') or row['url'] or row['canonical_url'],
        'canonical_url': article.get('canonical_url') or row['canonical_url'] or row['url'],
        'source_name': article.get('source_name') or row['source_name'],
        'shorts_score': article.get('shorts_score') if article.get('shorts_score') is not None else row['shorts_score'],
        'topic_bucket': article.get('topic_bucket'),
        'audience_fit': article.get('audience_fit'),
        'daily_rank_ungenerated': daily_rank,
    })
    return article


def select_articles(per_day: int = 5) -> list[dict]:
    now = datetime.now(timezone.utc).astimezone(KST)
    target_dates = [(now - timedelta(days=1)).date().isoformat(), now.date().isoformat()]
    history_titles, history_urls = _load_upload_history()
    selected: list[dict] = []
    selected_ids: set[str] = set()
    skipped_history = 0

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('''
        SELECT id, payload_json, title, url, canonical_url, source_name, shorts_score,
               published_at, fetched_at, shorts_video_status
        FROM articles
        WHERE shorts_video_status = 'not_generated'
        ORDER BY COALESCE(shorts_score, 0) DESC, published_at DESC, id ASC
    ''').fetchall()
    con.close()

    def eligible(row: sqlite3.Row) -> bool:
        nonlocal skipped_history
        if row['id'] in selected_ids:
            return False
        title_norm = _norm(row['title'])
        url_norm = _norm(row['url'] or row['canonical_url'])
        if (title_norm and title_norm in history_titles) or (url_norm and url_norm in history_urls):
            skipped_history += 1
            return False
        return True

    run_info = {'target_dates_kst': target_dates, 'per_day': per_day, 'shortage_fill': []}
    for target_date in target_dates:
        group: list[tuple[sqlite3.Row, str]] = []
        group_ids: set[str] = set()
        for row in rows:
            if row['id'] in group_ids or not eligible(row):
                continue
            pdt = _parse_dt(row['published_at'])
            if pdt and pdt.astimezone(KST).date().isoformat() == target_date:
                group.append((row, 'published_at_kst'))
                group_ids.add(row['id'])
        # If today's published articles are fewer than 5, fill with articles fetched that day.
        if len(group) < per_day:
            before = len(group)
            for row in rows:
                if len(group) >= per_day:
                    break
                if row['id'] in group_ids or not eligible(row):
                    continue
                fdt = _parse_dt(row['fetched_at'])
                if fdt and fdt.astimezone(KST).date().isoformat() == target_date:
                    group.append((row, 'fetched_at_kst_fill'))
                    group_ids.add(row['id'])
            if len(group) > before:
                run_info['shortage_fill'].append({'date': target_date, 'published_count': before, 'filled_to': len(group)})
        for idx, (row, basis) in enumerate(group[:per_day], 1):
            # Mark IDs as selected immediately so any same-day shortage-fill pass
            # cannot duplicate an already selected published article.
            if row['id'] in selected_ids:
                continue
            article = _row_to_article(row, target_date, idx, basis)
            selected.append(article)
            selected_ids.add(row['id'])

    run_info['selected_count'] = len(selected)
    run_info['skipped_upload_history'] = skipped_history
    RUN_INFO.write_text(json.dumps(run_info, ensure_ascii=False, indent=2), encoding='utf-8')
    print('RUN_INFO=', str(RUN_INFO), flush=True)
    print('TARGET_DATES_KST=', ','.join(target_dates), flush=True)
    print('SKIPPED_UPLOAD_HISTORY=', skipped_history, flush=True)
    return selected


def main() -> int:
    print('YESTERDAY_TODAY_TOP5_GENERATION_START', flush=True)
    print('out_dir=', OUT_DIR, flush=True)
    print('image_provider=', get_image_provider(), flush=True)
    print('image_model=', get_nanobanana2_model(), flush=True)
    print('tts_provider=', get_tts_provider(), flush=True)
    print('google_key_visible=', bool(get_env_var('GOOGLE_API_KEY')), flush=True)
    selected = select_articles(per_day=5)
    if not selected:
        raise SystemExit('No eligible not-generated articles found')
    print('SELECTED=', flush=True)
    for idx, article in enumerate(selected, 1):
        print(
            f"ITEM{idx}|date={article.get('selection_label_date')}|rank={article.get('daily_rank_ungenerated')}|"
            f"basis={article.get('selection_basis')}|score={article.get('shorts_score')}|"
            f"source={article.get('source_name')}|title={article.get('title')}",
            flush=True,
        )

    manifest: list[dict] = []
    for idx, article in enumerate(selected, 1):
        label_date = article.get('selection_label_date') or 'unknown-date'
        daily_rank = article.get('daily_rank_ungenerated') or idx
        print(f'GENERATE_{idx}_START|date={label_date}|daily_rank={daily_rank}', flush=True)
        mark_shorts_status(article, 'selected', rank=daily_rank)
        yt = YouTube.for_local_generation(niche='Korean IT News', language='Korean')
        path = yt.generate_video_from_news(TTS(), article)
        abs_path = str(Path(path).resolve())
        clip = VideoFileClip(abs_path)
        frame_path = OUT_DIR / f'frame_{label_date}_rank{daily_rank}.png'
        clip.save_frame(str(frame_path), t=min(max(clip.duration * 0.35, 1.0), max(clip.duration - 1, 1)))
        info = {
            'batch_index': idx,
            'selection_label_date': label_date,
            'selection_basis': article.get('selection_basis'),
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
            f"GENERATE_{idx}_DONE|date={label_date}|daily_rank={daily_rank}|path={abs_path}|"
            f"duration={info['duration']}|bytes={info['bytes']}",
            flush=True,
        )
    print('YESTERDAY_TODAY_TOP5_GENERATION_DONE', flush=True)
    print('MANIFEST=', str(MANIFEST), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
