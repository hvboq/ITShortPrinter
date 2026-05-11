from __future__ import annotations

from dataclasses import asdict

from config import get_news_pipeline_config
from status import warning
from .fetcher import fetch_rss
from .ranker import rank_articles
from .sources import PHASE_1_SOURCES


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
    """Fetch configured RSS sources and return ranked tech-news candidates."""
    if sources is None:
        try:
            advanced_articles = _collect_ranked_news_from_pipeline(limit=limit)
            if advanced_articles:
                return advanced_articles
        except Exception as exc:
            warning(f"Advanced news pipeline failed; falling back to RSS: {exc}")

    all_articles = []
    for source in sources or PHASE_1_SOURCES:
        try:
            all_articles.extend(
                fetch_rss(
                    source["rss_url"],
                    source_id=source["id"],
                    source_name=source["name"],
                    source_tier=source["tier"],
                )
            )
        except Exception as exc:
            warning(f"Failed to fetch RSS source {source.get('id', '?')}: {exc}")
            continue
    return rank_articles(all_articles)[:limit]


def get_top_news(sources: list[dict] | None = None) -> dict | None:
    ranked = collect_ranked_news(sources=sources, limit=1)
    return ranked[0] if ranked else None
