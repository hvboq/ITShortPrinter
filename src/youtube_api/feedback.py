"""Pure, upload-free helpers for delayed Shorts performance feedback."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _video_id(video: dict[str, Any]) -> str:
    return str(video.get("video_id") or video.get("id") or "").strip()


def require_expected_channel(actual_channel_id: str, expected_channel_id: str) -> None:
    """Fail closed before analytics collection when OAuth targets another channel."""
    actual = str(actual_channel_id or "").strip()
    expected = str(expected_channel_id or "").strip()
    if not expected:
        raise RuntimeError("Expected YouTube channel ID is not configured.")
    if actual != expected:
        raise RuntimeError(f"Authorized YouTube channel mismatch: expected {expected}, got {actual or 'none'}.")


def query_analytics_or_pending(fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Treat transient Analytics server failures as pending; fail closed on auth/client errors."""
    try:
        return fetch()
    except Exception as exc:
        status = getattr(getattr(exc, "resp", None), "status", None)
        if isinstance(status, int) and status >= 500:
            return {}
        raise


def infer_topic_bucket_from_title(title: str) -> str:
    """Reuse the production ranker to classify legacy uploads that lack topic metadata."""
    from news.ranker import score_article

    scored = score_article({"title": str(title or ""), "raw_excerpt": "", "source_tier": "news_secondary"})
    return str(scored.get("topic_bucket") or "general_it")


def analytics_date_window(published_at: datetime | str, target_hours: float = 48.0) -> tuple[str, str]:
    """Return a retry-stable Analytics window ending at the target video age."""
    published = _utc(published_at)
    target = published + timedelta(hours=target_hours)
    return published.date().isoformat(), target.date().isoformat()


def merge_48h_snapshots(
    existing: Iterable[dict[str, Any]],
    videos: Iterable[dict[str, Any]],
    analytics_by_video: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    eligibility_hours: float = 48.0,
    maximum_age_hours: float = 72.0,
) -> list[dict[str, Any]]:
    """Capture videos in a bounded window; pending rows may retry after it."""
    now = _utc(now or datetime.now(timezone.utc))
    rows = [dict(row) for row in existing if isinstance(row, dict)]
    positions = {_video_id(row): index for index, row in enumerate(rows) if _video_id(row)}

    for video in videos:
        video_id = _video_id(video)
        published = video.get("published_at") or video.get("publishedAt")
        if not video_id or not published:
            continue
        try:
            age_hours = (now - _utc(published)).total_seconds() / 3600.0
        except (TypeError, ValueError):
            continue
        old_index = positions.get(video_id)
        is_pending_retry = old_index is not None and rows[old_index].get("status") == "analytics_pending"
        if age_hours < eligibility_hours or (age_hours > maximum_age_hours and not is_pending_retry):
            continue
        new_bucket = str(video.get("topic_bucket") or "general_it")
        if old_index is not None and rows[old_index].get("status") == "captured":
            if rows[old_index].get("topic_bucket") in {None, "", "general_it"} and new_bucket != "general_it":
                rows[old_index]["topic_bucket"] = new_bucket
            continue

        analytics_available = video_id in analytics_by_video
        analytics = analytics_by_video.get(video_id) or {}
        row = {
            "video_id": video_id,
            "title": str(video.get("title") or ""),
            "published_at": _utc(published).isoformat(),
            "observed_at": now.isoformat(),
            "target_age_hours": eligibility_hours,
            "actual_age_hours": round(age_hours, 4),
            "topic_bucket": str(video.get("topic_bucket") or "general_it"),
            "status": "captured" if analytics_available else "analytics_pending",
            "trainable": bool(analytics_available and eligibility_hours <= age_hours <= maximum_age_hours),
            "views": int(_number(video.get("views", video.get("viewCount")))),
            "likes": int(_number(video.get("likes", video.get("likeCount")))),
            "comments": int(_number(video.get("comments", video.get("commentCount")))),
            "average_view_percentage": _number(
                analytics.get("average_view_percentage", analytics.get("averageViewPercentage"))
            ),
            "average_view_duration_seconds": _number(
                analytics.get("average_view_duration_seconds", analytics.get("averageViewDuration"))
            ),
        }
        if old_index is None:
            positions[video_id] = len(rows)
            rows.append(row)
        else:
            rows[old_index] = row
    return rows


def build_weekly_feedback(
    snapshots: Iterable[dict[str, Any]],
    *,
    minimum_sample: int = 5,
    shrinkage: float = 10.0,
    min_weight: float = 0.85,
    max_weight: float = 1.15,
) -> dict[str, Any]:
    """Build bounded topic multipliers with minimum samples and prior shrinkage."""
    minimum_sample = max(2, int(minimum_sample))
    shrinkage = max(1.0, float(shrinkage))
    min_weight = max(0.5, min(1.0, float(min_weight)))
    max_weight = max(1.0, min(1.5, float(max_weight)))
    groups: dict[str, list[float]] = {}
    for row in snapshots:
        actual_age = _number(row.get("actual_age_hours"), default=-1.0) if isinstance(row, dict) else -1.0
        if (
            not isinstance(row, dict)
            or row.get("status") != "captured"
            or row.get("trainable") is not True
            or not 48.0 <= actual_age <= 72.0
        ):
            continue
        bucket = str(row.get("topic_bucket") or "general_it")
        views = max(0.0, _number(row.get("views")))
        retention = max(0.0, min(200.0, _number(row.get("average_view_percentage"))))
        likes = max(0.0, _number(row.get("likes")))
        score = math.log1p(views) + retention / 100.0 + min(likes / max(views, 1.0), 0.2) * 5.0
        groups.setdefault(bucket, []).append(score)

    all_scores = [score for scores in groups.values() for score in scores]
    baseline = sum(all_scores) / len(all_scores) if all_scores else 1.0
    runtime_weights: dict[str, float] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for bucket, scores in sorted(groups.items()):
        count = len(scores)
        mean = sum(scores) / count
        if count < minimum_sample or baseline <= 0:
            weight = 1.0
        else:
            confidence = count / (count + shrinkage)
            weight = 1.0 + confidence * (mean / baseline - 1.0)
            weight = min(max_weight, max(min_weight, weight))
        runtime_weights[bucket] = round(weight, 4)
        summaries[bucket] = {"sample_count": count, "mean_quality_score": round(mean, 4)}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "minimum_sample": minimum_sample,
            "shrinkage": shrinkage,
            "min_weight": min_weight,
            "max_weight": max_weight,
        },
        "eligible_sample_count": len(all_scores),
        "runtime_weights": runtime_weights,
        "topic_summary": summaries,
    }


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    """Atomically replace local state so retries remain idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
