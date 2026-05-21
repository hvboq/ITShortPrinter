from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news.collector import collect_ranked_news  # noqa: E402
from news.ranker import select_portfolio_articles  # noqa: E402

JOB_DIR = ROOT / ".mp" / "two_hour_job"
LOCK_FILE = JOB_DIR / "run.lock"
LATEST_MANIFEST = JOB_DIR / "latest_manifest.json"
UPLOAD_MANIFEST = JOB_DIR / "upload_manifest.json"
LOG_DIR = JOB_DIR / "logs"
SCREEN_DIR = JOB_DIR / "screens"
UPLOAD_HISTORY = ROOT / "data" / "upload_history.json"


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


def load_upload_history() -> list[dict[str, Any]]:
    if not UPLOAD_HISTORY.exists():
        return []
    try:
        data = json.loads(UPLOAD_HISTORY.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"UPLOAD_HISTORY_READ_FAILED={exc}", flush=True)
        return []
    return data if isinstance(data, list) else []


def select_next_article(limit: int) -> Any:
    articles = collect_ranked_news(limit=limit)
    history = load_upload_history()
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
        candidates.append(article)

    selected = select_portfolio_articles(candidates, count=1)
    if not selected:
        raise RuntimeError("No unused Shorts-friendly article candidates found")
    return selected[0]


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
    article = select_next_article(limit=news_limit)
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
