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

from classes.youtube_review import (  # noqa: E402
    build_structure_quality_fields,
    extract_video_review_frame,
    review_archive_status,
)
from config import get_subtitle_max_chars  # noqa: E402
from news.archive import init_archive  # noqa: E402
from news.collector import collect_product_launch_news, collect_ranked_news  # noqa: E402
from news.duplicate_guard import (  # noqa: E402
    article_title,
    article_urls,
    atomic_write_json,
    duplicate_reason,
    file_lock,
    load_history,
)
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
RUN_MANIFEST_DIR = JOB_DIR / "manifests"
LOG_DIR = JOB_DIR / "logs"
SCREEN_DIR = JOB_DIR / "screens"
UPLOAD_HISTORY = ROOT / "data" / "upload_history.json"
UPLOAD_HISTORY_LOCK = ROOT / "data" / "upload_history.lock"
ARCHIVE_DB = ROOT / "data" / "news_archive.sqlite3"
_LOCK_OWNER_TOKEN: str | None = None


def _now() -> int:
    return int(time.time())


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"INVALID_ENV_INT|name={name}|value={raw}|default={default}", flush=True)
        return default
    if value < 1:
        print(f"INVALID_ENV_INT|name={name}|value={raw}|default={default}", flush=True)
        return default
    return value


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


def _video_review_fields(video_path: str, subtitle_path: str | Path | None = None) -> dict[str, Any]:
    frame_path = JOB_DIR / "latest_review_frame.png"
    try:
        review = extract_video_review_frame(
            video_path,
            frame_path,
            subtitle_path=subtitle_path,
            title_overlay_expected=True,
        )
    except Exception as exc:
        return {
            "duration": None,
            "size": None,
            "fps": None,
            "review_file_size_bytes": None,
            "frame_path": "",
            "review_frame_timestamp": None,
            "review_frame_paths": [],
            "review_frame_timestamps": [],
            "review_sheet_path": "",
            "review_sheet_frame_count": 0,
            "review_frame_brightness": None,
            "review_frame_contrast": None,
            "review_frame_brightness_values": [],
            "review_frame_contrast_values": [],
            "review_frame_center_brightness": None,
            "review_frame_center_contrast": None,
            "review_frame_center_brightness_values": [],
            "review_frame_center_contrast_values": [],
            "review_title_frame_count": 0,
            "review_frame_title_contrast": None,
            "review_frame_title_dark_ratio": None,
            "review_frame_title_bright_ratio": None,
            "review_frame_title_contrast_values": [],
            "review_frame_title_dark_ratio_values": [],
            "review_frame_title_bright_ratio_values": [],
            "review_subtitle_frame_count": 0,
            "review_frame_caption_contrast": None,
            "review_frame_caption_dark_ratio": None,
            "review_frame_caption_bright_ratio": None,
            "review_frame_caption_contrast_values": [],
            "review_frame_caption_dark_ratio_values": [],
            "review_frame_caption_bright_ratio_values": [],
            "review_frame_motion_scores": [],
            "review_frame_average_motion_score": None,
            "review_audio_peak": None,
            "review_audio_rms": None,
            "review_warnings": [f"review_failed:{type(exc).__name__}"],
            "review_quality_pass": False,
            "review_archive_status": "needs_review",
            "review_used_temp_copy": False,
        }

    archive_status = review_archive_status(review)
    return {
        "duration": review["duration"],
        "size": review["size"],
        "fps": review["fps"],
        "review_file_size_bytes": review["review_file_size_bytes"],
        "frame_path": review["frame_path"],
        "review_frame_timestamp": review["review_frame_timestamp"],
        "review_frame_paths": review["review_frame_paths"],
        "review_frame_timestamps": review["review_frame_timestamps"],
        "review_sheet_path": review["review_sheet_path"],
        "review_sheet_frame_count": review["review_sheet_frame_count"],
        "review_frame_brightness": review["review_frame_brightness"],
        "review_frame_contrast": review["review_frame_contrast"],
        "review_frame_brightness_values": review["review_frame_brightness_values"],
        "review_frame_contrast_values": review["review_frame_contrast_values"],
        "review_frame_center_brightness": review["review_frame_center_brightness"],
        "review_frame_center_contrast": review["review_frame_center_contrast"],
        "review_frame_center_brightness_values": review["review_frame_center_brightness_values"],
        "review_frame_center_contrast_values": review["review_frame_center_contrast_values"],
        "review_title_frame_count": review["review_title_frame_count"],
        "review_frame_title_contrast": review["review_frame_title_contrast"],
        "review_frame_title_dark_ratio": review["review_frame_title_dark_ratio"],
        "review_frame_title_bright_ratio": review["review_frame_title_bright_ratio"],
        "review_frame_title_contrast_values": review["review_frame_title_contrast_values"],
        "review_frame_title_dark_ratio_values": review["review_frame_title_dark_ratio_values"],
        "review_frame_title_bright_ratio_values": review["review_frame_title_bright_ratio_values"],
        "review_subtitle_frame_count": review["review_subtitle_frame_count"],
        "review_frame_caption_contrast": review["review_frame_caption_contrast"],
        "review_frame_caption_dark_ratio": review["review_frame_caption_dark_ratio"],
        "review_frame_caption_bright_ratio": review["review_frame_caption_bright_ratio"],
        "review_frame_caption_contrast_values": review["review_frame_caption_contrast_values"],
        "review_frame_caption_dark_ratio_values": review["review_frame_caption_dark_ratio_values"],
        "review_frame_caption_bright_ratio_values": review["review_frame_caption_bright_ratio_values"],
        "review_frame_motion_scores": review["review_frame_motion_scores"],
        "review_frame_average_motion_score": review["review_frame_average_motion_score"],
        "review_audio_peak": review["review_audio_peak"],
        "review_audio_rms": review["review_audio_rms"],
        "review_warnings": review["review_warnings"],
        "review_quality_pass": review["review_quality_pass"],
        "review_archive_status": archive_status,
        "review_used_temp_copy": review["used_temp_copy"],
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
            "출시설",
            "rumored",
            "expected release",
            "what to expect",
            "delay",
            "delayed",
            "postpone",
            "postponed",
            "연기",
            "지연",
            "무기한",
            "기관 대상",
            "장외",
            "예측시장",
            "트레이딩",
            "데스크",
            "거래소",
            "거래",
            "투자",
            "펀드",
            "증권",
            "금융",
            "신용카드",
            "체크카드",
            "제휴 카드",
            "카드사",
            "삼성카드",
            "롯데카드",
            "현대카드",
            "결제금액",
            "홈쇼핑",
            "credit card",
            "payment card",
            "card issuer",
            "stock",
            "trading",
            "prediction market",
            "exchange",
            "fund",
        ],
    )
    if has_blocked_term:
        return False
    if event_type == "product_launch":
        return True
    # Certification rows can still be launchable when the title is about a real
    # preorder/sale opening; the ranker may classify them as certification first.
    if event_type == "certification" and has_launch_term and _contains_any(text, ["사전예약", "사전 예약", "예약", "preorder", "pre-order", "판매"]):
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
    return load_history(UPLOAD_HISTORY)


def _is_product_launch_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return normalized in {"product_launch", "launch", "new_product"}


def _collect_articles_for_topic(limit: int, topic: str) -> list[Any]:
    if _is_product_launch_topic(topic):
        print("PRODUCT_LAUNCH_SOURCE_MODE=dedicated", flush=True)
        return collect_product_launch_news(limit=limit)
    return collect_ranked_news(limit=limit)


def _history_keys(history: list[dict]) -> tuple[set[str], set[str]]:
    used_urls: set[str] = set()
    used_titles: set[str] = set()
    for item in history:
        if not isinstance(item, dict):
            continue
        used_urls.update(article_urls(item))
        title = article_title(item)
        if title:
            used_titles.add(title)
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


def _is_dedicated_product_launch_archive_source(article: dict[str, Any]) -> bool:
    source = _norm(_article_get(article, "source_name", ""))
    return (
        "product launch" in source
        or "product_launch" in source
        or "product news" in source
        or "제품 출시" in source
    )


def _archive_fallback_candidates(limit: int, topic: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ARCHIVE_DB.exists():
        return []

    init_archive(ARCHIVE_DB)
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
        reason = duplicate_reason(_article_to_dict(article), history)
        if reason:
            print(f"SKIP_ARCHIVE_DUPLICATE|match={reason}|title={_article_get(article, 'title', '')}", flush=True)
            continue
        if not topic and _is_dedicated_product_launch_archive_source(article):
            continue
        if topic and not matches_requested_topic(article, topic):
            continue
        candidates.append(article)
    return candidates


def select_next_article(limit: int, topic: str = "") -> Any:
    articles = _collect_articles_for_topic(limit=limit, topic=topic)
    with file_lock(UPLOAD_HISTORY_LOCK):
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
        reason = duplicate_reason(_article_to_dict(article), history)
        if reason == "url" or (url and url in used_urls):
            print(f"SKIP_ALREADY_UPLOADED|match=url|title={_article_get(article, 'title', '')}", flush=True)
            continue
        if reason == "title_similarity" or (title and title in used_titles):
            print(f"SKIP_ALREADY_UPLOADED|match=title_similarity|title={_article_get(article, 'title', '')}", flush=True)
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

    fallback_candidates = _archive_fallback_candidates(limit, topic, history)
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
    global _LOCK_OWNER_TOKEN
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    owner_token = f"{os.getpid()}:{time.time_ns()}"
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
            started_at = int(lock.get("started_at", 0))
            stale_owner_token = str(lock.get("owner_token", ""))
            stale_mtime_ns = LOCK_FILE.stat().st_mtime_ns
        except Exception:
            stale_owner_token = ""
            try:
                stale_mtime_ns = LOCK_FILE.stat().st_mtime_ns
            except FileNotFoundError:
                return acquire_lock(lock_ttl_minutes)
            started_at = int(stale_mtime_ns / 1_000_000_000)
        age = _now() - started_at
        if age < lock_ttl_minutes * 60:
            print(f"LOCK_ACTIVE|age_seconds={age}|path={LOCK_FILE}", flush=True)
            return False
        print(f"LOCK_STALE|age_seconds={age}|path={LOCK_FILE}", flush=True)
        try:
            if stale_owner_token:
                current_lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
                if current_lock.get("owner_token") != stale_owner_token:
                    return acquire_lock(lock_ttl_minutes)
            elif LOCK_FILE.stat().st_mtime_ns != stale_mtime_ns:
                return acquire_lock(lock_ttl_minutes)
            LOCK_FILE.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            print(f"LOCK_STALE_UNLINK_SKIPPED|reason=owner_check_failed|path={LOCK_FILE}", flush=True)
            return False
        return acquire_lock(lock_ttl_minutes)
    with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
        json.dump(
            {"pid": os.getpid(), "started_at": _now(), "owner_token": owner_token},
            lock_file,
            ensure_ascii=False,
            indent=2,
        )
    _LOCK_OWNER_TOKEN = owner_token
    return True


def release_lock() -> None:
    global _LOCK_OWNER_TOKEN
    if not _LOCK_OWNER_TOKEN:
        return
    try:
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _LOCK_OWNER_TOKEN = None
        return
    except Exception:
        print(f"LOCK_RELEASE_SKIPPED|reason=unreadable_lock|path={LOCK_FILE}", flush=True)
        return
    if lock.get("owner_token") != _LOCK_OWNER_TOKEN:
        print(f"LOCK_RELEASE_SKIPPED|reason=owner_changed|path={LOCK_FILE}", flush=True)
        _LOCK_OWNER_TOKEN = None
        return
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass
    finally:
        _LOCK_OWNER_TOKEN = None


def write_single_item_manifest(article: Any, video_path: str, youtube: Any) -> Path:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    RUN_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    resolved_video_path = str(Path(video_path).resolve())
    script = getattr(youtube, "script", "")
    images = list(getattr(youtube, "images", []))
    subtitle_path = getattr(youtube, "subtitles_path", "")
    review_fields = _video_review_fields(resolved_video_path, subtitle_path=subtitle_path)
    structure_fields = build_structure_quality_fields(
        script=script,
        images=images,
        image_prompts=list(getattr(youtube, "image_prompts", [])),
        duration=review_fields["duration"],
        metadata=getattr(youtube, "metadata", {}),
        subtitle_path=subtitle_path,
        validate_image_files=True,
        subtitle_max_chars=get_subtitle_max_chars(),
        placeholder_visuals_used=bool(getattr(youtube, "has_placeholder_visuals", False)),
        placeholder_visual_reasons=list(getattr(youtube, "placeholder_visual_reasons", [])),
    )
    review_fields["review_archive_status"] = review_archive_status(review_fields, structure_fields)
    review_fields["overall_quality_pass"] = (
        review_fields["review_quality_pass"] and structure_fields["structure_quality_pass"]
    )
    manifest_item = {
        "rank": 1,
        "article_title": _article_get(article, "title", ""),
        "article_url": _article_get(article, "url", ""),
        "article_id": _article_get(article, "id", ""),
        "source": _article_get(article, "source_name", ""),
        "score": _article_get(article, "shorts_score", _article_get(article, "score", None)),
        "topic_bucket": _article_get(article, "topic_bucket", ""),
        "video_path": resolved_video_path,
        "metadata": getattr(youtube, "metadata", {}),
        "script": script,
        "images": images,
        "article": _article_to_dict(article),
    }
    manifest_item.update(review_fields)
    manifest_item.update(structure_fields)
    run_manifest = RUN_MANIFEST_DIR / f"manifest_{int(time.time())}_{os.getpid()}.json"
    atomic_write_json(run_manifest, [manifest_item])
    atomic_write_json(
        LATEST_MANIFEST,
        {"manifest": str(run_manifest), "updated_at_unix": time.time()},
    )
    print(f"MANIFEST={run_manifest}", flush=True)
    print(f"LATEST_MANIFEST_POINTER={LATEST_MANIFEST}", flush=True)
    return run_manifest


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
            "UPDATE_UPLOAD_HISTORY": "1",
            "UPDATE_ARCHIVE_STATUS": "1",
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

    visibility = os.environ.get("SHORTS_JOB_VISIBILITY", "unlisted").strip().lower()
    if visibility not in {"public", "unlisted"}:
        raise ValueError("SHORTS_JOB_VISIBILITY must be public or unlisted")
    if visibility == "public" and os.environ.get("ALLOW_PUBLIC_UPLOAD", "").strip().lower() not in {"1", "true", "yes"}:
        print("PUBLIC_UPLOAD_NOT_ALLOWED|fallback_visibility=unlisted", flush=True)
        visibility = "unlisted"

    dry_run = os.environ.get("SHORTS_JOB_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
    news_limit = _read_positive_int_env("NEWS_LIMIT", 50)
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

    with file_lock(UPLOAD_HISTORY_LOCK):
        reason = duplicate_reason(_article_to_dict(article), load_upload_history())
    if reason:
        print(f"SKIP_RENDER_DUPLICATE_BEFORE_GENERATION|match={reason}|title={_article_get(article, 'title', '')}", flush=True)
        return 0

    youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
    video_path = youtube.generate_video_from_news(TTS(), article)
    print(f"GENERATED_VIDEO={video_path}", flush=True)

    with file_lock(UPLOAD_HISTORY_LOCK):
        reason = duplicate_reason(_article_to_dict(article), load_upload_history())
    if reason:
        print(f"SKIP_UPLOAD_DUPLICATE_AFTER_GENERATION|match={reason}|title={_article_get(article, 'title', '')}", flush=True)
        return 0

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
    lock_ttl_minutes = _read_positive_int_env("SHORTS_JOB_LOCK_TTL_MINUTES", 110)
    if not acquire_lock(lock_ttl_minutes):
        return 0
    try:
        return run_job()
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
