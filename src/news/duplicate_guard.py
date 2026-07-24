from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TITLE_SIMILARITY_THRESHOLD = 0.90
TITLE_TOKEN_OVERLAP_THRESHOLD = 0.82
PENDING_UPLOAD_STALE_SECONDS = 6 * 60 * 60
_LOCK_STALE_SECONDS = 10 * 60
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src"}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def normalize_title(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[\[\]【】()（）{}<>〈〉:：|｜,，.!?！？'\"“”‘’]", " ", text)
    return " ".join(text.split())


def canonicalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return normalize_text(raw).rstrip("/")
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    query_items = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        key_l = key.lower()
        if key_l in _TRACKING_QUERY_KEYS or any(key_l.startswith(prefix) for prefix in _TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key_l, val))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def article_urls(item: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for key in ("article_url", "canonical_url", "url", "source_url", "link"):
        url = canonicalize_url(item.get(key))
        if url:
            urls.add(url)
    article = item.get("article")
    if isinstance(article, dict):
        urls.update(article_urls(article))
    return urls


def article_title(item: dict[str, Any]) -> str:
    for key in ("article_title", "title"):
        title = normalize_title(item.get(key))
        if title:
            return title
    article = item.get("article")
    if isinstance(article, dict):
        return article_title(article)
    return ""


def titles_similar(left: str, right: str) -> bool:
    left = normalize_title(left)
    right = normalize_title(right)
    if not left or not right:
        return False
    if left == right:
        return True
    if SequenceMatcher(None, left, right).ratio() >= TITLE_SIMILARITY_THRESHOLD:
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return overlap >= TITLE_TOKEN_OVERLAP_THRESHOLD


def is_stale_pending_upload(
    item: dict[str, Any],
    *,
    now: float | None = None,
    stale_seconds: int = PENDING_UPLOAD_STALE_SECONDS,
) -> bool:
    """Return whether a pending-upload reservation is too old to block reuse."""
    if item.get("upload_status") != "pending_upload":
        return False
    try:
        reserved_at = float(item.get("reserved_at_unix") or 0)
    except (TypeError, ValueError):
        reserved_at = 0
    if reserved_at <= 0:
        return True
    return (time.time() if now is None else now) - reserved_at > stale_seconds


def active_history_items(
    items: Iterable[dict[str, Any]],
    *,
    now: float | None = None,
    stale_seconds: int = PENDING_UPLOAD_STALE_SECONDS,
) -> list[dict[str, Any]]:
    """Drop stale pending-upload reservations from duplicate comparisons."""
    active: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if is_stale_pending_upload(item, now=now, stale_seconds=stale_seconds):
            continue
        active.append(item)
    return active


def duplicate_reason(candidate: dict[str, Any], existing_items: Iterable[dict[str, Any]]) -> str | None:
    candidate_urls = article_urls(candidate)
    candidate_title = article_title(candidate)
    for item in active_history_items(existing_items):
        existing_urls = article_urls(item)
        if candidate_urls and existing_urls and candidate_urls & existing_urls:
            return "url"
        existing_title = article_title(item)
        if candidate_title and existing_title and titles_similar(candidate_title, existing_title):
            return "title_similarity"
    return None


def load_history(history_path: Path) -> list[dict[str, Any]]:
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Upload history is unreadable: {history_path}") from exc
    if not isinstance(data, list):
        raise ValueError(f"Upload history must contain a list: {history_path}")
    return data


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def write_history(history_path: Path, history: list[dict[str, Any]]) -> None:
    atomic_write_json(history_path, history)


@contextmanager
def file_lock(lock_path: Path, stale_seconds: int = _LOCK_STALE_SECONDS):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "created_at": time.time()}).encode("utf-8"))
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > stale_seconds:
                try:
                    lock_path.unlink()
                    continue
                except FileNotFoundError:
                    continue
            time.sleep(0.2)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
