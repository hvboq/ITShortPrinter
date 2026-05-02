from __future__ import annotations

from .fetcher import fetch_rss
from .ranker import rank_articles
from .sources import PHASE_1_SOURCES


def collect_ranked_news(sources: list[dict] | None = None, limit: int = 20) -> list[dict]:
    """Fetch configured RSS sources and return ranked tech-news candidates."""
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
        except Exception:
            continue
    return rank_articles(all_articles)[:limit]


def get_top_news(sources: list[dict] | None = None) -> dict | None:
    ranked = collect_ranked_news(sources=sources, limit=1)
    return ranked[0] if ranked else None
