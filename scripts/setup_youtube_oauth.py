#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from youtube_api.auth import (  # noqa: E402
    CLIENT_SECRET_PATH,
    READONLY_SCOPES,
    get_credentials,
    print_token_status,
    youtube_data_service,
)

EXPECTED_CHANNEL_ID = "UCcDkCUSZbX6EUPIqtVhRGyQ"


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
    if EXPECTED_CHANNEL_ID not in active_ids:
        print(
            "\nWARNING: OAuth succeeded, but the authorized channel does not look like "
            f"IT한 하루 ({EXPECTED_CHANNEL_ID})."
        )
        print("If this is the wrong Google/brand channel, delete the token and rerun OAuth:")
        print("  rm -f secrets/youtube_oauth_token.json")
        return 3

    print("\nOK: Authorized channel matches IT한 하루.")
    print_token_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
