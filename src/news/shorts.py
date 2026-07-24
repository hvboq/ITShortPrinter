from __future__ import annotations


def format_article_for_prompt(article: dict) -> str:
    brands = ", ".join(article.get("brands", [])) or "unknown"
    technologies = ", ".join(article.get("technologies", [])) or "unknown"
    angle = article.get("shorts_angle") or {}
    return "\n".join(
        [
            f"Title: {article.get('title', '')}",
            f"Excerpt: {article.get('raw_excerpt', '')}",
            f"URL: {article.get('url') or article.get('canonical_url', '')}",
            f"Brands: {brands}",
            f"Technologies: {technologies}",
            f"Event Type: {article.get('event_type', '')}",
            f"Audience Fit: {article.get('audience_fit', '')}",
            f"Strategic Importance Score: {article.get('strategic_importance_score', '')}",
            f"Topic Bucket: {article.get('topic_bucket', '')}",
            f"Angle Type: {angle.get('angle_type', '')}",
            f"Hook Type: {angle.get('hook_type', '')}",
            f"Viewer Payoff: {angle.get('viewer_payoff', '')}",
            f"Angle Rationale: {angle.get('rationale', '')}",
            f"Confidence: {article.get('confidence', '')}",
            f"Shorts Score: {article.get('shorts_score', '')}",
        ]
    )


def build_shorts_script_prompt(
    article: dict,
    language: str = "Korean",
    sentence_length: int = 6,
) -> str:
    """Build a Korean news-briefing Shorts prompt from a ranked tech-news article."""
    article_block = format_article_for_prompt(article)
    sentence_length = max(5, int(sentence_length or 6))
    return f"""
너는 한국어 최신 IT 뉴스 브리핑 쇼츠 작가다.
아래 뉴스 하나를 바탕으로 30~45초 분량의 유튜브 쇼츠 내레이션 대본을 작성하라.
전체는 {sentence_length}문장 이내로 쓰되, 너무 긴 문장 하나로 시간을 채우지 말고 짧은 문장 여러 개로 리듬을 만든다.

채널 목표:
- 시청자가 최신 IT/기기/기술 소식을 빠르게 이해하게 만든다.
- 단순한 스펙 나열보다 "왜 중요한가", "무엇이 바뀌는가", "시청자에게 어떤 영향이 있는가"를 설명한다.
- 입력의 Angle Type, Hook Type, Viewer Payoff를 반영해 첫 3초 훅과 전체 흐름을 선명하게 만든다.

작성 규칙:
- 반드시 한국어로만 작성한다. 입력 뉴스가 영어여도 자연스러운 한국어 내레이션으로 번역하고 재구성한다.
- 첫 문장은 제목 반복이 아니라 변화, 비용, 사용 경험, 경쟁 구도처럼 바로 궁금해지는 포인트로 시작한다.
- 중간에는 "그래서 중요한 건"에 해당하는 해석 문장을 반드시 하나 넣는다.
- 각 문장은 모바일 자막으로 읽기 쉽게 45자 안팎을 목표로 하고, 한 문장에 정보를 과하게 몰아넣지 않는다.
- 전체 대본은 대략 260~380자 범위로 맞춘다.
- 불확실한 내용은 확정적으로 말하지 말고 "가능성이 있습니다", "확인이 필요합니다"처럼 표현한다.
- 루머, 미출시, 추정 정보는 단정하지 않는다.
- 저장 유도 금지.
- 시리즈화 금지.
- 과장 광고처럼 보이는 표현은 쓰지 않는다. 예: 국내 최초, 역대급, 대박, 무조건 사야 함, 놓치면 후회.
- 제품명과 브랜드명은 이해에 꼭 필요할 때만 최소한으로 사용한다.
- 마크다운, 제목, NARRATOR, VOICEOVER, 목록 기호, 출처 URL은 출력하지 않는다.
- 마지막 문장은 자연스러운 핵심 요약 또는 가벼운 구독 CTA로 끝낸다.
- 출력은 실제로 읽을 내레이션 대본만 반환한다.

뉴스 입력:
{article_block}
""".strip()
