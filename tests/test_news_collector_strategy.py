import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news.collector import _advanced_article_to_ranked_dict  # noqa: E402


class AdvancedCollectorStrategyTests(unittest.TestCase):
    def test_advanced_general_pipeline_gets_one_capped_strategy_boost(self):
        article = {
            "source": "advanced",
            "title": "Samsung HBM4 mass production starts for Nvidia GPU supply chain",
            "url": "https://example.com/hbm4",
            "summary": "The semiconductor product begins shipment under a concrete supply contract.",
            "score": 70,
        }

        ranked = _advanced_article_to_ranked_dict(article)

        self.assertGreater(ranked["strategy_priority_bonus"], 0)
        self.assertLessEqual(ranked["strategy_priority_bonus"], 12)
        self.assertEqual(ranked["shorts_score"], 70 + ranked["strategy_priority_bonus"])

    def test_advanced_general_pipeline_does_not_boost_generic_story(self):
        ranked = _advanced_article_to_ranked_dict({
            "source": "advanced",
            "title": "Company holds annual strategy meeting",
            "url": "https://example.com/meeting",
            "summary": "Executives discussed broad plans.",
            "score": 70,
        })

        self.assertEqual(ranked["strategy_priority_bonus"], 0)
        self.assertEqual(ranked["shorts_score"], 70)


if __name__ == "__main__":
    unittest.main()
