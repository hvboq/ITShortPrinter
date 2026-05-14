from __future__ import annotations

import re
import time
from typing import Iterable

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SHORTS_CONTENT_URL = "https://studio.youtube.com/channel/UCcDkCUSZbX6EUPIqtVhRGyQ/videos/short"
UPLOAD_URL = "https://www.youtube.com/upload"

VISIBILITY_OPTIONS = {
    "public": {
        "radio": "PUBLIC",
        "labels": ("공개", "Public"),
        "log": "PUBLIC",
    },
    "unlisted": {
        "radio": "UNLISTED",
        "labels": ("일부 공개", "Unlisted"),
        "log": "UNLISTED",
    },
}


def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()[:95]


def clean_description(value: str) -> str:
    return (value or "").strip()[:4500]


def body_text(driver) -> str:
    return driver.find_element(By.TAG_NAME, "body").text


def visible(element) -> bool:
    try:
        return element.is_displayed()
    except Exception:
        return False


def click_js(driver, element) -> None:
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center", inline:"center"});',
        element,
    )
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", element)


def click_if_text(driver, texts: Iterable[str], timeout: int = 5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        for text in texts:
            elements = driver.find_elements(
                By.XPATH,
                f'//*[normalize-space()="{text}" or contains(normalize-space(),"{text}")]',
            )
            for element in elements:
                try:
                    if visible(element):
                        click_js(driver, element)
                        return True
                except Exception:
                    pass
        time.sleep(0.3)
    return False


def wait_click(driver, by, selector: str, timeout: int = 180):
    element = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )
    click_js(driver, element)
    return element


def set_textbox(element, value: str) -> None:
    # YouTube may open hashtag/suggestion dropdowns that intercept normal clicks.
    try:
        element.parent.execute_script(
            'arguments[0].scrollIntoView({block:"center"}); arguments[0].click();',
            element,
        )
    except Exception:
        element.click()

    time.sleep(0.3)
    try:
        element.send_keys(Keys.ESCAPE)
    except Exception:
        pass
    element.send_keys(Keys.CONTROL, "a")
    time.sleep(0.1)
    element.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)
    element.send_keys(value)
    time.sleep(0.2)
    try:
        element.send_keys(Keys.ESCAPE)
    except Exception:
        pass


def wait_for_upload_textboxes(driver, timeout: int = 180) -> list:
    WebDriverWait(driver, timeout).until(
        lambda active_driver: len(active_driver.find_elements(By.ID, "textbox")) >= 2
    )
    time.sleep(5)
    return driver.find_elements(By.ID, "textbox")


def fill_upload_metadata(driver, title: str, description: str) -> None:
    textboxes = wait_for_upload_textboxes(driver)
    set_textbox(textboxes[0], title)
    set_textbox(textboxes[-1], description)


def select_not_made_for_kids(driver) -> None:
    try:
        not_kids = driver.find_element(By.NAME, "VIDEO_MADE_FOR_KIDS_NOT_MFK")
        click_js(driver, not_kids)
    except Exception:
        click_if_text(
            driver,
            ("아니요, 아동용이 아닙니다", "No, it's not made for kids"),
            timeout=5,
        )
    time.sleep(1)


def log_next_button_timeout(driver, rank: int, step: int, screen_dir) -> None:
    debug_shot = str(screen_dir / f"upload_rank{rank}_next_timeout_step{step}.png")
    try:
        driver.save_screenshot(debug_shot)
        body_debug = body_text(driver).replace("\n", " | ")[:3000]
        print(f"UPLOAD_{rank}_NEXT_TIMEOUT_SCREEN={debug_shot}", flush=True)
        print(f"UPLOAD_{rank}_NEXT_TIMEOUT_BODY={body_debug}", flush=True)
        buttons_debug = []
        for button in driver.find_elements(
            By.CSS_SELECTOR,
            "ytcp-button, tp-yt-paper-button, button",
        )[:40]:
            try:
                buttons_debug.append(
                    (
                        button.get_attribute("id"),
                        button.text,
                        button.get_attribute("aria-disabled"),
                        button.get_attribute("disabled"),
                        button.is_displayed(),
                    )
                )
            except Exception:
                pass
        print(f"UPLOAD_{rank}_BUTTONS_DEBUG={buttons_debug}", flush=True)
    except Exception as debug_exc:
        print(f"UPLOAD_{rank}_DEBUG_FAILED={debug_exc}", flush=True)


def advance_upload_steps(
    driver,
    rank: int,
    count: int = 3,
    timeout: int = 180,
    screen_dir=None,
) -> None:
    for step in range(count):
        try:
            wait_click(driver, By.ID, "next-button", timeout=timeout)
        except Exception:
            if screen_dir is not None:
                log_next_button_timeout(driver, rank, step + 1, screen_dir)
            raise
        print(f"UPLOAD_{rank}_NEXT_{step + 1}", flush=True)
        time.sleep(3)


def visibility_config(visibility: str) -> dict:
    try:
        return VISIBILITY_OPTIONS[visibility]
    except KeyError as exc:
        raise ValueError(f"Unsupported visibility: {visibility}") from exc


def select_visibility(driver, visibility: str, timeout: int = 10) -> bool:
    config = visibility_config(visibility)
    radio_selector = f'tp-yt-paper-radio-button[name="{config["radio"]}"]'
    radios = driver.find_elements(By.CSS_SELECTOR, radio_selector)
    if radios:
        click_js(driver, radios[0])
        time.sleep(1)
        return radios[0].get_attribute("aria-checked") == "true"

    if click_if_text(driver, config["labels"], timeout=timeout):
        time.sleep(1)
        radios = driver.find_elements(By.CSS_SELECTOR, radio_selector)
        return not radios or radios[0].get_attribute("aria-checked") == "true"

    labels = driver.find_elements(By.XPATH, '//*[@id="radioLabel"]')
    print("VISIBILITY_LABELS=", [label.text for label in labels], flush=True)
    for label in labels:
        if any(option in label.text for option in config["labels"]):
            click_js(driver, label)
            return True
    return False


def go_to_visibility_step(driver, visibility: str, max_steps: int = 5) -> bool:
    config = visibility_config(visibility)
    radio_selector = f'tp-yt-paper-radio-button[name="{config["radio"]}"]'
    for _ in range(max_steps):
        if driver.find_elements(By.CSS_SELECTOR, radio_selector):
            return True
        next_buttons = driver.find_elements(By.ID, "next-button")
        if (
            next_buttons
            and visible(next_buttons[0])
            and next_buttons[0].get_attribute("aria-disabled") != "true"
        ):
            click_js(driver, next_buttons[0])
            time.sleep(3)
        else:
            time.sleep(2)
    return bool(driver.find_elements(By.CSS_SELECTOR, radio_selector))


def select_visibility_radio(driver, visibility: str) -> bool:
    config = visibility_config(visibility)
    radio = WebDriverWait(driver, 60).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, f'tp-yt-paper-radio-button[name="{config["radio"]}"]')
        )
    )
    click_js(driver, radio)
    time.sleep(1)
    if radio.get_attribute("aria-checked") != "true":
        for child_selector in ("#radioContainer", "#radioLabel"):
            try:
                child = radio.find_element(By.CSS_SELECTOR, child_selector)
                click_js(driver, child)
                time.sleep(0.8)
                if radio.get_attribute("aria-checked") == "true":
                    break
            except Exception:
                pass
    return radio.get_attribute("aria-checked") == "true"


def click_publish_or_done(
    driver,
    debug_label: str,
    retry_delay: int = 0,
    attempts: int = 1,
) -> bool:
    candidates = []
    for attempt in range(max(1, attempts)):
        if retry_delay and attempt > 0:
            time.sleep(retry_delay)

        candidates = []
        candidates.extend(driver.find_elements(By.ID, "done-button"))
        candidates.extend(
            [
                button
                for button in driver.find_elements(
                    By.CSS_SELECTOR,
                    "ytcp-button, tp-yt-paper-button, button",
                )
                if button.text.strip() in ("게시", "Publish", "저장", "Save")
            ]
        )

        for button in candidates:
            if (
                visible(button)
                and button.get_attribute("aria-disabled") != "true"
                and button.get_attribute("disabled") is None
            ):
                click_js(driver, button)
                return True

    print(
        f"{debug_label}_BUTTONS_DEBUG=",
        [
            (
                button.get_attribute("id"),
                button.text,
                button.get_attribute("aria-disabled"),
                button.get_attribute("disabled"),
            )
            for button in candidates
        ],
        flush=True,
    )
    return False


def capture_video_url(driver) -> str | None:
    match = re.search(r"https://youtube\.com/shorts/[A-Za-z0-9_-]+", body_text(driver))
    if match:
        return match.group(0)

    anchors = driver.find_elements(
        By.XPATH,
        '//a[contains(@href,"youtu.be/") or contains(@href,"youtube.com/watch") or contains(@href,"/shorts/")]',
    )
    for anchor in anchors:
        href = anchor.get_attribute("href")
        if href:
            return href
    return None


def capture_latest_video_url_from_shorts_page(driver) -> str | None:
    driver.get(SHORTS_CONTENT_URL)
    time.sleep(8)
    anchors = driver.find_elements(
        By.XPATH,
        '//a[contains(@href,"/video/") or contains(@href,"watch")]',
    )
    for anchor in anchors:
        href = anchor.get_attribute("href")
        if href:
            return href
    return None


def open_first_draft(driver) -> str | None:
    WebDriverWait(driver, 120).until(
        EC.presence_of_element_located((By.TAG_NAME, "ytcp-video-row"))
    )
    rows = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
    draft_rows = [row for row in rows if "초안" in row.text or "Draft" in row.text]
    if not draft_rows:
        return None

    row = draft_rows[0]
    lines = [line.strip() for line in row.text.splitlines() if line.strip()]
    title_line = lines[1] if len(lines) >= 2 else ""
    ActionChains(driver).move_to_element(row).perform()
    time.sleep(1)

    buttons = [
        button
        for button in row.find_elements(
            By.CSS_SELECTOR,
            "ytcp-button, tp-yt-paper-button, button",
        )
        if "초안 수정" in button.text or "Edit draft" in button.text
    ]
    if not buttons:
        buttons = [
            button
            for button in driver.find_elements(
                By.CSS_SELECTOR,
                "ytcp-button, tp-yt-paper-button, button",
            )
            if "초안 수정" in button.text or "Edit draft" in button.text
        ]
    if not buttons:
        raise RuntimeError("No draft edit button found")

    click_js(driver, buttons[0])
    return title_line
