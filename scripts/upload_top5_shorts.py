from __future__ import annotations

import os
from pathlib import Path

from project_paths import project_root
from youtube_api_batch_upload import upload_manifest_with_api

ROOT = project_root()
MANIFEST = Path(
    os.environ.get(
        "UPLOAD_SOURCE_MANIFEST",
        str(ROOT / ".mp" / "batch_top5" / "manifest.json"),
    )
)
UPLOAD_MANIFEST = Path(
    os.environ.get(
        "UPLOAD_OUTPUT_MANIFEST",
        str(MANIFEST.parent / "upload_manifest.json"),
    )
)
SCREEN_DIR = Path(os.environ.get("UPLOAD_SCREEN_DIR", str(MANIFEST.parent / "upload_screens")))
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

# START_RANK and END_RANK are read by youtube_api_batch_upload for partial batch uploads.
VISIBILITY = "unlisted"


if __name__ == "__main__":
    upload_manifest_with_api(
        source_manifest=MANIFEST,
        output_manifest=UPLOAD_MANIFEST,
        visibility=VISIBILITY,
        update_history=False,
        update_archive=False,
        start_label="UPLOAD_TOP5_START",
        done_label="UPLOAD_TOP5_DONE",
    )
