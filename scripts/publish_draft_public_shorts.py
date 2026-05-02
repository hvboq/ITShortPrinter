from __future__ import annotations

import json
import re
import time
from pathlib import Path

from classes.YouTube import YouTube
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path('/opt/data/MoneyPrinterV2')
PROFILE = '/opt/data/firefox-profiles/youtube'
OUT = ROOT / '.mp' / 'batch_top5'
RESULTS = OUT / 'publish_manifest_public.json'
SCREEN_DIR = OUT / 'publish_screens'
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


def body_text(d):
    return d.find_element(By.TAG_NAME, 'body').text


def visible(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def click_js(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center", inline:"center"});', el)
    time.sleep(0.2)
    d.execute_script('arguments[0].click();', el)


def open_first_draft(d):
    WebDriverWait(d, 120).until(EC.presence_of_element_located((By.TAG_NAME, 'ytcp-video-row')))
    rows = d.find_elements(By.TAG_NAME, 'ytcp-video-row')
    draft_rows = [r for r in rows if '초안' in r.text or 'Draft' in r.text]
    if not draft_rows:
        return None
    row = draft_rows[0]
    lines = [x.strip() for x in row.text.splitlines() if x.strip()]
    title_line = lines[1] if len(lines) >= 2 else ''
    ActionChains(d).move_to_element(row).perform()
    time.sleep(1)
    buttons = [b for b in row.find_elements(By.CSS_SELECTOR, 'ytcp-button, tp-yt-paper-button, button') if ('초안 수정' in b.text or 'Edit draft' in b.text)]
    if not buttons:
        buttons = [b for b in d.find_elements(By.CSS_SELECTOR, 'ytcp-button, tp-yt-paper-button, button') if ('초안 수정' in b.text or 'Edit draft' in b.text)]
    if not buttons:
        raise RuntimeError('No draft edit button found')
    click_js(d, buttons[0])
    return title_line


def go_to_visibility(d):
    for _ in range(5):
        if d.find_elements(By.CSS_SELECTOR, 'tp-yt-paper-radio-button[name="PUBLIC"]'):
            return True
        nexts = d.find_elements(By.ID, 'next-button')
        if nexts and visible(nexts[0]) and nexts[0].get_attribute('aria-disabled') != 'true':
            click_js(d, nexts[0])
            time.sleep(3)
        else:
            time.sleep(2)
    return bool(d.find_elements(By.CSS_SELECTOR, 'tp-yt-paper-radio-button[name="PUBLIC"]'))


def select_public(d):
    radio = WebDriverWait(d, 60).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'tp-yt-paper-radio-button[name="PUBLIC"]')))
    click_js(d, radio)
    time.sleep(1)
    if radio.get_attribute('aria-checked') != 'true':
        for child_sel in ['#radioContainer', '#radioLabel']:
            try:
                child = radio.find_element(By.CSS_SELECTOR, child_sel)
                click_js(d, child)
                time.sleep(0.8)
                if radio.get_attribute('aria-checked') == 'true':
                    break
            except Exception:
                pass
    return radio.get_attribute('aria-checked') == 'true'


def click_publish_or_save(d):
    time.sleep(1)
    candidates = []
    candidates.extend(d.find_elements(By.ID, 'done-button'))
    candidates.extend([b for b in d.find_elements(By.CSS_SELECTOR, 'ytcp-button, tp-yt-paper-button, button') if b.text.strip() in ('게시', 'Publish', '저장', 'Save')])
    for b in candidates:
        if visible(b) and b.get_attribute('aria-disabled') != 'true' and b.get_attribute('disabled') is None:
            click_js(d, b)
            return True
    print('PUBLISH_BUTTONS_DEBUG=', [(b.get_attribute('id'), b.text, b.get_attribute('aria-disabled'), b.get_attribute('disabled')) for b in candidates], flush=True)
    return False


print('PUBLISH_DRAFTS_PUBLIC_START', flush=True)
y = YouTube('it-han-haru','IT한 하루',PROFILE,'Korean IT News','Korean')
d = y.browser
results = []
try:
    d.set_page_load_timeout(180)
    d.get('https://studio.youtube.com/channel/UCcDkCUSZbX6EUPIqtVhRGyQ/videos/short')
    time.sleep(15)
    print('LIST_READY_TITLE=', d.title, flush=True)
    print('ACTIVE_IT_HAN_HARU=', 'IT한 하루' in body_text(d), flush=True)
    if 'IT한 하루' not in body_text(d):
        raise RuntimeError('Wrong channel')
    for idx in range(1, 6):
        title = open_first_draft(d)
        if not title:
            print('NO_MORE_DRAFTS', flush=True)
            break
        print(f'PUBLISH_{idx}_OPENED|title={title}', flush=True)
        time.sleep(8)
        if not go_to_visibility(d):
            raise RuntimeError('Could not reach visibility step')
        text = body_text(d)
        m = re.search(r'https://youtube\.com/shorts/[A-Za-z0-9_-]+', text)
        url = m.group(0) if m else None
        ok = select_public(d)
        print(f'PUBLISH_{idx}_PUBLIC_SELECTED={ok}|url={url}', flush=True)
        if not ok:
            raise RuntimeError('Public radio did not select')
        shot = str(SCREEN_DIR / f'before_public_save_{idx}.png')
        d.save_screenshot(shot)
        if not click_publish_or_save(d):
            raise RuntimeError('Could not click Publish/Save/Done')
        time.sleep(10)
        result = {'sequence': idx, 'title': title, 'url': url, 'visibility': 'public', 'screenshot': shot}
        results.append(result)
        RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'PUBLISH_{idx}_SAVED|url={url}', flush=True)
        d.get('https://studio.youtube.com/channel/UCcDkCUSZbX6EUPIqtVhRGyQ/videos/short')
        time.sleep(12)
finally:
    try:
        d.quit()
    except Exception:
        pass
print('PUBLISH_DRAFTS_PUBLIC_DONE', flush=True)
print('PUBLISH_MANIFEST=', str(RESULTS), flush=True)
