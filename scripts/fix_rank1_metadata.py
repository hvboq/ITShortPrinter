from __future__ import annotations

import json
import re
import time

import _bootstrap  # noqa: F401
from classes.YouTube import YouTube
from project_paths import project_root, youtube_firefox_profile
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ROOT=project_root()
PROFILE=youtube_firefox_profile()
MANIFEST=ROOT/'.mp'/'batch_top5'/'manifest.json'
OUT=ROOT/'.mp'/'batch_top5'/'fix_rank1_metadata_result.json'
VIDEO_ID='eZTR8c8wuIc'
item=json.loads(MANIFEST.read_text(encoding='utf-8'))[0]
title=re.sub(r'\s+',' ', item.get('metadata',{}).get('title') or item.get('article_title') or '').strip()[:95]
desc=(item.get('metadata',{}).get('description') or '').strip()[:4500]
print('FIX_VIDEO_ID=', VIDEO_ID, flush=True)
print('FIX_TITLE=', title, flush=True)

def visible(el):
    try: return el.is_displayed()
    except Exception: return False

def click_js(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)
    time.sleep(0.2)

def set_textbox(d, el, value):
    click_js(d, el)
    time.sleep(0.5)
    try: el.send_keys(Keys.ESCAPE)
    except Exception: pass
    el.send_keys(Keys.CONTROL, 'a')
    time.sleep(0.1)
    el.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)
    el.send_keys(value)
    time.sleep(0.5)
    try: el.send_keys(Keys.ESCAPE)
    except Exception: pass

def click_save(d):
    for _ in range(10):
        buttons=[]
        buttons.extend(d.find_elements(By.ID,'save-button'))
        buttons.extend([b for b in d.find_elements(By.CSS_SELECTOR,'ytcp-button, tp-yt-paper-button, button') if b.text.strip() in ('저장','Save')])
        for b in buttons:
            if visible(b) and b.get_attribute('aria-disabled')!='true' and b.get_attribute('disabled') is None:
                click_js(d,b)
                return True
        time.sleep(1)
    print('SAVE_DEBUG=', [(b.get_attribute('id'),b.text,b.get_attribute('aria-disabled'),b.get_attribute('disabled')) for b in buttons], flush=True)
    return False

y=YouTube('it-han-haru','IT한 하루',PROFILE,'Korean IT News','Korean')
d=y.browser
try:
    d.set_page_load_timeout(180)
    d.get(f'https://studio.youtube.com/video/{VIDEO_ID}/edit')
    WebDriverWait(d,180).until(lambda drv: len(drv.find_elements(By.ID,'textbox'))>=2)
    time.sleep(8)
    body=d.find_element(By.TAG_NAME,'body').text
    print('ACTIVE_IT_HAN_HARU=', 'IT한 하루' in body, flush=True)
    textboxes=d.find_elements(By.ID,'textbox')
    set_textbox(d, textboxes[0], title)
    set_textbox(d, textboxes[-1], desc)
    if not click_save(d):
        raise RuntimeError('Could not save metadata')
    time.sleep(8)
    d.save_screenshot(str(ROOT/'.mp'/'batch_top5'/'rank1_metadata_fixed.png'))
    result={'video_id':VIDEO_ID,'url':f'https://youtube.com/shorts/{VIDEO_ID}','title':title,'description':desc,'saved':True}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    try: d.quit()
    except Exception: pass
print('FIX_METADATA_DONE=', OUT, flush=True)
