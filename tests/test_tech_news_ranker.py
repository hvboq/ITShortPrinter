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

    def test_product_launch_gets_extra_priority_bonus(self):
        from news.ranker import score_article

        launch = score_article(
            {
                "title": "Logitech launches new mechanical keyboard for PC users",
                "source_tier": "news_secondary",
                "raw_excerpt": "The new keyboard is officially unveiled with a lower-latency wireless receiver.",
            }
        )
        component = score_article(
            {
                "title": "Logitech keyboard uses lower-latency wireless receiver",
                "source_tier": "news_secondary",
                "raw_excerpt": "The keyboard technology improves wireless latency for PC users.",
            }
        )

        self.assertEqual(launch["event_type"], "product_launch")
        self.assertGreater(launch["launch_priority_bonus"], 0)
        self.assertEqual(component["launch_priority_bonus"], 0)
        self.assertGreaterEqual(launch["shorts_score"], component["shorts_score"])

    def test_software_and_deals_do_not_get_full_product_launch_bonus(self):
        from news.ranker import score_article

        software = score_article(
            {
                "title": "Apple releases iOS update for iPhone users",
                "source_tier": "news_secondary",
                "raw_excerpt": "The iOS app update adds new wallpapers and Messages features.",
            }
        )
        deal = score_article(
            {
                "title": "Galaxy phone price cut and sale starts today",
                "source_tier": "news_secondary",
                "raw_excerpt": "Retailers list a new discount and availability for the smartphone.",
            }
        )

        self.assertEqual(software["event_type"], "software_update")
        self.assertEqual(software["launch_priority_bonus"], 0)
        self.assertGreater(software["scope_drift_penalty"], 0)
        self.assertEqual(deal["event_type"], "price_availability")
        self.assertLess(deal["launch_priority_bonus"], 12)

    def test_channel_performance_signals_boost_rankings_and_phone_comparisons(self):
        from news.ranker import score_article

        comparison = score_article(
            {
                "title": "18주차 스마트폰 랭킹 TOP 10: 갤럭시와 아이폰 비교",
                "source_tier": "news_secondary",
                "raw_excerpt": "이번 주 가장 주목받는 foldable phone ranking and comparison.",
            }
        )
        generic = score_article(
            {
                "title": "New smartphone accessory market context",
                "source_tier": "news_secondary",
                "raw_excerpt": "A general update about smartphone accessories without a ranking or comparison hook.",
            }
        )

        self.assertGreaterEqual(comparison["performance_signal_bonus"], 10)
        self.assertGreater(comparison["shorts_score"], generic["shorts_score"])

    def test_learned_performance_weights_prioritize_pc_chip_bucket(self):
        from news.ranker import learned_performance_weight_bonus

        self.assertGreater(
            learned_performance_weight_bonus("pc_chip_device", "consumer", {"angle_type": "market_competition"}),
            learned_performance_weight_bonus("smartphone_foldable", "consumer", {"angle_type": "launch_impact"}),
        )

    def test_channel_analytics_boost_semiconductor_supply_chain_news(self):
        from news.ranker import score_article

        supply_chain = score_article(
            {
                "title": "한미반도체, SK하이닉스에 442억원 규모 HBM4용 TC본더 공급 계약",
                "source_tier": "news_secondary",
                "raw_excerpt": "반도체 후공정 장비 공급망과 HBM 패키징 경쟁이 커지고 있다.",
            }
        )
        broad_ai = score_article(
            {
                "title": "AI 비서 대화 기록, 자동 삭제가 정답일까?",
                "source_tier": "news_secondary",
                "raw_excerpt": "일반적인 AI 서비스 개인정보 이슈를 설명한다.",
            }
        )

        self.assertIn("SK Hynix", supply_chain["brands"])
        self.assertIn("Hanmi Semiconductor", supply_chain["brands"])
        self.assertIn("chipset", supply_chain["technologies"])
        self.assertEqual(supply_chain["topic_bucket"], "pc_chip_device")
        self.assertGreaterEqual(supply_chain["performance_signal_bonus"], 13)
        self.assertGreater(supply_chain["shorts_score"], broad_ai["shorts_score"])

    def test_low_retention_advice_titles_are_penalized(self):
        from news.ranker import score_article

        advice = score_article(
            {
                "title": "스마트폰 가격, 더 오르기 전에 사야 할까?",
                "source_tier": "news_secondary",
                "raw_excerpt": "구매 시점을 고민하는 일반 상담형 뉴스다.",
            }
        )
        delay_advice = score_article(
            {
                "title": "갤럭시 S26 지연설, 지금 폰 사도 될까?",
                "source_tier": "news_secondary",
                "raw_excerpt": "출시 지연 가능성을 바탕으로 구매 시점을 묻는 상담형 뉴스다.",
            }
        )
        concrete = score_article(
            {
                "title": "BOE, 삼성보다 낮은 가격에 갤럭시 S27 OLED 공급 제안",
                "source_tier": "news_secondary",
                "raw_excerpt": "디스플레이 공급망과 가격 경쟁이 스마트폰 시장을 바꾸고 있다.",
            }
        )

        self.assertGreater(advice["low_retention_format_penalty"], 0)
        self.assertGreater(delay_advice["low_retention_format_penalty"], 0)
        self.assertEqual(concrete["low_retention_format_penalty"], 0)
        self.assertGreater(concrete["shorts_score"], advice["shorts_score"])
        self.assertGreater(concrete["shorts_score"], delay_advice["shorts_score"])

    def test_channel_performance_penalizes_broad_update_and_event_opening_titles(self):
        from news.ranker import score_article

        event_opening = score_article(
            {
                "title": "컴퓨텍스 이천이십육 개막, 함께하는 인공지능 시대를 말하다",
                "source_tier": "news_secondary",
                "raw_excerpt": "행사 개막과 일반적인 AI 흐름을 넓게 소개한다.",
            }
        )
        concrete_gpu = score_article(
            {
                "title": "정부, 엔비디아 GPU 9704장 확보 이달 구매 발주",
                "source_tier": "news_secondary",
                "raw_excerpt": "구체적인 GPU 수량과 구매 발주가 AI 인프라 공급에 영향을 준다.",
            }
        )

        self.assertGreater(event_opening["low_retention_format_penalty"], 0)
        self.assertEqual(concrete_gpu["low_retention_format_penalty"], 0)
        self.assertGreater(concrete_gpu["shorts_score"], event_opening["shorts_score"])

    def test_latest_performance_weights_keep_pc_chip_ahead_of_general_ai(self):
        from news.ranker import learned_performance_weight_bonus

        self.assertGreater(
            learned_performance_weight_bonus("pc_chip_device", "consumer", {"angle_type": "market_competition"}),
            learned_performance_weight_bonus("ai_service_model", "consumer", {"angle_type": "consumer_ai_model_shift"}),
        )

    def test_ai_development_scope_drift_is_penalized_against_hardware_story(self):
        from news.ranker import score_article

        software = score_article(
            {
                "title": "OpenAI launches new developer software tools",
                "source_tier": "news_secondary",
                "raw_excerpt": "Programming and coding workflow updates for developers.",
            }
        )
        hardware = score_article(
            {
                "title": "Samsung launches new foldable smartphone",
                "source_tier": "news_secondary",
                "raw_excerpt": "A consumer hardware launch with display and battery improvements.",
            }
        )

        self.assertGreater(software["scope_drift_penalty"], 0)
        self.assertFalse(software["alert_allowed"])
        self.assertGreater(hardware["shorts_score"], software["shorts_score"])

    def test_ai_service_model_launches_are_allowed_not_penalized(self):
        from news.ranker import score_article

        claude = score_article(
            {
                "title": "Anthropic launches Claude 4.5 with faster coding and safer AI service features",
                "source_tier": "news_secondary",
                "raw_excerpt": "The new Claude model is available in the consumer AI service and business solution plans.",
            }
        )
        gemini = score_article(
            {
                "title": "Google Gemini 신규 모델 공개, 이미지와 검색 기능 강화",
                "source_tier": "news_secondary",
                "raw_excerpt": "제미나이 AI 서비스 솔루션에 새 모델이 추가됐다.",
            }
        )

        self.assertEqual(claude["scope_drift_penalty"], 0)
        self.assertGreater(claude["ai_service_solution_bonus"], 0)
        self.assertIn("Anthropic", claude["brands"])
        self.assertEqual(gemini["scope_drift_penalty"], 0)
        self.assertGreater(gemini["ai_service_solution_bonus"], 0)
        self.assertIn("Google", gemini["brands"])

    def test_avoided_ai_engineering_topics_get_strong_penalty(self):
        from news.ranker import score_article

        harness = score_article(
            {
                "title": "하네스 엔지니어링으로 AI 개발 생산성 높이는 방법",
                "source_tier": "tech_secondary",
                "raw_excerpt": "Developer workflow and benchmark harness engineering for coding teams.",
            }
        )
        turboquant = score_article(
            {
                "title": "TurboQuant framework released for LLM compression",
                "source_tier": "tech_secondary",
                "raw_excerpt": "터보퀀트는 모델 개발자를 위한 quantization engineering toolkit이다.",
            }
        )

        self.assertGreaterEqual(harness["scope_drift_penalty"], 30)
        self.assertGreaterEqual(turboquant["scope_drift_penalty"], 30)

    def test_audience_fit_strategic_importance_and_angle_are_auditable(self):
        from news.ranker import score_article

        hardware = score_article(
            {
                "title": "Samsung launches affordable foldable Galaxy phone to challenge iPhone",
                "source_tier": "news_secondary",
                "raw_excerpt": "The new mainstream foldable smartphone changes the price competition.",
            }
        )
        ai_service = score_article(
            {
                "title": "GPT 신규 모델 출시, ChatGPT 음성 검색 기능 강화",
                "source_tier": "news_secondary",
                "raw_excerpt": "일반 사용자가 앱에서 바로 쓸 수 있는 AI 서비스 업데이트다.",
            }
        )
        developer = score_article(
            {
                "title": "OpenAI SDK framework benchmark update for developers",
                "source_tier": "tech_secondary",
                "raw_excerpt": "API framework and coding workflow improvements for developer teams.",
            }
        )

        self.assertEqual(hardware["audience_fit"], "consumer")
        self.assertGreaterEqual(hardware["strategic_importance_score"], 8)
        self.assertIn(hardware["shorts_angle"]["angle_type"], {"launch_impact", "market_competition", "price_value_shift"})
        self.assertEqual(ai_service["audience_fit"], "consumer")
        self.assertEqual(ai_service["topic_bucket"], "ai_service_model")
        self.assertEqual(ai_service["shorts_angle"]["angle_type"], "consumer_ai_model_shift")
        self.assertEqual(developer["audience_fit"], "developer")
        self.assertLess(developer["audience_fit_score"], 0)

    def test_portfolio_selection_diversifies_top5_buckets(self):
        from news.ranker import rank_articles, select_portfolio_articles

        articles = [
            {"title": "iPhone Galaxy 스마트폰 랭킹 TOP 10 비교", "source_tier": "news_secondary", "raw_excerpt": "foldable phone comparison"},
            {"title": "Anthropic launches Claude 신규 모델 공개", "source_tier": "news_secondary", "raw_excerpt": "consumer AI service model launch"},
            {"title": "NVIDIA launches new RTX GPU for gaming PCs", "source_tier": "news_secondary", "raw_excerpt": "graphics card product launch"},
            {"title": "Logitech launches new mechanical keyboard", "source_tier": "news_secondary", "raw_excerpt": "wireless keyboard for PC users"},
            {"title": "Samsung launches new Galaxy smartphone", "source_tier": "news_secondary", "raw_excerpt": "consumer phone launch"},
            {"title": "Apple launches affordable iPad", "source_tier": "news_secondary", "raw_excerpt": "mainstream tablet launch"},
        ]

        selected = select_portfolio_articles(rank_articles(articles), count=5)
        buckets = [item["topic_bucket"] for item in selected]

        self.assertEqual(len(selected), 5)
        self.assertIn("ai_service_model", buckets)
        self.assertIn("pc_chip_device", buckets)
        self.assertIn("peripheral_wearable_audio", buckets)
        self.assertGreaterEqual(len(set(buckets)), 4)

    def test_shorts_prompt_includes_angle_and_viewer_payoff(self):
        from news.ranker import score_article
        from news.shorts import build_shorts_script_prompt

        article = score_article(
            {
                "title": "Google Gemini 신규 모델 공개, 이미지 생성 기능 강화",
                "source_tier": "news_secondary",
                "raw_excerpt": "일반 사용자가 AI 서비스에서 바로 쓸 수 있는 새 모델이다.",
            }
        )
        prompt = build_shorts_script_prompt(article)

        self.assertIn("Angle Type:", prompt)
        self.assertIn("Viewer Payoff:", prompt)
        self.assertIn("첫 3초 훅", prompt)
        self.assertIn("왜 중요", prompt)


if __name__ == "__main__":
    unittest.main()
