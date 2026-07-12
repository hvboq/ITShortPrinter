from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
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
    "product_launch": 42,
    "price_availability": 28,
    "component_tech": 22,
    "wireless_standard": 20,
    "software_update": 15,
    "certification": 12,
    "review_hands_on": 8,
    "rumor_leak": 5,
    "market_context": 8,
    "ignore": 0,
}

LAUNCH_PRIORITY_BONUS = {
    "product_launch": 12,
    "price_availability": 7,
}

BRANDS = {
    "Samsung": ["samsung", "galaxy", "one ui", "exynos"],
    "SK Hynix": ["sk hynix", "sk하이닉스", "하이닉스"],
    "Hanmi Semiconductor": ["hanmi semiconductor", "한미반도체"],
    "BOE": ["boe", "비오이"],
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
    "OpenAI": ["openai", "chatgpt", "gpt-", "gpt ", "sora"],
    "Anthropic": ["anthropic", "claude", "클로드"],
    "Google": ["google", "gemini", "제미나이"],
}

TECHNOLOGIES = {
    "battery": ["battery", "배터리", "charging", "충전", "silicon-carbon", "solid-state", "mAh", "Wh/kg"],
    "display": ["display", "oled", "ltpo", "microled", "mini led", "foldable", "폴더블", "디스플레이", "올레드", "nits", "pwm"],
    "wifi": ["wi-fi", "wifi", "wi-fi 7", "wi-fi 8", "6ghz", "802.11", "mlo", "afc"],
    "bluetooth": ["bluetooth", "le audio", "auracast", "lc3", "bluetooth 6"],
    "chipset": ["chip", "chipset", "soc", "processor", "npu", "snapdragon", "exynos", "dimensity", "apple silicon", "semiconductor", "반도체", "hbm", "파운드리", "후공정", "tc본더", "본더", "공급망"],
    "cpu": ["cpu", "processor", "core ultra", "ryzen", "xeon", "epyc", "threadripper", "인텔", "라이젠", "프로세서"],
    "gpu": ["gpu", "graphics", "geforce", "rtx", "radeon", "arc gpu", "blackwell", "cuda", "그래픽카드", "그래픽 카드"],
    "pc_laptop": ["laptop", "notebook", "desktop pc", "pc", "workstation", "mini pc", "gaming pc", "노트북", "데스크톱", "데스크탑", "워크스테이션", "게이밍 pc"],
    "keyboard_mouse": ["keyboard", "mouse", "mechanical keyboard", "gaming mouse", "키보드", "마우스", "기계식 키보드", "게이밍 마우스"],
    "audio_wearables": ["headset", "headphone", "headphones", "earbuds", "earphones", "true wireless", "tws", "anc", "spatial audio", "헤드셋", "헤드폰", "이어폰", "무선 이어폰", "노이즈 캔슬링", "공간 음향"],
    "wearable": ["smartwatch", "smart watch", "smart band", "fitness tracker", "wearable", "galaxy watch", "apple watch", "watch", "band", "스마트워치", "스마트 워치", "스마트밴드", "스마트 밴드", "웨어러블", "피트니스 트래커"],
}

LAUNCH_TERMS = ["launch", "launches", "launched", "unveil", "unveils", "unveiled", "announce", "announces", "announced", "release", "released", "preorder", "pre-order", "출시", "출격", "공개", "발표", "사전예약", "사전 예약", "사전 판매", "예약 판매", "판매 시작"]
PRICE_AVAILABILITY_TERMS = ["availability", "available", "price", "prices", "deal", "deals", "discount", "sale", "price cut", "가격", "판매", "할인"]
SOFTWARE_UPDATE_TERMS = ["software update", "firmware", "app", "apps", "ios", "ipados", "watchos", "macos", "android update", "one ui", "hyperos", "업데이트", "앱"]
RUMOR_TERMS = ["rumor", "leak", "leaked", "suggests", "claim", "may", "루머", "유출", "가능성"]
RESEARCH_TERMS = ["research", "study", "prototype", "concept", "begins", "early", "연구", "개념"]
CERTIFICATION_TERMS = ["certification", "fcc", "bluetooth sig", "wi-fi alliance", "인증", "특허", "patent"]
NOISE_TERMS = ["coupon", "deal", "discount", "sponsored", "할인", "광고", "earnings", "dividend"]

# Learned from live configured channel analytics (2026-05-07):
# - Ranking/TOP-list formats and A-vs-B comparisons over smartphone/foldable topics
#   have shown the strongest early view/retention signals.
# - AI development/engineering topics create scope drift, but AI service/model launches
#   such as Claude/GPT/Gemini releases are acceptable for this channel.
PERFORMANCE_FORMAT_TERMS = [
    "top 10", "top10", "ranking", "rankings", "ranked", "vs", "versus", "compare", "comparison",
    "랭킹", "순위", "top", "비교", "대결", "상위", "베스트",
]
PERFORMANCE_TOPIC_TERMS = [
    "smartphone", "phone", "iphone", "galaxy", "foldable", "fold", "flip", "razr", "pixel",
    "스마트폰", "폰", "아이폰", "갤럭시", "폴더블", "폴드", "플립",
]
AI_SERVICE_SOLUTION_TERMS = [
    "openai", "chatgpt", "gpt-", "gpt ", "anthropic", "claude", "클로드", "google gemini", "gemini", "제미나이",
    "ai 서비스", "ai 솔루션",
]
AI_MODEL_RELEASE_TERMS = [
    "new model", " model", "model launch", "model release", "model update", "신규 모델", "모델", "모델 출시", "모델 공개", "모델 업데이트",
]
AI_DEVELOPMENT_TERMS = [
    "developer", "developers", "programming", "coding", "sdk", "api framework", "agent framework",
    "prompt engineering", "fine-tuning", "training pipeline", "eval harness", "benchmark harness",
    "개발자", "개발", "프로그래밍", "코딩", "파인튜닝", "학습 파이프라인", "프롬프트 엔지니어링",
]
AVOID_TOPIC_TERMS = [
    "harness engineering", "하네스 엔지니어링", "turboquant", "turbo quant", "터보퀀트",
    "app store policy",
]
FINANCE_FALSE_POSITIVE_TERMS = [
    "credit card", "payment card", "card issuer", "card company", "financial card",
    "신용카드", "체크카드", "제휴 카드", "카드사", "삼성카드", "롯데카드", "현대카드",
    "결제금액", "홈쇼핑", "금융", "여신", "카드 혜택", "할부",
]

CONSUMER_AI_TERMS = [
    "voice", "image", "search", "app", "mobile", "free", "paid plan", "subscription", "web", "assistant",
    "음성", "이미지", "검색", "앱", "모바일", "무료", "유료", "구독", "어시스턴트", "비서",
]
BUSINESS_AI_TERMS = [
    "enterprise", "workspace", "business", "office", "productivity", "team", "workflow",
    "기업", "업무", "생산성", "협업", "팀", "워크스페이스", "오피스",
]
ENTERPRISE_PRODUCT_TERMS = [
    "enterprise", "business", "commercial", "corporate", "b2b", "workplace", "office", "for teams",
    "기업용", "비즈니스용", "업무용", "상업용", "법인", "기업 고객", "기업 시장", "사무용", "오피스용",
]
DEVELOPER_AUDIENCE_TERMS = AI_DEVELOPMENT_TERMS + [
    "github", "repository", "repo", "commit", "pull request", "cli", "terminal", "command line",
    "library", "framework", "benchmark", "inference", "quantization", "compression", "open source",
    "깃", "깃허브", "저장소", "커밋", "풀리퀘스트", "터미널", "명령줄", "커맨드라인",
    "라이브러리", "프레임워크", "벤치마크", "추론 최적화", "양자화", "압축", "오픈소스",
]
GEEKNEWS_DEVELOPER_COMMUNITY_TERMS = [
    "coding agent", "local coding", "developer tool", "dev tool", "github", "repository", "repo", "commit",
    "pull request", "cli", "terminal", "command line", "framework", "library", "sdk", "benchmark",
    "open source", "opensource", "self-hosted", "tutorial", "how to", "guide", "walkthrough",
    "codex", "prompt", "코덱스", "프롬프트", "코딩 에이전트", "로컬 코딩", "개발 도구", "개발자 도구",
    "깃", "깃허브", "저장소", "커밋", "풀리퀘스트", "터미널", "명령줄", "커맨드라인",
    "프레임워크", "라이브러리", "벤치마크", "오픈소스", "튜토리얼", "가이드", "설정하는 방법", "사용하는 방법",
]
ENTERTAINMENT_CULTURE_TERMS = [
    "movie", "film", "cinema", "box office", "trailer", "hollywood", "disney", "pixar", "toy story",
    "netflix", "drama", "anime", "animation", "celebrity", "entertainment", "culture",
    "영화", "박스오피스", "예고편", "할리우드", "디즈니", "픽사", "토이 스토리", "토이스토리",
    "넷플릭스", "드라마", "애니", "애니메이션", "연예", "엔터", "엔터테인먼트", "문화",
]
ENTERTAINMENT_TECH_ANGLE_TERMS = [
    "ai", "artificial intelligence", "vfx", "cgi", "render", "streaming", "vr", "ar", "technology", "tech",
    "인공지능", "생성 ai", "vfx", "cg", "컴퓨터 그래픽", "렌더링", "스트리밍", "기술",
]
GAME_NEWS_TERMS = [
    "game", "gaming", "console", "xbox", "playstation", "nintendo", "steam", "epic games",
    "게임", "게이밍", "콘솔", "엑스박스", "플레이스테이션", "닌텐도", "스팀",
]
STRATEGIC_IMPORTANCE_TERMS = [
    "first", "flagship", "mainstream", "affordable", "cheaper", "price cut", "faster", "battery", "foldable",
    "competition", "rival", "vs", "versus", "upgrade", "available", "launch", "new model",
    "최초", "플래그십", "보급형", "저렴", "가격", "성능", "배터리", "폴더블", "경쟁", "대결",
    "업그레이드", "출시", "공개", "신규 모델", "모델 출시",
]

# Applied from the IT한 하루 28-day performance review (2026-06-09):
# high-retention/high-subscriber Shorts skewed toward semiconductor supply-chain,
# GPU/AI-PC, NVIDIA/Samsung/BOE, and concrete price/supply/competition stories.
HIGH_PERFORMANCE_INDUSTRY_TERMS = [
    "semiconductor", "hbm", "foundry", "packaging", "gpu", "ai pc", "nvidia", "boe",
    "supply", "supplier", "supply chain", "oled", "display", "rtx", "blackwell",
    "반도체", "후공정", "파운드리", "공급", "공급망", "수주", "계약", "장비", "본더", "tc본더",
    "gpu", "엔비디아", "삼성디스플레이", "디스플레이", "올레드", "컴퓨텍스",
]
LOW_RETENTION_ADVICE_TERMS = [
    "살 만할까", "사야 할까", "사도 될까", "기다릴", "쓸모 있을까", "정답일까", "영향 있을까",
    "오나?", "살펴볼 때", "지연설", "고객만족도", "판매를 늘린", "개막", "검토", "언급",
    "should you buy", "worth buying", "wait for", "is it worth", "does it matter",
]

# Added 2026-06-30 from IT한 하루 28-day channel performance review:
# "quirky/over-tech" stories (iFixit teardown, robot ETF, foldable leak, price-bubble
# analysis) ranked in TOP 1-7 even though they aren't flagship Samsung/Apple news.
# Boost these in ranking so the auto-pipeline surfaces them more often.
QUIRKY_OVERTECH_TERMS = [
    # Teardown / dissection
    "teardown", "disassembled", "disassembly", "disassemble", "taken apart", "ifxit", "ifixit",
    "i fix it", "deconstructed", "분해", "분해기", "해부", "해체", "뜯어봤", "뜯어보",
    # Quirky / surprising hardware / niche product
    "robot etf", "robot ETF", "로봇 ETF", "로봇 etf",
    "foldable leak", "leaked photo", "leaked image", "leaked render",
    "폴더블 유출", "폴더블", "유출 사진", "유출 이미지", "유출 렌더", "유출",
    "가격 거품", "거품", "price bubble",
    # Unexpected / oddball tech
    "unexpected", "quirky", "weird", "strange", "odd", "unusual", "hidden", "secret",
    "수상한", "이상한", "의외", "숨겨진", "몰랐던", "비밀",
    # Niche / fun
    "compact camera", "팬톤 카메라", "전기항공기", "evtol", "eVTOL", "trump phone",
    "trumpphone", "트럼프폰", "키즈폰", "태블릿 키즈", "키즈 워치",
]

# Narrow signals learned from channel response; a bare number never qualifies.
ENGAGEMENT_INDUSTRY_TERMS = [
    "인공지능", "gpu", "hbm", "semiconductor", "반도체", "supply chain", "공급망",
    "투자", "investment", "발주", "contract", "계약", "정부", "government", "대기업",
]
ENGAGEMENT_SUCCESS_TERMS = [
    "성공", "successful", "succeeds", "완료", "completed", "실증", "상용화", "commercialized",
    "첫 비행", "first flight", "전기항공기", "evtol",
]
ENGAGEMENT_CONSUMER_CHOICE_TERMS = [
    "가격", "price", "부품", "component", "브랜드", "brand", "대신", "versus", " vs ",
    "선택", "choice", "경쟁", "competition", "비교", "compare",
]

ROOT_DIR = Path(__file__).resolve().parents[2]
PERFORMANCE_WEIGHTS_PATH = ROOT_DIR / "data" / "topic_performance_weights.json"


def _text(article: dict) -> str:
    return f"{article.get('title', '')} {article.get('raw_excerpt', '')}".lower()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _contains_brand_alias(text: str, term: str) -> bool:
    term = term.lower()
    # Korean aliases and symbol-heavy aliases are safe as substrings; ASCII brand aliases
    # need boundaries so generic words like "programming" do not match "ROG".
    if any("가" <= ch <= "힣" for ch in term):
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def extract_brands(text: str) -> list[str]:
    return [brand for brand, terms in BRANDS.items() if any(_contains_brand_alias(text, term) for term in terms)]


def extract_technologies(text: str) -> list[str]:
    return [tech for tech, terms in TECHNOLOGIES.items() if _contains_any(text, terms)]


def classify_event(article: dict, text: str) -> str:
    tier = article.get("source_tier", "news_secondary")
    if tier == "rumor_leak" or _contains_any(text, RUMOR_TERMS):
        return "rumor_leak"
    if _contains_any(text, CERTIFICATION_TERMS):
        return "certification"
    if _contains_any(text, SOFTWARE_UPDATE_TERMS):
        return "software_update"
    if _contains_any(text, PRICE_AVAILABILITY_TERMS):
        return "price_availability"
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
            "SK Hynix": 18,
            "Hanmi Semiconductor": 16,
            "BOE": 16,
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
            "OpenAI": 14,
            "Anthropic": 13,
            "Google": 14,
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
    if _contains_any(text, ["npu", "foldable", "microled", "battery", "launch", "flagship", "최초", "신형", "cpu", "gpu", "rtx", "ryzen", "core ultra", "laptop", "notebook", "keyboard", "mouse", "headset", "headphone", "earbuds", "earphones", "smartwatch", "smart watch", "smart band", "wearable", "노트북", "키보드", "마우스", "그래픽카드", "헤드셋", "헤드폰", "이어폰", "스마트워치", "스마트밴드", "웨어러블"]):
        score += 10
    if _contains_any(text, PERFORMANCE_FORMAT_TERMS) and _contains_any(text, PERFORMANCE_TOPIC_TERMS):
        score += 8
    if _contains_any(text, AI_SERVICE_SOLUTION_TERMS) and _contains_any(text, AI_MODEL_RELEASE_TERMS):
        score += 6
    if _contains_any(text, RESEARCH_TERMS):
        score -= 8
    return max(0, min(score, 35))


def performance_signal_bonus(text: str, technologies: list[str]) -> int:
    """Small adaptive boost from actual channel performance, capped to avoid overfitting."""
    bonus = 0
    if _contains_any(text, PERFORMANCE_FORMAT_TERMS):
        bonus += 5
    if _contains_any(text, PERFORMANCE_TOPIC_TERMS) or "display" in technologies:
        bonus += 5
    if _contains_any(text, PERFORMANCE_FORMAT_TERMS) and _contains_any(text, PERFORMANCE_TOPIC_TERMS):
        bonus += 5
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS) or any(t in technologies for t in ("gpu", "cpu", "chipset", "display", "pc_laptop")):
        bonus += 8
    if _contains_any(text, ["반도체", "hbm", "후공정", "파운드리", "tc본더", "boe", "oled", "디스플레이"]):
        bonus += 5
    return min(bonus, 18)


def low_retention_format_penalty(text: str) -> int:
    """Demote broad advice/question titles that underperformed in channel analytics."""
    if not _contains_any(text, LOW_RETENTION_ADVICE_TERMS):
        return 0
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS):
        return 4
    return 10


def enterprise_product_penalty(text: str, event_type: str, technologies: list[str]) -> int:
    """Demote enterprise/B2B product launches that are less consumer-friendly for Shorts."""
    if event_type not in {"product_launch", "price_availability", "component_tech"}:
        return 0
    if not _contains_any(text, ENTERPRISE_PRODUCT_TERMS):
        return 0
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS) or any(
        tech in technologies for tech in ("gpu", "cpu", "chipset", "display")
    ):
        return 10
    return 28


def ai_service_solution_bonus(text: str) -> int:
    if not _contains_any(text, AI_SERVICE_SOLUTION_TERMS):
        return 0
    if _contains_any(text, AI_MODEL_RELEASE_TERMS):
        return 8
    return 4


def geeknews_developer_community_penalty(text: str, source_id: str, technologies: list[str]) -> int:
    """Demote GeekNews posts that are useful for developers but weak for IT한 하루 viewers."""
    if source_id != "geeknews":
        return 0
    if not _contains_any(text, GEEKNEWS_DEVELOPER_COMMUNITY_TERMS):
        return 0
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS) or any(
        tech in technologies for tech in ("gpu", "cpu", "chipset", "display", "pc_laptop")
    ):
        return 25
    return 60


def entertainment_culture_penalty(text: str, source_id: str) -> int:
    """Demote movie/entertainment/culture stories in the general hourly queue.

    They may include a technology angle, but channel performance priorities favor
    concrete hardware/AI-PC/semiconductor/supply-chain stories over #영화뉴스류.
    """
    if not _contains_any(text, ENTERTAINMENT_CULTURE_TERMS):
        return 0
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS):
        return 10
    if source_id == "geeknews":
        return 48
    if _contains_any(text, ENTERTAINMENT_TECH_ANGLE_TERMS):
        return 34
    return 55


def game_news_penalty(text: str) -> int:
    """Allow game news, but rank it below GPU/AI-PC/semiconductor priorities."""
    if not _contains_any(text, GAME_NEWS_TERMS):
        return 0
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS) or _contains_any(text, ["gpu", "rtx", "radeon", "graphics", "그래픽카드"]):
        return 8
    return 18


def quirky_overtech_bonus(text: str, event_type: str) -> int:
    """Boost quirky/over-tech stories (iFixit teardowns, foldable leaks, robot ETF,
    price-bubble analysis, niche hardware). Added 2026-06-30 after channel review
    showed these rank TOP 1-7 disproportionately vs flagship Samsung/Apple news.

    Capped so a single story doesn't dominate the entire queue.
    """
    text = text.lower() if text else ""
    if not _contains_any(text, QUIRKY_OVERTECH_TERMS):
        return 0
    bonus = 8
    # Teardowns are particularly high-retention on the channel (TOP 7 confirmed).
    if _contains_any(text, ["teardown", "disassembled", "disassembly", "ifixit", "분해", "해부", "해체"]):
        bonus += 6
    # Leaks/renders also over-perform (TOP 5: 995회 foldable leak).
    if _contains_any(text, ["leak", "leaked", "render", "유출"]):
        bonus += 4
    # ETF / market-structure quirk (TOP 1: 1.3천회 robot ETF).
    if _contains_any(text, ["etf", "etf"]):
        bonus += 4
    return min(bonus, 18)


def engagement_evidence_bonus(text: str, event_type: str, source_tier: str) -> tuple[int, list[str]]:
    """Capped, auditable boost for concrete evidence in proven channel topics."""
    if _contains_any(text, ["광고", "sponsored", "coupon", "쿠폰"]):
        return 0, []
    has_quantity = re.search(
        r"\d[\d,.]*\s*(?:%|퍼센트|만원|원|달러|억원|조원|대|장|개|km|킬로미터|배|명|건|w|kw|mw|gw)",
        text,
        re.IGNORECASE,
    ) is not None
    if not has_quantity:
        return 0, []
    reasons: list[str] = []
    bonus = 0
    has_ai_term = re.search(r"(?<![a-z0-9])ai(?![a-z0-9])", text) is not None
    if has_ai_term or _contains_any(text, ENGAGEMENT_INDUSTRY_TERMS):
        bonus += 7
        reasons.append("quantified_ai_chip_supply_or_investment")
    if _contains_any(text, ENGAGEMENT_SUCCESS_TERMS):
        bonus += 7
        reasons.append("verified_technology_success")
    if _contains_any(text, ENGAGEMENT_CONSUMER_CHOICE_TERMS):
        bonus += 6
        reasons.append("quantified_consumer_choice")
    bonus = min(bonus, 14)
    if event_type == "rumor_leak" or source_tier == "rumor_leak":
        bonus = min(bonus, 3)
        reasons = [f"unverified:{reason}" for reason in reasons]
    return bonus, reasons


def scope_drift_penalty(text: str, event_type: str) -> int:
    if _contains_any(text, AVOID_TOPIC_TERMS):
        return 30
    if _contains_any(text, FINANCE_FALSE_POSITIVE_TERMS):
        return 55
    if _contains_any(text, AI_SERVICE_SOLUTION_TERMS) and _contains_any(text, AI_MODEL_RELEASE_TERMS):
        return 0
    if _contains_any(text, AI_DEVELOPMENT_TERMS):
        return 45
    if event_type == "software_update" and not _contains_any(text, AI_SERVICE_SOLUTION_TERMS):
        return 12
    return 0


def classify_audience_fit(text: str, technologies: list[str] | None = None) -> str:
    """Classify who can immediately care about the story.

    The channel should favor consumer/prosumer/business-user stories and demote
    developer/research-only AI engineering content.
    """
    technologies = technologies or []
    has_ai_service = _contains_any(text, AI_SERVICE_SOLUTION_TERMS)
    has_model_release = _contains_any(text, AI_MODEL_RELEASE_TERMS)
    if _contains_any(text, AVOID_TOPIC_TERMS):
        return "developer"
    if has_ai_service and has_model_release:
        if _contains_any(text, BUSINESS_AI_TERMS):
            return "business_user"
        return "consumer"
    if _contains_any(text, DEVELOPER_AUDIENCE_TERMS):
        return "developer"
    if has_ai_service:
        if _contains_any(text, BUSINESS_AI_TERMS):
            return "business_user"
        if _contains_any(text, CONSUMER_AI_TERMS):
            return "consumer"
        return "prosumer"
    if technologies:
        return "consumer"
    if _contains_any(text, RESEARCH_TERMS):
        return "researcher"
    return "prosumer"


def audience_fit_score(audience_fit: str) -> int:
    return {
        "consumer": 8,
        "prosumer": 5,
        "business_user": 4,
        "developer": -12,
        "researcher": -10,
    }.get(audience_fit, 0)


def strategic_importance_score(text: str, event_type: str, brands: list[str], technologies: list[str]) -> int:
    """Score whether the news explains a larger IT market/user-impact shift."""
    score = 0
    if event_type in {"product_launch", "price_availability"}:
        score += 3
    if brands and technologies:
        score += 3
    if _contains_any(text, STRATEGIC_IMPORTANCE_TERMS):
        score += 4
    if _contains_any(text, PERFORMANCE_FORMAT_TERMS) or _contains_any(text, ["competition", "rival", "경쟁", "대결"]):
        score += 3
    if _contains_any(text, AI_SERVICE_SOLUTION_TERMS) and _contains_any(text, AI_MODEL_RELEASE_TERMS):
        score += 3
    if _contains_any(text, HIGH_PERFORMANCE_INDUSTRY_TERMS):
        score += 4
    if _contains_any(text, ["developer", "sdk", "framework", "benchmark", "quantization", "개발자", "프레임워크", "벤치마크", "양자화"]):
        score -= 3
    return max(0, min(score, 12))


def determine_shorts_angle(text: str, event_type: str, brands: list[str], technologies: list[str], audience_fit: str) -> dict:
    if _contains_any(text, PERFORMANCE_FORMAT_TERMS) and _contains_any(text, PERFORMANCE_TOPIC_TERMS):
        return {
            "angle_type": "ranking_comparison",
            "hook_type": "순위/비교",
            "viewer_payoff": "어떤 제품이나 브랜드가 지금 더 주목받는지 빠르게 판단할 수 있음",
            "rationale": "채널 성과에서 TOP/랭킹/비교형 스마트폰 콘텐츠가 강한 신호를 보였음",
        }
    if _contains_any(text, AI_SERVICE_SOLUTION_TERMS) and _contains_any(text, AI_MODEL_RELEASE_TERMS):
        return {
            "angle_type": "consumer_ai_model_shift",
            "hook_type": "AI 서비스 변화",
            "viewer_payoff": "앞으로 어떤 AI 서비스를 써볼 만한지 감을 잡을 수 있음",
            "rationale": "개발자 도구가 아니라 일반 사용자/업무 사용자가 체감할 수 있는 AI 모델·서비스 변화임",
        }
    if event_type == "price_availability" or _contains_any(text, ["price", "discount", "sale", "가격", "할인", "보급형"]):
        return {
            "angle_type": "price_value_shift",
            "hook_type": "가격/가성비 변화",
            "viewer_payoff": "구매 타이밍이나 제품 가치 변화를 빠르게 이해할 수 있음",
            "rationale": "가격·판매 정보는 시청자 개인 의사결정과 바로 연결됨",
        }
    if _contains_any(text, ["vs", "versus", "competition", "rival", "비교", "경쟁", "대결"]):
        return {
            "angle_type": "market_competition",
            "hook_type": "경쟁 구도",
            "viewer_payoff": "브랜드 간 판도가 어떻게 바뀌는지 이해할 수 있음",
            "rationale": "경쟁 구도는 짧은 쇼츠에서 맥락 전달이 쉬움",
        }
    if event_type == "product_launch":
        return {
            "angle_type": "launch_impact",
            "hook_type": "신제품 영향",
            "viewer_payoff": "새 제품이 기존 선택지를 어떻게 바꾸는지 알 수 있음",
            "rationale": "공식 출시/공개 뉴스는 채널 기본 우선순위와 맞음",
        }
    if audience_fit in {"developer", "researcher"}:
        return {
            "angle_type": "scope_risk",
            "hook_type": "전문가 전용 주제",
            "viewer_payoff": "일반 시청자 체감도가 낮아 쇼츠 우선순위는 낮음",
            "rationale": "개발/연구 중심 주제는 채널 범위에서 벗어날 가능성이 큼",
        }
    return {
        "angle_type": "why_it_matters",
        "hook_type": "왜 중요한가",
        "viewer_payoff": "뉴스의 핵심 변화와 시청자에게 생길 영향을 빠르게 이해할 수 있음",
        "rationale": "단순 요약보다 변화의 의미를 설명하는 각도가 채널 전략과 맞음",
    }


def topic_bucket(text: str, technologies: list[str], angle: dict | None = None) -> str:
    angle_type = (angle or {}).get("angle_type")
    if angle_type == "ranking_comparison":
        return "ranking_comparison"
    if _contains_any(text, AI_SERVICE_SOLUTION_TERMS) and _contains_any(text, AI_MODEL_RELEASE_TERMS):
        return "ai_service_model"
    if any(t in technologies for t in ("keyboard_mouse", "audio_wearables", "wearable", "bluetooth", "wifi")):
        return "peripheral_wearable_audio"
    if any(t in technologies for t in ("cpu", "gpu", "chipset", "pc_laptop", "display")):
        return "pc_chip_device"
    if _contains_any(text, PERFORMANCE_TOPIC_TERMS):
        return "smartphone_foldable"
    if technologies:
        return "hardware_device"
    return "general_it"


def load_performance_weights(path: Path = PERFORMANCE_WEIGHTS_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def learned_performance_weight_bonus(bucket: str, audience_fit: str, angle: dict, weights: dict | None = None) -> int:
    weights = weights if weights is not None else load_performance_weights()
    if not weights:
        return 0
    bonus = 0
    for section, key in (
        ("topic_buckets", bucket),
        ("audience_fit", audience_fit),
        ("angles", angle.get("angle_type", "")),
    ):
        value = (weights.get(section) or {}).get(key, 0)
        if isinstance(value, (int, float)):
            bonus += int(round(value))
    return max(-8, min(bonus, 8))


def select_portfolio_articles(articles: Iterable[dict], count: int = 5) -> list[dict]:
    """Select a diversified Shorts batch instead of simply taking the top N."""
    ranked = sorted(articles, key=lambda item: item.get("shorts_score", 0), reverse=True)
    preferred_buckets = [
        "pc_chip_device",
        "smartphone_foldable",
        "ai_service_model",
        "peripheral_wearable_audio",
        "ranking_comparison",
        "hardware_device",
        "general_it",
    ]
    selected: list[dict] = []
    selected_ids: set[str] = set()

    def add(item: dict) -> bool:
        key = item.get("id") or item.get("url") or item.get("title")
        if not key or key in selected_ids:
            return False
        selected.append(item)
        selected_ids.add(key)
        return len(selected) >= count

    for bucket in preferred_buckets:
        for item in ranked:
            if item.get("topic_bucket") == bucket and add(item):
                return selected
            if item.get("topic_bucket") == bucket:
                break
    for item in ranked:
        if add(item):
            return selected
    return selected


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
    adaptive_bonus = performance_signal_bonus(text, technologies)
    ai_service_bonus = ai_service_solution_bonus(text)
    scope_penalty = scope_drift_penalty(text, event_type)
    geeknews_penalty = geeknews_developer_community_penalty(
        text, article.get("source_id", ""), technologies
    )
    entertainment_penalty = entertainment_culture_penalty(text, article.get("source_id", ""))
    game_penalty = game_news_penalty(text)
    audience_fit = classify_audience_fit(text, technologies)
    audience_score = audience_fit_score(audience_fit)
    strategic_score = strategic_importance_score(text, event_type, brands, technologies)
    angle = determine_shorts_angle(text, event_type, brands, technologies, audience_fit)
    bucket = topic_bucket(text, technologies, angle)
    learned_bonus = learned_performance_weight_bonus(bucket, audience_fit, angle)
    retention_penalty = low_retention_format_penalty(text)
    enterprise_penalty = enterprise_product_penalty(text, event_type, technologies)
    quirky_bonus = quirky_overtech_bonus(text, event_type)
    evidence_bonus, evidence_reasons = engagement_evidence_bonus(text, event_type, source_tier)

    llm_score = min(100, source_score + event_score + keyword_score - noise_penalty)
    launch_priority_bonus = LAUNCH_PRIORITY_BONUS.get(event_type, 0)
    shorts_score = max(
        0,
        min(
            100,
            round(
                (llm_score * 0.30)
                + (feasibility * 20 * 0.25)
                + (keyword_score / 35 * 100 * 0.25)
                + (virality / 35 * 100 * 0.20)
                + launch_priority_bonus
                + adaptive_bonus
                + ai_service_bonus
                + audience_score
                + strategic_score
                + learned_bonus
                + quirky_bonus
                + evidence_bonus
                - scope_penalty
                - geeknews_penalty
                - retention_penalty
                - enterprise_penalty
                - entertainment_penalty
                - game_penalty
            ),
        ),
    )
    if enterprise_penalty >= 20:
        shorts_score = min(shorts_score, 72)
    elif enterprise_penalty > 0:
        shorts_score = min(shorts_score, 88)

    alert_allowed = (
        shorts_score >= 75
        and confidence >= 0.65
        and event_type != "rumor_leak"
        and scope_penalty == 0
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
            "launch_priority_bonus": launch_priority_bonus,
            "performance_signal_bonus": adaptive_bonus,
            "ai_service_solution_bonus": ai_service_bonus,
            "audience_fit": audience_fit,
            "audience_fit_score": audience_score,
            "strategic_importance_score": strategic_score,
            "shorts_angle": angle,
            "topic_bucket": bucket,
            "learned_performance_weight_bonus": learned_bonus,
            "low_retention_format_penalty": retention_penalty,
            "enterprise_product_penalty": enterprise_penalty,
            "entertainment_culture_penalty": entertainment_penalty,
            "game_news_penalty": game_penalty,
            "quirky_overtech_bonus": quirky_bonus,
            "engagement_evidence_bonus": evidence_bonus,
            "engagement_evidence_reasons": evidence_reasons,
            "scope_drift_penalty": scope_penalty,
            "geeknews_developer_community_penalty": geeknews_penalty,
            "llm_score": llm_score,
            "shorts_score": shorts_score,
            "alert_allowed": alert_allowed,
            "rumor_status": "rumor" if event_type == "rumor_leak" else "confirmed",
            "score_breakdown": {
                "llm_score": llm_score,
                "launch_priority_bonus": launch_priority_bonus,
                "performance_signal_bonus": adaptive_bonus,
                "engagement_evidence_bonus": evidence_bonus,
                "quirky_overtech_bonus": quirky_bonus,
                "penalties": scope_penalty + geeknews_penalty + retention_penalty
                + enterprise_penalty + entertainment_penalty + game_penalty,
            },
        }
    )
    return scored


def rank_articles(articles: Iterable[dict]) -> list[dict]:
    return sorted((score_article(article) for article in articles), key=lambda item: item["shorts_score"], reverse=True)
