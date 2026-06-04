#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import get_youtube_channel_config  # noqa: E402
from youtube_api.auth import (  # noqa: E402
    CLIENT_SECRET_PATH,
    READONLY_SCOPES,
    get_credentials,
    print_token_status,
    youtube_data_service,
)


def main() -> int:
    print("YouTube OAuth setup for MoneyPrinterV2")
    print("Required OAuth scopes:")
    for scope in READONLY_SCOPES:
        print(f"- {scope}")
    print(f"\nClient secret path: {CLIENT_SECRET_PATH}")

    if not CLIENT_SECRET_PATH.exists():
        print("\nMissing client secret JSON.")
        print("Create a Google Cloud OAuth Desktop client and save the downloaded JSON here:")
        print(f"  {CLIENT_SECRET_PATH}")
        print("\nThen rerun:")
        print("  PYTHONPATH=src venv/bin/python scripts/setup_youtube_oauth.py")
        return 2

    creds = get_credentials(interactive=True)
    print("\nToken saved. Verifying channel identity...")
    youtube = youtube_data_service(creds)
    response = youtube.channels().list(part="id,snippet", mine=True).execute()
    items = response.get("items", [])
    compact = [
        {
            "id": item.get("id"),
            "title": item.get("snippet", {}).get("title"),
            "customUrl": item.get("snippet", {}).get("customUrl"),
        }
        for item in items
    ]
    print(json.dumps({"channels": compact}, ensure_ascii=False, indent=2))

    active_ids = {item.get("id") for item in items}
    channel_config = get_youtube_channel_config()
    expected_channel_id = channel_config["id"]
    expected_channel_name = channel_config["name"]
    if expected_channel_id and expected_channel_id not in active_ids:
        print(
            "\nWARNING: OAuth succeeded, but the authorized channel does not match "
            f"the configured channel ({expected_channel_id})."
        )
        print("If this is the wrong Google/brand channel, delete the token and rerun OAuth:")
        print("  rm -f secrets/youtube_oauth_token.json")
        return 3

    if expected_channel_id:
        print(f"\nOK: Authorized channel matches configured channel {expected_channel_name}.")
    else:
        print("\nOK: OAuth succeeded. Set YOUTUBE_CHANNEL_ID to enforce channel identity checks.")
    print_token_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
