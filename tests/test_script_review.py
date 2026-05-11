import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) in sys.path:
    sys.path.remove(str(SRC_DIR))
sys.path.insert(0, str(SRC_DIR))


class ScriptReviewTests(unittest.TestCase):
    def test_generate_script_reviews_with_configured_local_ollama_model(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.subject = "새로운 태블릿 발표"
        review_json = (
            '{"approved": false, "score": 82, "issues": ["후킹 약함"], '
            '"revised_script": "새 태블릿 발표에서 가장 중요한 변화는 배터리입니다. '
            '이 변화는 이동 중 사용 시간을 크게 늘릴 수 있습니다. '
            '더 많은 IT 기기 소식은 구독하고 확인해 주세요."}'
        )

        with patch("classes.YouTube.get_script_review_enabled", return_value=True), patch(
            "classes.YouTube.get_script_review_model", return_value="gemma4:e4b"
        ), patch.object(youtube, "_persist_script_review") as persist_review, patch(
            "classes.YouTube.generate_text",
            side_effect=[
                "새 태블릿이 나왔습니다. 배터리가 좋아졌습니다. 구독해주세요.",
                review_json,
            ],
        ) as generate_text:
            script = youtube.generate_script()

        self.assertIn("가장 중요한 변화는 배터리", script)
        self.assertEqual(generate_text.call_count, 2)
        self.assertEqual(generate_text.call_args_list[1].kwargs["model_name"], "gemma4:e4b")
        persist_review.assert_called_once()

    def test_review_keeps_original_when_review_json_is_unparseable(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        original = "새 기기가 공개됐습니다. 핵심은 가격입니다. 구독하고 다음 소식도 확인해 주세요."

        with patch("classes.YouTube.get_script_review_enabled", return_value=True), patch(
            "classes.YouTube.get_script_review_model", return_value="gemma4:e4b"
        ), patch.object(youtube, "generate_response", return_value="JSON이 아닌 응답"), patch.object(
            youtube, "_persist_script_review"
        ):
            final = youtube.review_script_with_local_ollama(original)

        self.assertEqual(final, original)


if __name__ == "__main__":
    unittest.main()
