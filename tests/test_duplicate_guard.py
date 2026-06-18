import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news.duplicate_guard import canonicalize_url, duplicate_reason, titles_similar  # noqa: E402


class DuplicateGuardTests(unittest.TestCase):
    def test_canonicalize_url_ignores_tracking_and_www(self):
        self.assertEqual(
            canonicalize_url("https://www.example.com/news/allwinner/?utm_source=x&ref=feed&id=7#top"),
            "https://example.com/news/allwinner?id=7",
        )

    def test_duplicate_reason_matches_nested_canonical_article_url(self):
        history = [
            {
                "article_title": "Allwinner unveils new RISC-V chip",
                "article_url": "https://news.example.com/allwinner-chip?utm_source=feed",
            }
        ]
        candidate = {
            "title": "Different generated title",
            "article": {"canonical_url": "https://news.example.com/allwinner-chip"},
        }

        self.assertEqual(duplicate_reason(candidate, history), "url")

    def test_duplicate_reason_matches_highly_similar_titles(self):
        history = [{"article_title": "Allwinner announces new AI chip for low cost devices"}]
        candidate = {"article_title": "Allwinner announces new AI chip for low-cost devices"}

        self.assertTrue(titles_similar(candidate["article_title"], history[0]["article_title"]))
        self.assertEqual(duplicate_reason(candidate, history), "title_similarity")


if __name__ == "__main__":
    unittest.main()
