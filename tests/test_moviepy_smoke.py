import os
import sys
import unittest
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class MoviePySmokeTests(unittest.TestCase):
    def test_can_compose_vertical_mp4_from_image_and_silent_wav(self):
        from PIL import Image
        from moviepy.editor import AudioFileClip, ImageClip

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        image_path = media_dir / "moviepy-smoke-source.png"
        wav_path = media_dir / "moviepy-smoke-source.wav"
        mp4_path = media_dir / "moviepy-smoke-output.mp4"

        Image.new("RGB", (1080, 1920), color=(20, 24, 40)).save(image_path)
        with wave.open(str(wav_path), "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * 24000)

        audio = AudioFileClip(str(wav_path))
        clip = ImageClip(str(image_path)).set_duration(audio.duration).set_fps(24).set_audio(audio)
        clip.write_videofile(
            str(mp4_path),
            codec="libx264",
            audio_codec="aac",
            fps=24,
            verbose=False,
            logger=None,
        )
        clip.close()
        audio.close()

        self.assertTrue(mp4_path.exists())
        self.assertGreater(os.path.getsize(mp4_path), 1000)


if __name__ == "__main__":
    unittest.main()
