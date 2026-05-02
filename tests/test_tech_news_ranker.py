import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class TechNewsRankerTests(unittest.TestCase):
    def test_launched_popular_official_chipset_news_scores_highest(self):
        from news.ranker import rank_articles

        articles = [
            {
                "title": "Researchers begin early battery material study",
                "source_tier": "tech_secondary",
                "raw_excerpt": "A university lab has started research into future batteries.",
                "published_at": "2026-04-24T10:00:00+09:00",
            },
            {
                "title": "Qualcomm launches Snapdragon 8 Elite for flagship phones",
                "source_tier": "official_primary",
                "raw_excerpt": "The new chipset is launching in consumer smartphones with improved NPU performance.",
                "published_at": "2026-04-24T12:00:00+09:00",
            },
        ]

        ranked = rank_articles(articles)

        self.assertEqual(ranked[0]["title"], "Qualcomm launches Snapdragon 8 Elite for flagship phones")
        self.assertGreaterEqual(ranked[0]["shorts_score"], 75)
        self.assertEqual(ranked[0]["event_type"], "product_launch")
        self.assertIn("Qualcomm", ranked[0]["brands"])
        self.assertIn("chipset", ranked[0]["technologies"])

    def test_rumor_is_ranked_but_never_marked_for_push_alert(self):
        from news.ranker import score_article

        article = {
            "title": "iPhone 17 leak suggests a new display design",
            "source_tier": "rumor_leak",
            "raw_excerpt": "A non-official leak claims Apple may use a different OLED panel.",
            "published_at": "2026-04-24T12:00:00+09:00",
        }

        scored = score_article(article)

        self.assertEqual(scored["event_type"], "rumor_leak")
        self.assertFalse(scored["alert_allowed"])
        self.assertLess(scored["confidence"], 0.65)
    def test_common_word_nothing_does_not_match_nothing_brand(self):
        from news.ranker import score_article

        article = {
            "title": "There is nothing surprising about this Apple update",
            "source_tier": "news_secondary",
            "raw_excerpt": "Apple released a small software update for iPhone users.",
        }

        scored = score_article(article)

        self.assertIn("Apple", scored["brands"])
        self.assertNotIn("Nothing", scored["brands"])


if __name__ == "__main__":
    unittest.main()
