import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

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
        "font": "bold_font.ttf",
        "imagemagick_path": "/usr/bin/convert",
    }


class LocalAiConfigTests(unittest.TestCase):
    def setUp(self):
        self.config_path = PROJECT_ROOT / "config.json"
        self.original = self.config_path.read_text(encoding="utf-8") if self.config_path.exists() else None

    def tearDown(self):
        if self.original is None:
            self.config_path.unlink(missing_ok=True)
        else:
            self.config_path.write_text(self.original, encoding="utf-8")

    def write_config(self, data):
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def test_ollama_defaults_target_docker_host_and_gemma_model(self):
        import config

        self.write_config(minimal_config())

        self.assertEqual(config.get_ollama_base_url(), "http://host.docker.internal:11434")
        self.assertEqual(config.get_ollama_model(), "gemma4:e4b")

    def test_ollama_base_url_can_be_overridden_by_environment(self):
        import config

        cfg = minimal_config()
        cfg["ollama_base_url"] = "http://host.docker.internal:11434"
        self.write_config(cfg)

        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://host.docker.internal:11434"}, clear=False):
            self.assertEqual(config.get_ollama_base_url(), "http://host.docker.internal:11434")

    def test_google_api_key_falls_back_for_gemini_image_generation(self):
        import config

        cfg = minimal_config()
        cfg["nanobanana2_api_key"] = ""
        self.write_config(cfg)

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "google-key"}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            self.assertEqual(config.get_nanobanana2_api_key(), "google-key")


if __name__ == "__main__":
    unittest.main()
