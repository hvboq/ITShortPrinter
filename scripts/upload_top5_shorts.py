from __future__ import annotations

import json
import os
import time
from pathlib import Path

from classes.YouTube import YouTube
from project_paths import project_root, youtube_firefox_profile
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from youtube_studio import UPLOAD_URL
from youtube_studio import advance_upload_steps
from youtube_studio import capture_latest_video_url_from_shorts_page
from youtube_studio import capture_video_url
from youtube_studio import clean_description
from youtube_studio import clean_title
from youtube_studio import click_publish_or_done
from youtube_studio import fill_upload_metadata
from youtube_studio import prepare_upload_video_file
from youtube_studio import select_not_made_for_kids
from youtube_studio import select_visibility
from youtube_studio import studio_channel_url
from youtube_studio import studio_upload_url
from youtube_studio import verify_expected_studio_channel

ROOT = project_root()
PROFILE = youtube_firefox_profile()
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
STAGING_DIR = Path(os.environ.get("UPLOAD_STAGING_DIR", str(MANIFEST.parent / "upload_files")))

VISIBILITY = "unlisted"

print("UPLOAD_TOP5_START", flush=True)
print("UPLOAD_SOURCE_MANIFEST=", str(MANIFEST), flush=True)
data = json.loads(MANIFEST.read_text(encoding="utf-8"))
for idx, item in enumerate(data, 1):
    if "rank" not in item:
        item["rank"] = item.get("batch_index") or idx
start_rank = int(os.environ.get("START_RANK", "1"))
end_rank = int(os.environ.get("END_RANK", "999"))
data = [item for item in data if start_rank <= int(item.get("rank", 0)) <= end_rank]
print("UPLOAD_RANK_RANGE=", start_rank, end_rank, "COUNT=", len(data), flush=True)
y = YouTube("it-han-haru", "IT한 하루", PROFILE, "Korean IT News", "Korean")
d = y.browser
results = []

try:
    d.set_page_load_timeout(180)
    expected_channel_name = os.environ.get("EXPECTED_YOUTUBE_CHANNEL_NAME", "IT한 하루")
    expected_channel_id = os.environ.get("EXPECTED_YOUTUBE_CHANNEL_ID", "UCcDkCUSZbX6EUPIqtVhRGyQ")
    d.get(studio_channel_url(expected_channel_id))
    time.sleep(10)
    print("STUDIO_TITLE=", d.title, flush=True)
    print("STUDIO_URL=", d.current_url, flush=True)
    verify_expected_studio_channel(d, expected_channel_id, expected_channel_name)

    for item in data:
        rank = item["rank"]
        title = clean_title(
            item.get("metadata", {}).get("title") or item.get("article_title")
        )
        if not title:
            raise ValueError(f"Rank {rank} has no safe human-readable title")
        video_path = prepare_upload_video_file(item["video_path"], title, STAGING_DIR)
        desc = clean_description(item.get("metadata", {}).get("description") or "")
        print(f"UPLOAD_{rank}_START|path={video_path}|title={title}", flush=True)

        d.get(studio_upload_url(expected_channel_id))
        if "404" in d.title or "not found" in d.title.lower():
            d.get(UPLOAD_URL)
        WebDriverWait(d, 120).until(
            EC.presence_of_element_located((By.TAG_NAME, "ytcp-uploads-file-picker"))
        )
        file_picker = d.find_element(By.TAG_NAME, "ytcp-uploads-file-picker")
        file_input = file_picker.find_element(By.TAG_NAME, "input")
        file_input.send_keys(video_path)

        fill_upload_metadata(d, title, desc)
        select_not_made_for_kids(d)
        advance_upload_steps(d, rank)

        if not select_visibility(d, VISIBILITY, timeout=10):
            raise RuntimeError("Could not select Unlisted visibility")
        print(f"UPLOAD_{rank}_VISIBILITY_UNLISTED", flush=True)
        time.sleep(1)

        if not click_publish_or_done(d, "DONE"):
            raise RuntimeError("Could not click Done button")
        print(f"UPLOAD_{rank}_DONE_CLICKED", flush=True)
        time.sleep(8)

        screenshot = str(SCREEN_DIR / f"upload_rank{rank}_done.png")
        d.save_screenshot(screenshot)

        url = capture_video_url(d)
        if not url:
            url = capture_latest_video_url_from_shorts_page(d)

        result = {
            "rank": rank,
            "video_path": video_path,
            "title": title,
            "description": desc,
            "visibility": VISIBILITY,
            "uploaded_url": url,
            "screenshot": screenshot,
            "source_video_path": item["video_path"],
        }
        results.append(result)
        UPLOAD_MANIFEST.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"UPLOAD_{rank}_DONE|url={url}", flush=True)
        time.sleep(3)

finally:
    try:
        d.quit()
    except Exception:
        pass

print("UPLOAD_TOP5_DONE", flush=True)
print("UPLOAD_MANIFEST=", str(UPLOAD_MANIFEST), flush=True)
