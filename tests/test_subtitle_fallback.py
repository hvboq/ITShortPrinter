import sys
import unittest
from pathlib import Path

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

    def test_subtitle_overlay_uses_image_clips_not_imagemagick_textclip(self):
        from classes.YouTube import YouTube
        from moviepy.video.VideoClip import ImageClip

        youtube = YouTube.for_local_generation(niche="Korean IT News", language="Korean")
        youtube.script = "한국어 자막 오버레이 테스트입니다."
        srt_path = youtube.generate_subtitles_from_script(duration_seconds=3.0)
        clips = youtube._create_subtitle_clips(srt_path)

        self.assertGreater(len(clips), 0)
        self.assertIsInstance(clips[0], ImageClip)
        self.assertGreater(clips[0].duration, 0)


if __name__ == "__main__":
    unittest.main()
