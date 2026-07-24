import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class NewsArchiveTests(unittest.TestCase):
    def test_init_archive_repairs_partial_schema_missing_source_id(self):
        from news.archive import init_archive

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            con = sqlite3.connect(db_path)
            try:
                con.execute(
                    """
                    CREATE TABLE articles (
                        id TEXT PRIMARY KEY,
                        canonical_url TEXT,
                        title TEXT NOT NULL,
                        published_at TEXT,
                        archived_at TEXT NOT NULL,
                        shorts_score INTEGER
                    )
                    """
                )
                con.commit()
            finally:
                con.close()

            init_archive(db_path)

            con = sqlite3.connect(db_path)
            try:
                columns = {
                    row[1]
                    for row in con.execute("PRAGMA table_info(articles)").fetchall()
                }
                indexes = {
                    row[1]
                    for row in con.execute("PRAGMA index_list(articles)").fetchall()
                }
            finally:
                con.close()

            self.assertIn("source_id", columns)
            self.assertIn("idx_articles_source_id", indexes)

    def test_archive_articles_upserts_summary_and_scores(self):
        from news.archive import archive_articles, recent_articles
        from news.ranker import score_article

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            article = score_article(
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "language": "en",
                    "title": "Samsung launches a new OLED phone",
                    "url": "https://example.com/samsung-oled",
                    "canonical_url": "https://example.com/samsung-oled",
                    "published_at": "2026-05-05T00:00:00+00:00",
                    "fetched_at": "2026-05-05T00:01:00+00:00",
                    "author": "Reporter",
                    "raw_excerpt": "<p>Samsung announced a brighter OLED display for a new phone.</p>",
                }
            )

            self.assertEqual(archive_articles([article], db_path=db_path), 1)
            self.assertEqual(archive_articles([article], db_path=db_path), 1)

            con = sqlite3.connect(db_path)
            count = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            row = con.execute(
                "SELECT title, content_summary, shorts_score, brands_json, payload_json FROM articles"
            ).fetchone()
            con.close()

            self.assertEqual(count, 1)
            self.assertEqual(row[0], "Samsung launches a new OLED phone")
            self.assertIn("brighter OLED", row[1])
            self.assertIsInstance(row[2], int)
            self.assertIn("Samsung", row[3])
            self.assertIn("canonical_url", row[4])
            self.assertEqual(len(recent_articles(db_path=db_path)), 1)

    def test_mark_shorts_status_tracks_selected_generated_uploaded(self):
        from news.archive import archive_articles, mark_shorts_status
        from news.ranker import score_article

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            article = score_article(
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "title": "Logitech launches a new keyboard",
                    "url": "https://example.com/keyboard",
                    "canonical_url": "https://example.com/keyboard",
                    "raw_excerpt": "Logitech launched a mechanical keyboard for PC users.",
                }
            )
            archive_articles([article], db_path=db_path)

            self.assertEqual(mark_shorts_status(article, "selected", rank=2, db_path=db_path), 1)
            self.assertEqual(
                mark_shorts_status(article, "generated", rank=2, video_path="/tmp/short.mp4", db_path=db_path),
                1,
            )
            self.assertEqual(
                mark_shorts_status(
                    {"article_url": "https://example.com/keyboard", "article_title": "Logitech launches a new keyboard"},
                    "uploaded",
                    rank=2,
                    video_path="/tmp/short.mp4",
                    uploaded_url="https://youtube.com/shorts/abc123",
                    db_path=db_path,
                ),
                1,
            )

            con = sqlite3.connect(db_path)
            row = con.execute(
                """
                SELECT shorts_video_status, shorts_rank, shorts_video_path, shorts_uploaded_url,
                       shorts_selected_at, shorts_generated_at, shorts_uploaded_at
                FROM articles
                """
            ).fetchone()
            con.close()

            self.assertEqual(row[0], "uploaded")
            self.assertEqual(row[1], 2)
            self.assertEqual(row[2], "/tmp/short.mp4")
            self.assertEqual(row[3], "https://youtube.com/shorts/abc123")
            self.assertTrue(row[4])
            self.assertTrue(row[5])
            self.assertTrue(row[6])

    def test_mark_shorts_status_tracks_quality_review_state(self):
        from news.archive import archive_articles, mark_shorts_status
        from news.ranker import score_article

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            article = score_article(
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "title": "A test phone launch needs video review",
                    "url": "https://example.com/review-phone",
                    "canonical_url": "https://example.com/review-phone",
                    "raw_excerpt": "A product launch article for a generated video.",
                }
            )
            archive_articles([article], db_path=db_path)

            self.assertEqual(
                mark_shorts_status(
                    article,
                    "needs_review",
                    rank=3,
                    video_path="/tmp/review-short.mp4",
                    db_path=db_path,
                ),
                1,
            )

            con = sqlite3.connect(db_path)
            row = con.execute(
                """
                SELECT shorts_video_status, shorts_rank, shorts_video_path, shorts_generated_at
                FROM articles
                """
            ).fetchone()
            con.close()

            self.assertEqual(row[0], "needs_review")
            self.assertEqual(row[1], 3)
            self.assertEqual(row[2], "/tmp/review-short.mp4")
            self.assertTrue(row[3])

    def test_archive_articles_defaults_missing_fetched_at(self):
        from news.archive import archive_articles

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            article = {
                "id": "missing-fetched-at",
                "title": "Samsung launches a new display phone",
                "url": "https://example.com/display-phone",
                "canonical_url": "https://example.com/display-phone",
                "shorts_score": 80,
            }

            archive_articles([article], db_path=db_path)

            con = sqlite3.connect(db_path)
            row = con.execute(
                "SELECT fetched_at, archived_at, payload_json FROM articles WHERE id = ?",
                ("missing-fetched-at",),
            ).fetchone()
            con.close()

            self.assertTrue(row[0])
            self.assertEqual(row[0], row[1])
            self.assertIn('"fetched_at"', row[2])

    def test_collect_ranked_news_archives_all_collected_articles_before_limit(self):
        import news.collector as collector

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            sources = [
                {"rss_url": "https://example.com/rss", "id": "example", "name": "Example Tech", "tier": "news_secondary"}
            ]
            fetched = [
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "language": "en",
                    "title": "Apple announces new iPad display",
                    "url": "https://example.com/ipad",
                    "canonical_url": "https://example.com/ipad",
                    "published_at": "2026-05-05T00:00:00+00:00",
                    "fetched_at": "2026-05-05T00:01:00+00:00",
                    "author": None,
                    "raw_excerpt": "Apple announced a new OLED iPad display.",
                },
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "language": "en",
                    "title": "Logitech launches a new keyboard",
                    "url": "https://example.com/keyboard",
                    "canonical_url": "https://example.com/keyboard",
                    "published_at": "2026-05-05T00:02:00+00:00",
                    "fetched_at": "2026-05-05T00:03:00+00:00",
                    "author": None,
                    "raw_excerpt": "Logitech launched a mechanical keyboard for PC users.",
                },
            ]

            archive_module = __import__("news.archive", fromlist=["archive_articles", "existing_article_keys"])
            with patch.object(collector, "fetch_rss", return_value=fetched), patch.object(
                collector, "existing_article_keys", side_effect=lambda: archive_module.existing_article_keys(db_path=db_path)
            ), patch.object(
                collector, "archive_articles", side_effect=lambda articles: archive_module.archive_articles(articles, db_path=db_path)
            ), patch.object(collector, "prune_daily_top_articles", return_value=0):
                ranked = collector.collect_ranked_news(sources=sources, limit=1)

            self.assertEqual(len(ranked), 1)
            con = sqlite3.connect(db_path)
            count = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            con.close()
            self.assertEqual(count, 2)

    def test_collect_ranked_news_skips_articles_already_in_archive(self):
        import news.collector as collector
        from news.archive import archive_articles
        from news.ranker import score_article

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            sources = [
                {"rss_url": "https://example.com/rss", "id": "example", "name": "Example Tech", "tier": "news_secondary"}
            ]
            existing = score_article(
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "title": "Apple announces new iPad display",
                    "url": "https://example.com/ipad",
                    "canonical_url": "https://example.com/ipad",
                    "raw_excerpt": "Apple announced a new OLED iPad display.",
                }
            )
            archive_articles([existing], db_path=db_path)
            fetched = [
                dict(existing),
                {
                    "source_id": "example",
                    "source_name": "Example Tech",
                    "source_tier": "news_secondary",
                    "title": "Logitech launches a new keyboard",
                    "url": "https://example.com/keyboard",
                    "canonical_url": "https://example.com/keyboard",
                    "raw_excerpt": "Logitech launched a mechanical keyboard for PC users.",
                },
            ]

            archive_module = __import__("news.archive", fromlist=["archive_articles", "existing_article_keys"])
            with patch.object(collector, "fetch_rss", return_value=fetched), patch.object(
                collector, "existing_article_keys", side_effect=lambda: archive_module.existing_article_keys(db_path=db_path)
            ), patch.object(
                collector, "archive_articles", side_effect=lambda articles: archive_module.archive_articles(articles, db_path=db_path)
            ), patch.object(collector, "prune_daily_top_articles", return_value=0):
                ranked = collector.collect_ranked_news(sources=sources, limit=10)

            self.assertEqual(len(ranked), 1)
            self.assertEqual(ranked[0]["title"], "Logitech launches a new keyboard")
            con = sqlite3.connect(db_path)
            count = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            con.close()
            self.assertEqual(count, 2)
    def test_prune_daily_top_articles_keeps_50th_place_ties_and_lifecycle_rows(self):
        from news.archive import archive_articles, mark_shorts_status, prune_daily_top_articles

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "archive.sqlite3"
            articles = []
            # 55 rows on one fetched day. Rank 50 score is 60, rank 51 ties at 60,
            # so keep_ties=True should retain 51 rows and delete only scores < 60.
            for idx in range(55):
                score = 1000 - idx if idx < 49 else (60 if idx < 51 else 10)
                articles.append(
                    {
                        "id": f"article-{idx}",
                        "title": f"Device launch story {idx}",
                        "url": f"https://example.com/{idx}",
                        "canonical_url": f"https://example.com/{idx}",
                        "fetched_at": "2026-05-08T00:00:00+00:00",
                        "shorts_score": score,
                        "alert_allowed": True,
                    }
                )
            archive_articles(articles, db_path=db_path)
            con = sqlite3.connect(db_path)
            con.execute("UPDATE articles SET fetched_at = ''")
            con.commit()
            con.close()
            # A low-score article that has entered the lifecycle must not be pruned.
            mark_shorts_status(articles[-1], "selected", rank=5, db_path=db_path)

            deleted = prune_daily_top_articles(per_day_limit=50, keep_ties=True, db_path=db_path)

            con = sqlite3.connect(db_path)
            count = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            low_lifecycle = con.execute(
                "SELECT COUNT(*) FROM articles WHERE id = ? AND shorts_video_status = 'selected'",
                ("article-54",),
            ).fetchone()[0]
            min_not_generated_score = con.execute(
                "SELECT MIN(shorts_score) FROM articles WHERE shorts_video_status = 'not_generated'"
            ).fetchone()[0]
            con.close()
            self.assertEqual(deleted, 3)
            self.assertEqual(count, 52)
            self.assertEqual(low_lifecycle, 1)
            self.assertEqual(min_not_generated_score, 60)


if __name__ == "__main__":
    unittest.main()
