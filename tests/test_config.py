import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import config


class PostBridgeConfigTests(unittest.TestCase):
    def write_config(self, directory: str, payload: dict) -> None:
        with open(os.path.join(directory, "config.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_missing_platforms_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {"post_bridge": {"enabled": True}})

            with patch.object(config, "ROOT_DIR", temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], ["tiktok", "instagram"])

    def test_invalid_or_empty_platforms_do_not_expand_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "post_bridge": {
                        "enabled": True,
                        "platforms": ["youtube", "tik-tok"],
                    }
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], [])

    def test_non_list_platforms_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "post_bridge": {
                        "enabled": True,
                        "platforms": "tiktok",
                    }
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], [])

    def test_non_object_post_bridge_config_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "post_bridge": None,
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir):
                post_bridge_config = config.get_post_bridge_config()

        self.assertEqual(post_bridge_config["platforms"], ["tiktok", "instagram"])
        self.assertEqual(post_bridge_config["account_ids"], [])
        self.assertFalse(post_bridge_config["enabled"])

    def test_news_pipeline_accepts_expanded_source_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "news_pipeline": {
                        "sources": [
                            "geeknews",
                            "newstap",
                            "etnews",
                            "engadget",
                            "ars_technica",
                            "wired",
                            "mit_technology_review",
                            "apple_newsroom",
                            "google_keyword",
                            "microsoft_source",
                            "samsung_newsroom",
                            "samsung_mobile_press",
                            "openai_news",
                            "anthropic_news",
                            "google_deepmind_blog",
                            "google_news_technology",
                            "ifixit_news",
                            "toms_hardware",
                            "meeco_news",
                            "quasarzone_hardware_news",
                            "quasarzone_mobile_news",
                            "the_edit",
                            "unknown_source",
                        ],
                    }
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir):
                news_config = config.get_news_pipeline_config()

        self.assertEqual(
            news_config["sources"],
            [
                "geeknews",
                "newstap",
                "etnews",
                "engadget",
                "ars_technica",
                "wired",
                "mit_technology_review",
                "apple_newsroom",
                "google_keyword",
                "microsoft_source",
                "samsung_newsroom",
                "samsung_mobile_press",
                "openai_news",
                "anthropic_news",
                "google_deepmind_blog",
                "google_news_technology",
                "ifixit_news",
                "toms_hardware",
                "meeco_news",
                "quasarzone_hardware_news",
                "quasarzone_mobile_news",
                "the_edit",
            ],
        )

    def test_youtube_channel_config_uses_config_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "youtube_channel": {
                        "slug": "configured-slug",
                        "name": "Configured Channel",
                        "id": "UCconfigured",
                    }
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir), patch.dict(os.environ, {}, clear=True):
                youtube_config = config.get_youtube_channel_config()

        self.assertEqual(
            youtube_config,
            {
                "slug": "configured-slug",
                "name": "Configured Channel",
                "id": "UCconfigured",
            },
        )

    def test_youtube_channel_env_overrides_config_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "youtube_channel": {
                        "slug": "configured-slug",
                        "name": "Configured Channel",
                        "id": "UCconfigured",
                    }
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir), patch.dict(
                os.environ,
                {
                    "YOUTUBE_CHANNEL_SLUG": "env-slug",
                    "YOUTUBE_CHANNEL_NAME": "Env Channel",
                    "YOUTUBE_CHANNEL_ID": "UCenv",
                },
                clear=True,
            ):
                youtube_config = config.get_youtube_channel_config()

        self.assertEqual(
            youtube_config,
            {
                "slug": "env-slug",
                "name": "Env Channel",
                "id": "UCenv",
            },
        )

    def test_youtube_channel_config_defaults_without_personal_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {})

            with patch.object(config, "ROOT_DIR", temp_dir), patch.dict(os.environ, {}, clear=True):
                youtube_config = config.get_youtube_channel_config()

        self.assertEqual(youtube_config, {"slug": "youtube-channel", "name": "", "id": ""})

    def test_video_audio_quality_config_is_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(
                temp_dir,
                {
                    "background_music_volume": 5,
                    "background_music_fade_seconds": -2,
                },
            )

            with patch.object(config, "ROOT_DIR", temp_dir):
                volume = config.get_background_music_volume()
                fade_seconds = config.get_background_music_fade_seconds()

        self.assertEqual(volume, 1.0)
        self.assertEqual(fade_seconds, 0.0)

    def test_video_audio_quality_config_defaults_are_narration_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {})

            with patch.object(config, "ROOT_DIR", temp_dir):
                volume = config.get_background_music_volume()
                fade_seconds = config.get_background_music_fade_seconds()

        self.assertEqual(volume, 0.08)
        self.assertEqual(fade_seconds, 0.75)

    def test_tts_defaults_are_korean_shorts_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {})

            with patch.object(config, "ROOT_DIR", temp_dir):
                provider = config.get_tts_provider()
                voice = config.get_tts_voice()

        self.assertEqual(provider, "edge")
        self.assertEqual(voice, "ko-KR-SunHiNeural")

    def test_script_sentence_default_supports_readable_shorts_pacing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {})

            with patch.object(config, "ROOT_DIR", temp_dir):
                sentence_length = config.get_script_sentence_length()

        self.assertEqual(sentence_length, 6)

    def test_subtitle_max_chars_config_is_clamped_for_vertical_readability(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.write_config(temp_dir, {"subtitle_max_chars": 4})

            with patch.object(config, "ROOT_DIR", temp_dir):
                too_small = config.get_subtitle_max_chars()

            self.write_config(temp_dir, {"subtitle_max_chars": 200})
            with patch.object(config, "ROOT_DIR", temp_dir):
                too_large = config.get_subtitle_max_chars()

        self.assertEqual(too_small, 10)
        self.assertEqual(too_large, 40)


if __name__ == "__main__":
    unittest.main()
