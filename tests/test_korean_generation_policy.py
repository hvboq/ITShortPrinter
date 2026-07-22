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
    def test_hashtag_evidence_must_exist_within_one_source_field(self):
        from classes.youtube_content import clean_metadata_title

        split = clean_metadata_title("소식 #GalaxyS27", source_text=["Galaxy", "S27 출시"])
        joined = clean_metadata_title("소식 #GalaxyS27", source_text=("Galaxy S27 출시",))
        self.assertNotIn("#GalaxyS27", split)
        self.assertIn("#GalaxyS27", joined)

    def test_unicode_digit_hashtag_fails_closed_without_exact_source_evidence(self):
        from classes.youtube_content import clean_metadata_title

        self.assertNotIn("#모델١", clean_metadata_title("소식 #모델١", source_text="모델 공개"))
        self.assertIn("#모델١", clean_metadata_title("소식 #모델١", source_text="모델١ 공개"))

    def test_generate_metadata_empty_article_never_uses_subject_in_prompt_or_evidence(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation()
        youtube.news_article = {}
        youtube.subject = "Galaxy S27"
        youtube.script = "일반 기술 소식입니다."
        prompts = []

        with patch.object(youtube, "generate_response", side_effect=lambda prompt: prompts.append(prompt) or ("기술 소식 #GalaxyS27" if len(prompts) == 1 else "설명")):
            metadata = youtube.generate_metadata()

        self.assertNotIn("Galaxy S27", prompts[0])
        self.assertNotIn("#GalaxyS27", metadata["title"])

    def test_metadata_removes_common_unsupported_mixed_model_generation_hashtags(self):
        from classes.youtube_content import clean_metadata_title

        model_tags = [
            "#ZFold8", "#Fold8Ultra", "#갤럭시S27", "#GalaxyS27",
            "#A37", "#Ryzen9000", "#CoreUltra400", "#Snapdragon8",
        ]
        for tag in model_tags:
            with self.subTest(tag=tag):
                cleaned = clean_metadata_title(f"신제품 소식 {tag} #스마트폰 #IT뉴스", source_text="새로운 IT 제품 소식")
                self.assertNotIn(tag, cleaned)
                self.assertIn("#스마트폰", cleaned)
                self.assertIn("#IT뉴스", cleaned)

    def test_metadata_preserves_supported_compact_hashtag_for_spaced_source_model(self):
        from classes.youtube_content import clean_metadata_title

        supported = [
            ("#ZFold8", "Samsung Galaxy Z Fold 8 smartphone"),
            ("#Fold8Ultra", "Galaxy Fold 8 Ultra 공개"),
            ("#갤럭시S27", "갤럭시 S27 출시"),
            ("#GalaxyS27", "Galaxy S27 launch"),
            ("#A37", "Galaxy A37 5G"),
            ("#Ryzen9000", "AMD Ryzen 9000 processor"),
            ("#CoreUltra400", "Intel Core Ultra 400 CPU"),
            ("#Snapdragon8", "Qualcomm Snapdragon 8 chipset"),
        ]
        for tag, source in supported:
            with self.subTest(tag=tag):
                self.assertIn(tag, clean_metadata_title(f"신제품 소식 {tag}", source_text=source))

    def test_metadata_removes_unsupported_generated_model_hashtags(self):
        from classes.youtube_content import clean_metadata_title

        generated = "폴더블 경쟁 본격화 #S27 #아이폰18 #RTX5090 #스마트폰 #IT뉴스"
        source = "RTX 5090 그래픽카드와 폴더블 스마트폰 경쟁"
        cleaned = clean_metadata_title(generated, source_text=source)
        self.assertNotIn("#S27", cleaned)
        self.assertNotIn("#아이폰18", cleaned)
        self.assertIn("#RTX5090", cleaned)
        self.assertIn("#스마트폰", cleaned)

    def test_metadata_prompt_forbids_model_and_generation_hashtag_inventions(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation()
        youtube.subject = "폴더블 스마트폰 힌지 변경"
        youtube.script = "힌지 구조가 바뀝니다."
        prompts = []
        with patch.object(youtube, "generate_response", side_effect=lambda prompt: prompts.append(prompt) or ("폴더블 변화 #S27 #IT뉴스" if len(prompts) == 1 else "설명")):
            metadata = youtube.generate_metadata()
        self.assertIn("원문 제목이나 요약에 없는", prompts[0])
        self.assertNotIn("#S27", metadata["title"])
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

    def test_digit_bearing_hashtags_are_grounded_generically_with_exact_separator_tolerant_matches(self):
        from classes.youtube_content import clean_metadata_title

        unsupported = "소식 #iPhone18 #GalaxyZFold8 #Pixel10 #DDR6 #WiFi8 #IT뉴스"
        cleaned = clean_metadata_title(unsupported, source_text="현재 스마트폰과 메모리 무선 기술 소식")
        for tag in ("#iPhone18", "#GalaxyZFold8", "#Pixel10", "#DDR6", "#WiFi8"):
            self.assertNotIn(tag, cleaned)
        self.assertIn("#IT뉴스", cleaned)

        supported = [
            ("#iPhone18", "Apple iPhone 18 공개"),
            ("#GalaxyZFold8", "Galaxy Z Fold 8 공개"),
            ("#Pixel10", "Google Pixel-10 출시"),
            ("#DDR6", "DDR 6 메모리 표준"),
            ("#WiFi8", "Wi-Fi 8 공유기"),
        ]
        for tag, source in supported:
            with self.subTest(tag=tag):
                self.assertIn(tag, clean_metadata_title(f"기술 소식 {tag}", source_text=source))

    def test_digit_hashtag_grounding_rejects_prefix_collision(self):
        from classes.youtube_content import clean_metadata_title

        self.assertNotIn("#A3", clean_metadata_title("신제품 #A3", source_text="Galaxy A37 5G"))

    def test_punctuated_digit_hashtags_require_exact_source_evidence(self):
        from classes.youtube_content import clean_metadata_title

        generated = "신제품 #Galaxy-S27 #iPhone.18 #스마트폰"
        unsupported = clean_metadata_title(generated, source_text="새 스마트폰 소식")
        self.assertNotIn("#Galaxy-S27", unsupported)
        self.assertNotIn("#iPhone.18", unsupported)
        self.assertIn("#스마트폰", unsupported)

        supported = clean_metadata_title(
            generated,
            source_text="Galaxy S27 and iPhone-18 launch",
        )
        self.assertIn("#Galaxy-S27", supported)
        self.assertIn("#iPhone.18", supported)

    def test_empty_article_object_does_not_use_subject_as_hashtag_evidence(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation()
        youtube.news_article = {}
        youtube.subject = "Galaxy S27"

        cleaned = youtube._clean_metadata_title("소식 #Galaxy-S27 #IT뉴스")
        self.assertNotIn("#Galaxy-S27", cleaned)
        self.assertIn("#IT뉴스", cleaned)

    def test_article_metadata_never_uses_subject_as_hashtag_evidence(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation()
        youtube.news_article = {"title": "새 폴더블폰 소식", "raw_excerpt": "힌지가 변경됐다."}
        youtube.subject = "iPhone 18"
        youtube.script = "새 폴더블폰의 힌지가 변경됐습니다."
        with patch.object(youtube, "generate_response", side_effect=["폴더블 변화 #iPhone18 #IT뉴스", "설명"]):
            metadata = youtube.generate_metadata()
        self.assertNotIn("#iPhone18", metadata["title"])
        self.assertIn("#IT뉴스", metadata["title"])


if __name__ == "__main__":
    unittest.main()
