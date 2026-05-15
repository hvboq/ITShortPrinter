import os
import sys
import types
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


fake_kittentts = types.ModuleType("kittentts")
fake_kittentts.KittenTTS = object

fake_ollama = types.ModuleType("ollama")
fake_ollama.Client = object

fake_llm_provider = types.ModuleType("llm_provider")
fake_llm_provider.select_model = lambda model: None

fake_tts_module = types.ModuleType("classes.Tts")
fake_tts_module.TTS = object

fake_twitter_module = types.ModuleType("classes.Twitter")
fake_twitter_module.Twitter = object

fake_youtube_module = types.ModuleType("classes.YouTube")
fake_youtube_module.YouTube = object


def import_cron_with_fakes():
    fake_modules = {
        "kittentts": fake_kittentts,
        "ollama": fake_ollama,
        "llm_provider": fake_llm_provider,
        "classes.Tts": fake_tts_module,
        "classes.Twitter": fake_twitter_module,
        "classes.YouTube": fake_youtube_module,
    }
    sys.modules.pop("cron", None)
    with patch.dict(sys.modules, fake_modules):
        import cron
    return cron


class CronPostBridgeTests(unittest.TestCase):
    def test_crosspost_does_not_run_when_youtube_upload_fails(self) -> None:
        cron = import_cron_with_fakes()

        with patch.object(cron, "maybe_crosspost_youtube_short") as crosspost_mock, patch.object(
            cron, "YouTube"
        ) as youtube_cls_mock, patch.object(cron, "TTS") as tts_cls_mock, patch.object(
            cron, "get_accounts"
        ) as get_accounts_mock, patch.object(
            cron, "select_model"
        ) as select_model_mock, patch.object(
            cron, "get_verbose"
        ) as get_verbose_mock:
            get_verbose_mock.return_value = False
            get_accounts_mock.return_value = [
                {
                    "id": "yt-1",
                    "nickname": "Channel",
                    "firefox_profile": "/tmp/profile",
                    "niche": "finance",
                    "language": "English",
                }
            ]
            youtube_instance = youtube_cls_mock.return_value
            youtube_instance.upload_video.return_value = False
            youtube_instance.video_path = "/tmp/video.mp4"
            youtube_instance.metadata = {"title": "Title"}

            with patch.object(
                sys,
                "argv",
                ["cron.py", "youtube", "yt-1", "llama3.2:3b"],
            ):
                cron.main()

            select_model_mock.assert_called_once_with("llama3.2:3b")
            tts_cls_mock.assert_called_once()
            youtube_instance.generate_video.assert_called_once()
            youtube_instance.upload_video.assert_called_once()
            crosspost_mock.assert_not_called()

        sys.modules.pop("cron", None)


if __name__ == "__main__":
    unittest.main()
