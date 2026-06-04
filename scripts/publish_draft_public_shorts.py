from __future__ import annotations

import json
import time

import _bootstrap  # noqa: F401
from classes.YouTube import YouTube
from config import get_youtube_channel_config
from project_paths import project_root, youtube_firefox_profile
from youtube_studio import body_text
from youtube_studio import capture_video_url
from youtube_studio import click_publish_or_done
from youtube_studio import go_to_visibility_step
from youtube_studio import open_first_draft
from youtube_studio import select_visibility_radio
from youtube_studio import studio_channel_url

ROOT = project_root()
PROFILE = youtube_firefox_profile()
OUT = ROOT / ".mp" / "batch_top5"
RESULTS = OUT / "publish_manifest_public.json"
SCREEN_DIR = OUT / "publish_screens"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

VISIBILITY = "public"

print("PUBLISH_DRAFTS_PUBLIC_START", flush=True)
channel_config = get_youtube_channel_config()
y = YouTube(channel_config["slug"], channel_config["name"], PROFILE, "Korean IT News", "Korean")
d = y.browser
results = []

try:
    d.set_page_load_timeout(180)
    channel_url = studio_channel_url(channel_config["id"])
    d.get(f"{channel_url}/videos/short")
    time.sleep(15)
    print("LIST_READY_TITLE=", d.title, flush=True)
    expected_name = channel_config["name"]
    active_expected_channel = bool(expected_name) and expected_name in body_text(d)
    print("ACTIVE_EXPECTED_CHANNEL=", active_expected_channel, flush=True)
    if expected_name and not active_expected_channel:
        raise RuntimeError("Wrong channel")

    for idx in range(1, 6):
        title = open_first_draft(d)
        if not title:
            print("NO_MORE_DRAFTS", flush=True)
            break

        print(f"PUBLISH_{idx}_OPENED|title={title}", flush=True)
        time.sleep(8)
        if not go_to_visibility_step(d, VISIBILITY, max_steps=5):
            raise RuntimeError("Could not reach visibility step")

        url = capture_video_url(d)
        ok = select_visibility_radio(d, VISIBILITY)
        print(f"PUBLISH_{idx}_PUBLIC_SELECTED={ok}|url={url}", flush=True)
        if not ok:
            raise RuntimeError("Public radio did not select")

        screenshot = str(SCREEN_DIR / f"before_public_save_{idx}.png")
        d.save_screenshot(screenshot)
        time.sleep(1)
        if not click_publish_or_done(d, "PUBLISH", retry_delay=1, attempts=1):
            raise RuntimeError("Could not click Publish/Save/Done")

        time.sleep(10)
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
        d.get(f"{channel_url}/videos/short")
        time.sleep(12)

finally:
    try:
        d.quit()
    except Exception:
        pass

print("PUBLISH_DRAFTS_PUBLIC_DONE", flush=True)
print("PUBLISH_MANIFEST=", str(RESULTS), flush=True)
