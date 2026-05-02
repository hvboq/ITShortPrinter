import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class NewsShortsPromptTests(unittest.TestCase):
    def test_prompt_enforces_news_briefing_subscribe_only_and_no_save(self):
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
        self.assertIn("구독", prompt)
        self.assertIn("시리즈화 금지", prompt)
        self.assertIn("https://example.com/snapdragon", prompt)
        self.assertIn("Qualcomm launches Snapdragon 8 Elite", prompt)


if __name__ == "__main__":
    unittest.main()
