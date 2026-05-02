from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

SOURCE_CONFIDENCE = {
    "official_primary": 0.95,
    "standards_primary": 0.92,
    "news_secondary": 0.72,
    "tech_secondary": 0.70,
    "industry_secondary": 0.68,
    "rumor_leak": 0.35,
    "search_aggregator": 0.55,
}

SOURCE_SCORE = {
    "official_primary": 40,
    "standards_primary": 36,
    "news_secondary": 25,
    "tech_secondary": 20,
    "industry_secondary": 18,
    "rumor_leak": 8,
    "search_aggregator": 10,
}

EVENT_SCORE = {
    "product_launch": 30,
    "price_availability": 20,
    "component_tech": 22,
    "wireless_standard": 20,
    "software_update": 15,
    "certification": 12,
    "review_hands_on": 8,
    "rumor_leak": 5,
    "market_context": 8,
    "ignore": 0,
}

BRANDS = {
    "Samsung": ["samsung", "galaxy", "one ui", "exynos"],
    "Apple": ["apple", "iphone", "ipad", "mac", "macbook", "vision pro", "airpods", "m-series"],
    "Qualcomm": ["qualcomm", "snapdragon", "adreno", "hexagon", "fastconnect"],
    "Xiaomi": ["xiaomi", "redmi", "poco", "hyperos", "샤오미", "홍미", "포코"],
    "Nothing": ["cmf", "glyph", "nothing os", "nothing phone", "낫싱"],
    "Intel": ["intel", "core ultra", "arc gpu", "xeon", "인텔"],
    "AMD": ["amd", "ryzen", "radeon", "epyc", "threadripper"],
    "NVIDIA": ["nvidia", "geforce", "rtx", "blackwell", "cuda", "엔비디아"],
    "Microsoft": ["microsoft", "surface", "windows", "copilot+ pc", "마이크로소프트"],
    "Logitech": ["logitech", "logi", "로지텍"],
    "Razer": ["razer", "레이저"],
    "Dell": ["dell", "alienware", "xps"],
    "Lenovo": ["lenovo", "thinkpad", "legion", "레노버"],
    "ASUS": ["asus", "rog", "zenbook", "tuf", "에이수스"],
    "HP": ["hp", "omen", "spectre", "elitebook"],
    "Sony": ["sony", "wh-1000", "wf-1000", "playstation headset", "소니"],
    "Bose": ["bose", "quietcomfort", "보스"],
    "Sennheiser": ["sennheiser", "젠하이저"],
    "Jabra": ["jabra", "자브라"],
    "Garmin": ["garmin", "가민"],
    "Fitbit": ["fitbit", "핏빗"],
    "Huawei": ["huawei", "watch gt", "화웨이"],
}

TECHNOLOGIES = {
    "battery": ["battery", "배터리", "charging", "충전", "silicon-carbon", "solid-state", "mAh", "Wh/kg"],
    "display": ["display", "oled", "ltpo", "microled", "mini led", "foldable", "폴더블", "nits", "pwm"],
    "wifi": ["wi-fi", "wifi", "wi-fi 7", "wi-fi 8", "6ghz", "802.11", "mlo", "afc"],
    "bluetooth": ["bluetooth", "le audio", "auracast", "lc3", "bluetooth 6"],
    "chipset": ["chip", "chipset", "soc", "processor", "npu", "snapdragon", "exynos", "dimensity", "apple silicon"],
    "cpu": ["cpu", "processor", "core ultra", "ryzen", "xeon", "epyc", "threadripper", "인텔", "라이젠", "프로세서"],
    "gpu": ["gpu", "graphics", "geforce", "rtx", "radeon", "arc gpu", "blackwell", "cuda", "그래픽카드", "그래픽 카드"],
    "pc_laptop": ["laptop", "notebook", "desktop pc", "pc", "workstation", "mini pc", "gaming pc", "노트북", "데스크톱", "데스크탑", "워크스테이션", "게이밍 pc"],
    "keyboard_mouse": ["keyboard", "mouse", "mechanical keyboard", "gaming mouse", "키보드", "마우스", "기계식 키보드", "게이밍 마우스"],
    "audio_wearables": ["headset", "headphone", "headphones", "earbuds", "earphones", "true wireless", "tws", "anc", "spatial audio", "헤드셋", "헤드폰", "이어폰", "무선 이어폰", "노이즈 캔슬링", "공간 음향"],
    "wearable": ["smartwatch", "smart watch", "smart band", "fitness tracker", "wearable", "galaxy watch", "apple watch", "watch", "band", "스마트워치", "스마트 워치", "스마트밴드", "스마트 밴드", "웨어러블", "피트니스 트래커"],
}

LAUNCH_TERMS = ["launch", "launches", "launched", "unveil", "announce", "release", "preorder", "availability", "price", "출시", "공개", "발표", "가격", "사전예약"]
RUMOR_TERMS = ["rumor", "leak", "leaked", "suggests", "claim", "may", "루머", "유출", "가능성"]
RESEARCH_TERMS = ["research", "study", "prototype", "concept", "begins", "early", "연구", "개념"]
CERTIFICATION_TERMS = ["certification", "fcc", "bluetooth sig", "wi-fi alliance", "인증", "특허", "patent"]
NOISE_TERMS = ["coupon", "deal", "discount", "sponsored", "할인", "광고", "earnings", "dividend"]


def _text(article: dict) -> str:
    return f"{article.get('title', '')} {article.get('raw_excerpt', '')}".lower()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def extract_brands(text: str) -> list[str]:
    return [brand for brand, terms in BRANDS.items() if _contains_any(text, terms)]


def extract_technologies(text: str) -> list[str]:
    return [tech for tech, terms in TECHNOLOGIES.items() if _contains_any(text, terms)]


def classify_event(article: dict, text: str) -> str:
    tier = article.get("source_tier", "news_secondary")
    if tier == "rumor_leak" or _contains_any(text, RUMOR_TERMS):
        return "rumor_leak"
    if _contains_any(text, CERTIFICATION_TERMS):
        return "certification"
    if _contains_any(text, LAUNCH_TERMS):
        return "product_launch"
    if extract_technologies(text):
        return "component_tech"
    if _contains_any(text, ["review", "hands-on", "reviewed", "리뷰", "핸즈온"]):
        return "review_hands_on"
    return "market_context"


def feasibility_score(event_type: str, text: str) -> int:
    if event_type in ["product_launch", "price_availability"]:
        return 5
    if event_type == "certification" or _contains_any(text, ["patent", "특허"]):
        return 4
    if _contains_any(text, ["demo", "prototype", "시연"]):
        return 3
    if _contains_any(text, RESEARCH_TERMS):
        return 1
    return 3


def popularity_score(brands: list[str], technologies: list[str]) -> int:
    score = 0
    for brand in brands:
        score += {
            "Apple": 18,
            "Samsung": 18,
            "NVIDIA": 16,
            "AMD": 16,
            "Intel": 16,
            "Qualcomm": 16,
            "Microsoft": 14,
            "ASUS": 13,
            "Lenovo": 13,
            "Dell": 12,
            "HP": 12,
            "Xiaomi": 12,
            "Logitech": 11,
            "Razer": 11,
            "Sony": 11,
            "Bose": 11,
            "Sennheiser": 11,
            "Garmin": 11,
            "Fitbit": 11,
            "Jabra": 10,
            "Huawei": 10,
            "Nothing": 10,
        }.get(brand, 6)
    for tech in technologies:
        score += {
            "gpu": 15,
            "cpu": 15,
            "pc_laptop": 15,
            "battery": 16,
            "display": 15,
            "chipset": 15,
            "keyboard_mouse": 13,
            "audio_wearables": 13,
            "wearable": 13,
            "wifi": 13,
            "bluetooth": 11,
        }.get(tech, 6)
    return min(score, 35)


def virality_score(article: dict, text: str, brands: list[str], technologies: list[str]) -> int:
    score = 8
    if brands:
        score += 8
    if technologies:
        score += 8
    if re.search(r"\d+", text):
        score += 8
    if _contains_any(text, ["ai", "npu", "foldable", "microled", "battery", "launch", "flagship", "최초", "신형", "cpu", "gpu", "rtx", "ryzen", "core ultra", "laptop", "notebook", "keyboard", "mouse", "headset", "headphone", "earbuds", "earphones", "smartwatch", "smart watch", "smart band", "wearable", "노트북", "키보드", "마우스", "그래픽카드", "헤드셋", "헤드폰", "이어폰", "스마트워치", "스마트밴드", "웨어러블"]):
        score += 10
    if _contains_any(text, RESEARCH_TERMS):
        score -= 8
    return max(0, min(score, 35))


def content_id(article: dict) -> str:
    raw = article.get("canonical_url") or article.get("url") or f"{article.get('source_id', '')}:{article.get('title', '')}:{article.get('published_at', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def score_article(article: dict) -> dict:
    text = _text(article)
    source_tier = article.get("source_tier", "news_secondary")
    brands = extract_brands(text)
    technologies = extract_technologies(text)
    event_type = classify_event(article, text)
    confidence = SOURCE_CONFIDENCE.get(source_tier, 0.55)

    source_score = SOURCE_SCORE.get(source_tier, 10)
    event_score = EVENT_SCORE.get(event_type, 0)
    keyword_score = popularity_score(brands, technologies)
    feasibility = feasibility_score(event_type, text)
    virality = virality_score(article, text, brands, technologies)
    noise_penalty = 25 if _contains_any(text, NOISE_TERMS) and source_tier != "official_primary" else 0

    llm_score = min(100, source_score + event_score + keyword_score - noise_penalty)
    shorts_score = round(
        (llm_score * 0.30)
        + (feasibility * 20 * 0.25)
        + (keyword_score / 35 * 100 * 0.25)
        + (virality / 35 * 100 * 0.20)
    )

    alert_allowed = (
        shorts_score >= 75
        and confidence >= 0.65
        and event_type != "rumor_leak"
        and source_tier in ["official_primary", "standards_primary", "news_secondary"]
    )

    scored = dict(article)
    scored.update(
        {
            "id": article.get("id") or content_id(article),
            "brands": brands,
            "technologies": technologies,
            "event_type": event_type,
            "confidence": confidence,
            "feasibility_score": feasibility,
            "popularity_score": keyword_score,
            "virality_score": virality,
            "llm_score": llm_score,
            "shorts_score": shorts_score,
            "alert_allowed": alert_allowed,
            "rumor_status": "rumor" if event_type == "rumor_leak" else "confirmed",
        }
    )
    return scored


def rank_articles(articles: Iterable[dict]) -> list[dict]:
    return sorted((score_article(article) for article in articles), key=lambda item: item["shorts_score"], reverse=True)
