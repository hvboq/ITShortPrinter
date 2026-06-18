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

    def test_parse_atom_entries_into_normalized_articles(self):
        from news.fetcher import parse_rss

        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>GLM 5.2 출시</title>
            <link rel="alternate" type="text/html" href="https://news.hada.io/topic?id=30478" />
            <summary>오픈소스 모델과 긴 컨텍스트 지원 소식입니다.</summary>
            <published>2026-06-14T13:29:43+09:00</published>
          </entry>
        </feed>
        """

        articles = parse_rss(xml, source_id="geeknews", source_name="GeekNews", source_tier="tech_secondary")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source_id"], "geeknews")
        self.assertEqual(articles[0]["title"], "GLM 5.2 출시")
        self.assertEqual(articles[0]["url"], "https://news.hada.io/topic?id=30478")
        self.assertIn("오픈소스 모델", articles[0]["raw_excerpt"])


    def test_parse_rss_escapes_non_xml_named_entities(self):
        from news.fetcher import parse_rss

        xml = """<?xml version="1.0"?>
        <rss><channel><title>Example</title>
          <item>
            <title>Meeco R&amp;D & GPU news</title>
            <link>https://meeco.kr/news/123</link>
            <description>GPU & AI 소식입니다.</description>
          </item>
        </channel></rss>
        """

        articles = parse_rss(xml, source_id="meeco_news", source_name="Meeco", source_tier="community_secondary")

        self.assertEqual(len(articles), 1)
        self.assertIn("R&D", articles[0]["title"])
        self.assertIn("GPU & AI", articles[0]["raw_excerpt"])


    def test_parse_relative_feed_links_against_base_url(self):
        from news.fetcher import parse_rss

        xml = """<?xml version="1.0"?>
        <rss><channel><title>Example</title>
          <item>
            <title>Samsung Mobile Press article</title>
            <link>/articles/galaxy-xr-launch</link>
            <description>Samsung announced a new Galaxy product.</description>
          </item>
        </channel></rss>
        """

        articles = parse_rss(
            xml,
            source_id="samsung_mobile_press",
            source_name="Samsung Mobile Press",
            source_tier="official_primary",
            base_url="https://www.samsungmobilepress.com/feed",
        )

        self.assertEqual(articles[0]["url"], "https://www.samsungmobilepress.com/articles/galaxy-xr-launch")


if __name__ == "__main__":
    unittest.main()
