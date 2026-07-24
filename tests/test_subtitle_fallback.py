import sys
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class SubtitleFallbackTests(unittest.TestCase):
    def test_script_subtitle_fallback_writes_korean_srt_chunks(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = (
            "화웨이가 새로운 폴더블 기기를 공개했습니다. "
            "이 제품은 대용량 배터리와 넓은 화면으로 주목받고 있습니다. "
            "최신 IT 소식을 계속 보고 싶다면 채널을 구독해 주세요."
        )

        srt_path = youtube.generate_subtitles_from_script(duration_seconds=9.0, max_chars=34)
        content = Path(srt_path).read_text(encoding="utf-8")

        self.assertTrue(Path(srt_path).exists())
        self.assertIn("00:00:00,000 -->", content)
        self.assertIn("화웨이가 새로운 폴더블 기기를 공개했습니다", content)
        self.assertIn("채널을 구독해 주세요", content)

    def test_safe_subtitle_generation_falls_back_to_script_when_stt_fails(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = "한국어 대본 기반 자막입니다. STT가 실패해도 화면에 보여야 합니다."

        def fail_stt(_audio_path):
            raise ImportError("No module named 'faster_whisper'")

        youtube.generate_subtitles = fail_stt
        srt_path = youtube.generate_safe_subtitles("missing.wav", duration_seconds=6.0)
        content = Path(srt_path).read_text(encoding="utf-8")

        self.assertIn("한국어 대본 기반 자막입니다", content)
        self.assertIn("STT가 실패해도 화면에 보여야 합니다", content)

    def test_safe_subtitle_generation_uses_script_by_default_without_stt(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = "갤럭시 A37 5G를 그대로 쓰는 대본 기반 자막입니다."

        def fail_if_called(_audio_path):
            raise AssertionError("STT should not be called by default")

        youtube.generate_subtitles = fail_if_called
        with mock.patch.dict("os.environ", {}, clear=True):
            srt_path = youtube.generate_safe_subtitles("missing.wav", duration_seconds=4.0)
        content = Path(srt_path).read_text(encoding="utf-8")

        self.assertIn("갤럭시 A37 5G를", content)

    def test_safe_subtitle_generation_can_opt_into_stt(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = "이 대본은 STT 선택 테스트입니다."

        def fake_stt(_audio_path):
            path = PROJECT_ROOT / ".mp" / "fake-stt-test.srt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("1\n00:00:00,000 --> 00:00:01,000\nSTT 자막\n", encoding="utf-8")
            return str(path)

        youtube.generate_subtitles = fake_stt
        with mock.patch.dict("os.environ", {"SHORTS_USE_STT_SUBTITLES": "1"}, clear=True):
            srt_path = youtube.generate_safe_subtitles("audio.wav", duration_seconds=4.0)
        content = Path(srt_path).read_text(encoding="utf-8")

        self.assertIn("STT 자막", content)

    def test_safe_subtitle_fallback_uses_configured_subtitle_chunk_length(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = "배터리 효율 변화가 실제 사용 시간에 어떤 영향을 주는지 빠르게 정리합니다."

        def fail_stt(_audio_path):
            raise ImportError("No module named 'faster_whisper'")

        youtube.generate_subtitles = fail_stt
        with patch("classes.YouTube.get_subtitle_max_chars", return_value=12):
            srt_path = youtube.generate_safe_subtitles("missing.wav", duration_seconds=6.0)

        content = Path(srt_path).read_text(encoding="utf-8")
        caption_lines = [
            line
            for line in content.splitlines()
            if line and "-->" not in line and not line.isdigit()
        ]

        self.assertGreater(len(caption_lines), 1)
        self.assertTrue(all(len(line.replace(" ", "")) <= 12 for line in caption_lines))

    def test_script_subtitle_fallback_merges_overcrowded_chunks_for_readability(self):
        from classes import youtube_subtitles

        script = " ".join(f"s{i:02d}" for i in range(20))
        content = youtube_subtitles.build_script_srt_content(
            script,
            duration_seconds=3.0,
            max_chars=4,
        )
        entries = []
        for block in content.strip().split("\n\n"):
            lines = block.splitlines()
            start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
            entries.append(
                (
                    youtube_subtitles.parse_srt_timestamp(start_raw),
                    youtube_subtitles.parse_srt_timestamp(end_raw),
                )
            )

        self.assertLess(len(entries), 20)
        self.assertLessEqual(
            len(entries),
            int(3.0 / youtube_subtitles.MIN_READABLE_SUBTITLE_SECONDS),
        )
        self.assertTrue(all(end > start for start, end in entries))
        self.assertTrue(
            all(
                end - start >= youtube_subtitles.MIN_READABLE_SUBTITLE_SECONDS * 0.75
                for start, end in entries
            )
        )
        self.assertTrue(
            all(entries[index][0] >= entries[index - 1][1] for index in range(1, len(entries)))
        )
        self.assertAlmostEqual(entries[-1][1], 3.0, places=3)
        self.assertIn("s00 s01", content)
        self.assertIn("s18 s19", content)

    def test_subtitle_overlay_uses_image_clips_not_imagemagick_textclip(self):
        from classes.YouTube import YouTube
        from moviepy.video.VideoClip import TextClip, VideoClip

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = "한국어 자막 오버레이 테스트입니다."
        srt_path = youtube.generate_subtitles_from_script(duration_seconds=3.0)
        clips = youtube._create_subtitle_clips(srt_path)

        self.assertGreater(len(clips), 0)
        self.assertIsInstance(clips[0], VideoClip)
        self.assertNotIsInstance(clips[0], TextClip)
        self.assertGreater(clips[0].duration, 0)

    def test_subtitle_style_uses_white_text_on_black_background(self):
        from classes import youtube_subtitles

        self.assertEqual(youtube_subtitles.SUBTITLE_TEXT_FILL, (255, 255, 255, 255))
        self.assertEqual(youtube_subtitles.SUBTITLE_BACKGROUND_FILL[:3], (0, 0, 0))
        self.assertEqual(youtube_subtitles.SUBTITLE_BACKGROUND_FILL[3], 255)

    def test_subtitle_text_corrections_fix_lenovo_mistranscription(self):
        from classes import youtube_subtitles

        content = youtube_subtitles.build_script_srt_content(
            "랜오버가 새 AI 노트북을 공개했습니다.",
            duration_seconds=3.0,
        )

        self.assertIn("레노버가 새 AI 노트북", content)
        self.assertNotIn("랜오버", content)
        self.assertEqual(
            youtube_subtitles.normalize_subtitle_text("랜 오버와 랜노버, 레너버"),
            "레노버와 레노버, 레노버",
        )

    def test_long_subtitle_and_title_render_inside_vertical_canvas(self):
        from classes.YouTube import YouTube
        from classes import youtube_subtitles

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        font_path = youtube._subtitle_font_path()

        subtitle_image = youtube_subtitles.render_subtitle_image(
            "삼성의 새 온디바이스 AI 기능은 배터리 사용 시간과 개인정보 처리 방식까지 바꿀 수 있습니다.",
            font_path,
        )
        title_image = youtube_subtitles.render_title_overlay_image(
            "갤럭시 새 AI 기능, 사용자가 체감할 변화는 무엇일까요",
            font_path,
        )

        self.assertEqual(subtitle_image.size, (1080, 360))
        self.assertEqual(title_image.size, (1080, 292))
        self.assertIsNotNone(subtitle_image.getbbox())
        self.assertIsNotNone(title_image.getbbox())

    def test_title_overlay_declutters_long_videos_after_intro(self):
        from classes.YouTube import YouTube
        from classes import youtube_subtitles

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        font_path = youtube._subtitle_font_path()
        short_clip = youtube_subtitles.create_title_overlay_clip(
            "짧은 영상은 제목을 계속 유지합니다",
            font_path,
            duration=4.0,
        )
        long_clip = youtube_subtitles.create_title_overlay_clip(
            "긴 영상은 초반 이후 화면을 더 넓게 보여줍니다",
            font_path,
            duration=30.0,
        )
        try:
            self.assertAlmostEqual(short_clip.duration, 4.0, places=2)
            self.assertAlmostEqual(
                long_clip.duration,
                youtube_subtitles.TITLE_OVERLAY_MAX_DURATION_SECONDS,
                places=2,
            )
            self.assertLess(long_clip.duration, 30.0)
        finally:
            short_clip.close()
            long_clip.close()


if __name__ == "__main__":
    unittest.main()
