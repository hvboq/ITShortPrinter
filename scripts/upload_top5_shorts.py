from __future__ import annotations

import json
import re
import time
from pathlib import Path

from classes.YouTube import YouTube
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path('/opt/data/MoneyPrinterV2')
PROFILE = '/opt/data/firefox-profiles/youtube'
MANIFEST = ROOT / '.mp' / 'batch_top5' / 'manifest.json'
UPLOAD_MANIFEST = ROOT / '.mp' / 'batch_top5' / 'upload_manifest.json'
SCREEN_DIR = ROOT / '.mp' / 'batch_top5' / 'upload_screens'
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

def clean_title(s: str) -> str:
    s = re.sub(r'\s+', ' ', (s or '')).strip()
    return s[:95]

def clean_description(s: str) -> str:
    s = (s or '').strip()
    # Avoid overlong auto descriptions and source-ish tails.
    return s[:4500]

def click_if_text(driver, texts, timeout=4):
    end = time.time() + timeout
    while time.time() < end:
        for text in texts:
            els = driver.find_elements(By.XPATH, f'//*[normalize-space()="{text}" or contains(normalize-space(),"{text}")]')
            for el in els:
                try:
                    if el.is_displayed():
                        driver.execute_script('arguments[0].click();', el)
                        return True
                except Exception:
                    pass
        time.sleep(0.3)
    return False

def wait_click(driver, by, selector, timeout=120):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
    driver.execute_script('arguments[0].click();', el)
    return el

def set_textbox(el, value: str):
    el.click()
    time.sleep(0.3)
    el.send_keys(Keys.CONTROL, 'a')
    time.sleep(0.1)
    el.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)
    el.send_keys(value)

print('UPLOAD_TOP5_START', flush=True)
data = json.loads(MANIFEST.read_text(encoding='utf-8'))
y = YouTube('it-han-haru', 'IT한 하루', PROFILE, 'Korean IT News', 'Korean')
d = y.browser
results = []
try:
    d.set_page_load_timeout(180)
    d.get('https://studio.youtube.com/')
    time.sleep(10)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('STUDIO_TITLE=', d.title, flush=True)
    print('STUDIO_URL=', d.current_url, flush=True)
    print('ACTIVE_IT_HAN_HARU=', 'IT한 하루' in body, flush=True)
    if 'IT한 하루' not in body:
        raise RuntimeError('Active Studio channel is not IT한 하루; aborting upload')
    click_if_text(d, ['계속', 'Continue'], timeout=3)

    for item in data:
        rank = item['rank']
        video_path = item['video_path']
        title = clean_title(item.get('metadata', {}).get('title') or item.get('article_title'))
        desc = clean_description(item.get('metadata', {}).get('description') or '')
        print(f'UPLOAD_{rank}_START|path={video_path}|title={title}', flush=True)

        d.get('https://www.youtube.com/upload')
        WebDriverWait(d, 120).until(EC.presence_of_element_located((By.TAG_NAME, 'ytcp-uploads-file-picker')))
        file_picker = d.find_element(By.TAG_NAME, 'ytcp-uploads-file-picker')
        file_input = file_picker.find_element(By.TAG_NAME, 'input')
        file_input.send_keys(video_path)

        # Wait for details dialog text boxes to appear.
        WebDriverWait(d, 180).until(lambda drv: len(drv.find_elements(By.ID, 'textbox')) >= 2)
        time.sleep(5)
        textboxes = d.find_elements(By.ID, 'textbox')
        title_el = textboxes[0]
        desc_el = textboxes[-1]
        set_textbox(title_el, title)
        set_textbox(desc_el, desc)

        # Not made for kids.
        try:
            not_kids = d.find_element(By.NAME, 'VIDEO_MADE_FOR_KIDS_NOT_MFK')
            d.execute_script('arguments[0].click();', not_kids)
        except Exception:
            click_if_text(d, ['아니요, 아동용이 아닙니다', "No, it's not made for kids"], timeout=5)
        time.sleep(1)

        # Next through Details -> Video elements -> Checks.
        for step in range(3):
            wait_click(d, By.ID, 'next-button', timeout=180)
            print(f'UPLOAD_{rank}_NEXT_{step+1}', flush=True)
            time.sleep(3)

        # Select Unlisted / 일부 공개 explicitly.
        selected = click_if_text(d, ['일부 공개', 'Unlisted'], timeout=10)
        if not selected:
            # fallback: click radio label containing text by traversing radios
            labels = d.find_elements(By.XPATH, '//*[@id="radioLabel"]')
            label_texts = [x.text for x in labels]
            print('VISIBILITY_LABELS=', label_texts, flush=True)
            for lab in labels:
                if '일부 공개' in lab.text or 'Unlisted' in lab.text:
                    d.execute_script('arguments[0].click();', lab)
                    selected = True
                    break
        if not selected:
            raise RuntimeError('Could not select Unlisted visibility')
        print(f'UPLOAD_{rank}_VISIBILITY_UNLISTED', flush=True)
        time.sleep(1)

        wait_click(d, By.ID, 'done-button', timeout=180)
        print(f'UPLOAD_{rank}_DONE_CLICKED', flush=True)
        time.sleep(8)
        screenshot = str(SCREEN_DIR / f'upload_rank{rank}_done.png')
        d.save_screenshot(screenshot)

        # Try to capture video URL from dialog or videos page.
        url = None
        anchors = d.find_elements(By.XPATH, '//a[contains(@href,"youtu.be/") or contains(@href,"youtube.com/watch")]')
        for a in anchors:
            href = a.get_attribute('href')
            if href and ('youtu.be/' in href or 'watch' in href):
                url = href
                break
        if not url:
            # Go to Shorts content page and read first row link.
            d.get('https://studio.youtube.com/channel/UCcDkCUSZbX6EUPIqtVhRGyQ/videos/short')
            time.sleep(8)
            anchors = d.find_elements(By.XPATH, '//a[contains(@href,"/video/") or contains(@href,"watch")]')
            for a in anchors:
                href = a.get_attribute('href')
                if href:
                    url = href
                    break
        result = {
            'rank': rank,
            'video_path': video_path,
            'title': title,
            'description': desc,
            'visibility': 'unlisted',
            'uploaded_url': url,
            'screenshot': screenshot,
        }
        results.append(result)
        UPLOAD_MANIFEST.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'UPLOAD_{rank}_DONE|url={url}', flush=True)
        time.sleep(3)

finally:
    try:
        d.quit()
    except Exception:
        pass

print('UPLOAD_TOP5_DONE', flush=True)
print('UPLOAD_MANIFEST=', str(UPLOAD_MANIFEST), flush=True)
