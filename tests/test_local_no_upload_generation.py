import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class LocalNoUploadGenerationTests(unittest.TestCase):
    def test_youtube_local_generation_factory_does_not_start_browser(self):
        from classes.YouTube import YouTube

        with patch("classes.YouTube.webdriver.Firefox") as firefox:
            youtube = YouTube.for_local_generation(niche="IT News", language="Korean")

        firefox.assert_not_called()
        self.assertEqual(youtube.niche, "IT News")
        self.assertEqual(youtube.language, "Korean")
        self.assertEqual(youtube.images, [])
        self.assertIsNone(youtube.news_article)

    def test_placeholder_image_provider_writes_vertical_png_without_gemini_key(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        with patch("classes.YouTube.get_image_provider", return_value="placeholder"):
            path = youtube.generate_image("A Korean IT news visual about a new foldable phone")

        image_path = Path(path)
        self.assertTrue(image_path.exists())
        self.assertEqual(image_path.suffix, ".png")
        self.assertIn(str(image_path), youtube.images)

    def test_generate_prompts_respects_configured_max_image_prompts(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.subject = "Foldable phone launch"
        youtube.script = "첫 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다."
        response = json.dumps(["prompt 1", "prompt 2", "prompt 3", "prompt 4"])

        with patch.object(youtube, "generate_response", return_value=response), patch(
            "classes.YouTube.get_max_image_prompts", return_value=2
        ):
            prompts = youtube.generate_prompts()

        self.assertEqual(prompts, ["prompt 1", "prompt 2"])


if __name__ == "__main__":
    unittest.main()
