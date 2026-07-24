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
    def test_generated_korean_text_cleaner_removes_markdown_list_markers(self):
        from classes.youtube_content import clean_generated_korean_text

        raw = (
            "1. \uccab \ubb38\uc7a5\uc785\ub2c8\ub2e4.\n"
            "- \ub450 \ubc88\uc9f8 \ubb38\uc7a5\uc785\ub2c8\ub2e4.\n"
            "NARRATOR: \uc138 \ubc88\uc9f8 \ubb38\uc7a5\uc785\ub2c8\ub2e4."
        )

        cleaned = clean_generated_korean_text(raw)

        self.assertEqual(
            cleaned,
            "\uccab \ubb38\uc7a5\uc785\ub2c8\ub2e4. "
            "\ub450 \ubc88\uc9f8 \ubb38\uc7a5\uc785\ub2c8\ub2e4. "
            "\uc138 \ubc88\uc9f8 \ubb38\uc7a5\uc785\ub2c8\ub2e4.",
        )
        self.assertNotIn("1.", cleaned)
        self.assertNotIn("-", cleaned)
        self.assertNotIn("NARRATOR", cleaned)

    def test_script_quality_warnings_flag_short_or_single_sentence_scripts(self):
        from classes.youtube_content import script_quality_warnings

        warnings = script_quality_warnings("짧은 대본입니다.")

        self.assertIn("structure_script_too_short", warnings)
        self.assertIn("structure_script_sentence_count_low", warnings)

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
        self.assertIn("30~45초", prompt)
        self.assertIn("260~380자", prompt)
        self.assertIn("모바일 자막", prompt)
        self.assertNotIn("45~60초", prompt)

    def test_general_youtube_script_prompt_targets_readable_shorts_pacing(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="English")
        youtube.subject = "A new AI laptop battery feature"
        captured_prompts = []

        def fake_response(prompt):
            captured_prompts.append(prompt)
            return (
                "새 AI 노트북 기능은 배터리 사용 방식을 바꾸는 소식입니다. "
                "핵심은 이동 중 작업 시간이 더 예측 가능해진다는 점입니다. "
                "기존처럼 충전기를 계속 의식하지 않아도 되는 상황이 늘어날 수 있습니다. "
                "다만 실제 효과는 기기 설정과 사용 환경에 따라 달라집니다. "
                "그래서 이번 변화는 성능보다 사용 시간의 안정성을 봐야 합니다."
            )

        with patch.object(youtube, "generate_response", side_effect=fake_response), patch(
            "classes.YouTube.get_script_review_enabled", return_value=False
        ), patch("classes.YouTube.get_script_sentence_length", return_value=6):
            youtube.generate_script()

        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("30~45초", captured_prompts[0])
        self.assertIn("260~380자", captured_prompts[0])
        self.assertIn("모바일 자막", captured_prompts[0])
        self.assertIn("6문장 이내", captured_prompts[0])

    def test_generate_script_rewrites_short_scripts_before_tts(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.subject = "A new AI laptop battery feature"
        captured_prompts = []

        def fake_response(prompt):
            captured_prompts.append(prompt)
            if len(captured_prompts) == 1:
                return "짧은 소식입니다."
            return (
                "새 AI 노트북 기능은 배터리 사용 시간을 더 예측 가능하게 만드는 소식입니다. "
                "핵심은 고성능 작업 중에도 전력 소모를 더 세밀하게 조절한다는 점입니다. "
                "사용자는 충전기를 찾는 횟수가 줄어드는 변화를 기대할 수 있습니다. "
                "다만 실제 효과는 화면 밝기와 실행 앱에 따라 달라질 수 있습니다. "
                "그래서 이번 변화는 단순 성능보다 이동 중 사용 안정성에 의미가 있습니다."
            )

        with patch.object(youtube, "generate_response", side_effect=fake_response), patch(
            "classes.YouTube.get_script_review_enabled", return_value=False
        ), patch("classes.YouTube.get_script_sentence_length", return_value=6):
            script = youtube.generate_script()

        self.assertEqual(len(captured_prompts), 2)
        self.assertIn("260~380", captured_prompts[1])
        self.assertNotEqual(script, "짧은 소식입니다.")
        self.assertGreater(len(script), 120)

    def test_generate_script_reviews_the_quality_rewrite(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.subject = "새로운 노트북 배터리 기능"
        revised = " ".join(
            [
                "새 노트북 기능이 이동 중 배터리 사용 시간을 안정적으로 늘립니다.",
                "백그라운드 작업의 전력 소비를 상황에 맞게 조절하는 방식입니다.",
                "사용자는 충전기를 찾는 횟수를 줄이는 변화를 기대할 수 있습니다.",
                "실제 효과는 화면 밝기와 실행 중인 앱에 따라 달라질 수 있습니다.",
                "출시 뒤 실사용 테스트에서 지속 시간과 성능을 함께 확인해야 합니다.",
            ]
        )

        with patch.object(
            youtube,
            "generate_response",
            side_effect=["짧은 소식입니다.", revised],
        ), patch.object(
            youtube,
            "review_script_with_local_ollama",
            side_effect=lambda script: script,
        ) as review, patch("classes.YouTube.get_script_sentence_length", return_value=6):
            script = youtube.generate_script()

        review.assert_called_once_with(revised)
        self.assertEqual(script, revised)

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
        self.assertIn("68자 이하", captured_prompts[0])

    def test_metadata_title_is_short_enough_for_overlay(self):
        from classes.youtube_content import METADATA_TITLE_MAX_CHARS
        from classes.youtube_content import clean_metadata_title

        title = clean_metadata_title(
            "제목: 화웨이가 새로운 폴더블 기기를 공개했습니다. "
            "이 제품은 대용량 배터리와 넓은 화면으로 주목받고 있습니다. "
            "최신 IT 소식을 계속 보고 싶다면 채널을 구독해 주세요."
        )

        self.assertLessEqual(len(title), METADATA_TITLE_MAX_CHARS)
        self.assertTrue(title.endswith("..."))
        self.assertNotIn("제목:", title)

    def test_safe_video_filename_uses_short_title_stem(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.metadata = {
            "title": (
                "화웨이가 새로운 폴더블 기기를 공개했습니다. "
                "이 제품은 대용량 배터리와 넓은 화면으로 주목받고 있습니다."
            )
        }

        filename = youtube._safe_video_filename()
        stem = filename.removesuffix(".mp4")

        self.assertTrue(filename.endswith(".mp4"))
        self.assertLessEqual(len(stem), 56)
        self.assertNotRegex(filename, r'[<>:"/\\|?*]')

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
        self.assertIn("첫 3초 훅", captured_prompts[0])
        self.assertIn("사용자가 체감할 변화", captured_prompts[0])


if __name__ == "__main__":
    unittest.main()
