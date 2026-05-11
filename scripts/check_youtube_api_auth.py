#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from youtube_api.auth import get_credentials, token_status, youtube_analytics_service, youtube_data_service  # noqa: E402

EXPECTED_CHANNEL_ID = "UCcDkCUSZbX6EUPIqtVhRGyQ"


def main() -> int:
    print(json.dumps({"oauth_status": token_status()}, ensure_ascii=False, indent=2))
    creds = get_credentials(interactive=False)

    youtube = youtube_data_service(creds)
    channels = youtube.channels().list(part="id,snippet,statistics,contentDetails", mine=True).execute()
    items = channels.get("items", [])
    compact_channels = []
    for item in items:
        compact_channels.append(
            {
                "id": item.get("id"),
                "title": item.get("snippet", {}).get("title"),
                "customUrl": item.get("snippet", {}).get("customUrl"),
                "statistics": item.get("statistics", {}),
                "uploads_playlist": item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads"),
            }
        )
    print(json.dumps({"channels": compact_channels}, ensure_ascii=False, indent=2))

    active_ids = {item.get("id") for item in items}
    if EXPECTED_CHANNEL_ID not in active_ids:
        print(f"WARNING: Expected channel id not found: {EXPECTED_CHANNEL_ID}")
        return 3

    analytics = youtube_analytics_service(creds)
    # Minimal Analytics smoke query: last 7 complete days is handled by YouTube if data exists.
    # Keep metrics low and non-monetary for read-only validation.
    from datetime import date, timedelta

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=6)
    report = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained",
        dimensions="day",
        sort="day",
    ).execute()
    print(json.dumps({"analytics_smoke_report": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
