import json
import os
import sys
import types
import unittest
import wave
from pathlib import Path

sys.modules.setdefault("srt_equalizer", types.SimpleNamespace(equalize_srt_file=lambda *args, **kwargs: None))
sys.modules.setdefault("termcolor", types.SimpleNamespace(colored=lambda text, *args, **kwargs: text))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def minimal_config():
    return {
        "verbose": False,
        "firefox_profile": "",
        "headless": True,
        "threads": 2,
        "zip_url": "",
        "is_for_kids": False,
        "twitter_language": "Korean",
        "google_maps_scraper": "",
        "google_maps_scraper_niche": "",
        "scraper_timeout": 300,
        "outreach_message_subject": "",
        "outreach_message_body_file": "",
        "assembly_ai_api_key": "",
        "tts_voice": "Jasper",
        "tts_provider": "silent",
        "font": "bold_font.ttf",
        "imagemagick_path": "/usr/bin/convert",
    }


class TtsProviderTests(unittest.TestCase):
    def setUp(self):
        self.config_path = PROJECT_ROOT / "config.json"
        self.original = self.config_path.read_text(encoding="utf-8") if self.config_path.exists() else None
        self.output = PROJECT_ROOT / ".mp" / "test-silent.wav"
        self.output.parent.mkdir(exist_ok=True)
        self.output.unlink(missing_ok=True)

    def tearDown(self):
        self.output.unlink(missing_ok=True)
        if self.original is None:
            self.config_path.unlink(missing_ok=True)
        else:
            self.config_path.write_text(self.original, encoding="utf-8")

    def write_config(self, data):
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def test_silent_tts_provider_imports_without_kittentts_and_writes_valid_wav(self):
        sys.modules.pop("classes.Tts", None)
        sys.modules.pop("kittentts", None)
        self.write_config(minimal_config())

        from classes.Tts import TTS

        result = TTS().synthesize("테스트 음성", str(self.output))

        self.assertEqual(result, str(self.output))
        self.assertTrue(self.output.exists())
        with wave.open(str(self.output), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 24000)
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertGreater(wav_file.getnframes(), 0)


if __name__ == "__main__":
    unittest.main()
