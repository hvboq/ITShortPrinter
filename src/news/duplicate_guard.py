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
SEMANTIC_TOPIC_WINDOW_SECONDS = 72 * 60 * 60
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


_TOPIC_STOPWORDS = {
    "a", "an", "as", "at", "for", "in", "of", "on", "the", "to", "with",
    "new", "starts", "start", "started", "begins", "begin", "began", "secured",
    "launch", "launches", "launched", "shipping", "shipments", "ships",
    "새", "신제품", "시작", "개시", "출시", "공개", "발표", "국내", "한국",
}
_CANONICAL_SUBSTITUTIONS = (
    (r"(?:에스케이|sk)[\s-]*하이닉스", "skhynix"),
    (r"sk[\s-]+hynix", "skhynix"),
    (r"삼성(?:전자)?", "samsung"),
    (r"애플", "apple"),
    (r"엔비디아", "nvidia"),
    (r"에이엠디", "amd"),
    (r"아이폰\s*(\d+)", r"iphone \1"),
    (r"갤럭시", "galaxy"),
    (r"라이젠", "ryzen"),
    (r"사전\s*예약|예약\s*판매|pre[\s-]*orders?", " preorderevent "),
    (r"대량\s*생산|양산|mass[\s-]*production", " massproductionevent "),
    (r"리뷰|reviews?", " reviewevent "),
    (r"출시|launch(?:es|ed)?", " launchevent "),
)
_BRAND_TOKENS = {"skhynix", "samsung", "apple", "nvidia", "amd", "intel", "qualcomm"}
_SUPPLIER_BRAND_TOKENS = {"skhynix", "samsung", "amd", "intel", "qualcomm"}
_EVENT_TOKENS = {"preorderevent", "massproductionevent", "reviewevent", "launchevent"}
_MODEL_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:hbm\s*\d+[a-z0-9]*|rtx\s*\d+[a-z0-9]*|gtx\s*\d+[a-z0-9]*|"
    r"iphone\s*\d+[a-z0-9]*|galaxy\s*[sz]\s*\d+[a-z0-9]*|[sz]\s*\d{2}[a-z0-9]*|"
    r"ryzen(?:\s*\d+)?\s*\d{4,5}[a-z0-9]*|\d{4,5}x3d|core\s*ultra\s*\d+[a-z0-9]*|"
    r"m\s*\d+[a-z0-9]*)(?![a-z0-9])",
    re.IGNORECASE,
)


def _canonical_semantic_text(title: str) -> str:
    text = normalize_title(title)
    for pattern, replacement in _CANONICAL_SUBSTITUTIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _model_identifiers(title: str) -> set[str]:
    canonical = _canonical_semantic_text(title)
    return {re.sub(r"\s+", "", match.casefold()) for match in _MODEL_PATTERN.findall(canonical)}


def _topic_tokens(title: str) -> set[str]:
    normalized = _canonical_semantic_text(title)
    return {
        token
        for token in re.findall(r"[a-z0-9가-힣]+", normalized)
        if len(token) > 1 and token not in _TOPIC_STOPWORDS
    }


def _models_conflict(left: str, right: str) -> bool:
    left_models = _model_identifiers(left)
    right_models = _model_identifiers(right)
    return bool(left_models and right_models and left_models.isdisjoint(right_models))


def _semantic_facts_conflict(left: str, right: str) -> bool:
    if _models_conflict(left, right):
        return True
    left_tokens = _topic_tokens(left)
    right_tokens = _topic_tokens(right)
    left_brands = left_tokens & _BRAND_TOKENS
    right_brands = right_tokens & _BRAND_TOKENS
    if left_brands and right_brands and left_brands.isdisjoint(right_brands):
        return True
    left_suppliers = left_brands & _SUPPLIER_BRAND_TOKENS
    right_suppliers = right_brands & _SUPPLIER_BRAND_TOKENS
    if left_suppliers and right_suppliers and left_suppliers.isdisjoint(right_suppliers):
        return True
    left_events = left_tokens & _EVENT_TOKENS
    right_events = right_tokens & _EVENT_TOKENS
    return bool(left_events and right_events and left_events.isdisjoint(right_events))


def semantic_topics_similar(left: str, right: str) -> bool:
    """Deterministic lexical topic match with explicit model/entity/event guards."""
    if _semantic_facts_conflict(left, right):
        return False
    left_tokens = _topic_tokens(left)
    right_tokens = _topic_tokens(right)
    common = left_tokens & right_tokens
    if len(common) < 2:
        return False
    overlap = len(common) / max(1, min(len(left_tokens), len(right_tokens)))
    return len(common) >= 3 and overlap >= 0.50


def _is_recent_topic_item(item: dict[str, Any], now: float) -> bool:
    raw_timestamp = item.get("uploaded_at_unix") or item.get("reserved_at_unix")
    if raw_timestamp in (None, ""):
        # Legacy rows have no timestamp; retain the prior conservative behavior.
        return True
    try:
        timestamp = float(raw_timestamp)
    except (TypeError, ValueError):
        return True
    return now - timestamp <= SEMANTIC_TOPIC_WINDOW_SECONDS


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


def duplicate_reason(
    candidate: dict[str, Any],
    existing_items: Iterable[dict[str, Any]],
    *,
    now: float | None = None,
) -> str | None:
    comparison_time = time.time() if now is None else now
    candidate_urls = article_urls(candidate)
    candidate_title = article_title(candidate)
    for item in active_history_items(existing_items, now=comparison_time):
        existing_urls = article_urls(item)
        if candidate_urls and existing_urls and candidate_urls & existing_urls:
            return "url"
        existing_title = article_title(item)
        if candidate_title and existing_title and _is_recent_topic_item(item, comparison_time):
            if _semantic_facts_conflict(candidate_title, existing_title):
                continue
            if titles_similar(candidate_title, existing_title):
                return "title_similarity"
            if semantic_topics_similar(candidate_title, existing_title):
                return "semantic_topic"
    return None


def load_history(history_path: Path) -> list[dict[str, Any]]:
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


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
