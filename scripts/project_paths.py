from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the repository root, overridable for Hermes/container workflows."""
    return Path(
        os.environ.get("MONEYPRINTER_ROOT", Path(__file__).resolve().parents[1])
    ).resolve()


def youtube_firefox_profile() -> str:
    """Return the Firefox profile used for YouTube Studio automation."""
    return os.environ.get(
        "YOUTUBE_FIREFOX_PROFILE",
        "/opt/data/firefox-profiles/youtube",
    )
