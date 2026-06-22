import re
from dataclasses import asdict, is_dataclass


def clean_generated_korean_text(text: str) -> str:
    """Clean common LLM artifacts before TTS/subtitles/metadata are rendered."""
    text = str(text or "")
    replacements = {
        "맥그네틱": "마그네틱",
        "AIagentic": "AI",
        "AI Agentic": "에이전틱 AI",
        "agentic AIagentic": "에이전틱 AI",
        "Agentic AIagentic": "에이전틱 AI",
        "갤럭시 에이37 5세대": "갤럭시 A37 5G",
        "에이37 5세대": "A37 5G",
        "A375G": "A37 5G",
        "갤럭시 에스이십칠 프로": "갤럭시 S27 Pro",
        "에스이십칠 프로": "S27 Pro",
        "갤럭시 에스이십칠": "갤럭시 S27",
        "에스이십칠": "S27",
        "갤럭시 에스이십육 FE": "갤럭시 S26 FE",
        "에스이십육 FE": "S26 FE",
        "중국형 가격대": "중급형 가격대",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[\u1100-\u11ff]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_metadata_title(title: str) -> str:
    """Normalize title text used for upload metadata and persistent overlays."""
    title = clean_generated_korean_text(title)
    title = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", title).strip()
    ad_replacements = {
        "국내 최초!": "",
        "국내 최초": "",
        "역대급": "큰",
        "수요 폭발": "수요 증가",
        "폭발": "증가",
        "극대화하는 법": "높이는 전략",
        "극대화": "향상",
        "새로운 기준": "새 접근",
    }
    for old, new in ad_replacements.items():
        title = title.replace(old, new)
    title = re.sub(r"\s+([!?])", r"\1", title)
    if len(title) > 92:
        title = title[:91].rstrip() + "…"
    return title or "오늘의 IT 핵심 이슈"


def normalize_news_article(article) -> dict:
    """Normalize supported news article shapes into the shorts prompt contract."""
    if is_dataclass(article):
        raw_article = asdict(article)
    elif isinstance(article, dict):
        raw_article = dict(article)
    else:
        raise TypeError("article must be a dict or dataclass-compatible news article.")

    excerpt = (
        raw_article.get("raw_excerpt")
        or raw_article.get("summary")
        or raw_article.get("content")
        or ""
    )
    if len(str(excerpt)) > 500:
        excerpt = str(excerpt)[:500].rstrip() + "..."

    return {
        **raw_article,
        "title": raw_article.get("title", ""),
        "raw_excerpt": excerpt,
        "url": raw_article.get("url") or raw_article.get("canonical_url", ""),
        "canonical_url": raw_article.get("canonical_url")
        or raw_article.get("url", ""),
        "brands": raw_article.get("brands", []),
        "technologies": raw_article.get("technologies", []),
        "event_type": raw_article.get("event_type", ""),
        "confidence": raw_article.get("confidence", ""),
        "shorts_score": raw_article.get("shorts_score", raw_article.get("score", "")),
    }
