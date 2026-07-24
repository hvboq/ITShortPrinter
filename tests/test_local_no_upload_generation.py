import json
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class LocalNoUploadGenerationTests(unittest.TestCase):
    def _png_bytes(self, width: int, height: int) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", (width, height), color=(10, 20, 30)).save(buffer, format="PNG")
        return buffer.getvalue()

    def _striped_png_bytes(self, width: int, height: int) -> bytes:
        image = Image.new("RGB", (width, height), color=(40, 180, 90))
        for x in range(width // 3):
            for y in range(height):
                image.putpixel((x, y), (220, 40, 50))
        for x in range(width * 2 // 3, width):
            for y in range(height):
                image.putpixel((x, y), (40, 80, 230))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

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

    def test_placeholder_visual_varies_by_prompt(self):
        from classes import youtube_visuals

        images = []
        first = youtube_visuals.generate_placeholder_image(
            "AI chip battery efficiency opening visual",
            images,
        )
        second = youtube_visuals.generate_placeholder_image(
            "Foldable display market analysis visual",
            images,
        )

        with Image.open(first) as first_image, Image.open(second) as second_image:
            self.assertEqual(first_image.size, (1080, 1920))
            self.assertEqual(second_image.size, (1080, 1920))
            self.assertNotEqual(
                first_image.getpixel((80, 80)),
                second_image.getpixel((80, 80)),
            )
            self.assertNotEqual(
                first_image.getpixel((530, 900)),
                second_image.getpixel((530, 900)),
            )

        self.assertEqual(images, [first, second])

    def test_persist_image_bytes_normalizes_provider_images_for_qc(self):
        from classes import youtube_visuals
        from classes.youtube_review import _image_artifact_quality

        buffer = BytesIO()
        Image.open(BytesIO(self._striped_png_bytes(1200, 675))).save(buffer, format="JPEG")

        images = []
        path = youtube_visuals.persist_image_bytes(
            buffer.getvalue(),
            "test provider",
            images,
        )

        self.assertEqual(images, [path])
        with Image.open(path) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1080, 1920))

        quality = _image_artifact_quality([path], validate_files=True)
        self.assertEqual(quality["image_sizes"], [[1080, 1920]])
        self.assertNotIn("structure_image_resolution_low", quality["warnings"])
        self.assertNotIn("structure_image_aspect_ratio_not_9_16", quality["warnings"])

    def test_download_image_rejects_tiny_article_images(self):
        from classes import youtube_visuals

        class FakeResponse:
            content = self._png_bytes(120, 120)

            def raise_for_status(self):
                return None

        images = []
        with patch("requests.get", return_value=FakeResponse()):
            path = youtube_visuals.download_image("https://example.com/icon.png", images)

        self.assertIsNone(path)
        self.assertEqual(images, [])

    def test_download_image_accepts_article_lead_visuals(self):
        from classes import youtube_visuals

        class FakeResponse:
            content = self._png_bytes(1200, 675)

            def raise_for_status(self):
                return None

        images = []
        with patch("requests.get", return_value=FakeResponse()):
            path = youtube_visuals.download_image("https://example.com/lead.png", images)

        image_path = Path(path)
        self.assertTrue(image_path.exists())
        self.assertIn(str(image_path), images)
        with Image.open(image_path) as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_article_lead_visual_preserves_wide_source_edges(self):
        from classes import youtube_visuals

        source = Image.open(BytesIO(self._striped_png_bytes(1200, 675)))
        visual = youtube_visuals.compose_article_lead_visual(source)

        self.assertEqual(visual.size, (1080, 1920))
        left_sample = visual.getpixel((76, 860))
        right_sample = visual.getpixel((1004, 860))
        self.assertGreater(left_sample[0], 160)
        self.assertLess(left_sample[2], 110)
        self.assertGreater(right_sample[2], 160)
        self.assertLess(right_sample[0], 110)

    def test_article_lead_image_is_used_when_available(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.news_article = {"image_url": "https://example.com/lead.png"}

        with patch.object(youtube, "download_image", return_value="lead.png") as download:
            image_path = youtube._add_article_lead_image()

        self.assertEqual(image_path, "lead.png")
        download.assert_called_once_with("https://example.com/lead.png")

    def test_generate_video_attempts_article_lead_image_before_ai_images(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.news_article = {"image_url": "https://example.com/lead.png"}

        def set_topic():
            youtube.subject = "AI phone launch"
            return youtube.subject

        def set_script():
            youtube.script = "AI 기능이 배터리 사용 방식을 바꿉니다."
            return youtube.script

        def set_metadata():
            youtube.metadata = {"title": "AI폰 배터리 변화"}
            return youtube.metadata

        def set_prompts():
            youtube.image_prompts = ["generic chip visual"]
            return youtube.image_prompts

        with patch.object(youtube, "generate_topic", side_effect=set_topic), patch.object(
            youtube, "generate_script", side_effect=set_script
        ), patch.object(youtube, "generate_metadata", side_effect=set_metadata), patch.object(
            youtube, "_add_article_lead_image"
        ) as add_lead, patch.object(
            youtube, "generate_prompts", side_effect=set_prompts
        ), patch.object(
            youtube, "generate_image"
        ) as generate_image, patch.object(
            youtube, "generate_script_to_speech"
        ), patch.object(
            youtube, "combine", return_value="out.mp4"
        ):
            path = youtube.generate_video(object())

        self.assertEqual(path, "out.mp4")
        add_lead.assert_called_once()
        generate_image.assert_called_once_with("generic chip visual")

    def test_hermes_image_provider_consumes_preseeded_queue_image(self):
        from classes.YouTube import YouTube

        with tempfile.TemporaryDirectory() as tmpdir:
            queue_dir = Path(tmpdir) / "queue"
            queue_dir.mkdir(parents=True, exist_ok=True)
            queued_image = queue_dir / "test-hermes-image.png"
            Image.new("RGB", (800, 800), color=(10, 20, 30)).save(queued_image)

            youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
            with patch("classes.YouTube.get_image_provider", return_value="hermes"), patch.dict(
                "os.environ", {"HERMES_IMAGE_QUEUE_DIR": str(queue_dir)}
            ):
                path = youtube.generate_image("A Korean IT news visual generated by Hermes")

            image_path = Path(path)
            self.assertTrue(image_path.exists())
            self.assertEqual(image_path.suffix, ".png")
            self.assertIn(str(image_path), youtube.images)
            self.assertFalse(queued_image.exists())
            self.assertIn("hermes", image_path.name)
            with Image.open(image_path) as image:
                self.assertEqual(image.size, (1080, 1920))

    def test_hermes_image_provider_can_generate_via_hermes_cli_when_enabled(self):
        from classes.YouTube import YouTube

        with tempfile.TemporaryDirectory() as tmpdir:
            generated = Path(tmpdir) / "generated.png"
            Image.new("RGB", (1080, 1920), color=(30, 40, 50)).save(generated)

            def fake_run(args, **kwargs):
                self.assertEqual(args[0], "hermes")
                self.assertIn("image_gen", args)
                self.assertIn("openai-codex", args)
                self.assertIn("gpt-5.5", args)
                return subprocess.CompletedProcess(args, 0, stdout=str(generated), stderr="")

            youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
            with patch("classes.YouTube.get_image_provider", return_value="hermes"), patch(
                "classes.youtube_visuals.subprocess.run", side_effect=fake_run
            ), patch.dict(
                "os.environ", {"HERMES_ENABLE_CLI_IMAGE_GENERATION": "1"}, clear=False
            ):
                path = youtube.generate_image("A Korean IT news visual generated by Hermes CLI")

            image_path = Path(path)
            self.assertTrue(image_path.exists())
            self.assertEqual(image_path.suffix, ".png")
            self.assertIn(str(image_path), youtube.images)
            self.assertIn("hermes", image_path.name)
            self.assertFalse(youtube.has_placeholder_visuals)

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

        self.assertEqual(len(prompts), 2)
        self.assertIn("Foldable phone launch", prompts[0])
        self.assertIn("prompt 1", prompts[0])
        self.assertIn("prompt 2", prompts[1])
        self.assertTrue(all("유튜브 쇼츠 UI 없음" in prompt for prompt in prompts))

    def test_generate_prompts_fills_missing_visual_beats_and_deduplicates(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="IT News", language="Korean")
        youtube.subject = "AI chip battery efficiency"
        youtube.script = "AI 칩이 배터리 효율을 바꾸는 이야기입니다."
        response = json.dumps(["generic chip close-up", "generic chip close-up"])

        with patch.object(youtube, "generate_response", return_value=response), patch(
            "classes.YouTube.get_max_image_prompts", return_value=3
        ):
            prompts = youtube.generate_prompts()

        self.assertEqual(len(prompts), 3)
        self.assertIn("generic chip close-up", prompts[0])
        self.assertIn("AI chip battery efficiency", prompts[1])
        self.assertIn("AI chip battery efficiency", prompts[2])
        self.assertEqual(len(set(prompts)), 3)
        self.assertTrue(all("이미지 안 텍스트 없음" in prompt for prompt in prompts))

    def test_finalize_image_prompts_assigns_scene_roles_to_each_cut(self):
        from classes import youtube_visuals

        prompts = youtube_visuals.finalize_image_prompts(
            ["generic device close-up", "generic chip detail", "market context visual"],
            target_count=3,
            subject="AI phone battery update",
        )

        self.assertIn(youtube_visuals.VISUAL_BEAT_TEMPLATES[0], prompts[0])
        self.assertIn(youtube_visuals.VISUAL_BEAT_TEMPLATES[1], prompts[1])
        self.assertIn(youtube_visuals.VISUAL_BEAT_TEMPLATES[2], prompts[2])
        self.assertTrue(all("AI phone battery update" in prompt for prompt in prompts))
        self.assertTrue(all("유튜브 쇼츠 UI 없음" in prompt for prompt in prompts))

    def test_finalize_image_prompts_does_not_prefix_english_subject_to_korean_prompt(self):
        from classes import youtube_visuals

        prompts = youtube_visuals.finalize_image_prompts(
            ["배터리 효율 변화를 보여주는 선명한 세로형 IT 뉴스 비주얼"],
            target_count=1,
            subject="Samsung details on-device AI battery improvements for upcoming phones",
        )

        self.assertIn("배터리 효율 변화", prompts[0])
        self.assertNotIn("Samsung details", prompts[0])
        self.assertTrue(prompts[0].startswith("배터리 효율"))

    def test_placeholder_display_text_hides_generation_safety_instructions(self):
        from classes import youtube_visuals

        prompt = (
            "AI 칩 배터리 효율 변화를 보여주는 선명한 뉴스 비주얼. "
            "이 컷은 핵심 변화가 곧 시작될 것 같은 긴장감 있는 세로형 IT 뉴스 오프닝 비주얼 구도로 구성. "
            f"{youtube_visuals.PROMPT_SAFETY_SUFFIX}"
        )

        display = youtube_visuals.placeholder_display_text(prompt)

        self.assertIn("AI 칩 배터리 효율", display)
        self.assertNotIn("이 컷은", display)
        self.assertNotIn("구도로 구성", display)
        self.assertNotIn("유튜브 쇼츠 UI 없음", display)
        self.assertNotIn("이미지 안 텍스트 없음", display)

    def test_placeholder_display_text_removes_english_subject_prefix(self):
        from classes import youtube_visuals

        prompt = (
            "Samsung details on-device AI battery improvements for upcoming phones "
            "주제를 반영한 배터리 효율 변화를 보여주는 선명한 세로형 IT 뉴스 비주얼. "
            f"{youtube_visuals.PROMPT_SAFETY_SUFFIX}"
        )

        display = youtube_visuals.placeholder_display_text(prompt)

        self.assertIn("배터리 효율 변화", display)
        self.assertNotIn("Samsung details", display)


if __name__ == "__main__":
    unittest.main()
