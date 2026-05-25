from __future__ import annotations

import json
import time

import _bootstrap  # noqa: F401
from classes.YouTube import YouTube
from project_paths import project_root, youtube_firefox_profile
from youtube_studio import SHORTS_CONTENT_URL
from youtube_studio import body_text
from youtube_studio import capture_video_url
from youtube_studio import click_publish_or_done
from youtube_studio import go_to_visibility_step
from youtube_studio import open_first_draft
from youtube_studio import select_visibility_radio

ROOT = project_root()
PROFILE = youtube_firefox_profile()
OUT = ROOT / ".mp" / "batch_top5"
RESULTS = OUT / "publish_manifest.json"
SCREEN_DIR = OUT / "publish_screens"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

VISIBILITY = "unlisted"

print("PUBLISH_DRAFTS_START", flush=True)
y = YouTube("it-han-haru", "IT한 하루", PROFILE, "Korean IT News", "Korean")
d = y.browser
results = []

try:
    d.set_page_load_timeout(180)
    d.get(SHORTS_CONTENT_URL)
    time.sleep(15)
    print("LIST_READY_TITLE=", d.title, flush=True)
    print("ACTIVE_IT_HAN_HARU=", "IT한 하루" in body_text(d), flush=True)
    if "IT한 하루" not in body_text(d):
        raise RuntimeError("Wrong channel")

    for idx in range(1, 6):
        title = open_first_draft(d)
        if not title:
            print("NO_MORE_DRAFTS", flush=True)
            break

        print(f"PUBLISH_{idx}_OPENED|title={title}", flush=True)
        time.sleep(8)
        if not go_to_visibility_step(d, VISIBILITY, max_steps=4):
            raise RuntimeError("Could not reach visibility step")

        url = capture_video_url(d)
        ok = select_visibility_radio(d, VISIBILITY)
        print(f"PUBLISH_{idx}_UNLISTED_SELECTED={ok}|url={url}", flush=True)
        if not ok:
            raise RuntimeError("Unlisted radio did not select")

        screenshot = str(SCREEN_DIR / f"before_save_{idx}.png")
        d.save_screenshot(screenshot)
        if not click_publish_or_done(d, "SAVE", retry_delay=2, attempts=2):
            raise RuntimeError("Could not click Save/Done")

        time.sleep(8)
        result = {
            "sequence": idx,
            "title": title,
            "url": url,
            "visibility": VISIBILITY,
            "screenshot": screenshot,
        }
        results.append(result)
        RESULTS.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"PUBLISH_{idx}_SAVED|url={url}", flush=True)
        d.get(SHORTS_CONTENT_URL)
        time.sleep(12)

finally:
    try:
        d.quit()
    except Exception:
        pass

print("PUBLISH_DRAFTS_DONE", flush=True)
print("PUBLISH_MANIFEST=", str(RESULTS), flush=True)
