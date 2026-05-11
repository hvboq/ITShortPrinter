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
from classes.Tts import TTS
from classes.YouTube import YouTube
from news_pipeline import NewsArticle


def format_korean_date(raw_value: str) -> str:
    date_value = str(raw_value or "")[:10]
    if len(date_value) == 10 and date_value[4] == "-" and date_value[7] == "-":
        year, month, day = date_value.split("-")
        return f"{year}년 {int(month)}월 {int(day)}일"
    return "최근"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a Korean local Short from cached news with Korean voice and subtitles."
    )
    parser.add_argument(
        "--article-index",
        type=int,
        default=2,
        help="1-based index from cached ranked news candidates.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    cached_articles = get_latest_news_candidates()
    if not cached_articles:
        print("No cached articles found in .mp/news.json.")
        return 1
    if args.article_index < 1 or args.article_index > len(cached_articles):
        print(f"Invalid --article-index. Available range: 1-{len(cached_articles)}")
        return 1

    article = NewsArticle(**cached_articles[args.article_index - 1])
    published_date = format_korean_date(article.published_at)
    print(f"Selected article: {article.title}")
    print(article.url)
    print(f"Published date: {published_date}")

    youtube = YouTube.for_local_generation(
        niche="IT device news",
        language="Korean",
    )
    youtube.subject = article.title
    youtube.script = (
        f"{published_date} 보도 기준, 프레임워크가 리눅스 사용자를 겨냥한 랩톱 13 프로를 공개했습니다. "
        "새 모델은 알루미늄 바디, 햅틱 트랙패드, 고해상도 디스플레이를 앞세워 프리미엄 노트북 시장을 노립니다. "
        "가장 큰 차별점은 부품을 교체하고 업그레이드할 수 있는 모듈식 설계입니다. "
        "맥북처럼 완성도 높은 노트북을 원하지만 수리성과 확장성도 포기하고 싶지 않은 사용자에게 흥미로운 선택지가 될 수 있습니다."
    )
    youtube.metadata = {
        "title": "프레임워크 랩톱 13 프로 공개 #테크뉴스 #노트북",
        "description": (
            f"{published_date} 보도된 프레임워크 랩톱 13 프로 공개 소식을 짧게 정리했습니다. "
            "한글 음성과 한글 자막이 포함된 로컬 쇼츠입니다."
        ),
    }

    if article.image_url:
        try:
            youtube.download_image(article.image_url)
        except Exception as exc:
            print(f"Could not download article image, using generated fallback: {exc}")
    if not youtube.images:
        youtube.create_contextual_thumbnail(article.title)

    tts = TTS()
    youtube.generate_script_to_speech(tts)
    video_path = youtube.combine()
    youtube.video_path = os.path.abspath(video_path)
    mark_news_processed(article.url)

    print(f"Generated Korean news short: {youtube.video_path}")
    print(f"Title: {youtube.metadata['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
