#!/usr/bin/env python3
import argparse
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from cache import get_latest_news_candidates
from cache import mark_news_processed
from config import assert_folder_structure
from config import get_ollama_model
from llm_provider import select_model
from news_pipeline import NewsArticle
from news_pipeline import NewsPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a local YouTube Short from the top ranked tech-news article."
    )
    parser.add_argument(
        "--article-index",
        type=int,
        default=1,
        help="1-based index from the ranked article list to use.",
    )
    parser.add_argument(
        "--language",
        default="Korean",
        help="Language for the generated voiceover and metadata.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Text model override. Supports local Ollama models and Gemini models like gemini-2.5-flash.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and print the selected article without generating media.",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use cached ranked news candidates from .mp/news.json instead of collecting fresh articles.",
    )
    return parser.parse_args()


def load_cached_articles() -> list[NewsArticle]:
    """
    Loads cached ranked news candidates from the local cache file.

    Returns:
        articles (list[NewsArticle]): Cached articles
    """
    articles = []
    for item in get_latest_news_candidates():
        if not isinstance(item, dict):
            continue
        try:
            articles.append(NewsArticle(**item))
        except TypeError:
            continue
    return articles


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    assert_folder_structure()

    configured_model = args.model.strip() or get_ollama_model()
    if configured_model:
        select_model(configured_model)
        print(f"Using text model: {configured_model}")
    else:
        print("No text model configured. Set ollama_model or pass --model.")
        return 1

    if args.use_cache:
        articles = load_cached_articles()
        print(f"Loaded {len(articles)} cached articles.")
    else:
        pipeline = NewsPipeline()
        articles = pipeline.collect_ranked_articles()
        if not articles:
            articles = load_cached_articles()
            if articles:
                print(
                    "Fresh news collection returned no articles. Falling back to cached candidates."
                )

    if not articles:
        print("No ranked tech-news articles were collected.")
        return 1

    if args.article_index < 1 or args.article_index > len(articles):
        print(f"Invalid --article-index. Available range: 1-{len(articles)}")
        return 1

    article = articles[args.article_index - 1]
    print(f"Selected article: [{article.score}] {article.title}")
    print(article.url)

    if args.dry_run:
        return 0

    from classes.Tts import TTS
    from classes.YouTube import YouTube

    youtube = YouTube.for_local_generation(
        niche="IT device news",
        language=args.language,
    )
    tts = TTS()
    video_path = youtube.generate_video_from_news(tts, article)

    mark_news_processed(article.url)
    print(f"Generated news short: {video_path}")
    print(f"Title: {youtube.metadata.get('title', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
