import re
from dataclasses import asdict, is_dataclass

SCRIPT_MIN_CHARS = 120
SCRIPT_MAX_CHARS = 520
SCRIPT_MIN_SENTENCES = 3
SCRIPT_SENTENCE_RE = re.compile(r"(?<=[.!?。！？…])\s+")
METADATA_TITLE_MAX_CHARS = 68


def script_char_count(script: str) -> int:
    """Count non-space characters for Shorts narration pacing checks."""
    return len(re.sub(r"\s+", "", str(script or "")))


def script_sentence_count(script: str) -> int:
    """Estimate sentence count in a generated narration script."""
    text = str(script or "").strip()
    if not text:
        return 0
    sentences = [part for part in SCRIPT_SENTENCE_RE.split(text) if part.strip()]
    return max(1, len(sentences))


def script_quality_warnings(script: str) -> list[str]:
    """Return structural warnings for a generated Shorts narration script."""
    char_count = script_char_count(script)
    warnings: list[str] = []
    if char_count <= 0:
        warnings.append("structure_script_empty")
    elif char_count < SCRIPT_MIN_CHARS:
        warnings.append("structure_script_too_short")
    elif char_count > SCRIPT_MAX_CHARS:
        warnings.append("structure_script_too_long")

    if char_count > 0 and script_sentence_count(script) < SCRIPT_MIN_SENTENCES:
        warnings.append("structure_script_sentence_count_low")
    return warnings


def clean_generated_korean_text(text: str) -> str:
    """Clean common LLM artifacts before TTS/subtitles/metadata are rendered."""
    text = str(text or "")
    replacements = {
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
        "마케팅마케팅": "마케팅",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"```(?:json)?|```", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?m)^\s*(?:NARRATOR|VOICEOVER|대본|내레이션)\s*[:：-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?m)^\s*(?:[-*•]+|\d+[.)])\s+", "", text)
    text = re.sub(r"[\u1100-\u11ff]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_metadata_title(title: str) -> str:
    """Normalize title text used for upload metadata and persistent overlays."""
    title = clean_generated_korean_text(title)
    title = re.sub(r"^\s*(?:제목|Title)\s*[:：-]\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^[\"'“”‘’\[\]{}()<>]+|[\"'“”‘’\[\]{}()<>]+$", "", title).strip()

    hype_replacements = {
        "국내 최초!": "",
        "국내 최초": "",
        "역대급": "큰 변화",
        "대박": "주목",
        "초특가": "",
        "무조건 사야": "살펴볼",
        "놓치면 후회": "확인할",
        "충격": "변화",
        "실화?": "",
    }
    for old, new in hype_replacements.items():
        title = title.replace(old, new)

    title = re.sub(r"\s+([!?])", r"\1", title)
    title = re.sub(r"\s+", " ", title).strip(" -|")
    if len(title) > METADATA_TITLE_MAX_CHARS:
        title = title[: METADATA_TITLE_MAX_CHARS - 3].rstrip(" .,!?:;~-|") + "..."
    return title or "오늘의 IT 핵심 뉴스"


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
