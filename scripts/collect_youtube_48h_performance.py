#!/usr/bin/env python3
"""Collect one idempotent performance snapshot after each Short reaches 48 hours."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from youtube_api.feedback import (  # noqa: E402
    analytics_date_window,
    infer_topic_bucket_from_title,
    load_json,
    merge_48h_snapshots,
    query_analytics_or_pending,
    require_expected_channel,
    write_json_atomic,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "youtube_48h_performance.json"


def _live_inputs(max_videos: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Read Data/Analytics APIs only; deliberately imports no uploader module."""
    from youtube_api.auth import get_credentials, youtube_analytics_service, youtube_data_service

    credentials = get_credentials(interactive=False)
    youtube = youtube_data_service(credentials)
    analytics_service = youtube_analytics_service(credentials)
    channel_response = youtube.channels().list(part="id,contentDetails", mine=True).execute()
    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError("Authorized account returned no YouTube channel.")
    expected_channel_id = os.getenv("EXPECTED_YOUTUBE_CHANNEL_ID", "").strip()
    require_expected_channel(channels[0].get("id", ""), expected_channel_id)
    playlist_id = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    playlist = youtube.playlistItems().list(
        part="contentDetails", playlistId=playlist_id, maxResults=min(max_videos, 50)
    ).execute()
    ids = [item.get("contentDetails", {}).get("videoId") for item in playlist.get("items", [])]
    ids = [video_id for video_id in ids if video_id]
    if not ids:
        return [], {}
    response = youtube.videos().list(part="id,snippet,statistics", id=",".join(ids)).execute()
    videos = []
    analytics: dict[str, dict[str, Any]] = {}
    for item in response.get("items", []):
        video_id = item.get("id")
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt"),
            "topic_bucket": infer_topic_bucket_from_title(snippet.get("title", "")),
            "views": stats.get("viewCount", 0),
            "likes": stats.get("likeCount", 0),
            "comments": stats.get("commentCount", 0),
        })
        published_date, target_date = analytics_date_window(snippet.get("publishedAt"))
        report = query_analytics_or_pending(lambda: analytics_service.reports().query(
            ids="channel==MINE",
            startDate=published_date,
            endDate=target_date,
            metrics="averageViewDuration,averageViewPercentage",
            dimensions="video",
            filters=f"video=={video_id}",
            maxResults=1,
        ).execute())
        rows = report.get("rows", [])
        if rows:
            headers = [header.get("name") for header in report.get("columnHeaders", [])]
            analytics[video_id] = dict(zip(headers, rows[0]))
    return videos, analytics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, idempotent YouTube 48-hour snapshot collector.")
    parser.add_argument("--fixture", type=Path, help="Local JSON with videos and analytics; skips OAuth/API calls.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Snapshot JSON state path.")
    parser.add_argument("--now", help="UTC ISO timestamp override for deterministic fixture runs.")
    parser.add_argument("--max-videos", type=int, default=50, help="Bounded recent-video API limit (1-50).")
    args = parser.parse_args(argv)

    if args.fixture:
        fixture = load_json(args.fixture, {})
        if not isinstance(fixture, dict):
            parser.error("fixture must be a JSON object")
        videos = fixture.get("videos", [])
        analytics = fixture.get("analytics", {})
    else:
        videos, analytics = _live_inputs(max(1, min(50, args.max_videos)))
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    existing = load_json(args.output, [])
    if not isinstance(existing, list):
        existing = []
    merged = merge_48h_snapshots(existing, videos, analytics, now=now)
    write_json_atomic(args.output, merged)
    status = {
        "ok": True,
        "output": str(args.output),
        "records": len(merged),
        "captured": sum(row.get("status") == "captured" for row in merged),
        "analytics_pending": sum(row.get("status") == "analytics_pending" for row in merged),
    }
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
