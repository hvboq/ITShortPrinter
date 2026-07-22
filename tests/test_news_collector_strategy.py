import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news.collector import _advanced_article_to_ranked_dict  # noqa: E402


class AdvancedCollectorStrategyTests(unittest.TestCase):
    def test_advanced_conversion_classifies_speculation_and_withholds_strategy_bonus(self):
        ranked = _advanced_article_to_ranked_dict({
            "source": "advanced",
            "title": "HBM4 GPU 양산 일정 전망",
            "summary": "업계 관측으로 9월 출하 예상",
            "score": 98,
        })

        self.assertEqual(ranked["event_type"], "rumor_leak")
        self.assertEqual(ranked["rumor_status"], "rumor")
        self.assertEqual(ranked["strategy_priority_bonus"], 0)
        self.assertLessEqual(ranked["shorts_score"], 74)
        self.assertFalse(ranked["alert_allowed"])

    def test_advanced_conversion_preserves_structured_ranking_fields(self):
        ranked = _advanced_article_to_ranked_dict({
            "source": "advanced",
            "title": "Official HBM4 production starts",
            "summary": "GPU shipments begin under a confirmed contract.",
            "score": 60,
            "source_tier": "official_primary",
            "event_type": "production_start",
            "rumor_status": "verified",
            "confidence": 0.93,
            "audience_fit": "business_user",
        })

        self.assertEqual(ranked["source_tier"], "official_primary")
        self.assertEqual(ranked["event_type"], "production_start")
        self.assertEqual(ranked["rumor_status"], "verified")
        self.assertEqual(ranked["confidence"], 0.93)
        self.assertEqual(ranked["audience_fit"], "business_user")
        self.assertGreater(ranked["strategy_priority_bonus"], 0)

    def test_product_slot_does_not_treat_speculative_production_words_as_confirmation(self):
        from news.collector import rank_product_slot_articles

        speculative = {
            "title": "HBM4 GPU 양산 일정 전망",
            "raw_excerpt": "업계 관측으로 9월 출하 예상",
            "shorts_score": 99,
        }
        consumer = {
            "title": "소비자용 폴더블 힌지 변경 공식 발표",
            "audience_fit": "consumer",
            "rumor_status": "confirmed",
            "event_type": "product_launch",
            "shorts_score": 50,
        }
        self.assertEqual(rank_product_slot_articles([speculative, consumer])[0], consumer)

    def test_product_slot_strategic_band_requires_affirmative_confirmation(self):
        from news.collector import rank_product_slot_articles

        rumor = {
            "title": "HBM4 mass production starts for GPU shipment",
            "source_tier": "rumor_leak",
            "shorts_score": 99,
        }
        consumer = {
            "title": "소비자용 갤럭시 스마트폰 출시",
            "audience_fit": "consumer",
            "event_type": "product_launch",
            "rumor_status": "confirmed",
            "shorts_score": 80,
        }
        confirmed_hbm = {
            "title": "SK하이닉스 HBM4 양산 시작",
            "raw_excerpt": "GPU 반도체 출하 일정 공식 확정",
            "event_type": "component_tech",
            "rumor_status": "confirmed",
            "source_tier": "news_secondary",
            "shorts_score": 60,
        }

        ordered = rank_product_slot_articles([rumor, consumer, confirmed_hbm])
        self.assertEqual(ordered[0], confirmed_hbm)
        self.assertLess(ordered.index(consumer), ordered.index(rumor))

    def test_advanced_pipeline_hard_excludes_non_it_verticals(self):
        from news.collector import _filter_channel_scope

        articles = [
            {"title": "은행 신용카드 대출 상품", "summary": "금융 혜택"},
            {"title": "RTX 5090 그래픽카드 출시", "summary": "GPU 하드웨어"},
        ]
        self.assertEqual([item["title"] for item in _filter_channel_scope(articles)], [articles[1]["title"]])

    def test_product_slot_orders_consumer_then_prosumer_and_keeps_strategic_exception(self):
        from news.collector import rank_product_slot_articles

        articles = [
            {"title": "산업용 창고 바코드 스캐너 출시", "raw_excerpt": "B2B 물류 기업용 장치", "shorts_score": 99},
            {"title": "전문가용 OLED 모니터 출시", "raw_excerpt": "크리에이터 프로슈머 제품", "shorts_score": 70},
            {"title": "소비자용 갤럭시 스마트폰 출시", "raw_excerpt": "일반 사용자 제품", "shorts_score": 65},
            {"title": "SK하이닉스 HBM4 양산 시작", "raw_excerpt": "GPU 반도체 출하 일정 확정", "shorts_score": 60},
        ]
        ordered = rank_product_slot_articles(articles)
        self.assertEqual(ordered[0]["title"], articles[3]["title"])
        self.assertEqual([item["title"] for item in ordered[1:]], [articles[2]["title"], articles[1]["title"], articles[0]["title"]])

    def test_general_ranking_does_not_inherit_product_slot_audience_order(self):
        from news.collector import rank_product_slot_articles

        articles = [
            {"title": "기업용 키보드 출시", "raw_excerpt": "B2B", "shorts_score": 99},
            {"title": "소비자용 키보드 출시", "raw_excerpt": "일반 사용자", "shorts_score": 50},
        ]
        self.assertEqual(sorted(articles, key=lambda x: x["shorts_score"], reverse=True)[0], articles[0])
        self.assertEqual(rank_product_slot_articles(articles)[0], articles[1])

    def test_product_slot_uses_audience_fit_before_score_and_complete_enterprise_fallback(self):
        from news.collector import rank_product_slot_articles

        for term in ("business", "commercial", "corporate", "business customers", "업무용", "법인", "기업 고객", "사무용"):
            articles = [
                {"title": f"{term} 노트북 출시", "shorts_score": 99},
                {"title": "일반 노트북 출시", "audience_fit": "consumer", "shorts_score": 1},
            ]
            with self.subTest(term=term):
                self.assertEqual(rank_product_slot_articles(articles)[0]["audience_fit"], "consumer")

        articles = [
            {"title": "commercial 디자인 노트북", "audience_fit": "consumer", "shorts_score": 10},
            {"title": "creator 노트북", "audience_fit": "prosumer", "shorts_score": 99},
        ]
        self.assertEqual(rank_product_slot_articles(articles)[0]["audience_fit"], "consumer")

    def test_advanced_general_pipeline_gets_one_capped_strategy_boost(self):
        article = {
            "source": "advanced",
            "title": "Samsung HBM4 mass production starts for Nvidia GPU supply chain",
            "url": "https://example.com/hbm4",
            "summary": "The semiconductor product begins shipment under a concrete supply contract.",
            "score": 70,
        }

        ranked = _advanced_article_to_ranked_dict(article)

        self.assertGreater(ranked["strategy_priority_bonus"], 0)
        self.assertLessEqual(ranked["strategy_priority_bonus"], 12)
        self.assertEqual(ranked["shorts_score"], 70 + ranked["strategy_priority_bonus"])

    def test_advanced_general_pipeline_does_not_boost_generic_story(self):
        ranked = _advanced_article_to_ranked_dict({
            "source": "advanced",
            "title": "Company holds annual strategy meeting",
            "url": "https://example.com/meeting",
            "summary": "Executives discussed broad plans.",
            "score": 70,
        })

        self.assertEqual(ranked["strategy_priority_bonus"], 0)
        self.assertEqual(ranked["shorts_score"], 70)


if __name__ == "__main__":
    unittest.main()
