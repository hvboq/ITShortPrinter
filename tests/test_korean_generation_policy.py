import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class KoreanGenerationPolicyTests(unittest.TestCase):
    def test_news_script_prompt_forces_korean_output_even_when_language_argument_differs(self):
        from news.shorts import build_shorts_script_prompt

        article = {
            "title": "Samsung launches a new AI phone",
            "raw_excerpt": "The device adds on-device AI features.",
            "url": "https://example.com/samsung-ai-phone",
            "brands": ["Samsung"],
            "technologies": ["AI", "smartphone"],
            "event_type": "product_launch",
            "confidence": 0.95,
            "shorts_score": 93,
        }

        prompt = build_shorts_script_prompt(article, language="English")

        self.assertIn("반드시 한국어로만 작성", prompt)
        self.assertNotIn("언어: English", prompt)

    def test_youtube_metadata_prompt_forces_korean_title_and_description(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="English")
        youtube.subject = "Samsung launches a new AI phone"
        youtube.script = "삼성이 온디바이스 AI 기능을 강화한 새 스마트폰을 공개했습니다."
        captured_prompts = []

        def fake_response(prompt):
            captured_prompts.append(prompt)
            return "삼성 AI폰 공개 #IT뉴스" if len(captured_prompts) == 1 else "삼성 AI폰 소식 요약입니다. 구독해 주세요."

        with patch.object(youtube, "generate_response", side_effect=fake_response):
            youtube.generate_metadata()

        self.assertEqual(len(captured_prompts), 2)
        self.assertIn("반드시 한국어로만", captured_prompts[0])
        self.assertIn("반드시 한국어로만", captured_prompts[1])

    def test_youtube_metadata_prompt_preserves_alphanumeric_model_names(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.subject = "삼성 갤럭시 S27 Pro 6.47인치 중형 화면 신설 소식"
        youtube.script = "갤럭시 S27 Pro 소식입니다."
        captured_prompts = []

        def fake_response(prompt):
            captured_prompts.append(prompt)
            return "삼성 갤럭시 에스이십칠 프로 소식 #갤럭시" if len(captured_prompts) == 1 else "설명입니다."

        with patch.object(youtube, "generate_response", side_effect=fake_response):
            metadata = youtube.generate_metadata()

        self.assertIn("공식 모델명은 한글로 풀어 쓰거나 번역하지 말고", captured_prompts[0])
        self.assertEqual(metadata["title"], "삼성 갤럭시 S27 Pro 소식 #갤럭시")

    def test_youtube_image_prompt_request_uses_korean_context_and_forces_korean_json_strings(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="English")
        youtube.subject = "Samsung launches a new AI phone"
        youtube.script = "삼성이 온디바이스 AI 기능을 강화한 새 스마트폰을 공개했습니다."
        captured_prompts = []

        def fake_response(prompt):
            captured_prompts.append(prompt)
            return json.dumps(["한국어 이미지 프롬프트 1", "한국어 이미지 프롬프트 2"], ensure_ascii=False)

        with patch.object(youtube, "generate_response", side_effect=fake_response), patch(
            "classes.YouTube.get_max_image_prompts", return_value=2
        ):
            youtube.generate_prompts()

        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("반드시 한국어로만", captured_prompts[0])
        self.assertIn("JSON 배열 안의 문자열도 한국어", captured_prompts[0])


if __name__ == "__main__":
    unittest.main()
