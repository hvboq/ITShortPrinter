from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "news_archive.sqlite3"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def normalize_text(value: object) -> str:
    """Return compact plain text suitable for durable article summaries/search."""
    if value is None:
        return ""
    text = str(value)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ")
    return _WS_RE.sub(" ", text).strip()


def normalize_key(value: object) -> str:
    """Return a case-insensitive dedupe/search key for URLs and titles."""
    return normalize_text(value).lower()


def summarize_article(article: dict, max_chars: int = 1200) -> str:
    """Build a lightweight saved summary from collected RSS article fields.

    This intentionally uses already-collected metadata/excerpts rather than making
    extra full-page requests, so cron collection stays cheap and low-risk.
    """
    excerpt = normalize_text(article.get("raw_excerpt") or article.get("summary") or article.get("description"))
    title = normalize_text(article.get("title"))
    if excerpt:
        summary = excerpt
    else:
        summary = title
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


def _json_dumps(value: object) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, sort_keys=True)


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init_archive(db_path: str | Path | None = None) -> Path:
    """Create the article archive DB/table if needed and return its path."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    with _connect(path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                canonical_url TEXT,
                url TEXT,
                title TEXT NOT NULL,
                source_id TEXT,
                source_name TEXT,
                source_tier TEXT,
                language TEXT,
                published_at TEXT,
                fetched_at TEXT,
                archived_at TEXT NOT NULL,
                author TEXT,
                raw_excerpt TEXT,
                content_summary TEXT,
                brands_json TEXT,
                technologies_json TEXT,
                event_type TEXT,
                confidence REAL,
                feasibility_score INTEGER,
                popularity_score INTEGER,
                virality_score INTEGER,
                llm_score INTEGER,
                shorts_score INTEGER,
                alert_allowed INTEGER,
                rumor_status TEXT,
                shorts_video_status TEXT NOT NULL DEFAULT 'not_generated',
                shorts_selected_at TEXT,
                shorts_generated_at TEXT,
                shorts_uploaded_at TEXT,
                shorts_video_path TEXT,
                shorts_uploaded_url TEXT,
                shorts_rank INTEGER,
                payload_json TEXT NOT NULL
            )
            """
        )
        existing_columns = {row[1] for row in con.execute("PRAGMA table_info(articles)").fetchall()}
        migrations = {
            "shorts_video_status": "ALTER TABLE articles ADD COLUMN shorts_video_status TEXT NOT NULL DEFAULT 'not_generated'",
            "shorts_selected_at": "ALTER TABLE articles ADD COLUMN shorts_selected_at TEXT",
            "shorts_generated_at": "ALTER TABLE articles ADD COLUMN shorts_generated_at TEXT",
            "shorts_uploaded_at": "ALTER TABLE articles ADD COLUMN shorts_uploaded_at TEXT",
            "shorts_video_path": "ALTER TABLE articles ADD COLUMN shorts_video_path TEXT",
            "shorts_uploaded_url": "ALTER TABLE articles ADD COLUMN shorts_uploaded_url TEXT",
            "shorts_rank": "ALTER TABLE articles ADD COLUMN shorts_rank INTEGER",
        }
        for column, sql in migrations.items():
            if column not in existing_columns:
                con.execute(sql)
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_archived_at ON articles(archived_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_source_id ON articles(source_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_shorts_score ON articles(shorts_score)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_canonical_url ON articles(canonical_url)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_shorts_video_status ON articles(shorts_video_status)")
    return path


def existing_article_keys(db_path: str | Path | None = None) -> dict[str, set[str]]:
    """Load existing archive keys so collection can skip duplicates before saving."""
    path = init_archive(db_path)
    keys = {"ids": set(), "urls": set(), "titles": set()}
    with _connect(path) as con:
        for article_id, canonical_url, url, title in con.execute(
            "SELECT id, canonical_url, url, title FROM articles"
        ):
            if article_id:
                keys["ids"].add(str(article_id))
            for value in (canonical_url, url):
                key = normalize_key(value)
                if key:
                    keys["urls"].add(key)
            title_key = normalize_key(title)
            if title_key:
                keys["titles"].add(title_key)
    return keys


def article_matches_existing_keys(article: dict, keys: dict[str, set[str]]) -> bool:
    """Return True when article URL/title/id is already present in archive keys."""
    article_id = article.get("id")
    if article_id and str(article_id) in keys.get("ids", set()):
        return True
    for field in ("canonical_url", "url", "article_url"):
        url_key = normalize_key(article.get(field))
        if url_key and url_key in keys.get("urls", set()):
            return True
    for field in ("title", "article_title"):
        title_key = normalize_key(article.get(field))
        if title_key and title_key in keys.get("titles", set()):
            return True
    return False


def archive_articles(articles: Iterable[dict], db_path: str | Path | None = None) -> int:
    """Upsert collected/scored articles into the durable SQLite archive.

    Returns the number of records attempted. Existing IDs are updated so ranking
    scores and summaries stay fresh while preserving a single row per article.
    """
    items = list(articles)
    if not items:
        init_archive(db_path)
        return 0

    path = init_archive(db_path)
    archived_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for article in items:
        article_id = str(article.get("id") or article.get("canonical_url") or article.get("url") or article.get("title"))
        payload = dict(article)
        summary = summarize_article(payload)
        rows.append(
            {
                "id": article_id,
                "canonical_url": payload.get("canonical_url") or payload.get("url"),
                "url": payload.get("url") or payload.get("canonical_url"),
                "title": normalize_text(payload.get("title")) or "(untitled)",
                "source_id": payload.get("source_id"),
                "source_name": payload.get("source_name"),
                "source_tier": payload.get("source_tier"),
                "language": payload.get("language"),
                "published_at": payload.get("published_at"),
                "fetched_at": payload.get("fetched_at"),
                "archived_at": archived_at,
                "author": payload.get("author"),
                "raw_excerpt": normalize_text(payload.get("raw_excerpt")),
                "content_summary": summary,
                "brands_json": _json_dumps(payload.get("brands")),
                "technologies_json": _json_dumps(payload.get("technologies")),
                "event_type": payload.get("event_type"),
                "confidence": payload.get("confidence"),
                "feasibility_score": payload.get("feasibility_score"),
                "popularity_score": payload.get("popularity_score"),
                "virality_score": payload.get("virality_score"),
                "llm_score": payload.get("llm_score"),
                "shorts_score": payload.get("shorts_score"),
                "alert_allowed": 1 if payload.get("alert_allowed") else 0,
                "rumor_status": payload.get("rumor_status"),
                "shorts_video_status": payload.get("shorts_video_status") or "not_generated",
                "shorts_selected_at": payload.get("shorts_selected_at"),
                "shorts_generated_at": payload.get("shorts_generated_at"),
                "shorts_uploaded_at": payload.get("shorts_uploaded_at"),
                "shorts_video_path": payload.get("shorts_video_path"),
                "shorts_uploaded_url": payload.get("shorts_uploaded_url"),
                "shorts_rank": payload.get("shorts_rank"),
                "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
            }
        )

    columns = list(rows[0].keys())
    placeholders = ", ".join(f":{column}" for column in columns)
    updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    sql = f"""
        INSERT INTO articles ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {updates}
    """
    with _connect(path) as con:
        con.executemany(sql, rows)
    return len(rows)


def prune_daily_top_articles(
    *,
    per_day_limit: int = 50,
    keep_ties: bool = True,
    db_path: str | Path | None = None,
) -> int:
    """Delete low-ranked archived articles while preserving each day's top candidates.

    The default policy keeps all rows at or above the 50th-ranked score per
    fetched day. This can retain slightly more than 50 rows on days where the
    50th place is tied, avoiding arbitrary deletion of equal-score candidates.

    Rows that have already entered the Shorts lifecycle are never deleted.
    """
    if per_day_limit < 1:
        raise ValueError("per_day_limit must be >= 1")

    path = init_archive(db_path)
    with _connect(path) as con:
        if keep_ties:
            sql = """
                WITH ranked AS (
                    SELECT id, date(fetched_at) AS d, shorts_score,
                           ROW_NUMBER() OVER (
                               PARTITION BY date(fetched_at)
                               ORDER BY shorts_score DESC, id ASC
                           ) AS rn
                    FROM articles
                ), thresholds AS (
                    SELECT d, shorts_score AS threshold_score
                    FROM ranked
                    WHERE rn = ?
                ), delete_ids AS (
                    SELECT r.id
                    FROM ranked r
                    JOIN thresholds t USING(d)
                    JOIN articles a ON a.id = r.id
                    WHERE r.shorts_score < t.threshold_score
                      AND a.shorts_video_status = 'not_generated'
                )
                DELETE FROM articles WHERE id IN (SELECT id FROM delete_ids)
            """
        else:
            sql = """
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY date(fetched_at)
                               ORDER BY shorts_score DESC, id ASC
                           ) AS rn
                    FROM articles
                ), delete_ids AS (
                    SELECT r.id
                    FROM ranked r
                    JOIN articles a ON a.id = r.id
                    WHERE r.rn > ?
                      AND a.shorts_video_status = 'not_generated'
                )
                DELETE FROM articles WHERE id IN (SELECT id FROM delete_ids)
            """
        before = con.total_changes
        con.execute(sql, (per_day_limit,))
        return con.total_changes - before


def article_lookup_keys(article: dict) -> tuple[str | None, str | None, str | None]:
    """Return archive lookup keys: id, canonical/url, title."""
    article_id = article.get("id")
    url = article.get("canonical_url") or article.get("url") or article.get("article_url")
    title = article.get("title") or article.get("article_title")
    return (
        str(article_id) if article_id else None,
        str(url) if url else None,
        normalize_key(title) if title else None,
    )


def mark_shorts_status(
    article: dict,
    status: str,
    *,
    rank: int | None = None,
    video_path: str | None = None,
    uploaded_url: str | None = None,
    timestamp: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Mark whether an archived article has been selected/generated/uploaded as a Short."""
    init_archive(db_path)
    article_id, url, title = article_lookup_keys(article)
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    timestamp_column = {
        "selected": "shorts_selected_at",
        "generated": "shorts_generated_at",
        "uploaded": "shorts_uploaded_at",
    }.get(status)

    set_parts = ["shorts_video_status = ?"]
    params: list[object] = [status]
    if timestamp_column:
        set_parts.append(f"{timestamp_column} = ?")
        params.append(timestamp)
    if rank is not None:
        set_parts.append("shorts_rank = ?")
        params.append(rank)
    if video_path:
        set_parts.append("shorts_video_path = ?")
        params.append(video_path)
    if uploaded_url:
        set_parts.append("shorts_uploaded_url = ?")
        params.append(uploaded_url)

    where_parts = []
    where_params: list[object] = []
    if article_id:
        where_parts.append("id = ?")
        where_params.append(article_id)
    if url:
        where_parts.append("canonical_url = ? OR url = ?")
        where_params.extend([url, url])
    if title:
        where_parts.append("lower(title) = ?")
        where_params.append(title)
    if not where_parts:
        return 0

    sql = f"UPDATE articles SET {', '.join(set_parts)} WHERE {' OR '.join(f'({part})' for part in where_parts)}"
    with _connect(db_path) as con:
        cur = con.execute(sql, params + where_params)
        return cur.rowcount


def recent_articles(limit: int = 20, db_path: str | Path | None = None) -> list[dict]:
    """Return recent archived article rows as dictionaries for quick inspection."""
    path = init_archive(db_path)
    with _connect(path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT id, title, source_name, canonical_url, published_at, archived_at,
                   content_summary, shorts_score, event_type, brands_json, technologies_json,
                   shorts_video_status, shorts_rank, shorts_video_path, shorts_uploaded_url
            FROM articles
            ORDER BY archived_at DESC, shorts_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
