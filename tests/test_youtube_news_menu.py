import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeNewsMenuTests(unittest.TestCase):
    def test_youtube_menu_starts_with_top_ranked_news_short_option(self):
        from constants import YOUTUBE_OPTIONS

        self.assertEqual(YOUTUBE_OPTIONS[0], "Create Top Ranked News Short")
        self.assertEqual(YOUTUBE_OPTIONS[1], "Upload Short")
        self.assertIn("Show all Shorts", YOUTUBE_OPTIONS)
        self.assertEqual(YOUTUBE_OPTIONS[-1], "Quit")


if __name__ == "__main__":
    unittest.main()
