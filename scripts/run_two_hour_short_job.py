from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news.collector import collect_product_launch_news, collect_ranked_news  # noqa: E402
from news.ranker import (  # noqa: E402
    LAUNCH_TERMS,
    _contains_any,
    classify_event,
    select_portfolio_articles,
)

JOB_DIR = ROOT / ".mp" / "two_hour_job"
LOCK_FILE = JOB_DIR / "run.lock"
LATEST_MANIFEST = JOB_DIR / "latest_manifest.json"
UPLOAD_MANIFEST = JOB_DIR / "upload_manifest.json"
LOG_DIR = JOB_DIR / "logs"
SCREEN_DIR = JOB_DIR / "screens"
UPLOAD_HISTORY = ROOT / "data" / "upload_history.json"
ARCHIVE_DB = ROOT / "data" / "news_archive.sqlite3"


def _now() -> int:
    return int(time.time())


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _article_get(article: Any, key: str, default: Any = None) -> Any:
    if isinstance(article, dict):
        return article.get(key, default)
    return getattr(article, key, default)


def _article_to_dict(article: Any) -> dict[str, Any]:
    if isinstance(article, dict):
        return dict(article)
    data = getattr(article, "__dict__", None)
    if isinstance(data, dict):
        return dict(data)
    return {
        "title": _article_get(article, "title", ""),
        "url": _article_get(article, "url", ""),
        "score": _article_get(article, "score", None),
    }


def _article_text(article: Any) -> str:
    return " ".join(
        str(_article_get(article, key, "") or "")
        for key in ("title", "raw_excerpt", "content_summary", "summary", "description")
    ).lower()


def _article_event_type(article: Any) -> str:
    event_type = str(_article_get(article, "event_type", "") or "").strip()
    if event_type:
        return event_type
    data = _article_to_dict(article)
    return classify_event(data, _article_text(article))


def matches_requested_topic(article: Any, topic: str) -> bool:
    """Return whether an article matches a scheduled specialty topic."""
    normalized = topic.strip().lower()
    if not normalized or normalized in {"any", "all", "general"}:
        return True
    if normalized not in {"product_launch", "launch", "new_product"}:
        raise ValueError(
            "SHORTS_JOB_TOPIC must be empty/any or product_launch"
        )

    text = _article_text(article)
    event_type = _article_event_type(article)
    has_launch_term = _contains_any(text, LAUNCH_TERMS)
    has_blocked_term = _contains_any(
        text,
        [
            "rumor",
            "leak",
            "루머",
            "유출",
            "concept",
            "prototype",
            "특허",
            "가능성",
            "delay",
            "delayed",
            "postpone",
            "postponed",
            "연기",
            "지연",
            "무기한",
        ],
    )
    if has_blocked_term:
        return False
    if event_type == "product_launch":
        return True
    # Launch/release stories with price or availability words are often scored as
    # price_availability because the ranker checks those terms first. They still
    # satisfy the 13:00 slot requirement when a launch term is present.
    if event_type == "price_availability" and has_launch_term:
        return True
    # Do not accept broad software-update/market/component stories just because
    # their titles contain "release/출시"; the 13:00 slot is for product launches
    # and new device/service availability.
    return False


def load_upload_history() -> list[dict[str, Any]]:
    if not UPLOAD_HISTORY.exists():
        return []
    try:
        data = json.loads(UPLOAD_HISTORY.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"UPLOAD_HISTORY_READ_FAILED={exc}", flush=True)
        return []
    return data if isinstance(data, list) else []


def _is_product_launch_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return normalized in {"product_launch", "launch", "new_product"}


def _collect_articles_for_topic(limit: int, topic: str) -> list[Any]:
    if _is_product_launch_topic(topic):
        print("PRODUCT_LAUNCH_SOURCE_MODE=dedicated", flush=True)
        return collect_product_launch_news(limit=limit)
    return collect_ranked_news(limit=limit)


def _history_keys(history: list[dict]) -> tuple[set[str], set[str]]:
    used_urls = {
        _norm(item.get("article_url") or item.get("url"))
        for item in history
        if isinstance(item, dict)
    }
    used_titles = {
        _norm(item.get("article_title") or item.get("title"))
        for item in history
        if isinstance(item, dict)
    }
    return used_urls, used_titles


def _row_to_archive_article(row: sqlite3.Row) -> dict[str, Any]:
    try:
        article = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        article = {}
    article.update(
        {
            "id": row["id"],
            "title": article.get("title") or row["title"],
            "url": article.get("url") or row["url"] or row["canonical_url"],
            "canonical_url": article.get("canonical_url") or row["canonical_url"] or row["url"],
            "source_name": article.get("source_name") or row["source_name"],
            "shorts_score": article.get("shorts_score") if article.get("shorts_score") is not None else row["shorts_score"],
            "event_type": article.get("event_type") or row["event_type"],
            "topic_bucket": article.get("topic_bucket"),
            "selection_source": "archive_fallback",
        }
    )
    return article


def _archive_fallback_candidates(limit: int, topic: str, used_urls: set[str], used_titles: set[str]) -> list[dict[str, Any]]:
    if not ARCHIVE_DB.exists():
        return []

    con = sqlite3.connect(ARCHIVE_DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT id, payload_json, title, url, canonical_url, source_name,
                   shorts_score, event_type, published_at, fetched_at, archived_at
            FROM articles
            WHERE shorts_video_status = 'not_generated'
            ORDER BY COALESCE(shorts_score, 0) DESC,
                     COALESCE(NULLIF(published_at, ''), fetched_at, archived_at) DESC,
                     id ASC
            LIMIT ?
            """,
            (max(limit, 50),),
        ).fetchall()
    finally:
        con.close()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        article = _row_to_archive_article(row)
        title = _norm(_article_get(article, "title", ""))
        url = _norm(_article_get(article, "url", ""))
        if (url and url in used_urls) or (title and title in used_titles):
            continue
        if topic and not matches_requested_topic(article, topic):
            continue
        candidates.append(article)
    return candidates


def select_next_article(limit: int, topic: str = "") -> Any:
    articles = _collect_articles_for_topic(limit=limit, topic=topic)
    history = load_upload_history()
    used_urls, used_titles = _history_keys(history)

    candidates = []
    seen = set()
    for article in articles:
        title = _norm(_article_get(article, "title", ""))
        url = _norm(_article_get(article, "url", ""))
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        if url and url in used_urls:
            print(f"SKIP_ALREADY_UPLOADED|match=url|title={_article_get(article, 'title', '')}", flush=True)
            continue
        if title and title in used_titles:
            print(f"SKIP_ALREADY_UPLOADED|match=title|title={_article_get(article, 'title', '')}", flush=True)
            continue
        if topic and not matches_requested_topic(article, topic):
            print(
                "SKIP_TOPIC_MISMATCH|"
                f"topic={topic}|event_type={_article_event_type(article)}|"
                f"title={_article_get(article, 'title', '')}",
                flush=True,
            )
            continue
        candidates.append(article)

    selected = select_portfolio_articles(candidates, count=1)
    if selected:
        return selected[0]

    fallback_candidates = _archive_fallback_candidates(limit, topic, used_urls, used_titles)
    fallback_selected = select_portfolio_articles(fallback_candidates, count=1)
    if fallback_selected:
        article = fallback_selected[0]
        print(
            "ARCHIVE_FALLBACK_SELECTED|"
            f"score={_article_get(article, 'shorts_score', '')}|"
            f"source={_article_get(article, 'source_name', '')}|"
            f"title={_article_get(article, 'title', '')}",
            flush=True,
        )
        return article

    topic_suffix = f" for topic={topic}" if topic else ""
    raise RuntimeError(f"No unused Shorts-friendly article candidates found{topic_suffix}")


def acquire_lock(lock_ttl_minutes: int) -> bool:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
            started_at = int(lock.get("started_at", 0))
        except Exception:
            started_at = 0
        age = _now() - started_at
        if age < lock_ttl_minutes * 60:
            print(f"LOCK_ACTIVE|age_seconds={age}|path={LOCK_FILE}", flush=True)
            return False
        print(f"LOCK_STALE|age_seconds={age}|path={LOCK_FILE}", flush=True)

    LOCK_FILE.write_text(
        json.dumps({"pid": os.getpid(), "started_at": _now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def write_single_item_manifest(article: Any, video_path: str, youtube: Any) -> Path:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    manifest_item = {
        "rank": 1,
        "article_title": _article_get(article, "title", ""),
        "article_url": _article_get(article, "url", ""),
        "article_id": _article_get(article, "id", ""),
        "source": _article_get(article, "source_name", ""),
        "score": _article_get(article, "shorts_score", _article_get(article, "score", None)),
        "topic_bucket": _article_get(article, "topic_bucket", ""),
        "video_path": str(Path(video_path).resolve()),
        "metadata": getattr(youtube, "metadata", {}),
        "script": getattr(youtube, "script", ""),
        "article": _article_to_dict(article),
    }
    LATEST_MANIFEST.write_text(
        json.dumps([manifest_item], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"MANIFEST={LATEST_MANIFEST}", flush=True)
    return LATEST_MANIFEST


def upload_manifest(manifest_path: Path, visibility: str) -> int:
    script_name = (
        "upload_top5_public_shorts.py"
        if visibility == "public"
        else "upload_top5_shorts.py"
    )
    script = ROOT / "scripts" / script_name
    env = os.environ.copy()
    env.update(
        {
            "UPLOAD_SOURCE_MANIFEST": str(manifest_path),
            "UPLOAD_OUTPUT_MANIFEST": str(UPLOAD_MANIFEST),
            "UPLOAD_SCREEN_DIR": str(SCREEN_DIR),
            "START_RANK": "1",
            "END_RANK": "1",
        }
    )
    print(f"UPLOAD_SCRIPT={script.name}|visibility={visibility}", flush=True)
    return subprocess.call([sys.executable, str(script)], cwd=str(ROOT), env=env)


def run_job() -> int:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)

    visibility = os.environ.get("SHORTS_JOB_VISIBILITY", "public").strip().lower()
    if visibility not in {"public", "unlisted"}:
        raise ValueError("SHORTS_JOB_VISIBILITY must be public or unlisted")

    dry_run = os.environ.get("SHORTS_JOB_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
    news_limit = int(os.environ.get("NEWS_LIMIT", "50"))
    topic = os.environ.get("SHORTS_JOB_TOPIC", "").strip()
    if topic:
        print(f"SHORTS_JOB_TOPIC={topic}", flush=True)
    article = select_next_article(limit=news_limit, topic=topic)
    print(f"SELECTED_ARTICLE={_article_get(article, 'title', '')}", flush=True)
    print(f"SELECTED_URL={_article_get(article, 'url', '')}", flush=True)

    if dry_run:
        print("SHORTS_JOB_DRY_RUN=1; skipping media generation and upload", flush=True)
        return 0

    from classes.Tts import TTS
    from classes.YouTube import YouTube

    youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
    video_path = youtube.generate_video_from_news(TTS(), article)
    print(f"GENERATED_VIDEO={video_path}", flush=True)

    manifest_path = write_single_item_manifest(article, video_path, youtube)
    upload_exit = upload_manifest(manifest_path, visibility)
    if upload_exit != 0:
        print(f"UPLOAD_FAILED|exit_code={upload_exit}", flush=True)
        return upload_exit

    print(f"UPLOAD_DONE|manifest={UPLOAD_MANIFEST}", flush=True)
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lock_ttl_minutes = int(os.environ.get("SHORTS_JOB_LOCK_TTL_MINUTES", "110"))
    if not acquire_lock(lock_ttl_minutes):
        return 0
    try:
        return run_job()
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
