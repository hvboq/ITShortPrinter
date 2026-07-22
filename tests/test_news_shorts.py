import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class NewsShortsPromptTests(unittest.TestCase):
    def test_consumer_comparison_precedes_generic_production_and_shipment_words(self):
        from news.shorts import choice_question_forbidden, choice_question_policy

        consumer_articles = (
            {
                "title": "아이폰과 갤럭시 가격 비교",
                "raw_excerpt": "소비자용 스마트폰은 9월 출하 예정",
                "audience_fit": "consumer",
            },
            {
                "title": "소비자 노트북 가격 비교",
                "raw_excerpt": "새 모델 생산 시작 뒤 어떤 제품을 선택할지 비교",
                "audience_fit": "consumer",
            },
        )
        for article in consumer_articles:
            with self.subTest(title=article["title"]):
                self.assertFalse(choice_question_forbidden(article))
                self.assertIn("선택 질문을 포함", choice_question_policy(article))

        for article in (
            {"title": "HBM 공급망 출하", "audience_fit": "business_user"},
            {"title": "enterprise HBM production comparison", "audience_fit": "consumer"},
        ):
            with self.subTest(title=article["title"]):
                self.assertTrue(choice_question_forbidden(article))
                self.assertIn("절대 만들지", choice_question_policy(article))

    def test_choice_question_policy_is_article_specific(self):
        from news.shorts import build_shorts_script_prompt

        consumer = build_shorts_script_prompt({"title": "아이폰과 갤럭시 가격 비교", "raw_excerpt": "소비자 선택 논쟁", "audience_fit": "consumer"})
        industrial = build_shorts_script_prompt({"title": "HBM 공급망 출하", "raw_excerpt": "B2B 산업 생산", "audience_fit": "business_user"})
        self.assertIn("선택 질문을 포함", consumer)
        self.assertIn("선택 질문을 절대 만들지", industrial)

    def test_review_prompt_preserves_article_specific_choice_question_ban(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation()
        youtube.news_article = {"title": "HBM 공급망 출하", "raw_excerpt": "B2B 산업 생산", "audience_fit": "business_user"}
        prompts = []
        with patch.object(youtube, "generate_response", side_effect=lambda prompt, model_name=None: prompts.append(prompt) or '{"approved": true, "score": 90, "issues": [], "revised_script": "확정 출하 소식입니다."}'), patch("classes.YouTube.get_script_review_enabled", return_value=True), patch.object(youtube, "_persist_script_review"):
            youtube.review_script_with_local_ollama("확정 출하 소식입니다.")
        self.assertIn("선택 질문을 절대 만들지", prompts[0])
    def test_prompt_enforces_engagement_flow_and_channel_value_cta(self):
        from news.shorts import build_shorts_script_prompt

        article = {
            "title": "Qualcomm launches Snapdragon 8 Elite for flagship phones",
            "raw_excerpt": "New NPU improves on-device AI performance and power efficiency.",
            "url": "https://example.com/snapdragon",
            "brands": ["Qualcomm"],
            "technologies": ["chipset"],
            "event_type": "product_launch",
            "confidence": 0.95,
            "shorts_score": 91,
        }

        prompt = build_shorts_script_prompt(article, language="Korean")

        self.assertIn("최신 IT 뉴스 브리핑", prompt)
        self.assertIn("저장 유도 금지", prompt)
        self.assertIn("사실 → 의미 → 시청자 선택", prompt)
        self.assertIn("소비자 선택이나 논쟁", prompt)
        self.assertIn("B2B", prompt)
        self.assertIn("채널 가치", prompt)
        self.assertIn("질문과 CTA를 한 문장에 합치지", prompt)
        self.assertIn("시리즈화 금지", prompt)
        self.assertIn("https://example.com/snapdragon", prompt)
        self.assertIn("Qualcomm launches Snapdragon 8 Elite", prompt)

    def test_prompt_qualifies_rumors_and_exposes_ranking_confidence(self):
        from news.shorts import build_shorts_script_prompt

        prompt = build_shorts_script_prompt({
            "title": "아이폰 부품 가격 유출",
            "raw_excerpt": "확인되지 않은 공급망 주장",
            "event_type": "rumor_leak",
            "rumor_status": "rumor",
            "confidence": 0.35,
        })

        self.assertIn("Rumor Status: rumor", prompt)
        self.assertIn("확인된 사실과 주장", prompt)
        self.assertIn("신뢰도", prompt)

    def test_b2b_choice_policy_covers_complete_business_vocabulary(self):
        from news.shorts import choice_question_policy

        for term in ("business", "commercial", "corporate", "business customers", "업무용", "법인", "기업 고객", "사무용"):
            with self.subTest(term=term):
                self.assertIn("절대 만들지", choice_question_policy({"title": f"새 제품 {term} 출시"}))

    def test_forbidden_choice_postprocessor_removes_forced_choice_but_keeps_information_hook(self):
        from news.shorts import remove_forbidden_choice_questions

        article = {"title": "법인 업무용 GPU 출시", "audience_fit": "business_user"}
        script = "왜 중요할까요? 생산성이 크게 오르기 때문입니다. 여러분은 어느 쪽을 고르시겠어요? 댓글로 선택해 주세요."
        cleaned = remove_forbidden_choice_questions(script, article)
        self.assertIn("왜 중요할까요?", cleaned)
        self.assertIn("생산성이 크게 오르기 때문입니다.", cleaned)
        self.assertNotIn("여러분은", cleaned)
        self.assertNotIn("댓글로", cleaned)

    def test_forbidden_choice_postprocessor_removes_common_product_and_comment_phrasing(self):
        from news.shorts import remove_forbidden_choice_questions

        article = {"title": "기업용 GPU", "audience_fit": "business_user"}
        script = "왜 중요할까요? 확정입니다. 어느 제품이 더 좋을까요? 댓글에 남겨 주세요. 둘 중 어떤 모델을 고르시겠어요?"
        cleaned = remove_forbidden_choice_questions(script, article)
        self.assertEqual(cleaned, "왜 중요할까요? 확정입니다.")

    def test_review_postprocessor_covers_noncompliant_revision_and_malformed_fallback(self):
        from classes.YouTube import YouTube

        article = {"title": "commercial GPU 출하", "audience_fit": "business_user"}
        original = "왜 중요할까요? 공급 일정이 확정됐습니다. 무엇을 선택하시겠어요?"
        youtube = YouTube.for_local_generation()
        youtube.news_article = article
        responses = [
            '{"approved": true, "score": 99, "issues": [], "revised_script": "출하가 확정됐습니다. 여러분은 어느 쪽을 고르시겠어요?"}',
            "not-json",
        ]
        with patch("classes.YouTube.get_script_review_enabled", return_value=True), patch.object(
            youtube, "_persist_script_review"
        ), patch.object(youtube, "generate_response", side_effect=responses):
            revised = youtube.review_script_with_local_ollama(original)
            fallback = youtube.review_script_with_local_ollama(original)
        self.assertEqual(revised, "출하가 확정됐습니다.")
        self.assertIn("왜 중요할까요?", fallback)
        self.assertNotIn("무엇을 선택", fallback)


if __name__ == "__main__":
    unittest.main()
