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


if __name__ == "__main__":
    unittest.main()
