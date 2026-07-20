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
from news.duplicate_guard import (  # noqa: E402
    active_history_items,
    article_urls,
    duplicate_reason,
    file_lock,
    load_history,
)
from news.ranker import (  # noqa: E402
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
    product_terms = [
        "smartphone", "phone", "iphone", "galaxy", "laptop", "notebook", "pc", "computer",
        "keyboard", "mouse", "headset", "headphone", "earbuds", "wearable", "smartwatch",
        "display", "oled", "gpu", "graphics card", "cpu", "processor", "chip", "chipset",
        "semiconductor", "hbm", "memory", "ssd", "server", "router", "camera", "device",
        "스마트폰", "아이폰", "갤럭시", "노트북", "컴퓨터", "키보드", "마우스", "헤드셋",
        "헤드폰", "이어폰", "웨어러블", "스마트워치", "디스플레이", "그래픽카드", "그래픽 카드",
        "프로세서", "반도체", "메모리", "서버", "공유기", "카메라", "제품",
        "ryzen", "radeon", "rtx", "geforce", "snapdragon", "exynos",
    ]
    evidence_terms = [
        "launch", "launches", "launched", "unveil", "unveils", "unveiled", "released",
        "preorder", "pre-order", "sale starts", "available now", "ships", "shipping", "shipment",
        "mass production", "production starts", "출시", "공개", "사전예약", "사전 예약", "예약 판매",
        "판매 시작", "판매 개시", "출하", "배송 시작", "양산", "대량 생산",
    ]
    blocked_terms = [
        "rumor", "leak", "루머", "유출", "concept", "prototype", "특허", "가능성", "출시설",
        "rumored", "expected release", "what to expect", "delay", "delayed", "postpone", "postponed",
        "연기", "지연", "무기한", "기관 대상", "장외", "예측시장", "트레이딩", "데스크", "거래소",
        "거래", "펀드", "증권", "금융", "신용카드", "체크카드", "제휴 카드", "카드사", "삼성카드",
        "롯데카드", "현대카드", "결제금액", "홈쇼핑", "credit card", "payment card", "card issuer",
        "stock", "trading", "prediction market", "exchange", "fund",
        "driver", "firmware", "benchmark", "vulnerability", "security advisory", "advisory",
        "review", "hands-on", "test result", "durability test", "stress test", "report",
        "드라이버", "펌웨어", "벤치마크", "취약점", "보안 권고", "권고문", "리뷰", "사용기",
        "테스트 결과", "내구성 테스트", "성능 테스트", "보고서",
    ]
    padded_text = f" {text} "
    if _contains_any(text, blocked_terms) or any(
        f" {word} " in padded_text for word in ("test", "tests")
    ):
        return False
    if not _contains_any(text, product_terms) or not _contains_any(text, evidence_terms):
        return False

    allowed_events = {"product_launch", "price_availability"}
    if event_type in allowed_events:
        return True
    if event_type == "certification":
        return _contains_any(text, ["사전예약", "사전 예약", "예약 판매", "preorder", "pre-order", "판매"])
    if event_type == "component_tech":
        return _contains_any(text, ["ships", "shipping", "shipment", "mass production", "production starts", "출하", "양산", "대량 생산"])
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
    # URL reuse is permanent. Title/topic reuse is time-bounded and is therefore
    # handled exclusively by duplicate_reason rather than a permanent title set.
    for item in active_history_items(history):
        used_urls.update(article_urls(item))
    return used_urls, set()


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


def _archive_fallback_candidates(
    limit: int,
    topic: str,
    used_urls: set[str],
    used_titles: set[str],
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not ARCHIVE_DB.exists():
        return []

    canonical_used_urls = set(used_urls)
    for used_url in used_urls:
        canonical_used_urls.update(article_urls({"url": used_url}))

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
        if duplicate_reason(article, history or []):
            continue
        if article_urls(article) & canonical_used_urls or (title and title in used_titles):
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
        if reason in {"title_similarity", "semantic_topic"} or (title and title in used_titles):
            print(f"SKIP_ALREADY_UPLOADED|match={reason or 'title_similarity'}|title={_article_get(article, 'title', '')}", flush=True)
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

    fallback_candidates = _archive_fallback_candidates(
        limit, topic, used_urls, used_titles, history
    )
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
        except Exception:
            started_at = 0
        age = _now() - started_at
        if age < lock_ttl_minutes * 60:
            print(f"LOCK_ACTIVE|age_seconds={age}|path={LOCK_FILE}", flush=True)
            return False
        print(f"LOCK_STALE|age_seconds={age}|path={LOCK_FILE}", flush=True)
        try:
            LOCK_FILE.unlink()
        except FileNotFoundError:
            pass
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
    run_manifest = RUN_MANIFEST_DIR / f"manifest_{int(time.time())}_{os.getpid()}.json"
    run_manifest.write_text(
        json.dumps([manifest_item], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LATEST_MANIFEST.write_text(
        json.dumps({"manifest": str(run_manifest), "updated_at_unix": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
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
    lock_ttl_minutes = int(os.environ.get("SHORTS_JOB_LOCK_TTL_MINUTES", "110"))
    if not acquire_lock(lock_ttl_minutes):
        return 0
    try:
        return run_job()
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
