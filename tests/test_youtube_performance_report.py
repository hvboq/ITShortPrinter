import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubePerformanceReportTests(unittest.TestCase):
    def test_ai_semiconductor_stories_are_in_scope_for_it_han_haru(self):
        from youtube_api.performance import classify_topic

        topic = classify_topic("과기정통부 2조 GPU 사업자에 삼성·네이버·엘리스 선정 #GPU #AI")

        self.assertIn("chip/pc/semiconductor", topic["topic_categories"])
        self.assertIn("ai/software", topic["topic_categories"])
        self.assertTrue(topic["fits_current_channel_scope"])

    def test_developer_only_ai_story_still_warns_as_scope_risk(self):
        from youtube_api.performance import classify_topic

        topic = classify_topic("OpenAI SDK framework benchmark update for developers")

        self.assertIn("ai/software", topic["topic_categories"])
        self.assertFalse(topic["fits_current_channel_scope"])


if __name__ == "__main__":
    unittest.main()
