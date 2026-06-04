from __future__ import annotations

import json
import time

import _bootstrap  # noqa: F401
from classes.YouTube import YouTube
from config import get_youtube_channel_config
from project_paths import project_root, youtube_firefox_profile
from selenium.webdriver.common.by import By
from youtube_studio import studio_channel_url

ROOT = project_root()
PROFILE = youtube_firefox_profile()
OUT = ROOT / '.mp' / 'batch_top5'
VERIFY = OUT / 'verify_public_manifest.json'
SCREEN = OUT / 'verify_public_list.png'
expected_urls = []
for p in [OUT / 'publish_manifest_public.json', OUT / 'upload_manifest_public.json']:
    if p.exists():
        data = json.loads(p.read_text(encoding='utf-8'))
        for item in data:
            url = item.get('url') or item.get('uploaded_url')
            if url:
                expected_urls.append(url)
# unique preserve order
seen = set()
expected_urls = [u for u in expected_urls if not (u in seen or seen.add(u))]
print('EXPECTED_URLS=', expected_urls, flush=True)
channel_config = get_youtube_channel_config()
y = YouTube(channel_config['slug'], channel_config['name'], PROFILE, 'Korean IT News', 'Korean')
d = y.browser
try:
    d.set_page_load_timeout(180)
    d.get(f"{studio_channel_url(channel_config['id'])}/videos/short")
    time.sleep(18)
    body = d.find_element(By.TAG_NAME, 'body').text
    expected_name = channel_config['name']
    active_expected_channel = bool(expected_name) and expected_name in body
    print('ACTIVE_EXPECTED_CHANNEL=', active_expected_channel, flush=True)
    print('BODY_HAS_DRAFT=', ('초안' in body or 'Draft' in body), flush=True)
    print('BODY_HAS_PUBLIC=', ('공개' in body or 'Public' in body), flush=True)
    rows = []
    for i, row in enumerate(d.find_elements(By.TAG_NAME, 'ytcp-video-row')[:12], 1):
        text = row.text
        hrefs = []
        for a in row.find_elements(By.TAG_NAME, 'a'):
            h = a.get_attribute('href')
            if h:
                hrefs.append(h)
        rows.append({'index': i, 'text': text, 'hrefs': hrefs})
        print(f'ROW_{i}=', text.replace('\n', ' | ')[:500], flush=True)
        print(f'ROW_{i}_HREFS=', hrefs, flush=True)
    d.save_screenshot(str(SCREEN))
    result = {
        'expected_urls': expected_urls,
        'active_expected_channel': active_expected_channel,
        'body_has_draft': ('초안' in body or 'Draft' in body),
        'body_has_public': ('공개' in body or 'Public' in body),
        'rows': rows,
        'screenshot': str(SCREEN),
    }
    VERIFY.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    try:
        d.quit()
    except Exception:
        pass
print('VERIFY_MANIFEST=', VERIFY, flush=True)
