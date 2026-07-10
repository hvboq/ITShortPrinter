import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeLlmDefaultsTests(unittest.TestCase):
    def test_generate_response_uses_default_text_model_when_no_model_passed(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        with patch("classes.YouTube.get_default_text_model", return_value="gemma4:e4b"), patch(
            "classes.YouTube.generate_text", return_value="ok"
        ) as generate_text:
            response = youtube.generate_response("hello")

        self.assertEqual(response, "ok")
        generate_text.assert_called_once_with("hello", model_name="gemma4:e4b")

    def test_generate_response_uses_explicit_model_when_passed(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        with patch("classes.YouTube.generate_text", return_value="ok") as generate_text:
            response = youtube.generate_response("hello", model_name="hermes:gpt-5.6-sol")

        self.assertEqual(response, "ok")
        generate_text.assert_called_once_with("hello", model_name="hermes:gpt-5.6-sol")


if __name__ == "__main__":
    unittest.main()
