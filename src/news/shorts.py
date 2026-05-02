from __future__ import annotations


def format_article_for_prompt(article: dict) -> str:
    brands = ", ".join(article.get("brands", [])) or "unknown"
    technologies = ", ".join(article.get("technologies", [])) or "unknown"
    return "\n".join(
        [
            f"Title: {article.get('title', '')}",
            f"Excerpt: {article.get('raw_excerpt', '')}",
            f"URL: {article.get('url') or article.get('canonical_url', '')}",
            f"Brands: {brands}",
            f"Technologies: {technologies}",
            f"Event Type: {article.get('event_type', '')}",
            f"Confidence: {article.get('confidence', '')}",
            f"Shorts Score: {article.get('shorts_score', '')}",
        ]
    )


def build_shorts_script_prompt(article: dict, language: str = "Korean", sentence_length: int = 5) -> str:
    """Builds a Korean news-briefing Shorts prompt from a ranked tech-news article."""
    article_block = format_article_for_prompt(article)
    return f"""
너는 한국어 최신 IT 뉴스 브리핑 쇼츠 작가다.
아래 뉴스 하나를 바탕으로 {sentence_length}문장 이내의 45~60초 유튜브 쇼츠 대본을 작성하라.

채널 목적:
- 항상 최신 IT/기기/기술 소식을 빠르게 요약해서 전달한다.
- 사용자는 트렌드를 파악하고 순수한 호기심을 채우기 위해 본다.
- 단순 스펙 나열보다 왜 중요한지, 무엇이 바뀌는지를 설명한다.

규칙:
- 반드시 한국어로만 작성한다. 입력 뉴스 제목/요약이 영어여도 자연스러운 한국어 나레이션으로 번역·재구성한다.
- 최신 IT 뉴스 브리핑 톤으로 작성한다.
- 저장 유도 금지.
- 시리즈화 금지.
- 마지막 CTA는 구독 유도만 허용한다.
- 루머/유출이면 확정 표현을 쓰지 말고 확인 필요성을 명시한다.
- 마크다운, 제목, NARRATOR, VOICEOVER 같은 라벨을 쓰지 않는다.
- 출처, 매체명, URL, 도메인, 링크, 날짜 문자열을 나레이션 대본에 넣지 않는다.
- 마지막 문장은 출처 안내가 아니라 자연스러운 구독 유도나 핵심 요약으로 끝낸다.

- 제품명과 브랜드명은 뉴스 이해에 꼭 필요할 때만 최소한으로 사용하고, 공식 광고처럼 보이는 홍보 카피는 피한다.
- `국내 최초`, `역대급`, `폭발`, `극대화`, `새로운 기준`, `~하는 법`처럼 광고/선전처럼 보이는 표현을 남발하지 않는다.
- 영어 기술 용어는 한 번만 자연스럽게 병기하고, `AIagentic`처럼 한글과 영어가 붙은 깨진 표현을 절대 만들지 않는다.
- 한글 자모만 남은 깨진 문자나 불필요한 특수문자를 쓰지 않는다.
- `맥그네틱`이 아니라 `마그네틱`처럼 표준적인 한국어 표기를 사용한다.

뉴스 입력:
{article_block}

출력은 실제로 읽을 나레이션 대본만 반환하라.
""".strip()
