import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class NewsShortsPromptTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
