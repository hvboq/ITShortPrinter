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
            '기존 제품보다 전력 관리가 세밀해져 이동 중 사용 시간이 더 안정적일 수 있습니다. '
            '화면 밝기와 실행 앱에 따라 실제 체감은 달라질 수 있습니다. '
            '그래서 이번 발표는 성능보다 오래 쓰는 경험에 초점을 맞춰 봐야 합니다. '
            '새 기기를 기다렸다면 배터리 개선 폭을 먼저 확인하는 것이 좋습니다."}'
        )
        quality_rewrite = (
            "새 태블릿 발표에서 가장 중요한 변화는 배터리 사용 시간입니다. "
            "기존 제품보다 전력 관리가 세밀해져 이동 중 사용이 안정적일 수 있습니다. "
            "화면 밝기와 실행 앱에 따라 실제 체감 시간은 달라질 수 있습니다. "
            "성능 수치보다 충전 없이 오래 쓰는 경험을 먼저 확인해야 합니다. "
            "출시 뒤 실사용 테스트에서 배터리 개선 폭을 살펴보는 것이 좋습니다."
        )

        with patch("classes.YouTube.get_script_review_enabled", return_value=True), patch(
            "classes.YouTube.get_script_review_model", return_value="gemma4:e4b"
        ), patch.object(youtube, "_persist_script_review") as persist_review, patch(
            "classes.YouTube.generate_text",
            side_effect=[
                "새 태블릿이 나왔습니다. 배터리가 좋아졌습니다. 구독해주세요.",
                quality_rewrite,
                review_json,
            ],
        ) as generate_text:
            script = youtube.generate_script()

        self.assertIn("가장 중요한 변화는 배터리", script)
        self.assertEqual(generate_text.call_count, 3)
        self.assertEqual(generate_text.call_args_list[2].kwargs["model_name"], "gemma4:e4b")
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
