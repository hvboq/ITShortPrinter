from __future__ import annotations

from dataclasses import asdict

from config import get_news_pipeline_config
from status import warning

from .archive import (
    archive_articles,
    article_matches_existing_keys,
    existing_article_keys,
    normalize_key,
    prune_daily_top_articles,
)
from .fetcher import fetch_rss
from .ranker import (
    SOURCE_CONFIDENCE,
    classify_event,
    is_channel_scope_excluded,
    is_speculative,
    rank_articles,
    strategy_priority_bonus,
)
from .sources import PHASE_1_SOURCES, PRODUCT_LAUNCH_SOURCES


def _advanced_article_to_ranked_dict(article) -> dict:
    """Convert NewsPipeline articles to the lightweight ranked-news contract."""
    item = (
        asdict(article)
        if hasattr(article, "__dataclass_fields__")
        else dict(article)
    )
    summary = item.get("summary") or item.get("content", "")
    base_score = item.get("score", 0)
    try:
        base_score = int(round(float(base_score)))
    except (TypeError, ValueError):
        base_score = 0
    text = f"{item.get('title', '')} {summary}".lower()
    source_tier = item.get("source_tier") or "news_secondary"
    event_type = item.get("event_type") or classify_event({**item, "source_tier": source_tier}, text)
    classification_record = {**item, "source_tier": source_tier, "event_type": event_type}
    speculative = is_speculative(classification_record)
    rumor_status = item.get("rumor_status") or ("rumor" if speculative else "confirmed")
    policy_bonus = strategy_priority_bonus(text, classification_record)
    shorts_score = min(100, base_score + policy_bonus)
    if speculative:
        shorts_score = min(shorts_score, 74)
    confidence = item.get("confidence")
    if confidence is None:
        confidence = SOURCE_CONFIDENCE.get(source_tier, 0.55)
    return {
        "source_id": item.get("source_id") or item.get("source", ""),
        "source_name": item.get("source_name") or item.get("source", ""),
        "source_tier": source_tier,
        "language": item.get("language", "unknown"),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "canonical_url": item.get("canonical_url") or item.get("url", ""),
        "published_at": item.get("published_at"),
        "fetched_at": item.get("fetched_at", ""),
        "author": item.get("author"),
        "raw_excerpt": summary,
        "brands": item.get("brands", []),
        "technologies": item.get("technologies", []),
        "event_type": event_type,
        "confidence": confidence,
        "audience_fit": item.get("audience_fit", ""),
        "shorts_score": shorts_score,
        "strategy_priority_bonus": policy_bonus,
        "alert_allowed": shorts_score >= 75 and not speculative,
        "rumor_status": rumor_status,
        "advanced_scores": {
            "public_interest": item.get("public_interest_score", 0),
            "realism": item.get("realism_score", 0),
            "llm": item.get("llm_score", 0),
            "keyword": item.get("keyword_score", 0),
            "reason": item.get("score_reason", ""),
        },
    }


def _filter_channel_scope(articles) -> list:
    """Apply the hard off-channel gate before archive or live selection."""
    return [
        article for article in articles
        if not is_channel_scope_excluded(article if isinstance(article, dict) else asdict(article))
    ]


def rank_product_slot_articles(articles: list[dict]) -> list[dict]:
    """Apply audience ordering only to the dedicated 13:00 product slot."""
    def priority(item: dict) -> tuple[int, int]:
        text = f"{item.get('title', '')} {item.get('raw_excerpt', '')} {item.get('summary', '')}".lower()
        rumor_status = str(item.get("rumor_status") or "").lower()
        event_type = str(item.get("event_type") or "").lower()
        source_tier = str(item.get("source_tier") or "").lower()
        speculative = is_speculative(item)
        affirmative = (
            rumor_status in {"confirmed", "verified", "official"}
            or event_type in {"official_release", "product_launch", "price_availability", "production_start"}
            or any(term in text for term in ("official", "confirmed", "verified", "공식", "확정", "확인"))
        )
        confirmed = (
            affirmative
            and rumor_status not in {"rumor", "unconfirmed", "speculative", "leak"}
            and event_type != "rumor_leak"
            and source_tier != "rumor_leak"
            and not speculative
        )
        strategic = confirmed and strategy_priority_bonus(text, item) > 0 and any(
            term in text for term in ("semiconductor", "반도체", "hbm", "gpu")
        ) and any(
            term in text for term in ("mass production", "production starts", "shipment", "양산", "대량 생산", "출하")
        )
        if strategic:
            band = 0
        else:
            audience = str(item.get("audience_fit") or "").lower()
            explicit_bands = {"consumer": 1, "prosumer": 2, "business_user": 4, "developer": 4, "researcher": 4}
            if audience in explicit_bands:
                band = explicit_bands[audience]
            elif any(term in text for term in ("consumer", "일반 사용자", "소비자용", "개인 사용자")):
                band = 1
            elif any(term in text for term in ("prosumer", "프로슈머", "creator", "크리에이터", "전문가용")):
                band = 2
            elif any(term in text for term in (
                "b2b", "enterprise", "industrial", "business", "commercial", "corporate",
                "business customers", "기업용", "산업용", "물류", "업무용", "법인", "기업 고객", "사무용",
            )):
                band = 4
            else:
                band = 3
        return band, -int(item.get("shorts_score", 0) or 0)

    return sorted(articles, key=priority)


def _collect_ranked_news_from_pipeline(limit: int) -> list[dict]:
    config = get_news_pipeline_config()
    if not config.get("enabled", False):
        return []

    from news_pipeline import NewsPipeline

    pipeline = NewsPipeline(config=config)
    return _filter_channel_scope([
        _advanced_article_to_ranked_dict(article)
        for article in pipeline.collect_ranked_articles()[:limit]
    ])


def collect_ranked_news(sources: list[dict] | None = None, limit: int = 20) -> list[dict]:
    """Fetch configured sources and return newly collected/ranked tech-news candidates.

    Prefer the advanced news pipeline when enabled and no explicit source list is
    provided. For the RSS fallback, check the persistent archive before saving
    and ranking so previously collected URLs or titles are skipped.
    """
    if sources is None:
        try:
            advanced_articles = _collect_ranked_news_from_pipeline(limit=limit)
            if advanced_articles:
                try:
                    archive_articles(advanced_articles)
                    prune_daily_top_articles(per_day_limit=50, keep_ties=True)
                except Exception as exc:
                    print(f"NEWS_ARCHIVE_ERROR={type(exc).__name__}:{exc}")
                return advanced_articles
        except Exception as exc:
            warning(f"Advanced news pipeline failed; falling back to RSS: {exc}")

    try:
        archive_keys = existing_article_keys()
        existing_count = len(archive_keys.get("ids", set()))
        if existing_count:
            print(f"NEWS_ARCHIVE_EXISTING_COUNT={existing_count}")
    except Exception as exc:
        print(f"NEWS_ARCHIVE_DEDUPE_LOAD_ERROR={type(exc).__name__}:{exc}")
        archive_keys = {"ids": set(), "urls": set(), "titles": set()}

    all_articles = []
    run_urls = set()
    run_titles = set()
    duplicate_count = 0
    for source in sources or PHASE_1_SOURCES:
        try:
            fetched_articles = fetch_rss(
                source["rss_url"],
                source_id=source["id"],
                source_name=source["name"],
                source_tier=source["tier"],
            )
        except Exception as exc:
            warning(f"Failed to fetch RSS source {source.get('id', '?')}: {exc}")
            continue
        for article in fetched_articles:
            url_key = normalize_key(article.get("canonical_url") or article.get("url"))
            title_key = normalize_key(article.get("title"))
            if article_matches_existing_keys(article, archive_keys):
                duplicate_count += 1
                continue
            if (url_key and url_key in run_urls) or (title_key and title_key in run_titles):
                duplicate_count += 1
                continue
            if url_key:
                run_urls.add(url_key)
            if title_key:
                run_titles.add(title_key)
            if not is_channel_scope_excluded(article):
                all_articles.append(article)

    if duplicate_count:
        print(f"NEWS_ARCHIVE_SKIPPED_DUPLICATES={duplicate_count}")
    ranked_articles = rank_articles(all_articles)
    try:
        archived_count = archive_articles(ranked_articles)
        if archived_count:
            print(f"NEWS_ARCHIVE_SAVED={archived_count}")
        pruned_count = prune_daily_top_articles(per_day_limit=50, keep_ties=True)
        if pruned_count:
            print(f"NEWS_ARCHIVE_PRUNED_BELOW_DAILY_TOP50={pruned_count}")
    except Exception as exc:
        print(f"NEWS_ARCHIVE_ERROR={type(exc).__name__}:{exc}")
    return ranked_articles[:limit]


def collect_product_launch_news(limit: int = 20) -> list[dict]:
    """Collect only product-launch/new-release candidates for the 13:00 slot.

    This intentionally bypasses the optional broad advanced pipeline and uses
    launch-focused RSS/search feeds so the product cron job does not spend its
    candidate budget on market/context/component stories.
    """
    return rank_product_slot_articles(
        _filter_channel_scope(collect_ranked_news(sources=PRODUCT_LAUNCH_SOURCES, limit=limit))
    )


def get_top_news(sources: list[dict] | None = None) -> dict | None:
    ranked = collect_ranked_news(sources=sources, limit=1)
    return ranked[0] if ranked else None
