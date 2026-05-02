#!/usr/bin/env python3
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from news_pipeline import NewsPipeline


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pipeline = NewsPipeline()
    articles = pipeline.collect_ranked_articles()

    for index, article in enumerate(articles, start=1):
        print(f"{index}. [{article.score}] {article.title}")
        print(f"   {article.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
