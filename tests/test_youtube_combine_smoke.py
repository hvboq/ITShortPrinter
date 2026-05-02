import os
import sys
import unittest
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeCombineSmokeTests(unittest.TestCase):
    def test_combine_can_write_mp4_without_subtitle_dependencies(self):
        from PIL import Image
        from classes.YouTube import YouTube

        media_dir = PROJECT_ROOT / ".mp"
        songs_dir = PROJECT_ROOT / "Songs"
        media_dir.mkdir(exist_ok=True)
        songs_dir.mkdir(exist_ok=True)

        image_path = media_dir / "youtube-combine-smoke-image.png"
        tts_path = media_dir / "youtube-combine-smoke-tts.wav"
        song_path = songs_dir / "youtube-combine-smoke-song.wav"

        Image.new("RGB", (1080, 1920), color=(15, 22, 36)).save(image_path)
        for wav_path in [tts_path, song_path]:
            with wave.open(str(wav_path), "w") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b"\x00\x00" * 24000)

        youtube = object.__new__(YouTube)
        youtube.images = [str(image_path)]
        youtube.tts_path = str(tts_path)

        output_path = youtube.combine()

        self.assertTrue(Path(output_path).exists())
        self.assertGreater(os.path.getsize(output_path), 1000)


if __name__ == "__main__":
    unittest.main()
