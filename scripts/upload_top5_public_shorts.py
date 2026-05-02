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
UPLOAD_MANIFEST = ROOT / '.mp' / 'batch_top5' / 'upload_manifest_public.json'
SCREEN_DIR = ROOT / '.mp' / 'batch_top5' / 'upload_screens'
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


def clean_title(s: str) -> str:
    s = re.sub(r'\s+', ' ', (s or '')).strip()
    return s[:95]


def clean_description(s: str) -> str:
    s = (s or '').strip()
    return s[:4500]


def visible(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def click_js(driver, el):
    driver.execute_script('arguments[0].scrollIntoView({block:"center", inline:"center"});', el)
    time.sleep(0.2)
    driver.execute_script('arguments[0].click();', el)


def click_if_text(driver, texts, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        for text in texts:
            els = driver.find_elements(By.XPATH, f'//*[normalize-space()="{text}" or contains(normalize-space(),"{text}")]')
            for el in els:
                try:
                    if visible(el):
                        click_js(driver, el)
                        return True
                except Exception:
                    pass
        time.sleep(0.3)
    return False


def wait_click(driver, by, selector, timeout=180):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, selector)))
    click_js(driver, el)
    return el


def set_textbox(el, value: str):
    # YouTube may open hashtag/suggestion dropdowns that intercept normal clicks.
    # Use JS focus/click and Escape to keep the field stable.
    try:
        el.parent.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    except Exception:
        el.click()
    time.sleep(0.3)
    try:
        el.send_keys(Keys.ESCAPE)
    except Exception:
        pass
    el.send_keys(Keys.CONTROL, 'a')
    time.sleep(0.1)
    el.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)
    el.send_keys(value)
    time.sleep(0.2)
    try:
        el.send_keys(Keys.ESCAPE)
    except Exception:
        pass


def select_public(driver):
    # Preferred: direct radio by YouTube internal name.
    radios = driver.find_elements(By.CSS_SELECTOR, 'tp-yt-paper-radio-button[name="PUBLIC"]')
    if radios:
        click_js(driver, radios[0])
        time.sleep(1)
        return radios[0].get_attribute('aria-checked') == 'true'
    # Fallback by Korean/English labels.
    if click_if_text(driver, ['공개', 'Public'], timeout=8):
        time.sleep(1)
        radios = driver.find_elements(By.CSS_SELECTOR, 'tp-yt-paper-radio-button[name="PUBLIC"]')
        return not radios or radios[0].get_attribute('aria-checked') == 'true'
    labels = driver.find_elements(By.XPATH, '//*[@id="radioLabel"]')
    print('VISIBILITY_LABELS=', [x.text for x in labels], flush=True)
    for lab in labels:
        if lab.text.strip() in ('공개', 'Public') or '공개' in lab.text or 'Public' in lab.text:
            click_js(driver, lab)
            return True
    return False


print('UPLOAD_TOP5_PUBLIC_START', flush=True)
data = json.loads(MANIFEST.read_text(encoding='utf-8'))
start_rank = int(__import__('os').environ.get('START_RANK', '1'))
end_rank = int(__import__('os').environ.get('END_RANK', '999'))
data = [item for item in data if start_rank <= int(item.get('rank', 0)) <= end_rank]
print('UPLOAD_RANK_RANGE=', start_rank, end_rank, 'COUNT=', len(data), flush=True)
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

        WebDriverWait(d, 180).until(lambda drv: len(drv.find_elements(By.ID, 'textbox')) >= 2)
        time.sleep(5)
        textboxes = d.find_elements(By.ID, 'textbox')
        set_textbox(textboxes[0], title)
        set_textbox(textboxes[-1], desc)

        try:
            not_kids = d.find_element(By.NAME, 'VIDEO_MADE_FOR_KIDS_NOT_MFK')
            click_js(d, not_kids)
        except Exception:
            click_if_text(d, ['아니요, 아동용이 아닙니다', "No, it's not made for kids"], timeout=5)
        time.sleep(1)

        for step in range(3):
            wait_click(d, By.ID, 'next-button', timeout=180)
            print(f'UPLOAD_{rank}_NEXT_{step+1}', flush=True)
            time.sleep(3)

        if not select_public(d):
            raise RuntimeError('Could not select Public visibility')
        print(f'UPLOAD_{rank}_VISIBILITY_PUBLIC', flush=True)
        time.sleep(1)

        # Public uploads may show Publish button, while drafts may keep Done.
        clicked = False
        for selector in ['done-button']:
            buttons = d.find_elements(By.ID, selector)
            if buttons and visible(buttons[0]) and buttons[0].get_attribute('aria-disabled') != 'true':
                click_js(d, buttons[0])
                clicked = True
                break
        if not clicked:
            for b in d.find_elements(By.CSS_SELECTOR, 'ytcp-button, tp-yt-paper-button, button'):
                if b.text.strip() in ('게시', 'Publish', '저장', 'Save') and visible(b) and b.get_attribute('aria-disabled') != 'true':
                    click_js(d, b)
                    clicked = True
                    break
        if not clicked:
            raise RuntimeError('Could not click Publish/Done button')
        print(f'UPLOAD_{rank}_PUBLISH_CLICKED', flush=True)
        time.sleep(12)
        screenshot = str(SCREEN_DIR / f'upload_rank{rank}_public_done.png')
        d.save_screenshot(screenshot)

        url = None
        body_text = d.find_element(By.TAG_NAME, 'body').text
        m = re.search(r'https://youtube\.com/shorts/[A-Za-z0-9_-]+', body_text)
        if m:
            url = m.group(0)
        if not url:
            anchors = d.find_elements(By.XPATH, '//a[contains(@href,"youtu.be/") or contains(@href,"youtube.com/watch") or contains(@href,"/shorts/")]')
            for a in anchors:
                href = a.get_attribute('href')
                if href:
                    url = href
                    break
        result = {'rank': rank, 'video_path': video_path, 'title': title, 'description': desc, 'visibility': 'public', 'uploaded_url': url, 'screenshot': screenshot}
        results.append(result)
        UPLOAD_MANIFEST.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'UPLOAD_{rank}_DONE|url={url}', flush=True)
        time.sleep(4)
finally:
    try:
        d.quit()
    except Exception:
        pass

print('UPLOAD_TOP5_PUBLIC_DONE', flush=True)
print('UPLOAD_MANIFEST=', str(UPLOAD_MANIFEST), flush=True)
