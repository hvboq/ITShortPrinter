import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class RssFetcherTests(unittest.TestCase):
    def test_parse_rss_items_into_normalized_articles(self):
        from news.fetcher import parse_rss

        xml = """<?xml version="1.0"?>
        <rss><channel><title>Example</title>
          <item>
            <title>Apple announces new iPhone display technology</title>
            <link>https://example.com/iphone</link>
            <description>Apple announced a new OLED display for iPhone.</description>
            <pubDate>Fri, 24 Apr 2026 10:00:00 GMT</pubDate>
          </item>
        </channel></rss>
        """

        articles = parse_rss(xml, source_id="apple_newsroom", source_name="Apple Newsroom", source_tier="official_primary")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source_id"], "apple_newsroom")
        self.assertEqual(articles[0]["source_tier"], "official_primary")
        self.assertEqual(articles[0]["title"], "Apple announces new iPhone display technology")
        self.assertEqual(articles[0]["url"], "https://example.com/iphone")
        self.assertIn("OLED", articles[0]["raw_excerpt"])


if __name__ == "__main__":
    unittest.main()
