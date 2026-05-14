from __future__ import annotations

import json
import time

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
from youtube_studio import click_if_text
from youtube_studio import click_publish_or_done
from youtube_studio import fill_upload_metadata
from youtube_studio import select_not_made_for_kids
from youtube_studio import select_visibility

ROOT = project_root()
PROFILE = youtube_firefox_profile()
MANIFEST = ROOT / ".mp" / "batch_top5" / "manifest.json"
UPLOAD_MANIFEST = ROOT / ".mp" / "batch_top5" / "upload_manifest.json"
SCREEN_DIR = ROOT / ".mp" / "batch_top5" / "upload_screens"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

VISIBILITY = "unlisted"

print("UPLOAD_TOP5_START", flush=True)
data = json.loads(MANIFEST.read_text(encoding="utf-8"))
y = YouTube("it-han-haru", "IT한 하루", PROFILE, "Korean IT News", "Korean")
d = y.browser
results = []

try:
    d.set_page_load_timeout(180)
    d.get("https://studio.youtube.com/")
    time.sleep(10)
    body = d.find_element(By.TAG_NAME, "body").text
    print("STUDIO_TITLE=", d.title, flush=True)
    print("STUDIO_URL=", d.current_url, flush=True)
    print("ACTIVE_IT_HAN_HARU=", "IT한 하루" in body, flush=True)
    if "IT한 하루" not in body:
        raise RuntimeError("Active Studio channel is not IT한 하루; aborting upload")
    click_if_text(d, ("계속", "Continue"), timeout=3)

    for item in data:
        rank = item["rank"]
        video_path = item["video_path"]
        title = clean_title(
            item.get("metadata", {}).get("title") or item.get("article_title")
        )
        desc = clean_description(item.get("metadata", {}).get("description") or "")
        print(f"UPLOAD_{rank}_START|path={video_path}|title={title}", flush=True)

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
