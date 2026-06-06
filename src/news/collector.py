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
from .ranker import rank_articles
from .sources import PHASE_1_SOURCES, PRODUCT_LAUNCH_SOURCES


def _advanced_article_to_ranked_dict(article) -> dict:
    """Convert NewsPipeline articles to the lightweight ranked-news contract."""
    item = (
        asdict(article)
        if hasattr(article, "__dataclass_fields__")
        else dict(article)
    )
    summary = item.get("summary") or item.get("content", "")
    return {
        "source_id": item.get("source", ""),
        "source_name": item.get("source", ""),
        "source_tier": "news_secondary",
        "language": "unknown",
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "canonical_url": item.get("url", ""),
        "published_at": item.get("published_at"),
        "fetched_at": "",
        "author": None,
        "raw_excerpt": summary,
        "brands": [],
        "technologies": [],
        "event_type": "",
        "confidence": "",
        "shorts_score": item.get("score", 0),
        "alert_allowed": item.get("score", 0) >= 75,
        "rumor_status": "confirmed",
        "advanced_scores": {
            "public_interest": item.get("public_interest_score", 0),
            "realism": item.get("realism_score", 0),
            "llm": item.get("llm_score", 0),
            "keyword": item.get("keyword_score", 0),
            "reason": item.get("score_reason", ""),
        },
    }


def _collect_ranked_news_from_pipeline(limit: int) -> list[dict]:
    config = get_news_pipeline_config()
    if not config.get("enabled", False):
        return []

    from news_pipeline import NewsPipeline

    pipeline = NewsPipeline(config=config)
    return [
        _advanced_article_to_ranked_dict(article)
        for article in pipeline.collect_ranked_articles()[:limit]
    ]


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
    return collect_ranked_news(sources=PRODUCT_LAUNCH_SOURCES, limit=limit)


def get_top_news(sources: list[dict] | None = None) -> dict | None:
    ranked = collect_ranked_news(sources=sources, limit=1)
    return ranked[0] if ranked else None
