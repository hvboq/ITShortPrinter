from __future__ import annotations

import re


B2B_CHOICE_TERMS = (
    "b2b", "industrial", "supply chain", "enterprise", "business", "commercial",
    "corporate", "business customers", "산업", "공급망", "기업용",
    "업무용", "법인", "기업 고객", "사무용",
)
GENERIC_PRODUCTION_TERMS = ("production", "shipment", "생산", "출하")
CONSUMER_CHOICE_TERMS = (
    "compare", "comparison", "versus", "controversy", "choice", "price",
    "비교", "논쟁", "선택", "가격",
)


def choice_question_forbidden(article: dict) -> bool:
    text = f"{article.get('title', '')} {article.get('raw_excerpt', '')} {article.get('summary', '')}".lower()
    if article.get("audience_fit") in {"business_user", "developer", "researcher"}:
        return True
    if any(term in text for term in B2B_CHOICE_TERMS):
        return True
    consumer_choice = article.get("audience_fit") == "consumer" or any(
        term in text for term in CONSUMER_CHOICE_TERMS
    )
    return not consumer_choice and any(term in text for term in GENERIC_PRODUCTION_TERMS)


def choice_question_policy(article: dict) -> str:
    """Return an explicit per-article rule shared by generation and review."""
    text = f"{article.get('title', '')} {article.get('raw_excerpt', '')} {article.get('summary', '')}".lower()
    forbidden = choice_question_forbidden(article)
    if forbidden:
        return "B2B·산업·공급망 기사이므로 댓글용 선택 질문을 절대 만들지 않는다."
    allowed = article.get("audience_fit") == "consumer" or any(
        term in text for term in CONSUMER_CHOICE_TERMS
    )
    if allowed:
        return "소비자 선택 또는 실제 논쟁·비교 기사이므로 구체적인 선택 질문을 포함한다."
    return "기사에 실제 선택·논쟁·비교가 없으면 선택 질문을 생략한다."


def remove_forbidden_choice_questions(script: str, article: dict | None) -> str:
    """Deterministically strip forced audience-choice prompts from B2B scripts."""
    text = str(script or "")
    if not article or not choice_question_forbidden(article):
        return text
    forced_choice = re.compile(
        r"여러분은|어느\s*(?:쪽|제품|모델|것)|어떤\s*(?:제품|모델|것)|둘\s*중|"
        r"무엇을\s*선택|댓글|골라|고르|선택하(?:시|실|세요)",
        flags=re.IGNORECASE,
    )
    sentences = re.findall(r"[^.!?。！？]+[.!?。！？]*", text)
    kept = [sentence.strip() for sentence in sentences if not forced_choice.search(sentence)]
    return " ".join(kept).strip()


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
            f"Rumor Status: {article.get('rumor_status', 'rumor' if article.get('event_type') == 'rumor_leak' else 'confirmed')}",
            f"Shorts Score: {article.get('shorts_score', '')}",
        ]
    )


def build_shorts_script_prompt(article: dict, language: str = "Korean", sentence_length: int = 5) -> str:
    """Builds a Korean news-briefing Shorts prompt from a ranked tech-news article."""
    article_block = format_article_for_prompt(article)
    question_policy = choice_question_policy(article)
    return f"""
너는 한국어 최신 IT 뉴스 브리핑 쇼츠 작가다.
아래 뉴스 하나를 바탕으로 {sentence_length}문장 이내의 30~40초 유튜브 쇼츠 대본을 작성하라.

채널 목적:
- 항상 최신 IT/기기/기술 소식을 빠르게 요약해서 전달한다.
- 사용자는 트렌드를 파악하고 순수한 호기심을 채우기 위해 본다.
- 단순 스펙 나열보다 왜 중요한지, 무엇이 바뀌는지를 설명한다.
- 입력의 Angle Type, Hook Type, Viewer Payoff를 반영해서 첫 3초 훅과 전체 관점을 잡는다.

규칙:
- 반드시 한국어로만 작성한다. 입력 뉴스 제목/요약이 영어여도 자연스러운 한국어 나레이션으로 번역·재구성한다.
- 최신 IT 뉴스 브리핑 톤으로 작성한다.
- 첫 문장은 뉴스 제목 반복이 아니라 질문형 훅으로 시작하고, 같은 첫 문장 안에서 답의 방향을 즉시 예고한다. 질문만 던지고 답을 미루지 않는다.
- 질문형 훅과 답의 방향 예고가 보통 말하기 속도 기준 첫 3초 안에 들리도록 짧고 구체적으로 쓴다.
- 전체 흐름은 사실 → 의미 → 시청자 선택 순서로 구성하고, 중간에는 “그래서 왜 중요하냐면”에 해당하는 맥락을 반드시 한 문장 포함한다.
- 저장 유도 금지.
- 시리즈화 금지.
- 기사별 선택 질문 정책: {question_policy}
- 댓글 질문은 허용한다. 가격·부품·브랜드처럼 소비자 선택이나 논쟁이 자연스러운 소재에만 구체적인 선택 질문을 쓴다.
- B2B·산업·공급망 뉴스는 시청자 개인 선택이 없으면 억지 댓글 질문을 만들지 않는다.
- 일반적인 “구독해 주세요” 대신 “검증된 IT 변화와 선택 기준을 계속 빠르게 전한다”처럼 채널 가치 약속이 담긴 구독 CTA를 쓴다.
- 질문과 CTA를 한 문장에 합치지 말고, {sentence_length}문장 제한 안에서 각각 자연스럽게 배치한다. 질문이 불필요하면 생략한다.
- 루머/유출이면 입력의 Confidence와 Rumor Status를 반영해 신뢰도를 분명히 표현하고, 확인된 사실과 주장을 구분하며 확정 표현을 쓰지 않는다.
- 마크다운, 제목, NARRATOR, VOICEOVER 같은 라벨을 쓰지 않는다.
- 출처, 매체명, URL, 도메인, 링크, 날짜 문자열을 나레이션 대본에 넣지 않는다.
- 마지막 문장은 출처 안내가 아니라 채널 가치 약속형 구독 CTA나 핵심 요약으로 끝낸다.

- 제품명과 브랜드명은 뉴스 이해에 꼭 필요할 때만 최소한으로 사용하고, 공식 광고처럼 보이는 홍보 카피는 피한다.
- `국내 최초`, `역대급`, `폭발`, `극대화`, `새로운 기준`, `~하는 법`처럼 광고/선전처럼 보이는 표현을 남발하지 않는다.
- 영어 기술 용어는 한 번만 자연스럽게 병기하고, `AIagentic`처럼 한글과 영어가 붙은 깨진 표현을 절대 만들지 않는다.
- 한글 자모만 남은 깨진 문자나 불필요한 특수문자를 쓰지 않는다.
- `맥그네틱`이 아니라 `마그네틱`처럼 표준적인 한국어 표기를 사용한다.

뉴스 입력:
{article_block}

출력은 실제로 읽을 나레이션 대본만 반환하라.
""".strip()
