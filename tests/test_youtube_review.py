import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeReviewTests(unittest.TestCase):
    def test_review_timestamps_include_intro_for_long_shorts(self):
        from classes.youtube_review import _review_timestamps

        self.assertEqual(_review_timestamps(32.0), [2.56, 11.2, 18.56, 26.24])

    def test_extract_video_review_frame_writes_metadata_for_real_mp4(self):
        from moviepy.editor import ColorClip
        from classes.youtube_review import extract_video_review_frame

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        video_path = media_dir / "youtube-review-source.mp4"
        frame_path = media_dir / "youtube-review-frame.png"
        sheet_path = media_dir / "youtube-review-frame_sheet.png"

        clip = ColorClip(size=(108, 192), color=(30, 45, 60), duration=0.6).set_fps(12)
        try:
            clip.write_videofile(
                str(video_path),
                codec="libx264",
                fps=12,
                audio=False,
                verbose=False,
                logger=None,
            )
        finally:
            clip.close()

        metadata = extract_video_review_frame(video_path, frame_path)

        self.assertTrue(frame_path.exists())
        self.assertTrue(sheet_path.exists())
        from PIL import Image
        with Image.open(sheet_path) as sheet:
            self.assertEqual(sheet.size, (302, 546))
        self.assertGreater(metadata["duration"], 0.5)
        self.assertLess(metadata["duration"], 0.8)
        self.assertEqual(metadata["size"], [108, 192])
        self.assertEqual(metadata["fps"], 12.0)
        self.assertEqual(metadata["frame_path"], str(frame_path))
        self.assertEqual(metadata["review_frame_paths"], [str(frame_path)])
        self.assertEqual(metadata["review_sheet_path"], str(sheet_path))
        self.assertEqual(metadata["review_sheet_frame_count"], 1)
        self.assertAlmostEqual(
            metadata["review_frame_timestamp"],
            round(metadata["duration"] / 2, 3),
            places=2,
        )
        self.assertEqual(
            metadata["review_frame_timestamps"],
            [metadata["review_frame_timestamp"]],
        )
        self.assertGreater(metadata["review_frame_brightness"], 0)
        self.assertGreaterEqual(metadata["review_frame_contrast"], 0)
        self.assertEqual(
            metadata["review_frame_brightness_values"],
            [metadata["review_frame_brightness"]],
        )
        self.assertEqual(
            metadata["review_frame_contrast_values"],
            [metadata["review_frame_contrast"]],
        )
        self.assertGreater(metadata["review_frame_center_brightness"], 0)
        self.assertGreaterEqual(metadata["review_frame_center_contrast"], 0)
        self.assertEqual(
            metadata["review_frame_center_brightness_values"],
            [metadata["review_frame_center_brightness"]],
        )
        self.assertEqual(
            metadata["review_frame_center_contrast_values"],
            [metadata["review_frame_center_contrast"]],
        )
        self.assertEqual(metadata["review_frame_motion_scores"], [])
        self.assertIsNone(metadata["review_frame_average_motion_score"])
        self.assertIn("review_frame_low_contrast", metadata["review_warnings"])
        self.assertIn("review_frame_center_empty", metadata["review_warnings"])
        self.assertIn("video_resolution_below_1080x1920", metadata["review_warnings"])
        self.assertIn("video_duration_under_5s", metadata["review_warnings"])
        self.assertIn("video_fps_below_24", metadata["review_warnings"])
        self.assertIn("audio_missing", metadata["review_warnings"])
        self.assertIsNone(metadata["review_audio_peak"])
        self.assertIsNone(metadata["review_audio_rms"])
        self.assertEqual(metadata["review_file_size_bytes"], video_path.stat().st_size)
        self.assertFalse(metadata["review_quality_pass"])
        self.assertFalse(metadata["used_temp_copy"])

    def test_extract_video_review_frame_retries_with_ascii_temp_copy(self):
        from classes import youtube_review

        class FakeClip:
            duration = 1.2
            size = (1080, 1920)
            fps = 30
            audio = None

            def __init__(self):
                self.closed = False

            def save_frame(self, frame_path: str, t: float) -> None:
                from PIL import Image

                Image.new("RGB", (8, 8), color=(10, 20, 30)).save(frame_path)

            def close(self) -> None:
                self.closed = True

        opened_paths: list[Path] = []
        fake_clip = FakeClip()

        def fake_video_file_clip(path: str):
            opened_paths.append(Path(path))
            if len(opened_paths) == 1:
                raise OSError("original path failed")
            return fake_clip

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source = tmp_path / "한국어 영상.mp4"
            source.write_bytes(b"fake mp4")
            frame = tmp_path / "frame.png"
            temp_dir = tmp_path / "review-temp"

            with patch.object(youtube_review, "VideoFileClip", side_effect=fake_video_file_clip):
                metadata = youtube_review.extract_video_review_frame(
                    source,
                    frame,
                    temp_dir=temp_dir,
                )

            self.assertEqual(len(opened_paths), 2)
            self.assertEqual(opened_paths[0], source)
            self.assertTrue(opened_paths[1].name.startswith("review-"))
            self.assertTrue(opened_paths[1].name.isascii())
            self.assertFalse(opened_paths[1].exists())
            self.assertTrue(frame.exists())
            self.assertTrue((tmp_path / "frame_sheet.png").exists())
            self.assertTrue(fake_clip.closed)
            self.assertTrue(metadata["used_temp_copy"])
            self.assertEqual(metadata["review_frame_timestamp"], 0.6)
            self.assertEqual(metadata["review_frame_paths"], [str(frame)])
            self.assertEqual(metadata["review_frame_timestamps"], [0.6])
            self.assertEqual(metadata["review_sheet_path"], str(tmp_path / "frame_sheet.png"))
            self.assertEqual(metadata["review_sheet_frame_count"], 1)
            self.assertEqual(metadata["duration"], 1.2)
            self.assertEqual(metadata["size"], [1080, 1920])
            self.assertEqual(metadata["review_frame_contrast"], 0.0)
            self.assertEqual(metadata["review_frame_contrast_values"], [0.0])
            self.assertEqual(metadata["review_frame_center_contrast"], 0.0)
            self.assertEqual(metadata["review_frame_center_contrast_values"], [0.0])
            self.assertEqual(metadata["review_frame_motion_scores"], [])
            self.assertIsNone(metadata["review_frame_average_motion_score"])
            self.assertIn("review_frame_low_contrast", metadata["review_warnings"])
            self.assertIn("review_frame_center_empty", metadata["review_warnings"])
            self.assertIn("audio_missing", metadata["review_warnings"])
            self.assertIn("video_duration_under_5s", metadata["review_warnings"])
            self.assertFalse(metadata["review_quality_pass"])

    def test_extract_video_review_frame_can_pass_for_valid_shorts_metadata(self):
        from classes import youtube_review

        class FakeAudio:
            def get_frame(self, times):
                import numpy as np

                times = np.asarray(times, dtype=float)
                tone = 0.35 * np.sin(2 * np.pi * 2 * times)
                return np.column_stack([tone, tone])

        saved_frames: list[tuple[Path, float]] = []

        class FakeClip:
            duration = 32.0
            size = (1080, 1920)
            fps = 30
            audio = FakeAudio()

            def save_frame(self, frame_path: str, t: float) -> None:
                from PIL import Image

                saved_frames.append((Path(frame_path), t))
                image = Image.new("RGB", (32, 32))
                pixels = image.load()
                shift = int(round(t * 3)) % 32
                for y in range(32):
                    for x in range(32):
                        pixels[x, y] = (
                            (x * 8 + shift * 5) % 256,
                            (y * 8 + shift * 7) % 256,
                            90,
                        )
                image.save(frame_path)

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "valid-short.mp4"
            frame = Path(tmpdir) / "frame.png"
            source.write_bytes(b"placeholder")

            with patch.object(youtube_review, "VideoFileClip", return_value=FakeClip()), patch.object(
                youtube_review, "_video_file_size", return_value=4_000_000
            ):
                metadata = youtube_review.extract_video_review_frame(source, frame)

        self.assertTrue(metadata["review_quality_pass"])
        self.assertEqual(metadata["review_warnings"], [])
        self.assertEqual(metadata["review_file_size_bytes"], 4_000_000)
        self.assertEqual(metadata["review_frame_timestamp"], 2.56)
        self.assertEqual(metadata["review_frame_paths"][0], str(frame))
        self.assertEqual(
            metadata["review_frame_paths"],
            [
                str(frame),
                str(frame.with_name("frame_2.png")),
                str(frame.with_name("frame_3.png")),
                str(frame.with_name("frame_4.png")),
            ],
        )
        self.assertEqual(metadata["review_frame_timestamps"], [2.56, 11.2, 18.56, 26.24])
        self.assertEqual(metadata["review_sheet_path"], str(frame.with_name("frame_sheet.png")))
        self.assertEqual(metadata["review_sheet_frame_count"], 4)
        self.assertEqual(
            saved_frames,
            [
                (frame, 2.56),
                (frame.with_name("frame_2.png"), 11.2),
                (frame.with_name("frame_3.png"), 18.56),
                (frame.with_name("frame_4.png"), 26.24),
            ],
        )
        self.assertEqual(len(metadata["review_frame_brightness_values"]), 4)
        self.assertEqual(len(metadata["review_frame_contrast_values"]), 4)
        self.assertEqual(len(metadata["review_frame_center_brightness_values"]), 4)
        self.assertEqual(len(metadata["review_frame_center_contrast_values"]), 4)
        self.assertGreater(metadata["review_frame_center_contrast"], 6)
        self.assertEqual(len(metadata["review_frame_motion_scores"]), 3)
        self.assertGreater(metadata["review_frame_average_motion_score"], 1.0)
        self.assertGreater(metadata["review_audio_peak"], 0.3)
        self.assertGreater(metadata["review_audio_rms"], 0.2)

    def test_review_frame_checks_visible_subtitle_region_when_expected(self):
        from PIL import Image, ImageDraw
        from classes.youtube_review import _analyze_review_frame

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            no_caption = tmp_path / "no-caption.png"
            with_caption = tmp_path / "with-caption.png"

            Image.new("RGB", (1080, 1920), color=(72, 96, 130)).save(no_caption)

            image = Image.new("RGB", (1080, 1920), color=(72, 96, 130))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((120, 1450, 960, 1620), radius=36, fill=(0, 0, 0))
            draw.rectangle((210, 1514, 870, 1556), fill=(255, 255, 255))
            image.save(with_caption)

            missing = _analyze_review_frame(no_caption, subtitle_expected=True)
            visible = _analyze_review_frame(with_caption, subtitle_expected=True)
            not_expected = _analyze_review_frame(no_caption, subtitle_expected=False)

        self.assertIn("review_subtitle_region_not_visible", missing["review_warnings"])
        self.assertGreater(visible["review_frame_caption_contrast"], 18)
        self.assertGreater(visible["review_frame_caption_dark_ratio"], 0.03)
        self.assertGreater(visible["review_frame_caption_bright_ratio"], 0.0015)
        self.assertNotIn("review_subtitle_region_not_visible", visible["review_warnings"])
        self.assertIsNone(not_expected["review_frame_caption_contrast"])
        self.assertNotIn("review_subtitle_region_not_visible", not_expected["review_warnings"])

    def test_review_frame_checks_visible_title_region_when_expected(self):
        from PIL import Image, ImageDraw
        from classes.youtube_review import _analyze_review_frame

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            no_title = tmp_path / "no-title.png"
            with_title = tmp_path / "with-title.png"

            Image.new("RGB", (1080, 1920), color=(90, 118, 150)).save(no_title)

            image = Image.new("RGB", (1080, 1920), color=(90, 118, 150))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((48, 44, 1032, 240), radius=34, fill=(0, 0, 0))
            draw.rounded_rectangle((76, 76, 190, 122), radius=18, fill=(255, 224, 52))
            draw.rectangle((240, 104, 930, 146), fill=(255, 255, 255))
            image.save(with_title)

            missing = _analyze_review_frame(no_title, title_overlay_expected=True)
            visible = _analyze_review_frame(with_title, title_overlay_expected=True)
            not_expected = _analyze_review_frame(no_title, title_overlay_expected=False)

        self.assertIn("review_title_region_not_visible", missing["review_warnings"])
        self.assertGreater(visible["review_frame_title_contrast"], 14)
        self.assertGreater(visible["review_frame_title_dark_ratio"], 0.02)
        self.assertGreater(visible["review_frame_title_bright_ratio"], 0.001)
        self.assertNotIn("review_title_region_not_visible", visible["review_warnings"])
        self.assertIsNone(not_expected["review_frame_title_contrast"])
        self.assertNotIn("review_title_region_not_visible", not_expected["review_warnings"])

    def test_extract_video_review_frame_flags_static_sampled_frames(self):
        from classes import youtube_review

        class FakeAudio:
            def get_frame(self, times):
                import numpy as np

                times = np.asarray(times, dtype=float)
                tone = 0.35 * np.sin(2 * np.pi * 2 * times)
                return np.column_stack([tone, tone])

        class FakeClip:
            duration = 32.0
            size = (1080, 1920)
            fps = 30
            audio = FakeAudio()

            def save_frame(self, frame_path: str, t: float) -> None:
                from PIL import Image

                image = Image.new("RGB", (32, 32))
                pixels = image.load()
                for y in range(32):
                    for x in range(32):
                        pixels[x, y] = (x * 8, y * 8, 90)
                image.save(frame_path)

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "static-short.mp4"
            frame = Path(tmpdir) / "frame.png"
            source.write_bytes(b"placeholder")

            with patch.object(youtube_review, "VideoFileClip", return_value=FakeClip()), patch.object(
                youtube_review, "_video_file_size", return_value=4_000_000
            ):
                metadata = youtube_review.extract_video_review_frame(source, frame)

        self.assertEqual(metadata["review_frame_motion_scores"], [0.0, 0.0, 0.0])
        self.assertEqual(metadata["review_frame_average_motion_score"], 0.0)
        self.assertIn("review_frames_low_motion", metadata["review_warnings"])
        self.assertFalse(metadata["review_quality_pass"])

    def test_extract_video_review_frame_flags_short_but_playable_duration(self):
        from classes import youtube_review

        class FakeAudio:
            def get_frame(self, times):
                import numpy as np

                times = np.asarray(times, dtype=float)
                tone = 0.35 * np.sin(2 * np.pi * 2 * times)
                return np.column_stack([tone, tone])

        class FakeClip:
            duration = 12.0
            size = (1080, 1920)
            fps = 30
            audio = FakeAudio()

            def save_frame(self, frame_path: str, t: float) -> None:
                from PIL import Image

                image = Image.new("RGB", (32, 32))
                pixels = image.load()
                shift = int(round(t * 3)) % 32
                for y in range(32):
                    for x in range(32):
                        pixels[x, y] = (
                            (x * 8 + shift * 5) % 256,
                            (y * 8 + shift * 7) % 256,
                            90,
                        )
                image.save(frame_path)

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "too-short-quality-short.mp4"
            frame = Path(tmpdir) / "frame.png"
            source.write_bytes(b"placeholder")

            with patch.object(youtube_review, "VideoFileClip", return_value=FakeClip()), patch.object(
                youtube_review, "_video_file_size", return_value=2_000_000
            ):
                metadata = youtube_review.extract_video_review_frame(source, frame)

        self.assertIn("video_duration_under_target", metadata["review_warnings"])
        self.assertNotIn("video_duration_under_5s", metadata["review_warnings"])
        self.assertFalse(metadata["review_quality_pass"])

    def test_extract_video_review_frame_flags_low_audio(self):
        from classes import youtube_review

        class QuietAudio:
            def get_frame(self, times):
                import numpy as np

                times = np.asarray(times, dtype=float)
                tone = 0.002 * np.sin(2 * np.pi * 2 * times)
                return np.column_stack([tone, tone])

        class FakeClip:
            duration = 32.0
            size = (1080, 1920)
            fps = 30
            audio = QuietAudio()

            def save_frame(self, frame_path: str, t: float) -> None:
                from PIL import Image

                image = Image.new("RGB", (32, 32))
                pixels = image.load()
                for y in range(32):
                    for x in range(32):
                        pixels[x, y] = (x * 8, y * 8, 90)
                image.save(frame_path)

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "quiet-short.mp4"
            frame = Path(tmpdir) / "frame.png"
            source.write_bytes(b"placeholder")

            with patch.object(youtube_review, "VideoFileClip", return_value=FakeClip()), patch.object(
                youtube_review, "_video_file_size", return_value=4_000_000
            ):
                metadata = youtube_review.extract_video_review_frame(source, frame)

        self.assertIn("audio_peak_too_low", metadata["review_warnings"])
        self.assertIn("audio_rms_too_low", metadata["review_warnings"])
        self.assertEqual(len(metadata["review_frame_paths"]), 4)
        self.assertFalse(metadata["review_quality_pass"])

    def test_extract_video_review_frame_retries_audio_sampling_one_timestamp_at_a_time(self):
        from classes import youtube_review

        class ScalarOnlyAudio:
            def get_frame(self, times):
                import numpy as np

                values = np.asarray(times, dtype=float)
                if values.ndim > 0:
                    raise IndexError("vector sampling failed")
                tone = 0.35 * np.sin(2 * np.pi * 2 * float(values))
                return [tone, tone]

        saved_frames: list[tuple[Path, float]] = []

        class FakeClip:
            duration = 32.0
            size = (1080, 1920)
            fps = 30
            audio = ScalarOnlyAudio()

            def save_frame(self, frame_path: str, t: float) -> None:
                from PIL import Image

                saved_frames.append((Path(frame_path), t))
                image = Image.new("RGB", (32, 32))
                pixels = image.load()
                shift = int(round(t * 3)) % 32
                for y in range(32):
                    for x in range(32):
                        pixels[x, y] = (
                            (x * 8 + shift * 5) % 256,
                            (y * 8 + shift * 7) % 256,
                            90,
                        )
                image.save(frame_path)

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "scalar-audio-short.mp4"
            frame = Path(tmpdir) / "frame.png"
            source.write_bytes(b"placeholder")

            with patch.object(youtube_review, "VideoFileClip", return_value=FakeClip()), patch.object(
                youtube_review, "_video_file_size", return_value=4_000_000
            ):
                metadata = youtube_review.extract_video_review_frame(source, frame)

        self.assertTrue(saved_frames)
        self.assertNotIn("audio_analysis_failed", metadata["review_warnings"])
        self.assertTrue(metadata["review_quality_pass"])
        self.assertGreater(metadata["review_audio_peak"], 0.3)
        self.assertGreater(metadata["review_audio_rms"], 0.2)

    def test_audio_quality_flags_nonfinite_samples(self):
        from classes.youtube_review import _analyze_audio_quality

        class NonfiniteAudio:
            def get_frame(self, times):
                import numpy as np

                values = np.asarray(times, dtype=float)
                if values.ndim == 0:
                    return np.array([float("nan"), float("inf")])
                return np.column_stack([
                    np.full(values.shape, float("nan")),
                    np.full(values.shape, float("inf")),
                ])

        class FakeClip:
            duration = 32.0
            audio = NonfiniteAudio()

        quality = _analyze_audio_quality(FakeClip())

        self.assertEqual(quality["review_audio_peak"], 0.0)
        self.assertEqual(quality["review_audio_rms"], 0.0)
        self.assertEqual(quality["review_audio_warnings"], ["audio_nonfinite_samples"])

    def test_review_archive_status_marks_failed_quality_for_review(self):
        from classes.youtube_review import review_archive_status

        self.assertEqual(review_archive_status({"review_quality_pass": True}), "generated")
        self.assertEqual(review_archive_status({"review_quality_pass": False}), "needs_review")
        self.assertEqual(
            review_archive_status(
                {"review_quality_pass": True},
                {"structure_quality_pass": False},
            ),
            "needs_review",
        )
        self.assertEqual(review_archive_status({}), "needs_review")

    def test_structure_quality_fields_flag_sparse_or_overcrowded_videos(self):
        from classes.youtube_review import build_structure_quality_fields

        weak = build_structure_quality_fields(
            script="short",
            images=["one.png"],
            image_prompts=["prompt"],
            duration=30.0,
            subtitle_max_chars=4,
        )
        self.assertFalse(weak["structure_quality_pass"])
        self.assertIn("structure_script_too_short", weak["structure_warnings"])
        self.assertIn("structure_image_count_low", weak["structure_warnings"])

        strong = build_structure_quality_fields(
            script=(
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            images=["one.png", "two.png", "three.png"],
            image_prompts=["prompt one", "prompt two", "prompt three"],
            metadata={"title": "갤럭시 AI 배터리 변화, 실제 체감은?"},
            duration=32.0,
            subtitle_max_chars=24,
        )
        self.assertTrue(strong["structure_quality_pass"])
        self.assertEqual(strong["metadata_title"], "갤럭시 AI 배터리 변화, 실제 체감은?")
        self.assertTrue(strong["metadata_title_has_hangul"])
        self.assertEqual(strong["image_count"], 3)
        self.assertGreaterEqual(strong["visual_clip_count"], 3)
        self.assertEqual(strong["image_prompt_unique_count"], 3)
        self.assertFalse(strong["placeholder_visuals_used"])
        self.assertEqual(strong["placeholder_visual_reasons"], [])

        too_short = build_structure_quality_fields(
            script=(
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            images=["one.png", "two.png", "three.png"],
            image_prompts=["prompt one", "prompt two", "prompt three"],
            metadata={"title": "갤럭시 AI 배터리 변화, 실제 체감은?"},
            duration=12.0,
            subtitle_max_chars=24,
        )
        self.assertFalse(too_short["structure_quality_pass"])
        self.assertIn("structure_duration_too_short", too_short["structure_warnings"])

    def test_structure_quality_fields_block_placeholder_visuals(self):
        from classes.youtube_review import build_structure_quality_fields

        quality = build_structure_quality_fields(
            script=(
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            images=["one.png", "two.png", "three.png"],
            image_prompts=["prompt one", "prompt two", "prompt three"],
            metadata={"title": "갤럭시 AI 배터리 변화"},
            duration=32.0,
            subtitle_max_chars=24,
            placeholder_visuals_used=True,
            placeholder_visual_reasons=["Hermes image queue empty", "  Gemini image unavailable  "],
        )

        self.assertFalse(quality["structure_quality_pass"])
        self.assertTrue(quality["placeholder_visuals_used"])
        self.assertEqual(
            quality["placeholder_visual_reasons"],
            ["Hermes image queue empty", "Gemini image unavailable"],
        )
        self.assertIn("structure_placeholder_visuals_used", quality["structure_warnings"])

    def test_structure_quality_uses_readable_subtitle_chunk_count(self):
        from classes.youtube_review import build_structure_quality_fields

        dense_script = " ".join(f"s{i:02d}" for i in range(20))
        quality = build_structure_quality_fields(
            script=dense_script,
            images=["one.png", "two.png", "three.png"],
            image_prompts=["prompt one", "prompt two", "prompt three"],
            metadata={"title": "Readable subtitle density check"},
            duration=3.0,
            subtitle_max_chars=4,
        )

        self.assertLess(quality["subtitle_chunk_count"], 20)
        self.assertGreaterEqual(quality["average_subtitle_seconds"], 0.65)
        self.assertNotIn("structure_subtitles_too_dense", quality["structure_warnings"])

    def test_structure_quality_fields_flag_bad_metadata_titles(self):
        from classes.youtube_review import build_structure_quality_fields

        base = {
            "script": (
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            "images": ["one.png", "two.png", "three.png"],
            "image_prompts": ["prompt one", "prompt two", "prompt three"],
            "duration": 32.0,
            "subtitle_max_chars": 24,
        }

        english_title = build_structure_quality_fields(
            **base,
            metadata={"title": "Samsung unveils new on-device AI battery feature"},
        )
        self.assertFalse(english_title["structure_quality_pass"])
        self.assertIn("structure_title_not_korean", english_title["structure_warnings"])
        self.assertFalse(english_title["metadata_title_has_hangul"])

        uuid_title = build_structure_quality_fields(
            **base,
            metadata={"title": "23bc7b7e-23cc-4e9d-95b7-385c39fc4397"},
        )
        self.assertIn("structure_title_uuid_like", uuid_title["structure_warnings"])

        missing_title = build_structure_quality_fields(**base, metadata={"title": ""})
        self.assertIn("structure_title_missing", missing_title["structure_warnings"])

    def test_structure_quality_fields_flag_missing_or_duplicate_image_prompts(self):
        from classes.youtube_review import build_structure_quality_fields

        base = {
            "script": (
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            "images": ["one.png", "two.png", "three.png"],
            "metadata": {"title": "갤럭시 AI 배터리 변화"},
            "duration": 32.0,
            "subtitle_max_chars": 24,
        }

        missing_prompts = build_structure_quality_fields(
            **base,
            image_prompts=[],
        )
        self.assertFalse(missing_prompts["structure_quality_pass"])
        self.assertEqual(missing_prompts["image_prompt_count"], 0)
        self.assertIn("structure_image_prompt_count_low", missing_prompts["structure_warnings"])

        duplicate_prompts = build_structure_quality_fields(
            **base,
            image_prompts=["generic chip close-up", "generic chip close-up"],
        )
        self.assertFalse(duplicate_prompts["structure_quality_pass"])
        self.assertEqual(duplicate_prompts["image_prompt_unique_count"], 1)
        self.assertIn("structure_image_prompt_duplicate", duplicate_prompts["structure_warnings"])

    def test_structure_quality_fields_validate_image_files_when_enabled(self):
        from PIL import Image
        from classes.youtube_review import build_structure_quality_fields

        base = {
            "script": (
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            "image_prompts": ["prompt one", "prompt two", "prompt three"],
            "metadata": {"title": "갤럭시 AI 배터리 변화"},
            "duration": 32.0,
            "subtitle_max_chars": 24,
            "validate_image_files": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            good_one = tmp_path / "good-one.png"
            good_two = tmp_path / "good-two.png"
            duplicate = tmp_path / "duplicate.png"
            small = tmp_path / "small.png"
            missing = tmp_path / "missing.png"
            Image.new("RGB", (1080, 1920), color=(10, 20, 30)).save(good_one)
            Image.new("RGB", (1080, 1920), color=(40, 50, 60)).save(good_two)
            Image.new("RGB", (1080, 1920), color=(10, 20, 30)).save(duplicate)
            Image.new("RGB", (320, 320), color=(70, 80, 90)).save(small)

            valid_images = build_structure_quality_fields(
                **base,
                images=[str(good_one), str(good_two)],
            )
            duplicate_images = build_structure_quality_fields(
                **base,
                images=[str(good_one), str(duplicate), str(good_two)],
            )
            bad_images = build_structure_quality_fields(
                **base,
                images=[str(good_one), str(small), str(missing)],
            )

        self.assertTrue(valid_images["structure_quality_pass"])
        self.assertTrue(valid_images["image_file_validation_enabled"])
        self.assertEqual(valid_images["image_file_existing_count"], 2)
        self.assertEqual(valid_images["image_file_missing_count"], 0)
        self.assertEqual(valid_images["image_file_low_resolution_count"], 0)
        self.assertEqual(valid_images["image_file_bad_aspect_count"], 0)
        self.assertEqual(valid_images["image_file_duplicate_count"], 0)
        self.assertEqual(valid_images["image_file_unique_fingerprint_count"], 2)
        self.assertEqual(valid_images["image_sizes"], [[1080, 1920], [1080, 1920]])

        self.assertFalse(duplicate_images["structure_quality_pass"])
        self.assertEqual(duplicate_images["image_file_existing_count"], 3)
        self.assertEqual(duplicate_images["image_file_duplicate_count"], 1)
        self.assertEqual(duplicate_images["image_file_unique_fingerprint_count"], 2)
        self.assertIn("structure_image_file_duplicate", duplicate_images["structure_warnings"])

        self.assertFalse(bad_images["structure_quality_pass"])
        self.assertEqual(bad_images["image_file_existing_count"], 2)
        self.assertEqual(bad_images["image_file_missing_count"], 1)
        self.assertEqual(bad_images["image_file_low_resolution_count"], 1)
        self.assertEqual(bad_images["image_file_bad_aspect_count"], 1)
        self.assertEqual(bad_images["image_file_duplicate_count"], 0)
        self.assertIn("structure_image_file_missing", bad_images["structure_warnings"])
        self.assertIn("structure_image_resolution_low", bad_images["structure_warnings"])
        self.assertIn("structure_image_aspect_ratio_not_9_16", bad_images["structure_warnings"])

    def test_structure_quality_fields_validate_subtitle_artifact_when_provided(self):
        from classes.youtube_review import build_structure_quality_fields

        base = {
            "script": (
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            "images": ["one.png", "two.png", "three.png"],
            "image_prompts": ["prompt one", "prompt two", "prompt three"],
            "metadata": {"title": "갤럭시 AI 배터리 변화"},
            "duration": 32.0,
            "subtitle_max_chars": 24,
        }

        missing_subtitles = build_structure_quality_fields(
            **base,
            subtitle_path="",
        )
        self.assertFalse(missing_subtitles["structure_quality_pass"])
        self.assertFalse(missing_subtitles["subtitle_file_exists"])
        self.assertIn("structure_subtitle_file_missing", missing_subtitles["structure_warnings"])

        with tempfile.TemporaryDirectory() as tmpdir:
            subtitle_path = Path(tmpdir) / "captions.srt"
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:15,000\n첫 번째 자막입니다.\n\n"
                "2\n00:00:15,000 --> 00:00:32,000\n두 번째 자막입니다.\n",
                encoding="utf-8",
            )
            valid_subtitles = build_structure_quality_fields(
                **base,
                subtitle_path=subtitle_path,
            )

        self.assertTrue(valid_subtitles["structure_quality_pass"])
        self.assertTrue(valid_subtitles["subtitle_file_exists"])
        self.assertGreater(valid_subtitles["subtitle_file_bytes"], 0)
        self.assertEqual(valid_subtitles["subtitle_entry_count"], 2)
        self.assertEqual(valid_subtitles["subtitle_first_start_seconds"], 0.0)
        self.assertEqual(valid_subtitles["subtitle_last_end_seconds"], 32.0)
        self.assertEqual(valid_subtitles["subtitle_coverage_ratio"], 1.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            short_subtitle_path = Path(tmpdir) / "short-captions.srt"
            short_subtitle_path.write_text(
                "1\n00:00:05,000 --> 00:00:08,000\n첫 번째 자막입니다.\n\n"
                "2\n00:00:08,000 --> 00:00:10,000\n두 번째 자막입니다.\n",
                encoding="utf-8",
            )
            short_coverage = build_structure_quality_fields(
                **base,
                subtitle_path=short_subtitle_path,
            )

        self.assertFalse(short_coverage["structure_quality_pass"])
        self.assertEqual(short_coverage["subtitle_first_start_seconds"], 5.0)
        self.assertEqual(short_coverage["subtitle_last_end_seconds"], 10.0)
        self.assertLess(short_coverage["subtitle_coverage_ratio"], 0.85)
        self.assertIn("structure_subtitle_starts_late", short_coverage["structure_warnings"])
        self.assertIn("structure_subtitle_ends_early", short_coverage["structure_warnings"])
        self.assertIn("structure_subtitle_coverage_low", short_coverage["structure_warnings"])


if __name__ == "__main__":
    unittest.main()
