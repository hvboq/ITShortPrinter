import os
import sys
import types
import unittest
from unittest.mock import Mock


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

fake_srt_equalizer = types.ModuleType("srt_equalizer")
fake_srt_equalizer.equalize_srt_file = lambda *args, **kwargs: None
sys.modules.setdefault("srt_equalizer", fake_srt_equalizer)

fake_termcolor = types.ModuleType("termcolor")
fake_termcolor.colored = lambda text, *args, **kwargs: text
sys.modules.setdefault("termcolor", fake_termcolor)

fake_ollama = types.ModuleType("ollama")
fake_ollama.Client = object
sys.modules.setdefault("ollama", fake_ollama)

import news_pipeline
from news_pipeline import NewsPipeline

news_pipeline.info = lambda *args, **kwargs: None
news_pipeline.warning = lambda *args, **kwargs: None


class MockResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class NewsPipelineTests(unittest.TestCase):
    def build_pipeline(self) -> NewsPipeline:
        config = {
            "enabled": True,
            "max_article_age_hours": 9999,
            "max_candidates_per_source": 3,
            "max_selected_articles": 3,
            "use_llm_scoring": True,
            "sources": ["theverge", "zdnet_korea", "bloter"],
            "priority_keywords": ["samsung", "udc", "battery", "launch", "출시"],
            "scoring_weights": {
                "public_interest": 0.35,
                "realism": 0.30,
                "llm": 0.25,
                "keyword": 0.10,
            },
        }
        pipeline = NewsPipeline(session=Mock(), config=config)
        pipeline.processed_urls = set()
        return pipeline

    def test_verge_rss_and_article_are_ranked(self) -> None:
        pipeline = self.build_pipeline()
        news_pipeline.generate_text = (
            lambda *args, **kwargs: '{"score": 84, "reason": "Strong mainstream product relevance."}'
        )
        news_pipeline.get_ollama_model = lambda: "gemma4:26b"
        pipeline.session.get.side_effect = [
            MockResponse(
                """<?xml version="1.0"?>
                <rss><channel>
                <item><link>https://www.theverge.com/tech/123/sample-story</link></item>
                </channel></rss>"""
            ),
            MockResponse("<html></html>"),
            MockResponse(
                """
                <html>
                    <head>
                        <meta property="og:title" content="Samsung UDC phone launch" />
                        <meta property="article:published_time" content="2026-04-21T10:00:00+00:00" />
                        <meta property="og:description" content="Samsung unveiled a new UDC concept." />
                    </head>
                    <body>
                        <article>
                            <p>Samsung unveiled a new under-display camera phone.</p>
                            <p>The launch focuses on display quality and battery life.</p>
                            <p>The product is expected to arrive in consumer devices soon.</p>
                            <p>Executives said the technology is designed for mainstream devices instead of distant concept hardware.</p>
                            <p>The company also highlighted better image processing and improved panel transparency for daily use.</p>
                        </article>
                    </body>
                </html>
                """
            ),
            MockResponse("<html></html>"),
            MockResponse("<html></html>"),
        ]

        articles = pipeline.collect_ranked_articles()

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].source, "theverge")
        self.assertIn("Samsung", articles[0].title)
        self.assertEqual(articles[0].llm_score, 84)
        self.assertGreater(articles[0].public_interest_score, 0)
        self.assertGreater(articles[0].realism_score, 0)
        self.assertGreater(articles[0].score, 0)

    def test_zdnet_candidate_filter_accepts_view_pages(self) -> None:
        pipeline = self.build_pipeline()

        self.assertTrue(
            pipeline._is_valid_candidate_url(
                "zdnet_korea",
                "https://zdnet.co.kr/view/?no=20260421140621",
                {"zdnet.co.kr", "www.zdnet.co.kr"},
            )
        )
        self.assertFalse(
            pipeline._is_valid_candidate_url(
                "zdnet_korea",
                "https://zdnet.co.kr/newsletter",
                {"zdnet.co.kr", "www.zdnet.co.kr"},
            )
        )

    def test_general_non_article_paths_are_blocked(self) -> None:
        pipeline = self.build_pipeline()

        blocked_cases = [
            ("theverge", "https://www.theverge.com/rss/index.xml", {"www.theverge.com", "theverge.com"}),
            ("theverge", "https://www.theverge.com/tag/samsung", {"www.theverge.com", "theverge.com"}),
            ("theverge", "https://www.theverge.com/topic/ai", {"www.theverge.com", "theverge.com"}),
            ("bloter", "https://www.bloter.net/newsroom", {"www.bloter.net", "bloter.net"}),
            ("bloter", "https://www.bloter.net/section/it", {"www.bloter.net", "bloter.net"}),
        ]

        for source, url, domains in blocked_cases:
            self.assertFalse(pipeline._is_valid_candidate_url(source, url, domains))

    def test_article_dedupe_uses_normalized_title(self) -> None:
        pipeline = self.build_pipeline()
        article_one = type(
            "Article",
            (),
            {"title": "Samsung UDC Launch!", "source": "theverge", "url": "a"},
        )()
        article_two = type(
            "Article",
            (),
            {"title": "Samsung UDC Launch", "source": "zdnet_korea", "url": "b"},
        )()

        dedupe_key_one = pipeline._build_dedupe_key(article_one)
        dedupe_key_two = pipeline._build_dedupe_key(article_two)

        self.assertEqual(dedupe_key_one, dedupe_key_two)

    def test_article_quality_gate_rejects_index_like_page(self) -> None:
        pipeline = self.build_pipeline()

        self.assertFalse(
            pipeline._looks_like_article(
                title="The Verge",
                content="Short listing text only",
                summary="Collection page",
                published_at="2026-04-21T10:00:00",
            )
        )
        self.assertTrue(
            pipeline._looks_like_article(
                title="Samsung launches a new UDC phone",
                content=(
                    "Samsung unveiled a new device. "
                    "It uses an under-display camera and a brighter display. "
                    "The product is expected to reach consumers in the near term. "
                    "The device is built for mainstream users and should ship soon. "
                    "Samsung said production planning is already underway for the next release cycle. "
                    "Executives described the product as a practical upgrade rather than an experimental concept. "
                    "The phone is positioned as a consumer model with clearer imaging and better battery efficiency."
                ),
                summary="A new Samsung phone with under-display camera technology.",
                published_at="2026-04-21T10:00:00",
            )
        )

    def test_product_launch_scores_above_management_news(self) -> None:
        pipeline = self.build_pipeline()

        product_public = pipeline._score_public_interest(
            "Samsung launches a new battery phone",
            "A consumer smartphone release with silicon-carbon battery.",
            "Samsung announced a new smartphone launch with better battery life and brighter display for consumers this year.",
        )
        management_public = pipeline._score_public_interest(
            "Apple CEO meets investors",
            "Executive transition and strategy update.",
            "Apple discussed executive leadership, investor relations, and corporate strategy during a management event.",
        )

        product_keyword = pipeline._score_keyword_relevance(
            "Samsung launches a new battery phone",
            "A consumer smartphone release with silicon-carbon battery.",
            "Samsung announced a new smartphone launch with better battery life and brighter display for consumers this year.",
            "theverge",
        )
        management_keyword = pipeline._score_keyword_relevance(
            "Apple CEO meets investors",
            "Executive transition and strategy update.",
            "Apple discussed executive leadership, investor relations, and corporate strategy during a management event.",
            "theverge",
        )

        self.assertGreater(product_public, management_public)
        self.assertGreater(product_keyword, management_keyword)

    def test_realism_penalizes_far_future_concepts(self) -> None:
        pipeline = self.build_pipeline()

        near_term_score = pipeline._score_realism(
            "Samsung launches a new display tech",
            "Commercial product release next year.",
            "Samsung said the display technology enters production next year and will ship in consumer products.",
        )
        far_future_score = pipeline._score_realism(
            "Lab reveals concept device",
            "A long-term theoretical concept.",
            "Researchers described a concept only project that may become practical in 2040 or later.",
        )

        self.assertGreater(near_term_score, far_future_score)

    def test_bloter_article_content_uses_id_selector(self) -> None:
        pipeline = self.build_pipeline()
        content = pipeline._extract_content(
            """
            <html>
                <body>
                    <div id="article-view-content-div">
                        <p>에픽게임즈가 트윈모션 2026.1을 공개하며 실시간 3D 시각화 기능을 대폭 강화했다고 밝혔다.</p>
                        <p>이번 업데이트는 실제 카메라와 유사한 렌즈 표현과 시각화 품질 개선을 포함한다.</p>
                        <p>사용자 편의성 개선과 다양한 산업 분야 적용도 함께 강조됐다.</p>
                    </div>
                </body>
            </html>
            """,
            "bloter",
        )

        self.assertIn("트윈모션 2026.1", content)
        self.assertIn("시각화 품질 개선", content)

    def test_final_score_uses_weighted_breakdown(self) -> None:
        pipeline = self.build_pipeline()

        score = pipeline._calculate_final_score(
            public_interest_score=80,
            realism_score=70,
            llm_score=60,
            keyword_score=50,
        )

        expected = round(80 * 0.35 + 70 * 0.30 + 60 * 0.25 + 50 * 0.10)
        self.assertEqual(score, expected)


if __name__ == "__main__":
    unittest.main()
